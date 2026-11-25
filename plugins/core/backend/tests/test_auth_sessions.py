import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI, HTTPException
from redis.asyncio import Redis

from app.auth import api, service, token
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import register_exception_handlers


class MemoryRedis:
    def __init__(self, clock):
        self.clock = clock
        self.values = {}
        self.expiries = {}
        self.sets = {}

    async def get(self, key):
        if self.expiries.get(key, float("inf")) <= self.clock.now(UTC).timestamp():
            self.values.pop(key, None)
        return self.values.get(key)

    async def eval(self, script, key_count, old_key, new_key, index_key, ttl, payload, old_token, new_token):
        if old_token and not await self.get(old_key):
            return 0
        index_ttl = max(ttl, await self.ttl(index_key))
        await self.setex(new_key, ttl, payload)
        if old_token:
            self.values.pop(old_key, None)
            await self.srem(index_key, old_token)
        await self.sadd(index_key, new_token)
        await self.expire(index_key, index_ttl)
        return 1

    async def setex(self, key, ttl, value):
        self.values[key] = value
        self.expiries[key] = int(self.clock.now(UTC).timestamp()) + ttl

    async def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)

    async def srem(self, key, value):
        self.sets.get(key, set()).discard(value)

    async def expire(self, key, ttl):
        self.expiries[key] = int(self.clock.now(UTC).timestamp()) + ttl

    async def ttl(self, key):
        if key not in self.values and key not in self.sets:
            return -2
        if key not in self.expiries:
            return -1
        return max(-2, self.expiries[key] - int(self.clock.now(UTC).timestamp()))


@pytest.fixture
def auth_environment(monkeypatch):
    start = datetime.now(UTC).replace(microsecond=0)

    class Clock(datetime):
        offset = timedelta()

        @classmethod
        def now(cls, tz=None):
            return (start + cls.offset).astimezone(tz)

    settings = SimpleNamespace(
        jwt_secret="test-secret-for-auth-session-tests-only",
        access_token_audience="test-erp",
        jwt_access_expire_minutes=120,
        jwt_refresh_expire_days=30,
        auth_session_expire_hours=12,
        auth_login_rate_limit_per_minute=10,
        auth_login_account_rate_limit_per_15_minutes=20,
        auth_refresh_rate_limit_per_minute=30,
    )
    redis = MemoryRedis(Clock)
    user_id = uuid4()
    tenant_id = uuid4()
    tenant_user_id = uuid4()
    for module in (token, service, api):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    for module in (token, service):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(token, "get_redis", lambda: redis)

    async def authenticate(email, password, portal=None, requested_tenant=None):
        return AuthenticatedUser(auth_user_id=user_id, tenant_id=requested_tenant or tenant_id, tenant_no="test",
                                 tenant_schema="t_test", user_id=tenant_user_id, email=email)

    async def noop(*args, **kwargs):
        return None

    async def active(*args):
        return False

    monkeypatch.setattr(service, "authenticate_with_password", authenticate)
    monkeypatch.setattr(service.online_user_registry, "is_session_revoked", active)
    monkeypatch.setattr(api.online_user_registry, "clear_session_revocation", noop)
    monkeypatch.setattr(api, "verify_login_captcha", noop)
    monkeypatch.setattr(api, "enforce_fixed_window_rate_limit", noop)
    monkeypatch.setattr(api, "append_login_attempt", noop)
    app = FastAPI()
    app.include_router(api.router)
    register_exception_handlers(app)
    return SimpleNamespace(clock=Clock, start=int(start.timestamp()), settings=settings,
                           redis=redis, user_id=user_id, tenant_id=tenant_id, tenant_user_id=tenant_user_id, app=app)


def post(environment, path, payload):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=environment.app),
                                     base_url="http://test") as client:
            return await client.post(path, json=payload)
    return asyncio.run(run())


def login_payload(**options):
    return {"login_name": "tester@example.com", "password": "test-password",
            "captcha_id": "captcha", "captcha_code": "1234", **options}


