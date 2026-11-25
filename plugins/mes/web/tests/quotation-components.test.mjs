// Run real SFC setup/watchers/actions with Vue's in-memory renderer. No browser,
// business database, file upload, network request or model call is involved.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const require = createRequire(
  new URL("../../../core/web/package.json", import.meta.url),
);
const { build } = require("esbuild");
const { parse, compileScript } = require("@vue/compiler-sfc");
const { createRenderer, h, reactive, nextTick } = require("vue");
const directory = fileURLToPath(
  new URL("../src/views/mes/quotations/", import.meta.url),
);
const output = await build({
  stdin: {
    contents: `export {default as Page} from ${JSON.stringify(path.join(directory, "QuotationPage.vue"))};export {default as Panel} from ${JSON.stringify(path.join(directory, "CncAdoptionPanel.vue"))};`,
    resolveDir: directory,
  },
  bundle: true,
  write: false,
  platform: "node",
  format: "cjs",
  external: ["vue"],
  plugins: [
    {
      name: "component-test",
      setup(builder) {
        const mocks = {
          "element-plus": `const record=t=>globalThis.__quotationFixture.messages.push(t);export const ElMessage=Object.assign(t=>globalThis.__quotationFixture.toasts.push(t),{error:record,success:record});export const ElMessageBox={confirm:async()=>{if(globalThis.__quotationFixture.cancel)throw 'cancel';},prompt:async()=>{if(globalThis.__quotationFixture.cancel)throw 'cancel';return {value:globalThis.__quotationFixture.promptValue ?? ''};}};`,
          "@pureadmin/utils": `export const isFunction=value=>typeof value==='function';`,
          "vue-router": `export const useRoute=()=>globalThis.__quotationFixture.route;export const useRouter=()=>({push:async()=>{},replace:async target=>globalThis.__quotationFixture.replacements.push(target)});`,
          "@/utils/http": `export const http={request:(...args)=>globalThis.__quotationFixture.request(...args)};`,
          "@/utils/auth": `export const getToken=()=>({userId:'test-user'});export const hasPerms=key=>globalThis.__quotationFixture.principal.permissions.includes(key);`,
          "@/store/modules/user": `export const useUserStoreHook=()=>globalThis.__quotationFixture.principal;`,
          "@/utils/todoRefresh": `export const notifyTodosChanged=()=>{};`,
          "cnc-api": `export const request=async()=>globalThis.__quotationFixture.cnc;`,
          "empty-component": `export default {};`,
        };
        builder.onResolve(
          {
            filter:
              /^(element-plus|vue-router|@pureadmin\/utils|@\/utils\/http|@\/utils\/auth|@\/utils\/todoRefresh|@\/store\/modules\/user)$/,
          },
          (args) => ({ path: args.path, namespace: "mock" }),
        );
        builder.onResolve({ filter: /^@\/utils\/message$/ }, () => ({
          path: fileURLToPath(new URL("../../../core/web/src/utils/message.ts", import.meta.url)),
        }));
        builder.onResolve({ filter: /quoting\/api$/ }, () => ({
          path: "cnc-api",
          namespace: "mock",
        }));
        builder.onResolve({ filter: /^@\/components\// }, () => ({
          path: "empty-component",
          namespace: "mock",
        }));
        builder.onLoad({ filter: /.*/, namespace: "mock" }, (args) => ({
          contents: mocks[args.path],
          loader: "ts",
        }));
        builder.onLoad({ filter: /\.vue$/ }, (args) => {
          if (
            !/\/(QuotationPage|CncAdoptionPanel)\.vue$/.test(
              args.path.replaceAll("\\", "/"),
            )
          )
            return { contents: "export default {};", loader: "ts" };
          const { descriptor } = parse(readFileSync(args.path, "utf8"), {
            filename: args.path,
          });
          return {
            contents: compileScript(descriptor, {
              id: "quotation-component-test",
            }).content,
            loader: "ts",
            resolveDir: path.dirname(args.path),
          };
        });
      },
    },
  ],
});
const module = { exports: {} };
new Function("require", "module", "exports", output.outputFiles[0].text)(
  require,
  module,
  module.exports,
);
const { Page, Panel } = module.exports;
Page.render = Panel.render = () => null;
const renderer = createRenderer({
  createElement: (tag) => ({ tag, children: [] }),
  createText: (text) => ({ text }),
  createComment: (text) => ({ text }),
  insert(node, parent) {
    parent.children.push(node);
  },
  remove() {},
  patchProp() {},
  setText(node, text) {
    node.text = text;
  },
  setElementText(node, text) {
    node.text = text;
  },
  parentNode: () => null,
  nextSibling: () => null,
});
const clone = (value) => JSON.parse(JSON.stringify(value));
async function flush() {
  for (let index = 0; index < 6; index++) {
    await Promise.resolve();
    await nextTick();
  }
}
const number = (index) => `PM-${String(index).padStart(4, "0")}`;

