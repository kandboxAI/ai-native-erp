import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import * as vue from "vue";
import { compileScript, parse } from "vue/compiler-sfc";
import ts from "typescript";

const source = readFileSync(
  new URL("./RequisitionActionDialog.vue", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(
  compileScript(parse(source).descriptor, { id: "receipt-actions" }).content,
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  },
).outputText;

async function dialog(t, action) {
  const calls = [],
    messages = [],
    events = [];
  let fail = false,
    gate;
  const api = Object.fromEntries(
    [
      "issueMaterialRequisition",
      "receiveMaterialRequisition",
      "resolveMaterialRequisitionException",
    ].map((name) => [
      name,
      async (...args) => {
        calls.push({ name, args });
        if (gate) await gate;
        if (fail) throw new Error("conflict");
      },
    ]),
  );
  let uploads = 0;
  const exports = {};
  runInNewContext(compiled, {
    exports,
    require(id) {
      if (id === "vue") return vue;
      if (id === "element-plus")
        return {
          ElMessage: Object.fromEntries(
            ["warning", "error", "success"].map((name) => [
              name,
              (value) => messages.push(value),
            ]),
          ),
        };
      if (id === "@/api/systemFile")
        return {
          discardFile: async () => {},
          uploadSelectedFiles: async (files) => {
            const id = files[0].response?.id;
            if (!id) uploads += 1;
            return [id || "photo-1"];
          },
        };
      if (id === "@/utils/http")
        return { getHttpErrorMessage: (error) => error.message };
      if (id.includes("inventoryRequisition")) return api;
      if (id.endsWith("RequisitionAssetSelect.vue")) return {};
      throw new Error(id);
    },
  });
  const props = vue.reactive({
    modelValue: false,
    action,
    request: {
      id: "request-1",
      version_no: 4,
      lines: [
        {
          id: "line-1",
          item_name_snapshot: "粉笔",
          unit_name: "盒",
          quantity: "5",
          issued_quantity: "3",
        },
      ],
    },
  });
  const scope = vue.effectScope();
  const state = scope.run(() =>
    exports.default.setup(props, {
      expose() {},
      emit: (...args) => events.push(args),
    }),
  );
  t.after(() => scope.stop());
  props.modelValue = true;
  await vue.nextTick();
  return {
    state,
    props,
    calls,
    messages,
    events,
    uploads: () => uploads,
    fail: (value) => (fail = value),
    gate: (value) => (gate = value),
  };
}

test("发放将实物选择随原申请明细提交", async (t) => {
  const f = await dialog(t, "issue");
  f.state.checks.value[0].quantity = 3;
  f.state.checks.value[0].asset_tracking = {
    selections: [
      {
        binding_id: "physical-asset",
        quantity: "3",
        department_id: "dept",
        target_location_id: "room",
      },
    ],
  };
  await f.state.save();
  assert.equal(
    f.calls[0].args[4][0].tracking.asset.selections[0].binding_id,
    "physical-asset",
  );
  assert.equal(f.calls[0].args[4][0].line_id, "line-1");
});

test("已选资产与实发数量不符时在上传照片及发放前拦截", async (t) => {
  const f = await dialog(t, "issue");
  f.state.checks.value[0].asset_tracking = {
    selections: [{ binding_id: "asset", quantity: "1" }],
  };
  f.state.files.value = [{ raw: {}, name: "photo.jpg" }];
  await f.state.save();
  assert.equal(f.calls.length, 0);
  assert.equal(f.uploads(), 0);
  assert(
    f.messages.some((message) => message.includes("数量须与实际发放数量一致")),
  );
});

test("签收按实际发放量核对，提交给签收接口并保留明细ID", async (t) => {
  const view = await dialog(t, "receive");
  assert.equal(view.state.checks.value[0].received_quantity, 3);
  await view.state.save();
  assert.equal(view.calls.length, 1);
  assert.equal(view.calls[0].name, "receiveMaterialRequisition");
  const [id, data, exception] = view.calls[0].args;
  assert.equal(id, "request-1");
  assert.equal(data.version_no, 4);
  assert.equal(data.lines[0].line_id, "line-1");
  assert.equal(data.lines[0].received_quantity, 3);
  assert.equal(exception, false);
  assert.ok(view.events.some((event) => event[0] === "saved"));
});

test("发放使用人工填写实发数量且连续点击只提交一次", async (t) => {
  const view = await dialog(t, "issue");
  view.state.checks.value[0].quantity = 2;
  let release;
  view.gate(new Promise((resolve) => (release = resolve)));
  const saving = view.state.save();
  await view.state.save();
  assert.equal(view.calls.length, 1);
  assert.equal(view.calls[0].name, "issueMaterialRequisition");
  assert.equal(view.calls[0].args[4][0].quantity, 2);
  release();
  await saving;
});

test("提交失败保留已上传文件ID，重试复用文件并保留版本", async (t) => {
  const view = await dialog(t, "receive");
  view.state.files.value = [{ name: "photo.jpg", raw: {} }];
  view.fail(true);
  await view.state.save();
  assert.equal(view.state.files.value[0].response.id, "photo-1");
  assert.equal(view.events.length, 0);
  view.fail(false);
  await view.state.save();
  assert.equal(view.uploads(), 1);
  assert.equal(view.calls[1].args[1].photo_file_ids[0], "photo-1");
  assert.equal(view.calls[1].args[1].version_no, 4);
});

test("破损异常缺照片拦截，少发自动计算差额并可无照片反馈", async (t) => {
  const view = await dialog(t, "exception");
  view.state.note.value = "请核实";
  const line = view.state.checks.value[0];
  line.exception_type_code = "damaged";
  line.exception_quantity = 1;
  await view.state.save();
  assert.equal(view.calls.length, 0);
  line.exception_type_code = "shortage";
  line.received_quantity = 1;
  view.state.updateMissing(line);
  assert.equal(line.exception_quantity, 2);
  await view.state.save();
  assert.equal(view.calls[0].args[2], true);
  assert.equal(view.calls[0].args[1].lines[0].exception_quantity, 2);
});

test("处理结果需要说明，只登记处理结果不调用发放或代签收", async (t) => {
  const view = await dialog(t, "resolve");
  await view.state.save();
  assert.equal(view.calls.length, 0);
  view.state.note.value = "已核实并补齐，关联 CK-002";
  await view.state.save();
  assert.equal(view.calls[0].name, "resolveMaterialRequisitionException");
});
