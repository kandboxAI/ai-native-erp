import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/utils/desktopSession.ts", import.meta.url),
  "utf8"
).replace("if (import.meta.hot) import.meta.hot.dispose(dispose);", "");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS }
}).outputText;

function setup(refresh, bind = async () => {}) {
  let session = { accessToken: "old-token", refreshToken: "refresh-token" };
  let listener;
  let retries = [];
  let logouts = 0;
  const notices = [];
  const exports = {};
  const store = {
    async handRefreshToken(data) {
      await refresh(data);
      session = { accessToken: "new-token", refreshToken: "new-refresh" };
      return { data: session };
    },
    logOut() {
      logouts++;
      session = null;
    }
  };
  runInNewContext(compiled, {
    exports,
    window: {
      erpDesktop: {
        bindErpSession: bind,
        onErpSessionExpired(callback) {
          listener = callback;
          return () => {
            listener = undefined;
          };
        }
      }
    },
    setTimeout(callback) {
      retries.push(callback);
      return callback;
    },
    clearTimeout(callback) {
      retries = retries.filter(item => item !== callback);
    },
    require(id) {
      if (id === "@/utils/auth") return { getToken: () => session };
      if (id === "@/store/modules/user")
        return { useUserStoreHook: () => store };
      if (id === "@/utils/message")
        return { message: text => notices.push(text) };
      throw new Error(id);
    }
  });
  const dispose = exports.installDesktopSession();
  return {
    dispose,
    emit: () => listener?.(),
    retry: () => retries.shift()?.(),
    switchAccount: () => {
      session = { accessToken: "other-token", refreshToken: "other-refresh" };
    },
    state: () => ({ session, logouts, notices, retryCount: retries.length })
  };
}

const flush = () => new Promise(resolve => setImmediate(resolve));

test("expired access token refreshes silently with one concurrent request", async () => {
  let release;
  let calls = 0;
  const app = setup(() => {
    calls++;
    return new Promise(resolve => {
      release = resolve;
    });
  });
  app.emit();
  app.emit();
  assert.equal(calls, 1);
  release();
  await flush();
  assert.equal(app.state().session.accessToken, "new-token");
  assert.equal(app.state().logouts, 0);
  app.dispose();
});

test("rejected refresh redirects to login and explains that chats are retained", async () => {
  const app = setup(async () => {
    throw { response: { status: 401 } };
  });
  app.emit();
  await flush();
  assert.equal(app.state().logouts, 1);
  assert.match(app.state().notices[0], /聊天记录会保留/);
  assert.equal(app.state().retryCount, 0);
  app.dispose();
});

test("a backend outage retries and recovers without signing out", async () => {
  let online = false;
  const app = setup(async () => {
    if (!online) throw { response: { status: 503 } };
  });
  app.emit();
  await flush();
  assert.equal(app.state().logouts, 0);
  assert.equal(app.state().retryCount, 1);
  online = true;
  app.retry();
  await flush();
  assert.equal(app.state().session.accessToken, "new-token");
  assert.equal(app.state().retryCount, 0);
  app.dispose();
});

test("a stale authentication rejection cannot sign out a different account", async () => {
  let reject;
  const app = setup(
    () =>
      new Promise((_, fail) => {
        reject = fail;
      })
  );
  app.emit();
  app.switchAccount();
  reject({ response: { status: 401 } });
  await flush();
  assert.equal(app.state().logouts, 0);
  assert.equal(app.state().session.accessToken, "other-token");
  app.dispose();
});

test("a renewed ERP login still rejected by the gateway opens login instead of refreshing forever", async () => {
  const app = setup(
    async () => {},
    async () => {
      throw new Error("ERP_SESSION_EXPIRED: ERP 登录已失效，请重新登录");
    }
  );
  app.emit();
  await flush();
  assert.equal(app.state().logouts, 1);
  assert.equal(app.state().retryCount, 0);
  app.dispose();
});

