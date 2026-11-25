from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GatewaySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=128)
    count: int = Field(default=5, ge=1, le=5, strict=True)


class GatewayCredentialRequest(BaseModel):
    client_id: UUID


class GatewayCredentialResponse(BaseModel):
    access_token: str
    expires_in: int


class GatewayIdentity(BaseModel):
    """auth_user_id / tenant_id：登录账号与会话租户（校验会话、重建当前用户）；user_id：租户内用户（配额与用量）。"""

    auth_user_id: UUID
    tenant_id: UUID
    user_id: UUID
    client_id: UUID
    email: str | None = None
