"""业务模块接入审批流的登记表。

审批流不导入任何业务模块；业务模块在导入时登记：
- 状态回调（started / task_completed / completed / rejected / cancelled）：register_business_hooks
- 业务适配（名称、摘要、详情、流程变量、业务关系人解析）：register_business_adapter
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.schemas import AuthenticatedUser


@dataclass
class WorkflowHookContext:
    session: AsyncSession
    instance_id: UUID
    business_type_code: str
    business_id: UUID
    org_id: UUID
    status_code: str
    current_user: AuthenticatedUser | None = None
    comment: str | None = None
    payload: dict[str, Any] | None = None


HookHandler = Callable[[WorkflowHookContext], Awaitable[None]]

BUSINESS_HANDLERS: dict[str, dict[str, HookHandler]] = {}


def register_business_hooks(business_type_code: str, handlers: dict[str, HookHandler]) -> None:
    BUSINESS_HANDLERS.setdefault(business_type_code, {}).update(handlers)


async def dispatch_hook(business_type_code: str, event: str, ctx: WorkflowHookContext) -> None:
    handler = BUSINESS_HANDLERS.get(business_type_code, {}).get(event)
    if handler is not None:
        await handler(ctx)
    if event == "started":
        adapter = get_business_adapter(business_type_code)
        if adapter and adapter.analysis_prepare and adapter.analysis_run:
            from app.modules.workflow.analysis_service import queue_after_commit
            await queue_after_commit(ctx.session, ctx.instance_id)



# 业务关系人：按业务单据解析出候选用户（sys_user.id），如“请假学生所在班级的当前班主任”
BusinessOwnerResolver = Callable[[AsyncSession, UUID], Awaitable[list[UUID]]]


@dataclass(frozen=True)
class BusinessOwnerDef:
    key: str
    label: str
    resolve: BusinessOwnerResolver


@dataclass
class WorkflowBusinessAdapter:
    business_type_code: str
    label: str
    # 直接调用 /api/workflow_runtime/start 发起该业务流程需要的权限
    start_permission: str | None = None
    # 业务单据 ORM 模型：用于“驳回后须先修改原单据再重新发起”的判断（读取 updated_at）
    record_model: Any | None = None
    summary: Callable[[AsyncSession, UUID], Awaitable[str | None]] | None = None
    detail: Callable[[AsyncSession, UUID], Awaitable[dict[str, Any]]] | None = None
    # 重新发起时，用修改后的业务单刷新流程条件变量
    variables: Callable[[AsyncSession, UUID], Awaitable[dict[str, Any]]] | None = None
    business_owners: dict[str, BusinessOwnerDef] = field(default_factory=dict)
    # 业务模块自己发送审批结果通知（如 request_review.approved）时为 True，审批流不再发送通用的 workflow.instance.completed
    notifies_result: bool = False
    detail_access: Callable[[AsyncSession, UUID, AuthenticatedUser], Awaitable[bool]] | None = None
    # 业务提供限定范围、脱敏的事实与分析模型，底座不引入行业语义。
    analysis_prepare: Callable[[AsyncSession, UUID, AuthenticatedUser], Awaitable[dict]] | None = None
    analysis_run: Callable[[dict], Awaitable[tuple[str, str]]] | None = None
    analysis_access: Callable[[AsyncSession, UUID, AuthenticatedUser], Awaitable[bool]] | None = None
    allow_quick_approve: bool = False

    start_permissions: tuple[str, ...] = ()
    # 待办卡片的关键事实，由业务提供，避免底座识别行业字段。
    todo_summary: Callable[[AsyncSession, UUID], Awaitable[str | None]] | None = None
    avatar: Callable[[AsyncSession, UUID], Awaitable[str | None]] | None = None

    def may_start(self, user: AuthenticatedUser) -> bool:
        permissions = (self.start_permission,) + self.start_permissions
        return not any(permissions) or any(key in user.permissions for key in permissions if key)


BUSINESS_ADAPTERS: dict[str, WorkflowBusinessAdapter] = {}


def register_business_adapter(adapter: WorkflowBusinessAdapter) -> None:
    BUSINESS_ADAPTERS[adapter.business_type_code] = adapter


def get_business_adapter(business_type_code: str) -> WorkflowBusinessAdapter | None:
    return BUSINESS_ADAPTERS.get(business_type_code)


def business_owner_def(business_type_code: str, key: str) -> BusinessOwnerDef | None:
    adapter = BUSINESS_ADAPTERS.get(business_type_code)
    return adapter.business_owners.get(key) if adapter else None