async function fixture(configure = () => {}) {
  const permissions = [
    "mes:quotation:list",
    "mes:quotation:price",
    "mes:quotation:manage",
    "mes:quote:list",
    "mes:quote:manage",
    "mes:quote:analyze",
  ];
  const f = {
    messages: [],
    toasts: [],
    replacements: [],
    calls: [],
    cancel: false,
    route: reactive({
      path: "/mes/quotations",
      fullPath: "/mes/quotations?quote_id=quote&mode=engineering",
      query: { quote_id: "quote", mode: "engineering" },
    }),
    principal: reactive({ username: "工程测试", permissions }),
    cnc: {
      version_no: 1,
      quote: { id: "snapshot", version_no: 1, approved_by: null },
      job: { status_code: "completed" },
    },
    server: {
      id: "quote",
      quote_no: "BJ-TEST",
      version_no: 1,
      revision: 1,
      title: "询价",
      status_code: "pending",
      currency: "EUR",
      lines: [],
      events: [],
    },
  };
  f.server.lines = Array.from({ length: 120 }, (_, index) => ({
    id: `line-${index + 1}`,
    drawing_no: number(index + 1),
    drawing_revision: "A",
    description: "零件",
    quantity: 10,
    unit_name: "件",
    customer_material: "6082",
    quoted_material: "",
    weight_kg: null,
    unit_price: index === 3 ? null : 20 + index / 100,
    lead_days: null,
    surface_treatment: "",
    engineering_note: "",
    note: "",
    files: [],
    cnc_records: [
      {
        id: `record-${index + 1}`,
        part_id: `part-${index + 1}`,
        created_at: "2026-11-05T06:00:00Z",
        status_code: index === 7 ? "failed" : "completed",
        stage: index === 7 ? "解析失败" : "解析完成",
        is_stale: false,
      },
    ],
  }));
  configure(f);
  f.request = async (method, url, options = {}) => {
    f.calls.push({ method, url, data: clone(options.data ?? null) });
    let data;
    if (url.endsWith("/adoption-preview")) {
      data = {
        items: options.data.line_ids.map((line_id) => ({
          line_id,
          can_adopt: line_id !== "line-2" && !f.blockAll,
          cnc_quote_id: `snapshot-${line_id}`,
          quoted_material: "AL6082",
          cnc_unit_price: "80.00",
          cnc_currency: "CNY",
          suggested_unit_price:
            f.server.currency === "CNY"
              ? "80.00"
              : options.data.exchange_rate
                ? (80 / options.data.exchange_rate).toFixed(2)
                : null,
          price_message: "请填写汇率后自动回填",
          message:
            line_id === "line-2" || f.blockAll ? "核价依据已更新" : "可采用",
        })),
      };
    } else if (url.includes("/exchange-rate?")) {
      if (f.rateWait) await f.rateWait;
      if (!f.autoRate) throw new Error("参考汇率暂不可用，请人工填写");
      data = f.autoRate;
    } else if (url.endsWith("/engineering")) {
      for (const line of options.data.lines)
        Object.assign(
          f.server.lines.find((row) => row.id === line.id),
          line,
        );
      f.server.version_no++;
      f.server.status_code = "pricing";
      data = f.server;
    } else if (url.endsWith("/adopt-batch")) {
      assert.equal(options.data.version_no, f.server.version_no);
      const items = options.data.lines.map((line) => {
        const is_success = line.line_id !== "line-6";
        if (is_success)
          Object.assign(
            f.server.lines.find((row) => row.id === line.line_id),
            {
              quoted_material: "AL6082",
              adopted_cnc_quote_id: line.cnc_quote_id,
              unit_price: Number(
                (
                  80 /
                  (f.server.currency === "CNY" ? 1 : options.data.exchange_rate)
                ).toFixed(2),
              ),
            },
          );
        return {
          line_id: line.line_id,
          is_success,
          code: is_success ? 0 : 409,
          message: is_success ? "已采用核价" : "核价快照已变化，请重新确认",
        };
      });
      f.server.version_no++;
      data = { quotation: f.server, items };
    } else if (url.endsWith("/adopt")) {
      const line = f.server.lines.find((row) =>
        url.includes(`/lines/${row.id}/`),
      );
      line.adopted_cnc_quote_id = options.data.cnc_quote_id;
      f.server.version_no++;
      data = f.server;
    } else if (method === "post" && url.endsWith("/approve")) {
      for (const supplied of options.data.lines) {
        const line = f.server.lines.find((row) => row.id === supplied.id);
        line.unit_price = supplied.unit_price;
        line.lead_days = supplied.lead_days;
        for (const tier of supplied.quantity_tiers) {
          line.quantity_tiers.find((row) => row.id === tier.id).unit_price =
            tier.unit_price;
        }
      }
      f.server.version_no++;
      f.server.status_code = "final_review";
      data = f.server;
    } else if (method === "post" && url.endsWith("/actions/final_approve")) {
      assert.equal(f.server.status_code, "final_review");
      assert.equal(options.data.version_no, f.server.version_no);
      f.server.version_no++;
      f.server.status_code = "quoted";
      data = f.server;
    } else if (method === "post" && url.endsWith("/actions/void")) {
      assert.equal(options.data.version_no, f.server.version_no);
      f.server.version_no++;
      f.server.status_code = "voided";
      data = f.server;
    } else if (method === "delete" && url === `/api/mes/quotations/quote?version_no=${f.server.version_no}`) {
      data = { id: f.server.id };
    } else if (method === "get" && url.endsWith("/quote")) data = f.server;
    else throw Error(`unexpected request ${method} ${url}`);
    return { code: 0, data: clone(data) };
  };
  globalThis.__quotationFixture = f;
  globalThis.document = {
    body: {},
    visibilityState: "visible",
    addEventListener() {},
    removeEventListener() {},
  };
  const app = renderer.createApp(Page);
  const page = app.mount({ children: [] }).$.setupState;
  await flush();
  const wrapper = {
    render: () =>
      h(Panel, {
        quote: page.draft,
        editable: page.price,
        disabled: page.busy || page.importBusy,
        progressMessage: page.progressMessage,
        persist: page.persistForAdoption,
        onUpdate: (quote) => {
          page.draft = quote;
        },
        onBusy: (value) => {
          page.adoptionBusy = value;
        },
      }),
  };
  const panelApp = renderer.createApp(wrapper);
  const panelRoot = panelApp.mount({ children: [] });
  const panel = panelRoot.$.subTree.component.setupState;
  function selectionStub(state, field, idsOnly) {
    const selected = new Map();
    return {
      clearSelection() {
        selected.clear();
        state[field] = [];
      },
      toggleRowSelection(row, checked) {
        if (checked) selected.set(row.id, row);
        else selected.delete(row.id);
        state[field] = idsOnly ? [...selected.keys()] : [...selected.values()];
      },
    };
  }
  page.detailTable = selectionStub(page, "selected", false);
  panel.table = selectionStub(panel, "selectedIds", true);
  return {
    ...f,
    page,
    panel,
    cleanup() {
      panelApp.unmount();
      app.unmount();
      delete globalThis.document;
      delete globalThis.__quotationFixture;
    },
  };
}

