// Actual Vue SFC setup/actions in memory; all HTTP and dialogs are controlled substitutes.
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
const { createRenderer, reactive, nextTick } = require("vue");
const directory = fileURLToPath(new URL("../src/views/mes/", import.meta.url));
const bundle = await build({
  stdin: {
    contents: `export {default as Order} from './sales-orders/OrderPage.vue';export {default as History} from './quotations/HistoricalPrices.vue';export {default as Edit} from './sales-orders/CustomerOrderEdit.vue';export {default as Tiers} from './quotations/QuantityTiers.vue';`,
    resolveDir: directory,
  },
  bundle: true,
  write: false,
  platform: "node",
  format: "cjs",
  external: ["vue"],
  plugins: [
    {
      name: "order-fixture",
      setup(builder) {
        const mocks = {
          "vue-router": `export const useRoute=()=>globalThis.__orderFixture.route;export const useRouter=()=>globalThis.__orderFixture.router;`,
          "element-plus": `export const ElMessage={success:t=>globalThis.__orderFixture.messages.push(t),warning:t=>globalThis.__orderFixture.messages.push(t)};export const ElMessageBox={confirm:async()=>{if(globalThis.__orderFixture.cancel)throw 'cancel';},prompt:async()=>({value:'取消测试'})};`,
          "@/utils/http": `export const http={request:(...args)=>globalThis.__orderFixture.request(...args)};`,
          "@/utils/message": `export const actionMessage=text=>globalThis.__orderFixture.messages.push(text);`,
          "@/utils/auth": `export const getToken=()=>({userId:'user'});export const hasPerms=()=>true;`,
          "@plugins/mes/web/src/api/mes": `export const getMesProductOptions=async()=>[];`,
        };
        builder.onResolve({ filter: /.*/ }, (args) => {
          if (mocks[args.path]) return { path: args.path, namespace: "mock" };
          if (args.path.startsWith("@/components/"))
            return { path: "empty", namespace: "mock" };
        });
        builder.onLoad({ filter: /.*/, namespace: "mock" }, (args) => ({
          contents: mocks[args.path] || "export default {};",
          loader: "ts",
        }));
        builder.onLoad({ filter: /\.vue$/ }, (args) => {
          if (
            !/(OrderPage|HistoricalPrices|CustomerOrderEdit|QuantityTiers)\.vue$/.test(
              args.path,
            )
          )
            return { contents: "export default {};", loader: "ts" };
          const { descriptor } = parse(readFileSync(args.path, "utf8"));
          return {
            contents: compileScript(descriptor, { id: "order-flow" }).content,
            loader: "ts",
            resolveDir: path.dirname(args.path),
          };
        });
      },
    },
  ],
});
const module = { exports: {} };
new Function("require", "module", "exports", bundle.outputFiles[0].text)(
  require,
  module,
  module.exports,
);
const { Order, History, Edit, Tiers } = module.exports;
Order.render = History.render = Edit.render = Tiers.render = () => null;
const renderer = createRenderer({
  createElement: () => ({ children: [] }),
  createText: (text) => ({ text }),
  createComment: (text) => ({ text }),
  insert: (node, parent) => parent.children.push(node),
  remove() {},
  patchProp() {},
  setText() {},
  setElementText() {},
  parentNode: () => null,
  nextSibling: () => null,
});
async function flush() {
  for (let i = 0; i < 12; i++) {
    await Promise.resolve();
    await nextTick();
  }
}
function source(index) {
  return {
    id: `line-${index}`,
    quotation_id: "quote",
    quotation_version_no: 7,
    quote_no: "BJ-1",
    revision: 1,
    org_id: "org",
    customer_id: "customer",
    customer_name_snapshot: "客户A",
    currency: "EUR",
    drawing_no: `P-${index}`,
    drawing_revision: "A",
    description: "零件",
    material: "6082",
    quantity: "10",
    unit_price: "12.80",
    unit_name: "件",
    lead_days: 14,
    quantity_tiers: [
      { id: `tier-${index}`, quantity: "50", unit_price: "8.00" },
    ],
  };
}
async function fixture(component = Order, props = {}, options = {}) {
  const f = (globalThis.__orderFixture = {
    route: reactive({
      path: "/mes/sales-orders",
      fullPath: "/mes/sales-orders?new=1&quote_id=quote",
      query: options.query || { new: "1", quote_id: "quote" },
    }),
    sources:
      options.sources || Array.from({ length: 120 }, (_, i) => source(i + 1)),
    calls: [],
    paths: [],
    messages: [],
    cancel: false,
    orders: {},
    failPost: false,
  });
  f.router = {
    push: async (target) => {
      f.paths.push(target);
    },
    replace: async (target) => {
      f.paths.push(target);
      f.route.path = target.path;
      f.route.query = target.query || {};
      f.route.fullPath =
        target.path + "?" + new URLSearchParams(target.query || {});
    },
  };
  f.request = async (method, url, options = {}) => {
    f.calls.push({ method, url, ...structuredClone(options) });
    if (url.includes("historical-prices"))
      return {
        code: 0,
        data: { items: f.history || [], total: f.history?.length || 0 },
      };
    if (url.endsWith("/production-defaults"))
      return {
        code: 0,
        data: f.defaults || { lines: [], unit_names: { piece: "件" } },
      };
    if (url.endsWith("/source-customers")) {
      const keyword = (options.params?.keyword || "").toLowerCase();
      return {
        code: 0,
        data: [
          ...new Map(
            f.sources.map((row) => [
              row.customer_id,
              { id: row.customer_id, name: row.customer_name_snapshot },
            ]),
          ).values(),
        ].filter((row) => row.name.toLowerCase().includes(keyword)),
      };
    }
    if (url.endsWith("/sources")) {
      const {
        page = 1,
        page_size = 20,
        customer_id,
        quotation_id,
        keyword = "",
      } = options.params || {};
      const rows = f.sources.filter(
        (row) =>
          (!customer_id || row.customer_id === customer_id) &&
          (!quotation_id || row.quotation_id === quotation_id) &&
          (!keyword ||
            row.drawing_no.includes(keyword) ||
            row.quote_no.includes(keyword)),
      );
      if (f.sourceWait) await f.sourceWait(options.params);
      return {
        code: 0,
        data: {
          items: rows.slice((page - 1) * page_size, page * page_size),
          total: rows.length,
        },
      };
    }
    if (method === "put")
      return {
        code: 0,
        data: { ...f.currentOrder, ...options.data, id: "order" },
      };
    if (method === "post") {
      if (f.failPost) throw Error("暂时失败");
      if (url.endsWith("/approve")) {
        f.currentOrder = {
          ...f.currentOrder,
          status_code: "approved",
          version_no: options.data.version_no + 1,
        };
        return { code: 0, data: f.currentOrder };
      }
      if (url.endsWith("/release"))
        return {
          code: 0,
          data: {
            ...f.currentOrder,
            remaining_count: 0,
            productions: [
              {
                id: "batch",
                production_order_id: "project",
                production_order_no: "PO-1",
                lines: options.data.lines,
              },
            ],
          },
        };
      const order = {
        id: "order",
        order_no: "SO-1",
        version_no: 1,
        currency: "EUR",
        status_code: "confirmed",
        lines: options.data.lines,
        productions: [],
      };
      f.orders.order = order;
      return { code: 0, data: order };
    }
    return {
      code: 0,
      data: f.orders[url.split("/").at(-1)] || { items: [], total: 0 },
    };
  };
  const app = renderer.createApp(component, props),
    vm = app.mount({ children: [] });
  await flush();
  return { f, state: vm.$.setupState, stop: () => app.unmount() };
}

