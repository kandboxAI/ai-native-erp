"""Version-one wire protocol and explicit provider configuration, without ERP types."""
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiscoveryError(Exception):
    """Safe public error mapped to the host framework's response by its adapter."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class DiscoveryRequest(StrictModel):
    action: Literal["domains", "search", "describe", "validate", "metric"]
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    ids: list[str] = Field(default_factory=list, max_length=6)
    domain_ids: list[str] = Field(default_factory=list, max_length=8)
    kinds: list[Literal["resource", "operation", "metric"]] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=8, ge=1, le=12)
    catalog_revision: str | None = Field(default=None, max_length=80)
    # Query/filter languages belong to each ERP. Adapters must validate these objects.
    query: dict[str, Any] | None = None
    metric_id: str | None = Field(default=None, max_length=160)
    filters: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    group_by: list[str] = Field(default_factory=list, max_length=3)
    offset: int = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def required_arguments(self):
        if self.action == "search" and not self.question:
            raise ValueError("search requires question")
        if self.action == "describe" and not self.ids:
            raise ValueError("describe requires ids")
        if self.action == "validate" and self.query is None:
            raise ValueError("validate requires query")
        if self.action == "metric" and not self.metric_id:
            raise ValueError("metric requires metric_id")
        if self.action in ("describe", "validate", "metric") and not self.catalog_revision:
            raise ValueError("this operation requires catalog_revision")
        return self


class DiscoverySettings(StrictModel):
    embedding_url: str | None = None
    embedding_api_key: str | None = Field(default=None, repr=False)
    embedding_model: str = ""
    embedding_dimensions: int = Field(default=1024, ge=1, le=16000)
    embedding_batch_size: int = Field(default=16, ge=1, le=64)
    # Some older OpenAI-compatible providers reject dimensions. Opt out explicitly.
    embedding_send_dimensions: bool = True
    timeout_seconds: float = Field(default=10, gt=0, le=60)
    recall_limit: int = Field(default=30, ge=12, le=100)
    lexical_enabled: bool = True
    rerank_url: str | None = None
    rerank_api_key: str | None = Field(default=None, repr=False)
    rerank_model: str = ""
    # Wire protocol is independent of the model name and provider hostname.
    rerank_protocol: Literal["compatible", "dashscope"] = "compatible"
    rerank_instruct: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("embedding_url", "rerank_url")
    @classmethod
    def safe_endpoint(cls, value):
        if not value:
            return None
        url = urlsplit(value)
        if not url.hostname or url.username or url.password or url.query or url.fragment \
                or (url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"})):
            raise ValueError("Discovery endpoint requires HTTPS or loopback HTTP without URL credentials")
        return value
