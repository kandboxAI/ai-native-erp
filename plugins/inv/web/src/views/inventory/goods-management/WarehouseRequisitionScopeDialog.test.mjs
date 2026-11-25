import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import * as vue from "vue";
import { compileScript, parse } from "vue/compiler-sfc";
import ts from "typescript";

const source = readFileSync(
  new URL("./WarehouseRequisitionScopeDialog.vue", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(
  compileScript(parse(source).descriptor, { id: "scope-dialog" }).content,
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  },
).outputText;
const fixture = (id) => ({
  warehouse_id: id,
  warehouse_name: id,
  owner_org_id: "school",
  owner_org_name: "示例总部",
  expected_updated_at: "2026-11-10T12:00:00+08:00",
  recipient_org_ids: ["east"],
  organizations: [
    { id: "east", org_name: "示例分部", parent_id: "school", is_available: true },
    {
      id: "department",
      org_name: "运营组",
      parent_id: "east",
      is_available: true,
    },
    { id: "old", org_name: "旧组织", parent_id: null, is_available: false },
  ],
});
const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await vue.nextTick();
};

async function dialog(
  t,
  read = async (id) => ({ code: 0, data: fixture(id) }),
) {
  const calls = [],
    events = [],
    messages = [];
  let fail = false,
    gate;
  const exports = {};
  runInNewContext(compiled, {
    exports,
    require(id) {
      if (id === "vue") return vue;
      if (id === "element-plus")
        return {
          ElMessage: {
            success: (message) => messages.push(message),
            error: (message) => messages.push(message),
          },
        };
      if (id === "@/utils/http")
        return { getHttpErrorMessage: (reason) => reason.message };
      if (id.includes("inventoryManagement"))
        return {
          getWarehouseRequisitionScope: read,
          saveWarehouseRequisitionScope: async (id, data) => {
            calls.push({ id, data });
            if (gate) await gate;
            if (fail) throw new Error("已被其他人修改");
            return {
              code: 0,
              data: {
                ...fixture(id),
                recipient_org_ids: data.recipient_org_ids,
              },
            };
          },
        };
      throw new Error(id);
    },
  });
  const props = vue.reactive({ modelValue: true, warehouseId: "warehouse-1" });
  const scope = vue.effectScope();
  const state = scope.run(() =>
    exports.default.setup(props, {
      expose() {},
      emit: (...args) => events.push(args),
    }),
  );
  t.after(() => scope.stop());
  await settle();
  return {
    state,
    props,
    calls,
    events,
    messages,
    fail: (value) => (fail = value),
    gate: (value) => (gate = value),
  };
}

test("加载当前范围并显示组织路径和失效提示", async (t) => {
  const view = await dialog(t);
  assert.equal(view.state.selected.value[0], "east");
  assert.equal(
    view.state.choices.value.find((row) => row.id === "department").label,
    "示例分部 / 运营组",
  );
  assert.match(
    view.state.choices.value.find((row) => row.id === "old").label,
    /失效/,
  );
});

test("保存仅提交选中的组织与并发版本，允许清空额外共享", async (t) => {
  const view = await dialog(t);
  view.state.selected.value = [];
  await view.state.save();
  assert.equal(view.calls[0].id, "warehouse-1");
  assert.equal(view.calls[0].data.recipient_org_ids.length, 0);
  assert.equal(
    view.calls[0].data.expected_updated_at,
    fixture("warehouse-1").expected_updated_at,
  );
  assert.ok(
    view.events.some(
      (event) => event[0] === "update:modelValue" && event[1] === false,
    ),
  );
});

test("保存冲突保留选择供核对，不自动覆盖服务器", async (t) => {
  const view = await dialog(t);
  view.fail(true);
  view.state.selected.value = ["department"];
  await view.state.save();
  assert.equal(view.state.selected.value[0], "department");
  assert.equal(view.calls.length, 1);
  assert.equal(view.events.length, 0);
  assert.match(view.messages[0], /已被其他人修改/);
});

test("连续点击保存只发送一次请求", async (t) => {
  const view = await dialog(t);
  let release;
  view.gate(new Promise((resolve) => (release = resolve)));
  const saving = view.state.save();
  await view.state.save();
  assert.equal(view.calls.length, 1);
  release();
  await saving;
});

test("切换仓库后忽略上一仓库的迟到响应", async (t) => {
  const pending = new Map();
  const view = await dialog(
    t,
    (id) => new Promise((resolve) => pending.set(id, resolve)),
  );
  view.props.warehouseId = "warehouse-2";
  await vue.nextTick();
  pending.get("warehouse-2")({ code: 0, data: fixture("warehouse-2") });
  await settle();
  pending.get("warehouse-1")({ code: 0, data: fixture("warehouse-1") });
  await settle();
  assert.equal(view.state.scope.value.warehouse_id, "warehouse-2");
});

test("加载失败时不能提交空范围覆盖已有授权", async (t) => {
  const view = await dialog(t, async () => {
    throw new Error("加载失败");
  });
  await view.state.save();
  assert.equal(view.calls.length, 0);
  assert.equal(view.state.scope.value, null);
  assert.equal(view.state.error.value, "加载失败");
});