@pytest.mark.parametrize("remember,days,seconds", [
    (True, 1, 86400), (True, 7, 7 * 86400), (True, 30, 30 * 86400),
    (False, 7, 12 * 3600),
])
def test_login_api_sets_requested_fixed_deadline(auth_environment, remember, days, seconds):
    env = auth_environment
    response = post(env, "/api/auth/login", login_payload(remember_me=remember, remember_days=days))
    assert response.status_code == 200
    session = response.json()["data"]["session"]
    assert session["remember_me"] is remember
    assert session["session_expires_at"] == env.start + seconds
    assert session["expires_in"] == 7200
    claims = token.verify_access_token(session["access_token"])
    assert claims["exp"] <= session["session_expires_at"]
    assert claims["sub"] == str(env.user_id)
    assert claims["tenant_id"] == str(env.tenant_id)
    saved = asyncio.run(token.verify_refresh_token(session["refresh_token"]))
    assert saved.tenant_id == env.tenant_id
    assert saved.expires_at == session["session_expires_at"]
    assert saved.remember_me is remember


def test_refresh_does_not_extend_deadline_and_caps_access_token_near_expiry(auth_environment):
    env = auth_environment
    session = post(env, "/api/auth/login", login_payload(remember_me=True)).json()["data"]["session"]
    env.clock.offset = timedelta(days=6, hours=23, minutes=30)
    response = post(env, "/api/auth/refresh", {"refresh_token": session["refresh_token"]})
    assert response.status_code == 200
    refreshed = response.json()["data"]
    assert refreshed["remember_me"] is True
    assert refreshed["session_expires_at"] == session["session_expires_at"]
    assert refreshed["expires_in"] == 1800
    assert refreshed["expires_at"] == session["session_expires_at"]
    assert refreshed["refresh_token"] != session["refresh_token"]
    claims = jwt.decode(refreshed["access_token"], env.settings.jwt_secret, algorithms=["HS256"],
                        audience=env.settings.access_token_audience, options={"verify_iat": False})
    assert claims["exp"] == session["session_expires_at"]
    assert claims["tenant_id"] == str(env.tenant_id)
    assert post(env, "/api/auth/refresh", {"refresh_token": session["refresh_token"]}).status_code == 401
    env.clock.offset = timedelta(days=7)
    assert post(env, "/api/auth/refresh", {"refresh_token": refreshed["refresh_token"]}).status_code == 401


def test_temporary_refresh_preserves_short_session_policy(auth_environment):
    env = auth_environment
    session = post(env, "/api/auth/login", login_payload()).json()["data"]["session"]
    env.clock.offset = timedelta(hours=3)
    response = post(env, "/api/auth/refresh", {"refresh_token": session["refresh_token"]})
    refreshed = response.json()["data"]
    assert refreshed["remember_me"] is False
    assert refreshed["session_expires_at"] == env.start + 12 * 3600
    env.clock.offset = timedelta(hours=12)
    assert post(env, "/api/auth/refresh", {"refresh_token": refreshed["refresh_token"]}).status_code == 401


@pytest.mark.parametrize("options", [
    {"remember_days": 0}, {"remember_days": 31}, {"remember_days": True},
    {"remember_days": "7"}, {"remember_me": "true"},
])
def test_login_rejects_invalid_remember_policy(auth_environment, options):
    assert post(auth_environment, "/api/auth/login", login_payload(**options)).status_code == 422


def test_login_enforces_configured_maximum(auth_environment):
    env = auth_environment
    env.settings.jwt_refresh_expire_days = 7
    response = post(env, "/api/auth/login", login_payload(remember_me=True, remember_days=30))
    assert response.status_code == 400
    assert response.json()["message"] == "免登录期限不能超过 7 天"
    assert not env.redis.values


def test_legacy_refresh_keeps_remaining_redis_lifetime(auth_environment):
    env = auth_environment
    asyncio.run(env.redis.setex(f"{token.REFRESH_KEY_PREFIX}legacy", 3600,
                                json.dumps({"user_id": str(env.user_id), "email": "tester@example.com", "tenant_id": str(env.tenant_id)})))
    session = post(env, "/api/auth/refresh", {"refresh_token": "legacy"}).json()["data"]
    assert session["session_expires_at"] == env.start + 3600
    assert session["expires_in"] == 3600
    env.clock.offset = timedelta(minutes=30)
    refreshed = post(env, "/api/auth/refresh", {"refresh_token": session["refresh_token"]}).json()["data"]
    assert refreshed["session_expires_at"] == session["session_expires_at"]


