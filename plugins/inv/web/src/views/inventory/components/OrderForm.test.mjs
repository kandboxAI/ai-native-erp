import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import * as vue from "vue";
import dayjs from "dayjs";
import { compileScript, parse } from "vue/compiler-sfc";
import ts from "typescript";

const source = readFileSync(new URL("./OrderForm.vue", import.meta.url), "utf8");
const exposed = `\ndefineExpose({ header, lines, itemOptions, itemLoading,
  availabilityLoading, searchItems, refreshAvailable, onFromWarehouseChange, onItemChange,
  loadLots, itemChoices, save, buildLines, assetDepartment, setAssetDepartment, onToWarehouseChange, loadOrder,
  types, isPurchaseInbound, canSelectExistingAsset, assetSelectionPurpose, clearAssetSelection });`;
const { descriptor } = parse(source.replace("</script>", `${exposed}\n</script>`));
const compiled = ts.transpileModule(compileScript(descriptor, { id: "order-stock-test" }).content, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true, target: ts.ScriptTarget.ES2022 }
}).outputText;
const ok = items => ({ code: 0, data: { items } });
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};
const settle = async () => {
  for (let i = 0; i < 3; i++) {
    await new Promise(resolve => setImmediate(resolve));
    await vue.nextTick();
  }
};
const material = (id, quantity = "5") => ({
  id, item_no: id, item_name: id, unit_code: "piece", available_quantity: quantity
});
const selected = (id, lot_id = "old-lot") => ({
  key: id, item_id: id, item_no: id, item_name: id, unit_code: "piece",
  quantity: 2, unit_price: 0, available_quantity: "10", lot_id, lots: [{ id: lot_id }]
});

async function form(t, business = "damage", overrides = {}, props = {}) {
  const calls = [];
  const errors = [], warnings = [];
  const direction = { inbound: "in", outbound: "out", damage: "out", transfer: "move", lend: "status", return: "status" }[business];
  const api = {
    listStockOrderTypeOptions: async () => ok([{ id: "type", type_no: business === "inbound" ? "PURCHASE_IN" : business.toUpperCase(), direction_code: direction,
      default_from_status_code: business === "return" ? "lent" : "available" }]),
    listWarehouseOptions: async () => ok([{ id: "A", org_id: "org-A" }, { id: "B", org_id: "org-B" }]),
    listPersonnelOptions: async () => ({ code: 0, data: { users: [], departments: [] } }),
    listSupplierOptions: async () => ok([]),
    listItemOptions: async params => { calls.push({ ...params }); return ok([]); },
    listLotOptions: async () => ok([]),
    toNumber: value => Number(value || 0),
    ...overrides
  };
  const exports = {};
  runInNewContext(compiled, {
    exports,
    require(id) {
      if (id === "vue") return vue;
      if (id === "dayjs") return dayjs;
      if (id === "element-plus") return { ElMessage: {
        error: message => errors.push(message), warning: message => warnings.push(message), success() {}
      }, ElMessageBox: {} };
      if (id === "@/utils/http") return { getHttpErrorMessage: (error, fallback) => error?.message || fallback };
      if (id === "./warehouseContext") return {
        preferredWarehouseId: overrides.preferredWarehouseId || (items => items.length === 1 ? items[0].id : ""),
        rememberWarehouse: overrides.rememberWarehouse || (() => {})
      };
      if (id.endsWith("/api/inventoryManagement") || id.endsWith("/api/invGoodsManagement")) return api;
      if (id.endsWith("StockAssetTrackingEditor.vue") || id.endsWith("WarehouseDepartmentSelect.vue")) return {};
      if (id === "./common") return {
        FORM_TEXT: { [business]: { noun: business } }, canForm: () => true,
        useInventoryMeta: () => ({ meta: vue.ref({}), loadMeta: async () => {}, unitLabel: value => value })
      };
      throw new Error(id);
    }
  });
  const renderer = vue.createRenderer({
    createElement: () => ({}), createComment: () => ({}), createText: () => ({}),
    setText() {}, setElementText() {}, parentNode() {}, nextSibling() {}, patchProp() {}, insert() {}, remove() {}
  });
  exports.default.render = () => null;
  const app = renderer.createApp(exports.default, { form: business, ...props });
  const vm = app.mount({});
  t.after(() => app.unmount());
  await settle();
  return { vm, api, calls, errors, warnings };
}

