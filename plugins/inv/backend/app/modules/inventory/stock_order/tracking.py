"""库存明细追踪扩展：保存、读取及过账共用事务，库存不依赖追踪拥有者。"""

_providers = {}
_source_contexts = {}


def register_tracking_source(source_type, resolver):
    """来源模块提供已鉴权的流转上下文；客户端 tracking 不能声明该上下文。"""
    _source_contexts[source_type] = resolver


async def source_tracking_context(session, order, user):
    resolver = _source_contexts.get(order.source_doc_type_code)
    return await resolver(session, order, user) if resolver else {}


def register_tracking_provider(key, provider):
    _providers[key] = provider


async def save_tracking(session, order, lines, payloads, user):
    from app.core.exceptions import AppException
    for line, payload in zip(lines, payloads, strict=True):
        unknown = set(payload.tracking) - set(_providers)
        if unknown:
            raise AppException("单据包含未支持的实物追踪配置", status_code=400)
        for key, provider in _providers.items():
            await provider.save(session, order, line, payload.tracking.get(key), user)


async def read_tracking(session, line):
    result = {}
    for key, provider in _providers.items():
        value = await provider.read(session, line)
        if value is not None:
            result[key] = value
    return result


async def post_tracking(session, order, order_type, lines, items, warehouses, transactions, user):
    for provider in _providers.values():
        await provider.post(session, order, order_type, lines, items, warehouses, transactions, user)


async def prepare_tracking(session, order, lines, user, *, order_type=None, items=None, warehouses=None):
    result = {}
    for provider in _providers.values():
        for line_id, quotas in (await provider.prepare(
            session, order, lines, user, order_type=order_type, items=items, warehouses=warehouses,
        )).items():
            if line_id in result:
                from app.core.exceptions import AppException
                raise AppException("单据明细包含冲突的实物批次分配", status_code=400)
            result[line_id] = quotas
    return result
