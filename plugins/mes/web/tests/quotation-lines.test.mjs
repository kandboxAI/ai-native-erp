import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const ts = createRequire(
  new URL("../../../../web/package.json", import.meta.url),
)("typescript");
const exports = {};
runInNewContext(
  ts.transpileModule(
    readFileSync(
      new URL("../src/views/mes/quotations/lines.ts", import.meta.url),
      "utf8",
    ),
    {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    },
  ).outputText,
  { exports },
);
const { matchesDrawing, pageItems, canSelectAdoption, reviewAdoptions } =
  exports;

test("matching history fills only blank engineering prices and retains an auditable source", () => {
  const reference = {
    is_compatible: true,
    currency: "EUR",
    unit_price: "12.80",
    quantity: "10",
    quoted_material: "AL6082",
    weight_kg: "0.5",
    quote_no: "BJ-OLD",
    revision: 2,
    drawing_revision: "A",
  };
  const blank = {
    drawing_no: "PM-001",
    unit_price: null,
    quoted_material: "",
    weight_kg: null,
    engineering_note: "",
    historical_reference: reference,
  };
  const manual = { ...blank, unit_price: 20 };
  const adopted = { ...blank, adopted_cnc_quote_id: "adopted" };
  const changed = {
    ...blank,
    historical_reference: { ...reference, is_compatible: false },
  };
  const foreign = {
    ...blank,
    historical_reference: { ...reference, currency: "CNY" },
  };
  const quote = {
    status_code: "pending",
    currency: "EUR",
    lines: [blank, manual, adopted, changed, foreign],
  };
  exports.fillHistoricalPrices(quote);
  assert.equal(blank.unit_price, 12.8);
  assert.equal(blank.quoted_material, "AL6082");
  assert.equal(blank.weight_kg, 0.5);
  assert.match(blank.engineering_note, /BJ-OLD R2/);
  assert.equal(manual.unit_price, 20);
  assert.equal(adopted.unit_price, null);
  assert.equal(changed.unit_price, null);
  assert.equal(foreign.unit_price, null);
  const note = blank.engineering_note;
  exports.fillHistoricalPrices(quote);
  assert.equal(blank.engineering_note, note);
  const review = { ...blank, unit_price: null };
  exports.fillHistoricalPrices({
    ...quote,
    status_code: "review",
    lines: [review],
  });
  assert.equal(review.unit_price, null);
});
const goods = (id = "line") => ({
  id,
  drawing_no: "PM-Y2008130-01",
  unit_price: 18.5,
  cnc_records: [{ id: "record", status_code: "completed", is_stale: false }],
});

test("drawing search is trimmed and case insensitive and retains original form objects", () => {
  const lines = Array.from({ length: 120 }, (_, index) => ({
    ...goods(String(index)),
    drawing_no: `PM-${String(index).padStart(3, "0")}`,
  }));
  lines[95].unit_price = 48.8;
  const filtered = lines.filter((line) => matchesDrawing(line, "  pm-09 "));
  assert.equal(filtered.length, 10);
  assert.equal(
    filtered.find((line) => line.id === "95"),
    lines[95],
  );
  pageItems(filtered, 1, 5)[0].unit_price = 29;
  assert.equal(lines[90].unit_price, 29);
  assert.equal(lines[95].unit_price, 48.8);
  assert.equal(lines.length, 120);
});

test("pagination covers 120 items once without changing their order or values", () => {
  const lines = Array.from({ length: 120 }, (_, index) => goods(String(index)));
  const result = Array.from({ length: 6 }, (_, index) =>
    pageItems(lines, index + 1, 20),
  ).flat();
  assert.equal(new Set(result.map((line) => line.id)).size, 120);
  assert.equal(result[119], lines[119]);
});

test("only completed, current, persisted goods are selectable", () => {
  assert.equal(canSelectAdoption(goods()), true);
  for (const status_code of ["queued", "running", "failed", "idle"]) {
    const line = goods();
    line.cnc_records[0].status_code = status_code;
    assert.equal(canSelectAdoption(line), false);
  }
  const stale = goods();
  stale.cnc_records[0].is_stale = true;
  assert.equal(canSelectAdoption(stale), false);
  assert.equal(canSelectAdoption({ ...goods(), id: undefined }), false);
});

test("adoption always uses the AI quote and keeps the old price only for comparison", () => {
  const item = {
    line_id: "line",
    can_adopt: true,
    cnc_quote_id: "snapshot",
    cnc_unit_price: "122.47",
    cnc_currency: "CNY",
    suggested_unit_price: "15.31",
    message: "可采用",
  };
  for (const oldPrice of [null, 0, 12, 18.88]) {
    const line = { ...goods(), unit_price: oldPrice };
    const result = reviewAdoptions([line], [item])[0];
    assert.equal(result.state, "ready");
    assert.equal(result.unit_price, 15.31);
    assert.equal(result.original_unit_price, oldPrice);
    assert.equal(line.unit_price, oldPrice);
  }
  assert.equal(reviewAdoptions([], [item])[0].state, "blocked");
  assert.equal(
    reviewAdoptions(
      [goods()],
      [{ ...item, can_adopt: false, message: "依据已变化" }],
    )[0].message,
    "依据已变化",
  );
});

test("missing or invalid AI quote cannot fall back to an existing manual price", () => {
  const base = {
    line_id: "line",
    can_adopt: true,
    cnc_quote_id: "snapshot",
    message: "可采用",
  };
  for (const suggested_unit_price of [null, NaN, Infinity, -1, 100000001]) {
    assert.equal(
      reviewAdoptions(
        [{ ...goods(), unit_price: 12 }],
        [{ ...base, suggested_unit_price }],
      )[0].state,
      "blocked",
    );
  }
  const missing = reviewAdoptions(
    [goods()],
    [{ ...base, price_message: "请填写汇率" }],
  )[0];
  assert.equal(missing.state, "blocked");
  assert.equal(missing.message, "请填写汇率");
});
