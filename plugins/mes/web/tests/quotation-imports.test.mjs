import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const requireWeb = createRequire(
  new URL("../../../core/web/package.json", import.meta.url),
);
const ts = requireWeb("typescript");
function load(path, dependencies) {
  const exports = {};
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  runInNewContext(
    ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText,
    {
      exports,
      require: (name) => {
        if (name in dependencies) return dependencies[name];
        throw Error(`Unexpected dependency: ${name}`);
      },
    },
  );
  return exports;
}
const api = load("../src/views/mes/quotations/api.ts", {
  "@/utils/http": {},
  "@/utils/auth": {},
});
const { planDrawings, bindDrawing, mergeExcel } = load(
  "../src/views/mes/quotations/imports.ts",
  { "./api": api },
);
const line = (drawing_no = "") => ({ ...api.newLine(), drawing_no });
const file = (name, size = 20) => ({ name, size });

test("Excel creation reuses the initial A revision row and preserves an existing drawing revision", () => {
  const items = [
    {
      row_no: 2,
      drawing_no: "NEW",
      description: "新货品",
      quantity: 2,
      customer_material: "钢",
      surface_treatment: "",
      note: "",
    },
    {
      row_no: 3,
      drawing_no: "EXISTING",
      description: "已有货品",
      quantity: 3,
      customer_material: "钢",
      surface_treatment: "",
      note: "",
    },
  ];
  const existing = { ...line("EXISTING"), drawing_revision: "B", weight_kg: 0.125 };
  const result = mergeExcel([line(), existing], items);
  assert.equal(result.lines.length, 2);
  assert.equal(result.lines[0].drawing_revision, "A");
  assert.equal(result.lines[1].drawing_revision, "B");
  assert.equal(existing.drawing_revision, "B");
  assert.equal(result.lines[1].weight_kg, 0.125);
  assert.ok(!("weight_kg" in api.requirements({ lines: result.lines }).lines[1]));
});

test("existing mode selects six drawing numbers from fifty files without adding other goods", () => {
  const lines = Array.from({ length: 6 }, (_, index) => line(`P${index}`));
  const files = Array.from({ length: 50 }, (_, index) => file(`p${index}.PDF`));
  const plan = planDrawings(lines, files, undefined, "existing");
  assert.equal(plan.filter((row) => !row.is_skipped).length, 6);
  assert.equal(
    plan.filter((row) => row.is_skipped && row.status === "已跳过").length,
    44,
  );
  assert.ok(plan.every((row) => !row.error));
  assert.throws(() => bindDrawing(lines, plan[10], {}), /已跳过/);
  assert.equal(lines.length, 6);
  assert.ok(lines.every((row) => row.files.length === 0));
});

test("add mode groups PDF and model into one new item while retaining existing attachments", () => {
  const lines = [line("P1")];
  lines[0].files = [{ kind: "pdf", attachment_id: "old-pdf" }];
  const plan = planDrawings(
    lines,
    [file("P1.step"), file("NEW.pdf"), file("NEW.stp")],
    undefined,
    "add",
  );
  assert.ok(plan.every((row) => !row.is_skipped && !row.error));
  plan.forEach((row, index) =>
    bindDrawing(lines, row, { kind: row.kind, attachment_id: `new-${index}` }),
  );
  assert.equal(lines.length, 2);
  assert.equal(
    lines[0].files.find((row) => row.kind === "pdf").attachment_id,
    "old-pdf",
  );
  assert.equal(lines[1].files.length, 2);
  assert.equal(lines[1].drawing_no, "NEW");
  assert.equal(lines[1].drawing_revision, "A");
  assert.equal(lines[1].quantity, 1);
  assert.equal(lines[1].customer_material, "");
});

test("skipped duplicates, oversized and unrelated files do not block matched files", () => {
  const lines = [line("P1")];
  const files = [
    file("P1.pdf"),
    file("unrelated.pdf", 201 * 1024 * 1024),
    file("unrelated.pdf"),
    ...Array.from({ length: 110 }, (_, index) => file(`other-${index}.step`)),
  ];
  const plan = planDrawings(lines, files, undefined, "existing");
  assert.equal(plan.filter((row) => !row.is_skipped).length, 1);
  assert.ok(plan.every((row) => !row.error));
  const adding = planDrawings(lines, files, undefined, "add");
  assert.ok(adding[1].error);
});

test("more than 100 files and 200MB can be queued while the per-file limit is enforced", () => {
  const lines = Array.from({ length: 101 }, (_, index) => line(`P${index}`));
  const files = lines.map((row) =>
    file(`${row.drawing_no}.pdf`, 3 * 1024 * 1024),
  );
  const plan = planDrawings(lines, files, undefined, "existing");
  assert.equal(plan.length, 101);
  assert.ok(plan.every((row) => !row.error && !row.is_skipped));
  const oversized = planDrawings(
    lines,
    [file("P0.step", 20 * 1024 * 1024 + 1)],
    undefined,
    "existing",
  );
  assert.match(oversized[0].error, /20MB/);
});

test("matched duplicate model files require correction before upload", () => {
  const plan = planDrawings(
    [line("P1")],
    [file("P1.stp"), file("p1.STEP")],
    undefined,
    "existing",
  );
  assert.ok(plan.every((row) => !row.is_skipped && row.error.includes("重复")));
});

test("multiple versions never guess a matching target", () => {
  const plan = planDrawings(
    [line("P1"), { ...line("p1"), drawing_revision: "B" }],
    [file("P1.pdf")],
    undefined,
    "existing",
  );
  assert.match(plan[0].error, /多个版本/);
  assert.equal(plan[0].is_skipped, false);
});

test("empty existing list skips all files, while add mode reuses a blank item", () => {
  const lines = [line()];
  const files = [file("NEW.pdf"), file("new.step")];
  assert.ok(
    planDrawings(lines, files, undefined, "existing").every(
      (row) => row.is_skipped,
    ),
  );
  const plan = planDrawings(lines, files, undefined, "add");
  plan.forEach((row) =>
    bindDrawing(lines, row, { kind: row.kind, attachment_id: row.file.name }),
  );
  assert.equal(lines.length, 1);
  assert.equal(lines[0].files.length, 2);
});

test("row upload targets the selected item even when filenames differ", () => {
  const lines = [line("P1")];
  const plan = planDrawings(
    lines,
    [file("a.pdf"), file("b.step")],
    lines[0],
    "existing",
  );
  assert.ok(
    plan.every(
      (row) => !row.error && !row.is_skipped && row.drawing_no === "P1",
    ),
  );
  const duplicate = planDrawings(
    lines,
    [file("a.pdf"), file("b.pdf")],
    lines[0],
    "existing",
  );
  assert.ok(duplicate.every((row) => row.error.includes("重复")));
});

test("existing mode at the goods limit ignores new drawing numbers", () => {
  const lines = Array.from({ length: 500 }, (_, index) => line(`P${index}`));
  const files = [file("P0.pdf"), file("NEW.pdf")];
  assert.equal(
    planDrawings(lines, files, undefined, "existing")[1].is_skipped,
    true,
  );
  assert.throws(
    () => planDrawings(lines, files, undefined, "add"),
    /超过 500 项/,
  );
});
