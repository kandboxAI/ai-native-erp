/** 可随纯底座发行的路由契约测试，不读取任何业务插件。 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { test } from "node:test";
import { isDeepStrictEqual } from "node:util";
import ts from "typescript";
import * as vue from "vue";

const exports = {};
runInNewContext(ts.transpileModule(
  readFileSync(new URL("../src/router/authMenuRoutes.ts", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } },
).outputText, { exports });
const menu = (key, extra = {}) => ({ id: key, menu_key: key, menu_name: key,
  menu_type_code: "menu", path: `/${key}`, component: "system/users/index", ...extra });

test("仅为后端授权树注册活动页面，隐藏页面保留直接访问入口", () => {
  const rows = exports.buildAsyncRoutes([menu("users"), menu("hidden", { is_visible: false }),
    menu("disabled", { is_active: false })]);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].path, "/users");
  assert.equal(rows[1].meta.showLink, false);
  assert.equal(rows[0].meta.roles, undefined);
});

test("目录跳转只使用当前授权的可导航子页面", () => {
  const [row] = exports.buildAsyncRoutes([menu("system", { menu_type_code: "directory",
    flex_form: { route: { redirect: "/missing" } }, children: [
      menu("hidden", { is_visible: false }), menu("users"), menu("disabled", { is_active: false }),
    ] })]);
  assert.equal(row.redirect, "/users");
  assert.equal(row.children.length, 2);
});

test("单页签菜单替换同路径的旧列表和详情并保留最新地址", () => {
  const module = {};
  const dependencies = {
    pinia: { defineStore: (_, config) => config },
    "../utils": {
      isUrl: () => false,
      isBoolean: value => typeof value === "boolean",
      isEqual: isDeepStrictEqual,
      getConfig: () => ({})
    }
  };
  runInNewContext(ts.transpileModule(
    readFileSync(new URL("../src/store/modules/multiTags.ts", import.meta.url), "utf8"),
    { compilerOptions: { module: ts.ModuleKind.CommonJS } }
  ).outputText, { exports: module, require: key => dependencies[key] || {} });
  const [route] = exports.buildAsyncRoutes([menu("single", {
    flex_form: { route: { meta: { dynamicLevel: 1 } } }
  })]);
  const home = { path: "/welcome" };
  const other = { path: "/other" };
  const state = { multiTags: [home, route, other, { ...route, query: { id: "old" } }], tagsCache() {} };
  const push = tag => module.useMultiTagsStore.actions.handleTags.call(state, "push", tag);
  const detail = { ...route, query: { id: "active", mode: "engineering" } };
  push(detail);
  assert.equal(state.multiTags.length, 3);
  assert.equal(state.multiTags[0], home);
  assert.equal(state.multiTags[1], detail);
  assert.equal(state.multiTags[2], other);
  push(route);
  assert.equal(state.multiTags.length, 3);
  assert.equal(state.multiTags[1], route);
});

test("首项为顶级页面、单层或多层目录时均可初始化顶部导航", () => {
  const source = readFileSync(new URL("../src/router/utils.ts", import.meta.url), "utf8");
  const tree = ts.createSourceFile("utils.ts", source, ts.ScriptTarget.Latest, true);
  const functions = tree.statements.filter(node => ts.isFunctionDeclaration(node) &&
    ["handleTopMenu", "getTopMenu"].includes(node.name?.text)).map(node => node.getText(tree)).join("\n");
  const state = { wholeMenus: [] };
  const pushes = [];
  const context = {
    usePermissionStoreHook: () => state,
    useMultiTagsStoreHook: () => ({ handleTags: (...args) => pushes.push(args) })
  };
  runInNewContext(ts.transpileModule(functions, {}).outputText + "; this.topMenu = getTopMenu;", context);
  const dashboard = { path: "/dashboard", name: "Dashboard" };
  const first = { path: "/first" }, redirected = { path: "/chosen" };
  for (const [menus, expected] of [
    [[dashboard], dashboard],
    [[{ path: "/group", children: [dashboard] }], dashboard],
    [[{ path: "/group", children: [{ path: "/nested", children: [dashboard] }] }], dashboard],
    [[{ path: "/group", redirect: "/chosen", children: [first, redirected] }], redirected],
    [[{ path: "/group", redirect: "/removed", children: [first] }], first]
  ]) {
    state.wholeMenus = menus;
    assert.equal(context.topMenu(), expected);
    assert.equal(context.topMenu(true), expected);
  }
  state.wholeMenus = [];
  const count = pushes.length;
  assert.equal(context.topMenu(true), undefined);
  assert.equal(pushes.length, count);
});

test("首次访问没有界面缓存时标签栏默认显示，并尊重已有隐藏设置", () => {
  const source = readFileSync(new URL("../src/layout/hooks/useTag.ts", import.meta.url), "utf8");
  for (const saved of [null, undefined, {}, { hideTabs: false }, { hideTabs: true }]) {
    const module = {};
    const dependencies = {
      vue: { ...vue, getCurrentInstance: () => ({ refs: {} }), onMounted() {} },
      "vue-router": { useRoute: () => ({ meta: {}, query: {}, params: {} }), useRouter: () => ({}) },
      "@/config": { responsiveStorageNameSpace: () => "test-" },
      "@pureadmin/utils": { storageLocal: () => ({ getItem: () => saved }) },
      "@/plugins/i18n": { $t: value => value },
      "@/store/modules/settings": { useSettingStoreHook: () => ({}) },
      "@/store/modules/multiTags": { useMultiTagsStoreHook: () => ({ multiTags: [{ path: "/welcome" }, { path: "/workbench" }] }) }
    };
    runInNewContext(ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS }
    }).outputText, { exports: module, require: key => dependencies[key] || {} });
    const tags = module.useTags();
    assert.equal(tags.showTags.value, saved?.hideTabs ?? false);
    assert.equal(tags.tagsViews.length, 7);
    assert.equal(tags.multiTags.value.length, 2);
  }
});
