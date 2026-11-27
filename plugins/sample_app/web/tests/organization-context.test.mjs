import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";

const require = createRequire(
  new URL("../../../core/web/package.json", import.meta.url),
);
const vue = require("vue");
const ts = require("typescript");
const { parse, compileScript, compileTemplate } = require("@vue/compiler-sfc");

function evaluate(source, dependencies, globals = {}) {
  const exports = {};
  runInNewContext(
    ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText,
    {
      exports,
      require: (name) => {
        if (!(name in dependencies))
          throw new Error(`Unexpected import: ${name}`);
        return dependencies[name];
      },
      ...globals,
    },
  );
  return exports;
}

function renderer() {
  const node = (type, text = "") => ({
    type,
    text,
    children: [],
    parent: null,
  });
  return {
    root: node("root"),
    renderer: vue.createRenderer({
      createElement: (type) => node(type),
      createText: (text) => node("text", text),
      createComment: (text) => node("comment", text),
      insert(child, parent, anchor = null) {
        if (child.parent)
          child.parent.children.splice(child.parent.children.indexOf(child), 1);
        child.parent = parent;
        const at = anchor ? parent.children.indexOf(anchor) : -1;
        if (at < 0) parent.children.push(child);
        else parent.children.splice(at, 0, child);
      },
      remove(child) {
        if (child.parent)
          child.parent.children.splice(child.parent.children.indexOf(child), 1);
        child.parent = null;
      },
      setElementText(element, text) {
        element.text = text;
        element.children = [];
      },
      setText(element, text) {
        element.text = text;
      },
      parentNode: (node) => node.parent,
      nextSibling: (node) =>
        node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
      patchProp(element, key, _old, value) {
        element[key] = value;
      },
    }),
  };
}

const text = (node) => node.text + node.children.map(text).join("");
async function flush() {
  await vue.nextTick();
  await vue.nextTick();
}

test("页面组织状态互相独立，读取默认不限定组织，写入使用表单归属", async () => {
  const contextModule = evaluate(
    readFileSync(
      new URL("../src/api/sample_appContext.ts", import.meta.url),
      "utf8",
    ),
    { vue },
  );
  const first = contextModule.createBusinessContext(),
    second = contextModule.createBusinessContext();
  first.operationOrg.value = "A";
  assert.equal(second.operationOrg.value, "");
  const calls = [];
  const module = evaluate(
    readFileSync(new URL("../src/api/sample_app.ts", import.meta.url), "utf8"),
    {
      "@/utils/http": {
        http: {
          request: (...args) => {
            calls.push(args);
            return Promise.resolve({ code: 0, data: [] });
          },
        },
      },
      "./sample_appContext": { useBusinessContext: () => first },
    },
  );
  const apiA = module.createSampleApi(() => first.operationOrg.value);
  const apiB = module.createSampleApi(() => second.operationOrg.value);
  await apiA.listEmployees();
  assert.equal(calls.at(-1)[2].params.org_id, undefined);
  await apiA.saveEmployee({
    org_id: "B",
    employee_no: "1",
    full_name: "test",
    employment_status_code: "active",
    hire_date: null,
  });
  assert.equal(calls.at(-1)[2].params.org_id, "B");
  await apiB.getCashLedger();
  assert.equal(calls.at(-1)[2].params.org_id, undefined);
  await apiA.calculatePayroll("2026-10");
  assert.equal(calls.at(-1)[2].params.org_id, "A");
});

