def is_oss_configured() -> bool:
    return False


def get_object_access_url(bucket: str, key: str) -> str:
    raise RuntimeError("OSS 未配置")
