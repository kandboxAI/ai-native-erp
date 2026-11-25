from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.auth.schemas import LoginResponse


QrLoginStatus = Literal["pending", "scanned", "confirmed", "cancelled", "consumed"]


class EmployeeQrLoginSessionRecord(BaseModel):
    session_id: str
    scene: str
    browser_secret_hash: str
    status: QrLoginStatus = "pending"
    pc_ip: str = ""
    pc_user_agent: str = ""
    auth_user_id: str | None = None
    employee_name: str | None = None
    created_at: datetime
    scanned_at: datetime | None = None
    confirmed_at: datetime | None = None
    cancelled_at: datetime | None = None
    consumed_at: datetime | None = None


class EmployeeQrLoginSessionCreateResult(BaseModel):
    session_id: str
    browser_secret: str
    qr_url: str
    status: QrLoginStatus
    expires_in: int
    expires_at: datetime


class EmployeeQrLoginStatusItem(BaseModel):
    session_id: str
    status: QrLoginStatus | Literal["expired"]
    employee_name: str | None = None
    expires_in: int = 0


class EmployeeQrLoginBrowserRequest(BaseModel):
    browser_secret: str = Field(..., min_length=20, max_length=256)


class EmployeeQrLoginWechatRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=512)
    phone_code: str | None = Field(default=None, max_length=512)
    confirm: bool = False


class EmployeeQrLoginWechatResult(BaseModel):
    status: QrLoginStatus
    bound: bool
    requires_phone: bool
    employee_name: str | None = None
    login: LoginResponse | None = None
