import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import * as vue from "vue";
import { compileScript, parse } from "vue/compiler-sfc";
import ts from "typescript";

function load(source, inlineTemplate = false) {
  const exports = {};
  const content = inlineTemplate
    ? compileScript(parse(source).descriptor, {
        id: "summary-test",
        inlineTemplate: true,
      }).content
    : source;
  runInNewContext(
    ts.transpileModule(content, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText,
    {
      exports,
      require: (id) => {
        if (id === "vue") return vue;
        if (id === "@/utils/quantity") return quantity;
        throw new Error(id);
      },
    },
  );
  return exports;
}
const quantity = load(
  readFileSync(
    new URL("../../../../../../../web/src/utils/quantity.ts", import.meta.url),
    "utf8",
  ),
);
const component = load(
  readFileSync(new URL("./OrderItemSummary.vue", import.meta.url), "utf8"),
  true,
).default;

function render(t, items) {
  const node = (type, text = "") => ({ type, text, children: [], props: {} });
  const renderer = vue.createRenderer({
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
      child.parent?.children.splice(child.parent.children.indexOf(child), 1);
    },
  });
  const root = node("root");
  const app = renderer.createApp(component, {
    items,
    unitLabel: (code) => ({ kg: "千克", set: "台" })[code] || code,
  });
  app.component("ElPopover", {
    props: ["visible"],
    emits: ["update:visible"],
    setup(props, { slots, emit }) {
      return () =>
        vue.h("div", [
          vue.h(
            "div",
            {
              class: "popover-reference",
              onClick: () => emit("update:visible", !props.visible),
            },
            slots.reference?.(),
          ),
          props.visible ? vue.h("aside", slots.default?.()) : null,
        ]);
    },
  });
  app.component("ElScrollbar", {
    setup(_, { slots }) {
      return () => vue.h("div", slots.default?.());
    },
  });
  app.mount(root);
  t.after(() => app.unmount());
  return root;
}
const nodes = (root) => [root, ...root.children.flatMap(nodes)];
const text = (root) =>
  nodes(root)
    .map((node) => node.text)
    .join(" ");

test("mixed units stay paired; all details open in a popover without expanding the table row", async (t) => {
  const root = render(t, [
    { line_no: 1, item_name: "小米", quantity: "12.345", unit_code: "kg" },
    { line_no: 2, item_name: "投影仪", quantity: "5.000", unit_code: "set" },
    { line_no: 3, item_name: "其他物料", quantity: "0.125", unit_code: "box" },
  ]);
  const lines = () =>
    nodes(root).filter((node) => node.props.class === "order-item");
  assert.equal(lines().length, 2);
  assert.match(text(lines()[0]), /小米.*12\.345 千克/);
  assert.match(text(lines()[1]), /投影仪.*5 台/);
  const button = nodes(root).find((node) => node.type === "button");
  assert.match(text(button), /共 3 项.*查看明细/);
  assert.equal(button.props["aria-expanded"], false);
  const reference = nodes(root).find(
    (node) => node.props.class === "popover-reference",
  );
  reference.props.onClick();
  await vue.nextTick();
  assert.equal(lines().length, 2);
  const panel = nodes(root).find((node) => node.type === "aside");
  const details = nodes(panel).filter((node) => node.type === "td");
  assert.equal(details.length, 6);
  assert.equal(details[0].text, "小米");
  assert.match(details[1].text, /12\.345 千克/);
  assert.equal(details[4].text, "其他物料");
  assert.match(details[5].text, /0\.125 box/);
  assert.equal(button.props["aria-expanded"], true);
  reference.props.onClick();
  await vue.nextTick();
  assert.equal(lines().length, 2);
  assert.equal(
    nodes(root).some((node) => node.type === "aside"),
    false,
  );
  assert.equal(button.props["aria-expanded"], false);
});

test("empty orders and missing units are explicit", (t) => {
  assert.match(text(render(t, [])), /—/);
  const root = render(t, [
    { line_no: 1, item_name: "小米", quantity: "2", unit_code: "" },
  ]);
  assert.match(text(root), /2 单位缺失/);
  assert.equal(
    nodes(root).some((node) => node.type === "button"),
    false,
  );
});