for (const business of ["damage", "outbound", "transfer", "lend"]) {
  test(`${business}: no catalog is loaded before a source warehouse is selected; selection uses positive warehouse stock`, async t => {
    const { vm, calls } = await form(t, business);
    assert.equal(calls.length, 0);
    vm.header.from_warehouse_id = "A";
    await vm.onFromWarehouseChange();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].warehouse_id, "A");
    assert.equal(calls[0].in_stock_only, true);
    assert.equal(calls[0].stock_status_code, "available");
  });
}

test("inbound can choose materials that have never been stocked", async t => {
  const { vm, calls } = await form(t, "inbound");
  assert.equal(calls.length, 0);
  vm.header.to_warehouse_id = "A";
  await vm.onToWarehouseChange();
  assert.equal(calls[0].in_stock_only, false);
  assert.equal(calls[0].inbound_warehouse_id, "A");
  assert.equal(calls[0].warehouse_id, undefined);
  vm.lines = [selected("new")];
  await vm.onFromWarehouseChange();
  assert.equal(vm.lines[0].item_id, "new");
});

test("切换入库目标仓库逐项校验，保留适用物料并清理不适用项", async t => {
  const { vm, warnings } = await form(t, "inbound", {
    listItemOptions: async params => ok(params.item_id
      ? (params.item_id === "shared" ? [material("shared", "0")] : [])
      : [material("new-book", "0")])
  });
  vm.header.to_warehouse_id = "A";
  vm.lines = [selected("shared"), selected("only-A")];
  vm.header.to_warehouse_id = "B";
  await vm.onToWarehouseChange();
  assert.equal(vm.lines[0].item_id, "shared");
  assert.equal(vm.lines[1].item_id, "");
  assert(warnings.at(-1).includes("1 行"));
  assert.equal(vm.itemOptions[0].id, "new-book");
});

test("旧目标仓库的迟到候选与明细核对响应不能覆盖新目标", async t => {
  const old = deferred();
  const { vm } = await form(t, "inbound", {
    listItemOptions: params => params.inbound_warehouse_id === "A"
      ? old.promise : Promise.resolve(ok([material("shared", "0")]))
  });
  vm.lines = [selected("shared")];
  vm.header.to_warehouse_id = "A";
  const first = vm.onToWarehouseChange();
  vm.header.to_warehouse_id = "B";
  await vm.onToWarehouseChange();
  old.resolve(ok([]));
  await first;
  assert.equal(vm.lines[0].item_id, "shared");
  assert.equal(vm.itemOptions[0].id, "shared");
  assert.equal(vm.availabilityLoading, false);
});

test("清空入库目标仓库清理选料，不退回全量物料候选", async t => {
  const { vm, calls } = await form(t, "inbound");
  vm.header.to_warehouse_id = "A";
  vm.lines = [selected("old")];
  vm.header.to_warehouse_id = "";
  await vm.onToWarehouseChange();
  assert.equal(vm.lines[0].item_id, "");
  assert.equal(calls.length, 0);
  assert.equal(vm.itemOptions.length, 0);
});

test("missing business type metadata does not fall back to an unscoped material catalog", async t => {
  const { calls } = await form(t, "damage", { listStockOrderTypeOptions: async () => ok([]) });
  assert.equal(calls.length, 0);
});

test("late keyword search cannot replace newer results in the same warehouse", async t => {
  const old = deferred();
  const { vm } = await form(t, "damage", {
    listItemOptions: params => params.keyword === "old" ? old.promise : Promise.resolve(ok([material("new")]))
  });
  vm.header.from_warehouse_id = "A";
  const first = vm.searchItems("old");
  await vm.searchItems("new");
  old.resolve(ok([material("old")]));
  await first;
  assert.equal(vm.itemOptions[0].id, "new");
});

test("changing source preserves valid materials, clears invalid materials and resets all batches", async t => {
  const calls = [];
  const api = async params => {
    calls.push(params);
    return ok(params.item_id ? [material(params.item_id, params.item_id === "valid" ? "7" : "0")] : [material("valid", "7")]);
  };
  const setup = await form(t, "damage", { listItemOptions: api });
  setup.vm.lines = [selected("valid"), selected("empty")];
  setup.vm.header.from_warehouse_id = "B";
  await setup.vm.onFromWarehouseChange();
  assert.equal(setup.vm.lines[0].item_id, "valid");
  assert.equal(setup.vm.lines[0].available_quantity, "7");
  assert.equal(setup.vm.lines[0].quantity, 2);
  assert.equal(setup.vm.lines[1].item_id, "");
  assert.ok(setup.vm.lines.every(row => row.lot_id === null && row.lots.length === 0));
  assert.ok(calls.filter(call => call.item_id).every(call => call.limit === 1 && call.warehouse_id === "B"));
  assert.equal(setup.warnings.length, 1);
});

