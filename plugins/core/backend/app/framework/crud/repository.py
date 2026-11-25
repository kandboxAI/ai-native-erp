from typing import Any
from inspect import isawaitable
from uuid import UUID

from pydantic import BaseModel
from fastapi import status
from sqlalchemy import Text, cast, false, func, or_
from sqlmodel import SQLModel, desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.data_scope import (
    DATA_SCOPE_ALL,
    DATA_SCOPE_DEPARTMENT,
    DATA_SCOPE_ORGANIZATION,
    DATA_SCOPE_RELATED,
    DATA_SCOPE_SELF,
)
from app.auth.schemas import AuthenticatedUser
from app.core.exceptions import AppException
from app.db.pagination import PageParams
from app.framework.datetime_local import parse_datetime_input
from app.framework.db.models import utc_now

CONCURRENCY_TOKEN_FIELD = "__expected_updated_at"

ORGANIZATION_SCOPE_REQUIRED = "required"
ORGANIZATION_SCOPE_PUBLIC_READ = "public_read"
ORGANIZATION_SCOPE_NONE = "none"

PUBLIC_WRITE_DENY = "deny"
PUBLIC_WRITE_ADMIN_ONLY = "admin_only"
PUBLIC_WRITE_PERMISSION_BASED = "permission_based"


CrudPayloadNormalizer = Any


