"""员工门户独立样式，适配桌面与手机。"""
CSS = r'''
:root {
  color-scheme: light;
  --bg: #f5f7f5;
  --surface: #fff;
  --ink: #202c32;
  --muted: #77828e;
  --line: #e5ebe7;
  --teal: #24766c;
  --teal-soft: #edf7f3;
  --radius: 12px;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  font-size: 14px;
  color: var(--ink);
  background: var(--bg);
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
}
button,
input,
select {
  font: inherit;
}
button,
a,
input,
summary {
  outline-offset: 4px;
}
button {
  cursor: pointer;
  border: 1px solid #d7dfdb;
  border-radius: 6px;
  padding: 10px 17px;
  background: #fff;
  color: var(--ink);
  font-weight: 500;
  transition: background 0.15s;
}
button:hover {
  background: #f1f5f2;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
button:focus-visible,
a:focus-visible,
input:focus-visible,
summary:focus-visible {
  outline: 2px solid var(--teal);
}
a {
  color: var(--teal);
  text-decoration: none;
}
input,
select {
  display: block;
  width: 100%;
  min-height: 43px;
  padding: 10px 13px;
  border: 1px solid #d9e0dc;
  border-radius: 6px;
  background: #fff;
  color: var(--ink);
}
input:focus {
  border-color: var(--teal);
}
input[readonly] {
  background: #f9fbf9;
}
input[type="checkbox"] {
  width: 17px;
  min-height: 17px;
  height: 17px;
  flex-shrink: 0;
  accent-color: var(--teal);
}
input[type="file"] {
  margin-top: 12px;
  font-size: 12px;
  background: #fff;
  max-width: 100%;
}
label {
  display: block;
  margin: 22px 0 8px;
  font-weight: 500;
}
label input {
  margin-top: 8px;
}
h1,
h2,
h3,
p {
  margin-top: 0;
}
h1 {
  font-size: 30px;
  line-height: 1.4;
  letter-spacing: -0.6px;
  margin-bottom: 9px;
}
h2 {
  font-size: 18px;
  margin-bottom: 10px;
}
h3 {
  font-size: 15px;
  margin-bottom: 10px;
}
p {
  line-height: 1.8;
}
ol,
ul {
  margin: 0;
  padding: 0;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #f5f8f6;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 14px;
  font-size: 12px;
  line-height: 1.8;
}
summary {
  cursor: pointer;
  font-weight: 600;
  padding: 18px 0 4px;
}
details {
  margin-top: 16px;
  border-top: 1px solid var(--line);
}
[hidden] {
  display: none !important;
}
.muted {
  color: var(--muted);
}
.small {
  font-size: 12px;
}
.required {
  color: #c95445;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  overflow-wrap: anywhere;
}
.full-width {
  width: 100%;
}
.primary {
  background: var(--teal);
  border-color: var(--teal);
  color: white;
}
.primary:hover {
  background: #1b625a;
}
.outline {
  border-color: var(--teal);
  color: var(--teal);
}
.text-button,
.back-button {
  border: 0;
  background: transparent;
  padding: 7px 0;
  color: var(--teal);
}
.back-button {
  margin-bottom: 12px;
  font-size: 13px;
}
.topbar {
  background: #fff;
  border-bottom: 1px solid var(--line);
}
.topbar-inner {
  max-width: 1320px;
  min-height: 76px;
  display: flex;
  gap: 55px;
  align-items: center;
  margin: auto;
  padding: 0 40px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 19px;
  font-weight: 700;
  color: var(--ink);
  white-space: nowrap;
}
.brand svg {
  width: 29px;
  height: 29px;
  fill: none;
  stroke: var(--teal);
  stroke-width: 2.2;
  stroke-linejoin: round;
}
.brand-divider {
  padding: 0 7px;
}
nav {
  display: flex;
  gap: 26px;
  align-self: stretch;
}
.nav-button {
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0 3px;
  color: #687681;
}
.nav-button.active {
  color: var(--teal);
  box-shadow: inset 0 -3px var(--teal);
}
.account-area {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.account-area .text-button {
  margin-left: 6px;
  font-size: 12px;
  color: var(--muted);
}
.avatar {
  display: grid;
  place-items: center;
  width: 31px;
  height: 31px;
  border-radius: 50%;
  background: var(--teal-soft);
  color: var(--teal);
  font-size: 12px;
}
main {
  max-width: 1320px;
  margin: auto;
  padding: 34px 40px 0;
}
.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin: 4px 0 26px;
}
.page-heading p {
  margin-bottom: 0;
}
.inline-meta {
  margin-left: 16px;
  padding-left: 16px;
  border-left: 1px solid #d6ded9;
  font-size: 12px;
}
.workspace {
  display: grid;
  grid-template-columns: minmax(0, 2.3fr) minmax(260px, 1fr);
  gap: 22px;
  align-items: start;
}
.workspace.narrow {
  grid-template-columns: minmax(0, 520px);
  justify-content: start;
}
.home-stacks {
  display: grid;
  gap: 18px;
}
.stack-form {
  display: grid;
  gap: 10px;
}
.stack-form label {
  margin-top: 4px;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 14px;
}
.pager .outline {
  min-width: 88px;
}
.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 26px;
  box-shadow: 0 2px 4px #263d2e02;
}
.card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
}
.card-heading h2,
.card-heading p {
  margin-bottom: 0;
}
.card-heading p {
  margin-top: 8px;
}
.notice {
  padding: 22px 24px;
  background: var(--teal-soft);
  border: 1px solid #dceee6;
  border-radius: var(--radius);
  color: #4c6860;
  margin-top: 22px;
}
.notice p:last-child {
  margin-bottom: 0;
}
.notice h3 {
  color: var(--teal);
}
.page-footer {
  display: flex;
  justify-content: space-between;
  padding: 25px 0;
  margin-top: 25px;
  font-size: 11px;
  color: #929d96;
}
.feedback {
  border: 1px solid #eed8d1;
  border-radius: 8px;
  padding: 13px 17px;
  background: #fff5f0;
  color: #9c4d3c;
  margin: 0 0 22px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.feedback.success {
  background: var(--teal-soft);
  border-color: #cfe5da;
  color: var(--teal);
}
.feedback:empty {
  display: none;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 22px;
}
.form-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  border-top: 1px solid var(--line);
  margin-top: 24px;
  padding-top: 20px;
}
.form-footer p {
  margin: 0;
}
.button-row {
  display: flex;
  gap: 10px;
  margin: 12px 0 20px;
}
.dropzone {
  border: 1px dashed #bdcec4;
  border-radius: 8px;
  padding: 23px;
  text-align: center;
  background: #fafcfb;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.dropzone:hover {
  border-color: var(--teal);
  background: #f5faf7;
}
.dropzone .upload-icon {
  font-size: 26px;
  color: #8b9f93;
}
.dropzone.compact {
  padding: 16px;
}
.dropzone strong {
  font-weight: 500;
  color: var(--teal);
}
.file-list {
  list-style: none;
  margin-top: 16px;
  display: grid;
  gap: 9px;
  max-height: 420px;
  overflow: auto;
}
.file-row {
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.file-icon {
  width: 30px;
  height: 33px;
  border: 1px solid #eaccc4;
  background: #fff4ef;
  border-radius: 5px;
  color: #b65b48;
  display: grid;
  place-items: center;
  font-size: 9px;
  flex-shrink: 0;
}
.file-name {
  min-width: 0;
  flex: 1;
  overflow-wrap: anywhere;
}
.file-name button {
  max-width: 100%;
  border: 0;
  background: none;
  padding: 0;
  text-align: left;
  color: var(--ink);
  overflow-wrap: anywhere;
}
.file-size {
  display: block;
  color: var(--muted);
  font-size: 11px;
  margin-top: 4px;
}
.file-preview {
  font-size: 12px;
  color: var(--teal);
  flex-shrink: 0;
}
.empty-state {
  padding: 50px 15px;
  text-align: center;
  color: #829087;
  line-height: 2;
}
.ai-card {
  padding: 26px;
}
.line-illustration {
  display: grid;
  place-items: center;
  width: 54px;
  height: 54px;
  margin-bottom: 23px;
  border-radius: 14px;
  background: var(--teal-soft);
  color: var(--teal);
  font-size: 28px;
}
.steps {
  list-style: none;
  counter-reset: step;
  margin: 24px 0;
}
.steps li {
  counter-increment: step;
  display: flex;
  align-items: center;
  gap: 13px;
  margin: 17px 0;
  font-size: 13px;
}
.steps li:before {
  content: counter(step);
  width: 25px;
  height: 25px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--teal-soft);
  color: var(--teal);
  font-size: 12px;
}
.ai-card > p:last-child {
  margin: 12px 0 0;
}
.record-filters {
  display: flex;
  gap: 10px;
  border-bottom: 1px solid var(--line);
  margin: 24px 0 0;
  padding-bottom: 17px;
  flex-wrap: wrap;
}
.filter-button {
  padding: 6px 13px;
  border-color: transparent;
  font-size: 12px;
  color: #7b887f;
}
.filter-button.active {
  background: var(--teal-soft);
  color: var(--teal);
}
.record-row {
  display: flex;
  align-items: center;
  gap: 17px;
  width: 100%;
  border: 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  padding: 20px 0;
  text-align: left;
}
.record-row:hover {
  background: #fbfdfb;
}
.record-main {
  flex: 1;
  min-width: 0;
}
.record-subject {
  display: block;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.record-date {
  display: block;
  color: var(--muted);
  font-size: 11px;
  margin-top: 7px;
}
.record-amount {
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
}
.status-pill {
  display: inline-block;
  border-radius: 20px;
  padding: 5px 12px;
  font-size: 11px;
  white-space: nowrap;
  font-weight: 500;
  background: #f0f3f1;
  color: #6b7c70;
}
.status-pill.pending {
  background: #fff3d7;
  color: #957328;
}
.status-pill.processing {
  background: #edf3fb;
  color: #506e9d;
}
.status-pill.posted {
  background: var(--teal-soft);
  color: var(--teal);
}
.status-pill.rejected {
  background: #fff0eb;
  color: #aa5e4a;
}
.amount-block {
  margin: 25px 0;
  padding: 24px;
  background: #f5f9f6;
  border-radius: 8px;
}
.amount-block > div {
  margin-top: 10px;
}
.amount-block strong {
  font-size: 37px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: -1px;
}
.currency {
  font-size: 21px;
  margin-right: 8px;
  color: #60746a;
}
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 23px;
  margin: 25px 0;
}
.detail-grid .wide {
  grid-column: 1/-1;
}
.detail-grid dt {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 9px;
}
.detail-grid dd {
  margin: 0;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.detail-grid .mono {
  font-size: 12px;
}
.invoice-heading {
  border-top: 1px solid var(--line);
  padding-top: 25px;
  margin-top: 27px;
}
.confirm-area {
  margin-top: 28px;
}
.checkbox-label {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  line-height: 1.5;
}
.checkbox-label input {
  margin: 1px 0 0;
}
.submitted-notice {
  padding: 20px;
  background: var(--teal-soft);
  border-radius: 8px;
  color: var(--teal);
  margin-top: 25px;
}
.submitted-notice p {
  font-size: 13px;
  margin: 8px 0 0;
}
.timeline {
  list-style: none;
  margin-top: 26px;
}
.timeline li {
  position: relative;
  margin-left: 8px;
  padding: 0 0 27px 24px;
  font-size: 13px;
  color: #93a098;
  border-left: 1px solid #dfe7e1;
}
.timeline li:before {
  position: absolute;
  left: -5px;
  top: 3px;
  content: "";
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #dfe7e1;
}
.timeline li.current {
  color: var(--teal);
}
.timeline li.current:before {
  background: var(--teal);
  box-shadow: 0 0 0 4px var(--teal-soft);
}
.timeline li.done {
  color: var(--teal);
}
.timeline li.done:before {
  background: var(--teal);
}
.timeline li:last-child {
  border: 0;
  padding-bottom: 0;
}
.narrow-card {
  max-width: 660px;
  margin: 30px auto;
}
.narrow-card .primary {
  margin-top: 24px;
}
.login-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: center;
  max-width: 430px;
  margin: 45px auto 65px;
  min-height: 520px;
}
.login-card {
  padding: 32px;
}
.login-card h2 {
  font-size: 23px;
}
.login-card .primary {
  margin-top: 27px;
}
.login-card .small {
  margin-bottom: 0;
}
.captcha-row {
  display: flex;
  align-items: stretch;
  gap: 12px;
}
.captcha-row input {
  flex: 1;
  min-width: 0;
}
.captcha-button {
  padding: 0;
  flex-shrink: 0;
  width: 122px;
  overflow: hidden;
  background: #f5f8f6;
}
.captcha-button img {
  display: block;
  width: 120px;
  height: 43px;
  object-fit: contain;
}
.login-card > p {
  font-size: 13px;
}
@media (min-width: 1550px) {
  main {
    padding-top: 48px;
  }
  .page-heading {
    margin-bottom: 30px;
  }
  .card {
    padding: 30px;
  }
}
@media (max-width: 900px) {
  .workspace {
    grid-template-columns: minmax(0, 1fr) 270px;
    gap: 16px;
  }
  .topbar-inner {
    gap: 28px;
    padding: 0 24px;
  }
  main {
    padding: 28px 24px 0;
  }
  .card {
    padding: 22px;
  }
  .brand {
    font-size: 17px;
  }
  .inline-meta {
    display: block;
    border: 0;
    padding: 0;
    margin: 8px 0 0;
  }
}
@media (max-width: 700px) {
  .topbar-inner {
    padding: 0 18px;
    min-height: 68px;
    gap: 0;
    flex-wrap: wrap;
  }
  .brand {
    font-size: 16px;
  }
  .brand svg {
    width: 25px;
  }
  .account-area {
    gap: 6px;
    max-width: 48%;
    font-size: 12px;
  }
  .account-area #identity {
    max-width: 95px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .account-area .avatar {
    display: none;
  }
  nav {
    order: 3;
    width: 100%;
    height: 46px;
    gap: 24px;
  }
  .nav-button {
    font-size: 13px;
  }
  main {
    padding: 24px 16px 0;
  }
  .page-heading {
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 22px;
  }
  h1 {
    font-size: 25px;
  }
  .page-heading .primary {
    padding: 9px 12px;
    font-size: 12px;
    white-space: nowrap;
  }
  .page-heading p {
    font-size: 12px;
  }
  .workspace {
    grid-template-columns: minmax(0, 1fr);
  }
  .card {
    padding: 21px 18px;
  }
  .workspace aside {
    display: grid;
    gap: 16px;
  }
  .workspace aside .notice {
    margin-top: 0;
  }
  .workspace aside .card {
    margin-top: 0;
  }
  .login-layout {
    display: block;
    margin: 15px auto;
    min-height: 0;
    max-width: 430px;
  }
  .login-card {
    padding: 28px 23px;
  }
  .form-grid {
    gap: 15px;
  }
  .form-footer {
    flex-direction: column;
    align-items: stretch;
  }
  .form-footer button {
    width: 100%;
  }
  .record-row {
    gap: 10px;
  }
  .record-amount {
    font-size: 13px;
  }
  .status-pill {
    padding: 5px 8px;
    font-size: 10px;
  }
  .record-subject {
    font-size: 13px;
  }
  .record-row > .chevron {
    display: none;
  }
  .dropzone {
    padding: 18px 12px;
  }
  .detail-grid {
    gap: 20px;
  }
  .amount-block strong {
    font-size: 32px;
  }
  .page-footer {
    font-size: 10px;
    gap: 10px;
  }
  .button-row {
    flex-wrap: wrap;
  }
  .button-row button {
    flex: 1;
    padding: 10px;
  }
  .narrow-card {
    margin: 0;
  }
  .file-preview {
    font-size: 11px;
  }
  .feedback {
    font-size: 12px;
  }
  .account-area .text-button {
    padding: 8px 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  * {
    transition: none !important;
    scroll-behavior: auto !important;
  }
}
'''
