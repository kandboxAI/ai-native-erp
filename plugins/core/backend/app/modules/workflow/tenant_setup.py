"""幂等安装所选插件声明的审批模板；底座不预置业务流程。"""

from __future__ import annotations

from .definition.repository import repository
from .definition.service import compile_and_validate
from .design_models import default_designs
from app.framework.catalog import iter_module_attr
from .models import WfDefinition



async def setup_tenant(session, ctx, *, only: set[str] | None = None) -> None:
    designs = default_designs(only)
    definitions = [spec for module in iter_module_attr("workflow_defaults", only) for spec in getattr(module, "BUILTIN_DEFINITIONS", ())]
    for spec in definitions:
        if spec["business_type_code"] not in designs:
            raise ValueError("审批模板缺少对应的 DEFAULT_DESIGNS 工厂")
        if await repository.get_by_definition_no(session, spec["definition_no"]) is not None:
            continue
        # 发布默认流程会停用同组织同业务的其他默认流程，保留租户自建定义。
        if await repository.has_default_for_org(session, org_id=ctx.root_org_id,
                                               business_type_code=spec["business_type_code"]):
            continue
        definition = WfDefinition(
            org_id=ctx.root_org_id,
            is_active=False,
            created_by=ctx.admin_user_id,
            updated_by=ctx.admin_user_id,
            **spec,
        )
        await repository.add(session, definition)
        design, bpmn_process_no, bpmn_xml, _ = compile_and_validate(
            designs[spec["business_type_code"]](), spec["business_type_code"]
        )
        version = await repository.create_version(
            session,
            definition_id=definition.id,
            bpmn_xml=bpmn_xml,
            bpmn_process_no=bpmn_process_no,
            user_id=ctx.admin_user_id,
            remark="内置流程",
            spiff_spec_snapshot={"source": "designer_v3", "design": design.model_dump(mode="json")},
        )
        await repository.publish_version(session, version=version, definition=definition, user_id=ctx.admin_user_id)
