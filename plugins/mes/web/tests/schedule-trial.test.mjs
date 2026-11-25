// Exercise the actual Vue setup actions. HTTP is substituted; no business database is touched.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
const require = createRequire(
  new URL("../../../core/web/package.json", import.meta.url)
);
const { build } = require("esbuild");
const { parse, compileScript, compileTemplate } = require("@vue/compiler-sfc");
const { createRenderer, nextTick } = require("vue");
const filename = fileURLToPath(
  new URL("../src/views/mes/scheduling/ScheduleTrial.vue", import.meta.url)
);
const { descriptor } = parse(readFileSync(filename, "utf8"));
const script = compileScript(descriptor, { id: "schedule-trial" });
assert.deepEqual(
  compileTemplate({
    source: descriptor.template.content,
    filename,
    id: "schedule-trial",
    compilerOptions: { bindingMetadata: script.bindings }
  }).errors,
  []
);
const mocks = {
  "@/utils/message":
    "export const actionMessage=(value,type='error')=>globalThis.__trial.notify(value,{type});",
  "@/components/ListPagination/index.vue": "export default {};",
  "@/utils/http":
    "export const getHttpErrorMessage=(error,fallback)=>error.message||fallback;",
  "@plugins/mes/web/src/api/mesScheduleTrial": `export const prepareScheduleTrial=async body=>globalThis.__trial.prepare(body); export const solveScheduleTrial=async body=>globalThis.__trial.solve(body);`
};
const bundle = await build({
  stdin: {
    contents: script.content,
    loader: "ts",
    resolveDir: fileURLToPath(
      new URL("../src/views/mes/scheduling", import.meta.url)
    )
  },
  bundle: true,
  write: false,
  platform: "node",
  format: "cjs",
  external: ["vue"],
  plugins: [
    {
      name: "controlled-trial",
      setup(builder) {
        builder.onResolve({ filter: /.*/ }, args =>
          mocks[args.path] ? { path: args.path, namespace: "mock" } : undefined
        );
        builder.onLoad({ filter: /.*/, namespace: "mock" }, args => ({
          contents: mocks[args.path],
          loader: "ts"
        }));
      }
    }
  ]
});
const module = { exports: {} };
new Function("require", "module", "exports", bundle.outputFiles[0].text)(
  require,
  module,
  module.exports
);
const Component = module.exports.default;
Component.render = () => null;
const renderer = createRenderer({
  createElement: () => ({ children: [] }),
  createText: text => ({ text }),
  createComment: text => ({ text }),
  insert: (node, parent) => parent.children.push(node),
  remove() {},
  patchProp() {},
  setText() {},
  setElementText() {},
  parentNode: () => null,
  nextSibling: () => null
});

function fixture(props = {}) {
  const calls = [];
  const notices = [];
  globalThis.__trial = {
    notify: (value, options) => {
      const notice = {
        value,
        options,
        closed: false,
        close() {
          this.closed = true;
        }
      };
      notices.push(notice);
      return notice;
    },
    prepare: async body => ({
      snapshot_key: "snapshot",
      issues: [],
      processes: [{ id: "qc", process_name: "检验" }],
      orders: body.work_order_ids.map(id => ({
        id,
        version_no: 2,
        work_order_no: id,
        quantity: "3",
        unit_code: "piece",
        due_at: body.end_at,
        operations: [
          {
            id: `operation-${id}`,
            operation_name: "测试工序",
            version_no: 3,
            standard_minutes_per_unit: 17.5
          }
        ]
      }))
    }),
    solve: async body => {
      calls.push(body);
      return {
        status_code: "OPTIMAL",
        issues: [],
        segments: [],
        completions: []
      };
    }
  };
  const app = renderer.createApp(Component, {
    orgId: "org",
    workOrderIds: ["one", "two"],
    ...props
  });
  const vm = app.mount({ children: [] });
  return { state: vm.$.setupState, calls, notices, stop: () => app.unmount() };
}

test("reads complete selected work orders and leaves unknown parameters blank", async () => {
  const f = fixture();
  try {
    await f.state.load();
    assert.equal(f.state.rules.length, 2);
    assert.equal(f.state.rules[0].kind_key, "");
    assert.equal(f.state.rules[0].setup_minutes, undefined);
    assert.equal(f.state.orders[0].confirmed, false);
    await f.state.solve();
    assert.equal(f.calls.length, 0);
    assert.match(f.notices.at(-1).value, /确认/);
    assert.equal(f.notices.at(-1).options.type, "error");
  } finally {
    f.stop();
  }
});

