"""通用提示词及行业上下文的租户启用边界。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.ai_assistant import context_service
from app.modules.ai_assistant.context_schemas import ContextContribution, PositionKnowledge


@pytest.mark.parametrize("plugin_enabled", [False, True])
def test_context_uses_generic_instructions_and_only_enabled_plugin_facts(monkeypatch, plugin_enabled):
    @asynccontextmanager
    async def session():
        yield object()

    contribution = ContextContribution(
        facts=["当前岗位：机加工检验"],
        position_knowledge=[
            PositionKnowledge(
                position_id=uuid4(),
                position_name="机加工检验",
                knowledge_base_id=uuid4(),
                knowledge_base_name="检验规范",
                overview_document_id=uuid4(),
                can_contribute=True,
            ),
        ],
    )
    provider = SimpleNamespace(current_context=AsyncMock(return_value=contribution))
    manifest = SimpleNamespace(key="test_industry", ai_context_providers=["test_provider:provider"])
    monkeypatch.setattr(context_service, "get_session_context", session)
    monkeypatch.setattr(context_service, "loaded_plugin_manifests", lambda: [manifest])
    monkeypatch.setattr(context_service, "import_module", lambda _name: SimpleNamespace(provider=provider))
    for name, value in (
        ("preference", None),
        ("templates", []),
        ("role_ids", set()),
        ("template_preferences", []),
    ):
        monkeypatch.setattr(context_service.repository, name, AsyncMock(return_value=value))
    user = SimpleNamespace(
        role_names=["管理员"],
        enabled_plugin_keys=[manifest.key] if plugin_enabled else [],
    )

    context = asyncio.run(context_service.current_context(user))

    prompt = context["prompt"]
    assert "问候时，简短回应" in prompt
    assert "当前租户已启用的功能和账号权限" in prompt
    assert all(term not in prompt for term in ("班级", "课程", "学生"))
    if plugin_enabled:
        provider.current_context.assert_awaited_once_with(user)
        assert "当前岗位：机加工检验" in prompt
        assert "【岗位经验维护】" in prompt
    else:
        provider.current_context.assert_not_awaited()
        assert "机加工检验" not in prompt
