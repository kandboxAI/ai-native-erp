import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import * as vue from "vue";
import { parse, compileScript } from "vue/compiler-sfc";
import ts from "typescript";

const { descriptor } = parse(
  readFileSync(new URL("./ItemTab.vue", import.meta.url), "utf8")
);
const compiled = ts.transpileModule(
  compileScript(descriptor, { id: "item-transfer-test" }).content,
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true
    }
  }
).outputText;

function setup(failure, overrides = {}) {
  const calls = [],
    downloads = [],
    errors = [];
  const api = new Proxy(
    {},
    { get: (_, key) => overrides[key] || (async () => ({ code: 0, data: { items: [], total: 0 } })) }
  );
  const exports = {};
  runInNewContext(compiled, {
    exports,
    require(id) {
      if (id === "vue") return { ...vue, onMounted() {} };
      if (id === "element-plus")
        return {
          ElMessage: { error: value => errors.push(value) },
          ElMessageBox: {}
        };
      if (id === "@element-plus/icons-vue") return {};
      if (id === "@/utils/auth") return { hasPerms: () => true };
      if (id.endsWith("/warehouseContext")) return {
        preferredWarehouseId: overrides.preferredWarehouseId || (items => items.length === 1 ? items[0].id : ""),
        rememberWarehouse: overrides.rememberWarehouse || (() => {})
      };
      if (id === "@/utils/http")
        return {
          getHttpErrorMessage: (error, fallback) => error?.message || fallback
        };
      if (id === "../components/common")
        return {
          useInventoryMeta: () => ({
            meta: vue.ref({}),
            loadMeta: async () => {},
            unitLabel: value => value
          })
        };
      if (id === "./GoodsImportDialog.vue")
        return { __esModule: true, default: {} };
      if (id.endsWith("/api/invGoodsImport"))
        return {
          async exportGoodsTemplateData(params) {
            calls.push(params);
            if (failure) throw new Error("下载失败");
            return "export-blob";
          },
          async downloadGoodsImportTemplate(kind) {
            calls.push(kind);
            return "template-blob";
          }
        };
      if (id.endsWith("/shared/utils/exportXlsxFromApi"))
        return {
          omitEmptyParams: params =>
            Object.fromEntries(
              Object.entries(params).filter(
                ([, value]) =>
                  value !== "" && value !== undefined && value !== null
              )
            ),
          saveExcelBlob: async (...args) => downloads.push(args)
        };
      if (id.startsWith("@plugins/inv/web/src/api/")) return api;
      throw new Error(id);
    }
  });
  return {
    state: exports.default.setup({}, { expose() {} }),
    calls,
    downloads,
    errors
  };
}

test("物料导出保留适用仓库、分类和停用筛选，排除分页及空参数", async () => {
  const { state, calls, downloads } = setup();
  Object.assign(state.query, {
    page: 8,
    page_size: 10,
    keyword: "笔",
    category_id: "category-id",
    applicable_warehouse_id: "warehouse-id",
    is_active: false
  });
  await state.exportItems();
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), {
    keyword: "笔",
    category_id: "category-id",
    applicable_warehouse_id: "warehouse-id",
    is_active: false
  });
  assert.deepEqual(downloads, [["export-blob", "物料档案"]]);
  assert.equal(state.exporting.value, false);
});

test("物料模板可直接从列表下载", async () => {
  const { state, calls, downloads } = setup();
  await state.downloadTemplate();
  assert.deepEqual(calls, ["product"]);
  assert.deepEqual(downloads, [["template-blob", "物料档案导入模板"]]);
  assert.equal(state.downloadingTemplate.value, false);
});

test("导出失败展示错误并恢复按钮，不下载错误内容", async () => {
  const { state, downloads, errors } = setup(true);
  await state.exportItems();
  assert.deepEqual(errors, ["下载失败"]);
  assert.equal(downloads.length, 0);
  assert.equal(state.exporting.value, false);
});

const settle = async () => { for (let index = 0; index < 3; index++) await Promise.resolve(); };
const warehouse = id => ({ id, warehouse_name: id, org_name: "学校", label: `学校 / ${id}` });

test("新增物料在同一个请求中提交多选适用仓库", async () => {
  const payloads = [];
  const { state } = setup(false, {
    listItemWarehouseOptions: async () => ({ code: 0, data: { items: [warehouse("A"), warehouse("B")] } }),
    createItem: async body => { payloads.push(body); return { code: 0 }; }
  });
  state.openDialog();
  await settle();
  Object.assign(state.form, { item_name: "教材", unit_code: "book", warehouse_ids: ["A", "B"] });
  state.formRef.value = { validate: async () => true };
  await state.save();
  assert.equal(payloads.length, 1);
  assert.deepEqual(Array.from(payloads[0].warehouse_ids), ["A", "B"]);
  assert.equal(payloads[0].expected_updated_at, undefined);
});

test("编辑保留已选关系并携带物料版本，仓库选项失败时禁止提交", async () => {
  const payloads = [];
  let fail = false;
  const { state } = setup(false, {
    listItemWarehouseOptions: async () => {
      if (fail) throw new Error("仓库选项读取失败");
      return { code: 0, data: { items: [warehouse("A")] } };
    },
    updateItem: async (_, body) => { payloads.push(body); return { code: 0 }; }
  });
  const row = { id: "one", item_name: "教材", unit_code: "book", updated_at: "2026-11-13T02:00:00Z",
    warehouse_ids: ["A", "B"], warehouses: [{ ...warehouse("B"), is_available: true }] };
  state.openDialog(row);
  await settle();
  state.formRef.value = { validate: async () => true };
  await state.save();
  assert.equal(payloads[0].expected_updated_at, row.updated_at);
  assert.deepEqual(Array.from(payloads[0].warehouse_ids), ["A", "B"]);
  assert.equal(state.formWarehouseOptions.value.find(option => option.id === "B").disabled, true);
  fail = true;
  state.openDialog(row);
  await settle();
  await state.save();
  assert.equal(payloads.length, 1);
  assert.match(state.warehouseOptionsError.value, /读取失败/);
});

test("旧新增弹窗的仓库选项响应不能覆盖后来打开的编辑弹窗", async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const { state } = setup(false, { listItemWarehouseOptions: action => action === "create"
    ? pending : Promise.resolve({ code: 0, data: { items: [warehouse("B")] } }) });
  state.openDialog();
  state.openDialog({ id: "one", warehouse_ids: ["B"], warehouses: [] });
  await settle();
  finish({ code: 0, data: { items: [warehouse("A")] } });
  await settle();
  assert.deepEqual(Array.from(state.editableWarehouseOptions.value.map(option => option.id)), ["B"]);
});

test("新增物料默认带入当前仓库，共享物料编辑只提交仓库关系", async () => {
  const payloads = [];
  const { state } = setup(false, {
    listItemWarehouseOptions: async () => ({ code: 0, data: { items: [warehouse("A")] } }),
    updateItem: async (_, body) => { payloads.push(body); return { code: 0 }; }
  });
  state.openDialog();
  await settle();
  assert.deepEqual(Array.from(state.form.warehouse_ids), ["A"]);
  state.openDialog({ id: "shared", item_name: "共用教材", unit_code: "book", warehouse_ids: ["A"],
    updated_at: "2026-11-13T03:00:00Z", can_edit_base_fields: false, warehouses: [] });
  await settle();
  state.form.item_name = "不应提交";
  state.formRef.value = { validate: async () => true };
  await state.save();
  assert.deepEqual(Object.keys(payloads[0]).sort(), ["expected_updated_at", "warehouse_ids"]);
});
