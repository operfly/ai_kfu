# tests/test_orchestrator.py
from pinduoduo_ai.orchestrator import Orchestrator
from pinduoduo_ai.session_manager import SessionManager
from pinduoduo_ai.ai_reply_engine import AIReplyEngine
from pinduoduo_ai.safety import default_sensitive_words

CONFIG = {
    "polling": {
        "interval_seconds": 1,
        "conversation_cooldown_seconds": 60,
        "global_rate_limit_seconds": 1,
        "daily_reply_limit": 100,
    },
    "ai": {"max_history_messages": 20},
}


class FakeBrowser:
    def __init__(self, convos, messages, sent=None):
        self.convos = convos
        self.messages = messages
        self.sent = sent if sent is not None else []

    def ensure_service_page(self):
        return object()

    def get_conversations(self, page):
        return self.convos

    def open_conversation(self, page, name):
        return True

    def read_last_messages(self, page, n=20):
        return self.messages

    def fill_and_send(self, page, text):
        self.sent.append(text)
        return True

    def close(self):
        pass


class FakeAI:
    def __init__(self, result):
        self.result = result

    def generate_reply(self, history, shop_context=""):
        return self.result


def _make_orch(convos, ai_result, messages=None):
    b = FakeBrowser(convos, messages or ["买家: 在吗", "我: 亲在的"], sent=[])
    sm = SessionManager()
    ai = FakeAI(ai_result)
    return Orchestrator(CONFIG, b, sm, ai, default_sensitive_words()), b, sm


def test_reply_flow_sends_message():
    orch, b, sm = _make_orch(
        [{"name": "买家A", "has_unread": True}],
        {"action": "reply", "text": "亲，您好！请问有什么可以帮您？"},
    )
    actions = orch.run_once()
    assert b.sent == ["亲，您好！请问有什么可以帮您？"]
    assert actions[0]["action"] == "reply"
    assert sm.get_state("买家A").value == "replied"


def test_sensitive_triggers_handoff_no_send():
    orch, b, sm = _make_orch(
        [{"name": "买家A", "has_unread": True}],
        {"action": "reply", "text": "可以退款的亲"},
    )
    actions = orch.run_once()
    assert b.sent == []  # 含"退款"的回复被拦截，不发送
    assert actions[0]["action"] == "handoff"
    assert sm.get_state("买家A").value == "handoff"


def test_handoff_action_no_send():
    orch, b, sm = _make_orch(
        [{"name": "买家A", "has_unread": True}],
        {"action": "handoff", "text": "涉及退款"},
    )
    actions = orch.run_once()
    assert b.sent == []
    assert sm.get_state("买家A").value == "handoff"


def test_no_unread_no_action():
    orch, b, sm = _make_orch(
        [{"name": "买家A", "has_unread": False}],
        {"action": "reply", "text": "x"},
    )
    actions = orch.run_once()
    assert actions == []
