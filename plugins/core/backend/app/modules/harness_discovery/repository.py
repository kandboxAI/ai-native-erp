"""租户内索引存储；使用当前事务 search_path，不访问历史 public 索引。"""
import json
from collections.abc import Callable

from sqlalchemy import inspect, text

from app.framework.db.ids import uuid7
from app.framework.db.session import get_session_context
from app.framework.db.tenant import require_tenant_schema
from app.integrations.erp_discovery.adapter import NAMESPACE
from resource_discovery.catalog import validate_namespace
from resource_discovery.repository import vector_literal

from .index_models import AiResourceActive, AiResourceBundle, AiResourceDocument


class IndexSchemaError(RuntimeError):
    """Safe local diagnostic; never contains credentials, SQL parameters or vectors."""


def validate_index_schema(connection, schema):
    inspector = inspect(connection)
    for model in (AiResourceBundle, AiResourceDocument, AiResourceActive):
        table = model.__table__
        if not inspector.has_table(table.name, schema=schema):
            raise IndexSchemaError(f"目标租户 {schema} 缺少索引表 {table.name}；请检查该租户迁移。")
        columns = {column["name"]: column for column in inspector.get_columns(table.name, schema=schema)}
        for expected in table.columns:
            actual = columns.get(expected.name)
            if actual is None or actual["nullable"] != expected.nullable \
                    or str(actual["type"].compile(dialect=connection.dialect)).upper() != str(expected.type.compile(dialect=connection.dialect)).upper():
                raise IndexSchemaError(f"目标租户 {schema} 的 {table.name}.{expected.name} 与当前模型不一致；请检查迁移。")
        if inspector.get_pk_constraint(table.name, schema=schema)["constrained_columns"] != ["id"]:
            raise IndexSchemaError(f"索引表 {table.name} 的主键不匹配。")
        unique_keys = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table.name, schema=schema)}
        required = ("namespace", "revision") if model is AiResourceBundle else ("bundle_id", "document_key") if model is AiResourceDocument else ("namespace",)
        if required not in unique_keys:
            raise IndexSchemaError(f"索引表 {table.name} 缺少发布所需的唯一约束。")
        if model is not AiResourceBundle:
            foreign_keys = inspector.get_foreign_keys(table.name, schema=schema)
            if not any(item["constrained_columns"] == ["bundle_id"] and item["referred_table"] == "ai_resource_bundle"
                       and item["referred_columns"] == ["id"] and item.get("referred_schema") in (None, schema)
                       for item in foreign_keys):
                raise IndexSchemaError(f"索引表 {table.name} 的版本外键不匹配。")


class TenantPgVectorRepository:
    def __init__(self, session_context: Callable, namespace: str):
        self.session_context = session_context
        self.namespace = validate_namespace(namespace)
        if len(self.namespace) > 128:
            raise ValueError("索引命名空间超过 128 字符")

    async def initialize(self):
        schema = require_tenant_schema()
        async with self.session_context() as session:
            connection = await session.connection()
            await connection.run_sync(lambda bind: validate_index_schema(bind, schema))

    async def publish(self, revision, model, dimensions, documents, vectors):
        schema = require_tenant_schema()
        if len(vectors) != len(documents) or not documents or len({doc["id"] for doc in documents}) != len(documents):
            raise ValueError("Invalid catalog or embedding count")
        # Validate the entire batch before opening a publication transaction.
        records = [{"id": uuid7(), "document_key": doc["id"], "content_hash": doc["content_hash"],
                    "vector": vector_literal(vector, dimensions)} for doc, vector in zip(documents, vectors, strict=True)]
        args = {"namespace": self.namespace, "revision": revision, "model": model, "dimensions": dimensions}
        async with self.session_context() as session:
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"{schema}:{self.namespace}"})
            bundle = (await session.execute(text("SELECT id, model, dimensions FROM ai_resource_bundle WHERE namespace=:namespace AND revision=:revision"), args)).mappings().one_or_none()
            if bundle is None:
                bundle_id = uuid7()
                await session.execute(text("INSERT INTO ai_resource_bundle(id, namespace, revision, model, dimensions) VALUES (:id, :namespace, :revision, :model, :dimensions)"), {**args, "id": bundle_id})
                await session.execute(text("INSERT INTO ai_resource_document(id, bundle_id, document_key, content_hash, embedding) VALUES (:id, :bundle_id, :document_key, :content_hash, CAST(:vector AS vector))"),
                                      [{**record, "bundle_id": bundle_id} for record in records])
            else:
                if bundle["model"] != model or bundle["dimensions"] != dimensions:
                    raise ValueError("Existing bundle identity differs")
                bundle_id = bundle["id"]
            await session.execute(text("""INSERT INTO ai_resource_active(id, namespace, bundle_id)
                VALUES (:id, :namespace, :bundle_id) ON CONFLICT (namespace)
                DO UPDATE SET bundle_id=excluded.bundle_id, updated_at=now()"""),
                {"id": uuid7(), "namespace": self.namespace, "bundle_id": bundle_id})
            await session.commit()

    async def vector_search(self, documents, vector, model, dimensions, limit):
        require_tenant_schema()
        if not documents:
            return [], "ready"
        statement = text("""WITH active AS MATERIALIZED (
            SELECT b.id,b.model,b.dimensions FROM ai_resource_bundle b
            JOIN ai_resource_active a ON a.bundle_id=b.id AND a.namespace=b.namespace
            WHERE b.namespace=:namespace
        ), authorized AS MATERIALIZED (
            SELECT d.document_key,d.embedding FROM ai_resource_document d
            JOIN active b ON b.id=d.bundle_id
            JOIN jsonb_to_recordset(CAST(:allowed AS jsonb)) AS approved(id text, content_hash text)
              ON approved.id=d.document_key AND approved.content_hash=d.content_hash
            WHERE b.model=:model AND b.dimensions=:dimensions
        ), ranked AS (
            SELECT document_key, embedding <=> CAST(:vector AS vector) AS distance FROM authorized
            ORDER BY distance, document_key LIMIT :limit
        ) SELECT (SELECT model FROM active) AS model, (SELECT dimensions FROM active) AS dimensions,
            (SELECT count(*) FROM authorized) AS matched_count,
            COALESCE((SELECT jsonb_agg(document_key ORDER BY distance,document_key) FROM ranked), '[]'::jsonb) AS ids""")
        args = {"namespace": self.namespace, "allowed": json.dumps([{"id": doc["id"], "content_hash": doc["content_hash"]} for doc in documents]),
                "model": model, "dimensions": dimensions, "vector": vector_literal(vector, dimensions), "limit": limit}
        async with self.session_context() as session:
            row = (await session.execute(statement, args)).mappings().one()
        if row["model"] is None:
            return [], "not_built"
        if row["model"] != model or row["dimensions"] != dimensions:
            return [], "model_changed"
        if row["matched_count"] != len(documents):
            return [], "catalog_changed"
        return list(row["ids"]), "ready"

    async def index_status(self):
        require_tenant_schema()
        async with self.session_context() as session:
            row = (await session.execute(text("""SELECT b.namespace,b.revision,b.model,b.dimensions,b.created_at,
                (SELECT count(*) FROM ai_resource_document d WHERE d.bundle_id=b.id) AS documents
                FROM ai_resource_bundle b JOIN ai_resource_active a ON a.bundle_id=b.id AND a.namespace=b.namespace
                WHERE b.namespace=:namespace"""), {"namespace": self.namespace})).mappings().one_or_none()
        return dict(row) if row else None


def create_store():
    return TenantPgVectorRepository(get_session_context, NAMESPACE)