test("header selects and clears only its page while preserving cross-page choices and edits", async () => {
  const { f, state, stop } = await fixture();
  try {
    state.choose(state.sources[0], true);
    state.choices["line-1"].quantity = 3;
    assert.equal(state.pageSelectedCount, 1);
    state.choosePage(true);
    assert.equal(state.pageSelectedCount, 20);
    state.sourcePage = 2;
    await state.loadSources();
    assert.equal(state.pageSelectedCount, 0);
    state.choosePage(true);
    assert.equal(state.selected.length, 40);
    state.choosePage(false);
    assert.equal(state.selected.length, 20);
    assert.equal(state.pageSelectedCount, 0);
    state.choosePage(true);
    for (let page = 3; page <= 6; page++) {
      state.sourcePage = page;
      await state.loadSources();
      state.choosePage(true);
    }
    assert.equal(state.selected.length, 120);
    assert.equal(state.choices["line-1"].quantity, 3);
    assert.equal(
      f.calls.filter((c) => c.url.endsWith("/sources") && c.params.customer_id)
        .length,
      6,
    );
  } finally {
    stop();
  }
});

test("new order requires a customer before querying or selecting quotation goods", async () => {
  const { f, state, stop } = await fixture(Order, {}, { query: { new: "1" } });
  try {
    assert.equal(state.sourceCustomer, null);
    assert.equal(state.sources.length, 0);
    assert.equal(
      f.calls.some((call) => call.url.endsWith("/sources")),
      false,
    );
    await state.loadSources();
    state.choose(f.sources[0], true);
    assert.equal(state.selected.length, 0);
    await assert.rejects(state.confirmOrder(), /先选择客户/);
    await state.changeCustomer("customer");
    assert.equal(state.sourceCustomer.id, "customer");
    assert.equal(state.sources.length, 20);
    assert.equal(
      f.calls.filter((call) => call.url.endsWith("/sources")).at(-1).params
        .customer_id,
      "customer",
    );
  } finally {
    stop();
  }
});