test("标准表格支持搜索、分页及行内编辑，并随工作表更新动态插槽", async () => {
  const { descriptor } = parse(
    readFileSync(
      new URL(
        "../src/views/sample-app/components/BusinessTable.vue",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  let tableProps, goToPage, enterSearch, changeKeyword, changeOrganization;
  const Table = vue.defineComponent({
    props: ["data", "columns", "pagination"],
    emits: ["page-current-change", "page-size-change"],
    setup(props, { emit, slots, expose }) {
      expose({ getTableRef: () => ({}) });
      tableProps = props;
      goToPage = (page) => emit("page-current-change", page);
      return () =>
        vue.h(
          "table",
          props.data.map((row) =>
            vue.h(
              "cell",
              props.columns.map((column) =>
                column.slot
                  ? slots[column.slot]?.({ row })
                  : String(row[column.prop] ?? ""),
              ),
            ),
          ),
        );
    },
  });
  const Bar = vue.defineComponent({
    inheritAttrs: false,
    props: ["columns", "title", "tableRef"],
    emits: ["refresh", "fullscreen"],
    setup(props, { slots }) {
      // 与真实工具栏一样，仅在挂载时缓存列配置。
      const dynamicColumns = [...props.columns];
      return () => [
        slots.title?.(),
        slots.default?.({ size: "default", dynamicColumns }),
      ];
    },
  });
  const BusinessTable = evaluate(
    compileScript(descriptor, { id: "business-table", inlineTemplate: true })
      .content,
    {
      vue,
      "@pureadmin/table": { PureTable: Table },
      "element-plus": {
        ElMessage: { error() {}, success() {} },
        ElMessageBox: { confirm: async () => {} },
      },
      "@plugins/sample_app/web/src/api/sample_app": {
        deleteSampleRecord: async () => ({ code: 0 }),
      },
      "@plugins/sample_app/web/src/api/sample_appContext": {
        useBusinessContext: () => ({
          organizations: vue.ref([
            { id: "A", org_name: "组织A" },
            { id: "B", org_name: "组织B" },
          ]),
          operationOrg: vue.ref(""),
        }),
      },
      "@/components/RePureTableBar": { PureTableBar: Bar },
      "@/api/systemFile": {
        uploadSelectedFiles: async () => [],
        getFileUrl: async () => ({ code: 0, data: { url: "" } }),
      },
      "@/components/ReIcon/src/hooks": { useRenderIcon: () => null },
    },
  ).default;
  const loadedRows = Array.from({ length: 26 }, (_, index) => ({
    id: index + 1,
    name: `员工${index + 1}`,
    org_id: index % 2 === 0 ? "A" : "B",
    org_name: index % 2 === 0 ? "组织A" : "组织B",
    amount: 1234.5,
  }));
  const rows = vue.ref([]);
  const slotName = vue.ref("first");
  const controlled = vue.ref(false),
    selectedOrganization = vue.ref(""),
    showOrganization = vue.ref(true);
  const columns = vue.computed(() => [
    { label: "姓名", prop: "name" },
    { label: "金额", prop: "amount" },
    { label: "动态列", slot: slotName.value },
  ]);
  const host = renderer();
  const app = host.renderer.createApp({
    render: () =>
      vue.h(
        BusinessTable,
        {
          title: "测试",
          data: rows.value,
          columns: columns.value,
          organizationFilterVisible: showOrganization.value,
          ...(controlled.value
            ? {
                organization: selectedOrganization.value,
                "onUpdate:organization": (value) => {
                  selectedOrganization.value = value;
                },
              }
            : {}),
        },
        {
          summary: ({ rows }) =>
            vue.h("summary-hint", `统计范围:${rows.length}`),
          [slotName.value]: ({ row }) =>
            vue.h("slot-cell", `${slotName.value}:${row.id}`),
        },
      ),
  });
  app.component("ElInput", {
    props: ["modelValue"],
    emits: ["update:modelValue", "keyup"],
    setup(_props, { emit }) {
      changeKeyword = (value) => emit("update:modelValue", value);
      enterSearch = () => emit("keyup", { key: "Enter" });
      return () => vue.h("input");
    },
  });
  app.component("ElSelect", {
    props: ["modelValue"],
    emits: ["update:modelValue"],
    setup(_props, { emit, slots }) {
      changeOrganization = (value) => emit("update:modelValue", value);
      return () => vue.h("select", slots.default?.());
    },
  });
  for (const name of ["ElForm", "ElFormItem", "ElButton", "ElOption"])
    app.component(name, {
      setup(_props, { slots, attrs }) {
        return () => vue.h("control", attrs, slots.default?.());
      },
    });
  app.mount(host.root);
  await flush();
  assert.equal(tableProps.data.length, 0);
  assert.equal(tableProps.columns[0].prop, "org_name");
  rows.value = loadedRows;
  await flush();
  assert.equal(tableProps.columns[0].label, "所属组织");
  assert.equal(tableProps.columns[0].formatter({ org_id: "A" }), "组织A");
  assert.equal(tableProps.columns[0].formatter({ org_id: "unknown" }), "—");
  assert.equal(tableProps.data.length, 20);
  assert.equal(tableProps.pagination.total, 26);
  assert.match(text(host.root), /统计范围:26/);
  assert.equal(
    tableProps.columns
      .find((column) => column.prop === "amount")
      .formatter({}, {}, 1234.5),
    "1,234.50",
  );
  goToPage(2);
  await flush();
  assert.equal(tableProps.data.length, 6);
  tableProps.data[0].name = "已编辑";
  assert.equal(rows.value[20].name, "已编辑");
  changeOrganization("A");
  await flush();
  assert.equal(tableProps.pagination.total, 13);
  assert.match(text(host.root), /统计范围:13/);
  changeKeyword("已编辑");
  await flush();
  enterSearch();
  await flush();
  assert.equal(tableProps.data.length, 1);
  assert.equal(tableProps.pagination.currentPage, 1);
  assert.equal(tableProps.data[0].id, 21);
  assert.match(text(host.root), /统计范围:1/);
  slotName.value = "second";
  await flush();
  assert.match(text(host.root), /second:21/);
  assert.doesNotMatch(text(host.root), /first:21/);
  controlled.value = true;
  selectedOrganization.value = "B";
  changeKeyword("");
  enterSearch();
  await flush();
  assert.equal(tableProps.pagination.total, 13);
  changeOrganization("A");
  await flush();
  assert.equal(selectedOrganization.value, "A");
  assert.equal(tableProps.pagination.total, 13);
  const find = (node, predicate) =>
    predicate(node)
      ? node
      : node.children.map((child) => find(child, predicate)).find(Boolean);
  find(
    host.root,
    (node) => node.type === "control" && text(node) === "重置",
  ).onClick();
  await flush();
  assert.equal(selectedOrganization.value, "");
  assert.equal(tableProps.pagination.total, 26);
  showOrganization.value = false;
  await flush();
  assert.equal(
    find(host.root, (node) => node.type === "select"),
    undefined,
  );
  app.unmount();
});

test("资金弹窗绑定当前报销单、防止重复提交，并固定成本入账月份", async () => {
  const { descriptor } = parse(
    readFileSync(
      new URL("../src/views/sample-app/content/cash.vue", import.meta.url),
      "utf8",
    ),
  );
  const calls = [];
  let finish;
  const ok = { code: 0, message: "ok", data: [] };
  const api = new Proxy(
    {},
    {
      get: (_target, name) => {
        if (name === "actReimbursement")
          return (id, body) => {
            calls.push([id, body]);
            return new Promise((resolve) => {
              finish = resolve;
            });
          };
        if (name === "createReimbursement")
          return async (body) => {
            calls.push(["claim", body]);
            return ok;
          };
        if (name === "createLoan")
          return async (body) => {
            calls.push(["loan", body]);
            return ok;
          };
        if (name === "chargeFixedCost")
          return async (id, month) => {
            calls.push([id, month]);
            return ok;
          };
        if (name === "getCashLedger")
          return async () => ({
            ...ok,
            data: {
              accounts: [],
              entries: [],
              checkpoints: [],
              month_income: 0,
              month_expense: 0,
              month_net: 0,
            },
          });
        return async () => ok;
      },
    },
  );
  const page = evaluate(
    compileScript(descriptor, { id: "cash-test" }).content,
    {
      vue: { ...vue, onMounted: () => {} },
      "@/api/systemFile": {
        uploadSelectedFiles: async () => [],
        getFileUrl: async () => ({ code: 0, data: { url: "" } }),
      },
      "@/components/ReIcon/src/hooks": { useRenderIcon: () => null },
      "../components/BusinessTable.vue": {},
      "../components/OrganizationField.vue": {},
      "@plugins/sample_app/web/src/api/sample_appContext": {
        useOrganizationLifetime: () => () => true,
      },
      "element-plus": { ElMessage: { warning() {}, error() {}, success() {} } },
      "@plugins/sample_app/web/src/api/sample_app": { useSampleApi: () => api },
    },
  ).default.setup({}, { expose() {} });
  assert.equal(page.month.value, null);
  page.loans.value = [
    {
      id: "a",
      borrowed_on: "2026-08-01",
      debt_type_code: "company_payable",
      outstanding_amount: 100,
      repayment_status_code: "unpaid",
    },
    {
      id: "b",
      borrowed_on: "2026-09-01",
      debt_type_code: "employee_loan",
      outstanding_amount: 40,
      repayment_status_code: "partial",
    },
  ];
  assert.equal(page.filteredDebts.value.length, 2);
  assert.match(
    page.debtHint(page.filteredDebts.value),
    /公司待付 100.00 元，往来方待还 40.00 元/,
  );
  page.debtMonth.value = "2026-09";
  assert.equal(page.filteredDebts.value.length, 1);
  assert.match(
    page.debtHint(page.filteredDebts.value),
    /公司待付 0.00 元，往来方待还 40.00 元/,
  );
  assert.match(
    page.flowHint([
      { direction_code: "income", amount: 100 },
      { direction_code: "expense", amount: 30 },
    ]),
    /净流入 70.00 元/,
  );
  page.openPost({ id: "claim-a", subject: "a", amount: 10 });
  page.postAccount.value = "old-account";
  page.openPost({ id: "claim-b", subject: "b", amount: 20 });
  assert.equal(page.postAccount.value, "");
  await page.submitForm();
  assert.equal(calls.length, 0);
  page.postAccount.value = "bank-b";
  const pending = page.submitForm();
  await page.submitForm();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "claim-b");
  assert.equal(calls[0][1].account_id, "bank-b");
  finish(ok);
  await pending;
  assert.equal(page.formDialog.value, "");
  page.month.value = "2026-08";
  page.openCharge({ id: "cost-a", account_id: "bank-a", monthly_amount: 50 });
  page.postingMonth.value = "2026-08";
  page.month.value = "2026-09";
  await page.submitForm();
  assert.equal(calls[1][0], "cost-a");
  assert.equal(calls[1][1], "2026-08");
  page.entry.amount = 999;
  page.openForm("entry");
  assert.equal(page.entry.amount, 0);
  assert.equal(page.entry.account_id, "");
  page.openDebt();
  page.loan.org_id = "company-kuaihe";
  page.loan.employee_id = "person-employed-at-qingdao";
  page.loan.amount = 100;
  await page.submitDebt();
  assert.equal(calls.at(-1)[0], "loan");
  assert.equal(calls.at(-1)[1].org_id, "company-kuaihe");
  assert.equal(calls.at(-1)[1].employee_id, "person-employed-at-qingdao");
  page.openForm("claim");
  page.claim.org_id = "company-kuaihe";
  page.claim.employee_id = "person-employed-at-qingdao";
  page.claim.amount = 100;
  page.claim.subject = "expense";
  await page.submitForm();
  assert.equal(calls.at(-1)[0], "claim");
  assert.equal(calls.at(-1)[1].org_id, "company-kuaihe");
  assert.equal(calls.at(-1)[1].employee_id, "person-employed-at-qingdao");
  await page.showRepaymentHistory({
    id: "decimal-debt",
    full_name: "test",
    debt_type_code: "company_payable",
    amount: "1526.65",
    outstanding_amount: 1526.65,
  });
  assert.equal(page.repaymentHistoryDialog.value, true);
  assert.equal(page.repaymentHistoryLoading.value, false);
  // 接口的 Decimal 为字符串；实际编译并渲染弹窗金额，防止再次调用字符串.toFixed。
  const source = readFileSync(
    new URL("../src/views/sample-app/content/cash.vue", import.meta.url),
    "utf8",
  );
  const start = source.indexOf('<p v-if="selectedDebt"');
  const fragment = source.slice(start, source.indexOf("</p>", start) + 4);
  const compiled = compileTemplate({
    source: fragment,
    filename: "repayment-detail.vue",
    id: "repayment-detail",
  });
  assert.equal(compiled.errors.length, 0);
  const render = evaluate(compiled.code, { vue }).render;
  const host = renderer();
  const app = host.renderer.createApp({
    render: () => render(vue.proxyRefs(page), []),
  });
  app.mount(host.root);
  assert.match(text(host.root), /1,526.65/);
  app.unmount();
});

test("社保支付按费用月份筛选，认领已有流水不重复新增并保留付款公司", async () => {
  const { descriptor } = parse(
    readFileSync(
      new URL(
        "../src/views/sample-app/content/social-bills.vue",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const calls = [];
  let finish;
  const api = {
    listSocialBills: async () => ({ code: 0, data: [] }),
    getCashLedger: async () => ({
      code: 0,
      data: {
        accounts: [],
        entries: [
          {
            id: "bank-oct",
            org_id: "A",
            account_id: "account-a",
            occurred_on: "2026-10-24",
            amount: "7000.00",
            direction_code: "expense",
            source_type_code: null,
            source_id: null,
          },
          {
            id: "other-org",
            org_id: "B",
            account_id: "account-b",
            occurred_on: "2026-10-24",
            amount: 7000,
            direction_code: "expense",
          },
          {
            id: "claimed",
            org_id: "A",
            amount: 7000,
            direction_code: "expense",
            source_type_code: "social_bill",
          },
        ],
      },
    }),
    paySocialBill: (...args) => {
      calls.push(args);
      return new Promise((resolve) => {
        finish = resolve;
      });
    },
  };
  const page = evaluate(
    compileScript(descriptor, { id: "social-payment" }).content,
    {
      vue: { ...vue, onMounted: () => {} },
      "../components/BusinessTable.vue": {},
      "../components/OrganizationField.vue": {},
      "element-plus": {
        ElMessage: { warning() {}, error() {}, success() {} },
        ElMessageBox: { confirm: async () => {} },
      },
      "@plugins/sample_app/web/src/api/sample_app": {
        useSampleApi: () => api,
        socialAmountLabels: {
          pension_employee_amount: "个人养老",
          pension_employer_amount: "单位养老",
        },
      },
    },
  ).default.setup({}, { expose() {} });
  assert.equal(page.month.value, null);
  const october = {
    id: "oct",
    bill_id: "oct",
    org_id: "A",
    period_month: "2026-10-01",
    total_amount: 7000,
    employee_amount: 2000,
    employer_amount: 5000,
    pending_recovery_amount: 2000,
    paid_amount: 0,
  };
  page.rows.value = [
    october,
    { ...october, id: "nov", period_month: "2026-11-01" },
  ];
  assert.equal(page.filtered.value.length, 2);
  page.month.value = "2026-10";
  assert.equal(page.filtered.value.length, 1);
  assert.match(page.summary(page.filtered.value), /单位承担 5,000.00 元/);
  await page.openPayment(october, "social");
  assert.deepEqual(
    Array.from(page.candidates.value, (e) => e.id),
    ["bank-oct"],
  );
  page.payment.mode = "existing";
  await flush();
  page.payment.cash_entry_id = "bank-oct";
  await flush();
  assert.equal(page.payment.account_id, "account-a");
  assert.equal(page.payment.paid_on, "2026-10-24");
  const pending = page.pay();
  await page.pay();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "oct");
  assert.equal(calls[0][1].org_id, "A");
  assert.equal(calls[0][1].cash_entry_id, "bank-oct");
  finish({ code: 0 });
  await pending;
});
test("internal employee account can be replaced and unlinked by an administrator", async () => {
  const { descriptor } = parse(
    readFileSync(
      new URL("../src/views/sample-app/content/employee.vue", import.meta.url),
      "utf8",
    ),
  );
  const employee = { id: "employee-a", full_name: "员工甲", org_id: "org-a" };
  let bindings = [
    {
      employee_id: employee.id,
      user_id: "old-user",
      account_name: "原账号",
      is_active: true,
      org_id: employee.org_id,
    },
  ];
  const writes = [];
  const api = {
    listFlexFields: async () => ({ code: 0, data: [] }),
    listEmployees: async () => ({ code: 0, data: [employee] }),
    listEmployeeAccountBindings: async () => ({ code: 0, data: [...bindings] }),
    listEmployeeAccountOptions: async () => ({
      code: 0,
      data: [{ id: "new-user", name: "新账号", org_name: "快盒" }],
    }),
    bindEmployeeAccount: async (body) => {
      writes.push(body);
      bindings = [
        { ...bindings[0], user_id: body.user_id, account_name: "新账号" },
      ];
      return { code: 0 };
    },
    unbindEmployeeAccount: async (userId, employeeId) => {
      writes.push([userId, employeeId]);
      bindings = [];
      return { code: 0 };
    },
  };
  const page = evaluate(
    compileScript(descriptor, { id: "employee-binding" }).content,
    {
      vue: { ...vue, onMounted() {} },
      "../components/FlexFields.vue": {},
      "../components/BusinessTable.vue": {},
      "../components/OrganizationField.vue": {},
      "@/components/ReIcon/src/hooks": { useRenderIcon() {} },
      "@/store/modules/user": {
        useUserStoreHook: () => ({
          permissions: [
            "sample_app:access",
            "user_profile:detail",
            "user_profile:list",
          ],
        }),
      },
      "element-plus": {
        ElMessage: { error() {}, success() {} },
        ElMessageBox: { confirm: async () => {} },
      },
      "@plugins/sample_app/web/src/api/sample_app": { useSampleApi: () => api },
    },
  ).default.setup({ personnelType: "internal" }, { expose() {} });
  await page.load();
  assert.equal(page.bindingFor(employee.id).account_name, "原账号");
  await page.openBinding(employee);
  page.bindingUserId.value = "new-user";
  await page.saveBinding();
  assert.equal(writes[0].previous_user_id, "old-user");
  assert.equal(writes[0].employee_id, employee.id);
  assert.equal(page.bindingFor(employee.id).account_name, "新账号");
  await page.removeBinding(employee);
  assert.deepEqual(Array.from(writes[1]), ["new-user", employee.id]);
  assert.equal(page.bindingFor(employee.id), undefined);
});

test("删除需确认、拒绝重复点击、失败不刷新，正式报销按状态限制", async () => {
  const { descriptor } = parse(
    readFileSync(
      new URL(
        "../src/views/sample-app/components/BusinessTable.vue",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  let confirmResolve,
    calls = 0,
    refreshed = 0;
  const props = {
    columns: [],
    data: [],
    title: "报销",
    deleteResource: "reimbursements",
  };
  const page = evaluate(
    compileScript(descriptor, { id: "delete-table" }).content,
    {
      vue: { ...vue, useSlots: () => ({}) },
      "@pureadmin/table": { PureTable: {} },
      "@/components/RePureTableBar": { PureTableBar: {} },
      "@/components/ReIcon/src/hooks": { useRenderIcon() {} },
      "@plugins/sample_app/web/src/api/sample_appContext": {
        useBusinessContext: () => undefined,
      },
      "@plugins/sample_app/web/src/api/sample_app": {
        deleteSampleRecord: async () => {
          calls++;
          return { code: 0 };
        },
      },
      "element-plus": {
        ElMessage: { error() {}, success() {} },
        ElMessageBox: {
          confirm: () =>
            new Promise((resolve) => {
              confirmResolve = resolve;
            }),
        },
      },
    },
  ).default.setup(props, {
    expose() {},
    emit(name) {
      if (name === "refresh") refreshed++;
    },
  });
  assert.equal(page.canDelete({ id: "a", status_code: "posted" }), false);
  assert.equal(page.canDelete({ id: "a", status_code: "submitted" }), false);
  const row = { id: "a", status_code: "draft" };
  const pending = page.deleteRow(row);
  await page.deleteRow(row);
  assert.equal(calls, 0);
  confirmResolve();
  await pending;
  assert.equal(calls, 1);
  assert.equal(refreshed, 1);
});
