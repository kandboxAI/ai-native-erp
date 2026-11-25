"""Enable constraint-proven relations only between approved fields and resources."""
import hashlib
import json

from resource_query.compiler import Relation

from .harness_query_repository import RESOURCES
from .harness_schema_catalog import load_snapshot


def relation_id(source, fields, target, target_fields):
    identity = json.dumps([source, list(fields), target, list(target_fields)], separators=(",", ":"))
    return "relation:" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def approved_relations(resources=None, snapshot=None, semantics=None):
    resources = RESOURCES if resources is None else resources
    snapshot = load_snapshot() if snapshot is None else snapshot
    tables = {row['name']: row for row in snapshot["tables"]}
    result = {}

    def unique(name, fields):
        table = tables.get(name, {})
        return any(key and set(key) <= set(fields) for key in [table.get("primary_key", []), *table.get("unique_keys", [])])

    def add(source, fields, target, target_fields, origin):
        if source not in resources or target not in resources or not fields or len(fields) != len(target_fields):
            return
        if set(fields) - set(resources[source].ai_fields) or set(target_fields) - set(resources[target].ai_fields):
            return
        if not unique(target, target_fields):
            return
        kind = "one_to_one" if unique(source, fields) else "many_to_one"
        rid = relation_id(source, fields, target, target_fields)
        result[rid] = Relation(rid, source, target, tuple(fields), tuple(target_fields), kind, origin)
        reverse = relation_id(target, target_fields, source, fields)
        result[reverse] = Relation(reverse, target, source, tuple(target_fields), tuple(fields),
                                   "one_to_one" if kind == "one_to_one" else "one_to_many", origin)

    for source, table in sorted(tables.items()):
        for fk in table.get("foreign_keys", []):
            if fk.get("validated"):
                add(source, fk["fields"], fk["target"], fk["target_fields"], "foreign_key")
    if semantics is not None:
        for source, extra in semantics.resources.items():
            for relation in extra.relations:
                # Explicit business mappings may lack a database FK, but the
                # singular side must still have a database-proven unique key.
                if relation.cardinality == "one_to_many":
                    add(relation.target, [relation.target_field], source, [relation.field], "reviewed_mapping")
                else:
                    rid = relation_id(source, [relation.field], relation.target, [relation.target_field])
                    if rid not in result:
                        add(source, [relation.field], relation.target, [relation.target_field], "reviewed_mapping")
    return result


def relation_documents(source, relations):
    return [{"id": row.id, "field": row.fields[0], "fields": list(row.fields),
             "target": "resource:" + row.target, "target_field": row.target_fields[0],
             "target_fields": list(row.target_fields), "cardinality": row.cardinality,
             "origin": row.origin, "availability": "executable", "join_supported": True}
            for row in sorted(relations.values(), key=lambda row: row.id) if row.source == source]
