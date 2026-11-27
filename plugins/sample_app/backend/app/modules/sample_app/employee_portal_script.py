"""员工门户交互：正常账号鉴权、本人记录、原件直传与人工确认。"""
BOOTSTRAP = r'''
"use strict";
const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
let requestId = params.get("request_id");
let reimbursementId = requestId ? null : params.get("reimbursement_id");
let softwareClaimId = params.get("software_claim_id");
const browserCode = params.get("browser_code");
let access = "", captchaId = "", current = null, softwareCurrent = null, busy = false, connectionInfo = null;
let records = [], softwareRecords = [], recordFilter = "all", composeAttempt = null, accountName = "本人";
let expensePage = 1, expensePageSize = 20, expenseTotal = 0;
let softwarePage = 1, softwarePageSize = 20, softwareTotal = 0;
let draftFiles = [], draftRequestId = null, editingPreviousRequestId = null;
const states = {
 awaiting_confirmation:["待确认","pending"], approved:["待提交","pending"],
 submitted:["处理中","processing"], draft:["草稿","pending"],
 posted:["已入账","posted"], rejected:["已驳回","rejected"],
 cancelled:["已撤销",""], voided:["已作废",""], expired:["已过期",""],
 preparing:["准备中","pending"], ready:["待核对","pending"],
 applied:["已写入工资","posted"], superseded:["已失效",""], legacy:["需重新准备",""]
};
const softwareStates = {ready:["待核对","pending"], approved:["已确认","posted"], applied:["已写入工资","posted"], preparing:["准备中","pending"], superseded:["已失效",""]};
const sourceLabels = {wechat:"微信",alipay:"支付宝",bank_card:"信用卡",invoice:"Invoice"};
function statusInfo(status) { return states[status] || ["处理中","processing"]; }
function softwareStatusInfo(status) { return softwareStates[status] || statusInfo(status); }
function money(value) {
 const [integer,fraction=""]=String(value ?? "0").split(".");
 return integer.replace(/\B(?=(\d{3})+(?!\d))/g,",")+"."+fraction.padEnd(2,"0").slice(0,2);
}
function fileSize(bytes) { return bytes >= 1048576 ? (bytes/1048576).toFixed(1)+" MB" : Math.max(1,Math.ceil((bytes||0)/1024))+" KB"; }
function message(text, success=false) {
 $("message").textContent=text; $("message").hidden=!text;
 $("message").classList.toggle("success",success);
}
function element(tag, className, text) {
 const node=document.createElement(tag); if(className) node.className=className;
 if(text !== undefined) node.textContent=text; return node;
}
function showView(name) {
 for(const view of ["home","compose","expense","software","pairing","connection","account"]) $(view).hidden=view!==name;
 $("navHome").classList.toggle("active",!["connection","account"].includes(name));
 $("navConnection").classList.toggle("active",name==="connection");
 message(""); window.scrollTo({top:0,behavior:"instant"});
}
function withSessionLock(callback) {
 return globalThis.navigator?.locks ? navigator.locks.request("kuaihe-employee-session",callback) : callback();
}
async function renewSession() {
 const session=await withSessionLock(()=>api("/employee/session/refresh",{},false));
 access=session.access_token;
}
async function api(path, data, auth=true, retry=true) {
 const result=await fetch(path,{method:data===undefined?"GET":"POST",
  headers:{"Content-Type":"application/json",...(auth && access?{Authorization:"Bearer "+access}:{})},
  ...(data===undefined?{}:{body:JSON.stringify(data)})});
 let payload;
 try { payload=await result.json(); } catch { throw new Error("服务暂时无法响应，请稍后重试。"); }
 if(!result.ok || (payload.code!==undefined && payload.code!==0)) {
  if(result.status===401 && auth && retry && access && data===undefined) {
   let renewed=false;
   try { await renewSession(); renewed=true; } catch { /* 进入原有登录失效处理 */ }
   if(renewed) return api(path,data,auth,false);
  }
  if(result.status===401 && auth) { access=""; $("loggedIn").hidden=true; $("loginView").hidden=false; $("navigation").hidden=true; $("accountArea").hidden=true; $("credential").value=""; await captcha(); }
  throw new Error(payload.message || (typeof payload.detail==="string"?payload.detail:"操作失败，请检查信息或联系管理员。"));
 }
 return payload.code===undefined?payload:payload.data;
}
async function action(fn) {
 if(busy) return; busy=true; message("");
 document.querySelectorAll("button").forEach(button=>button.disabled=true);
 document.querySelectorAll("form input").forEach(input=>input.disabled=true);
 renderState();
 try { await fn(); } catch(error) { message(error.message || "操作失败，请稍后重试。"); }
 finally {
  busy=false; document.querySelectorAll("button").forEach(button=>button.disabled=false);
  document.querySelectorAll("form input").forEach(input=>input.disabled=false); renderState();
 }
}
function renderSoftwareState() {
 const attachments=softwareCurrent?.attachments || [];
 const status=softwareCurrent?.status;
 const done=["approved","applied"].includes(status);
 const inactive=status==="superseded";
 const ready=status==="ready";
 const expired=!!softwareCurrent && !done && new Date(softwareCurrent.expires_at).getTime()<=Date.now();
 $("softwareConfirmArea").hidden=done || expired || inactive || !ready;
 $("softwareApprove").disabled=busy || !ready || !softwareCurrent || !attachments.length || !$("softwareConfirmContent").checked || expired || inactive;
 $("softwareConfirmContent").disabled=busy || done || inactive || !ready;
 $("softwareDoneNotice").hidden=!done && !expired && !inactive;
 if(done) {
  $("softwareDoneTitle").textContent=status==="applied"?"已写入工资":"已确认";
  $("softwareDoneDescription").textContent=status==="applied"
   ?"软件报销已写入当月工资单。封账前管理员重新核算也会保留该金额。"
   :"已确认。若当月工资尚未核算，核算时会自动带入；已有草稿工资单则已立即写入。";
 } else if(inactive) {
  $("softwareDoneTitle").textContent="申请已失效";
  $("softwareDoneDescription").textContent="请让 AI 使用新的幂等标识重新准备。";
 } else if(expired) {
  $("softwareDoneTitle").textContent="申请已过期";
  $("softwareDoneDescription").textContent="请让 AI 重新发起软件报销。";
 }
}
function renderState() {
 $("copyUrl").disabled=busy || !connectionInfo; $("copyConfig").disabled=busy || !connectionInfo;
 renderSoftwareState();
 const attachments=current?.attachments || [], submitted=!!current?.reimbursement_id;
 const inactive=!submitted && ["superseded","legacy"].includes(current?.request_status);
 const ready=["ready","approved"].includes(current?.request_status);
 const expired=!!current && !submitted && new Date(current.expires_at).getTime()<=Date.now();
 $("confirmArea").hidden=submitted || expired || inactive || !ready;
 $("approve").disabled=busy || !ready || !current || !attachments.length || !$("confirmContent").checked || expired || inactive || submitted;
 $("confirmContent").disabled=busy || submitted || inactive || !ready;
 $("approve").textContent=current?.approved?"继续提交报销":"确认并提交报销";
 $("editManual").hidden=!current || submitted || current.source!=="manual";
 $("copyAiRevision").hidden=!current || submitted || current.source!=="mcp" || inactive;
 $("reviewNote").textContent=inactive?"旧申请已失效或需要重新准备，不能继续上传、确认或提交。":!ready && !submitted?"原定清单尚未全部上传，请在原填写流程或 AI 中继续准备；此页不提供追加附件。":current?.source==="manual"?"此页仅核对。若发票、金额、事由或日期有误，请返回填写页整体修改，并重新确认。":"此页仅核对。若内容有误，请让 AI 整体重新准备，替换本次申请。";
 $("submittedNotice").hidden=!submitted && !expired && !inactive;
 if(submitted) {
  $("submittedTitle").textContent=statusInfo(current.status)[0];
  $("submittedDescription").textContent=current.status==="posted"?"本次报销已入账。如有疑问，请联系管理员。":"报销单已生成，请等待管理员处理，无需重复提交。";
  if(current.status==="rejected") $("submittedDescription").textContent="本次报销已驳回，请联系管理员确认处理方式。";
  if(current.status==="draft") $("submittedDescription").textContent="这是一份正式报销草稿，请联系管理员核对和处理。";
  if(["cancelled","voided"].includes(current.status)) $("submittedDescription").textContent="本次报销已结束，无需再次提交。";
 } else if(inactive) {
  $("submittedTitle").textContent=statusInfo(current.request_status)[0];
  $("submittedDescription").textContent="本申请不能继续提交，请使用重新准备后的新申请。";
 } else if(expired) {
  $("submittedTitle").textContent="本次申请已过期";
  $("submittedDescription").textContent="请重新创建报销；若由 AI 整理，请让 AI 重新发起申请。";
 }
}
async function captcha() {
 const result=await api("/api/auth/captcha",undefined,false); captchaId=result.captcha_id; $("captchaImage").src=result.image;
}
async function loadConnection() {
 connectionInfo=await api("/employee/connection",undefined,false); $("mcpUrl").value=connectionInfo.mcp_url; renderState();
}
async function copyText(text) {
 if(!navigator.clipboard) throw new Error("浏览器不支持自动复制，请手动选择文本复制。");
 await navigator.clipboard.writeText(text);
}
function fileRow(file, preview=false) {
 const li=element("li","file-row"), icon=element("span","file-icon",file.content_type==="application/pdf"?"PDF":"图片");
 const info=element("div","file-name"); info.append(element("span","",file.file_name),element("span","file-size",fileSize(file.file_size)));
 li.append(icon,info);
 if(preview) {
  const button=element("button","text-button file-preview","查看原件 ↗"); button.type="button";
  button.onclick=()=>action(async()=>{
   // 先打开空白页以保留用户点击手势，随后鉴权获取短时链接。
   const tab=window.open("about:blank","_blank"); if(tab) tab.opener=null;
   try {
    const item=await api("/api/files/"+encodeURIComponent(file.id)+"/url");
    const url=new URL(item.url,location.href);
    if(!["https:","http:"].includes(url.protocol)) throw new Error("文件地址无效。");
    if(tab) tab.location.replace(url.href); else throw new Error("请允许浏览器打开文件预览窗口后重试。");
   } catch(error) { if(tab) tab.close(); throw error; }
  }); li.append(button);
 }
 return li;
}
function renderRecords() {
 $("history").replaceChildren();
 const filtered=records.filter(row=>recordFilter==="all" ||
  (recordFilter==="pending" && ["awaiting_confirmation","approved","draft","preparing"].includes(row.status)) ||
  (recordFilter==="processing" && row.status==="submitted") || (recordFilter==="posted" && row.status==="posted"));
 $("historyEmpty").hidden=filtered.length>0;
 $("historyEmpty").textContent=records.length?"当前筛选下没有报销记录。":"还没有报销记录，点击“新建报销”开始提交。";
 for(const row of filtered) {
  const button=element("button","record-row"); button.type="button";
  const info=element("span","record-main"), [label,tone]=statusInfo(row.status);
  info.append(element("span","record-subject",row.subject),element("span","record-date",row.occurred_on));
  button.append(info,element("span","record-amount","¥"+money(row.amount)),element("span","status-pill "+tone,label),element("span","chevron","›"));
  button.onclick=()=>action(async()=>{reimbursementId=row.reimbursement_id || null;requestId=reimbursementId?null:row.request_id;softwareClaimId=null;current=null;$("confirmContent").checked=false;showView("expense");await refresh();updateRequestUrl();});
  $("history").append(button);
 }
}
function renderSoftwareRecords() {
 $("softwareHistory").replaceChildren();
 $("softwareHistoryEmpty").hidden=softwareRecords.length>0;
 for(const row of softwareRecords) {
  const button=element("button","record-row"); button.type="button";
  const info=element("span","record-main"), [label,tone]=softwareStatusInfo(row.status);
  info.append(element("span","record-subject",row.period_month+" 软件报销"),
              element("span","record-date","计入工资 ¥"+money(row.applied_amount)));
  button.append(info,element("span","record-amount","¥"+money(row.claimed_amount)),element("span","status-pill "+tone,label),element("span","chevron","›"));
  button.onclick=()=>action(async()=>{softwareClaimId=row.claim_id;requestId=null;reimbursementId=null;softwareCurrent=null;showView("software");await refreshSoftware();updateRequestUrl();});
  $("softwareHistory").append(button);
 }
 const pages=Math.max(1, Math.ceil(softwareTotal/softwarePageSize));
 $("softwarePager").hidden=softwareTotal<=softwarePageSize;
 $("softwarePageLabel").textContent=`第 ${softwarePage}/${pages} 页 · 共 ${softwareTotal} 条`;
 $("softwarePrev").disabled=softwarePage<=1;
 $("softwareNext").disabled=softwarePage>=pages;
}
function renderExpensePager() {
 const pages=Math.max(1, Math.ceil(expenseTotal/expensePageSize));
 $("expensePager").hidden=expenseTotal<=expensePageSize && expensePage===1;
 $("expensePageLabel").textContent=`第 ${expensePage}/${pages} 页 · 正式单据 ${expenseTotal} 条`;
 $("expensePrev").disabled=expensePage<=1;
 $("expenseNext").disabled=expensePage>=pages;
}
async function loadHome() {
 const [data, software]=await Promise.all([
  api("/employee/requests?page="+expensePage+"&page_size="+expensePageSize),
  api("/employee/software-claims?page="+softwarePage+"&page_size="+softwarePageSize)]);
 records=data.items; softwareRecords=software.items || [];
 expenseTotal=data.total || 0; expensePage=data.page || expensePage; expensePageSize=data.page_size || expensePageSize;
 softwareTotal=software.total || 0; softwarePage=software.page || softwarePage; softwarePageSize=software.page_size || softwarePageSize;
 $("homeIdentity").textContent=data.employee_name+" · "+data.org_name;
 renderRecords(); renderExpensePager(); renderSoftwareRecords();
}
function updateRequestUrl() {
 const url=new URL(location.href); url.search="";
 if(softwareClaimId) url.searchParams.set("software_claim_id",softwareClaimId);
 else if(requestId) url.searchParams.set("request_id",requestId);
 else if(reimbursementId) url.searchParams.set("reimbursement_id",reimbursementId);
 history.replaceState(null,"",url.pathname+url.search);
}
async function goHome() { requestId=null;reimbursementId=null;softwareClaimId=null;current=null;softwareCurrent=null;updateRequestUrl();showView("home");await loadHome(); }
async function refreshSoftware() {
 if(!softwareClaimId) return;
 softwareCurrent=null;renderState();
 softwareCurrent=await api("/employee/software-claims/"+encodeURIComponent(softwareClaimId));
 $("softwareApplied").textContent=money(softwareCurrent.applied_amount);
 $("softwareClaimed").textContent="¥"+money(softwareCurrent.claimed_amount);
 $("softwareMonth").textContent=softwareCurrent.period_month;
 $("softwareEmployee").textContent=softwareCurrent.employee_name || accountName;
 $("softwareOrg").textContent=softwareCurrent.org_name || "本人关联企业";
 const [label,tone]=softwareStatusInfo(softwareCurrent.status);
 $("softwareStatus").textContent=label; $("softwareStatus").className="status-pill "+tone;
 $("softwareTitle").textContent=["approved","applied"].includes(softwareCurrent.status)?"软件报销详情":"核对软件报销";
 $("softwareItems").replaceChildren();
 for(const item of softwareCurrent.items || []) {
  const row=element("li","file-row");
  row.append(element("div","file-name",`${item.occurred_on} · ${item.merchant_name}`));
  row.append(element("div","small muted",`${sourceLabels[item.source_code]||item.source_code} · ¥${money(item.amount)}`));
  $("softwareItems").append(row);
 }
 $("softwareFiles").replaceChildren();
 for(const file of softwareCurrent.attachments || []) $("softwareFiles").append(fileRow(file,true));
 $("softwareAttachmentCount").textContent=String((softwareCurrent.attachments || []).length);
 $("softwareFilesEmpty").hidden=!!softwareCurrent.attachments?.length;
 renderState();
}
async function refresh() {
 if(!requestId && !reimbursementId) return;
 const previous=current;
 current=null;renderState();
 if(previous?.request_id!==requestId || previous?.reimbursement_id!==reimbursementId) {
  for(const id of ["detailAmount","detailSubject","detailEmployee","detailDate","detailOrg"]) $(id).textContent="—";
  $("files").replaceChildren();$("attachmentCount").textContent="正在读取…";
  $("receiptNumber").hidden=true;$("expenseStatus").textContent="正在读取";
 }
 current=await api(reimbursementId?"/employee/reimbursements/"+encodeURIComponent(reimbursementId):"/employee/requests/"+encodeURIComponent(requestId));
 const contents=value=>JSON.stringify([value?.request_id,value?.subject,value?.amount,value?.occurred_on,(value?.attachments||[]).map(file=>file.id)]);
 if(contents(previous)!==contents(current)) $("confirmContent").checked=false;
 $("detailAmount").textContent=money(current.amount); $("detailSubject").textContent=current.subject;
 $("detailEmployee").textContent=current.employee_name || accountName;
 $("detailDate").textContent=current.occurred_on; $("detailOrg").textContent=current.org_name || "本人关联企业";
 const submitted=!!current.reimbursement_id, [label,tone]=statusInfo(current.status);
 $("expenseTitle").textContent=submitted?"报销详情":"核对报销";
 $("expenseSubtitle").textContent=submitted?"查看报销单的当前状态与发票原件。":"提交前，请核对费用信息和全部发票原件。";
 $("expenseStatus").textContent=label; $("expenseStatus").className="status-pill "+tone;
 $("receiptNumber").hidden=!submitted; $("detailNumber").textContent=current.reimbursement_id || "";
 $("files").replaceChildren(); for(const file of current.attachments || []) $("files").append(fileRow(file,true));
 $("attachmentCount").textContent=(current.attachments || []).length+" / 50";
 $("filesEmpty").hidden=!!current.attachments?.length;
 $("stepConfirm").classList.toggle("done",submitted);
 $("stepConfirm").classList.toggle("current",!submitted);
 $("stepProcess").classList.toggle("done",current.status==="posted");
 $("stepProcess").classList.toggle("current",current.status==="submitted");
 $("stepPosted").classList.toggle("done",current.status==="posted"); renderState();
}
function selectedFiles() {
 const files=draftFiles; if(!files.length) throw new Error("请先选择本次全部发票原件。");
 if(files.length>50) throw new Error("每单最多 50 份发票。");
 const types={pdf:"application/pdf",jpg:"image/jpeg",jpeg:"image/jpeg",png:"image/png",webp:"image/webp"};
 return files.map(file=>{
  const contentType=types[file.name.split(".").pop().toLowerCase()];
  if(!contentType || !file.size || file.size>20*1024*1024) throw new Error("发票须为20MB以内的 PDF、JPG、PNG 或 WebP。");
  return {file,contentType};
 });
}
async function uploadInvoices(selected,id,progress,skip=new Set()) {
 let index=0;
 for(const {file,contentType} of selected) {
  index++; const bytes=await file.arrayBuffer(), digest=md5base64(bytes);
  if(!selected[index-1].description || selected[index-1].description.content_md5!==digest) throw new Error("原件与本次预定清单不一致，请整体重新准备。");
  if(skip.has(digest)) continue;
  $(progress).textContent=`正在上传第 ${index} / ${selected.length} 份发票…`;
  const response=await api("/employee/upload-tickets",{request_id:id,files:[{file_name:file.name,content_type:contentType,file_size:file.size,content_md5:digest}]});
  const ticket=response.tickets[0];
  let uploaded;
  try { uploaded=await fetch(ticket.upload.url,{method:ticket.upload.method,headers:ticket.upload.headers,body:bytes}); }
  catch { throw new Error("发票上传连接失败，请检查网络或联系管理员检查文件存储跨域配置。"); }
  if(!uploaded.ok) throw new Error("发票上传失败，请稍后使用相同内容重试。");
  await api("/employee/complete-upload",{request_id:id,file_id:ticket.id}); skip.add(digest);
 }
 $(progress).textContent="发票上传完成。";
}
function renderDraftFiles() {
 $("composeFileList").replaceChildren();
 draftFiles.forEach((file,index)=>{
  const row=fileRow({file_name:file.name,file_size:file.size,content_type:file.type});
  const remove=element("button","text-button","移除");remove.type="button";
  remove.onclick=()=>{if(busy)return;draftFiles.splice(index,1);renderDraftFiles();};
  row.append(remove);$("composeFileList").append(row);
 });
}
'''

