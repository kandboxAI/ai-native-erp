// Exercise real page setup actions with controlled HTTP; never touches the business database.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
const require = createRequire(
  new URL("../../../core/web/package.json", import.meta.url)
);
const { build } = require("esbuild");
const { parse, compileScript, compileTemplate } = require("@vue/compiler-sfc");
const { createRenderer, nextTick } = require("vue");
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
async function page(path, services, props = {}) {
  globalThis.__scheduleTest = services;
  const filename = fileURLToPath(
    new URL(`../src/views/mes/${path}`, import.meta.url)
  );
  const { descriptor } = parse(readFileSync(filename, "utf8"));
  const script = compileScript(descriptor, { id: path });
  assert.deepEqual(
    compileTemplate({
      source: descriptor.template.content,
      filename,
      id: path,
      compilerOptions: { bindingMetadata: script.bindings }
    }).errors,
    []
  );
  const exports = [
    "resourcePage",
    "resourceDetail",
    "saveResource",
    "resourceOrganizations",
    "resourceProcesses",
    "resourceOptions",
    "schedulePlans",
    "schedulePlan",
    "schedulePlanCommand",
    "savePlanReadiness",
    "createSchedulePlan"
  ];
  const mocks = {
    "@/utils/auth": "export const hasPerms=()=>true;",
    "@/utils/http": "export const getHttpErrorMessage=(e,f)=>e.message||f;",
    "@/utils/message": "export const message=()=>{};export const actionMessage=(text,type)=>globalThis.__scheduleTest.onNotice?.(text,type);",
    "vue-router":
      "export const useRoute=()=>({query:{}});export const useRouter=()=>({push:(...args)=>globalThis.__scheduleTest.onPush?.(...args),replace(){}});",
    "element-plus": "export const ElMessageBox={confirm:async()=>true};",
    "@plugins/mes/web/src/api/mes":
      "export const getMesScheduleOrgOptions=async()=>[];"
  };
  const api = exports
    .map(
      key =>
        `export const ${key}=(...args)=>globalThis.__scheduleTest.${key}(...args);`
    )
    .join("\n");
  const result = await build({
    stdin: {
      contents: script.content,
      loader: "ts",
      resolveDir: dirname(filename)
    },
    bundle: true,
    write: false,
    platform: "node",
    format: "cjs",
    external: ["vue"],
    plugins: [
      {
        name: "isolated-page",
        setup(builder) {
          builder.onResolve({ filter: /.*/ }, args =>
            args.path.endsWith(".vue")
              ? { path: args.path, namespace: "component" }
              : mocks[args.path]
                ? { path: args.path, namespace: "mock" }
                : args.path.includes("api/mesSchedule")
                  ? { path: args.path, namespace: "api" }
                  : undefined
          );
          builder.onLoad({ filter: /.*/, namespace: "component" }, () => ({
            contents: "export default {};"
          }));
          builder.onLoad({ filter: /.*/, namespace: "mock" }, args => ({
            contents: mocks[args.path]
          }));
          builder.onLoad({ filter: /.*/, namespace: "api" }, () => ({
            contents: api
          }));
        }
      }
    ]
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", result.outputFiles[0].text)(
    require,
    module,
    module.exports
  );
  const component = module.exports.default;
  component.render = () => null;
  const app = renderer.createApp(component, props),
    vm = app.mount({ children: [] });
  await new Promise(resolve => setImmediate(resolve));
  return { state: vm.$.setupState, stop: () => app.unmount() };
}
function resources() {
  const writes = [];
  const person = {
    id: "person",
    org_id: "org",
    version_no: 7,
    person_no: "P1",
    full_name: "测试人员",
    is_active: true,
    qualifications: []
  };
  return {
    writes,
    person,
    resourcePage: async () => ({ items: [], total: 0 }),
    resourceDetail: async () => person,
    saveResource: async (...args) => {
      writes.push(args);
      return person;
    },
    resourceOrganizations: async () => [],
    resourceProcesses: async () => [],
    resourceOptions: async () => ({
      people: [
        { id: "p1", label: "P1" },
        { id: "p2", label: "P2" }
      ],
      equipment: []
    })
  };
}

test("plan Gantt opens on the first work window and expands real stages when zoomed", async () => {
  const windowStart = new Date(2026, 10, 18, 8).getTime();
  const first = new Date(2026, 10, 19, 8).getTime();
  const at = minutes => new Date(first + minutes * 60000).toISOString();
  const segment = (id, kind, start, end, extra = {}) => ({
    id,
    plan_operation_id: "op-a",
    work_order_no: "WO-A",
    operation_name: "NC车",
    production_phase_code: "first",
    segment_type_code: kind,
    planned_start_at: at(start),
    planned_end_at: at(end),
    equipment_id: "equipment-a",
    equipment_name_snapshot: "NC-1",
    production_person_id: "person-a",
    person_no_snapshot: "P1",
    person_capacity_units_snapshot: 1,
    ...extra
  });
  const f = await page("schedule-plans/PlanTimeline.vue", {}, {
    startAt: new Date(windowStart).toISOString(),
    endAt: at(7 * 24 * 60),
    operations: [
      { id: "op-a", work_order_id: "order-a", work_order_no: "WO-A" },
      { id: "op-b", work_order_id: "order-b", work_order_no: "WO-B" }
    ],
    search: "",
    segments: [
      segment("external", "external_wait", 170, 1800, {
        equipment_id: null, production_person_id: null, person_capacity_units_snapshot: 0
      }),
      segment("load", "load", 10, 20),
      segment("prepare", "preparation", 5, 10),
      segment("run", "run", 20, 50),
      segment("other-order", "run", 25, 45, {
        plan_operation_id: "op-b", work_order_no: "WO-B",
        equipment_id: "equipment-b", equipment_name_snapshot: "NC-2"
      }),
      segment("waiting", "waiting_unload", 50, 60, { person_capacity_units_snapshot: 0 }),
      segment("unload", "unload", 65, 70),
      segment("remaining", "run", 70, 90, { production_phase_code: "remaining" })
    ],
    completions: [{
      work_order_id: "order-a", work_order_no: "WO-A-OLD",
      first_article_release_at: at(100), inspection_release_at: at(100),
      due_at: at(8 * 24 * 60)
    }]
  });
  try {
    const { state } = f;
    assert.equal(state.view, "order");
    assert.equal(state.range, "work");
    assert.deepEqual(state.window, { start: first, end: first + 8 * 3600000 });
    assert.deepEqual(state.lanes.map(row => row.label), ["WO-A", "WO-B"]);
    const firstLane = state.lanes[0];
    assert.deepEqual(firstLane.tracks[0].map(bar => [bar.kind, bar.count]), [
      ["run", 3], ["waiting_unload", 1], ["run", 1], ["run", 1], ["external_wait", 1]
    ]);
    assert.equal(firstLane.tracks[0][0].end, Date.parse(at(50)));
    assert.equal(state.eventMarkers(firstLane)[0].events.length, 2);
    state.setRange("overview");
    assert.equal(state.window.start, windowStart);
    assert.equal(state.eventMarkers(state.lanes[0]).at(-1).symbol, "›");

    state.showBar(state.lanes[0].tracks[0][0]);
    state.focusSelection();
    assert.equal(state.range, "detail");
    assert.equal(state.window.start, first);
    assert.deepEqual(state.lanes[0].tracks[0].slice(0, 3).map(bar => bar.kind), [
      "preparation", "load", "run"
    ]);
    state.move(1);
    assert.equal(state.window.start, first + 2 * 3600000);
    state.move(-1);
    state.view = "equipment";
    assert.deepEqual(state.lanes.map(row => row.label), ["NC-1", "NC-2"]);
    state.view = "person";
    assert.deepEqual(state.lanes.map(row => row.label), ["P1"]);
    assert.equal(state.lanes[0].tracks.length, 2);
    assert.equal(state.lanes[0].tracks.flat().some(bar => bar.kind === "waiting_unload"), false);
  } finally {
    f.stop();
  }
});

test("opens the saved plan by ID and exits creation only after navigation", async () => {
  const attempts = [];
  let closed = 0;
  let navigationFailure = { type: 4 };
  const f = await page(
    "schedule-plans/CreatePlan.vue",
    {
      onPush: async target => {
        attempts.push(target);
        return navigationFailure;
      }
    },
    { orgId: "org", workOrderIds: ["one"], onClose: () => closed++ }
  );
  try {
    await f.state.openPlan("created-plan");
    assert.equal(closed, 0);
    navigationFailure = undefined;
    await f.state.openPlan("created-plan");
    assert.deepEqual(attempts, [
      { path: "/mes/schedule-plans", query: { plan_id: "created-plan" } },
      { path: "/mes/schedule-plans", query: { plan_id: "created-plan" } }
    ]);
    assert.equal(closed, 1);
  } finally {
    f.stop();
  }
});

async function readinessFixture() {
  const writes = [];
  const f = await page(
    "schedule-plans/CreatePlan.vue",
    {
      createSchedulePlan: async body => {
        writes.push(body);
        return { status_code: "OPTIMAL" };
      }
    },
    { orgId: "org", workOrderIds: ["one", "two", "three"] }
  );
  const scope = {
    start_at: "2030-11-11T08:00:00+08:00",
    end_at: "2030-11-18T18:00:00+08:00"
  };
  const data = {
    orders: ["one", "two", "three"].map(id => ({ id, work_order_no: id })),
    readiness: []
  };
  f.state.prepared(data, scope);
  await nextTick();
  return { ...f, writes, data, scope };
}

test("batch expected times target all conditions without confirming actual readiness or writing", async () => {
  const f = await readinessFixture();
  try {
    f.state.batchExpectedAt = new Date("2030-11-12T09:30:00+08:00");
    f.state.applyExpectedTime();
    assert.equal(f.state.targetConditions.length, 12);
    assert.equal(f.state.readinessCount, 0);
    for (const row of f.state.conditions)
      for (const kind of row.kinds) {
        assert.equal(
          kind.expected_at.toISOString(),
          "2030-11-12T01:30:00.000Z"
        );
        assert.equal(kind.is_confirmed, false);
      }
    assert.notEqual(
      f.state.conditions[0].kinds[0].expected_at,
      f.state.conditions[1].kinds[0].expected_at
    );
    assert.equal(f.writes.length, 0);
    f.state.batchExpectedAt = undefined;
    assert.equal(f.state.canApplyTime, false);
    f.state.applyExpectedTime();
    assert.equal(
      f.state.conditions[0].kinds[0].expected_at.toISOString(),
      "2030-11-12T01:30:00.000Z"
    );
  } finally {
    f.stop();
  }
});

test("batch readiness respects selected orders and condition kind, and supports clearing confirmations", async () => {
  const f = await readinessFixture();
  try {
    f.state.selectOrders([f.state.conditions[1]]);
    f.state.batchKind = "material";
    f.state.confirmReadiness(true);
    assert.equal(f.state.batchScope, "selected");
    assert.equal(f.state.targetConditions.length, 1);
    assert.equal(f.state.readinessCount, 1);
    assert.equal(
      f.state.conditions[0].kinds.every(kind => !kind.is_confirmed),
      true
    );
    f.state.batchExpectedAt = new Date("2030-11-13T08:00:00+08:00");
    f.state.applyExpectedTime();
    assert.equal(
      f.state.conditions[1].kinds[0].expected_at.toISOString(),
      "2030-11-13T00:00:00.000Z"
    );
    assert.equal(
      f.state.conditions[1].kinds[1].expected_at.toISOString(),
      "2030-11-11T00:00:00.000Z"
    );
    f.state.confirmReadiness(false);
    assert.equal(f.state.readinessCount, 0);
    f.state.selectOrders([]);
    assert.equal(f.state.targetConditions.length, 0);
    f.state.confirmReadiness(true);
    assert.equal(f.state.readinessCount, 0);
    f.state.batchScope = "all";
    f.state.batchKind = "all";
    f.state.confirmReadiness(true);
    assert.equal(f.state.readinessCount, 12);
    f.state.conditions[0].kinds[0].is_confirmed = false;
    assert.equal(f.state.readinessCount, 11);
    assert.equal(f.writes.length, 0);
  } finally {
    f.stop();
  }
});

test("batch changes invalidate previous results and final compute carries per-order readiness", async () => {
  const f = await readinessFixture();
  try {
    let invalidations = 0;
    f.state.trial = {
      invalidate: () => {
        invalidations++;
      }
    };
    f.state.confirmReadiness(true);
    await nextTick();
    assert.ok(invalidations > 0);
    await f.state.compute({ org_id: "org", snapshot_key: "snapshot" });
    assert.equal(f.writes.length, 1);
    assert.equal(f.writes[0].readiness.length, 12);
    assert.equal(
      new Set(f.writes[0].readiness.map(row => row.work_order_id)).size,
      3
    );
    assert.equal(
      f.writes[0].readiness.every(row => row.is_confirmed),
      true
    );
    f.state.prepared(f.data, f.scope);
    assert.equal(f.state.readinessCount, 0);
    assert.equal(f.state.selectedOrderIds.length, 0);
    assert.equal(f.state.batchScope, "all");
  } finally {
    f.stop();
  }
});
test("person edit carries current version and qualification keeps explicit validity", async () => {
  const mock = resources(),
    f = await page("resources/people/index.vue", mock);
  try {
    await f.state.open(mock.person);
    f.state.form.job_title_snapshot = "技术员";
    await f.state.save();
    assert.equal(mock.writes[0][0], "people/person");
    assert.equal(mock.writes[0][1].version_no, 7);
    await f.state.open(mock.person);
    f.state.openSkill();
    f.state.qualification.process_id = "cnc3";
    f.state.qualification.valid_from = new Date("2030-11-11T00:00:00Z");
    f.state.qualification.valid_to = new Date("2030-12-01T00:00:00Z");
    await f.state.saveSkill();
    assert.equal(mock.writes[1][0], "people/person/qualifications");
    assert.equal(mock.writes[1][1].valid_to, "2030-12-01T00:00:00.000Z");
    assert.equal(f.state.skillVisible, false);
  } finally {
    f.stop();
  }
});
test("calendar batch keeps explicit lunch and refuses exceptions before unsaved weekly changes", async () => {
  const mock = resources(),
    f = await page("resources/calendars/index.vue", mock);
  const notices = [];
  mock.onNotice = (text, type) => notices.push({ text, type });
  try {
    f.state.query.org_id = "org";
    await f.state.open();
    f.state.form.calendar_name = "标准周";
    f.state.chosen = ["p1", "p2"];
    f.state.standardWeek();
    await f.state.save();
    const [path, body] = mock.writes[0];
    assert.equal(path, "calendar-batch");
    assert.equal(body.calendars.length, 2);
    assert.equal(
      body.calendars[0].periods.filter(p => p.period_type_code === "lunch")
        .length,
      5
    );
    assert.equal(body.calendars[0].periods[1].start_minute_of_day, 720);
    f.state.form.calendar_name = "未保存";
    f.state.openException();
    assert.match(notices.at(-1).text, /先保存/);
    assert.equal(f.state.error, "");
  } finally {
    f.stop();
  }
});
test("confirming a plan uses latest version, refreshes its real applied state and stops polling", async () => {
  let status = "ready";
  const commands = [];
  const mock = {
    schedulePlans: async () => ({ items: [], total: 0 }),
    schedulePlan: async () => ({
      id: "plan",
      version_no: 3,
      status_code: status,
      segments: [],
      operations: [],
      result: { completions: [] },
      readiness: []
    }),
    schedulePlanCommand: async (...args) => {
      commands.push(args);
      status = "applied";
    }
  };
  const f = await page("schedule-plans/index.vue", mock);
  try {
    await f.state.open("plan");
    await f.state.command("apply");
    assert.deepEqual(commands[0].slice(0, 3), ["plan", "apply", 3]);
    assert.equal(f.state.detail.status_code, "applied");
    assert.equal(f.state.timer, undefined);
    status = "calculating";
    await f.state.open("plan");
    assert.ok(f.state.timer);
    status = "ready";
    await f.state.open("plan");
    assert.equal(f.state.timer, undefined);
    await nextTick();
  } finally {
    f.stop();
  }
});
