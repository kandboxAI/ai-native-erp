"""微信小程序登录。

微信身份只绑定现有登录账号：首次登录通过微信授权手机号匹配
``public.auth_user.mobile``，不创建账号、不补写或修改手机号。
"""

from fastapi import status
from sqlalchemy.exc import IntegrityError

from app.auth.models import AuthIdentity
from app.auth.repository import repository
from app.auth.schemas import LoginResponse, WechatMiniappLoginRequest
from app.auth.service import login_with_auth_user_id
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.framework.db.session import get_session_context
from app.integrations.wechat_miniapp import client as wechat_client


WECHAT_MINIAPP_PROVIDER = "wechat_miniapp"
WECHAT_PHONE_REQUIRED_MESSAGE = "首次微信登录请授权手机号，用于匹配已存在的系统账号"
WECHAT_ACCOUNT_NOT_FOUND_MESSAGE = "该手机号未匹配到已开通的系统账号，请联系管理员"
WECHAT_ACCOUNT_DISABLED_MESSAGE = "该手机号对应的系统账号已停用，请联系管理员"
WECHAT_ALREADY_BOUND_MESSAGE = "该系统账号已绑定其他微信，请联系管理员处理"


async def login_with_wechat_miniapp(payload: WechatMiniappLoginRequest) -> LoginResponse:
    settings = get_settings()
    appid = (settings.wechat_miniapp_appid or "").strip()
    if not appid:
        raise AppException("未配置微信小程序 AppID", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # code 与 phone_code 都是一次性凭证，按顺序调用微信接口，避免重复消费。
    wechat_session = await wechat_client.code2session(payload.code)

    async with get_session_context() as session:
        identity = await repository.find_auth_identity(
            session,
            provider=WECHAT_MINIAPP_PROVIDER,
            appid=appid,
            external_user_no=wechat_session.openid,
        )
        if identity is not None:
            if wechat_session.unionid and identity.unionid != wechat_session.unionid:
                identity.unionid = wechat_session.unionid
                identity.updated_by = identity.auth_user_id
                session.add(identity)
                await session.commit()
            return await login_with_auth_user_id(identity.auth_user_id, payload.tenant_id)

    if not payload.phone_code:
        raise AppException(
            WECHAT_PHONE_REQUIRED_MESSAGE,
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
        )

    phone = (await wechat_client.get_phone_number(payload.phone_code)).pure_phone_number.strip()
    async with get_session_context() as session:
        auth_user = await repository.find_auth_user_by_login(session, email=None, mobile=phone)
        if auth_user is None:
            raise AppException(WECHAT_ACCOUNT_NOT_FOUND_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)
        if not auth_user.is_active:
            raise AppException(WECHAT_ACCOUNT_DISABLED_MESSAGE, status_code=status.HTTP_403_FORBIDDEN)

        existing_for_user = await repository.find_auth_identity_for_user(
            session,
            provider=WECHAT_MINIAPP_PROVIDER,
            appid=appid,
            auth_user_id=auth_user.id,
        )
        if existing_for_user is not None:
            raise AppException(WECHAT_ALREADY_BOUND_MESSAGE, status_code=status.HTTP_409_CONFLICT)

        # 并发首次绑定由数据库唯一索引兜底；不保存微信返回的手机号，
        # 更不会用它更新 auth_user.mobile。
        identity = AuthIdentity(
            auth_user_id=auth_user.id,
            provider=WECHAT_MINIAPP_PROVIDER,
            appid=appid,
            external_user_no=wechat_session.openid,
            unionid=wechat_session.unionid,
            created_by=auth_user.id,
            updated_by=auth_user.id,
        )
        session.add(identity)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise AppException(WECHAT_ALREADY_BOUND_MESSAGE, status_code=status.HTTP_409_CONFLICT) from exc

    return await login_with_auth_user_id(auth_user.id, payload.tenant_id)
