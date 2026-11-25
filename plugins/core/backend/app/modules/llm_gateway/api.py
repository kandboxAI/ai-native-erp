from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthenticatedUser
from app.core.response import success_response
from app.core.config import get_settings
from app.modules.llm_gateway import repository, service
from app.modules.llm_gateway.models import GatewayCredentialRequest

router = APIRouter(prefix="/api/llm-gateway", tags=["LLM Gateway"])


@router.post("/credential")
async def issue_gateway_credential(body: GatewayCredentialRequest,
                                   user: AuthenticatedUser = Depends(get_current_user)):
    issued = await service.issue_credential(user, body.client_id)
    return success_response(issued.model_dump())


@router.delete("/credential")
async def revoke_gateway_credential(x_api_key: str | None = Header(default=None),
                                    x_erp_client_id: str | None = Header(default=None)):
    await service.authenticate_credential(x_api_key, x_erp_client_id)
    await repository.revoke_credential(x_api_key)
    return success_response({})


@router.post("/anthropic/v1/messages")
async def messages(request: Request, x_api_key: str | None = Header(default=None),
                   x_erp_client_id: str | None = Header(default=None),
                   anthropic_version: str | None = Header(default=None),
                   anthropic_beta: str | None = Header(default=None)):
    return await _relay(request, x_api_key, x_erp_client_id, anthropic_version, anthropic_beta)


@router.post("/web-search/{client_id}/messages", include_in_schema=False)
async def search_messages(client_id: UUID, request: Request, x_api_key: str | None = Header(default=None),
                          anthropic_version: str | None = Header(default=None),
                          anthropic_beta: str | None = Header(default=None)):
    # DSH 原生搜索提供器不发送自定义 client-id 头；使用非秘密的运行实例 ID 完成同样校验。
    return await _relay(request, x_api_key, str(client_id), anthropic_version, anthropic_beta)


@router.post("/web-search/{client_id}/search", include_in_schema=False)
async def web_search(client_id: UUID, request: Request, x_api_key: str | None = Header(default=None)):
    identity = await service.authenticate_credential(x_api_key, str(client_id))
    return await service.search_web(identity, await _read_body(request))


async def _relay(request: Request, x_api_key: str | None, x_erp_client_id: str | None,
                 anthropic_version: str | None, anthropic_beta: str | None):
    identity = await service.authenticate_credential(x_api_key, x_erp_client_id)
    return await service.relay_messages(identity, await _read_body(request), anthropic_version, anthropic_beta)


async def _read_body(request: Request):
    maximum = get_settings().llm_gateway_max_request_bytes
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > maximum:
            raise HTTPException(status_code=413, detail="模型请求内容过大，请减少上下文或附件后重试")
        chunks.extend(chunk)
    return bytes(chunks)
