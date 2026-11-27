"""软件报销工资月归属规则（纯函数，服务端与本地工具共用，不访问数据库）。

- 所属工资月优先取凭证明确标注的所属账期（billing_month）；未标注时取扣款日期所在月（occurred_on）。
- 两者都无法确定时不得推断，须询问用户；询问时给出时间窗建议：每月 1 日至 5 日（含）上传的记录建议归上月，其余归本月。
- 可申报的工资月为上月、本月、下月（支持预付下月账单）。
- 一次申报只对应一个工资月，同一工资月内的明细才能一并提交。
"""
from datetime import date


def _shift(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _text(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def resolved_billing_month(occurred_on: date | None, billing_month: str | None) -> str | None:
    """单条明细的所属工资月：凭证标注的账期优先，否则为扣款日期所在月，都没有则为 None。"""
    if billing_month:
        return billing_month
    if occurred_on is not None:
        return _text(occurred_on)
    return None


def suggest_period_month(today: date) -> str:
    """上传时间窗建议：本月 5 日（含）前归上月，之后归本月。"""
    first = today.replace(day=1)
    return _text(_shift(first, -1) if today.day <= 5 else first)


def allowed_period_months(today: date) -> set[str]:
    first = today.replace(day=1)
    return {_text(_shift(first, offset)) for offset in (-1, 0, 1)}


def billing_problem(period_month: str, billing_months: list[str | None], today: date) -> dict | None:
    """billing_months 为各条明细经 resolved_billing_month 解析后的结果。

    返回需要向用户或 AI 说明的结构；全部归属于申报工资月时返回 None。
    """
    missing = [index + 1 for index, value in enumerate(billing_months) if value is None]
    if missing:
        suggested = suggest_period_month(today)
        return {
            "status": "needs_input",
            "missing_fields": ["items.occurred_on"],
            "missing_items": missing,
            "suggested_period_month": suggested,
            "question": (f"第 {', '.join(map(str, missing))} 条扣款的日期和所属账期在凭证中都无法确定。"
                         f"请告知这些记录属于哪个工资月（按上传时间规则建议 {suggested}）；"
                         "凭证未明确显示时不得推断，请由本人确认后再提交。"),
        }
    other = [(index + 1, value) for index, value in enumerate(billing_months) if value != period_month]
    if other:
        months = sorted({value for _, value in other})
        return {
            "status": "needs_split",
            "period_month": period_month,
            "conflicting_months": months,
            "question": (f"部分扣款所属月份为 {', '.join(months)}，与申报工资月 {period_month} 不一致。"
                         "一次只能申报一个工资月，请按月分别提交。"),
        }
    return None
