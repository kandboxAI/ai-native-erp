"""旧插件隐私接口的兼容入口；不再扫描或改写业务内容。"""
from urllib.parse import urlsplit

def redact_messages(messages: list[object]) -> tuple[list[object], dict[str, int]]:
    # 保留调用契约，已安装插件无需为取消脱敏逐个升级。
    return messages, {}


def redact_public_source(source: dict) -> tuple[dict | None, dict[str, int]]:
    """只校验网页来源地址，不过滤网址参数或正文。"""
    try:
        parsed = urlsplit(source.get("url", ""))
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
            return source, {}
    except ValueError:
        pass
    return None, {"invalid_public_source": 1}
