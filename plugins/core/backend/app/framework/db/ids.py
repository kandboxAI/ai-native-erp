"""主键生成：UUIDv7（前 48 位为毫秒时间戳，按时间有序）。

应用写入时生成主键；数据库默认值 uuidv7()（PostgreSQL 18 内置）只作兜底。
Python 3.14 起标准库提供 uuid.uuid7()，此处在更低版本上按 RFC 9562 实现。
"""

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_last_seq = 0


def uuid7() -> uuid.UUID:
    """生成 UUIDv7；同一毫秒内用 12 位计数器保证单进程内单调递增。"""
    global _last_ms, _last_seq
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms > _last_ms:
            _last_ms = ms
            _last_seq = int.from_bytes(os.urandom(2), "big") & 0x07FF
        else:
            _last_seq += 1
            if _last_seq > 0x0FFF:
                _last_ms += 1
                _last_seq = 0
            ms = _last_ms
        seq = _last_seq
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFF_FFFF_FFFF_FFFF
    value = (ms & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76
    value |= seq << 64
    value |= 0b10 << 62
    value |= rand_b
    return uuid.UUID(int=value)
