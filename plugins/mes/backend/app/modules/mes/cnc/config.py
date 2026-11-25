"""询价解析参数；使用 MES 独立配置，兼容原 backend/.env。"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import BASE_DIR, get_settings
from app.framework.plugin_settings import load_plugin_settings
from app.framework.db.tenant import require_tenant_schema

ROOT = BASE_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MES_CNC_", extra="ignore")
    storage_dir: Path = ROOT / "storage/mes-cnc"
    max_concurrent_jobs: int = Field(default=1, ge=1, le=16)
    analysis_timeout_seconds: int = Field(default=240, ge=10, le=3600)
    ai_api_key: SecretStr = SecretStr("")
    ai_base_url: str = "https://api.deepseek.com"
    ai_model: str = "deepseek-flash"
    ai_request_timeout: int = Field(default=120, ge=10, le=300)
    ai_total_timeout: int = Field(default=360, ge=30, le=1800)
    paddleocr_access_token: SecretStr = SecretStr("")
    paddleocr_base_url: str = "https://paddleocr.aistudio-app.com"
    paddleocr_model: str = "PaddleOCR-VL-1.6"
    paddleocr_poll_timeout: int = Field(default=600, ge=10, le=1800)

    @property
    def storage(self) -> Path:
        # 后台任务与请求均须建立租户上下文，产物不能跨租户共用目录。
        directory = self.storage_dir if self.storage_dir.is_absolute() else ROOT / self.storage_dir
        path = directory / require_tenant_schema()
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()


@lru_cache
def settings() -> Settings:
    config = load_plugin_settings("mes", Settings)
    if not config.ai_api_key.get_secret_value():
        config.ai_api_key = SecretStr(get_settings().llm_gateway_deepseek_api_key or "")
    return config
