"""按 SDK 片段发布原始回答；不再为隐私识别缓存或替换文本。"""


def protected_text(text):
    return text


class ProtectedTextStream:
    # 类名保留兼容，feed/finish 仍返回累积答案。
    def __init__(self):
        self.answer = ""

    def feed(self, text):
        self.answer += text
        return self.answer

    def finish(self):
        return self.answer
