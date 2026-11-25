"""将已加载能力包的审核语义合并到通用 ERP 发现目录。"""

from app.framework.ai_catalog import ai_providers
from .erp_discovery.models import Semantics


def load_semantics() -> Semantics:
    resources = {}
    metrics = {}
    for _, provider in ai_providers():
        if provider.semantics_path is None:
            continue
        source = Semantics.model_validate_json(provider.semantics_path.read_text(encoding="utf-8"))
        declared = {item.table_name for item in provider.resources}
        if set(source.resources) - declared or any(item.resource not in declared for item in source.metrics.values()):
            raise ValueError(f"AI 提供器 {provider.domain} 的语义引用了未声明资源")
        if resources.keys() & source.resources.keys() or metrics.keys() & source.metrics.keys():
            raise ValueError("AI 资源或指标语义重复")
        resources.update(source.resources)
        metrics.update(source.metrics)
    return Semantics(version=1, resources=resources, metrics=metrics)
