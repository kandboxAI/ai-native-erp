import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const require = createRequire(
  new URL("../../../../web/package.json", import.meta.url)
);
const { build } = require("esbuild");
const { parse, compileScript, compileTemplate } = require("@vue/compiler-sfc");
const { createRenderer, nextTick } = require("vue");
const renderer = createRenderer({
  createElement: () => ({}),
  createText: () => ({}),
  createComment: () => ({}),
  insert() {},
  remove() {},
  patchProp() {},
  setText() {},
  setElementText() {},
  parentNode: () => null,
  nextSibling: () => null
});

async function fixture() {
  const calls = [],
    notices = [];
  const data = {
    version_no: 4,
    config: {
      is_auto_apply: true,
      materials: [],
      processes: [
        {
          id: "old",
          name: "CNC通用",
          keywords: ["CNC"],
          is_active: true,
          hourly_rate: 60
        }
      ],
      external_processes: []
    },
    process_catalog: [],
    manufacturing_processes: [
      {
        id: "cnc2",
        process_no: "GY005",
        process_name: "CNC2",
        processing_type_code: "in_house",
        process_type_code: "cnc"
      },
      {
        id: "cnc4",
        process_no: "GY006",
        process_name: "CNC4",
        processing_type_code: "in_house",
        process_type_code: "cnc"
      },
      {
        id: "out",
        process_no: "OUT01",
        process_name: "委外氧化",
        processing_type_code: "outsourced"
      }
    ]
  };
  globalThis.__quoteRuleBinding = {
    async request(path, options) {
      calls.push({ path, options });
      return structuredClone(data);
    },
    notice(value) {
      notices.push(value);
    }
  };
  const filename = fileURLToPath(
    new URL(
      "../src/views/mes/quoting/components/QuoteRules.vue",
      import.meta.url
    )
  );
  const { descriptor } = parse(readFileSync(filename, "utf8"));
  const script = compileScript(descriptor, { id: "quote-rules" });
  assert.deepEqual(
    compileTemplate({
      source: descriptor.template.content,
      filename,
      id: "quote-rules",
      compilerOptions: { bindingMetadata: script.bindings }
    }).errors,
    []
  );
  const result = await build({
    stdin: {
      contents: script.content,
      loader: "ts",
      resolveDir: fileURLToPath(new URL("../../../../web/", import.meta.url))
    },
    bundle: true,
    write: false,
    platform: "node",
    format: "cjs",
    external: ["vue"],
    plugins: [
      {
        name: "isolated-rule-editor",
        setup(builder) {
          builder.onResolve({ filter: /.*/ }, args =>
            args.path === "vue"
              ? undefined
              : { path: args.path, namespace: "mock" }
          );
          builder.onLoad({ filter: /.*/, namespace: "mock" }, args => ({
            contents: args.path.endsWith(".vue")
              ? "export default {};"
              : args.path === "element-plus"
                ? "export const ElMessage={error:globalThis.__quoteRuleBinding.notice,warning:globalThis.__quoteRuleBinding.notice,success:globalThis.__quoteRuleBinding.notice};"
                : "export const request=(...args)=>globalThis.__quoteRuleBinding.request(...args);export const jsonOptions=(value,method)=>({body:JSON.stringify(value),method});"
          }));
        }
      }
    ]
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", result.outputFiles[0].text)(
    require,
    module,
    module.exports
  );
  const component = module.exports.default;
  component.render = () => null;
  const app = renderer.createApp(component, { orgId: "org1" });
  const vm = app.mount({});
  const state = vm.$.setupState;
  await state.show();
  return { state, calls, notices, stop: () => app.unmount() };
}

test("batch creates separate formal rules and preserves existing generic rates", async () => {
  const { state, calls, stop } = await fixture();
  try {
    assert.deepEqual(
      state.processOptions("processes").map(row => row.id),
      ["cnc2", "cnc4"]
    );
    assert.deepEqual(
      state.processOptions("external_processes").map(row => row.id),
      ["out"]
    );
    state.pendingProcesses = ["cnc2", "cnc4"];
    state.addProcesses();
    assert.equal(state.config.processes.length, 3);
    assert.deepEqual(
      state.config.processes.slice(1).map(row => row.process_id),
      ["cnc2", "cnc4"]
    );
    assert.equal(state.config.processes[1].process_type_code, "cnc");
    assert.equal(state.config.processes[1].hourly_rate, undefined);
    assert.equal(state.config.processes[0].hourly_rate, 60);
    assert.equal(state.isBound("cnc2"), true);
    state.pendingProcesses = ["cnc2"];
    state.addProcesses();
    assert.equal(state.config.processes.length, 3);
    await state.save();
    const saved = JSON.parse(calls.at(-1).options.body);
    assert.equal(saved.version_no, 4);
    assert.equal(saved.config.processes[1].process_id, "cnc2");
    assert.deepEqual(saved.config.processes[1].keywords, []);
    assert.equal(state.open, false);
  } finally {
    stop();
  }
});

test("external tab creates external binding and clearing binding requires generic keywords", async () => {
  const { state, calls, notices, stop } = await fixture();
  try {
    state.tab = "external";
    await nextTick();
    state.pendingProcesses = ["out"];
    state.addProcesses();
    assert.equal(state.config.external_processes[0].process_id, "out");
    const rule = state.config.external_processes[0];
    rule.process_id = "";
    state.bindProcess(rule, "external_processes");
    assert.equal(rule.process_id, null);
    await state.save();
    assert.equal(calls.length, 1);
    assert.ok(notices.some(value => value.includes("匹配条件")));
    state.wordInputs[rule.id] = "氧化";
    await state.save();
    assert.equal(calls.length, 2);
  } finally {
    stop();
  }
});