test("order review can confirm or clear all rows without confirming actual readiness", async () => {
  const f = fixture();
  try {
    await f.state.load();
    f.state.confirmOrders(true);
    assert.equal(f.state.confirmedOrderCount, 2);
    assert.equal(
      f.state.orders.every(row => row.confirmed),
      true
    );
    assert.equal(f.calls.length, 0);
    f.state.orders[0].confirmed = false;
    assert.equal(f.state.confirmedOrderCount, 1);
    f.state.confirmOrders(false);
    assert.equal(f.state.confirmedOrderCount, 0);
  } finally {
    f.stop();
  }
});

test("sends explicit phase confirmations and versions, then invalidates edited results", async () => {
  const f = fixture();
  try {
    await f.state.load();
    for (const row of f.state.rules)
      Object.assign(row, {
        kind_key: "machine",
        setup_minutes: 10,
        load_minutes: 1,
        unload_minutes: 2
      });
    for (const row of f.state.orders) row.confirmed = true;
    Object.assign(f.state.inspection, {
      mode_key: "separate",
      process_id: "qc",
      equipment: "none",
      minutes: 2
    });
    f.state.timingConfirmed = f.state.calendarConfirmed = true;
    await nextTick();
    await f.state.solve();
    const body = f.calls[0];
    assert.equal(body.operation_rules.length, 2);
    assert.equal(body.operation_rules[0].version_no, 3);
    assert.equal(body.operation_rules[0].is_timing_confirmed, true);
    assert.equal(body.order_rules[0].version_no, 2);
    assert.equal(body.inspection.is_equipment_required, false);
    assert.equal(f.state.result.status_code, "OPTIMAL");
    f.state.rules[0].load_minutes = 3;
    await nextTick();
    assert.equal(f.state.result, undefined);
    f.state.startAt = new Date(Date.now() + 3600000);
    await nextTick();
    assert.equal(f.state.prepared, undefined);
  } finally {
    f.stop();
  }
});

test("manual task does not inherit automatic machine supervision parameters", async () => {
  const f = fixture();
  try {
    await f.state.load();
    const row = f.state.rules[0];
    Object.assign(row, {
      kind_key: "manual",
      supervision_key: "two_machines",
      is_lunch_auto_allowed: true,
      load_minutes: 1,
      unload_minutes: 1
    });
    f.state.kindChanged(row.operation_id);
    assert.equal(row.supervision_key, "exclusive");
    assert.equal(row.is_lunch_auto_allowed, false);
    assert.equal(row.load_minutes, 0);
    assert.equal(row.unload_minutes, 0);
  } finally {
    f.stop();
  }
});

test("canonical manual process initializes disabled machine fields to zero without guessing setup time", async () => {
  const f = fixture();
  const original = globalThis.__trial.prepare;
  globalThis.__trial.prepare = async body => {
    const value = await original(body);
    value.orders.forEach(o =>
      o.operations.forEach(op => {
        op.execution_kind_code = "manual";
      })
    );
    return value;
  };
  try {
    await f.state.load();
    const row = f.state.rules[0];
    assert.equal(row.kind_key, "manual");
    assert.equal(row.load_minutes, 0);
    assert.equal(row.unload_minutes, 0);
    assert.equal(row.setup_minutes, undefined);
    f.state.editConditions(row);
    f.state.enableQa(true);
    assert.equal(row.inspection.minutes_per_piece, undefined);
  } finally {
    f.stop();
  }
});

test("repeated validation errors replace the current notice and unmount closes only its own notice", async () => {
  const f = fixture();
  await f.state.load();
  await f.state.solve();
  const first = f.notices.at(-1);
  await f.state.solve();
  assert.equal(first.closed, true);
  assert.equal(f.notices.at(-1).closed, false);
  f.stop();
  assert.equal(f.notices.at(-1).closed, true);
});

