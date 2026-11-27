"""离线覆盖导入口径、敏感信息处理、组织边界与重复导入。"""
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.modules.sample_app.api import business_user
from app.modules.sample_app.excel_source import SourceRow, is_note, mask_account, ledger_difference
from app.modules.sample_app.import_service import project_contract, import_workbook
from app.framework.db.tenant import use_tenant_schema


def test_subtotals_are_not_employees_or_projects():
    assert is_note(SourceRow("工资概览", 7, {"发薪主体": "测试主体", "姓名": "合计"}))
    assert is_note(SourceRow("项目台账", 22, {"项目名称": "应收总计"}))
    assert not is_note(SourceRow("人员薪资", 2, {"姓名": "测试员工"}))


def test_accounts_are_irreversibly_masked_before_persistence():
    assert mask_account("1234 5678 9012 3456") == "****3456"
    assert mask_account(None) is None


def test_contract_requires_reconciling_totals_or_explicit_usd():
    assert project_contract({"合同总价": "44500", "已回款": "44750", "应收(总价-已付)": "-250"}) == ("CNY", Decimal("44500"), Decimal("44750"))
    assert project_contract({"合同总价": "160"}) is None
    assert project_contract({"合同总价": "4K USD"}) == ("USD", Decimal("4000"), None)
    assert project_contract({"合同总价": "100", "已回款": "30", "应收(总价-已付)": "90"}) is None


def test_ledger_differences_preserve_negative_interest_and_zero():
    assert ledger_difference({"工资+社保": "100", "固定支出": "0", "报销/零散": "2", "手续费/利息": "-6", "支出合计": "96"}) == 0
    assert ledger_difference({"工资+社保": "100", "固定支出": "0", "报销/零散": "2", "手续费/利息": "0", "支出合计": "120"}) == 18


async def _selecting_another_org_requires_access_and_does_not_mutate_user():
    own, other = uuid4(), uuid4()
    user = AuthenticatedUser(auth_user_id=uuid4(), tenant_id=uuid4(), tenant_no="test", tenant_schema="t_test", user_id=uuid4(), org_id=own,
                             permission_scopes={"sample_app:access": "organization"})
    with pytest.raises(AppException):
        await business_user(user=user, org_id=other)
    user.org_ids = [own, other]
    selected = await business_user(user=user, org_id=other)
    assert selected.selected_org_id == other
    assert selected.user is user
    assert user.org_id == own


async def _same_source_is_idempotent_without_any_business_writes():
    @asynccontextmanager
    async def session():
        yield SimpleNamespace()
    source = SourceRow("说明", 2, {"项目": "说明"})
    with patch("app.modules.sample_app.import_service.read_source", return_value=("abc", [source])), \
         patch("app.modules.sample_app.import_service.get_session_context", session), \
         patch("app.modules.sample_app.import_repository.lock_import", new_callable=AsyncMock), \
         patch("app.modules.sample_app.import_repository.imported_rows", new_callable=AsyncMock, return_value=[SimpleNamespace(source_sha256="abc")]), \
         patch("app.modules.sample_app.import_repository.insert", new_callable=AsyncMock) as insert:
        with use_tenant_schema("t_test"):
            result = await import_workbook(Path("test.xlsx"), uuid4(), apply=True)
        assert result["mode"] == "already_imported"
        insert.assert_not_called()


def test_selecting_another_org_requires_access_and_does_not_mutate_user():
    _complete(_selecting_another_org_requires_access_and_does_not_mutate_user())


def test_same_source_is_idempotent_without_any_business_writes():
    _complete(_same_source_is_idempotent_without_any_business_writes())


def _complete(coroutine):
    # 本文件全部await都为立即完成的mock，不建立Windows网络事件循环。
    try:
        coroutine.send(None)
    except StopIteration:
        return
    finally:
        coroutine.close()
    raise AssertionError("测试意外产生了真实异步I/O")
