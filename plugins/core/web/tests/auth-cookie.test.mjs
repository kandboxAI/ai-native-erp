import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/utils/auth.ts", import.meta.url),
  "utf8"
);
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true }
}).outputText;

function loadAuth({
  cookiesAvailable = true,
  userValues = new Map(),
  sessionValues = new Map()
} = {}) {
  let contextResets = 0;
  const cookieValues = new Map();
  const cookieOptions = new Map();
  const cookies = {
    get(key) {
      return cookiesAvailable ? cookieValues.get(key) : undefined;
    },
    set(key, value, options) {
      if (cookiesAvailable) cookieValues.set(key, value);
      cookieOptions.set(key, options);
    },
    remove(key) {
      cookieValues.delete(key);
    }
  };
  const storage = {
    getItem: key => userValues.get(key) ?? null,
    setItem: (key, value) => userValues.set(key, value),
    removeItem: key => userValues.delete(key)
  };
  const userStore = {
    isRemembered: false,
    loginDay: 7,
    SET_AVATAR() {},
    SET_USERNAME() {},
    SET_NICKNAME() {},
    SET_ROLES() {},
    SET_PERMS() {}
  };
  const exports = {};
  runInNewContext(compiled, {
    exports,
    window: {
      sessionStorage: {
        getItem: key => sessionValues.get(key) ?? null,
        setItem: (key, value) => sessionValues.set(key, value),
        removeItem: key => sessionValues.delete(key)
      }
    },
    require(id) {
      switch (id) {
        case "@/store":
          return { store: {} };
        case "@/store/modules/aiPageContext":
          return {
            useAiPageContextStore: () => ({
              resetContext() {
                contextResets++;
              }
            })
          };
        case "js-cookie":
          return cookies;
        case "@/store/modules/user":
          return { useUserStoreHook: () => userStore };
        case "@pureadmin/utils":
          return {
            storageLocal: () => storage,
            isString: value => typeof value === "string",
            isIncludeAllChildren: () => false
          };
        default:
          throw new Error(`unexpected import: ${id}`);
      }
    }
  });
  return {
    auth: exports,
    contextResetCount: () => contextResets,
    cookieValues,
    cookieOptions,
    sessionValues,
    userValues
  };
}

const login = accessToken => ({
  accessToken,
  refreshToken: "refresh-token",
  expires: new Date(Date.now() + 60_000),
  rememberMe: false,
  sessionExpires: Date.now() + 12 * 60 * 60 * 1000,
  username: "tester",
  roles: ["user"]
});

test("login keeps its cookie and multi-tab behavior", () => {
  const { auth, cookieValues, userValues } = loadAuth();
  userValues.set("async-routes", [{ path: "/stale-account-route" }]);
  userValues.set(auth.asyncRoutesKey, [{ path: "/stale-versioned-route" }]);
  auth.setToken(login("standalone-token"));
  assert.equal(auth.getToken().accessToken, "standalone-token");
  assert.equal(cookieValues.has(auth.TokenKey), true);
  assert.equal(cookieValues.has(auth.multipleTabsKey), true);
  assert.equal(userValues.has(auth.TokenKey), false);
  assert.equal(userValues.has("async-routes"), false);
  assert.equal(userValues.has(auth.asyncRoutesKey), false);
  userValues.set(auth.asyncRoutesKey, [{ path: "/current-account-route" }]);
  auth.removeToken();
  assert.equal(cookieValues.size, 0);
  assert.equal(userValues.has(auth.asyncRoutesKey), false);
});

test("temporary desktop login survives reload but not a new client window", () => {
  const { auth, userValues, sessionValues } = loadAuth({
    cookiesAvailable: false
  });
  userValues.set(auth.userKey, { username: "stale user" });
  assert.equal(auth.getToken(), null);

  auth.setToken(login("desktop-token"));
  assert.equal(auth.getToken().accessToken, "desktop-token");
  assert.equal(userValues.has(auth.TokenKey), false);
  assert.equal(userValues.get(auth.userKey).refreshToken, undefined);
  const reload = loadAuth({
    cookiesAvailable: false,
    userValues,
    sessionValues
  });
  assert.equal(reload.auth.getToken().accessToken, "desktop-token");
  const restart = loadAuth({ cookiesAvailable: false, userValues });
  assert.equal(restart.auth.getToken(), null);

  auth.removeToken();
  assert.equal(auth.getToken(), null);
  assert.equal(userValues.has(auth.TokenKey), false);
  assert.equal(sessionValues.has(auth.TokenKey), false);
});

test("remembered browser and desktop login restores after restart and keeps the backend deadline on refresh", () => {
  for (const cookiesAvailable of [true, false]) {
    const app = loadAuth({ cookiesAvailable });
    const sessionExpires = Date.now() + 7 * 86400000;
    app.auth.setToken({
      ...login("remembered"),
      rememberMe: true,
      sessionExpires
    });
    assert.equal(
      app.userValues.get(app.auth.TokenKey).accessToken,
      "remembered"
    );
    assert.equal(app.sessionValues.has(app.auth.TokenKey), false);
    assert.equal(
      app.cookieOptions.get(app.auth.TokenKey).expires.getTime(),
      sessionExpires
    );
    assert.equal(
      app.cookieOptions.get(app.auth.multipleTabsKey).expires.getTime(),
      sessionExpires
    );
    const restart = loadAuth({ cookiesAvailable, userValues: app.userValues });
    assert.equal(restart.auth.getToken().accessToken, "remembered");
    restart.auth.setToken({
      ...login("refreshed"),
      rememberMe: true,
      sessionExpires
    });
    assert.equal(restart.auth.getToken().sessionExpires, sessionExpires);
    assert.equal(restart.auth.getToken().rememberMe, true);
    restart.auth.removeToken();
    assert.equal(restart.auth.getToken(), null);
  }
});

test("temporary browser cookies have no persistent expiry", () => {
  const app = loadAuth();
  app.auth.setToken(login("temporary"));
  assert.equal(app.cookieOptions.get(app.auth.TokenKey).expires, undefined);
  assert.equal(
    app.cookieOptions.get(app.auth.multipleTabsKey).expires,
    undefined
  );
  app.cookieValues.clear();
  app.sessionValues.clear();
  assert.equal(app.auth.getToken(), null);
});

test("a remembered session cannot restore after its fixed deadline even if access token claims remain cached", () => {
  const app = loadAuth({ cookiesAvailable: false });
  app.auth.setToken({
    ...login("expired"),
    rememberMe: true,
    sessionExpires: Date.now() - 1000
  });
  assert.equal(app.auth.isLoginSessionActive(), false);
});

test("legacy desktop persistent tokens are not restored without an explicit remember policy", () => {
  const app = loadAuth({ cookiesAvailable: false });
  app.userValues.set(app.auth.TokenKey, {
    accessToken: "legacy",
    refreshToken: "legacy-refresh"
  });
  assert.equal(app.auth.getToken(), null);
});

test("page context clears on account or tenant-user switch and logout, but survives token rotation", () => {
  const { auth, contextResetCount } = loadAuth();
  auth.setToken({ ...login("first"), userId: "tenant-user-1" });
  assert.equal(contextResetCount(), 1);
  auth.setToken({ ...login("rotated"), userId: "tenant-user-1" });
  auth.setToken(login("legacy-rotation-without-user-id"));
  assert.equal(contextResetCount(), 1);
  auth.setToken({ ...login("other-tenant"), userId: "tenant-user-2" });
  assert.equal(contextResetCount(), 2);
  auth.removeToken();
  assert.equal(contextResetCount(), 3);
});
