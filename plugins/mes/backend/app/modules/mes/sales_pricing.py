"""成交折扣以所选报价档原价为基数；七折是优惠下限，不冒充成本价。"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING

from app.core.exceptions import AppException

DISCOUNT_RATES = {Decimal(value) for value in ("1", "0.95", "0.9", "0.85", "0.8", "0.7")}


def discounted_price(original, rate):
    minimum = (original * Decimal("0.7")).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    return max(minimum, (original * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def validate_price(original, price, rate, drawing_no):
    minimum = discounted_price(original, Decimal("0.7"))
    if price < minimum:
        raise AppException(f"{drawing_no}：成交单价不能低于所选报价的七折（{minimum}）", 422)
    if rate is not None:
        if rate not in DISCOUNT_RATES:
            raise AppException("请选择有效的成交折扣档位，最低七折", 422)
        if price != discounted_price(original, rate):
            raise AppException(f"{drawing_no}：成交单价与所选折扣不一致，请重新核对", 422)
