"""将 SDK 事件投影为安全的阶段日志；不读取或发布工具参数、正文和模型思考。"""
import logging
import json
import re
from time import monotonic
from urllib.parse import urlsplit

from .schemas import AssistantProgress, AssistantRun

# 默认 Uvicorn 入口只为自身配置输出，沿用其日志链，保证阶段 INFO 实际可见。
logger = logging.getLogger("uvicorn.error.ai_assistant")
TOOL_LABELS = {
    "erp_discover": "查找业务入口", "erp_api": "查询业务信息",
    "erp_query": "查询业务信息", "erp_knowledge_search": "查找相关知识",
    "erp_knowledge_read_document": "查找相关知识", "web_search": "联网搜索", "web_fetch": "读取网页",
}
# 按用户理解的阶段归并工具；联网搜索、网页读取单独展示。
TOOL_GROUPS = {
    "erp_knowledge_search": ("erp_knowledge_search", "erp_knowledge_read_document"),
    "erp_discover": ("erp_discover",),
    "erp_api": ("erp_api", "erp_query"),
    "web_search": ("web_search",),
    "web_fetch": ("web_fetch",),
}
TOOL_ERRORS = {
    "WEB_BLOCKED_URL": "地址被网络安全检查拒绝；请检查 DNS、代理或目标地址",
    "WEB_REDIRECT_BLOCKED": "网页跳转被网络策略拒绝",
    "WEB_FETCH_TIMEOUT": "网页读取超时", "WEB_ABORTED": "联网查询已取消",
    "WEB_PROVIDER_ERROR": "联网服务未能取得可用结果",
    "WEB_PROVIDER_UNAVAILABLE": "联网服务不可用",
    "WEB_UNSUPPORTED_CONTENT_TYPE": "站点没有返回可读取的网页正文",
    "WEB_HTTP_ERROR": "站点拒绝访问或返回错误",
}


def _hostname(url):
    """过程面板只展示站点域名，不发布路径、查询参数或 URL 中的认证信息。"""
    if not isinstance(url, str):
        return ""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host if len(host) <= 253 and re.fullmatch(r"[a-zA-Z0-9.-]+", host) else ""