HANDLERS = r'''
async function enterPortal(user) {
 accountName=user.display_name || "本人";
 $("identity").textContent=accountName;
 $("loginView").hidden=true;$("loggedIn").hidden=false;$("navigation").hidden=false;$("accountArea").hidden=false;
 if(softwareClaimId) {showView("software");await refreshSoftware();}
 else if(requestId || reimbursementId) {showView("expense");await refresh();}
 else if(browserCode) showView("pairing");
 else {showView("home");await loadHome();}
}
$("loginForm").onsubmit=event=>{event.preventDefault();action(async()=>{
 try {
  const result=await withSessionLock(()=>api("/employee/session/login",{login_name:$("loginName").value,password:$("password").value,captcha_id:captchaId,captcha_code:$("captchaCode").value,remember_me:false},false));
  access=result.session.access_token;
  $("password").value="";$("captchaCode").value="";
  await enterPortal(result.user);
 } catch(error) {if(!access) await captcha();throw error;}
});};
$("captchaRefresh").onclick=()=>action(captcha);
$("logout").onclick=()=>action(async()=>{
 await withSessionLock(()=>api("/employee/session/logout",{},false));
 access="";$("credential").value="";location.reload();
});
$("navHome").onclick=()=>action(goHome);$("backFromCompose").onclick=()=>action(goHome);$("backFromExpense").onclick=()=>action(goHome);$("backFromSoftware").onclick=()=>action(goHome);$("backFromAccount").onclick=()=>action(goHome);
$("openAccount").onclick=()=>{ $("passwordForm").reset(); showView("account"); };
$("softwareRefresh").onclick=()=>action(refreshSoftware);
$("softwareConfirmContent").onchange=renderState;
$("softwareApprove").onclick=()=>action(async()=>{
 if(!softwareCurrent?.attachments?.length || softwareCurrent.status!=="ready" || !$("softwareConfirmContent").checked) throw new Error("请先核对完整申请并勾选确认。");
 await api("/employee/software-claims/approve",{request_id:softwareClaimId});
 await refreshSoftware();
 message("软件报销已确认。",true);
});
for(const id of ["navConnection","openConnection"]) $(id).onclick=()=>action(async()=>{showView("connection");await loadConnection();});
$("reloadHistory").onclick=()=>action(loadHome);
$("reloadSoftwareHistory").onclick=()=>action(loadHome);
$("expensePrev").onclick=()=>action(async()=>{ if(expensePage>1){ expensePage-=1; await loadHome(); }});
$("expenseNext").onclick=()=>action(async()=>{ if(expensePage*expensePageSize<expenseTotal){ expensePage+=1; await loadHome(); }});
$("softwarePrev").onclick=()=>action(async()=>{ if(softwarePage>1){ softwarePage-=1; await loadHome(); }});
$("softwareNext").onclick=()=>action(async()=>{ if(softwarePage*softwarePageSize<softwareTotal){ softwarePage+=1; await loadHome(); }});
$("passwordForm").onsubmit=event=>{event.preventDefault();action(async()=>{
 const current_password=$("currentPassword").value, new_password=$("newPassword").value, confirm_password=$("confirmPassword").value;
 if(new_password!==confirm_password) throw new Error("两次输入的新密码不一致。");
 const result=await api("/employee/session/change-password",{current_password,new_password,confirm_password});
 access=""; $("passwordForm").reset();
 message(result.message || "密码已更新，请重新登录。",true);
 await withSessionLock(()=>api("/employee/session/logout",{},false).catch(()=>null));
 setTimeout(()=>location.reload(), 800);
});};
document.querySelectorAll("[data-filter]").forEach(button=>button.onclick=()=>{
 recordFilter=button.dataset.filter;document.querySelectorAll("[data-filter]").forEach(item=>item.classList.toggle("active",item===button));renderRecords();
});
$("newExpense").onclick=()=>{
 if(draftRequestId || editingPreviousRequestId) {
  $("expenseForm").reset();draftFiles=[];renderDraftFiles();
  draftRequestId=null;editingPreviousRequestId=null;composeAttempt=null;
 }
 showView("compose");
};
$("composeFiles").onchange=()=>{
 if(busy)return;
 const next=[...draftFiles];
 for(const file of $("composeFiles").files) {
  if(!next.some(old=>old.name===file.name && old.size===file.size && old.lastModified===file.lastModified)) next.push(file);
 }
 if(next.length>50) {message("每单最多50份发票，请先移除不需要的原件。");$("composeFiles").value="";return;}
 draftFiles=next;$("composeFiles").value="";renderDraftFiles();
};
$("expenseForm").onsubmit=event=>{event.preventDefault();action(async()=>{
 const selected=selectedFiles(),subject=$("expenseSubject").value.trim(),amount=$("expenseAmount").value,occurred_on=$("expenseDate").value;
 if(!subject || !amount || !occurred_on) throw new Error("请填写报销事由、金额和费用发生日期。");
 const descriptions=[];
 for(const item of selected) {
  $("composeProgress").textContent="正在核对完整发票清单…";
  item.description={file_name:item.file.name,content_type:item.contentType,file_size:item.file.size,content_md5:md5base64(await item.file.arrayBuffer())};
  descriptions.push(item.description);
 }
 if(new Set(descriptions.map(item=>item.content_md5)).size!==descriptions.length) throw new Error("同一份发票文件不能重复提交，请在填写页移除重复原件。");
 let signature=JSON.stringify({subject,amount,occurred_on,files:descriptions,previous_request_id:editingPreviousRequestId});
 if(composeAttempt && composeAttempt.signature!==signature && composeAttempt.id) {
  await api("/employee/revise",{request_id:composeAttempt.id});
  editingPreviousRequestId=composeAttempt.id;composeAttempt=null;
  signature=JSON.stringify({subject,amount,occurred_on,files:descriptions,previous_request_id:editingPreviousRequestId});
 }
 if(!composeAttempt) composeAttempt={signature,key:crypto.randomUUID(),id:null,uploaded:new Set()};
 if(composeAttempt.signature!==signature) composeAttempt={signature,key:crypto.randomUUID(),id:null,uploaded:new Set()};
 if(!composeAttempt.id) {
  const result=await api("/employee/prepare",{request_key:composeAttempt.key,subject,amount,occurred_on,files:descriptions,previous_request_id:editingPreviousRequestId});
  if(!result.request_id) throw new Error(result.question || "请补全报销信息。");
  composeAttempt.id=result.request_id;
 }
 const saved=await api("/employee/requests/"+encodeURIComponent(composeAttempt.id));
 for(const file of saved.attachments || []) composeAttempt.uploaded.add(file.content_md5);
 if(saved.approved || saved.reimbursement_id) {
  requestId=composeAttempt.id;reimbursementId=null;current=null;showView("expense");updateRequestUrl();await refresh();return;
 }
 await uploadInvoices(selected,composeAttempt.id,"composeProgress",composeAttempt.uploaded);
 requestId=composeAttempt.id;reimbursementId=null;draftRequestId=requestId;current=null;$("confirmContent").checked=false;
 showView("expense");updateRequestUrl();await refresh();
 composeAttempt=null;editingPreviousRequestId=null;
});};
$("editManual").onclick=()=>action(async()=>{
 if(!current || current.source!=="manual" || current.reimbursement_id) throw new Error("这份申请不能在员工端直接修改。");
 const original=current;
 await api("/employee/revise",{request_id:original.request_id});
 if(draftRequestId!==original.request_id) {draftFiles=[];renderDraftFiles();}
 $("expenseSubject").value=original.subject;$("expenseAmount").value=original.amount;$("expenseDate").value=original.occurred_on;
 editingPreviousRequestId=original.request_id;composeAttempt=null;requestId=null;current=null;
 updateRequestUrl();showView("compose");$("confirmContent").checked=false;
 $("composeProgress").textContent=draftFiles.length?"旧申请已失效。请整体核对事由、金额、日期及全部发票，再进入新的核对页。":"旧申请已失效。请重新选择本次全部发票，并核对金额、事由和日期。";
});
$("copyAiRevision").onclick=()=>action(async()=>{
 if(!current || current.source!=="mcp" || current.reimbursement_id)return;
 await copyText(`请帮我整体重新准备报销，替换原申请 ${current.request_id}。先询问我需要调整的事由、金额、费用日期或发票，确定完整原件清单后再生成新申请，并使原申请失效。`);
 message("修改提示已复制，请交给 AI 并说明要修改的内容。",true);
});
$("confirmContent").onchange=renderState;
$("refresh").onclick=()=>action(refresh);
$("approve").onclick=()=>action(async()=>{
 if(!current?.attachments?.length || !["ready","approved"].includes(current.request_status) || !$("confirmContent").checked) throw new Error("请先核对完整申请并勾选确认。");
 if(!current.approved) await api("/employee/approve",{request_id:requestId});
 // 保留原有服务端幂等机制；网络中断后同一申请重试不会重复生成单据。
 await api("/employee/submit",{request_id:requestId});await refresh();
 message("报销已提交，请等待管理员处理。",true);
});
$("pair").onclick=()=>action(async()=>{
 await api("/employee/pair",{browser_code:browserCode});$("pair").hidden=true;
 $("pairResult").hidden=false;$("pairResult").textContent="已授权，请回到 AI 使用相同报销标识继续。此页面可以关闭。";
});
$("copyUrl").onclick=()=>action(async()=>{if(!connectionInfo)return;await copyText(connectionInfo.mcp_url);message("服务地址已复制。",true);});
$("copyConfig").onclick=()=>action(async()=>{if(!connectionInfo)return;await copyText(JSON.stringify({mcpServers:{kuaihe_employee:{type:"http",url:connectionInfo.mcp_url,headers:{Authorization:"Bearer <短期凭证>"}}}},null,2));message("已复制通用配置示例，请按客户端要求调整并替换凭证占位符。",true);});
$("issue").onclick=()=>action(async()=>{
 $("credential").value="";$("credential").hidden=true;$("copyToken").hidden=true;$("endpoint").textContent="";
 const result=await api("/employee/token",{});$("endpoint").textContent="凭证到期时间："+new Date(Date.now()+result.expires_in*1000).toLocaleString()+"（"+Math.floor(result.expires_in/86400)+" 天）";
 $("credential").value=result.access_token;$("credential").hidden=false;$("copyToken").hidden=false;
});
$("copyToken").onclick=()=>action(async()=>{await copyText($("credential").value);message("凭证已复制，请仅填入客户端的认证配置。",true);});
async function restoreLogin() {
 try { await renewSession(); }
 catch { await captcha(); return; }
 await enterPortal(await api("/api/auth/me"));
}
restoreLogin().catch(error=>message(error.message));
'''
