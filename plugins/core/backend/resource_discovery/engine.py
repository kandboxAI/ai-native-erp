"""Authorization-first discovery orchestration, independent of HTTP and ERP schemas."""
import json
import logging
from collections import Counter
from time import monotonic

import httpx
from sqlalchemy.exc import SQLAlchemyError

from .catalog import normalize_catalog, public_document, revision, searchable_text, validate_namespace
from .models import DiscoveryError, DiscoveryRequest, DiscoverySettings
from .ports import DiscoveryAdapter, Embedder, Reranker, VectorStore
from .providers import embedding_identity
from .ranking import rank

logger = logging.getLogger(__name__)


class DiscoveryEngine:
    def __init__(self, adapter: DiscoveryAdapter, settings: DiscoverySettings,
                 store: VectorStore, embedder: Embedder, reranker: Reranker | None = None):
        self.adapter = adapter
        self.namespace = validate_namespace(adapter.namespace)
        self.settings = settings
        self.store = store
        if store.namespace != self.namespace:
            raise ValueError("Adapter and vector store namespaces differ")
        self.embedder = embedder
        self.reranker = reranker

    def current_catalog(self, principal) -> list[dict]:
        complete = normalize_catalog(self.adapter.compile_catalog())
        authorized = self.adapter.authorize(complete, principal)
        by_id = {d["id"]: d for d in complete}
        # Authorization may select definitions, never rewrite or invent them.
        if any(by_id.get(d["id"]) != d for d in authorized) or len({d["id"] for d in authorized}) != len(authorized):
            raise ValueError("Adapter authorization must return a subset of reviewed definitions")
        allowed = {d["id"] for d in authorized}
        # Remove missing dependency chains to a fixed point.
        while True:
            retained = {d["id"] for d in authorized if d["id"] in allowed and all(dep in allowed for dep in d["dependencies"])}
            if retained == allowed:
                break
            allowed = retained
        return [d for d in authorized if d["id"] in allowed]

    def check_revision(self, expected: str, principal) -> None:
        if expected != revision(self.current_catalog(principal), self.namespace):
            raise DiscoveryError(409, "CATALOG_STALE")

    async def discover(self, request: DiscoveryRequest, principal) -> dict:
        started = monotonic()
        documents = self.current_catalog(principal)
        catalog_revision = revision(documents, self.namespace)
        by_id = {d["id"]: d for d in documents}
        if request.catalog_revision and request.catalog_revision != catalog_revision:
            raise DiscoveryError(409, "CATALOG_STALE")
        result = {"discovery_contract_version": 1, "catalog_revision": catalog_revision}
        if request.action == "domains":
            result["domains"] = [{"id": d, "resources": count} for d, count in sorted(Counter(d["domain"] for d in documents).items())]
        elif request.action == "describe":
            if len(request.ids) != len(set(request.ids)) or any(id_ not in by_id for id_ in request.ids):
                raise DiscoveryError(404, "RESOURCE_UNAVAILABLE")
            result["definitions"] = [public_document(by_id[id_], set(by_id)) for id_ in request.ids]
        elif request.action == "validate":
            result.update(self.adapter.validate_query(request.query, principal))
        elif request.action == "metric":
            doc = by_id.get(request.metric_id)
            if doc is None or doc["kind"] != "metric":
                raise DiscoveryError(404, "RESOURCE_UNAVAILABLE")
            result.update(await self.adapter.execute_metric(doc, request, principal))
        else:
            question = self.adapter.redact_question(request.question, principal)
            selected = [d for d in documents if not request.kinds or d["kind"] in request.kinds]
            vector_ids, vector_status = [], "not_configured"
            settings = self.settings
            if settings.embedding_url and selected:
                try:
                    vector = (await self.embedder.embed([question]))[0]
                    vector_ids, vector_status = await self.store.vector_search(selected, vector, embedding_identity(settings),
                                                     settings.embedding_dimensions, settings.recall_limit)
                    if len(set(vector_ids)) != len(vector_ids) or any(id_ not in {d["id"] for d in selected} for id_ in vector_ids):
                        raise ValueError("Vector store returned unauthorized IDs")
                    if vector_status != "ready":
                        vector_ids = []
                except (httpx.HTTPError, ValueError, SQLAlchemyError, OSError):
                    vector_ids, vector_status = [], "unavailable"
            ranked, matched = rank(question, selected, vector_ids, settings.recall_limit, request.domain_ids,
                                   lexical_enabled=settings.lexical_enabled)
            rerank_status = "not_configured"
            if self.reranker is not None and settings.rerank_url and ranked:
                try:
                    indexes = await self.reranker.rerank(question, [searchable_text(by_id[id_]) for id_ in ranked])
                    if sorted(indexes) != list(range(len(ranked))) or any(type(i) is not int for i in indexes):
                        raise ValueError("Invalid reranker indexes")
                    ranked = [ranked[i] for i in indexes]
                    rerank_status = "ready"
                except (httpx.HTTPError, ValueError, OSError):
                    rerank_status = "unavailable"
            chosen = ranked[:request.limit]
            result["candidates"] = [{"id": id_, "kind": by_id[id_]["kind"], "label": by_id[id_]["label"],
                "summary": by_id[id_]["description"], "capabilities": by_id[id_]["capabilities"], "matched_on": matched.get(id_, [])} for id_ in chosen]
            related = []
            for id_ in chosen:
                doc = by_id[id_]
                for target in [r["target"] for r in doc["relations"]] + doc["dependencies"]:
                    if target in by_id and target not in chosen and target not in related:
                        related.append(target)
            result["related_candidates"] = [{"id": id_, "label": by_id[id_]["label"], "kind": by_id[id_]["kind"]} for id_ in related[:12]]
            result.update(vector_status=vector_status, rerank_status=rerank_status,
                          lexical_enabled=settings.lexical_enabled, needs_clarification=not bool(chosen),
                          guidance="先 describe 核实字段、粒度和口径；只能使用定义声明的执行能力，缺少资源可改写问题补检索，不得猜测数据。")
        # Host policy can change during any awaited provider or execution call.
        self.check_revision(catalog_revision, principal)
        if len(json.dumps(result, ensure_ascii=False).encode()) > 45000:
            raise DiscoveryError(413, "Describe fewer resources or narrow the request")
        logger.info("discovery namespace=%s action=%s actor=%s revision=%s duration_ms=%d", self.namespace,
                    request.action, self.adapter.audit_actor(principal), catalog_revision, int((monotonic() - started) * 1000))
        return result
