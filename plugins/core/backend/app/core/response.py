from typing import Any


def success_response(data: Any = None, message: str = "success") -> dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "data": data,
    }


def paginated_response(*, items: list[Any], total: int, page: int, page_size: int) -> dict[str, Any]:
    return success_response(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )
