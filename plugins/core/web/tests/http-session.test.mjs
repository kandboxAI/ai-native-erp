import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const compiled = ts.transpileModule(
  readFileSync(new URL("../src/utils/http/index.ts", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true } }
).outputText;

function setup(refresh) {
  let interceptor;
  let logouts = 0;
  let session = { accessToken: "expired", refreshToken: "refresh", expires: 0 };
  const exports = {};
  const instance = {
    interceptors: {
      request: {
        use(callback) {
          interceptor = callback;
        }
      },
      response: { use() {} }
    }
  };
  runInNewContext(compiled, {
    exports,
    require(id) {
      if (id === "axios") return { create: () => instance };
      if (id === "qs") return { stringify: () => "" };
      if (id === "@/utils/message") return { message() {} };
      if (id === "@/utils/listState") return { prepareListRequest() {}, recordListResponse() {} };
      if (id === "@/plugins/i18n")
        return { $t: text => text, transformI18n: text => text };
      if (id === "@/utils/auth")
        return {
          getToken: () => session,
          formatToken: token => `Bearer ${token}`
        };
      if (id === "@/store/modules/user")
        return {
          useUserStoreHook: () => ({
            handRefreshToken: refresh,
            logOut() {
              logouts++;
              session = null;
            }
          })
        };
      throw new Error(id);
    }
  });
  return {
    request: () => interceptor({ url: "/api/auth/menus", headers: {} }),
    logouts: () => logouts
  };
}

test("expired HTTP login waits for refresh and uses the new access token", async () => {
  const app = setup(async () => ({ data: { accessToken: "renewed" } }));
  assert.equal((await app.request()).headers.Authorization, "Bearer renewed");
  assert.equal(app.logouts(), 0);
});

test("a failed refresh rejects waiting HTTP requests without logging out during an outage", async () => {
  const app = setup(async () => {
    throw new Error("offline");
  });
  await assert.rejects(app.request(), /offline/);
  assert.equal(app.logouts(), 0);
});

test("a rejected refresh logs out and rejects all waiting HTTP requests", async () => {
  const app = setup(async () => {
    throw { response: { status: 401 } };
  });
  const result = await Promise.allSettled([app.request(), app.request()]);
  assert.ok(result.every(item => item.status === "rejected"));
  assert.equal(app.logouts(), 1);
});
