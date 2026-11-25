import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const ts = createRequire(
  new URL("../../../../web/package.json", import.meta.url),
)("typescript");
function fixture() {
  const timers = new Map();
  let sequence = 0;
  const exports = {};
  runInNewContext(
    ts.transpileModule(
      readFileSync(
        new URL("../src/views/mes/quotations/progress.ts", import.meta.url),
        "utf8",
      ),
      {
        compilerOptions: { module: ts.ModuleKind.CommonJS },
      },
    ).outputText,
    {
      exports,
      setTimeout: (callback, delay) => {
        assert.equal(delay, 4000);
        timers.set(++sequence, callback);
        return sequence;
      },
      clearTimeout: (id) => timers.delete(id),
    },
  );
  const record = (status = "queued") => ({
    id: "record",
    part_id: "part",
    status_code: status,
    stage: status,
  });
  const quote = {
    id: "quote",
    version_no: 7,
    lines: [
      {
        id: "line",
        unit_price: 12.5,
        quoted_material: "手工材料",
        weight_kg: 2,
        lead_days: 9,
        cnc_records: [record()],
      },
    ],
  };
  const state = {
    target: { key: "page-1", quote },
    paused: false,
    calls: 0,
    message: "",
    response: undefined,
  };
  state.response = async () => ({
    lines: [{ id: "line", cnc_records: [record("completed")] }],
  });
  const poller = exports.createCncProgressPoller({
    target: () => state.target,
    paused: () => state.paused,
    fetch: async (id) => {
      assert.equal(id, state.target.quote.id);
      state.calls++;
      return state.response();
    },
    notify: (message) => {
      state.message = message;
    },
  });
  const tick = () => {
    assert.equal(timers.size, 1);
    const [id, callback] = timers.entries().next().value;
    timers.delete(id);
    return callback();
  };
  return { state, quote, record, timers, poller, tick };
}

test("queued/running/terminal states refresh without changing unsaved values or version", async () => {
  const f = fixture();
  f.state.response = async () => ({
    lines: [
      { id: "line", unit_price: 999, cnc_records: [f.record("running")] },
    ],
    version_no: 999,
  });
  f.poller.sync();
  await f.tick();
  assert.equal(f.quote.lines[0].cnc_records[0].status_code, "running");
  f.quote.lines[0].unit_price = 18.88;
  f.state.response = async () => ({
    lines: [{ id: "line", cnc_records: [f.record("completed")] }],
  });
  await f.tick();
  assert.equal(f.quote.lines[0].cnc_records[0].status_code, "completed");
  assert.equal(f.quote.version_no, 7);
  assert.equal(f.quote.lines[0].unit_price, 18.88);
  assert.equal(f.quote.lines[0].quoted_material, "手工材料");
  assert.equal(f.quote.lines[0].weight_kg, 2);
  assert.equal(f.quote.lines[0].lead_days, 9);
  assert.equal(f.timers.size, 0);
});

test("slow requests do not overlap; form actions pause requests", async () => {
  const f = fixture();
  let resolve;
  f.state.paused = true;
  f.poller.sync();
  await f.tick();
  assert.equal(f.state.calls, 0);
  f.state.paused = false;
  f.state.response = () =>
    new Promise((done) => {
      resolve = done;
    });
  const pending = f.tick();
  f.poller.sync();
  f.poller.sync();
  assert.equal(f.timers.size, 0);
  assert.equal(f.state.calls, 1);
  resolve({ lines: [{ id: "line", cnc_records: [f.record("running")] }] });
  await pending;
  assert.equal(f.quote.lines[0].cnc_records[0].status_code, "queued");
  assert.equal(f.timers.size, 1);
});

test("navigation, identity/page generation changes and disposal discard late responses", async () => {
  for (const change of ["hidden", "identity", "replaced", "unmount"]) {
    const f = fixture();
    let resolve;
    f.state.response = () =>
      new Promise((done) => {
        resolve = done;
      });
    f.poller.sync();
    const pending = f.tick();
    if (change === "hidden") f.state.target = undefined;
    if (change === "identity")
      f.state.target = { ...f.state.target, key: "page-2" };
    if (change === "replaced")
      f.state.target = { ...f.state.target, quote: { ...f.quote } };
    if (change === "unmount") f.poller.dispose();
    else f.poller.sync();
    resolve({ lines: [{ id: "line", cnc_records: [f.record("completed")] }] });
    await pending;
    assert.equal(f.quote.lines[0].cnc_records[0].status_code, "queued", change);
    f.poller.dispose();
    assert.equal(f.timers.size, 0);
  }
});

test("transient failures retry quietly and recover", async () => {
  const f = fixture();
  f.state.response = async () => {
    throw Error("offline");
  };
  f.poller.sync();
  await f.tick();
  assert.match(f.state.message, /正在重试/);
  f.state.response = async () => ({
    lines: [{ id: "line", cnc_records: [f.record("failed")] }],
  });
  await f.tick();
  assert.equal(f.state.message, "");
  assert.equal(f.timers.size, 0);
});

test("authorization/not-found errors stop repeated calls for this page", async () => {
  for (const status of [401, 403, 404]) {
    const f = fixture();
    f.state.response = async () => {
      throw { status };
    };
    f.poller.sync();
    await f.tick();
    f.poller.sync();
    assert.equal(f.state.calls, 1);
    assert.equal(f.timers.size, 0);
    assert.match(f.state.message, /权限/);
  }
});