test("quotation entry preselects its customer and lists goods from all that customer's quotations", async () => {
  const rows = [
    source(1),
    { ...source(2), quotation_id: "second-quote", quote_no: "BJ-2" },
    {
      ...source(3),
      quotation_id: "other-quote",
      customer_id: "other",
      customer_name_snapshot: "客户B",
    },
  ];
  const { f, state, stop } = await fixture(Order, {}, { sources: rows });
  try {
    assert.equal(state.sourceCustomer.id, "customer");
    assert.equal(state.sources.length, 2);
    assert.deepEqual(
      state.sources.map((row) => row.quotation_id),
      ["quote", "second-quote"],
    );
    const query = f.calls
      .filter((call) => call.url.endsWith("/sources"))
      .at(-1).params;
    assert.equal(query.customer_id, "customer");
    assert.equal(query.quotation_id, undefined);
    state.choosePage(true);
    assert.equal(state.selected.length, 2);
    state.sourceKeyword = "BJ-2";
    await state.loadSources();
    assert.equal(state.sources.length, 1);
    assert.equal(state.selected.length, 2);
  } finally {
    stop();
  }
});

test("switching customer confirms clearing choices and cancellation preserves entered deal values", async () => {
  const rows = [
    source(1),
    {
      ...source(2),
      customer_id: "other",
      customer_name_snapshot: "客户B",
      quotation_id: "other-quote",
    },
  ];
  const { f, state, stop } = await fixture(Order, {}, { sources: rows });
  try {
    state.choose(state.sources[0], true);
    state.selected[0].quantity = 3;
    const key = state.requestKey;
    f.cancel = true;
    await state.changeCustomer("other");
    assert.equal(state.sourceCustomer.id, "customer");
    assert.equal(state.selected[0].quantity, 3);
    assert.equal(state.requestKey, key);
    f.cancel = false;
    await state.changeCustomer("other");
    assert.equal(state.sourceCustomer.id, "other");
    assert.equal(state.selected.length, 0);
    assert.notEqual(state.requestKey, key);
    assert.equal(state.sources[0].customer_id, "other");
    await state.changeCustomer("");
    assert.equal(state.sources.length, 0);
    assert.equal(state.sourceTotal, 0);
    assert.equal(state.sourceCustomer, null);
  } finally {
    stop();
  }
});

test("remote customer search preserves the selected option and late goods responses are discarded", async () => {
  const rows = [
    source(1),
    {
      ...source(2),
      customer_id: "other",
      customer_name_snapshot: "客户B",
      quotation_id: "other-quote",
    },
  ];
  const { f, state, stop } = await fixture(Order, {}, { sources: rows });
  let release;
  try {
    await state.loadSourceCustomers("客户B");
    assert.equal(state.customerOptions.length, 2);
    const wait = new Promise((resolve) => {
      release = resolve;
    });
    f.sourceWait = async (params) => {
      if (params.customer_id === "customer") await wait;
    };
    const stale = state.loadSources();
    await flush();
    await state.changeCustomer("other");
    release();
    await stale;
    assert.equal(state.sourceCustomer.id, "other");
    assert.equal(state.sources[0].customer_id, "other");
    assert.equal(state.sourceTotal, 1);
  } finally {
    release?.();
    stop();
  }
});

