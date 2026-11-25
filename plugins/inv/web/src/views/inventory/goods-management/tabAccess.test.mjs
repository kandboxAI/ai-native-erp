import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const exports = {};
runInNewContext(
  ts.transpileModule(
    readFileSync(new URL("./tabAccess.ts", import.meta.url), "utf8"),
    {
      compilerOptions: { module: ts.ModuleKind.CommonJS }
    }
  ).outputText,
  { exports }
);

test("warehouse-only access selects a usable pane instead of an inaccessible default item pane", () => {
  const tabs = exports.accessibleMaterialTabs(
    permission => permission === "inventory_warehouse:list"
  );
  assert.deepEqual([...tabs], ["warehouses"]);
  assert.equal(exports.selectMaterialTab("items", tabs), "warehouses");
});

test("permission revocation selects another authorized pane, or none when all access is removed", () => {
  const tabs = exports.accessibleMaterialTabs(
    permission => permission === "supplier:list"
  );
  assert.equal(exports.selectMaterialTab("warehouses", tabs), "suppliers");
  assert.equal(exports.selectMaterialTab("suppliers", tabs), "suppliers");
  assert.equal(exports.selectMaterialTab("suppliers", []), "");
  assert.equal(exports.accessibleMaterialTabs(() => false).length, 0);
});

test("legacy rule permissions do not expose a configuration pane", () => {
  const tabs = exports.accessibleMaterialTabs(
    permission => permission.startsWith("inventory_stock_order_type:")
  );
  assert.equal(tabs.length, 0);
});
