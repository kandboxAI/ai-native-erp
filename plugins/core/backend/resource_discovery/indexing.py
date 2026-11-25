"""Explicit index maintenance with all embeddings prepared before atomic publication."""
from .catalog import digest, normalize_catalog, searchable_text, validate_namespace
from .models import DiscoverySettings
from .ports import DiscoveryAdapter, Embedder, VectorStore
from .providers import embedding_identity


async def build_index(adapter: DiscoveryAdapter, settings: DiscoverySettings, store: VectorStore, embedder: Embedder) -> str:
    namespace = validate_namespace(adapter.namespace)
    if store.namespace != namespace:
        raise ValueError("Adapter and vector store namespaces differ")
    documents = normalize_catalog(adapter.compile_catalog())
    if not documents:
        raise ValueError("Empty catalog cannot be published")
    identity = embedding_identity(settings)
    revision = digest({"namespace": namespace, "catalog": documents, "embedding_identity": identity})
    vectors = []
    batch = settings.embedding_batch_size
    for start in range(0, len(documents), batch):
        vectors.extend(await embedder.embed([searchable_text(d) for d in documents[start:start + batch]]))
    if documents != normalize_catalog(adapter.compile_catalog()):
        raise ValueError("Catalog changed while building; retry")
    await store.publish(revision, identity, settings.embedding_dimensions, documents, vectors)
    return revision
