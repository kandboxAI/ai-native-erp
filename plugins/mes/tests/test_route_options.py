"""在选产品前浏览路线，仍限定组织、动作权限及最小物料信息。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.exceptions import AppException
from app.modules.mes import production_service as module
from app.modules.mes.production_service import production_service
from app.modules.mes.production_repository import production_repository
from app.modules.mes.schemas import ProcessTemplateQuery
from test_web_production import actor


def test_options_before_product_selection_include_minimal_product_context_and_cache_reads(monkeypatch):
    user=actor("mes:work_order:create")
    product_id=uuid4()
    rows=[SimpleNamespace(id=uuid4(),product_item_id=product_id) for _ in range(2)]
    reads=[]
    @asynccontextmanager
    async def sessions(): yield object()
    async def templates(session,query,current_user,**kwargs):
        assert query.org_id == user.org_id and query.product_item_id is None and query.is_active is True
        assert kwargs["permission"] == "mes:work_order:create"
        return rows,2
    async def item(session,row): return {"id":str(row.id),"product_item_id":str(row.product_item_id)}
    async def product(session,identifier):
        reads.append(identifier)
        return SimpleNamespace(id=identifier,item_no="P1",item_name="支架",unit_code="pcs")
    monkeypatch.setattr(module,"get_session_context",sessions)
    monkeypatch.setattr(production_repository,"templates",templates)
    monkeypatch.setattr(production_service,"template_item",item)
    monkeypatch.setattr(module,"get_active_item",product)
    result=asyncio.run(production_service.template_options(ProcessTemplateQuery(org_id=user.org_id),user))
    assert reads == [product_id]
    assert result["items"][0]["product_option"] == {"value":str(product_id),"label":"P1 · 支架","unit":"pcs"}
    assert result["items"][0]["is_product_active"] is True
    with pytest.raises(AppException): asyncio.run(production_service.template_options(ProcessTemplateQuery(org_id=uuid4()),user))
    with pytest.raises(AppException): asyncio.run(production_service.template_options(ProcessTemplateQuery(),user))
