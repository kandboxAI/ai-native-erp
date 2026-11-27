// 员工门户交互回归：模拟 DOM / fetch，禁止连接线上服务。
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";

const source = JSON.parse(readFileSync(0, "utf8"));
const elements = new Map();
class Element {
  constructor() {
    this.value = ""; this.hidden = true; this.disabled = false;
    this.textContent = ""; this.children = []; this.files = []; this.checked = false;
    this.classList = { toggle() {} };
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  reset() { this.value = ""; }
}
const $ = id => {
  if (!elements.has(id)) elements.set(id, new Element());
  return elements.get(id);
};
let request = {
  request_id: "request-a", subject: "<img src=x onerror=alert(1)>", amount: "286.00",
  occurred_on: "2026-10-26", employee_name: "本人", org_name: "本人企业",
  expires_at: "2099-01-01T00:00:00+00:00", approved: false, reimbursement_id: null,
  source: "mcp", request_status: "ready",
  status: "awaiting_confirmation", attachments: [{ id: "file-a", file_name: "invoice.pdf", file_size: 100, content_type: "application/pdf" }]
};
const writes = [], uploads = [], reads = [], urls = [];
const formal = { ...request, request_id: null, reimbursement_id: "admin-receipt", subject: "后台代录报销",
  status: "posted", amount: "1351.19", request_status: undefined, source: undefined };
let interrupted = false;
let nonce=0, requestVersion=0, expectedCount=0;
const context = vm.createContext({
  URL, URLSearchParams, Uint8Array, Set,
  crypto: { randomUUID: () => "request-key-"+(++nonce) },
  location: { search: "?request_id=request-a", href: "http://localhost/?request_id=request-a" },
  history: { replaceState(_state, _title, url) { urls.push(url); } }, window: { scrollTo() {} },
  document: { getElementById: $, createElement: () => new Element(), querySelectorAll: () => [] },
  fetch: async (path, options = {}) => {
    reads.push(path);
    const body = options.body && typeof options.body === "string" ? JSON.parse(options.body) : null;
    if (path.startsWith("/employee/requests/")) return { ok: true, json: async () => structuredClone(request) };
    if (path === "/employee/reimbursements/admin-receipt") return { ok: true, json: async () => structuredClone(formal) };
    if (path === "/api/auth/captcha") return { ok: true, json: async () => ({ captcha_id: "mock", image: "mock" }) };
    if (path === "/employee/prepare") {
      writes.push([path, body]);
      expectedCount=body.files.length;
      request = { ...request, request_id: "request-new-"+(++requestVersion), source: "manual", request_status: "preparing", subject: body.subject, amount:body.amount, approved: false, reimbursement_id: null, attachments: [] };
      return { ok: true, json: async () => ({ request_id: request.request_id }) };
    }
    if (path === "/employee/revise") {
      writes.push([path,body]);request.request_status="superseded";
      return {ok:true,json:async()=>({})};
    }
    if (path === "/employee/upload-tickets") {
      writes.push([path, body]);
      return { ok: true, json: async () => ({ tickets: [{ id: body.files[0].file_name, upload: { url: "https://files.example.com/upload", method: "PUT", headers: {} } }] }) };
    }
    if (path === "https://files.example.com/upload") {
      uploads.push(path);
      if (uploads.length === 2 && !interrupted) { interrupted = true; throw new TypeError("offline"); }
      return { ok: true };
    }
    if (path === "/employee/complete-upload") {
      const invoice = writes.filter(([p]) => p === "/employee/upload-tickets").at(-1)[1].files[0];
      request.attachments.push({ id: body.file_id, ...invoice });
      if(request.attachments.length===expectedCount)request.request_status="ready";
      return { ok: true, json: async () => ({}) };
    }
    if (path === "/employee/approve") { writes.push([path, body]); request.approved = true;request.request_status="approved"; return { ok: true, json: async () => ({}) }; }
    if (path === "/employee/submit") {
      writes.push([path, body]); request.reimbursement_id = "receipt-a"; request.status = "submitted";
      return { ok: true, json: async () => ({ reimbursement_id: "receipt-a" }) };
    }
    throw new Error("Unexpected request: " + path);
  }
});
vm.runInContext(source, context);
const run = code => vm.runInContext(code, context);
assert.equal(run('money("9999999999999999.99")'), "9,999,999,999,999,999.99");
await run("refresh()");
assert.equal($("detailSubject").textContent, request.subject); // 自由文本只能作为文本显示。
assert.equal($("approve").disabled, true);
$("confirmContent").checked = true;
await run("renderState()");
assert.equal($("approve").disabled, false);
// 后台清单变动后，必须重新勾选，不沿用旧确认。
request.attachments.push({ ...request.attachments[0], id: "file-b" });
await run("refresh()");
assert.equal($("confirmContent").checked, false);
await $("approve").onclick();
assert.equal(writes.length, 0);
$("confirmContent").checked = true;
await $("approve").onclick();
assert.deepEqual(writes.map(([path]) => path), ["/employee/approve", "/employee/submit"]);
assert.equal($("confirmArea").hidden, true);
assert.equal($("editManual").hidden, true);
assert.equal($("copyAiRevision").hidden, true);
assert.equal($("files").children.length, 2); // 提交后仍可查看原件。
assert.equal($("receiptNumber").hidden, false);

// 模拟两份原件中第二份上传断网：重试复用同一申请，不重传第一份。
writes.length = 0;
$("expenseSubject").value = "出差"; $("expenseAmount").value = "10.00"; $("expenseDate").value = "2026-10-26";
$("composeFiles").files = [1, 2].map(i => ({
  name: i + ".pdf", size: 10, lastModified: 1,
  arrayBuffer: async () => new Uint8Array([37, 80, 68, 70, i]).buffer
}));
$("composeFiles").onchange();
// 直接等待 action 任务，模拟原生表单提交事件。
const submit = () => run("new Promise(resolve => { const original=action; action=async fn=>{try{await original(fn);}finally{action=original;resolve();}}; document.getElementById('expenseForm').onsubmit({preventDefault(){}}); })");
await submit();
assert.match($("message").textContent, /上传连接失败/);
assert.equal(request.attachments.length, 1);
await submit();
assert.equal(writes.filter(([path]) => path === "/employee/prepare").length, 1);
assert.equal(request.attachments.length, 2);
assert.equal(uploads.length, 3);
assert.equal($("confirmContent").checked, false);
assert.equal($("expense").hidden, false);
assert.equal(writes.filter(([path]) => path === "/employee/submit").length, 0);

// 发现漏传时，只能返回完整填写页；旧申请先失效，新申请关联旧版本。
const oldRequestId=request.request_id;
await $("editManual").onclick();
assert.equal(request.request_status,"superseded");
assert.equal($("compose").hidden,false);
assert.equal($("composeFileList").children.length,2);
$("composeFileList").children[0].children.at(-1).onclick();
assert.equal($("composeFileList").children.length,1);
$("composeFiles").files=[{name:"3.pdf",size:10,lastModified:1,arrayBuffer:async()=>new Uint8Array([37,80,68,70,3]).buffer}];
$("composeFiles").onchange();
$("expenseAmount").value="20.00";
await submit();
const newPrepare=writes.filter(([path])=>path==="/employee/prepare").at(-1)[1];
assert.equal(newPrepare.previous_request_id,oldRequestId);
assert.equal(newPrepare.amount,"20.00");
assert.deepEqual(newPrepare.files.map(file=>file.file_name),["2.pdf","3.pdf"]);
assert.notEqual(request.request_id,oldRequestId);
assert.equal($("confirmContent").checked,false);
assert.equal($("editManual").hidden,false);
assert.equal(writes.filter(([path])=>path==="/employee/submit").length,0);
// 后台代录的正式单据按报销ID打开，不能误走申请确认入口。
const before = writes.length;
run('records=[{request_id:null,reimbursement_id:"admin-receipt",subject:"后台代录报销",amount:"1351.19",occurred_on:"2026-10-19",status:"posted"}];renderRecords();');
await $("history").children[0].onclick();
assert.equal(reads.at(-1), "/employee/reimbursements/admin-receipt");
assert.equal(urls.at(-1), "/?reimbursement_id=admin-receipt");
assert.equal($("detailSubject").textContent, "后台代录报销");
assert.equal($("detailAmount").textContent, "1,351.19");
assert.equal($("expenseStatus").textContent, "已入账");
assert.equal($("confirmArea").hidden, true);
assert.equal($("editManual").hidden, true);
assert.equal(writes.length, before);
// 从正式报销返回待确认申请，恢复申请详情和原确认操作。
run('records=[{request_id:"request-next",reimbursement_id:null,subject:"新申请",amount:"20.00",occurred_on:"2026-10-26",status:"awaiting_confirmation"}];renderRecords();');
await $("history").children[0].onclick();
assert.equal(reads.at(-1), "/employee/requests/request-next");
assert.equal(urls.at(-1), "/?request_id=request-next");
assert.equal($("confirmArea").hidden, false);
const originalFetch = context.fetch;
context.fetch = async (path, options) => {
  if (path === "/employee/session/refresh") return { ok: true, json: async () => ({ access_token: "restored" }) };
  if (path === "/api/auth/me") {
    assert.equal(options.headers.Authorization, "Bearer restored");
    return { ok: true, json: async () => ({ display_name: "已登录员工" }) };
  }
  return originalFetch(path, options);
};
run('access=""; requestId="request-a"; reimbursementId=null;');
await run("restoreLogin()");
assert.equal($("loginView").hidden, true);
assert.equal($("identity").textContent, "已登录员工");
assert.equal(reads.at(-1), "/employee/requests/request-a");
console.log("portal UI: readonly review, versioned manual editing, confirmation, interrupted upload retry and session recovery passed");
