import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const compiled = ts.transpileModule(
  readFileSync(new URL("../src/api/user.ts", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } }
).outputText;

function loadApi(session) {
  const exports = {};
  const requests = [];
  runInNewContext(compiled, {
    exports,
    require(id) {
      if (id !== "@/utils/http") throw new Error(id);
      return {
        http: {
          async request(method, url, options) {
            requests.push({ method, url, data: options?.data });
            return {
              code: 0,
              data: url.endsWith("/login")
                ? {
                    session,
                    user: { user_id: "user-1", roles: [], permissions: [] }
                  }
                : session
            };
          }
        }
      };
    }
  });
  return { api: exports, requests };
}

test("login sends the checkbox and selected days and uses the backend's policy", async () => {
  const deadline = Math.floor(Date.now() / 1000) + 7 * 86400;
  const { api, requests } = loadApi({
    access_token: "access",
    refresh_token: "refresh",
    expires_in: 7200,
    remember_me: true,
    session_expires_at: deadline
  });
  const result = await api.getLogin({
    username: "admin",
    password: "password",
    captchaId: "captcha",
    captchaCode: "1234",
    rememberMe: true,
    rememberDays: 7
  });
  assert.equal(requests[0].data.remember_me, true);
  assert.equal(requests[0].data.remember_days, 7);
  assert.equal(result.data.rememberMe, true);
  assert.equal(result.data.sessionExpires, deadline * 1000);
  assert.equal(result.data.userId, "user-1");
});

test("refresh preserves the backend's deadline and remember policy", async () => {
  const deadline = Math.floor(Date.now() / 1000) + 1800;
  const { api, requests } = loadApi({
    user_id: "user-1",
    access_token: "new-access",
    refresh_token: "new-refresh",
    expires_at: deadline,
    remember_me: false,
    session_expires_at: deadline
  });
  const result = await api.refreshTokenApi({ refreshToken: "old-refresh" });
  assert.equal(requests[0].data.refresh_token, "old-refresh");
  assert.equal(result.data.rememberMe, false);
  assert.equal(result.data.sessionExpires, deadline * 1000);
  assert.equal(result.data.userId, "user-1");
});