test("reading errors use floating messages and a successful retry clears the previous error", async () => {
  const f = fixture();
  const prepare = globalThis.__trial.prepare;
  try {
    globalThis.__trial.prepare = async () => {
      throw new Error("工单读取失败，请重试");
    };
    await f.state.load();
    assert.equal(f.notices.at(-1).value, "工单读取失败，请重试");
    assert.equal(f.notices.at(-1).options.type, "error");
    const failed = f.notices.at(-1);
    globalThis.__trial.prepare = prepare;
    await f.state.load();
    assert.equal(failed.closed, true);
    assert.equal(f.state.loading, false);
  } finally {
    f.stop();
  }
});

test("large preflight issue lists show a short floating summary and keep every detail available on request", async () => {
  const f = fixture();
  const prepare = globalThis.__trial.prepare;
  const issues = Array.from({ length: 120 }, (_, i) => `工序${i + 1}缺少资料`);
  try {
    globalThis.__trial.prepare = async body => ({
      ...(await prepare(body)),
      issues
    });
    await f.state.load();
    const notice = f.notices.at(-1);
    assert.equal(notice.options.type, "warning");
    assert.equal(f.state.issuesVisible, false);
    assert.equal(
      notice.value.children[0].children,
      "请先处理工单资料（120项）"
    );
    notice.value.children[1].props.onClick();
    assert.equal(f.state.issuesVisible, true);
    assert.equal(f.state.issueItems.length, 120);
    assert.equal(f.state.issueItems[119], issues[119]);
    assert.equal(notice.closed, true);
    await f.state.solve();
    assert.equal(f.calls.length, 0);
  } finally {
    f.stop();
  }
});

test("a late failed request after leaving the page does not create a lingering message", async () => {
  const f = fixture();
  let reject;
  globalThis.__trial.prepare = () =>
    new Promise((_, fail) => {
      reject = fail;
    });
  const pending = f.state.load();
  f.stop();
  reject(new Error("延迟返回错误"));
  await pending;
  assert.equal(f.notices.length, 0);
});

test("compute failures keep the filled form and show the business reason at the top", async () => {
  const f = fixture();
  try {
    await f.state.load();
    for (const row of f.state.rules)
      Object.assign(row, {
        kind_key: "manual",
        setup_minutes: 0,
        load_minutes: 0,
        unload_minutes: 0
      });
    for (const row of f.state.orders) row.confirmed = true;
    f.state.timingConfirmed = f.state.calendarConfirmed = true;
    f.state.inspection.mode_key = "last_operation";
    await nextTick();
    globalThis.__trial.solve = async () => {
      throw new Error("资源日历已更新，请重新读取");
    };
    await f.state.solve();
    assert.equal(f.notices.at(-1).value, "资源日历已更新，请重新读取");
    assert.equal(f.notices.at(-1).options.type, "error");
    assert.equal(f.state.orders[0].confirmed, true);
    assert.equal(f.state.rules[0].kind_key, "manual");
    assert.equal(f.state.loading, false);
    assert.equal(f.state.result, undefined);
  } finally {
    f.stop();
  }
});

test("only a successfully calculated formal plan opens its saved detail", async () => {
  const opened = [];
  let status = "OPTIMAL";
  const f = fixture({
    formal: true,
    compute: async () => ({
      plan_id: "saved-plan",
      plan_no: "SP-TEST",
      status_code: status,
      issues: status === "INFEASIBLE" ? ["资源可用时段不足"] : [],
      warnings: ["仅用于预测"],
      segments: [],
      completions: []
    }),
    onSaved: id => opened.push(id)
  });
  try {
    await f.state.load();
    for (const row of f.state.rules)
      Object.assign(row, {
        kind_key: "manual",
        setup_minutes: 0,
        load_minutes: 0,
        unload_minutes: 0
      });
    f.state.confirmOrders(true);
    f.state.timingConfirmed = f.state.calendarConfirmed = true;
    f.state.inspection.mode_key = "last_operation";
    await nextTick();

    await f.state.solve();
    assert.deepEqual(opened, ["saved-plan"]);
    status = "FEASIBLE";
    await f.state.solve();
    assert.deepEqual(opened, ["saved-plan", "saved-plan"]);
    status = "INFEASIBLE";
    await f.state.solve();
    assert.equal(f.state.result.status_code, "INFEASIBLE");
    assert.deepEqual(opened, ["saved-plan", "saved-plan"]);
  } finally {
    f.stop();
  }
});
