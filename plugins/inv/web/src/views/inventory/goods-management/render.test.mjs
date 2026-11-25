import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import { createRenderer, h, nextTick, ref } from "vue";
import * as vue from "vue";
import { parse, compileScript } from "vue/compiler-sfc";
import ts from "typescript";

const { descriptor } = parse(
  readFileSync(new URL("./index.vue", import.meta.url), "utf8"),
);
const compiled = ts.transpileModule(
  compileScript(descriptor, { id: "material-test", inlineTemplate: true })
    .content,
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      esModuleInterop: true,
      target: ts.ScriptTarget.ES2022,
    },
  },
).outputText;

async function render(grants, error, props = {}) {
  const menuView = typeof props === "string" ? props : undefined;
  props = typeof props === "string" ? {} : props;
  const permissions = ref([]); // Reproduce the stale login cache before /auth/me returns.
  const tree = { children: [] };
  const node = (type, text = "") => ({
    type,
    text,
    children: [],
    props: {},
    parent: null,
  });
  const renderer = createRenderer({
    createElement: (type) => node(type),
    createText: (text) => node("text", text),
    createComment: () => node("comment"),
    setText: (target, text) => {
      target.text = text;
    },
    setElementText: (target, text) => {
      target.text = text;
      target.children = [];
    },
    parentNode: (target) => target.parent,
    nextSibling: (target) =>
      target.parent?.children[target.parent.children.indexOf(target) + 1],
    patchProp: (target, key, _, value) => {
      target.props[key] = value;
    },
    insert(child, parent, anchor) {
      if (child.parent)
        child.parent.children.splice(child.parent.children.indexOf(child), 1);
      const index = parent.children.indexOf(anchor);
      parent.children.splice(
        index < 0 ? parent.children.length : index,
        0,
        child,
      );
      child.parent = parent;
    },
    remove(child) {
      if (child.parent)
        child.parent.children.splice(child.parent.children.indexOf(child), 1);
    },
  });
  const stub = {
    props: ["description", "title"],
    setup:
      (props, { slots }) =>
      () =>
        h("div", [
          props.description,
          props.title,
          slots.header?.(),
          slots.default?.(),
        ]),
  };
  const itemTab = {
    setup(_, { expose }) {
      expose({ reload() {} });
      return () => h("section", "物料列表");
    },
  };
  const crudTab = {
    props: ["noun"],
    setup:
      (props, { slots }) =>
      () =>
        h("section", [
          props.noun + "列表",
          slots.actions?.({ row: { id: "warehouse-1", is_active: true } }),
        ]),
  };
  const api = new Proxy(
    {},
    { get: () => async () => ({ code: 0, data: { items: [] } }) },
  );
  const tabModule = {};
  runInNewContext(
    ts.transpileModule(
      readFileSync(new URL("./tabAccess.ts", import.meta.url), "utf8"),
      { compilerOptions: { module: ts.ModuleKind.CommonJS } },
    ).outputText,
    { exports: tabModule },
  );
  const exports = {};
  runInNewContext(compiled, {
    exports,
    require(id) {
      if (id === "vue") return vue;
      if (id === "@/utils/auth")
        return {
          hasPerms: (permission) => permissions.value.includes(permission),
        };
      if (id === "@/store/modules/user")
        return {
          useUserStoreHook: () => ({
            async refreshCurrentUser() {
              if (error) throw error;
              permissions.value = grants;
            },
          }),
        };
      if (id === "@/utils/menuView")
        return { useMenuView: (fallback) => ref(menuView || fallback) };
      if (id === "vue-router")
        return { useRoute: () => ({ meta: { menuView } }) };
      if (id === "@/utils/http")
        return {
          getHttpErrorMessage: (value, fallback) => value?.message || fallback,
        };
      if (id === "element-plus") return { ElMessage: {}, ElMessageBox: {} };
      if (id === "@element-plus/icons-vue") return { Upload: () => null };
      if (id === "../components/common")
        return {
          useOrgOptions: () => ({
            orgOptions: ref([]),
            loadOrgOptions: async () => {},
          }),
          useInventoryMeta: () => ({
            meta: ref({}),
            loadMeta: async () => {},
            label: () => "",
          }),
        };
      if (id === "./tabAccess") return tabModule;
      if (id === "./ItemTab.vue") return { __esModule: true, default: itemTab };
      if (id === "./SimpleCrudTab.vue")
        return { __esModule: true, default: crudTab };
      if (id === "./GoodsImportDialog.vue")
        return { __esModule: true, default: () => null };
      if (id === "./WarehouseRequisitionScopeDialog.vue" || id === "./WarehouseAccessDialog.vue")
        return { __esModule: true, default: () => null };
      if (id.startsWith("@/api/") || id.startsWith("@plugins/inv/web/src/api/"))
        return api;
      throw new Error(id);
    },
  });
  const app = renderer.createApp(exports.default, props);
  for (const name of [
    "ReListPresentation",
    "el-card",
    "el-empty",
    "el-tabs",
    "el-tab-pane",
    "el-alert",
    "el-button",
    "el-table-column",
    "el-table",
    "ReListTable",
    "el-input",
    "el-form-item",
    "el-col",
    "el-switch",
    "el-row",
    "el-form",
  ])
    app.component(name, stub);
  app.component("ReMenuViews", {
    setup:
      (_, { slots }) =>
      () =>
        h(
          "section",
          (slots.default?.() || []).filter(
            (node) => !menuView || node.props?.name === menuView,
          ),
        ),
  });
  app.component("el-dialog", () => null);
  app.directive("loading", {});
  app.mount(tree);
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
  const text = (target) =>
    (target.text || "") + (target.children || []).map(text).join("");
  const result = text(tree);
  app.unmount();
  return result;
}

