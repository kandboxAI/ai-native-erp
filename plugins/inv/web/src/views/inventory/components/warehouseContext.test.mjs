import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

test("当前仓库仅复用当前账号会话中仍在授权候选内的选择", () => {
  const source = readFileSync(new URL("./warehouseContext.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const entries = new Map();
  let identity = { userId: "academic", sessionExpires: 10 };
  const exports = {};
  runInNewContext(compiled, {
    exports,
    require: () => ({ getToken: () => identity }),
    window: { sessionStorage: {
      getItem: key => entries.get(key), setItem: (key, value) => entries.set(key, value), removeItem: key => entries.delete(key)
    } }
  });
  const { preferredWarehouseId: preferred, rememberWarehouse: remember } = exports;
  const options = [{ id: "textbook" }, { id: "hq" }];
  assert.equal(preferred(options), "");
  assert.equal(preferred([options[0]]), "textbook");
  remember("hq");
  assert.equal(preferred(options), "hq");
  identity = { userId: "logistics", sessionExpires: 10 };
  assert.equal(preferred(options), "");
  identity = { userId: "academic", sessionExpires: 11 };
  assert.equal(preferred(options), "");
  identity.sessionExpires = 10;
  assert.equal(preferred([options[0]]), "textbook");
  assert.equal(preferred(options), ""); // 失效 ID 已清除，不能在后续选项中复活。
});
