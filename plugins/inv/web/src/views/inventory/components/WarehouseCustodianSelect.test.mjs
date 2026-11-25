import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import * as vue from "vue";
import { compileScript, parse } from "vue/compiler-sfc";
import ts from "typescript";

const source = readFileSync(
  new URL("./WarehouseCustodianSelect.vue", import.meta.url),
  "utf8",
);
const { descriptor } = parse(
  source.replace(
    "</script>",
    "defineExpose({ options, loading, error, load });\n</script>",
  ),
);
const compiled = ts.transpileModule(
  compileScript(descriptor, { id: "department-select" }).content,
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  },
).outputText;
const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await vue.nextTick();
};
const ok = (value, org_id = "A") => ({
  code: 0,
  data: { items: [{ value, label: "后勤科", org_id }] },
});

async function mount(t, fetch, values = {}) {
  const props = vue.reactive({
    permissionKey: "inventory_warehouse:update",
    orgId: undefined,
    ...values,
  });
  const exports = {};
  runInNewContext(compiled, {
    exports,
    require(id) {
      if (id === "vue") return vue;
      if (id === "@/utils/http")
        return { getHttpErrorMessage: (error) => error.message };
      if (id.endsWith("api/inventoryManagement"))
        return { listWarehouseAssetCustodianOptions: fetch };
      throw new Error(id);
    },
  });
  exports.default.render = () => null;
  const renderer = vue.createRenderer({
    createElement: () => ({}),
    createComment: () => ({}),
    createText: () => ({}),
    setText() {},
    setElementText() {},
    parentNode() {},
    nextSibling() {},
    patchProp() {},
    insert() {},
    remove() {},
  });
  let instance;
  const app = renderer.createApp({
    setup: () => () =>
      vue.h(exports.default, {
        ...props,
        ref: (value) => {
          instance = value;
        },
      }),
  });
  app.mount({});
  t.after(() => app.unmount());
  await settle();
  return { props, vm: () => instance };
}

test("选择组织后按当前编辑权限加载保管人，切换为入库权限时重新查询", async (t) => {
  const calls = [];
  const f = await mount(t, async (params) => {
    calls.push({ ...params });
    return ok("dept");
  });
  assert.equal(calls.length, 0);
  f.props.orgId = "A";
  await settle();
  assert.deepEqual(calls[0], {
    org_id: "A",
    permission_key: "inventory_warehouse:update",
  });
  assert.equal(f.vm().options[0].value, "dept");
  f.props.permissionKey = "inventory_inbound:create";
  await settle();
  assert.equal(calls[1].permission_key, "inventory_inbound:create");
});

test("旧组织的迟到响应不覆盖当前组织，清空组织后不保留旧保管人", async (t) => {
  let finishOld;
  const f = await mount(
    t,
    (params) =>
      params.org_id === "A"
        ? new Promise((resolve) => {
            finishOld = resolve;
          })
        : Promise.resolve(ok("B-dept", "B")),
    { orgId: "A" },
  );
  assert.equal(f.vm().loading, true);
  f.props.orgId = "B";
  await settle();
  finishOld(ok("A-dept"));
  await settle();
  assert.equal(f.vm().options[0].value, "B-dept");
  f.props.orgId = undefined;
  await settle();
  assert.equal(f.vm().options.length, 0);
});

test("加载失败保留可重试错误，成功空列表与请求失败分开处理", async (t) => {
  let response = { code: 403, message: "无权选择责任保管人" };
  const f = await mount(t, async () => response, { orgId: "A" });
  assert.equal(f.vm().error, "无权选择责任保管人");
  assert.equal(f.vm().options.length, 0);
  response = ok("dept");
  await f.vm().load();
  assert.equal(f.vm().error, "");
  assert.equal(f.vm().options[0].value, "dept");
  response = { code: 0, data: { items: [] } };
  await f.vm().load();
  assert.equal(f.vm().error, "");
  assert.equal(f.vm().options.length, 0);
});