test("engineering page automatically fills matching blank historical prices and preserves existing prices", async () => {
  const reference = {
    quote_no: "BJ-HISTORY",
    revision: 1,
    quoted_at: "2026-10-01",
    currency: "EUR",
    unit_price: "12.80",
    quantity: "10",
    quoted_material: "AL6082",
    weight_kg: "0.5",
    drawing_revision: "A",
    is_compatible: true,
    unit_name: "件",
  };
  const f = await fixture((state) => {
    state.server.lines[0].historical_reference = reference;
    state.server.lines[3].historical_reference = reference;
  });
  const page = f.page;
  try {
    assert.equal(page.draft.lines[0].unit_price, 20);
    assert.equal(page.draft.lines[3].unit_price, 12.8);
    assert.match(page.draft.lines[3].engineering_note, /BJ-HISTORY/);
    assert.equal(f.server.lines[3].unit_price, null);
  } finally {
    f.cleanup();
  }
});

test("real page searches and pages 120 goods without losing edits or full-form scope", async () => {
  const f = await fixture();
  try {
    const p = f.page;
    assert.equal(p.visibleLines.length, 20);
    p.lineKeyword = " pm-0096 ";
    await flush();
    assert.equal(p.visibleLines.length, 1);
    p.visibleLines[0].unit_price = 88.88;
    p.lineKeyword = "";
    await flush();
    p.linePage = 5;
    await flush();
    assert.equal(p.visibleLines[15].unit_price, 88.88);
    p.selectAllDetail();
    assert.equal(p.selected.length, 120);
    p.lineKeyword = "PM-009";
    await flush();
    p.selectAllDetail();
    assert.equal(p.selected.length, 10);
    assert.equal(p.draft.lines.length, 120);
    assert.equal(f.calls.length, 1);
  } finally {
    f.cleanup();
  }
});

