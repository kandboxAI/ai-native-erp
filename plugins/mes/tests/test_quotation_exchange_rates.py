"""公开汇率契约及缓存测试；HTTP 全部使用 MockTransport，不访问网络或业务库。"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.core.exceptions import AppException
from app.modules.mes import quotation_exchange_rates as fx


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(fx, "signing_key", lambda: b"test-only-reference-key")
    actual_client = httpx.AsyncClient
    today = datetime.now(timezone.utc).date()
    state = {"calls": [], "status": 200, "body": {
        "date": today.isoformat(), "base": "EUR", "quote": "CNY", "rate": 7.4846}, "clock": 0}

    async def reply(request):
        state["calls"].append(request)
        if state.get("timeout"):
            raise httpx.ReadTimeout("offline", request=request)
        return httpx.Response(state["status"], json=state["body"])

    monkeypatch.setattr(fx.httpx, "AsyncClient", lambda **kwargs: actual_client(
        **kwargs, transport=httpx.MockTransport(reply)))
    monkeypatch.setattr(fx, "monotonic", lambda: state["clock"])
    return state, fx.ExchangeRates()


def test_pair_direction_decimal_receipt_and_cache_are_stable(provider):
    state, rates = provider

    async def check():
        values = await asyncio.gather(*(rates.get("EUR", "CNY") for _ in range(5)))
        assert len(state["calls"]) == 1
        result = values[0]
        assert result["rate"] == "7.48460000"
        assert result["base"] == "EUR" and result["quote"] == "CNY"
        request = state["calls"][0]
        assert str(request.url) == "https://api.frankfurter.dev/v2/providers/ecb/rate/eur/cny"
        assert request.method == "GET" and not request.content
        assert "authorization" not in request.headers
        note = fx.reference_note(result["reference"], "EUR", {"CNY"}, Decimal("7.4846"))
        assert fx.PROVIDER in note and result["rate_date"] in note
        assert "人工调整" not in note
        assert "人工调整" in fx.reference_note(result["reference"], "EUR", {"CNY"}, Decimal("8"))
        result["rate"] = "999"  # 调用者不可改写缓存中的观察值。
        assert (await rates.get("EUR", "CNY"))["rate"] == "7.48460000"
        state["clock"] = fx.CACHE_SECONDS + 1
        state["body"]["rate"] = 8
        assert (await rates.get("EUR", "CNY"))["rate"] == "8.00000000"
        assert len(state["calls"]) == 2
        # 重新获取后旧参考仍能说明原采用时的汇率，不随缓存改变。
        assert "7.48460000" in fx.reference_note(result["reference"], "EUR", {"CNY"}, Decimal("7.4846"))

    asyncio.run(check())


@pytest.mark.parametrize("changes", [
    {"rate": 0}, {"rate": -1}, {"rate": "NaN"}, {"rate": 1000001},
    {"base": "CNY"}, {"quote": "USD"}, {"date": "invalid"},
    {"date": (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()},
    {"date": (datetime.now(timezone.utc).date() - timedelta(days=15)).isoformat()},
])
def test_invalid_or_stale_provider_data_never_becomes_rate_one(provider, changes):
    state, rates = provider
    state["body"].update(changes)
    with pytest.raises(AppException) as error:
        asyncio.run(rates.get("EUR", "CNY"))
    assert error.value.status_code == 503 and rates.cache == {}


@pytest.mark.parametrize("status,timeout", [(429, False), (500, False), (302, False), (200, True)])
def test_http_errors_keep_manual_fallback_and_do_not_reuse_expired_cache(provider, status, timeout):
    state, rates = provider

    async def check():
        await rates.get("EUR", "CNY")
        state.update(clock=fx.CACHE_SECONDS + 1, status=status, timeout=timeout)
        with pytest.raises(AppException, match="人工填写"):
            await rates.get("EUR", "CNY")

    asyncio.run(check())


def test_reference_tampering_and_wrong_currency_are_rejected(provider):
    _, rates = provider
    value = asyncio.run(rates.get("EUR", "CNY"))
    for reference, base, quotes in [
        (value["reference"] + "0", "EUR", {"CNY"}),
        (value["reference"], "USD", {"CNY"}),
        (value["reference"], "EUR", {"USD"}),
    ]:
        with pytest.raises(AppException) as error:
            fx.reference_note(reference, base, quotes, Decimal("8"))
        assert error.value.status_code == 422
    assert fx.reference_note(None, "EUR", {"CNY"}, Decimal("8")) == "汇率来源：人工填写"


@pytest.mark.parametrize("base,quote", [("GBP", "CNY"), ("EUR", "BTC"), ("EUR", "EUR")])
def test_unsupported_or_equal_currency_never_calls_provider(provider, base, quote):
    state, rates = provider
    with pytest.raises(AppException) as error:
        asyncio.run(rates.get(base, quote))
    assert error.value.status_code == 422 and not state["calls"]
