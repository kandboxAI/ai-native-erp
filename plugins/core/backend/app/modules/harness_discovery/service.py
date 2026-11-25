"""FastAPI composition root for the portable engine and ERP adapter."""
from fastapi import HTTPException

from app.core.config import get_settings
from app.integrations.erp_discovery.adapter import ErpDiscoveryAdapter
from resource_discovery import DiscoveryEngine, DiscoveryError, DiscoverySettings
from resource_discovery.providers import EmbeddingClient, HttpReranker

from . import repository


def discovery_settings(settings) -> DiscoverySettings:
    return DiscoverySettings(
        embedding_url=settings.harness_embedding_url, embedding_api_key=settings.harness_embedding_api_key,
        embedding_model=settings.harness_embedding_model, embedding_dimensions=settings.harness_embedding_dimensions,
        embedding_batch_size=settings.harness_embedding_batch_size,
        embedding_send_dimensions=settings.harness_embedding_send_dimensions,
        timeout_seconds=settings.harness_discovery_timeout_seconds, recall_limit=settings.harness_discovery_recall_limit,
        lexical_enabled=settings.harness_discovery_lexical_enabled,
        rerank_url=settings.harness_rerank_url, rerank_api_key=settings.harness_rerank_api_key,
        rerank_model=settings.harness_rerank_model, rerank_protocol=settings.harness_rerank_protocol,
        rerank_instruct=settings.harness_rerank_instruct)


def create_engine() -> DiscoveryEngine:
    settings = discovery_settings(get_settings())
    return DiscoveryEngine(ErpDiscoveryAdapter(), settings, repository.create_store(), EmbeddingClient(settings), HttpReranker(settings))


def current_catalog(user):
    return create_engine().current_catalog(user)


def check_revision(expected, user):
    try:
        create_engine().check_revision(expected, user)
    except DiscoveryError as error:
        raise HTTPException(error.status_code, error.detail) from None


async def discover(request, user):
    try:
        return await create_engine().discover(request, user)
    except DiscoveryError as error:
        raise HTTPException(error.status_code, error.detail) from None