class SqlModelCrudRepository:
    """通用 CRUD 仓储。

    导出：`GET /api/{module}/export` 一律走 :meth:`export_rows`。

    - 默认：单表行（无外键时可理解为「纯主表」列）。
    - 关联字段：在子类声明 ``export_relation_paths``（见 ``app.framework.export.relation_paths``），
      由路由层与 ``sanitize_export_rows`` 将嵌套的 ``model_dump`` 拍平为宽表列；需保证列表或导出查询已 ``selectinload`` 嵌套关联。
    - 仅导出需要预加载时可设 ``export_load_options``；默认与列表查询一致的加载可由 :class:`OrmRelationshipCrudRepository` 接管。
    - 导出序列化可选用 ``export_row_model``（不配则用 ``item_model`` / 子类 `_serialize_list_entity`）。
    """

    export_relation_paths: tuple[Any, ...] = ()

    def __init__(
        self,
        *,
        table_model: type[SQLModel],
        item_model: type[BaseModel],
        writable_columns: list[str],
        searchable_columns: list[str],
        filterable_columns: list[str] | None = None,
        create_payload_normalizer: CrudPayloadNormalizer | None = None,
        update_payload_normalizer: CrudPayloadNormalizer | None = None,
        export_load_options: list[Any] | None = None,
        export_row_model: type[BaseModel] | None = None,
        organization_scope: str = ORGANIZATION_SCOPE_REQUIRED,
        public_write: str = PUBLIC_WRITE_DENY,
        scope_resource: str | None = None,
        organization_write_kind: str = "active",
    ) -> None:
        if organization_write_kind not in {"active", "any"}:
            raise ValueError("organization_write_kind 仅支持 active/any；行业组织限制请在插件 Repository 实现")
        self.table_model = table_model
        self.item_model = item_model
        self.writable_columns = writable_columns
        self.searchable_columns = searchable_columns
        self.filterable_columns = filterable_columns or []
        self.create_payload_normalizer = create_payload_normalizer
        self.update_payload_normalizer = update_payload_normalizer
        self.export_load_options = list(export_load_options or [])
        self.export_row_model = export_row_model
        self.organization_scope = organization_scope
        self.public_write = public_write
        self.scope_resource = scope_resource
        self.organization_write_kind = organization_write_kind

    def _permission_code(self, action: str | None) -> str | None:
        if not action:
            raise AppException(
                "permission action is required for data scope evaluation",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if not self.scope_resource:
            raise AppException(
                f"scope resource is not configured for table: {getattr(self.table_model, '__tablename__', self.table_model)}",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return f"{self.scope_resource}:{action}"

    def _parse_entity(self, entity: SQLModel) -> BaseModel:
        return self.item_model.model_validate(entity)

    def _normalize_id(self, item_id: str) -> UUID | str:
        try:
            return UUID(str(item_id))
        except ValueError:
            return item_id

    @staticmethod
    def _has_global_access(current_user: AuthenticatedUser, permission_code: str | None = None) -> bool:
        from app.auth.scope_filters import has_global_access

        return has_global_access(current_user, permission_code)

    def _uses_organization_scope(self) -> bool:
        return hasattr(self.table_model, "org_id")

    def _uses_department_scope(self) -> bool:
        return hasattr(self.table_model, "department_id")

    def _uses_owner_scope(self) -> bool:
        return self._owner_column_name() is not None

    def _is_organization_table(self) -> bool:
        return getattr(self.table_model, "__tablename__", "") == "sys_org"

    def _owner_column_name(self) -> str | None:
        """本人数据范围的归属字段：user_id，否则 created_by。"""
        if hasattr(self.table_model, "user_id"):
            return "user_id"
        if hasattr(self.table_model, "created_by"):
            return "created_by"
        return None

    def _ensure_org_access(
        self,
        current_user: AuthenticatedUser,
        org_id: UUID | None,
        permission_code: str | None = None,
    ) -> UUID:
        from app.auth.scope_filters import ensure_org_access

        return ensure_org_access(current_user, org_id, permission_code)

    def _resolve_write_org_id(
        self,
        current_user: AuthenticatedUser,
        org_id: UUID | None,
        permission_code: str | None = None,
    ) -> UUID:
        from app.auth.scope_filters import resolve_write_org_id

        return resolve_write_org_id(current_user, org_id, permission_code)

    def _require_department_id(self, current_user: AuthenticatedUser) -> UUID:
        if current_user.department_id is None:
            raise AppException(
                "current user is not bound to any department",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return current_user.department_id

    def _organization_scope_condition(self, current_user: AuthenticatedUser, permission_code: str | None = None):
        from app.auth.scope_filters import table_scope_condition

        return table_scope_condition(self.table_model, current_user, permission_code)

    def _department_scope_condition(self, current_user: AuthenticatedUser, permission_code: str | None = None):
        if self._uses_department_scope():
            return getattr(self.table_model, "department_id") == self._require_department_id(current_user)
        return self._organization_scope_condition(current_user, permission_code)

    def _self_scope_condition(self, current_user: AuthenticatedUser):
        from app.auth.scope_filters import _self_scope_condition

        return _self_scope_condition(self.table_model, current_user)

    def _related_scope_condition(self, current_user: AuthenticatedUser):
        from app.auth.scope_filters import _related_scope_condition

        return _related_scope_condition(self.table_model, current_user)

    def _scope_condition(self, current_user: AuthenticatedUser, action: str | None = None):
        """数据范围条件。"""
        from app.auth.scope_filters import table_scope_condition

        if self.organization_scope == ORGANIZATION_SCOPE_NONE:
            return None
        permission_code = self._permission_code(action)
        if self.organization_scope == ORGANIZATION_SCOPE_PUBLIC_READ and self._uses_organization_scope():
            return self._public_read_scope_condition(current_user, permission_code)
        return table_scope_condition(self.table_model, current_user, permission_code)

    def _public_read_scope_condition(self, current_user: AuthenticatedUser, permission_code: str | None = None):
        if self._has_global_access(current_user, permission_code):
            return None

        from app.auth.scope_filters import accessible_org_ids, has_all_organization_access

        if has_all_organization_access(current_user, permission_code):
            return None

        org_column = getattr(self.table_model, "org_id")
        org_ids = accessible_org_ids(current_user)
        if not org_ids:
            return org_column.is_(None)
        if len(org_ids) == 1:
            return or_(org_column.is_(None), org_column == org_ids[0])
        return or_(org_column.is_(None), org_column.in_(org_ids))

    def _apply_scope(self, statement, current_user: AuthenticatedUser, action: str | None = None):
        # 租户隔离由 schema 完成，这里只施加数据范围
        condition = self._scope_condition(current_user, action)
        if condition is None:
            return statement
        return statement.where(condition)

    def _alive_row_condition(self) -> Any | None:
        """软删除表只取有效数据。"""
        column = getattr(self.table_model, "deleted_at", None)
        return None if column is None else column.is_(None)

    def _apply_alive(self, statement):
        alive = self._alive_row_condition()
        if alive is None:
            return statement
        return statement.where(alive)

    def _scoped_detail_statement(
        self,
        item_id: str,
        current_user: AuthenticatedUser,
        *,
        for_update: bool = False,
        action: str = "detail",
    ):
        statement = select(self.table_model).where(getattr(self.table_model, "id") == self._normalize_id(item_id))
        statement = self._apply_scope(statement, current_user, action)
        statement = self._apply_alive(statement)
        return statement.with_for_update() if for_update else statement

    def _assert_not_stale(self, entity: SQLModel, expected_updated_at: Any) -> None:
        if expected_updated_at is None or not hasattr(entity, "updated_at"):
            return
        expected = parse_datetime_input(expected_updated_at)
        actual = parse_datetime_input(getattr(entity, "updated_at", None))
        if expected is None or actual is None:
            raise AppException("无效的并发版本标识", status_code=status.HTTP_400_BAD_REQUEST)
        if expected.replace(microsecond=0) != actual.replace(microsecond=0):
            raise AppException("记录已被他人修改，请刷新后重试", status_code=status.HTTP_409_CONFLICT)

    def _list_statement(self, current_user: AuthenticatedUser):
        statement = self._apply_scope(select(self.table_model), current_user, "list")
        return self._apply_alive(statement)

    def _total_statement(self, current_user: AuthenticatedUser):
        statement = self._apply_scope(select(func.count()).select_from(self.table_model), current_user, "list")
        return self._apply_alive(statement)

    def _serialize_list_entity(self, entity: SQLModel) -> dict[str, Any]:
        return self._parse_entity(entity).model_dump(mode="json")

    def _serialize_detail_entity(self, entity: SQLModel) -> BaseModel:
        return self._parse_entity(entity)

    async def _normalize_payload_for_scope(
        self,
        session: AsyncSession,
        payload: dict[str, Any],
        current_user: AuthenticatedUser,
        *,
        is_create: bool,
        entity: SQLModel | None = None,
        action: str | None = None,
    ) -> dict[str, Any]:
        from app.auth.scope_filters import resolve_effective_data_scope

        permission_code = self._permission_code(action or ("create" if is_create else "update"))
        data = {key: value for key, value in payload.items() if key in self.writable_columns}
        if self._is_organization_table():
            if is_create and not self._has_global_access(current_user, permission_code):
                raise AppException(
                    "only super admin can create organization records",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            return data
        if self._has_global_access(current_user, permission_code):
            if (
                self._uses_organization_scope()
                and self.organization_scope != ORGANIZATION_SCOPE_NONE
                and self.organization_write_kind == "active"
                and data.get("org_id") is not None
            ):
                from app.modules.organization.validators import ensure_active_org

                data["org_id"] = await ensure_active_org(session, current_user, data["org_id"])
            return data

        resolved_scope = resolve_effective_data_scope(current_user, permission_code)

        if self._uses_organization_scope():
            if self.organization_scope == ORGANIZATION_SCOPE_NONE:
                return data
            if self.organization_scope == ORGANIZATION_SCOPE_PUBLIC_READ:
                return await self._normalize_public_read_payload_for_scope(
                    data,
                    session,
                    current_user,
                    is_create=is_create,
                    entity=entity,
                    permission_code=permission_code,
                )
            data["org_id"] = self._resolve_write_org_id(current_user, data.get("org_id"), permission_code)
            if self.organization_write_kind == "active":
                from app.modules.organization.validators import ensure_active_org

                data["org_id"] = await ensure_active_org(session, current_user, data["org_id"])
        if resolved_scope == DATA_SCOPE_DEPARTMENT and self._uses_department_scope():
            data["department_id"] = self._require_department_id(current_user)
        if resolved_scope == DATA_SCOPE_SELF:
            owner_column_name = self._owner_column_name()
            if owner_column_name is None:
                raise AppException(
                    "current data scope does not allow creating records for this module",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            data[owner_column_name] = current_user.user_id
            if self._uses_department_scope() and current_user.department_id is not None:
                data["department_id"] = current_user.department_id
        return data

    async def _normalize_public_read_payload_for_scope(
        self,
        data: dict[str, Any],
        session: AsyncSession,
        current_user: AuthenticatedUser,
        *,
        is_create: bool,
        entity: SQLModel | None,
        permission_code: str | None = None,
    ) -> dict[str, Any]:
        has_org_id = "org_id" in data
        org_id = data.get("org_id")
        if org_id is not None:
            data["org_id"] = self._ensure_org_access(current_user, org_id, permission_code)
            if self.organization_write_kind == "active":
                from app.modules.organization.validators import ensure_active_org

                data["org_id"] = await ensure_active_org(session, current_user, data["org_id"])
            return data

        if not is_create and not has_org_id and getattr(entity, "org_id", None) is not None:
            return data

        if self.public_write == PUBLIC_WRITE_PERMISSION_BASED:
            return data
        if self.public_write == PUBLIC_WRITE_ADMIN_ONLY and self._has_global_access(current_user, permission_code):
            return data

        raise AppException(
            "only admin can write public organization records",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    def _stamp_create(self, data: dict[str, Any], current_user: AuthenticatedUser) -> None:
        """新增时写入审计字段。"""
        for column in ("created_by", "updated_by"):
            if hasattr(self.table_model, column):
                data[column] = current_user.user_id

    def _stamp_update(self, data: dict[str, Any], current_user: AuthenticatedUser) -> None:
        if hasattr(self.table_model, "updated_by"):
            data["updated_by"] = current_user.user_id
        if hasattr(self.table_model, "updated_at"):
            data["updated_at"] = utc_now()

    def _filter_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key in self.writable_columns}

    async def _run_payload_normalizer(
        self,
        normalizer: CrudPayloadNormalizer | None,
        session: AsyncSession,
        payload: dict[str, Any],
        current_user: AuthenticatedUser,
        *,
        entity: SQLModel | None = None,
        is_create: bool,
    ) -> dict[str, Any]:
        data = self._filter_payload(payload)
        if normalizer is None:
            return await self._normalize_payload_for_scope(
                session,
                data,
                current_user,
                is_create=is_create,
                entity=entity,
            )

        normalized = normalizer(session, data, current_user, entity)
        if isawaitable(normalized):
            normalized = await normalized
        if not isinstance(normalized, dict):
            raise TypeError("payload normalizer must return a dict")
        return await self._normalize_payload_for_scope(
            session,
            normalized,
            current_user,
            is_create=is_create,
            entity=entity,
        )

    def _search_expressions(self, params: PageParams) -> list[Any]:
        if not params.keyword or not self.searchable_columns:
            return []

        keyword = f"%{params.keyword}%"
        return [
            cast(getattr(self.table_model, column_name), Text).ilike(keyword)
            for column_name in self.searchable_columns
        ]

    def _filter_conditions(self, params: PageParams) -> list[Any]:
        if not isinstance(params, BaseModel) or not self.filterable_columns:
            return []
        filters = params.model_dump(exclude_none=True)
        return [
            getattr(self.table_model, column_name) == filters[column_name]
            for column_name in self.filterable_columns
            if column_name in filters
        ]

    def _filtered_list_statements(
        self,
        params: Any,
        current_user: AuthenticatedUser,
        *,
        action: str = "list",
    ) -> tuple[Any, Any]:
        search_expressions = self._search_expressions(params)
        conditions = [*self._filter_conditions(params)]
        if search_expressions:
            conditions.append(or_(*search_expressions))

        if action == "list":
            total_statement = self._total_statement(current_user)
            items_statement = self._list_statement(current_user)
        else:
            total_statement = self._apply_alive(
                self._apply_scope(select(func.count()).select_from(self.table_model), current_user, action)
            )
            items_statement = self._apply_alive(
                self._apply_scope(select(self.table_model), current_user, action)
            )
        for condition in conditions:
            total_statement = total_statement.where(condition)
            items_statement = items_statement.where(condition)
        return total_statement, items_statement

    def _statement_options_for_export(self) -> list[Any]:
        return self.export_load_options

    def _serialize_for_export(self, entity: SQLModel) -> dict[str, Any]:
        if self.export_row_model is not None:
            return self.export_row_model.model_validate(entity).model_dump(mode="json")
        return self._serialize_list_entity(entity)

    async def export_rows(
        self,
        session: AsyncSession,
        params: Any,
        current_user: AuthenticatedUser,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        _total_statement, items_statement = self._filtered_list_statements(params, current_user, action="export")
        updated_at_column = getattr(self.table_model, "updated_at")
        items_statement = items_statement.order_by(desc(updated_at_column)).limit(limit)
        opts = self._statement_options_for_export()
        if opts:
            items_statement = items_statement.options(*opts)
        rows = await session.exec(items_statement)
        return [self._serialize_for_export(row) for row in rows.all()]

    async def list(self, session: AsyncSession, params: PageParams, current_user: AuthenticatedUser) -> dict[str, Any]:
        total_statement, items_statement = self._filtered_list_statements(params, current_user)

        total_result = await session.exec(total_statement)
        total = total_result.one() or 0

        updated_at_column = getattr(self.table_model, "updated_at")
        items_statement = (
            items_statement.order_by(desc(updated_at_column))
            .limit(params.page_size)
            .offset((params.page - 1) * params.page_size)
        )
        rows = await session.exec(items_statement)
        items = [self._serialize_list_entity(row) for row in rows.all()]
        return {
            "items": items,
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
        }

    async def detail(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser) -> BaseModel | None:
        entity = (await session.exec(self._scoped_detail_statement(item_id, current_user, action="detail"))).one_or_none()
        return self._serialize_detail_entity(entity) if entity else None

    async def before_commit(self, session, entity, current_user, action):
        """模块可在同一事务内维护关联资源，默认无额外动作。"""

    async def create(
        self,
        session: AsyncSession,
        payload: dict[str, Any],
        current_user: AuthenticatedUser,
    ) -> BaseModel:
        data = await self._run_payload_normalizer(
            self.create_payload_normalizer,
            session,
            payload,
            current_user,
            is_create=True,
        )
        self._stamp_create(data, current_user)
        entity = self.table_model(**data)
        session.add(entity)
        await self.before_commit(session, entity, current_user, "create")
        await session.commit()
        await session.refresh(entity)
        return self._parse_entity(entity)

    async def update(
        self,
        session: AsyncSession,
        item_id: str,
        payload: dict[str, Any],
        current_user: AuthenticatedUser,
    ) -> BaseModel | None:
        entity = (await session.exec(self._scoped_detail_statement(item_id, current_user, for_update=True, action="update"))).one_or_none()
        if entity is None:
            return None

        expected_updated_at = payload.pop(CONCURRENCY_TOKEN_FIELD, None)
        data = await self._run_payload_normalizer(
            self.update_payload_normalizer,
            session,
            payload,
            current_user,
            entity=entity,
            is_create=False,
        )
        self._assert_not_stale(entity, expected_updated_at)
        if not data:
            return self._parse_entity(entity)

        self._stamp_update(data, current_user)
        for column_name, value in data.items():
            setattr(entity, column_name, value)

        session.add(entity)
        await self.before_commit(session, entity, current_user, "update")
        await session.commit()
        await session.refresh(entity)
        return self._parse_entity(entity)

    async def delete(self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser) -> bool:
        if self._is_organization_table() and not self._has_global_access(current_user, self._permission_code("delete")):
            raise AppException(
                "only super admin can delete organization records",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        entity = (await session.exec(self._scoped_detail_statement(item_id, current_user, for_update=True, action="delete"))).one_or_none()
        if entity is None:
            return False
        if hasattr(entity, "deleted_at"):
            entity.deleted_at = utc_now()
            entity.deleted_by = current_user.user_id
            if hasattr(entity, "updated_by"):
                entity.updated_by = current_user.user_id
            session.add(entity)
            await self.before_commit(session, entity, current_user, "delete")
            await session.commit()
            return True
        await session.flush()
        await session.delete(entity)
        await session.commit()
        return True


class OrmRelationshipCrudRepository(SqlModelCrudRepository):
    """带 Relationship 的业务表：Pydantic 详情模型里常含嵌套的 organization / building / room 等。

    业务层（Service / Router）仍然只调用 list、detail、create、update、delete，与基类一致。

    与 SqlModelCrudRepository 的差异：

    - 列表与详情查询：在 SQL 上加 list_load_options / detail_load_options（如 selectinload），再 model_validate。
    - create/update：基类 commit + refresh 后若直接校验 ORM，Relationship 可能未加载从而导致 MissingGreenlet。
      本子类重写 create/update，写库后用 _reload_for_detail_serialization 按「详情同款」语句再加载一条，
      再序列化返回。

    _reload_for_detail_serialization 仅服务于上述 create/update，不要在模块外单独调用。
    """

    def __init__(
        self,
        *,
        list_item_model: type[BaseModel] | None = None,
        detail_item_model: type[BaseModel] | None = None,
        list_load_options: list[Any] | None = None,
        detail_load_options: list[Any] | None = None,
        export_load_options: list[Any] | None = None,
        export_row_model: type[BaseModel] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(export_load_options=export_load_options, export_row_model=export_row_model, **kwargs)
        self.list_item_model = list_item_model or self.item_model
        self.detail_item_model = detail_item_model or self.item_model
        self.list_load_options = list_load_options or []
        self.detail_load_options = detail_load_options or self.list_load_options

    def _statement_options_for_export(self) -> list[Any]:
        if self.export_load_options:
            return self.export_load_options
        return self.list_load_options

    def _list_statement(self, current_user: AuthenticatedUser):
        statement = super()._list_statement(current_user)
        if self.list_load_options:
            statement = statement.options(*self.list_load_options)
        return statement

    def _scoped_detail_statement(
        self,
        item_id: str,
        current_user: AuthenticatedUser,
        *,
        for_update: bool = False,
        action: str = "detail",
    ):
        statement = super()._scoped_detail_statement(item_id, current_user, for_update=for_update, action=action)
        if self.detail_load_options:
            statement = statement.options(*self.detail_load_options)
        return statement

    async def _reload_for_detail_serialization(
        self, session: AsyncSession, item_id: str, current_user: AuthenticatedUser, fallback: SQLModel
    ) -> SQLModel:
        """create/update 后 refresh 的实体 Relationship 未预加载；直接 model_validate ORM 会触发惰性 IO。"""
        reloaded = (
            await session.exec(self._scoped_detail_statement(item_id, current_user, action="detail"))
        ).one_or_none()
        return reloaded or fallback

    async def create(
        self,
        session: AsyncSession,
        payload: dict[str, Any],
        current_user: AuthenticatedUser,
    ) -> BaseModel:
        data = await self._run_payload_normalizer(
            self.create_payload_normalizer,
            session,
            payload,
            current_user,
            is_create=True,
        )
        self._stamp_create(data, current_user)
        entity = self.table_model(**data)
        session.add(entity)
        await session.commit()
        await session.refresh(entity)
        loaded = await self._reload_for_detail_serialization(session, str(entity.id), current_user, entity)
        return self._serialize_detail_entity(loaded)

    async def update(
        self,
        session: AsyncSession,
        item_id: str,
        payload: dict[str, Any],
        current_user: AuthenticatedUser,
    ) -> BaseModel | None:
        entity = (await session.exec(self._scoped_detail_statement(item_id, current_user, for_update=True, action="update"))).one_or_none()
        if entity is None:
            return None

        expected_updated_at = payload.pop(CONCURRENCY_TOKEN_FIELD, None)
        data = await self._run_payload_normalizer(
            self.update_payload_normalizer,
            session,
            payload,
            current_user,
            entity=entity,
            is_create=False,
        )
        self._assert_not_stale(entity, expected_updated_at)
        if not data:
            loaded = await self._reload_for_detail_serialization(session, item_id, current_user, entity)
            return self._serialize_detail_entity(loaded)

        self._stamp_update(data, current_user)
        for column_name, value in data.items():
            setattr(entity, column_name, value)

        session.add(entity)
        await session.commit()
        await session.refresh(entity)
        loaded = await self._reload_for_detail_serialization(session, item_id, current_user, entity)
        return self._serialize_detail_entity(loaded)

    def _serialize_list_entity(self, entity: SQLModel) -> dict[str, Any]:
        return self.list_item_model.model_validate(entity).model_dump(mode="json")

    def _serialize_detail_entity(self, entity: SQLModel) -> BaseModel:
        return self.detail_item_model.model_validate(entity)