test("real panel selects every matching page and keeps stable selected ids", async () => {
  const f = await fixture();
  try {
    const p = f.panel;
    p.keyword = "pm-00";
    await flush();
    assert.equal(p.filtered.length, 99);
    p.selectAll();
    await flush();
    assert.equal(p.selectedIds.length, 98);
    p.page = 2;
    await flush();
    assert.equal(p.visible[0].drawing_no, "PM-0021");
    assert.equal(p.selectedIds.length, 98);
    p.keyword = "PM-0096";
    await flush();
    p.selectAll();
    await flush();
    assert.deepEqual([...p.selectedIds], ["line-96"]);
    p.reset();
    await flush();
    p.selectAll();
    await flush();
    assert.equal(p.selectedIds.length, 119);
  } finally {
    f.cleanup();
  }
});

test("business search removes the selected goods and adding a row reveals the last page", async () => {
  const f = await fixture();
  try {
    const p = f.page;
    p.mode = "sales";
    p.draft.status_code = "draft";
    p.lineKeyword = "PM-0096";
    await flush();
    p.removeGoods(p.visibleLines[0]);
    await flush();
    assert.equal(p.draft.lines.length, 119);
    assert.equal(
      p.draft.lines.some((line) => line.id === "line-96"),
      false,
    );
    assert.equal(p.draft.lines[0].id, "line-1");
    p.removeGoods({ id: "unknown" });
    assert.equal(p.draft.lines.length, 119);
    await p.addGoods();
    await p.addGoods();
    await flush();
    assert.equal(p.lineKeyword, "");
    assert.equal(p.linePage, 7);
    assert.equal(p.visibleLines.at(-1).drawing_no, "");
    assert.notEqual(
      p.detailRowKey(p.draft.lines.at(-1)),
      p.detailRowKey(p.draft.lines.at(-2)),
    );
  } finally {
    f.cleanup();
  }
});

test("real batch adoption updates existing prices and preserves only failed selections", async () => {
  const f = await fixture();
  try {
    const p = f.panel;
    f.page.draft.lines[95].unit_price = 88.88;
    p.selectAll();
    await flush();
    await p.preview();
    await flush();
    assert.equal(p.dialog, true);
    assert.equal(p.reviewRows.length, 119);
    assert.equal(p.ready.length, 0);
    p.exchangeRate = 8;
    await p.preview(p.targetIds);
    await flush();
    assert.equal(p.ready.length, 118);
    assert.equal(
      p.reviewRows.find((row) => row.line_id === "line-2").message,
      "核价依据已更新",
    );
    await p.submit();
    assert.equal(
      f.calls.filter((call) => call.url.endsWith("/engineering")).length,
      0,
    );
    p.confirmed = true;
    await p.submit();
    await flush();
    assert.equal(p.submitted, true);
    assert.equal(p.successCount, 117);
    assert.equal(p.selectedIds.length, 2);
    assert.equal(p.dialog, true);
    assert.equal(
      p.reviewRows.filter((row) => row.state === "failed").length,
      1,
    );
    assert.equal(
      f.calls.filter((call) => call.url.endsWith("/engineering")).length,
      1,
    );
    assert.equal(
      f.calls.filter((call) => call.url.endsWith("/adopt-batch")).length,
      1,
    );
    assert.equal(
      f.calls.find((call) => call.url.endsWith("/engineering")).data.lines
        .length,
      120,
    );
    const body = f.calls.find((call) => call.url.endsWith("/adopt-batch")).data;
    assert.equal(body.lines.length, 118);
    assert.deepEqual(Object.keys(body.lines[0]).sort(), [
      "cnc_quote_id",
      "line_id",
    ]);
    assert.equal(f.page.draft.lines[95].unit_price, 10);
    assert.equal(
      f.page.draft.lines.filter((row) => row.adopted_cnc_quote_id).length,
      117,
    );
    await p.submit();
    assert.equal(
      f.calls.filter((call) => call.url.endsWith("/adopt-batch")).length,
      1,
    );
  } finally {
    f.cleanup();
  }
});