test("old warehouse search and quantity responses cannot overwrite the current warehouse", async t => {
  const oldSearch = deferred(), oldQuantity = deferred();
  const { vm } = await form(t, "damage", {
    listItemOptions: async params => params.warehouse_id === "A"
      ? (params.item_id ? oldQuantity.promise : oldSearch.promise)
      : ok([material("same", "8")])
  });
  vm.lines = [selected("same")];
  vm.header.from_warehouse_id = "A";
  const first = vm.onFromWarehouseChange();
  vm.header.from_warehouse_id = "B";
  await vm.onFromWarehouseChange();
  oldSearch.resolve(ok([material("wrong")]));
  oldQuantity.resolve(ok([material("same", "0")]));
  await first;
  assert.equal(vm.itemOptions[0].id, "same");
  assert.equal(vm.lines[0].item_id, "same");
  assert.equal(vm.lines[0].available_quantity, "8");
});

test("late batch response cannot restore a batch from the previous warehouse", async t => {
  const oldLots = deferred();
  const { vm } = await form(t, "damage", {
    listItemOptions: async () => ok([material("same")]),
    listLotOptions: params => params.warehouse_id === "A" ? oldLots.promise : Promise.resolve(ok([{ id: "B-lot" }]))
  });
  vm.header.from_warehouse_id = "A";
  vm.lines = [selected("same")];
  const old = vm.loadLots(vm.lines[0]);
  vm.header.from_warehouse_id = "B";
  await vm.onFromWarehouseChange();
  await vm.loadLots(vm.lines[0]);
  oldLots.resolve(ok([{ id: "A-lot" }]));
  await old;
  assert.equal(vm.lines[0].lots[0].id, "B-lot");
  assert.equal(vm.lines[0].lot_id, null);
});

test("clearing source clears selected materials without querying all warehouses", async t => {
  const { vm, calls } = await form(t);
  vm.lines = [selected("same")];
  await vm.onFromWarehouseChange();
  assert.equal(vm.lines[0].item_id, "");
  assert.equal(calls.length, 0);
});

test("failed material search clears previous candidates and shows an error", async t => {
  const { vm, errors } = await form(t, "damage", { listItemOptions: async () => { throw new Error("query failed"); } });
  vm.header.from_warehouse_id = "A";
  vm.itemOptions = [material("old")];
  await vm.searchItems();
  assert.equal(vm.itemOptions.length, 0);
  assert.equal(vm.itemLoading, false);
  assert.equal(errors[0], "query failed");
});

test("return quantities use lent stock and refreshing a draft does not erase unavailable lines", async t => {
  const { vm, calls } = await form(t, "return");
  vm.header.from_warehouse_id = "A";
  vm.lines = [selected("historical")];
  await vm.refreshAvailable();
  assert.equal(vm.lines[0].item_id, "historical");
  assert.equal(vm.lines[0].available_quantity, 0);
  assert.equal(calls[0].item_id, "historical");
  assert.equal(calls[0].stock_status_code, "lent");
});

test("资产入库带出仓库部门，修改部门随明细保存，换仓库后重新带出", async t => {
  const { vm } = await form(t, "inbound", {
    listWarehouseOptions: async () => ok([
      { id: "A", org_id: "org-A", default_asset_department_id: "logistics-A" },
      { id: "B", org_id: "org-B", default_asset_department_id: "logistics-B" }
    ]),
    listItemOptions: async () => ok([{ ...material("computer"), is_asset_managed: true, default_asset_management_mode_code: "individual" }])
  });
  vm.header.to_warehouse_id = "A";
  await vm.onToWarehouseChange();
  vm.lines = [selected("computer")];
  vm.onItemChange(vm.lines[0], "computer");
  assert.equal(vm.lines[0].is_asset_managed, true);
  assert.equal(vm.assetDepartment(vm.lines[0]), "logistics-A");
  vm.setAssetDepartment(vm.lines[0], "teaching-A");
  assert.equal(vm.buildLines()[0].tracking.asset.registration.department_id, "teaching-A");
  vm.header.to_warehouse_id = "B";
  vm.onToWarehouseChange();
  await settle();
  assert.equal(vm.assetDepartment(vm.lines[0]), "logistics-B");
  assert.equal(vm.buildLines()[0].tracking, undefined);
});

