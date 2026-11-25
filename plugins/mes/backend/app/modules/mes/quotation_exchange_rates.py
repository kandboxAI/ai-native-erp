"""询价采用使用的 ECB 日参考汇率；只向固定公开来源发送币种，不发送业务资料。"""
import asyncio
import base64
import hashlib
import hmac
import json
from time import monotonic
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppException


CURRENCIES = {"CNY", "EUR", "USD"}
PROVIDER = "Frankfurter / ECB"
CACHE_SECONDS = 3600


def signing_key():
    # 用途隔离，仅证明公开参考值来自本服务，不是身份或授权令牌。
    return hmac.digest(get_settings().jwt_secret.encode(), b"mes-quotation-fx-reference-v1", "sha256")


def seal_reference(value):
    payload = base64.urlsafe_b64encode(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).decode()
    return payload + "." + hmac.new(signing_key(), payload.encode(), hashlib.sha256).hexdigest()


def reference_note(reference, base, quotes, used_rate):
    if not reference:
        return "汇率来源：人工填写" if used_rate is not None and quotes - {base} else ""
    try:
        payload, signature = reference.split(".")
        expected = hmac.new(signing_key(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        value = json.loads(base64.urlsafe_b64decode(payload))
        if value["base"] != base or value["quote"] not in quotes - {base} or used_rate is None:
            raise ValueError()
        adjusted = Decimal(value["rate"]) != used_rate
    except (ValueError, KeyError, TypeError, InvalidOperation):
        raise AppException("汇率参考信息无效，请重新获取参考汇率或改为人工填写", 422)
    return (f"汇率来源：{value['provider']}，参考日期 {value['rate_date']}，获取时间 {value['fetched_at']}"
        f"，参考值 1 {base} = {value['rate']} {value['quote']}" + ("，已人工调整" if adjusted else ""))


class ExchangeRates:
    def __init__(self):
        self.cache = {}
        self.locks = {}

    async def get(self, base, quote):
        if base not in CURRENCIES or quote not in CURRENCIES or base == quote:
            raise AppException("请选择不同的有效币种获取参考汇率", 422)
        pair = (base, quote)
        async with self.locks.setdefault(pair, asyncio.Lock()):
            cached = self.cache.get(pair)
            if cached and cached[0] > monotonic():
                return dict(cached[1])
            try:
                async with httpx.AsyncClient(timeout=6, follow_redirects=False) as client:
                    response = await client.get(
                        f"https://api.frankfurter.dev/v2/providers/ecb/rate/{base.lower()}/{quote.lower()}")
                    response.raise_for_status()
                    # Decimal 解析避免先经过二进制浮点，再按采用接口精度取整。
                    value = json.loads(response.text, parse_float=Decimal)
                observed = date.fromisoformat(value["date"])
                rate = Decimal(str(value["rate"]))
                if (value["base"] != base or value["quote"] != quote
                        or not 0 <= (datetime.now(timezone.utc).date() - observed).days <= 14
                        or not rate.is_finite() or not 0 < rate <= 1000000):
                    raise ValueError()
                rate = rate.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
                if rate <= 0:
                    raise ValueError()
            except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation):
                raise AppException("暂时无法获取有效参考汇率，请稍后重试或人工填写汇率", 503)
            result = dict(base=base, quote=quote, rate=str(rate), rate_date=observed.isoformat(),
                provider=PROVIDER, fetched_at=datetime.now(timezone.utc).isoformat())
            result["reference"] = seal_reference(result)
            self.cache[pair] = (monotonic() + CACHE_SECONDS, result)
            return dict(result)


exchange_rates = ExchangeRates()
