"""由服务端内部派发建立的模型调用上下文；不信任客户端自报请求头。"""

from contextlib import contextmanager
from contextvars import ContextVar

_model_request = ContextVar("model_request", default=False)


def is_model_request():
    return _model_request.get()


@contextmanager
def model_request_context():
    token = _model_request.set(True)
    try:
        yield
    finally:
        _model_request.reset(token)
