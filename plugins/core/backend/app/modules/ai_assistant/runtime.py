"""官方 DSH Python SDK 适配；每轮独立进程，恢复本会话日志，使用本轮新凭据。"""
import json
import os
import threading
from pathlib import Path

from fastapi import HTTPException

from app.core.config import BASE_DIR, get_settings


class OwnedRuntime:
    """串行管理启动和关闭，取消发生在启动前时不再创建进程。"""

    def __init__(self, harness):
        self.harness = harness
        self._startup = threading.Lock()
        self._closed = False
        self.phase = "preparing"

    def run(self, question, *, session_id, on_notification=None):
        with self._startup:
            if self._closed:
                raise RuntimeError("智能体任务已取消")
            self.phase = "initializing"
            session = self.harness.start_session(session_id)
            self.phase = "running"
        return session.run(question, on_notification=on_notification)

    def close(self):
        with self._startup:
            self._closed = True
            self.harness.close()


def runtime_paths():
    settings = get_settings()
    if not settings.server_assistant_enabled or not settings.server_assistant_dsh_root:
        raise HTTPException(503, "服务端智能体尚未启用，请联系管理员")
    root = Path(settings.server_assistant_dsh_root).expanduser().resolve()
    directory = root / "integrations/server-assistant"
    executable = root / "apps/cli/src/bin.ts"
    if not executable.is_file() or not (directory / "cordis.patch.yml").is_file():
        raise HTTPException(503, "DSH 服务端运行代码尚未配置，请检查仓库路径")
    try:
        from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig
    except ImportError as exc:
        raise HTTPException(503, "请先安装 DSH Python SDK") from exc
    return root, executable, DeepSeekHarness, DeepSeekHarnessConfig


def _create_harness(home, access_token, credential, client_id, *, approval_token="", run_id="", session_id="", user_context=""):
    root, executable, harness_type, config_type = runtime_paths()
    settings = get_settings()
    assets = Path(__file__).resolve().parent / "dsh"
    # SDK 不继承 FastAPI 的 DATABASE_URL、供应商密钥等环境变量。
    allowed = {
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME", "USERPROFILE",
        "APPDATA", "LOCALAPPDATA", "PNPM_HOME",
        # 交给 DSH 原生代理策略解析，保留大小写和 NO_PROXY 绕过规则。
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment.update({
        "ERP_SERVER_ACCESS_TOKEN": access_token,
        "ERP_SERVER_GATEWAY_TOKEN": credential,
        "ERP_SERVER_CLIENT_ID": str(client_id),
        "ERP_SERVER_API_URL": settings.server_assistant_api_url,
        "ERP_SERVER_GATEWAY_URL": settings.server_assistant_api_url + "/api/llm-gateway/anthropic",
        "ERP_SERVER_MODEL": settings.server_assistant_model,
        "ERP_SERVER_TOOL_TIMEOUT_MS": str(settings.server_assistant_tool_timeout_ms),
        "ERP_SERVER_MAX_RESPONSE_CHARS": str(settings.server_assistant_max_response_chars),
        "ERP_SERVER_APPROVAL_TOKEN": approval_token,
        "ERP_SERVER_RUN_ID": str(run_id),
        "ERP_SERVER_SESSION_ID": str(session_id),
        "ERP_SERVER_APPROVAL_TIMEOUT_MS": str(min(90, max(15, settings.server_assistant_turn_timeout_seconds - 45)) * 1000),
    })
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Loader 的插件名不执行表达式；生成普通字符串地址，适配各环境的 ERP 安装路径。
    time_patch = home / "time-context.patch.json"
    time_patch.write_text(json.dumps([{"insert": [{
        "id": "erp-server-time-context",
        "name": (assets / "time_context.mjs").as_uri(),
        "config": {"timeZone": "Asia/Shanghai"},
    }]}], ensure_ascii=False), encoding="utf-8")
    # 知识工具与 DSH 桌面端共用；提示词和只读工具范围由 ERP 随包维护。
    knowledge_patch = home / "knowledge.patch.json"
    knowledge_patch.write_text(json.dumps([
        {"id": "system-prompt", "config": {
            "includeHarnessIdentity": False, "includeRuntimeContext": False,
            "personaPrefix": (assets / "knowledge_prompt.txt").read_text(encoding="utf-8") + ("\n\n" + user_context if user_context else ""),
        }},
        {"insert": [{"id": "erp-server-knowledge", "name": (assets / "knowledge.mjs").as_uri()}]},
    ], ensure_ascii=False), encoding="utf-8")
    web_patch = home / "web.patch.json"
    web_patch.write_text(json.dumps([{"insert": [{
        "id": "erp-server-web", "name": (assets / "web.mjs").as_uri(),
    }]}], ensure_ascii=False), encoding="utf-8")
    return harness_type(config_type(
        provider="erp-gateway", model=settings.server_assistant_model,
        max_tokens=min(settings.server_assistant_max_output_tokens, settings.llm_gateway_max_output_tokens),
        cwd=str(home), runtime_cwd=str(root), dsh_bin=str(executable), profile="sdk-minimal",
        patches=(str(root / "integrations/server-assistant/cordis.patch.yml"),
                 str(time_patch), str(knowledge_patch), str(web_patch)),
        dsh_home=str(home), env=environment, inherit_env=False,
        node_bin=settings.server_assistant_node_bin,
        initialize_timeout_seconds=60, request_timeout_seconds=settings.server_assistant_turn_timeout_seconds,
    ))


def create_runtime(user, session_id, access_token, credential, client_id, *, approval_token="", run_id="", public_session_id="", user_context=""):
    settings = get_settings()
    home = (BASE_DIR / settings.server_assistant_storage_dir / str(user.tenant_id) / str(user.user_id) / str(session_id)).resolve()
    return OwnedRuntime(_create_harness(home, access_token, credential, client_id,
                                        approval_token=approval_token, run_id=run_id, session_id=public_session_id, user_context=user_context))


def check_startup():
    """在独立临时目录初始化 SDK；不发送问题、不调用模型、不查询 ERP。"""
    from tempfile import TemporaryDirectory
    from uuid import uuid4
    runtime_paths()
    storage = (BASE_DIR / get_settings().server_assistant_storage_dir).resolve()
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)
    with TemporaryDirectory(prefix=".startup-check-", dir=storage) as directory:
        harness = _create_harness(Path(directory), "startup-check-erp", "startup-check-gateway", uuid4(),
                                  approval_token="startup-check-approval", run_id=uuid4(), session_id=uuid4())
        try:
            harness.start()
        finally:
            harness.close()