test("编辑入库草稿保留责任配置，接口只读登记进度不回传", async t => {
  const { vm } = await form(t, "inbound", {
    getStockOrder: async () => ({ code: 0, data: {
      id: "draft", org_id: "org-A", order_type_id: "type", to_warehouse_id: "A",
      lines: [{ ...selected("computer"), is_asset_managed: true, default_asset_management_mode_code: "individual",
        tracking: { asset: { registration: { department_id: "teaching-A" }, registration_summary: { quantity: "2" }, selections: [] } } }]
    } })
  });
  await vm.loadOrder("draft");
  assert.equal(vm.lines[0].is_asset_managed, true);
  assert.equal(vm.assetDepartment(vm.lines[0]), "teaching-A");
  const value = vm.buildLines()[0].tracking.asset;
  assert.equal(value.registration.department_id, "teaching-A");
  assert.equal(value.registration_summary, undefined);
  vm.itemOptions = [material("paper")];
  vm.onItemChange(vm.lines[0], "paper");
  assert.equal(vm.lines[0].asset_tracking, undefined);
});

test("采购入库隐藏原资产选择，确认时只提交自动登记责任信息", async t => {
  let submitted;
  const { vm } = await form(t, "inbound", {
    createStockOrder: async data => { submitted = data; return { code: 0, data: { id: "new" } }; }
  });
  vm.header.to_warehouse_id = "A";
  vm.lines = [{ ...selected("computer"), is_asset_managed: true }];
  vm.setAssetDepartment(vm.lines[0], "department");
  assert.equal(vm.isPurchaseInbound, true);
  assert.equal(vm.canSelectExistingAsset, false);
  await vm.save("confirm");
  assert.equal(submitted.confirm, true);
  assert.equal(submitted.lines[0].tracking.asset.registration.department_id, "department");
  assert.equal(submitted.lines[0].tracking.asset.selections.length, 0);
});

test("台账入库入口查询资产物料，多行和多件通过同一入库请求提交", async t => {
  let submitted;
  const { vm, calls } = await form(t, "inbound", {
    createStockOrder: async data => { submitted = data; return { code: 0, data: { id: "new" } }; },
    listStockOrderTypeOptions: async () => ok([{ id: "other", type_no: "OTHER_IN", direction_code: "in" }]),
    listWarehouseOptions: async () => ok([{ id: "A", org_id: "org-A", default_asset_department_id: "dept" }]),
  }, { assetOnly: true });
  assert.equal(calls[0].is_asset_managed, true);
  assert.equal(vm.canSelectExistingAsset, false);
  vm.lines = [
    { ...selected("computer"), quantity: 10, is_asset_managed: true, default_asset_management_mode_code: "individual" },
    { ...selected("chair"), quantity: 20, is_asset_managed: true, default_asset_management_mode_code: "batch" },
  ];
  await vm.save("confirm");
  assert.equal(submitted.to_warehouse_id, "A");
  assert.equal(submitted.confirm, true);
  assert.equal(submitted.lines.length, 2);
  assert.equal(submitted.lines[0].quantity, 10);
  assert.equal(submitted.lines[1].quantity, 20);
  assert.ok(vm.lines.every(row => vm.assetDepartment(row) === "dept"));
  assert.ok(submitted.lines.every(row => row.tracking === undefined)); // 未覆盖部门时由后端沿用仓库配置。
  assert.ok(submitted.lines.every(row => !row.asset_no));
});

test("制造仓库范围和初始单据类型可与资产登记入口同时使用", async t => {
  const warehouseQueries = [], typeQueries = [];
  let submitted;
  const { vm, calls, errors } = await form(t, "inbound", {
    listStockOrderTypeOptions: async params => {
      typeQueries.push(params);
      return ok([
        { id: "purchase", type_no: "PURCHASE_IN", direction_code: "in" },
        { id: "tool", type_no: "MES_TOOL_IN", direction_code: "in", required_field_config: { warehouse_type_codes: ["mes_tool"] } }
      ]);
    },
    listWarehouseOptions: async params => {
      warehouseQueries.push(params);
      return ok([
        { id: "A", org_id: "org-A", warehouse_type_code: "mes_tool", default_asset_department_id: "dept" },
        { id: "B", org_id: "org-B", warehouse_type_code: "general" }
      ]);
    },
    createStockOrder: async data => { submitted = data; return { code: 0, data: { id: "new" } }; }
  }, { assetOnly: true, warehouseScopeKey: "mes", initialTypeNo: "MES_TOOL_IN" });
  assert.equal(errors.length, 0);
  assert(typeQueries.every(query => query.warehouse_scope_key === "mes"));
  assert(warehouseQueries.every(query => query.warehouse_scope_key === "mes"));
  assert.equal(vm.header.order_type_id, "tool");
  assert.equal(vm.header.to_warehouse_id, "A");
  assert.equal(calls[0].is_asset_managed, true);
  vm.lines = [{ ...selected("tool"), is_asset_managed: true }];
  assert.equal(vm.assetDepartment(vm.lines[0]), "dept");
  vm.setAssetDepartment(vm.lines[0], "chosen-dept");
  await vm.save("confirm");
  assert.equal(submitted.order_type_id, "tool");
  assert.equal(submitted.to_warehouse_id, "A");
  assert.equal(submitted.lines[0].tracking.asset.registration.department_id, "chosen-dept");
});

