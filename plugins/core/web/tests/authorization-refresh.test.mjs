import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const compiled = ts.transpileModule(
  readFileSync(
    new URL("../src/store/modules/user.ts", import.meta.url),
    "utf8"
  ),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } }
).outputText;

function setup(fetchUser) {
  let session = {
    userId: "user-1",
    accessToken: "access",
    refreshToken: "refresh",
    sessionExpires: 123456789
  };
  const cache = new Map([
    ["user-info", { permissions: ["old:list"], roles: [] }]
  ]);
  let config;
  let tokenWrites = 0;
  const exports = {};
  runInNewContext(compiled, {
    exports,
    require(id) {
      if (id === "pinia")
        return {
          defineStore(_, value) {
            config = value;
            return () => user;
          }
        };
      if (id === "../utils")
        return {
          storageLocal: () => ({
            getItem: key => cache.get(key),
            setItem: (key, value) => cache.set(key, value)
          })
        };
      if (id === "@/api/user") return { getCurrentUser: fetchUser };
      if (id === "@/utils/auth")
        return {
          userKey: "user-info",
          getToken: () => session,
          setToken: () => tokenWrites++
        };
      if (id === "./multiTags") return {};
      throw new Error(id);
    }
  });
  const user = { ...config.state(), ...config.actions };
  return {
    user,
    cache,
    tokenWrites: () => tokenWrites,
    session: () => session,
    setSession: value => {
      session = value;
    }
  };
}

const response = permissions => ({
  code: 0,
  data: { user_id: "user-1", permissions, role_nos: ["viewer"] }
});

test("fresh backend permissions replace login cache without touching tokens or deadline", async () => {
  const app = setup(async () => response(["inventory_product:list"]));
  const session = app.session();
  await app.user.refreshCurrentUser();
  assert.deepEqual([...app.user.permissions], ["inventory_product:list"]);
  assert.deepEqual(
    [...app.cache.get("user-info").permissions],
    ["inventory_product:list"]
  );
  assert.equal(app.session(), session);
  assert.equal(app.tokenWrites(), 0);
});

test("revoked permissions are removed instead of merged with cached grants", async () => {
  const app = setup(async () => response([]));
  await app.user.refreshCurrentUser();
  assert.equal(app.user.permissions.length, 0);
  assert.equal(app.cache.get("user-info").permissions.length, 0);
});

test("a late response cannot restore permissions after logout or an account switch", async () => {
  for (const replacement of [
    null,
    { userId: "other-user", sessionExpires: 987654321 }
  ]) {
    let finish;
    const app = setup(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    );
    const pending = app.user.refreshCurrentUser();
    app.setSession(replacement);
    app.user.permissions = ["other:list"];
    finish(response(["inventory_product:list"]));
    await assert.rejects(pending, /登录状态已改变/);
    assert.deepEqual(app.user.permissions, ["other:list"]);
  }
});

test("normal token rotation within the same fixed session allows permission refresh", async () => {
  let finish;
  const app = setup(
    () =>
      new Promise(resolve => {
        finish = resolve;
      })
  );
  const pending = app.user.refreshCurrentUser();
  app.setSession({
    ...app.session(),
    accessToken: "rotated",
    refreshToken: "rotated-refresh"
  });
  finish(response(["inventory_product:list"]));
  await pending;
  assert.deepEqual([...app.user.permissions], ["inventory_product:list"]);
  assert.equal(app.session().accessToken, "rotated");
});

test("failed authorization refresh clears stale grants and remains retryable", async () => {
  const app = setup(async () => {
    throw new Error("offline");
  });
  await assert.rejects(app.user.refreshCurrentUser(), /offline/);
  assert.equal(app.user.permissions.length, 0);
  assert.equal(app.cache.get("user-info").permissions.length, 0);
  assert.ok(app.session());
});
