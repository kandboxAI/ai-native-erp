import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
TENANT_NO_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,29}")


def validate_tenant_no(value: str) -> str:
    """租户编号：小写字母开头，小写字母、数字、下划线，最长 30 位（schema 名 t_<租户编号> 不超过 32 位）。"""
    value = (value or "").strip()
    if not TENANT_NO_PATTERN.fullmatch(value):
        raise ValueError("租户编号只能由小写字母开头，包含小写字母、数字、下划线，最长 30 位")
    return value


def tenant_schema_name(tenant_no: str) -> str:
    """每个租户一个 schema：t_<租户编号>。"""
    return f"t_{validate_tenant_no(tenant_no)}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "erp_foundation"
    employee_login_email_domain: str = "admin.com"
    app_env: str = "development"
    debug: bool = True
    api_prefix: str = "/api"
    # 页面自助接入：主密钥仅在服务器保存；来源白名单防止管理员表单成为任意网络代理。
    knowledge_credential_encryption_key: SecretStr | None = None
    knowledge_engine_allowed_origins: list[str] = Field(default_factory=list)
    database_url: str
    # 默认租户编号；租户 schema 名为 t_<租户编号>
    default_tenant_no: str = "default"
    default_tenant_name: str = "示例组织"
    # 默认租户内置管理员（bootstrap 首次开通时创建；之后不覆盖密码）。生产环境必须通过环境变量配置密码
    init_admin_email: str = "admin@admin.com"
    init_admin_password: str | None = None
    database_pool_min_size: int = Field(default=1, ge=1)
    database_pool_max_size: int = Field(default=10, ge=1)
    database_pool_timeout_seconds: int = Field(default=30, ge=1)
    database_statement_timeout_ms: int = Field(default=30000, ge=1000)
    sqlalchemy_pool_size: int = Field(default=10, ge=1)
    sqlalchemy_max_overflow: int = Field(default=20, ge=0)
    sqlalchemy_pool_timeout_seconds: int = Field(default=30, ge=1)
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_socket_timeout_seconds: int = Field(default=5, ge=1)
    redis_socket_connect_timeout_seconds: int = Field(default=5, ge=1)
    redis_max_connections: int = Field(default=50, ge=1)
    rabbitmq_url: str | None = None
    rabbitmq_connect_timeout_seconds: int = 10
    message_bus_enabled: bool = False
    message_bus_default_exchange: str = "erp.events"
    message_bus_publish_batch_size: int = 50
    message_bus_max_retries: int = 10
    jwt_secret: str
    jwt_access_expire_minutes: int = Field(default=120, ge=1)
    jwt_refresh_expire_days: int = Field(default=30, ge=1, le=30)
    auth_session_expire_hours: int = Field(default=12, ge=1, le=168)
    auth_login_rate_limit_per_minute: int = Field(default=10, ge=1)
    auth_login_account_rate_limit_per_15_minutes: int = Field(default=20, ge=1)
    auth_refresh_rate_limit_per_minute: int = Field(default=30, ge=1)
    auth_login_captcha_ttl_seconds: int = Field(default=300, ge=60, le=1800)
    auth_captcha_rate_limit_per_minute: int = Field(default=60, ge=1)
    api_export_rate_limit_per_minute: int = Field(default=10, ge=1)
    # 文件与附件（file_attachment）：客户端直传对象存储；见 docs/foundation-platform/file-attachment-design.md
    # file_storage_backend：auto = 配好 OSS 时用 OSS，否则用本地存储（仅开发环境，协议与 OSS 相同）
    file_storage_backend: Literal["auto", "oss", "local"] = "auto"
    attachment_storage_dir: str = "storage/attachments"  # 本地存储根目录
    attachment_pending_hours: int = Field(default=24, ge=1, le=168)  # 上传后未绑定单据的保留时长
    file_upload_url_expires_seconds: int = Field(default=600, ge=60, le=3600)
    file_download_url_expires_seconds: int = Field(default=600, ge=60, le=86400)
    # 阿里云 OSS 对象存储：一个私有 bucket，不开放公共读
    oss_access_key_id: str | None = None
    oss_access_key_secret: str | None = None
    oss_region: str | None = None
    oss_endpoint: str | None = None
    oss_bucket_files: str = "files"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:8848",
            "http://127.0.0.1:8848",
            "http://localhost:5173",
        ]
    )
    access_token_audience: str = "authenticated"
    harness_query_key: str | None = None
    harness_query_max_joins: int = Field(default=8, ge=1, le=32)
    harness_embedding_url: str | None = None
    harness_embedding_api_key: str | None = Field(default=None, repr=False)
    harness_embedding_model: str = ""
    harness_embedding_dimensions: int = Field(default=1024, ge=1, le=16000)
    harness_embedding_batch_size: int = Field(default=16, ge=1, le=64)
    harness_embedding_send_dimensions: bool = True
    harness_discovery_timeout_seconds: int = Field(default=10, ge=1, le=60)
    harness_discovery_recall_limit: int = Field(default=30, ge=12, le=100)
    harness_discovery_lexical_enabled: bool = True
    harness_rerank_url: str | None = None
    harness_rerank_api_key: str | None = Field(default=None, repr=False)
    harness_rerank_model: str = ""
    harness_rerank_protocol: Literal["compatible", "dashscope"] = "compatible"
    harness_rerank_instruct: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("harness_embedding_url", "harness_rerank_url")
    @classmethod
    def _discovery_endpoint(cls, value: str | None) -> str | None:
        if not value:
            return None
        url = urlsplit(value)
        if not url.hostname or url.username or url.password or url.query or url.fragment \
                or (url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1"))):
            raise ValueError("Discovery endpoint must use HTTPS or local loopback HTTP")
        return value
    # 服务端 DSH：网页和小程序共用，客户端不配置模型密钥。
    server_assistant_enabled: bool = False
    server_assistant_dsh_root: str | None = None
    server_assistant_node_bin: str = Field(default="node", min_length=1)
    server_assistant_api_url: str = "http://127.0.0.1:8000"
    server_assistant_storage_dir: str = "storage/server-assistant"
    server_assistant_model: str = "deepseek-flash"
    server_assistant_turn_timeout_seconds: int = Field(default=180, ge=30, le=3600)
    server_assistant_max_concurrent_runs: int = Field(default=4, ge=1, le=32)
    server_assistant_session_ttl_seconds: int = Field(default=30 * 86400, ge=3600)
    server_assistant_max_output_tokens: int = Field(default=32768, ge=256)
    server_assistant_tool_timeout_ms: int = Field(default=30000, ge=1000, le=120000)
    server_assistant_max_response_chars: int = Field(default=50000, ge=1000, le=500000)

    @field_validator("server_assistant_api_url")
    @classmethod
    def _server_assistant_endpoint(cls, value: str) -> str:
        url = urlsplit(value)
        if not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/") \
                or (url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1"))):
            raise ValueError("服务端智能体地址须为 ERP HTTPS 根地址或本机回环 HTTP 根地址")
        return value.rstrip("/")

    assistant_llm_base_url: str | None = None
    assistant_llm_api_key: str | None = None
    assistant_llm_model: str | None = None
    assistant_embedding_model: str | None = None
    knowledge_position_summary_model: str = "deepseek-v4.1-flash"
    knowledge_position_embedding_model: str = "qwen3-vl-embedding"
    assistant_llm_timeout_seconds: int = 20
    # Desktop DSH model gateway: the upstream key exists only on this server.
    llm_gateway_deepseek_api_key: str | None = None
    llm_gateway_upstream_base_url: str = "https://api.deepseek.com/anthropic"
    llm_gateway_search_base_url: str = "https://api.deepseek.com"
    llm_gateway_allowed_models: list[str] = Field(default_factory=lambda: ["deepseek-flash"])
    llm_gateway_credential_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    llm_gateway_requests_per_minute: int = Field(default=30, ge=1)
    llm_gateway_requests_per_day: int = Field(default=1000, ge=1)
    llm_gateway_max_output_tokens: int = Field(default=393216, ge=256, le=393216)
    llm_gateway_max_request_bytes: int = Field(default=32 * 1024 * 1024, ge=1024)

    @field_validator("llm_gateway_upstream_base_url", "llm_gateway_search_base_url")
    @classmethod
    def _validate_llm_gateway_upstream_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password \
                or parsed.query or parsed.fragment:
            raise ValueError("LLM gateway upstream must be an HTTPS URL without credentials or query")
        return value.rstrip("/")

    # 微信小程序：登录与通知
    wechat_miniapp_appid: str | None = None
    wechat_miniapp_secret: str | None = None
    wechat_miniapp_code2session_url: str = "https://api.weixin.qq.com/sns/jscode2session"
    wechat_miniapp_phone_url: str = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"
    wechat_miniapp_stable_token_url: str = "https://api.weixin.qq.com/cgi-bin/stable_token"
    wechat_miniapp_subscribe_send_url: str = "https://api.weixin.qq.com/cgi-bin/message/subscribe/send"
    wechat_miniapp_subscribe_state: str = "formal"
    wechat_miniapp_qr_env_version: str = "release"
    wechat_employee_qr_login_url_prefix: str = ""
    employee_qr_login_ttl_seconds: int = 120
    wechat_employee_bind_url_prefix: str = ""
    employee_wechat_binding_ttl_seconds: int = 300
    wechat_miniapp_request_timeout_seconds: int = Field(default=10, ge=1)
    # 微信服务号：模板消息通知
    wechat_official_appid: str | None = None
    wechat_official_secret: str | None = None
    wechat_official_token_url: str = "https://api.weixin.qq.com/cgi-bin/token"
    wechat_official_stable_token_url: str = "https://api.weixin.qq.com/cgi-bin/stable_token"
    wechat_official_template_send_url: str = "https://api.weixin.qq.com/cgi-bin/message/template/send"
    wechat_official_oauth_authorize_url: str = "https://open.weixin.qq.com/connect/oauth2/authorize"
    wechat_official_oauth_token_url: str = "https://api.weixin.qq.com/sns/oauth2/access_token"
    wechat_official_user_info_url: str = "https://api.weixin.qq.com/cgi-bin/user/info"
    wechat_official_account_name: str | None = None
    wechat_official_qr_code_url: str | None = None
    wechat_official_bind_callback_url: str | None = None
    wechat_official_bind_success_redirect_url: str | None = None
    wechat_official_bind_failure_redirect_url: str | None = None
    wechat_official_bind_state_ttl_seconds: int = Field(default=600, ge=60, le=1800)
    wechat_official_request_timeout_seconds: int = Field(default=10, ge=1)
    # 统一收银台前端公网基址（勿带末尾 /）；二维码为 {base}/cashier?token=...
    unified_payment_public_base_url: str | None = None

    @field_validator("default_tenant_no")
    @classmethod
    def _validate_default_tenant_no(cls, value: str) -> str:
        return validate_tenant_no(value)

    @property
    def default_tenant_schema(self) -> str:
        return tenant_schema_name(self.default_tenant_no)

    @field_validator("database_pool_max_size")
    @classmethod
    def _validate_database_pool_max_size(cls, value: int, info) -> int:
        min_size = info.data.get("database_pool_min_size")
        if isinstance(min_size, int) and value < min_size:
            raise ValueError("DATABASE_POOL_MAX_SIZE must be greater than or equal to DATABASE_POOL_MIN_SIZE")
        return value

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            secret = (self.jwt_secret or "").strip()
            if len(secret) < 32 or secret in {"change-me", "change-me-to-a-long-random-secret"}:
                raise ValueError("生产环境必须配置长度不少于 32 位的强随机 JWT_SECRET")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