test("disposing the page cancels recovery timers", async () => {
  const app = setup(async () => {
    throw new TypeError("offline");
  });
  app.emit();
  await flush();
  app.dispose();
  assert.equal(app.state().retryCount, 0);
});

function loadRefreshAction({
  shared = { session: { refreshToken: "refresh-token" } },
  locks
} = {}) {
  const compiledStore = ts.transpileModule(
    readFileSync(
      new URL("../src/store/modules/user.ts", import.meta.url),
      "utf8"
    ),
    { compilerOptions: { module: ts.ModuleKind.CommonJS } }
  ).outputText;
  let release;
  let calls = 0;
  const exports = {};
  runInNewContext(compiledStore, {
    exports,
    window: { navigator: { locks } },
    require(id) {
      if (id === "pinia")
        return { defineStore: (_name, options) => options.actions };
      if (id === "../utils") return {};
      if (id === "@/api/user")
        return {
          refreshTokenApi: () => {
            calls++;
            return new Promise(resolve => {
              release = resolve;
            });
          }
        };
      if (id === "./multiTags") return {};
      if (id === "@/utils/auth")
        return {
          getToken: () => shared.session,
          setToken: data => {
            shared.session = {
              ...data,
              expires: new Date(data.expires).getTime()
            };
          }
        };
      throw new Error(id);
    }
  });
  return {
    refresh: () =>
      exports.useUserStore.handRefreshToken({ refreshToken: "refresh-token" }),
    resolve: () =>
      release({
        code: 0,
        data: {
          accessToken: "new-access",
          refreshToken: "rotated-token",
          userId: "user-1",
          rememberMe: true,
          expires: new Date(Date.now() + 7200000),
          sessionExpires: Date.now() + 86400000
        }
      }),
    logout: () => {
      shared.session = null;
    },
    state: () => ({ session: shared.session, calls })
  };
}

test("desktop and HTTP refreshes share one token rotation", async () => {
  const store = loadRefreshAction();
  const first = store.refresh();
  const second = store.refresh();
  assert.equal(store.state().calls, 1);
  store.resolve();
  await Promise.all([first, second]);
  assert.equal(store.state().session.refreshToken, "rotated-token");
});

test("an in-flight refresh cannot restore a login after logout", async () => {
  const store = loadRefreshAction();
  const pending = store.refresh();
  store.logout();
  store.resolve();
  await assert.rejects(pending, /登录状态已改变/);
  assert.equal(store.state().session, null);
});

function queuedLocks() {
  let pending = Promise.resolve();
  return {
    request(_name, callback) {
      const next = pending.then(callback);
      pending = next.catch(() => {});
      return next;
    }
  };
}

test("browser tabs serialize rotation and reuse the same account's refreshed token", async () => {
  const shared = {
    session: { userId: "user-1", refreshToken: "refresh-token", expires: 0 }
  };
  const locks = queuedLocks();
  const firstTab = loadRefreshAction({ shared, locks });
  const secondTab = loadRefreshAction({ shared, locks });
  const first = firstTab.refresh();
  const second = secondTab.refresh();
  await flush();
  firstTab.resolve();
  const results = await Promise.all([first, second]);
  assert.equal(firstTab.state().calls, 1);
  assert.equal(secondTab.state().calls, 0);
  assert.equal(results[1].data.accessToken, "new-access");
});

test("a waiting tab cannot use a different account's login after a switch", async () => {
  const shared = {
    session: { userId: "user-1", refreshToken: "refresh-token", expires: 0 }
  };
  const tab = loadRefreshAction({ shared, locks: queuedLocks() });
  const pending = tab.refresh();
  shared.session = {
    userId: "user-2",
    refreshToken: "other-refresh",
    expires: Date.now() + 7200000
  };
  await assert.rejects(pending, /登录状态已改变/);
  assert.equal(tab.state().calls, 0);
});