test("no eligible records means no engineering save or adoption write", async () => {
  const f = await fixture();
  try {
    globalThis.__quotationFixture.blockAll = true;
    f.panel.selectAll();
    await flush();
    await f.panel.preview();
    f.panel.confirmed = true;
    await f.panel.submit();
    assert.equal(f.panel.ready.length, 0);
    assert.equal(
      f.calls.filter(
        (call) =>
          call.url.endsWith("/engineering") ||
          call.url.endsWith("/adopt-batch"),
      ).length,
      0,
    );
  } finally {
    f.cleanup();
  }
});

test("individual adoption fills blank price and closes the dialog on success", async () => {
  const f = await fixture();
  try {
    const p = f.panel;
    await p.preview(["line-4"]);
    await flush();
    assert.equal(p.reviewRows.length, 1);
    assert.equal(p.ready.length, 0);
    assert.equal(p.needsRate, true);
    p.exchangeRate = 8;
    p.confirmed = true;
    await p.submit();
    assert.equal(
      f.calls.filter((call) => call.url.endsWith("/engineering")).length,
      0,
    );
    await p.preview(p.targetIds);
    await flush();
    assert.equal(p.ready.length, 1);
    assert.equal(p.ready[0].unit_price, 10);
    p.confirmed = true;
    await p.submit();
    await flush();
    assert.equal(f.page.draft.lines[3].unit_price, 10);
    assert.equal(f.page.draft.status_code, "pricing");
    assert.equal(p.submitted, true);
    assert.equal(p.dialog, false);
    assert.equal(p.exchangeRate, 8);
    assert.equal(
      Object.hasOwn(
        f.calls.find((call) => call.url.endsWith("/adopt-batch")).data.lines[0],
        "final_unit_price",
      ),
      false,
    );
  } finally {
    f.cleanup();
  }
});

test("same-currency AI price fills automatically without a rate or manual price", async () => {
  const f = await fixture();
  try {
    f.server.currency = f.page.draft.currency = "CNY";
    await flush();
    const p = f.panel;
    await p.preview(["line-4"]);
    await flush();
    assert.equal(p.needsRate, false);
    assert.equal(p.ready.length, 1);
    assert.equal(p.ready[0].unit_price, 80);
    p.confirmed = true;
    await p.submit();
    await flush();
    assert.equal(f.page.draft.lines[3].unit_price, 80);
  } finally {
    f.cleanup();
  }
});

test("one rate fills an entire batch of blank prices and invalidates stale previews", async () => {
  const f = await fixture();
  try {
    for (const row of f.page.draft.lines) row.unit_price = null;
    const p = f.panel;
    p.selectAll();
    await flush();
    await p.preview();
    await flush();
    assert.equal(p.ready.length, 0);
    assert.equal(p.needsRate, true);
    p.exchangeRate = 8;
    await p.preview(p.targetIds);
    await flush();
    assert.equal(p.ready.length, 118);
    p.exchangeRate = 10;
    p.confirmed = true;
    await p.submit();
    assert.equal(p.ready.length, 0);
    assert.equal(
      f.calls.filter((call) => call.url.endsWith("/engineering")).length,
      0,
    );
    p.exchangeRate = 8;
    p.confirmed = true;
    await p.submit();
    await flush();
    assert.equal(p.successCount, 117);
    assert.equal(p.selectedIds.length, 2);
    assert.equal(
      f.page.draft.lines.filter((row) => row.unit_price === 10).length,
      117,
    );
    const body = f.calls.find((call) => call.url.endsWith("/adopt-batch")).data;
    assert.equal(body.exchange_rate, 8);
    assert.equal(body.lines.length, 118);
    assert.equal(
      body.lines.every((row) => !Object.hasOwn(row, "final_unit_price")),
      true,
    );
  } finally {
    f.cleanup();
  }
});

