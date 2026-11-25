"""Bind portable discovery to approved ERP metadata and scoped repositories."""
from fastapi import HTTPException
from pydantic import ValidationError

from app.integrations.harness_query_repository import RESOURCES, canonical_resource_name, read_query
from app.integrations.harness_query_schemas import QueryRequest
from resource_discovery.models import DiscoveryError, DiscoveryRequest

from . import catalog
from app.framework.plugin import loaded_plugin_manifests

# One index per server deployment composition; authorization still applies per request.
NAMESPACE = "erp." + (".".join(sorted(item.key for item in loaded_plugin_manifests())) or "core")


class ErpDiscoveryAdapter:
    namespace = NAMESPACE

    def compile_catalog(self):
        return catalog.compile_catalog()

    def authorize(self, documents, principal):
        return catalog.authorized_catalog(documents, principal)

    def redact_question(self, question, principal):
        return question

    def audit_actor(self, principal):
        return str(principal.user_id)

    def validate_query(self, query, principal):
        try:
            parsed = QueryRequest.model_validate(query)
            if parsed.operation == "plan":
                from app.integrations.harness_plan_repository import compile_erp_plan
                compiled = compile_erp_plan(parsed.plan, principal)
                return {"valid": True, "resources": compiled.resources, "grain": compiled.grain,
                        "group_totals_additive": compiled.group_totals_additive}
            parsed = parsed.model_copy(update={"resource": canonical_resource_name(parsed.resource)})
            if parsed.operation != "query":
                raise DiscoveryError(400, "validate requires a query operation")
            catalog.validate_query(parsed, principal)
        except ValidationError:
            raise DiscoveryError(422, "Invalid ERP query arguments") from None
        except HTTPException as error:
            raise DiscoveryError(error.status_code, error.detail) from None
        return {"valid": True, "resource": parsed.resource}

    async def execute_metric(self, document: dict, request: DiscoveryRequest, principal):
        if len(set(request.group_by)) != len(request.group_by) or set(request.group_by) - set(document["dimensions"]):
            raise DiscoveryError(400, "Unsupported metric dimension")
        try:
            query = QueryRequest.model_validate({**document["recipe"], "group_by": request.group_by,
                "filters": document["recipe"]["filters"] + request.filters, "limit": 100, "offset": request.offset})
            catalog.validate_query(query, principal)
            result = await read_query(RESOURCES[query.resource], query, principal)
        except ValidationError:
            raise DiscoveryError(422, "Invalid ERP metric arguments") from None
        except HTTPException as error:
            raise DiscoveryError(error.status_code, error.detail) from None
        return {"metric_id": document["id"], "definition": document["description"], "unit": document["unit"], "result": result}
