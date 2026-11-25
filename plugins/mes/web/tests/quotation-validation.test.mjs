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
      new URL("../src/views/mes/quotations/validation.ts", import.meta.url),
      "utf8",
    ),
    {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    },
  ).outputText,
  { exports },
);
const { validateRequirements, validateEngineering, validateApproval } = exports;
const goods = () => ({
  drawing_no: "P1",
  description: "连接板",
  quantity: 10,
  customer_material: "6082",
  files: [],
  quoted_material: "AL6082",
  unit_price: 0,
  lead_days: 5,
});
const quote = () => ({
  title: "客户询价",
  customer_id: "customer",
  lines: [goods()],
});

test("basic requirements must be complete for both save and submission", () => {
  for (const submitting of [false, true]) {
    const body = quote();
    body.lines[0].customer_material = "  ";
    assert.throws(() => validateRequirements(body, submitting), /P1.*客户材料/);
  }
});

test("save accepts pending attachments but submission requires a drawing or model", () => {
  const body = quote();
  validateRequirements(body);
  assert.throws(() => validateRequirements(body, true), /P1.*图纸或模型/);
  body.lines[0].files = [{ attachment_id: "file", kind: "pdf" }];
  validateRequirements(body, true);
});

test("invalid quantity, empty inquiry and missing header data are blocked", () => {
  for (const quantity of [0, -1, NaN]) {
    const body = quote();
    body.lines[0].quantity = quantity;
    assert.throws(() => validateRequirements(body), /数量/);
  }
  assert.throws(
    () => validateRequirements({ ...quote(), lines: [] }),
    /至少录入/,
  );
  assert.throws(
    () => validateRequirements({ ...quote(), title: " " }),
    /询价名称/,
  );
  assert.throws(
    () => validateRequirements({ ...quote(), customer_id: "" }),
    /客户/,
  );
});

test("engineering submission requires material and price but not final delivery", () => {
  validateEngineering(quote());
  validateEngineering({ ...quote(), lines: [{ ...goods(), lead_days: null }] });
  for (const [field, value, label] of [
    ["quoted_material", "", "材料"],
    ["unit_price", null, "单价"],
  ]) {
    const body = quote();
    body.lines[0][field] = value;
    assert.throws(() => validateEngineering(body), new RegExp(`P1.*${label}`));
  }
});

test("approval requires final delivery for every item", () => {
  validateApproval(quote());
  for (const days of [null, 0, -1, 1.5, 3651]) {
    const body = quote();
    body.lines[0].lead_days = days;
    assert.throws(() => validateApproval(body), /P1.*最终交期/);
  }
});

test("approval rejects cleared, invalid main or quantity-tier prices before submitting", () => {
  for (const value of [null, NaN, Infinity, -1]) {
    const body = quote();
    body.lines[0].unit_price = value;
    assert.throws(() => validateApproval(body), /有效单价/);
    body.lines[0].unit_price = 10;
    body.lines[0].quantity_tiers = [
      { id: "tier", quantity: 100, unit_price: value },
    ];
    assert.throws(() => validateApproval(body), /所有数量档/);
  }
});
