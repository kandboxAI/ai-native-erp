"""Read PostgreSQL constraints for the independent schema snapshot command."""

_CONSTRAINT_SQL = """
SELECT n.nspname AS schema_name, c.relname AS table_name, k.contype::text AS kind,
       ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY u(num, pos)
             JOIN pg_catalog.pg_attribute a ON a.attrelid=k.conrelid AND a.attnum=u.num ORDER BY u.pos) AS fields,
       tn.nspname AS target_schema, tc.relname AS target_table,
       ARRAY(SELECT a.attname FROM unnest(k.confkey) WITH ORDINALITY u(num, pos)
             JOIN pg_catalog.pg_attribute a ON a.attrelid=k.confrelid AND a.attnum=u.num ORDER BY u.pos) AS target_fields,
       k.convalidated AS validated
FROM pg_catalog.pg_constraint k
JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
LEFT JOIN pg_catalog.pg_class tc ON tc.oid=k.confrelid
LEFT JOIN pg_catalog.pg_namespace tn ON tn.oid=tc.relnamespace
WHERE n.nspname=$1 AND k.contype IN ('p','u','f')
ORDER BY c.relname, k.contype, k.conname
"""


def attach_constraints(snapshot, rows, *, schema):
    tables = {row["name"]: row for row in snapshot["tables"]}
    for table in tables.values():
        table.update(primary_key=[], unique_keys=[], foreign_keys=[])
    for row in rows:
        table = tables.get(row["table_name"]) if row["schema_name"] == schema else None
        if table is None:
            continue
        fields = list(row["fields"])
        kind = row["kind"].decode("ascii") if isinstance(row["kind"], bytes) else row["kind"]
        if kind == "p":
            table["primary_key"] = fields
        elif kind == "u":
            table["unique_keys"].append(fields)
        elif kind == "f":
            # Only relations inside this tenant can be exposed or executed.
            if row['target_schema'] != schema or row['target_table'] not in tables:
                continue
            table["foreign_keys"].append({"fields": fields,
                "target": row['target_table'],
                "target_fields": list(row["target_fields"]), "validated": bool(row["validated"])})
        else:
            raise RuntimeError("Unknown PostgreSQL constraint kind")
    for table in tables.values():
        table["unique_keys"].sort()
        table["foreign_keys"].sort(key=lambda row: (row["fields"], row["target"], row["target_fields"]))
    return snapshot


async def read_constraints(connection, schema):
    return await connection.fetch(_CONSTRAINT_SQL, schema)