test("default AI adoption replaces an existing 12.00 price rather than preserving it", async () => {
  const f = await fixture();
  try {
    f.page.draft.lines[0].unit_price = 12;
    const p = f.panel;
    await p.preview(["line-1"]);
    await flush();
    assert.equal(p.ready.length, 0);
    assert.equal(p.needsRate, true);
    p.exchangeRate = 8;
    await p.preview(p.targetIds);
    await flush();
    assert.equal(p.ready[0].original_unit_price, 12);
    assert.equal(p.ready[0].unit_price, 10);
    p.confirmed = true;
    await p.submit();
    await flush();
    const body = f.calls.find((call) => call.url.endsWith("/adopt-batch")).data;
    assert.deepEqual(Object.keys(body.lines[0]).sort(), [
      "cnc_quote_id",
      "line_id",
    ]);
    assert.equal(f.page.draft.lines[0].unit_price, 10);
    assert.equal(p.reviewRows[0].original_unit_price, 12);
  } finally {
    f.cleanup();
  }
});

test("engineer can manually adjust the customer price after adopting AI quote", async () => {
  const f = await fixture();
  try {
    const p = f.panel;
    await p.preview(["line-1"]);
    p.exchangeRate = 8;
    await p.preview(p.targetIds);
    p.confirmed = true;
    await p.submit();
    await flush();
    assert.equal(f.page.draft.lines[0].unit_price, 10);
    f.page.draft.lines[0].unit_price = 19.99;
    await f.page.savePrice(false);
    await flush();
    assert.equal(f.page.draft.lines[0].unit_price, 19.99);
    assert.equal(f.page.draft.status_code, "pricing");
  } finally {
    f.cleanup();
  }
});

const referenceRate = (rate = "8.00000000") => ({
  base: "EUR",
  quote: "CNY",
  rate,
  rate_date: "2026-11-05",
  provider: "Frankfurter / ECB",
  fetched_at: "2026-11-06T01:00:00Z",
  reference: "signed-public-reference",
});

test("reference rate fills the adoption preview automatically and travels with the confirmed value", async () => {
  const f = await fixture();
  try {
    globalThis.__quotationFixture.autoRate = referenceRate();
    const p = f.panel;
    await p.preview(["line-1", "line-4"]);
    assert.equal(p.exchangeRate, 8);
    assert.equal(p.rateReference.provider, "Frankfurter / ECB");
    assert.equal(p.rateReference.rate_date, "2026-11-05");
    assert.equal(p.ready.length, 2);
    assert.equal(p.ready[0].unit_price, 10);
    assert.equal(p.confirmed, false);
    p.confirmed = true;
    await p.submit();
    const body = f.calls.find((call) => call.url.endsWith("/adopt-batch")).data;
    assert.equal(body.exchange_rate, 8);
    assert.equal(body.exchange_rate_reference, "signed-public-reference");
    assert.equal(f.page.draft.lines[0].unit_price, 10);
    assert.equal(
      f.calls.filter((call) => call.url.includes("/exchange-rate?")).length,
      1,
    );
  } finally {
    f.cleanup();
  }
});

test("manual rate overrides a reference without a new lookup and requires a fresh preview", async () => {
  const f = await fixture();
  try {
    globalThis.__quotationFixture.autoRate = referenceRate();
    const p = f.panel;
    await p.preview(["line-1"]);
    p.exchangeRate = 10;
    p.confirmed = true;
    await p.submit();
    assert.equal(p.ready.length, 0);
    await p.preview(p.targetIds);
    assert.equal(p.ready[0].unit_price, 8);
    assert.equal(p.confirmed, false);
    assert.equal(
      f.calls.filter((call) => call.url.includes("/exchange-rate?")).length,
      1,
    );
    p.confirmed = true;
    await p.submit();
    assert.equal(
      f.calls.find((call) => call.url.endsWith("/adopt-batch")).data
        .exchange_rate,
      10,
    );
    assert.equal(f.page.draft.lines[0].unit_price, 8);
  } finally {
    f.cleanup();
  }
});

test("lookup failure leaves no invented rate and explicit retry can recover", async () => {
  const f = await fixture();
  try {
    const p = f.panel;
    await p.preview(["line-1"]);
    assert.equal(p.exchangeRate, null);
    assert.match(f.toasts.at(-1).message, /人工填写/);
    assert.equal(p.ready.length, 0);
    globalThis.__quotationFixture.autoRate = referenceRate();
    await p.preview(p.targetIds, true);
    assert.equal(p.exchangeRate, 8);
    assert.equal(f.toasts.length, 1);
    p.exchangeRate = 10;
    globalThis.__quotationFixture.autoRate = null;
    await p.preview(p.targetIds, true);
    assert.equal(p.exchangeRate, 10);
    assert.equal(p.ready[0].unit_price, 8);
    assert.match(f.toasts.at(-1).message, /人工填写/);
  } finally {
    f.cleanup();
  }
});

