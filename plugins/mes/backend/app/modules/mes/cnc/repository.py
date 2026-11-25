"""询价持久化；所有父对象先按当前动作权限过滤，再读取其明细。"""

from uuid import UUID

from sqlalchemy import delete, select, update, func

from app.auth.scope_filters import scoped_conditions, ensure_org_access
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from .models import (
    CncPart,
    CncOperation,
    CncDrawingFile,
    CncAnalysisJob,
    CncQuote,
    CncRuleSet,
    CncRuleEntry,
)
from .rules import RuleConfig
from .schemas import Specs, Operation

LIST = "mes:quote:list"
MANAGE = "mes:quote:manage"
ANALYZE = "mes:quote:analyze"
APPROVE = "mes:quote:approve"
RULES = "mes:quote:rules"
RULE_CATEGORIES = ("materials", "processes", "external_processes")


class CncRepository:
    def add(self, session, row):
        session.add(row)

    async def part(self, session, identifier, user, permission=LIST, *, lock=False, deleted=False):
        filters = scoped_conditions(CncPart, user, permission, include_deleted=deleted)
        query = select(CncPart).where(CncPart.id == identifier, *filters)
        if lock:
            query = query.with_for_update()
        row = (await session.execute(query)).scalar_one_or_none()
        if row is None:
            raise AppException("询价零件不存在或无权访问", 404)
        return row

    async def parts(self, session, user, deleted=False, search="", page=1, page_size=200):
        query = select(CncPart).where(*scoped_conditions(CncPart, user, LIST, include_deleted=deleted))
        query = query.where(CncPart.deleted_at.is_not(None) if deleted else CncPart.deleted_at.is_(None))
        if search.strip():
            query = query.where(CncPart.name.icontains(search.strip(), autoescape=True))
        return (
            (
                await session.execute(
                    query.order_by(CncPart.created_at.desc(), CncPart.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )

    async def operations(self, session, part_id):
        return (
            (
                await session.execute(
                    select(CncOperation).where(CncOperation.part_id == part_id).order_by(CncOperation.sort_no)
                )
            )
            .scalars()
            .all()
        )

    async def files(self, session, part_id):
        return (
            (await session.execute(select(CncDrawingFile).where(CncDrawingFile.part_id == part_id)))
            .scalars()
            .all()
        )

    async def jobs(self, session, part_id):
        return (
            (
                await session.execute(
                    select(CncAnalysisJob)
                    .where(CncAnalysisJob.part_id == part_id)
                    .order_by(CncAnalysisJob.created_at.desc(), CncAnalysisJob.id.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def active(self, session, part_id):
        return (
            (
                await session.execute(
                    select(CncAnalysisJob).where(
                        CncAnalysisJob.part_id == part_id,
                        CncAnalysisJob.status_code.in_(("queued", "running")),
                    )
                )
            )
            .scalars()
            .first()
        )

    async def quote(self, session, identifier):
        row = await session.get(CncQuote, identifier)
        if row is None:
            raise AppException("报价不存在", 404)
        return row

    async def quotes(self, session, part_id):
        return (
            (
                await session.execute(
                    select(CncQuote)
                    .where(CncQuote.part_id == part_id)
                    .order_by(CncQuote.created_at.desc(), CncQuote.id.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )

    async def save_inputs(self, session, part, specs, operations, user):
        for key, value in Specs.model_validate(specs).model_dump().items():
            setattr(part, key, value)
        existing = {str(row.id): row for row in await self.operations(session, part.id)}
        wanted = set()
        for index, item in enumerate(operations):
            values = Operation.model_validate(item).model_dump(exclude={"id"})
            for field in ("source_job_id",):
                if values.get(field):
                    # 来源任务须属于同一零件，不能伪造其他零件的识别依据。
                    identifier = UUID(str(values[field]))
                    source = await session.get(CncAnalysisJob, identifier)
                    if source is None or source.part_id != part.id:
                        raise AppException("工序来源任务不属于本零件", 422)
                    values[field] = identifier
            row = existing.get(str(item.get("id")))
            if row is None:
                row = CncOperation(part_id=part.id, org_id=part.org_id, created_by=user.user_id)
            row.sort_no = index
            row.updated_by = user.user_id
            for key, value in values.items():
                setattr(row, key, value)
            session.add(row)
            wanted.add(row.id)
        for row in existing.values():
            if row.id not in wanted:
                await session.delete(row)
        part.updated_by = user.user_id
        session.add(part)

    async def rules(self, session, user, permission=LIST, *, lock=False, org_id=None):
        org_id = org_id or user.org_id
        if org_id is None:
            raise AppException("请先关联当前组织", 403)
        ensure_org_access(user, org_id, permission)
        # 规则为组织共享定义；自身/关联范围也必须经规则对象范围过滤，不能扩大授权。
        query = select(CncRuleSet).where(
            CncRuleSet.org_id == org_id, *scoped_conditions(CncRuleSet, user, permission)
        )
        if lock:
            query = query.with_for_update()
        row = (await session.execute(query)).scalar_one_or_none()
        if row is None:
            # 初始化规则属于当前用户动作的同一事务；租户开通无需预先知道业务组织。
            from app.auth.scope_filters import resolve_effective_data_scope

            if resolve_effective_data_scope(user, permission) == "related":
                raise AppException("当前规则未配置关联数据范围", 403)
            existing = (
                await session.execute(select(CncRuleSet.id).where(CncRuleSet.org_id == org_id))
            ).first()
            if existing:
                raise AppException("无权访问当前组织的报价规则", 403)
            row = CncRuleSet(org_id=org_id, created_by=user.user_id, updated_by=user.user_id)
            session.add(row)
            await session.flush()
            from ..process_matching import matching_catalog
            from .rules import archive_rules

            catalogue = await matching_catalog(session, org_id, user, permission, lock=True)
            config = archive_rules(catalogue)
            await self.save_rules(session, row, config, user)
        entries = (
            (
                await session.execute(
                    select(CncRuleEntry)
                    .where(
                        CncRuleEntry.rule_set_id == row.id,
                        CncRuleEntry.category_code.in_(RULE_CATEGORIES),
                    )
                    .order_by(CncRuleEntry.sort_no)
                )
            )
            .scalars()
            .all()
        )
        config = {
            "is_auto_apply": row.is_auto_apply,
            "stock_allowance": row.stock_allowance,
            "materials": [],
            "processes": [],
            "external_processes": [],
        }
        for entry in entries:
            definition = {
                **entry.definition,
                "id": entry.rule_no,
                "name": entry.name,
                "is_active": entry.is_active,
            }
            if entry.category_code in {"processes", "external_processes"}:
                definition["process_id"] = entry.process_id
            config[entry.category_code].append(definition)
        return row, RuleConfig.model_validate(config)

    async def save_rules(self, session, row, config, user):
        # 只替换仍使用的三类规则；旧模板由环境迁移清理，避免触碰尚存的明细外键。
        await session.execute(
            delete(CncRuleEntry).where(
                CncRuleEntry.rule_set_id == row.id,
                CncRuleEntry.category_code.in_(RULE_CATEGORIES),
            )
        )
        row.is_auto_apply, row.stock_allowance = config.is_auto_apply, config.stock_allowance
        row.updated_by = user.user_id
        for category in RULE_CATEGORIES:
            for index, item in enumerate(getattr(config, category)):
                definition = item.model_dump(mode="json", exclude={"id", "name", "is_active", "process_id"})
                entry = CncRuleEntry(
                    rule_set_id=row.id,
                    org_id=row.org_id,
                    rule_no=item.id,
                    category_code=category,
                    name=item.name,
                    is_active=item.is_active,
                    sort_no=index,
                    process_id=getattr(item, "process_id", None),
                    definition=definition,
                    created_by=user.user_id,
                    updated_by=user.user_id,
                )
                session.add(entry)

    async def claim(self, session):
        # 多个后端实例通过行锁分领；过期任务只失败，不重复调用付费云服务。
        await session.execute(
            update(CncAnalysisJob)
            .where(CncAnalysisJob.status_code == "running", CncAnalysisJob.lease_expires_at < utc_now())
            .values(
                status_code="failed",
                stage="解析已中断，可重试",
                error="处理进程中断；已有结果保留，请手动重新解析",
                updated_at=utc_now(),
            )
        )
        row = (
            (
                await session.execute(
                    select(CncAnalysisJob)
                    .where(CncAnalysisJob.status_code == "queued")
                    .order_by(CncAnalysisJob.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        return row

    async def is_ready(self, session):
        names = [
            model.__tablename__
            for model in (
                CncPart,
                CncOperation,
                CncDrawingFile,
                CncAnalysisJob,
                CncQuote,
                CncRuleSet,
                CncRuleEntry,
            )
        ]
        return all((await session.execute(select(*(func.to_regclass(name) for name in names)))).one())

    async def job(self, session, identifier, *, lock=False):
        return await session.get(CncAnalysisJob, identifier, with_for_update=lock)


repository = CncRepository()