test("台账入库入口阻止普通物料、已有实物和资产小数数量", async t => {
  let saved = 0;
  const { vm, warnings } = await form(t, "inbound", {
    createStockOrder: async () => { saved++; return { code: 0, data: {} }; },
    listWarehouseOptions: async () => ok([{ id: "A", org_id: "org-A", default_asset_department_id: "dept" }]),
  }, { assetOnly: true });
  vm.lines = [{ ...selected("paper"), is_asset_managed: false }];
  await vm.save("draft");
  assert(warnings.at(-1).includes("已纳入资产管理"));
  vm.lines = [{ ...selected("computer"), is_asset_managed: true, asset_tracking: { selections: [{ binding_id: "old", quantity: "2" }] } }];
  await vm.save("confirm");
  assert(warnings.at(-1).includes("已有资产退库"));
  vm.lines = [{ ...selected("computer"), quantity: 1.5, is_asset_managed: true, default_asset_management_mode_code: "individual" }];
  await vm.save("confirm");
  assert(warnings.at(-1).includes("必须为整数"));
  assert.equal(saved, 0);
});

for (const assetOnly of [false, true]) {
  test(`新资产数量必须为整数，旧数量管理配置不能绕过校验（assetOnly=${assetOnly}）`, async t => {
    let saved = 0;
    const { vm, warnings } = await form(t, "inbound", {
      listWarehouseOptions: async () => ok([{ id: "A", org_id: "org-A", default_asset_department_id: "dept" }]),
      createStockOrder: async () => { saved++; return { code: 0, data: {} }; },
    }, { assetOnly });
    vm.lines = [{ ...selected("chair"), quantity: 1.5, is_asset_managed: true, default_asset_management_mode_code: "batch" }];
    await vm.save("confirm");
    assert(warnings.at(-1).includes("必须为整数"));
    assert.equal(saved, 0);
    if (!assetOnly) {
      vm.lines = [{ ...selected("paper"), quantity: 1.5, is_asset_managed: false }];
      await vm.save("confirm");
      assert.equal(saved, 1); // 普通库存物料仍可按公斤等计量单位记录小数数量。
    }
  });
}

test("其他入库允许选择退库原资产，切换采购后阻止误提交并要求明确清除", async t => {
  const submitted = [];
  const { vm, warnings } = await form(t, "inbound", {
    listStockOrderTypeOptions: async () => ok([
      { id: "purchase", type_no: "PURCHASE_IN", direction_code: "in" },
      { id: "other", type_no: "OTHER_IN", direction_code: "in" }
    ]),
    createStockOrder: async data => { submitted.push(data); return { code: 0, data: { id: "saved" } }; }
  });
  vm.header.order_type_id = "other";
  vm.header.to_warehouse_id = "A";
  await settle();
  vm.lines = [{ ...selected("computer"), is_asset_managed: true,
    asset_tracking: { selections: [{ binding_id: "issued", quantity: "2" }] } }];
  assert.equal(vm.canSelectExistingAsset, true);
  assert.equal(vm.assetSelectionPurpose, "stock_return");
  await vm.save("confirm");
  assert.equal(submitted[0].lines[0].tracking.asset.selections[0].binding_id, "issued");
  vm.header.order_type_id = "purchase";
  await settle();
  await vm.save("draft");
  assert.equal(submitted.length, 1);
  assert(warnings.at(-1).includes("采购入库不能关联已有资产"));
  assert.equal(vm.lines[0].asset_tracking.selections[0].binding_id, "issued");
  vm.clearAssetSelection(vm.lines[0]);
  await vm.save("draft");
  assert.equal(submitted.length, 2);
  assert.equal(submitted[1].lines[0].tracking, undefined);
});