test("tier selection fills its price and confirmed goods are posted as one customer order", async () => {
  const { f, state, stop } = await fixture();
  try {
    state.choose(state.sources[0], true);
    state.choose(state.sources[1], true);
    const selected = state.choices["line-1"];
    selected.tier_id = "tier-1";
    state.tierChanged(selected);
    assert.equal(selected.quantity, 50);
    assert.equal(selected.unit_price, 8);
    assert.equal(state.originalPrice(selected), 8);
    await state.confirmOrder();
    await flush();
    const writes = f.calls.filter((c) => c.method === "post");
    assert.equal(writes.length, 1);
    assert.equal(writes[0].data.lines.length, 2);
    assert.equal(writes[0].data.lines[0].quotation_tier_id, "tier-1");
    assert.equal(writes[0].data.lines[0].quotation_version_no, 7);
    assert.equal(f.paths.at(-1).query.order_id, "order");
  } finally {
    stop();
  }
});

test("main quote is visibly selected, switching back restores its quantity and price, and posts no tier UUID", async () => {
  const { f, state, stop } = await fixture();
  try {
    state.sources[1].quantity_tiers = [];
    state.choose(state.sources[0], true);
    state.choose(state.sources[1], true);
    const row = state.choices["line-1"];
    const main = state.tierOptions(row.source)[0];
    assert.ok(main.value && row.tier_id === main.value);
    assert.equal(main.label, "10 件 / 12.80 EUR");
    assert.deepEqual(state.tierOptions(state.sources[1]), [main]);
    row.tier_id = "tier-1";
    state.tierChanged(row);
    assert.equal(row.quantity, 50);
    assert.equal(row.unit_price, 8);
    row.is_price_confirmed = true;
    row.tier_id = main.value;
    state.tierChanged(row);
    assert.equal(row.quantity, 10);
    assert.equal(row.unit_price, 12.8);
    assert.equal(state.originalPrice(row), 12.8);
    assert.equal(row.is_price_confirmed, false);
    await state.confirmOrder();
    const write = f.calls.find((call) => call.method === "post");
    assert.equal(write.data.lines[0].quotation_tier_id, null);
    assert.equal(write.data.lines[1].quotation_tier_id, null);
  } finally {
    stop();
  }
});

test("failed confirmation preserves its idempotency key and cancellation writes nothing", async () => {
  const { f, state, stop } = await fixture();
  try {
    state.choose(state.sources[0], true);
    f.cancel = true;
    await assert.rejects(state.confirmOrder());
    assert.equal(f.calls.filter((c) => c.method === "post").length, 0);
    f.cancel = false;
    f.failPost = true;
    await assert.rejects(state.confirmOrder());
    const key = f.calls.at(-1).data.idempotency_key;
    f.failPost = false;
    await state.confirmOrder();
    assert.equal(
      f.calls.filter((c) => c.method === "post").at(-1).data.idempotency_key,
      key,
    );
  } finally {
    stop();
  }
});

test("discount recalculates against each quote tier and manual price cannot undercut seven tenths", async () => {
  const { f, state, stop } = await fixture();
  try {
    state.choose(state.sources[0], true);
    const row = state.choices["line-1"];
    assert.equal(row.discount_rate, "1");
    row.discount_rate = "0.9";
    state.applyDiscount(row, state.originalPrice(row));
    assert.equal(row.unit_price, 11.52);
    assert.equal(row.adjustment_reason, "订单折扣：九折");
    row.tier_id = "tier-1";
    state.tierChanged(row);
    assert.equal(row.quantity, 50);
    assert.equal(row.unit_price, 7.2);
    assert.equal(state.originalPrice(row), 8);
    row.is_price_confirmed = true;
    await state.confirmOrder();
    const call = f.calls.find((value) => value.method === "post");
    assert.equal(call.data.lines[0].discount_rate, "0.9");
    assert.equal(call.data.lines[0].unit_price, 7.2);
  } finally {
    stop();
  }
  const second = await fixture();
  try {
    second.state.choose(second.state.sources[0], true);
    const row = second.state.choices["line-1"];
    row.discount_rate = "manual";
    row.unit_price = 8.95;
    await assert.rejects(second.state.confirmOrder(), /七折/);
    assert.equal(
      second.f.calls.some((value) => value.method === "post"),
      false,
    );
    assert.equal(second.state.discountPrice("0.03", "0.7"), 0.03);
    assert.equal(second.state.discountPrice("1.01", "0.95"), 0.96);
  } finally {
    second.stop();
  }
});

