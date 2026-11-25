"""SQLAlchemy pgvector repository with independent active bundles per trusted namespace."""
import json
import math
from dataclasses import dataclass
from collections.abc import Callable

from sqlalchemy import Table, text
from sqlalchemy.dialects import postgresql

from .catalog import validate_namespace
from .orm import validate_schema


@dataclass(frozen=True)
class IndexTables:
    """Trusted host ORM bindings; never supplied by a tool or HTTP request."""
    bundle: Table
    document: Table
    active: Table
    document_key: str
    bundle_id: str | None = None

    @classmethod
    def legacy(cls):
        from .orm import DiscoveryBundle, DiscoveryDocument, DiscoveryActive
        return cls(DiscoveryBundle.__table__, DiscoveryDocument.__table__, DiscoveryActive.__table__, "id")


def vector_literal(values: list[float], dimensions: int) -> str:
    if len(values) != dimensions or not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
        raise ValueError("Invalid embedding dimensions or values")
    if not any(v != 0 for v in values):
        raise ValueError("Zero embeddings are not supported for cosine search")
    return json.dumps(values, separators=(",", ":"))


class PgVectorRepository:
    """Session factory comes from the host; namespace never comes from a model request."""

    def __init__(self, session_context: Callable, namespace: str, *, tables: IndexTables | None = None, schema: str | None = None):
        self.session_context = session_context
        self.namespace = validate_namespace(namespace)
        self.tables = tables if tables is not None else IndexTables.legacy()
        self.schema = schema
        if self.tables.document_key not in self.tables.document.c:
            raise ValueError("Missing document key column in index bindings")
        preparer = postgresql.dialect().identifier_preparer
        self._identifiers = {key: preparer.format_table(getattr(self.tables, key)) for key in ("bundle", "document", "active")}
        self._identifiers["document_key"] = preparer.quote(self.tables.document_key)
        if self.tables.bundle_id is not None:
            if "id" not in self.tables.bundle.c or any(self.tables.bundle_id not in table.c for table in (self.tables.document, self.tables.active)):
                raise ValueError("Missing bundle identity in index bindings")
            self._identifiers["bundle_id"] = preparer.quote(self.tables.bundle_id)

    def _statement(self, template: str):
        return text(template.format(**self._identifiers))

    async def initialize(self) -> None:
        """Legacy init entry point validates the host-managed schema without changing it."""
        async with self.session_context() as session:
            connection = await session.connection()
            await connection.run_sync(lambda conn: validate_schema(conn, [self.tables.bundle, self.tables.document, self.tables.active], schema=self.schema))

    async def publish(self, revision: str, model: str, dimensions: int, documents: list[dict], vectors: list[list[float]]) -> None:
        if len(vectors) != len(documents) or not documents or len({d["id"] for d in documents}) != len(documents):
            raise ValueError("Invalid catalog or embedding count")
        records = [{"namespace": self.namespace, "revision": revision, "id": d["id"], "hash": d["content_hash"],
                    "vector": vector_literal(v, dimensions)} for d, v in zip(documents, vectors, strict=True)]
        args = {"namespace": self.namespace, "revision": revision, "model": model, "dimensions": dimensions}
        async with self.session_context() as session:
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:namespace, 0))"), {"namespace": self.namespace})
            fields = "id,model,dimensions" if self.tables.bundle_id is not None else "model,dimensions"
            exists = (await session.execute(self._statement("SELECT " + fields + " FROM {bundle} WHERE namespace=:namespace AND revision=:revision"), args)).mappings().one_or_none()
            if exists is None:
                insert = "INSERT INTO {bundle}(namespace,revision,model,dimensions) VALUES (:namespace,:revision,:model,:dimensions)"
                if self.tables.bundle_id is not None:
                    bundle_id = (await session.execute(self._statement(insert + " RETURNING id"), args)).scalar_one()
                    records = [{"bundle_id": bundle_id, **record} for record in records]
                    await session.execute(self._statement("""INSERT INTO {document}({bundle_id},{document_key},content_hash,embedding)
                                              VALUES (:bundle_id,:id,:hash,CAST(:vector AS vector))"""), records)
                else:
                    await session.execute(self._statement(insert), args)
                    await session.execute(self._statement("""INSERT INTO {document}(namespace,revision,{document_key},content_hash,embedding)
                                           VALUES (:namespace,:revision,:id,:hash,CAST(:vector AS vector))"""), records)
            elif exists["model"] != model or exists["dimensions"] != dimensions:
                raise ValueError("Existing bundle identity differs")
            if self.tables.bundle_id is not None:
                if exists is not None:
                    bundle_id = exists["id"]
                args["bundle_id"] = bundle_id
                column, value, update = "{bundle_id}", ":bundle_id", "{bundle_id}=excluded.{bundle_id}"
            else:
                column, value, update = "revision", ":revision", "revision=excluded.revision"
            update += ", updated_at=now()" if "updated_at" in self.tables.active.c else ""
            await session.execute(self._statement("INSERT INTO {active}(namespace," + column + ") VALUES (:namespace," + value + ") ON CONFLICT (namespace) DO UPDATE SET " + update), args)
            await session.commit()

    async def vector_search(self, documents: list[dict], vector: list[float], model: str, dimensions: int, limit: int) -> tuple[list[str], str]:
        if not documents:
            return [], "ready"
        # One statement sees one active pointer, including concurrent bundle publication.
        # Authorization and hashes are materialized before exact cosine distance calculation.
        linked = self.tables.bundle_id is not None
        bundle_identity = "b.id AS bundle_id," if linked else ""
        active_join = "a.{bundle_id}=b.id" if linked else "a.revision=b.revision"
        document_join = "d.{bundle_id}=b.bundle_id" if linked else "b.revision=d.revision"
        document_scope = "" if linked else "d.namespace=:namespace AND "
        statement = self._statement("""WITH active AS MATERIALIZED (
            SELECT """ + bundle_identity + """b.revision,b.model,b.dimensions FROM {bundle} b
            JOIN {active} a ON a.namespace=b.namespace AND """ + active_join + """
            WHERE b.namespace=:namespace
        ), authorized AS MATERIALIZED (
            SELECT d.{document_key} AS id,d.embedding FROM {document} d
            JOIN active b ON """ + document_join + """
            JOIN jsonb_to_recordset(CAST(:allowed AS jsonb)) AS approved(id text, content_hash text)
              ON approved.id=d.{document_key} AND approved.content_hash=d.content_hash
            WHERE """ + document_scope + """b.model=:model AND b.dimensions=:dimensions
        ), ranked AS (
            SELECT id, embedding <=> CAST(:vector AS vector) AS distance FROM authorized
            ORDER BY distance, id LIMIT :limit
        ) SELECT (SELECT model FROM active) AS model, (SELECT dimensions FROM active) AS dimensions,
            (SELECT count(*) FROM authorized) AS matched_count,
            COALESCE((SELECT jsonb_agg(id ORDER BY distance,id) FROM ranked), '[]'::jsonb) AS ids""")
        args = {"namespace": self.namespace, "allowed": json.dumps([{"id": d["id"], "content_hash": d["content_hash"]} for d in documents]),
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

    async def index_status(self) -> dict | None:
        linked = self.tables.bundle_id is not None
        document_join = "d.{bundle_id}=b.id" if linked else "d.namespace=b.namespace AND d.revision=b.revision"
        active_join = "a.{bundle_id}=b.id" if linked else "a.revision=b.revision"
        async with self.session_context() as session:
            row = (await session.execute(self._statement("""SELECT b.namespace,b.revision,b.model,b.dimensions,b.created_at,
                (SELECT count(*) FROM {document} d WHERE """ + document_join + """) AS documents
                FROM {bundle} b JOIN {active} a
                ON a.namespace=b.namespace AND """ + active_join + """ WHERE b.namespace=:namespace"""), {"namespace": self.namespace})).mappings().one_or_none()
            return dict(row) if row else None
