from __future__ import annotations

import re

from app.core.config import get_settings

EMPLOYEE_LOGIN_EMAIL_DOMAIN = "admin.com"


def _is_cn_mobile(digits: str) -> bool:
    return len(digits) == 11 and digits.startswith("1")


def normalize_login_mobile(value: str | None) -> str:
    mobile = "".join((value or "").split())
    if not mobile.isascii() or not mobile.isdigit() or not _is_cn_mobile(mobile):
        raise ValueError("请输入以 1 开头的 11 位手机号")
    return mobile


def resolve_login_identity(login_name: str) -> tuple[str | None, str | None]:
    """登录名 → （邮箱, 手机号）：含 @ 按邮箱；11 位手机号按手机号；其余按员工登录名补全配置域名的邮箱。"""
    value = login_name.strip().lower()
    if "@" in value:
        return value, None
    digits = re.sub(r"\D", "", value)
    if _is_cn_mobile(digits) and digits == value:
        return None, digits
    return resolve_employee_login_email(value), None


def resolve_employee_login_email(login_name: str) -> str:
    """员工登录名统一转换为配置域名邮箱，完整邮箱保持不变。"""
    value = login_name.strip().lower()
    if "@" in value:
        return value
    domain = get_settings().employee_login_email_domain.strip().lstrip("@") or EMPLOYEE_LOGIN_EMAIL_DOMAIN
    return f"{value}@{domain}"
