"""Normalized metadata, immutable hashes and model-visible projection."""
import hashlib
import json
import re
from typing import Any, Literal

from pydantic import Field

from .models import StrictModel


class Definition(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    kind: Literal["resource", "operation", "metric"]
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    domain: str = Field(min_length=1, max_length=80)
    grain: str = Field(default="", max_length=512)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    execution: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    response_resource: str | None = None
    parameter_contract: str | None = None
    unit: str | None = None
    dimensions: list[str] = Field(default_factory=list)
    # Private adapter metadata: absent from embedding text and describe responses.
    permissions_any: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    recipe: dict[str, Any] | None = None
    plugin_key: str | None = None
    content_hash: str | None = None


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_namespace(namespace: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}", namespace):
        raise ValueError("Invalid discovery namespace")
    return namespace


def normalize_catalog(documents: list[dict]) -> list[dict]:
    """Validate adapter metadata and compute hashes; schemas never grant permissions."""
    result = []
    ids = set()
    for source in documents:
        doc = Definition.model_validate(source).model_dump(exclude_unset=True)
        doc.pop("content_hash", None)
        for name in ("fields", "relations", "aliases", "capabilities", "dependencies"):
            doc.setdefault(name, [])
        if doc["id"] in ids:
            raise ValueError("Duplicate discovery definition")
        ids.add(doc["id"])
        doc["content_hash"] = digest(doc)
        result.append(doc)
    for doc in result:
        if any(id_ not in ids for id_ in doc["dependencies"]):
            raise ValueError("Discovery dependency is missing")
        if any(not isinstance(r.get("target"), str) or r["target"] not in ids for r in doc["relations"]):
            raise ValueError("Discovery relation is missing")
    return sorted(result, key=lambda doc: doc["id"])


def revision(documents: list[dict], namespace: str) -> str:
    return "sha256:" + digest({"namespace": namespace, "definitions": sorted((d["id"], d["content_hash"]) for d in documents)})


def public_document(doc: dict, allowed: set[str]) -> dict:
    return {key: ([r for r in value if r["target"] in allowed] if key == "relations" else value)
            for key, value in doc.items() if key not in {"permissions_any", "dependencies", "content_hash", "recipe", "plugin_key"}}


def searchable_text(doc: dict) -> str:
    # Include paths and approved parameter/field descriptions, never recipe/permissions/rows.
    return " ".join([doc["id"], doc["label"], doc.get("description", ""), doc.get("grain", ""),
                     *doc.get("aliases", []), str(doc.get("execution", {}).get("path", "")),
                     *[" ".join([f["name"], f.get("description", ""), *f.get("aliases", [])]) for f in doc.get("fields", [])],
                     *[" ".join([name, str(spec.get("description", ""))]) for name, spec in doc.get("parameters", {}).items()]])
