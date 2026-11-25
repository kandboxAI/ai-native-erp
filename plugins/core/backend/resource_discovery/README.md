# ERP Resource Discovery

Portable Python metadata discovery with no dependency on `app`, FastAPI, SQLModel business models, education resources, roles or a particular query language. The distribution is `erp-resource-discovery`; Python imports use `resource_discovery`.

## Responsibilities

- `engine.py`: authorized search, bounded describe, revision validation and adapter dispatch.
- `catalog.py`: normalized definitions, dependency checks, hashes and public projection.
- `ports.py`: ERP adapter, vector repository, embedding and reranking interfaces.
- `ranking.py`: exact identifiers, optional BM25, dense vector ranks and RRF.
- `providers.py`: OpenAI-compatible dense embedding requests and optional compatible/DashScope HTTP reranking protocols.
- `repository.py`: SQLAlchemy session factory injection and pgvector bundles scoped by namespace.
- `orm.py`: independent SQLAlchemy models for bundles/documents/active, registered with the host migration metadata.
- `indexing.py`: explicit index builds with atomic publication after all embeddings succeed.

## Integration

Implement `DiscoveryAdapter` from `ports.py`. The host owns catalog import (ORM/schema comments, OpenAPI, reviewed manifests), authentication, resource/field approval, data scopes, privacy projection, query validation and execution. `principal` is opaque to the core: it can be a host user object, dictionary or another authenticated identity.

```python
from resource_discovery import DiscoveryEngine, DiscoveryRequest, DiscoverySettings
from resource_discovery.providers import EmbeddingClient, HttpReranker
from resource_discovery.repository import PgVectorRepository

# adapter and session_context are supplied by your ERP, not by the model.
settings = DiscoverySettings(
    embedding_url="https://your-provider.example/v1/embeddings",
    embedding_model="your-model",
    embedding_dimensions=1024,
)
store = PgVectorRepository(session_context, adapter.namespace)
engine = DiscoveryEngine(adapter, settings, store, EmbeddingClient(settings), HttpReranker(settings))
result = await engine.discover(DiscoveryRequest(action="search", question="库存数量"), authenticated_principal)
```

The host maps `DiscoveryError.status_code/detail` to its HTTP envelope. It maps embedding and reranking failures to a degraded discovery result without publishing provider error bodies. Its query executor must reapply current permissions and row scopes; discover results are not credentials or authorization grants. Every field in returned definitions must already be approved by the adapter. Do not use raw business rows as definitions or embeddings.

`compile_catalog()` returns normalized resource/operation/metric dictionaries; `authorize()` returns a subset without modifying them. Relations must target known definitions. Missing authorized dependencies remove their dependents, including metrics. Core metadata schemas do not infer foreign-key execution, metric business meaning or sensitive fields. Execution tool names and parameter objects come from the adapter. No arbitrary SQL executor is included.

## Maintenance and packaging

```python
from resource_discovery.indexing import build_index

await store.initialize()  # Optional read-only schema check, after host migrations.
revision = await build_index(adapter, settings, store, EmbeddingClient(settings))
status = await store.index_status()
```

Build a reusable wheel from the ERP repository root with `uv build backend/resource_discovery --wheel`. Other Python ERP repositories can install that wheel; non-Python backends can expose the same discovery JSON protocol through a service wrapping this library. Host API routes, auth token transport and execution tool registration still require an ERP adapter.

The host owns schema changes. Supply trusted ORM tables through `IndexTables` when constructing `PgVectorRepository`; the repository quotes their table and document-key identifiers and uses the host session factory. The ERP host binds tenant-local `ai_resource_bundle`, `ai_resource_document` and `ai_resource_active` SQLModel tables, with standard UUID keys and audit columns. Legacy `DiscoveryBase` models remain available for standalone consumers, but are no longer included in the ERP host migrations. Install pgvector and apply reviewed, scoped host migrations before building vectors. `init` validates structure without DDL; runtime never calls `create_all`.

Namespace is trusted server configuration, never a request parameter. Use distinct namespaces for independently managed ERP catalogs/tenant schemas; identical table identifiers can coexist. All repositories and engines for one catalog must use the same namespace. This is index isolation, not a substitute for business row authorization. Existing `harness_discovery_*` indexes are not reused; host migrations manage the new `resource_discovery_*` tables. Index publication remains independent of schema migration and does not automatically call embedding during deployment.

BM25 remains enabled by default. `lexical_enabled=False` disables BM25 while preserving deterministic identifier/path/field matching. With embedding unavailable, natural-language recall may be empty in that mode. Dense embeddings do not replace exact identifiers. Changing dimensions/model/provider or embedding text format requires rebuilding; keys are never stored in index identity.

Reranking wire protocols are explicit provider configuration, independent of ERP schemas and model names. `rerank_protocol="compatible"` (default) sends `{model,query,documents,top_n,instruct?}` and reads top-level `results`. `rerank_protocol="dashscope"` sends `{model,input:{query,documents},parameters:{top_n,instruct?}}` and reads `output.results`; use this for `qwen3.7-text-rerank` with the full native endpoint `/api/v1/services/rerank/text-rerank/text-rerank`. Optional `rerank_instruct` guides metadata selection. Only redacted questions and authorized metadata reach the provider. All candidate indexes and finite scores must be returned; the engine limits results after sorting. Provider errors and invalid responses degrade to the original fused ranks. Reranking model/protocol/instruction changes do not require rebuilding embeddings. See the host setup document for the region/workspace URL and environment variables.

The core acceptance suite in `backend/tests/test_resource_discovery_core.py` uses a retail ERP with an opaque principal, verifies app-free imports, non-education execution mappings, permission changes, provider redaction and build failures. Real pgvector tests require a disposable database and are not implied by keyless tests. Business recall and provider accuracy require a separate ERP-specific evaluation set.