def test_expired_session_cannot_issue_new_access_token(auth_environment):
    with pytest.raises(HTTPException) as failure:
        token.create_access_token(auth_environment.user_id, "tester@example.com", auth_environment.tenant_id,
                                  session_expires_at=auth_environment.start)
    assert failure.value.status_code == 401


def test_pre_tenant_refresh_token_requires_new_login(auth_environment):
    env = auth_environment
    asyncio.run(env.redis.setex(f"{token.REFRESH_KEY_PREFIX}unbound", 3600,
                                json.dumps({"user_id": str(env.user_id), "email": "tester@example.com"})))
    assert post(env, "/api/auth/refresh", {"refresh_token": "unbound"}).status_code == 401


def test_refresh_keeps_the_tenant_selected_at_login(auth_environment):
    env = auth_environment
    selected = uuid4()
    session = post(env, "/api/auth/login", login_payload(tenant_id=str(selected), remember_me=True)).json()["data"]["session"]
    refreshed = post(env, "/api/auth/refresh", {"refresh_token": session["refresh_token"]}).json()["data"]
    assert token.verify_access_token(refreshed["access_token"])["tenant_id"] == str(selected)
    assert asyncio.run(token.verify_refresh_token(refreshed["refresh_token"])).tenant_id == selected


def test_duplicate_rotation_produces_only_one_successor(auth_environment):
    env = auth_environment
    session = post(env, "/api/auth/login", login_payload(remember_me=True)).json()["data"]["session"]

    async def run():
        saved = await token.verify_refresh_token(session["refresh_token"])
        return await asyncio.gather(token.rotate_refresh_token(session["refresh_token"], saved),
                                    token.rotate_refresh_token(session["refresh_token"], saved),
                                    return_exceptions=True)

    results = asyncio.run(run())
    assert sum(isinstance(item, str) for item in results) == 1
    assert sum(isinstance(item, HTTPException) and item.status_code == 401 for item in results) == 1


def test_short_session_does_not_shorten_user_revocation_index(auth_environment):
    env = auth_environment
    post(env, "/api/auth/login", login_payload(remember_me=True, remember_days=30))
    post(env, "/api/auth/login", login_payload(remember_me=False))
    assert asyncio.run(env.redis.ttl(f"{token.REFRESH_USER_SET_PREFIX}{env.user_id}")) == 30 * 86400


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("AUTH_SESSION_TEST_REDIS") != "1", reason="requires explicit Redis test opt-in")
def test_atomic_rotation_against_real_redis(monkeypatch):
    from app.core.config import get_settings

    user_id = uuid4()

    async def run():
        redis = Redis.from_url(get_settings().redis_url, decode_responses=True,
                               socket_connect_timeout=2, socket_timeout=2)
        monkeypatch.setattr(token, "get_redis", lambda: redis)
        try:
            await redis.ping()
            saved = token.RefreshSession(user_id, "test@example.com", True,
                                          int(datetime.now(UTC).timestamp()) + 60, uuid4())
            old = await token.issue_refresh_token(saved)
            results = await asyncio.gather(token.rotate_refresh_token(old, saved),
                                            token.rotate_refresh_token(old, saved), return_exceptions=True)
            successors = [item for item in results if isinstance(item, str)]
            assert len(successors) == 1
            assert any(isinstance(item, HTTPException) and item.status_code == 401 for item in results)
            assert await token.verify_refresh_token(successors[0]) == saved
            assert 0 < await redis.ttl(f"{token.REFRESH_KEY_PREFIX}{successors[0]}") <= 60
            assert await redis.smembers(f"{token.REFRESH_USER_SET_PREFIX}{user_id}") == {successors[0]}
        finally:
            await token.revoke_all_refresh_tokens(user_id)
            await redis.aclose()

    asyncio.run(run())
