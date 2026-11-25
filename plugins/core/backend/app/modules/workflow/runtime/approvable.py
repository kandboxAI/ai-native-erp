"""供业务模块使用：当前用户待办理的流程实例（子查询），如“待我审批的请假”。"""

from __future__ import annotations

from uuid import UUID

from app.modules.workflow.runtime.repository import runtime_repository


def pending_instance_ids_for_user(user_id: UUID):
    """子查询：用户是候选人、且尚未投票的待办所属实例 ID。"""
    return runtime_repository.pending_instance_ids_for_user(user_id)
