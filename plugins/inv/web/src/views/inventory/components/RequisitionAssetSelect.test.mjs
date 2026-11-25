import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import * as vue from "vue";
import ts from "typescript";
import { parse } from "vue/compiler-sfc";

const script = parse(
  readFileSync(
    new URL("./RequisitionAssetSelect.vue", import.meta.url),
    "utf8",
  ),
).descriptor.scriptSetup.content;
const code = ts.transpileModule(
  `${script}\nexport { selectedIds, selections, selectedQuantity, mismatch, optionRows, page, load, visible, search, select, updateQuantity, shortNo, number, status, disabledOption, error, loading };`,
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  },
).outputText;

function view(t, api, overrides = {}) {
  const props = vue.reactive({
    modelValue: { selections: [] },
    itemId: "pc",
    warehouseId: "warehouse",
    itemName: "实训电脑",
    unit: "台",
    quantity: 2,
    ...overrides,
  });
  const state = {},
    requests = [],
    events = [];
  const scope = vue.effectScope();
  scope.run(() =>
    runInNewContext(code, {
      exports: state,
      defineProps: () => props,
      defineEmits: () => (event, value) => {
        events.push({ event, value });
        props.modelValue = value;
      },
      require(name) {
        if (name === "vue") return vue;
        if (name.includes("ListPagination")) return {};
        if (name === "@/utils/auth") return { hasPerms: () => true };
        if (name === "@/utils/http")
          return { getHttpErrorMessage: (error) => error.message };
        return {
          listStockAssetBindings: (params) => {
            requests.push(params);
            return api(params);
          },
        };
      },
    }),
  );
  t.after(() => scope.stop());
  return { props, state, requests, events };
}
const binding = (id, changes = {}) => ({
  id,
  asset_no: `ZC-20261112-${id.padStart(32, "0")}`,
  quantity: "1.000",
  management_mode: "individual",
  stock_status_code: "available",
  status_code: "idle",
  registration_status_code: "confirmed",
  ...changes,
});

test("下拉直接多选并按实际发放数量限制，取消选择实时更新", async (t) => {
  const rows = [binding("1"), binding("2"), binding("3")];
  const f = view(t, async () => ({ data: { items: rows, total: 3 } }));
  await f.state.load();
  f.state.select(["1", "2"]);
  assert.equal(f.state.selectedQuantity.value, 2);
  assert.equal(f.state.disabledOption(rows[2]), true);
  assert.equal(f.state.disabledOption(rows[0]), false);
  assert.equal(f.props.modelValue.selections[0].quantity, "1");
  assert.equal("department_id" in f.props.modelValue.selections[0], false);
  f.state.select(["2"]);
  assert.equal(f.state.selectedQuantity.value, 1);
  assert.equal(f.state.mismatch.value, true);
  assert.equal(f.state.disabledOption(rows[2]), false);
  f.props.quantity = 1;
  assert.equal(f.state.mismatch.value, false);
});

test("跨分页与搜索保留已选资产，长编号简写而完整编号仍可核对", async (t) => {
  const first = binding("a"),
    second = binding("b");
  const f = view(t, async (params) => ({
    data: {
      items: params.page === 1 && !params.keyword ? [first] : [second],
      total: 40,
    },
  }));
  await f.state.load();
  f.state.select(["a"]);
  f.state.page.value = 2;
  await f.state.load();
  assert.equal(f.state.optionRows.value.length, 2);
  f.state.select(["a", "b"]);
  f.state.search(" SN-2 ");
  await vue.nextTick();
  assert.equal(f.requests.at(-1).page, 1);
  assert.equal(f.requests.at(-1).keyword, "SN-2");
  assert.equal(f.state.selections.value.length, 2);
  assert.equal(f.state.shortNo(first.asset_no), "ZC-20261112…0000000a");
  assert.equal(f.state.optionRows.value[0].asset_no, first.asset_no);
  assert.equal(f.state.status(first), "可发放");
});

test("仓库切换忽略迟到响应并清空旧选择，失败可重试", async (t) => {
  let complete;
  const f = view(
    t,
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  const pending = f.state.load();
  f.props.warehouseId = "other";
  await vue.nextTick();
  complete({ data: { items: [binding("stale")], total: 1 } });
  await pending;
  assert.equal(f.state.optionRows.value.length, 0);
  assert.equal(f.state.loading.value, false);
  const failing = view(t, async () => {
    throw new Error("网络异常");
  });
  await failing.state.load();
  assert.equal(failing.state.error.value, "网络异常");
  assert.equal(failing.state.loading.value, false);
});

test("历史数量资产按剩余实发量关联，小数不会产生过长精度", async (t) => {
  const f = view(
    t,
    async () => ({
      data: {
        items: [
          binding("a", { management_mode: "batch", quantity: "0.100" }),
          binding("b", { management_mode: "batch", quantity: "0.300" }),
        ],
        total: 2,
      },
    }),
    { quantity: 0.3 },
  );
  await f.state.load();
  f.state.select(["a", "b"]);
  assert.equal(f.props.modelValue.selections[1].quantity, "0.2");
  assert.equal(f.state.selectedQuantity.value, 0.3);
  f.state.updateQuantity("b", 0.1);
  assert.equal(f.state.mismatch.value, true);
  f.props.disabled = true;
  f.state.select([]);
  assert.equal(f.state.selections.value.length, 2);
});