test("an empty login cache is refreshed and the real page renders its authorized material pane", async () => {
  const text = await render(["inventory_product:list"]);
  assert.ok(text.includes("物料列表"));
  assert.ok(!text.includes("物料与基础资料"));
  assert.ok(!text.includes("暂无可查看"));
});

test("the real page displays authorized warehouse content without item permission", async () => {
  const text = await render(["inventory_warehouse:list"]);
  assert.ok(text.includes("仓库列表"));
  assert.ok(!text.includes("物料与基础资料"));
  assert.ok(!text.includes("物料列表"));
});

test("missing permissions show an explanation and retry instead of a title-only page", async () => {
  const text = await render([]);
  assert.ok(text.includes("暂无可查看的物资资料"));
  assert.ok(text.includes("刷新权限"));
});

test("an authorization request failure displays an error and a retry action", async () => {
  const text = await render([], new Error("读取权限失败"));
  assert.ok(text.includes("读取权限失败"));
  assert.ok(text.includes("刷新权限"));
});

test("MES goods archive reuses the material pane without exposing foundation tabs", async () => {
  const text = await render(
    [
      "inventory_product:list",
      "supplier:list",
      "inventory_warehouse:list",
      "inventory_product_category:list",
    ],
    undefined,
    { onlyTab: "items", title: "货品档案" },
  );
  assert.ok(text.includes("货品档案") && text.includes("物料列表"));
  assert.ok(
    !text.includes("供应商列表") &&
      !text.includes("仓库列表") &&
      !text.includes("物料分类列表"),
  );
});

test("MES supplier archive displays only the authorized shared supplier pane", async () => {
  const text = await render(
    ["inventory_product:list", "supplier:list", "inventory_warehouse:list"],
    undefined,
    { onlyTab: "suppliers", title: "供应商档案" },
  );
  assert.ok(text.includes("供应商档案") && text.includes("供应商列表"));
  assert.ok(!text.includes("物料列表") && !text.includes("仓库列表"));
});

test("a warehouse menu stays on its requested function after the login cache is refreshed", async () => {
  const text = await render(
    ["inventory_product:list", "inventory_warehouse:list"],
    undefined,
    "warehouses",
  );
  assert.ok(text.includes("仓库列表"));
  assert.ok(!text.includes("物料列表"));
});

test("a revoked menu does not fall back to another authorized material function", async () => {
  const text = await render(["inventory_warehouse:list"], undefined, "items");
  assert.ok(text.includes("暂无可查看"));
  assert.ok(!text.includes("仓库列表"));
});

test("仓库操作栏仅向有申领范围配置权限的人显示入口", async () => {
  const readonly = await render(
    ["inventory_warehouse:list"],
    undefined,
    "warehouses",
  );
  assert.ok(!readonly.includes("申领范围"));
  const manager = await render(
    ["inventory_warehouse:list", "inventory_warehouse:requisition_scope"],
    undefined,
    "warehouses",
  );
  assert.ok(manager.includes("申领范围"));
});

test("管理账号授权入口要求独立权限", async () => {
  const readonly = await render(["inventory_warehouse:list"], undefined, "warehouses");
  assert.ok(!readonly.includes("管理账号"));
  const manager = await render(["inventory_warehouse:list", "inventory_warehouse:authorize"], undefined, "warehouses");
  assert.ok(manager.includes("管理账号"));
});
