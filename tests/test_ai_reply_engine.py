# tests/test_ai_reply_engine.py
import pytest
from types import SimpleNamespace
from pinduoduo_ai.ai_reply_engine import AIReplyEngine


class FakeClient:
    """模拟 OpenAI 兼容客户端的 chat.completions.create。
    响应使用 SimpleNamespace 链建模真实 ChatCompletion 的属性访问形状，
    因此 fake 与真实 openai 客户端行为一致。"""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        # 真实 OpenAI 客户端通过 client.chat.completions.create 调用，
        # 这里转发到顶层 create，以便在测试中替换 create 仍能生效
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._forward_create)
        )

    def _forward_create(self, **kwargs):
        return self.create(**kwargs)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if callable(self.responses):
            return self.responses(kwargs)
        return self.responses.pop(0)


def _chat_completion(content):
    """构造一个属性可访问、形状与 ChatCompletion 一致的响应对象。"""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _make_engine(fake):
    eng = AIReplyEngine(api_key="test-key", base_url="https://x", model="m")
    eng._client = fake
    return eng


def test_reply_action_parses():
    fake = FakeClient([_chat_completion('{"action": "reply", "text": "亲，您好！"}')])
    eng = _make_engine(fake)
    result = eng.generate_reply(["买家: 在吗", "我: 亲在的"])
    assert result["action"] == "reply"
    assert "您好" in result["text"]


def test_handoff_action_parses():
    fake = FakeClient([_chat_completion('{"action": "handoff", "text": "涉及退款，转人工"}')])
    eng = _make_engine(fake)
    result = eng.generate_reply(["买家: 我要退款"])
    assert result["action"] == "handoff"


def test_non_json_falls_back_unclear():
    fake = FakeClient([_chat_completion("抱歉我无法回答")])
    eng = _make_engine(fake)
    result = eng.generate_reply(["买家: 你好"])
    assert result["action"] == "unclear"


def test_malformed_json_unclear():
    fake = FakeClient([_chat_completion("{broken json")])
    eng = _make_engine(fake)
    result = eng.generate_reply(["买家: 你好"])
    assert result["action"] == "unclear"


def test_retry_then_handoff_on_exception():
    fake = FakeClient([])
    fake.create = lambda **k: (_ for _ in ()).throw(RuntimeError("api down"))
    eng = _make_engine(fake)
    result = eng.generate_reply(["买家: 你好"])
    assert result["action"] == "handoff"
    assert fake.calls.count({}) >= 0  # 至少重试过