test("same currency does not query exchange rates", async () => {
  const f = await fixture();
  try {
    f.server.currency = f.page.draft.currency = "CNY";
    await flush();
    await f.panel.preview(["line-1"]);
    assert.equal(
      f.calls.filter((call) => call.url.includes("/exchange-rate?")).length,
      0,
    );
    assert.equal(f.panel.ready[0].unit_price, 80);
  } finally {
    f.cleanup();
  }
});

test("a late reference response cannot populate a different quotation currency", async () => {
  const f = await fixture();
  let release;
  try {
    const state = globalThis.__quotationFixture;
    state.autoRate = referenceRate();
    state.rateWait = new Promise((resolve) => {
      release = resolve;
    });
    const pending = f.panel.preview(["line-1"]);
    await flush();
    f.page.draft.currency = "USD";
    await flush();
    release();
    await pending;
    assert.equal(f.panel.exchangeRate, null);
    assert.equal(f.panel.rateReference, null);
    assert.equal(f.panel.dialog, false);
  } finally {
    release?.();
    f.cleanup();
  }
});

test("successful batch adoption closes the dialog after updating prices", async () => {
  const f = await fixture();
  try {
    f.server.currency = f.page.draft.currency = "CNY";
    await flush();
    const p = f.panel;
    await p.preview([
      "line-1",
      "line-3",
      "line-4",
      "line-5",
      "line-7",
      "line-9",
    ]);
    await flush();
    assert.equal(p.ready.length, 6);
    assert.equal(p.dialog, true);
    p.confirmed = true;
    await p.submit();
    await flush();
    assert.equal(p.successCount, 6);
    assert.equal(p.dialog, false);
    assert.equal(
      f.page.draft.lines.filter((row) => row.adopted_cnc_quote_id).length,
      6,
    );
    assert.match(f.messages.at(-1), /已采用 6 项/);
  } finally {
    f.cleanup();
  }
});

test("failed adoption keeps the dialog and error available for retry", async () => {
  const f = await fixture();
  try {
    f.server.currency = f.page.draft.currency = "CNY";
    await flush();
    const p = f.panel;
    await p.preview(["line-1"]);
    await flush();
    const state = globalThis.__quotationFixture,
      original = state.request;
    state.request = async (method, url, options) => {
      if (url.endsWith("/adopt-batch")) throw new Error("采用失败，请稍后重试");
      return original(method, url, options);
    };
    p.confirmed = true;
    await p.submit();
    await flush();
    assert.equal(p.dialog, true);
    assert.equal(p.submitted, false);
    assert.match(f.toasts.at(-1).message, /采用失败/);
    assert.equal(p.working, false);
  } finally {
    f.cleanup();
  }
});

test("deletes the selected draft only after confirmation", async () => {
  const f = await fixture(state => {
    state.route.query.mode = "view";
    state.server.status_code = "draft";
  });
  try {
    assert.equal(f.page.canDelete(f.page.draft), true);
    assert.equal(f.page.canDelete({ ...f.page.draft, status_code: "quoted" }), false);
    globalThis.__quotationFixture.cancel = true;
    await f.page.run(() => f.page.deleteQuote(f.page.draft));
    assert.equal(f.calls.filter(call => call.method === "delete").length, 0);
    globalThis.__quotationFixture.cancel = false;
    await f.page.run(() => f.page.deleteQuote(f.page.draft));
    const removal = f.calls.find(call => call.method === "delete");
    assert.equal(removal.url, "/api/mes/quotations/quote?version_no=1");
    assert.deepEqual(f.replacements, ["/mes/quotations"]);
    assert.match(f.toasts.at(-1).message, /已删除/);
  } finally {
    f.cleanup();
  }
});

