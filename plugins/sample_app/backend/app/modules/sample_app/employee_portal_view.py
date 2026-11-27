"""员工自助门户结构；仅由独立员工服务提供，不进入管理端。"""
HTML = r'''
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>快盒 · 员工服务</title>
    <link rel="stylesheet" href="/portal.css" />
  </head>
  <body>
    <header class="topbar">
      <div class="topbar-inner">
        <a class="brand" href="/" aria-label="快盒员工服务首页"
          ><svg viewBox="0 0 32 32" aria-hidden="true">
            <path
              d="M16 2 29 9v14l-13 7L3 23V9Z M3 9l13 7 13-7 M16 16v14 M10 6l13 7v7"
            /></svg
          ><span>快盒<span class="brand-divider">·</span>员工服务</span></a
        >
        <nav id="navigation" hidden aria-label="主导航">
          <button id="navHome" class="nav-button active" type="button">
            我的事务</button
          ><button id="navConnection" class="nav-button" type="button">
            AI 连接
          </button>
        </nav>
        <div id="accountArea" class="account-area" hidden>
          <span class="avatar" aria-hidden="true">人</span
          ><span id="identity"></span
          ><button id="openAccount" class="text-button" type="button">修改密码</button
          ><button id="logout" class="text-button" type="button">退出</button>
        </div>
      </div>
    </header>
    <main>
      <div
        id="message"
        class="feedback"
        role="status"
        aria-live="polite"
        hidden
      ></div>
      <div id="loginView" class="login-layout">
        <section class="card login-card">
          <h2>登录员工服务</h2>
          <p class="muted">使用管理员为你开通的系统账号。</p>
          <form id="loginForm">
            <label for="loginName">账号</label
            ><input
              id="loginName"
              autocomplete="username"
              placeholder="请输入登录账号"
              required
              maxlength="128"
            />
            <label for="password">密码</label
            ><input
              id="password"
              type="password"
              autocomplete="current-password"
              placeholder="请输入密码"
              required
            />
            <label for="captchaCode">验证码</label>
            <div class="captcha-row">
              <input
                id="captchaCode"
                autocomplete="off"
                placeholder="请输入验证码"
                required
                maxlength="16"
              /><button
                id="captchaRefresh"
                type="button"
                class="captcha-button"
                aria-label="刷新验证码"
              >
                <img id="captchaImage" alt="验证码，点击刷新" />
              </button>
            </div>
            <button id="loginButton" class="primary full-width" type="submit">
              登录
            </button>
            <p class="small muted">
              账号未关联员工？请联系管理员在“内部员工”中维护。
            </p>
          </form>
        </section>
      </div>
      <div id="loggedIn" hidden>
        <section id="home" hidden>
          <div class="page-heading">
            <div>
              <h1>我的事务</h1>
              <p class="muted">
                费用报销与软件报销。<span
                  id="homeIdentity"
                  class="inline-meta"
                ></span>
              </p>
            </div>
            <button id="newExpense" class="primary" type="button">
              <span aria-hidden="true">＋</span> 新建报销
            </button>
          </div>
          <div class="workspace">
            <div class="home-stacks">
              <section class="card records-card">
                <div class="card-heading">
                  <div>
                    <h2>费用报销</h2>
                    <p class="small muted">最近 50 条本人报销及待提交申请</p>
                  </div>
                  <button id="reloadHistory" class="text-button" type="button">
                    刷新 ↻
                  </button>
                </div>
                <div
                  class="record-filters"
                  role="group"
                  aria-label="报销状态筛选"
                >
                  <button
                    class="filter-button active"
                    data-filter="all"
                    type="button"
                  >
                    全部</button
                  ><button
                    class="filter-button"
                    data-filter="pending"
                    type="button"
                  >
                    待确认</button
                  ><button
                    class="filter-button"
                    data-filter="processing"
                    type="button"
                  >
                    处理中</button
                  ><button
                    class="filter-button"
                    data-filter="posted"
                    type="button"
                  >
                    已入账
                  </button>
                </div>
                <div id="history" aria-live="polite"></div>
                <p id="historyEmpty" class="empty-state" hidden>
                  还没有报销记录<br /><span class="small"
                    >点击“新建报销”，或连接 AI 帮你整理发票。</span
                  >
                </p>
                <div id="expensePager" class="pager" hidden>
                  <button id="expensePrev" type="button" class="outline">上一页</button>
                  <span id="expensePageLabel" class="small muted"></span>
                  <button id="expenseNext" type="button" class="outline">下一页</button>
                </div>
              </section>
              <section class="card records-card">
                <div class="card-heading">
                  <div>
                    <h2>软件报销</h2>
                    <p class="small muted">
                      Codex / Cursor 等订阅费；由 AI 提交后本人确认
                    </p>
                  </div>
                  <button
                    id="reloadSoftwareHistory"
                    class="text-button"
                    type="button"
                  >
                    刷新 ↻
                  </button>
                </div>
                <div id="softwareHistory" aria-live="polite"></div>
                <p id="softwareHistoryEmpty" class="empty-state" hidden>
                  还没有软件报销<br /><span class="small"
                    >连接 AI 助手上传扣款截图或 invoice 后，会出现在这里。</span
                  >
                </p>
                <div id="softwarePager" class="pager" hidden>
                  <button id="softwarePrev" type="button" class="outline">上一页</button>
                  <span id="softwarePageLabel" class="small muted"></span>
                  <button id="softwareNext" type="button" class="outline">下一页</button>
                </div>
              </section>
            </div>
            <aside>
              <section class="card ai-card">
                <span class="line-illustration" aria-hidden="true">↗</span>
                <h2>也可以让 AI 帮你提交</h2>
                <ol class="steps">
                  <li>把发票或扣款截图交给 AI</li>
                  <li>说明报销事由、金额或所属工资月</li>
                  <li>本人核对后确认提交</li>
                </ol>
                <button
                  id="openConnection"
                  class="outline full-width"
                  type="button"
                >
                  连接 AI 助手
                </button>
                <p class="small muted">仅可提交和查看本人费用与软件报销。</p>
              </section>
              <section class="notice">
                <h3>提交前请核对</h3>
                <p>
                  费用报销：发票、金额和事由应一致。<br />软件报销：确认后写入工资「软件报销」。
                </p>
              </section>
            </aside>
          </div>
        </section>
        <section id="account" hidden>
          <div class="page-heading">
            <div>
              <button id="backFromAccount" class="back-button" type="button">
                ← 我的事务
              </button>
              <h1>修改密码</h1>
              <p class="muted">修改后需使用新密码重新登录；其他设备上的登录也会失效。</p>
            </div>
          </div>
          <div class="workspace narrow">
            <section class="card">
              <form id="passwordForm" class="stack-form">
                <label for="currentPassword">当前密码</label>
                <input
                  id="currentPassword"
                  type="password"
                  autocomplete="current-password"
                  required
                  maxlength="128"
                />
                <label for="newPassword">新密码</label>
                <input
                  id="newPassword"
                  type="password"
                  autocomplete="new-password"
                  required
                  maxlength="128"
                />
                <label for="confirmPassword">确认新密码</label>
                <input
                  id="confirmPassword"
                  type="password"
                  autocomplete="new-password"
                  required
                  maxlength="128"
                />
                <p class="small muted">新密码长度须符合公司安全策略，且不能与最近使用过的密码相同。</p>
                <div class="button-row">
                  <button id="savePassword" class="primary" type="submit">
                    保存新密码
                  </button>
                </div>
              </form>
            </section>
          </div>
        </section>
        <section id="compose" hidden>
          <div class="page-heading">
            <div>
              <button id="backFromCompose" class="back-button" type="button">
                ← 我的事务
              </button>
              <h1>新建报销</h1>
              <p class="muted">填写费用信息，上传发票后进入核对。</p>
            </div>
          </div>
          <div class="workspace">
            <section class="card">
              <form id="expenseForm">
                <label for="expenseSubject"
                  >报销事由 <span class="required">*</span></label
                ><input
                  id="expenseSubject"
                  placeholder="例如：项目出差交通费"
                  required
                  maxlength="128"
                />
                <div class="form-grid">
                  <div>
                    <label for="expenseAmount"
                      >报销金额（元） <span class="required">*</span></label
                    ><input
                      id="expenseAmount"
                      type="number"
                      min="0.01"
                      max="9999999999999999.99"
                      step="0.01"
                      inputmode="decimal"
                      placeholder="0.00"
                      required
                    />
                  </div>
                  <div>
                    <label for="expenseDate"
                      >费用发生日期 <span class="required">*</span></label
                    ><input id="expenseDate" type="date" required />
                  </div>
                </div>
                <label for="composeFiles"
                  >发票附件 <span class="required">*</span></label
                ><label class="dropzone" for="composeFiles"
                  ><span class="upload-icon" aria-hidden="true">↑</span
                  ><strong>选择发票文件</strong
                  ><span class="small muted"
                    >PDF / JPG / PNG / WebP · 单份 20MB · 每单最多 50 份</span
                  ><input
                    id="composeFiles"
                    type="file"
                    multiple
                    accept=".pdf,.jpg,.jpeg,.png,.webp"
                /></label>
                <ul id="composeFileList" class="file-list"></ul>
                <div class="form-footer">
                  <span id="composeProgress" class="small muted"
                    >页面关闭前请完成提交，未填写内容不会自动保存。</span
                  ><button id="createRequest" class="primary" type="submit">
                    上传并核对 →
                  </button>
                </div>
              </form>
            </section>
            <aside>
              <section class="notice">
                <h3>报销信息由你确认</h3>
                <p>
                  费用企业根据本人员工关联确定。上传完毕后，请再次核对金额、事由与全部发票，再确认提交。
                </p>
                <p>刷新或关闭页面会丢失尚未上传的表单内容。</p>
              </section>
            </aside>
          </div>
        </section>
        <section id="expense" hidden>
          <div class="page-heading">
            <div>
              <button id="backFromExpense" class="back-button" type="button">
                ← 我的事务
              </button>
              <h1 id="expenseTitle">核对报销</h1>
              <p id="expenseSubtitle" class="muted">
                提交前，请核对费用信息和发票原件。
              </p>
            </div>
            <span id="expenseStatus" class="status-pill"></span>
          </div>
          <div class="workspace">
            <section class="card expense-card">
              <div class="card-heading">
                <h2>报销信息</h2>
                <button id="refresh" class="text-button" type="button">
                  刷新状态 ↻
                </button>
              </div>
              <div class="amount-block">
                <span class="small muted">报销金额</span>
                <div>
                  <span class="currency">¥</span
                  ><strong id="detailAmount">—</strong>
                </div>
              </div>
              <dl class="detail-grid">
                <div class="wide">
                  <dt>报销事由</dt>
                  <dd id="detailSubject">—</dd>
                </div>
                <div>
                  <dt>报销人</dt>
                  <dd id="detailEmployee">—</dd>
                </div>
                <div>
                  <dt>费用发生日期</dt>
                  <dd id="detailDate">—</dd>
                </div>
                <div class="wide">
                  <dt>费用企业</dt>
                  <dd id="detailOrg">—</dd>
                </div>
                <div id="receiptNumber" class="wide" hidden>
                  <dt>报销单号</dt>
                  <dd id="detailNumber" class="mono"></dd>
                </div>
              </dl>
              <div class="card-heading invoice-heading">
                <h2>发票附件</h2>
                <span id="attachmentCount" class="small muted">0 / 50</span>
              </div>
              <ul id="files" class="file-list"></ul>
              <p id="filesEmpty" class="empty-state" hidden>
                原定发票尚未上传完整，请在原填写流程或 AI 中继续准备。
              </p>
              <div class="notice">
                <p id="reviewNote">此页仅核对，不能增删发票或修改金额。</p>
                <div class="button-row">
                  <button id="editManual" type="button" class="outline" hidden>返回填写页整体修改</button>
                  <button id="copyAiRevision" type="button" class="outline" hidden>复制给 AI 的修改提示</button>
                </div>
              </div>
              <div id="confirmArea" class="confirm-area">
                <label class="checkbox-label"
                  ><input
                    id="confirmContent"
                    type="checkbox"
                  />我已核对事由、金额和全部发票，确认提交本次报销。</label
                >
                <div class="form-footer">
                  <p class="small muted">确认本次完整申请，提交后等待管理员处理。</p>
                  <button id="approve" class="primary" type="button">
                    确认并提交报销
                  </button>
                </div>
              </div>
              <div id="submittedNotice" class="submitted-notice" hidden>
                <strong id="submittedTitle">报销已提交</strong>
                <p id="submittedDescription">
                  请等待管理员处理，无需重复提交。
                </p>
              </div>
            </section>
            <aside>
              <section class="card">
                <h2>报销进度</h2>
                <ol class="timeline">
                  <li class="done">整理费用与发票</li>
                  <li id="stepConfirm">本人核对并提交</li>
                  <li id="stepProcess">管理员处理</li>
                  <li id="stepPosted">入账完成</li>
                </ol>
              </section>
              <section class="notice">
                <h3>由你完成最后确认</h3>
                <p>
                  无论手动填写还是 AI
                  整理，均需本人核对。确认会创建已提交的报销单，不会执行付款。
                </p>
              </section>
            </aside>
          </div>
        </section>
        <section id="software" hidden>
          <div class="page-heading">
            <div>
              <button id="backFromSoftware" class="back-button" type="button">
                ← 我的事务
              </button>
              <h1 id="softwareTitle">核对软件报销</h1>
              <p id="softwareSubtitle" class="muted">
                确认后写入当月工资「软件报销」。
              </p>
            </div>
            <span id="softwareStatus" class="status-pill">待核对</span>
          </div>
          <div class="workspace">
            <section class="card">
              <div class="card-heading">
                <h2>报销信息</h2>
                <button id="softwareRefresh" class="text-button" type="button">
                  刷新状态 ↻
                </button>
              </div>
              <div class="amount-block">
                <span class="small muted">计入工资金额</span>
                <div>
                  <span class="currency">¥</span
                  ><strong id="softwareApplied">—</strong>
                </div>
                <p class="small muted">申报合计 <span id="softwareClaimed">—</span></p>
              </div>
              <dl class="detail-grid">
                <div>
                  <dt>工资月份</dt>
                  <dd id="softwareMonth">—</dd>
                </div>
                <div>
                  <dt>报销人</dt>
                  <dd id="softwareEmployee">—</dd>
                </div>
                <div class="wide">
                  <dt>所属企业</dt>
                  <dd id="softwareOrg">—</dd>
                </div>
              </dl>
              <div class="card-heading invoice-heading">
                <h2>消费明细</h2>
              </div>
              <ul id="softwareItems" class="file-list"></ul>
              <div class="card-heading invoice-heading">
                <h2>凭证附件</h2>
                <span id="softwareAttachmentCount" class="small muted">0</span>
              </div>
              <ul id="softwareFiles" class="file-list"></ul>
              <p id="softwareFilesEmpty" class="empty-state" hidden>
                凭证尚未上传完整，请在 AI 中继续准备。
              </p>
              <div id="softwareConfirmArea" class="confirm-area">
                <label class="checkbox-label"
                  ><input
                    id="softwareConfirmContent"
                    type="checkbox"
                  />我已核对明细、金额和凭证，确认写入当月工资软件报销。</label
                >
                <div class="form-footer">
                  <p class="small muted">确认后不可在本页撤销；封账前管理员核算会同步该金额。</p>
                  <button id="softwareApprove" class="primary" type="button">
                    确认软件报销
                  </button>
                </div>
              </div>
              <div id="softwareDoneNotice" class="submitted-notice" hidden>
                <strong id="softwareDoneTitle">已确认</strong>
                <p id="softwareDoneDescription">软件报销已确认。</p>
              </div>
            </section>
          </div>
        </section>
        <section id="pairing" hidden>
          <div class="page-heading">
            <div>
              <h1>连接 AI 助手</h1>
              <p class="muted">授权本次本地连接，让 AI 帮你整理报销。</p>
            </div>
          </div>
          <section class="card narrow-card">
            <span class="line-illustration" aria-hidden="true">↗</span>
            <h2>确认是你发起的连接</h2>
            <p>
              本次连接只可办理本人报销。登录密码留在当前页面，AI
              不会获得你的系统登录信息。
            </p>
            <div class="notice">
              <p>
                仅在你刚刚从 AI 客户端发起连接时授权。报销仍需你本人核对后提交。
              </p>
            </div>
            <button id="pair" class="primary" type="button">
              授权本次连接
            </button>
            <p id="pairResult" class="muted" hidden></p>
          </section>
        </section>
        <section id="connection" hidden>
          <div class="page-heading">
            <div>
              <h1>AI 连接</h1>
              <p class="muted">
                连接你使用的 AI 客户端，帮助整理发票与报销信息。
              </p>
            </div>
          </div>
          <div class="workspace">
            <section class="card">
              <h2>连接员工报销服务</h2>
              <p class="muted">
                使用本地上传桥接时，按 AI 提示在浏览器登录授权即可。
              </p>
              <div class="notice">
                <p>
                  普通 HTTP
                  连接不会自动读取聊天附件。客户端需要支持文件传输，或使用本地上传桥接。
                </p>
              </div>
              <details id="manualConnection" open>
                <summary>手动配置连接</summary>
                <label>服务名称<input value="快盒员工报销" readonly /></label>
                <div class="form-grid">
                  <label
                    >连接方式<input value="Streamable HTTP" readonly /></label
                  ><label
                    >认证方式<input value="Bearer Token" readonly
                  /></label>
                </div>
                <label for="mcpUrl">MCP 服务地址</label
                ><input
                  id="mcpUrl"
                  class="mono"
                  readonly
                  placeholder="正在读取连接信息"
                />
                <div class="button-row">
                  <button id="copyUrl" class="outline" disabled type="button">
                    复制服务地址</button
                  ><button id="copyConfig" type="button">复制配置示例</button>
                </div>
                <label>认证请求头</label>
                <pre>Authorization: Bearer &lt;短期凭证&gt;</pre>
                <p class="small muted">
                  Token 输入框只填凭证；自定义请求头名称填 Authorization，值填
                  Bearer 加空格及凭证。本服务暂不支持 OAuth。
                </p>
                <button id="issue" class="primary" type="button">
                  获取短期凭证
                </button>
                <p id="endpoint" class="small muted"></p>
                <input
                  id="credential"
                  type="password"
                  readonly
                  hidden
                  aria-label="短期凭证"
                /><button id="copyToken" type="button" hidden>复制凭证</button>
              </details>
            </section>
            <aside>
              <section class="notice">
                <h3>凭证只用于连接设置</h3>
                <p>
                  不要把凭证发给 AI 或其他人。到期后重新获取，并更新客户端设置。
                </p>
                <p>配置示例使用占位符，不包含真实凭证。</p>
              </section>
            </aside>
          </div>
        </section>
      </div>
      <footer class="page-footer">
        快盒员工服务<span>仅展示本人费用与软件报销信息</span>
      </footer>
    </main>
    <script src="/portal.js"></script>
  </body>
</html>
'''