class ProgressTracker:
    def __init__(self, run: AssistantRun):
        self.run = run
        self.started = monotonic()
        self.step = 1
        self.calls = {}
        self.records = {}
        self.starts = {}
        self.ends = {}
        self.tool_names = {}
        self.hosts = {}
        self.http_statuses = {}
        self.source_urls = set()
        self._begin("runtime", "理解问题")

    def _record(self, key, label, status, detail="", elapsed_ms=None, error_code=None):
        self.records[key] = AssistantProgress(key=key, label=label, status=status, detail=detail,
                                              elapsed_ms=elapsed_ms, error_code=error_code)
        self.run.progress = self._summary()
        logger.info("assistant_progress run_id=%s stage=%s label=%s status=%s elapsed_ms=%s error_code=%s",
                    self.run.run_id, key, label, status, elapsed_ms, error_code)

    def _begin(self, key, label):
        self.starts[key] = monotonic()
        self._record(key, label, "running")

    def _end(self, key, *, error_code=None, fatal=False):
        record = self.records.get(key)
        if record is None or record.status != "running":
            return False
        self.ends[key] = monotonic()
        elapsed_ms = max(0, int((self.ends[key] - self.starts[key]) * 1000))
        detail = f"用时 {elapsed_ms / 1000:.1f} 秒"
        label = record.label
        if error_code:
            label += "失败"
            detail = TOOL_ERRORS.get(error_code, "工具未能取得结果") + "；" + detail
        # 工具失败仍可继续问答；整轮结果由单独的 result 步骤决定。
        self._record(key, label, "error" if fatal or error_code else "done", detail, elapsed_ms, error_code)
        return True

    def _elapsed(self, keys):
        # 并行读取多个网页时按实际等待区间合并，避免把 1 秒显示成累计 2 秒。
        now = monotonic()
        intervals = sorted((self.starts[key], self.ends.get(key, now)) for key in keys)
        total, previous_end = 0, 0
        for start, end in intervals:
            total += max(0, end - max(start, previous_end))
            previous_end = max(previous_end, end)
        return max(0, int(total * 1000))

    def _summary(self):
        """详细事件留在后端日志；页面按阶段合并，只展示实际发生的步骤。"""
        result = [self.records["runtime"]]
        for name, tools in TOOL_GROUPS.items():
            keys = [key for key, tool in self.tool_names.items() if tool in tools]
            if not keys:
                continue
            running = [key for key in keys if self.records[key].status == "running"]
            failures = [key for key in keys if self.records[key].status == "error"]
            done = len(keys) - len(running) - len(failures)
            if name == "web_search":
                detail = f"已完成 {done} 次检索，发现 {len(self.source_urls)} 个候选来源"
            elif name == "web_fetch":
                detail = f"已获取 {done} 页，{len(failures)} 页不可用"
                host = self.hosts.get((running or keys)[-1])
                if host:
                    detail += f"；{'正在读取' if running else '最近读取'} {host}"
            else:
                detail = f"已完成 {done} 次调用"
            if running:
                detail += f"；{len(running)} 项进行中"
            if failures:
                failed_key = failures[-1]
                code = self.records[failed_key].error_code
                status = self.http_statuses.get(failed_key)
                reason = f"网站返回 HTTP {status}" if status and status >= 400 else TOOL_ERRORS.get(code, "工具未能取得结果")
                detail += f"；{len(failures)} 次失败：{reason}"
            status = "running" if running else "error" if len(failures) == len(keys) else "done"
            elapsed_ms = self._elapsed(keys)
            detail += f"；用时 {elapsed_ms / 1000:.1f} 秒"
            result.append(AssistantProgress(key=f"tool-{name}", label=TOOL_LABELS[name], status=status,
                detail=detail, elapsed_ms=elapsed_ms,
                error_code=self.records[failures[-1]].error_code if failures else None))
        models = [key for key in self.records if key.startswith("model-")]
        if models:
            running = any(self.records[key].status == "running" for key in models)
            failed = any(self.records[key].status == "error" for key in models)
            elapsed_ms = self._elapsed(models)
            result.append(AssistantProgress(key="answer", label="整理回答",
                status="running" if running else "error" if failed else "done", elapsed_ms=elapsed_ms,
                detail=f"共 {len(models)} 轮处理，用时 {elapsed_ms / 1000:.1f} 秒"))
        if "result" in self.records:
            result.append(self.records["result"])
        return result

    def handle(self, event):
        kind, data = event.get("type"), event.get("data", {})
        if kind == "step/start":
            self.step = data["step"]
        if kind in {"step/start", "request/context"}:
            # 首轮 step/start 可能早于 SDK 接收本轮问题，以请求上下文事件补齐。
            if f"model-{self.step}" in self.records:
                return False
            self._end("runtime")
            self._begin(f"model-{self.step}", "理解问题" if self.step == 1 else "整理回答")
        elif kind == "tool/call" and data.get("name") in TOOL_LABELS:
            self._end(f"model-{self.step}")
            key = f"tool-{len(self.calls) + 1}"
            self.calls[data["callId"]] = key
            self.tool_names[key] = data["name"]
            if data["name"] == "web_fetch":
                args = data.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if isinstance(args, dict):
                    self.hosts[key] = _hostname(args.get("url"))
            self._begin(key, TOOL_LABELS[data["name"]])
        elif kind == "tool/result":
            key = self.calls.get(data.get("message", {}).get("toolCallId"))
            if key is None:
                return False
            meta = data.get("meta") or {}
            if self.tool_names[key] == "web_search":
                self.source_urls.update(source["url"] for source in meta.get("sources", []) if source.get("url"))
            elif self.tool_names[key] == "web_fetch":
                self.hosts[key] = _hostname(meta.get("url")) or self.hosts.get(key, "")
                self.http_statuses[key] = meta.get("statusCode")
            code = None
            if data["message"].get("isError"):
                raw_code = data.get("error", {}).get("code")
                code = raw_code if raw_code in TOOL_ERRORS else "TOOL_FAILED"
            elif (self.http_statuses.get(key) or 0) >= 400:
                code = "WEB_HTTP_ERROR"
            self._end(key, error_code=code)
        elif kind == "step/end":
            return self._end(f"model-{self.step}")
        else:
            return False
        return True

    def finish(self):
        failed = self.run.status != "completed"
        for key, record in list(self.records.items()):
            if record.status == "running":
                self._end(key, fatal=failed)
        elapsed_ms = max(0, int((monotonic() - self.started) * 1000))
        self._record("result", "已完成" if not failed else "本轮未完成", "error" if failed else "done",
                     f"总用时 {elapsed_ms / 1000:.1f} 秒", elapsed_ms)