test("voids an approved quotation without orders and displays its saved status", async () => {
  const f = await fixture(state => {
    state.route.query.mode = "view";
    state.server.status_code = "quoted";
    state.server.customer_order_count = 0;
    state.promptValue = "  客户取消询价  ";
  });
  try {
    const quote = f.page.draft;
    assert.equal(f.page.canVoid(quote), true);
    assert.equal(f.page.canVoid({ ...quote, customer_order_count: 1 }), false);
    assert.equal(f.page.canVoid({ ...quote, status_code: "draft" }), false);
    globalThis.__quotationFixture.cancel = true;
    await f.page.run(() => f.page.voidQuote(quote));
    assert.equal(f.calls.some(call => call.url.endsWith("/actions/void")), false);
    globalThis.__quotationFixture.cancel = false;
    await f.page.run(() => f.page.voidQuote(quote));
    const action = f.calls.find(call => call.url.endsWith("/actions/void"));
    assert.deepEqual(action.data, { version_no: 1, note: "客户取消询价" });
    assert.equal(f.page.draft.status_code, "voided");
    assert.equal(f.page.canVoid(f.page.draft), false);
  } finally {
    f.cleanup();
  }
});

test("approval validation displays a temporary viewport toast without setting the inline error", async () => {
  const f = await fixture(state => {
    state.principal.permissions = ["mes:quotation:list", "mes:quotation:approve"];
    state.route.query.mode = "review";
    state.server.status_code = "review";
    state.server.lines.forEach(line => Object.assign(line, {
      unit_price: 20, quoted_material: "AL6082", lead_days: 14,
    }));
    state.server.lines.at(-1).lead_days = null;
  });
  try {
    await f.page.run(() => f.page.action("approve"));
    const [toast] = f.toasts;
    assert.match(toast.message, /请填写最终交期/);
    assert.equal(toast.placement, "top");
    assert.equal(toast.appendTo, document.body);
    assert.equal(toast.duration, 5000);
    assert.equal(f.page.error, "");
    assert.equal(f.server.status_code, "review");
  } finally {
    f.cleanup();
  }
});

test("reviewer edits main and tier prices across pages, requires a reason and approves atomically", async () => {
  const f = await fixture((state) => {
    state.principal.permissions = [
      "mes:quotation:list",
      "mes:quotation:approve",
    ];
    state.route.query.mode = "review";
    state.server.status_code = "review";
    state.server.lines.forEach((line) =>
      Object.assign(line, {
        unit_price: 20,
        quoted_material: "AL6082",
        lead_days: 14,
      }),
    );
    state.server.lines[0].quantity_tiers = [
      {
        id: "tier-1",
        quantity: 100,
        unit_price: 10,
        calculation_note: "工程依据",
      },
    ];
  });
  try {
    assert.equal(f.page.review, true);
    assert.equal(f.page.price, false);
    f.page.draft.lines[0].unit_price = 25;
    f.page.draft.lines[0].quantity_tiers[0].unit_price = 12;
    f.page.draft.lines[119].unit_price = 30;
    assert.equal(f.page.reviewOriginal.lines[0].unit_price, 20);
    assert.equal(
      f.page.reviewOriginal.lines[0].quantity_tiers[0].unit_price,
      10,
    );
    assert.equal(f.page.reviewPriceChanged, true);
    await assert.rejects(() => f.page.action("approve"), /改价说明/);
    assert.equal(
      f.calls.filter((call) => call.url.endsWith("/approve")).length,
      0,
    );
    f.page.priceAdjustmentReason = "  客户定价调整  ";
    await f.page.action("approve");
    await flush();
    const payload = f.calls.find((call) => call.url.endsWith("/approve")).data;
    assert.equal(payload.price_adjustment_reason, "客户定价调整");
    assert.equal(payload.lines.length, 120);
    assert.equal(payload.lines[0].unit_price, 25);
    assert.deepEqual(payload.lines[0].quantity_tiers, [
      { id: "tier-1", unit_price: 12 },
    ]);
    assert.equal(payload.lines[119].unit_price, 30);
    assert.equal(payload.lines[0].lead_days, 14);
    assert.equal(f.page.draft.status_code, "final_review");
    assert.equal(f.page.review, false);
    f.page.mode = "final_review";
    assert.equal(f.page.finalReview, true);
    const beforeFinalReview = clone(f.page.draft.lines);
    await f.page.action("final_approve");
    assert.equal(f.page.draft.status_code, "quoted");
    assert.equal(f.page.finalReview, false);
    assert.deepEqual(clone(f.page.draft.lines), beforeFinalReview);
    assert.equal(
      f.server.lines[0].quantity_tiers[0].calculation_note,
      "工程依据",
    );
  } finally {
    f.cleanup();
  }
});
