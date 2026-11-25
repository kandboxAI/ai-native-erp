"""Portable SQLAlchemy index models; the host's migrations own schema creation."""
from __future__ import annotations

from datetime import datetime

import numpy as np
from numpy.typing import NDArray
from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Integer, Text, UniqueConstraint, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DiscoveryBase(DeclarativeBase):
    """Own metadata, independent of an ERP's SQLModel registry and business tables."""


class DiscoveryBundle(DiscoveryBase):
    __tablename__ = "resource_discovery_bundles"
    __table_args__ = (
        CheckConstraint("dimensions > 0", name="resource_discovery_bundles_dimensions_check"),
        {"schema": "public"},
    )

    namespace: Mapped[str] = mapped_column(Text, primary_key=True)
    revision: Mapped[str] = mapped_column(Text, primary_key=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class DiscoveryDocument(DiscoveryBase):
    __tablename__ = "resource_discovery_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["namespace", "revision"],
            ["public.resource_discovery_bundles.namespace", "public.resource_discovery_bundles.revision"],
            name="resource_discovery_documents_namespace_revision_fkey",
        ),
        {"schema": "public"},
    )

    namespace: Mapped[str] = mapped_column(Text, primary_key=True)
    revision: Mapped[str] = mapped_column(Text, primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Dimensions are bundle metadata: different model generations can coexist.
    embedding: Mapped[NDArray[np.float32]] = mapped_column(Vector(), nullable=False)


class DiscoveryActive(DiscoveryBase):
    __tablename__ = "resource_discovery_active"
    __table_args__ = (
        ForeignKeyConstraint(
            ["namespace", "revision"],
            ["public.resource_discovery_bundles.namespace", "public.resource_discovery_bundles.revision"],
            name="resource_discovery_active_namespace_revision_fkey",
        ),
        {"schema": "public"},
    )

    namespace: Mapped[str] = mapped_column(Text, primary_key=True)
    revision: Mapped[str] = mapped_column(Text, nullable=False)


def validate_schema(connection, tables=None, *, schema=None) -> None:
    """Read-only compatibility check; never executes extension or table DDL."""
    inspector = inspect(connection)
    for table in DiscoveryBase.metadata.sorted_tables if tables is None else tables:
        target_schema = table.schema or schema
        if not inspector.has_table(table.name, schema=target_schema):
            raise RuntimeError(f"Discovery table {table.name} is missing; apply the host's scoped migrations")
        columns = {col["name"]: col for col in inspector.get_columns(table.name, schema=target_schema)}
        for expected in table.columns:
            actual = columns.get(expected.name)
            if actual is None or actual["nullable"] != expected.nullable \
                    or str(actual["type"].compile(dialect=connection.dialect)).upper() \
                       != str(expected.type.compile(dialect=connection.dialect)).upper():
                raise RuntimeError("Discovery schema differs from its ORM models; run/review host migrations")
        pk = inspector.get_pk_constraint(table.name, schema=target_schema)
        if pk["constrained_columns"] != [col.name for col in table.primary_key.columns]:
            raise RuntimeError("Discovery primary key differs from its ORM models")
        unique_keys = [tuple(c.name for c in item.columns) for item in table.constraints if isinstance(item, UniqueConstraint)]
        if unique_keys:
            actual_keys = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table.name, schema=target_schema)}
            if set(unique_keys) - actual_keys:
                raise RuntimeError("Discovery publication unique key is missing")
        actual_fks = inspector.get_foreign_keys(table.name, schema=target_schema)
        for expected in table.foreign_key_constraints:
            source = [element.parent.name for element in expected.elements]
            target = [element.column.name for element in expected.elements]
            referred_table = next(iter(expected.elements)).column.table
            if not any(fk["constrained_columns"] == source and fk["referred_columns"] == target
                       and fk["referred_table"] == referred_table.name
                       and fk.get("referred_schema") in (None, referred_table.schema or schema) for fk in actual_fks):
                raise RuntimeError("Discovery bundle foreign key is missing")
