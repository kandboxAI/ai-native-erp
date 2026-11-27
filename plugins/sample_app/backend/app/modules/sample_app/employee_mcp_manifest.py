"""对发票文件名、大小和传输校验值计算稳定摘要，不保存文件内容。"""
import hashlib
import json


def manifest_hash(files):
    values = sorted((item["file_name"], item["file_size"], item["content_md5"]) for item in files)
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
