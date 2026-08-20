# tests/test_orchestrator.py
import asyncio

import pytest

from pinduoduo_ai.message_types import IncomingMessage, MsgType
from pinduoduo_ai.orchestrator import Orchestrator
from pinduoduo_ai.session_manager import SessionManager


CONFIG = {
    "polling": {
        "conversation_cooldown_seconds": 60,
        "global_rate_limit_seconds": 1,
        "daily_reply_limit": 100,
    },
    "shop_context": {"file": ""},
    "fallback_text": "亲，客服正在为您处理，请稍等片刻。",
}


class FakeAI:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def generate_reply(self, history, shop_context=""):
        self.calls.append((history, shop_context))
        return self.result


class FakeApi:
    def __init__(self, send_ok=True):
        self.send_ok = send_ok
        self.sent = []

    async def send_text(self, uid, content):
        self.sent.append((uid, content))
        return self.send_ok


def _msg(content="在吗", uid="buyer-1"):
    return IncomingMessage(msg_id="m1", uid=uid, type=MsgType.TEXT, content=content, nickname="买家A")


def run(coro):
    return asyncio.run(coro)


def _make(ai_result, send_ok=True, sensitive=None):
    ai = FakeAI(ai_result)
    api = FakeApi(send_ok=send_ok)
    sm = SessionManager()
    orch = Orchestrator(CONFIG, api, sm, ai, sensitive_words=sensitive)
    return orch, api, sm, ai


def test_reply_flow_sends_message():
    orch, api, sm, ai = _make({"action": "reply", "text": "亲，您好！请问有什么可以帮您？"})
    action = run(orch.handle_message(_msg()))
    assert api.sent == [("buyer-1", "亲，您好！请问有什么可以帮您？")]
    assert action["action"] == "reply"
    assert sm.get_state("buyer-1").value == "replied"


def test_sensitive_triggers_handoff_no_send():
    orch, api, sm, ai = _make({"action": "reply", "text": "可以退款的亲"})
    action = run(orch.handle_message(_msg()))
    assert api.sent == []  # 含"退款"被拦截
    assert action["action"] == "handoff"
    assert sm.get_state("buyer-1").value == "handoff"


def test_handoff_action_no_send():
    orch, api, sm, ai = _make({"action": "handoff", "text": "涉及退款"})
    action = run(orch.handle_message(_msg()))
    assert api.sent == []
    assert action["action"] == "handoff"
    assert sm.get_state("buyer-1").value == "handoff"


def test_unclear_no_send_no_state():
    orch, api, sm, ai = _make({"action": "unclear", "text": ""})
    action = run(orch.handle_message(_msg()))
    assert api.sent == []
    assert action["action"] == "unclear"
    # unclear 不标记 replied/handoff，但已进入 processing
    assert sm.get_state("buyer-1").value == "processing"


def test_cooldown_skips_reply():
    orch, api, sm, ai = _make({"action": "reply", "text": "x"})
    run(orch.handle_message(_msg(uid="a")))  # 先回复一次
    action = run(orch.handle_message(_msg(uid="a")))  # 冷却期内
    assert action["action"] == "skip"
    assert len(api.sent) == 1


def test_send_failure_uses_fallback():
    orch, api, sm, ai = _make({"action": "reply", "text": "正常回复"}, send_ok=False)
    action = run(orch.handle_message(_msg()))
    # 先试发原回复失败，再补发兜底话术
    assert api.sent == [
        ("buyer-1", "正常回复"),
        ("buyer-1", "亲，客服正在为您处理，请稍等片刻。"),
    ]
    assert action["note"] == "send_failed_fallback"


def test_shop_context_loaded_and_passed():
    orch, api, sm, ai = _make({"action": "unclear", "text": ""})
    # 无 shop_context 文件时传入空串
    run(orch.handle_message(_msg()))
    assert ai.calls[0][1] == ""
