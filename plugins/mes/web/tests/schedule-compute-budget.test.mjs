// Verify actual compute requests wait through the server's solve and modelling budgets.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
const require = createRequire(
  new URL("../../../core/web/package.json", import.meta.url)
);
const { build } = require("esbuild");

test("trial and formal plan requests allow 60 seconds of solving plus modelling", async () => {
  const calls = [];
  globalThis.__scheduleBudgetHttp = async (...args) => {
    calls.push(args);
    return { data: { status_code: "FEASIBLE" } };
  };
  try {
    const result = await build({
      stdin: {
        contents: `export { solveScheduleTrial } from "./mesScheduleTrial"; export { createSchedulePlan } from "./mesSchedulePlans";`,
        resolveDir: fileURLToPath(new URL("../src/api/", import.meta.url)),
        loader: "ts"
      },
      bundle: true,
      write: false,
      format: "esm",
      platform: "node",
      plugins: [
        {
          name: "mock-http",
          setup(builder) {
            builder.onResolve({ filter: /^@\/utils\/http/ }, () => ({
              path: "http",
              namespace: "mock"
            }));
            builder.onLoad({ filter: /.*/, namespace: "mock" }, () => ({
              contents:
                "export const http={request:(...args)=>globalThis.__scheduleBudgetHttp(...args)};",
              loader: "js"
            }));
          }
        }
      ]
    });
    const api = await import(
      `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`
    );
    const body = { time_limit_seconds: 60 };
    assert.equal((await api.solveScheduleTrial(body)).status_code, "FEASIBLE");
    assert.equal((await api.createSchedulePlan(body)).status_code, "FEASIBLE");
    assert.deepEqual(
      calls.map(call => call[1]),
      ["/api/mes/schedule-trials/solve", "/api/mes/schedule-plans"]
    );
    for (const [method, , config] of calls) {
      assert.equal(method, "post");
      assert.equal(config.data, body);
      assert.ok(config.timeout >= (body.time_limit_seconds + 30 + 10) * 1000);
    }
  } finally {
    delete globalThis.__scheduleBudgetHttp;
  }
});
