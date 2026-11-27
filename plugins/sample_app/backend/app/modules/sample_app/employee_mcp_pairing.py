"""本地 MCP 的浏览器配对；设备密钥只交本地进程，浏览器不得获知。"""
import hashlib
import json
import secrets
from app.integrations.redis_client import get_redis
from app.core.exceptions import AppException

TTL = 300


def key(kind, value):
    return "sample_app:employee-mcp:" + kind + ":" + hashlib.sha256(value.encode()).hexdigest()


async def start():
    device, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    redis = get_redis()
    await redis.set(key("device", device), "pending", ex=TTL)
    await redis.set(key("browser", browser), key("device", device), ex=TTL)
    return {"device_code": device, "browser_code": browser, "expires_in": TTL}


async def approve(browser_code, token):
    # 对浏览器代码、设备等待状态和一次性交付做原子检查，不允许重复授权覆盖。
    updated = await get_redis().eval("""
local device = redis.call('GET', KEYS[1])
if not device or redis.call('GET', device) ~= 'pending' then return 0 end
redis.call('SETEX', device, ARGV[1], ARGV[2])
redis.call('DEL', KEYS[1])
return 1
""", 1, key("browser", browser_code), TTL, json.dumps(token))
    if not updated:
        raise AppException("配对已过期或已使用，请在 AI 中重试", status_code=410)


async def poll(device_code):
    raw = await get_redis().eval("""
local value = redis.call('GET', KEYS[1])
if value and value ~= 'pending' then redis.call('DEL', KEYS[1]) end
return value
""", 1, key("device", device_code))
    if raw is None:
        return {"status": "expired"}
    if raw == "pending":
        return {"status": "pending"}
    return {"status": "authorized", **json.loads(raw)}
