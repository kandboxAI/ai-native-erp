"""兼容业务状态派生的只读待办；已注册统一待办的模块不再重复投影。"""
from app.framework.todos import sources, todo_datetime


async def pending_projections(user, keyword, limit):
    items, total = [], 0
    for source in sources(user, exclude_registered=True):
        if keyword.strip():
            # 检索必须由业务来源按权限、范围过滤后计数，不能过滤截断后的页面。
            if source.search is None:
                continue
            result = await source.search(user, keyword, limit)
        else:
            result = await source.load(user, limit)
        total += result.total
        for item in result.items:
            items.append(dict(id=item.id, todo_type_key=source.key, type_label=item.description,
                source_id=item.id, title=item.title, summary=item.description,
                status_code="pending", assignee_status_code="pending", priority_code="normal",
                arrived_at=item.arrived_at, due_at=None, path=item.path, targets={"web": item.path},
                actions=[], is_projection=True, is_overdue=False))
    return items, total


def merged_page(items, query):
    def timestamp(value, fallback):
        parsed = todo_datetime(value)
        return parsed.timestamp() if parsed else fallback

    def order(item):
        arrived = -timestamp(item["arrived_at"], float("-inf"))
        return ({"urgent": 0, "important": 1}.get(item["priority_code"], 2),
                timestamp(item.get("due_at"), float("inf")), arrived, item["id"])

    if query.sort_by == "arrived_at":
        items.sort(key=lambda item: (timestamp(item["arrived_at"], float("-inf")), item["id"]), reverse=True)
    else:
        items.sort(key=order)
    start = (query.page - 1) * query.page_size
    return items[start:start + query.page_size]