test("mixed customers cannot be selected by the page header and no partial choice is retained", async () => {
  const { f, state, stop } = await fixture();
  try {
    f.sources[10].customer_id = "other";
    state.choosePage(true);
    assert.match(f.messages.at(-1), /客户/);
    assert.equal(state.selected.length, 0);
    state.choose(f.sources[0], true);
    state.choose(f.sources[10], true);
    assert.equal(state.selected.length, 1);
  } finally {
    stop();
  }
});

test("confirmation requires order review before opening or submitting production", async () => {
  const { f, state, stop } = await fixture();
  try {
    state.order = f.currentOrder = {
      id: "order",
      version_no: 1,
      status_code: "confirmed",
      lines: [{ id: "a", remaining_quantity: "10", unit_name_snapshot: "件" }],
    };
    await assert.rejects(state.startRelease(), /审核/);
    await assert.rejects(state.release(), /审核/);
    assert.equal(
      f.calls.some(call => call.url.endsWith("/production-defaults") || call.url.endsWith("/release")),
      false,
    );
    await state.approveOrder();
    assert.equal(state.order.status_code, "approved");
    assert.deepEqual(f.calls.find(call => call.url.endsWith("/approve")).data, { version_no: 1 });
    await state.startRelease();
    assert.equal(state.releaseOpen, true);
  } finally {
    stop();
  }
});

test("production compares actual units and needs no extra confirmation when they match", async () => {
  const { f, state, stop } = await fixture();
  try {
    state.order = f.currentOrder = {
      id: "order",
      version_no: 3,
      status_code: "approved",
      lines: [
        { id: "a", remaining_quantity: "10", unit_name_snapshot: "件" },
        { id: "b", remaining_quantity: "20", unit_name_snapshot: "件" },
      ],
      productions: [],
    };
    await state.startRelease();
    await assert.rejects(state.release(), /货品/);
    state.releaseRows.forEach((row) => {
      row.product_item_id = "material";
      row.product_unit_code = "kg";
    });
    await assert.rejects(state.release(), /单位/);
    state.releaseRows.forEach((row) => (row.product_unit_code = "piece"));
    await state.release();
    assert.equal(state.releaseOpen, false);
    const writes = f.calls.filter((c) => c.method === "post");
    assert.equal(writes.length, 1);
    assert.equal(writes[0].data.lines.length, 2);
    assert.equal(writes[0].data.lines[0].quantity, 10);
    assert.equal("is_unit_confirmed" in writes[0].data, false);
    assert.equal(state.order.productions.length, 1);
  } finally {
    stop();
  }
});

test("historical references require same currency and explicit confirmation, and preserve customer requirements", async () => {
  const { f, state, stop } = await fixture(History, {
    currency: "EUR",
    customerId: "customer",
    editable: true,
  });
  try {
    const line = reactive({
      drawing_no: "P-1",
      drawing_revision: "B",
      quantity: 10,
      customer_material: "客户材料",
      quoted_material: "",
      weight_kg: null,
      unit_price: null,
      engineering_note: "",
    });
    state.open(line);
    await flush();
    const historical = {
      quote_no: "BJ-OLD",
      revision: 2,
      drawing_no: "P-1",
      drawing_revision: "A",
      quantity: "50",
      customer_material: "旧材料",
      quoted_material: "6082",
      weight_kg: "0.5",
      unit_price: "8",
      currency: "CNY",
    };
    await state.apply(historical);
    assert.equal(line.unit_price, null);
    historical.currency = "EUR";
    f.cancel = true;
    await state.apply(historical);
    assert.equal(line.unit_price, null);
    f.cancel = false;
    await state.apply(historical);
    assert.equal(line.unit_price, 8);
    assert.equal(line.customer_material, "客户材料");
    assert.equal(line.quantity, 10);
    assert.match(line.engineering_note, /BJ-OLD R2/);
    assert.equal(state.visible, false);
  } finally {
    stop();
  }
});

test("order editing submits only editable deal fields and its current version", async () => {
  const order = {
    id: "order",
    version_no: 4,
    customer_po_no: "PO-A",
    note: "",
    lines: [
      {
        id: "line",
        drawing_no_snapshot: "P1",
        quantity: "10",
        unit_price: "12.80",
        original_unit_price_snapshot: "12.80",
        due_date: "2026-12-01",
      },
    ],
  };
  const saved = [];
  const { f, state, stop } = await fixture(Edit, {
    order,
    onSaved: (value) => saved.push(value),
  });
  try {
    f.currentOrder = order;
    state.rows[0].quantity = 6;
    state.rows[0].unit_price = 11;
    state.rows[0].is_price_confirmed = true;
    state.rows[0].adjustment_reason = "客户确认优惠";
    await state.save();
    const request = f.calls.find((call) => call.method === "put");
    assert.equal(request.data.version_no, 4);
    assert.equal(request.data.lines[0].unit_price, 11);
    assert.equal(request.data.lines[0].adjustment_reason, "客户确认优惠");
    assert.equal(
      "original_unit_price_snapshot" in request.data.lines[0],
      false,
    );
    assert.equal(order.lines[0].unit_price, "12.80");
    assert.equal(saved.length, 1);
  } finally {
    stop();
  }
});

test("quantity editor emits distinct valid tiers without mutating props and respects the five-tier limit", async () => {
  const line = reactive({
    quantity: 999999.999,
    unit_name: "件",
    unit_price: null,
    quantity_tiers: [],
  });
  const { state, stop } = await fixture(Tiers, {
    line,
    business: true,
    price: false,
    currency: "EUR",
    onUpdate: (value) => (line.quantity_tiers = value),
  });
  try {
    for (let i = 0; i < 5; i++) state.add();
    assert.equal(line.quantity_tiers.length, 4);
    assert.equal(new Set(line.quantity_tiers.map((t) => t.quantity)).size, 4);
    assert.ok(
      line.quantity_tiers.every((t) => t.quantity > 0 && t.quantity <= 1000000),
    );
    state.change(0, { quantity: 50 });
    state.remove(1);
    assert.equal(line.quantity_tiers[0].quantity, 50);
    assert.equal(line.quantity_tiers.length, 3);
  } finally {
    stop();
  }
});

test("production defaults fill existing items and units, and mark missing goods for transactional creation", async () => {
  const { f, state, stop } = await fixture();
  try {
    state.order = f.currentOrder = {
      id: "order",
      version_no: 3,
      status_code: "approved",
      lines: [
        {
          id: "a",
          drawing_no_snapshot: "P1",
          description_snapshot: "连接板",
          remaining_quantity: "10",
          unit_name_snapshot: "件",
        },
        {
          id: "b",
          drawing_no_snapshot: "P2",
          remaining_quantity: "20",
          unit_name_snapshot: "件",
        },
      ],
      productions: [],
    };
    f.defaults = {
      unit_names: { piece: "件" },
      lines: [
        {
          order_line_id: "a",
          product_item_id: null,
          item_no: "P1",
          item_name: "连接板",
          unit_code: "piece",
          unit_name: "件",
          match_status: "not_found",
          is_create_product: true,
          can_create: true,
        },
        {
          order_line_id: "b",
          product_item_id: "existing",
          item_no: "P2",
          item_name: "法兰盘",
          unit_code: "piece",
          unit_name: "件",
          match_status: "matched",
          is_create_product: false,
          can_create: true,
        },
      ],
    };
    await state.startRelease();
    assert.equal(state.releaseRows[0].is_create_product, true);
    assert.equal(state.releaseRows[0].product_unit_code, "piece");
    assert.equal(state.releaseRows[1].product_item_id, "existing");
    assert.equal(state.releaseRows[1].unit, "件");
    assert.match(state.releaseRows[1].initial_option.label, /P2/);
    await state.release();
    const request = f.calls.find((call) => call.url.endsWith("/release"));
    assert.equal(request.data.lines[0].is_create_product, true);
    assert.equal(request.data.lines[0].product_item_id, null);
    assert.equal(request.data.lines[0].product_unit_code, "piece");
    assert.equal(request.data.lines[1].product_item_id, "existing");
  } finally {
    stop();
  }
});
