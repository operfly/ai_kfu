# tests/test_orchestrator.py
import asyncio

import pytest

from pinduoduo_ai.knowledge import KnowledgeBase
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

KB_MD = """# 测试话术库
## 发货
- 问发货时间：亲，我们承诺 48 小时内发货的哦～
## 物流
- 问物流进度：亲，您可以在【我的订单】里查看物流单号
"""


class FakeAI:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def generate_reply(self, history, shop_context=""):
        self.calls.append((history, shop_context))
        return self.result


class FakeApi:
    def __init__(self, send_ok=True, cs_list=None, move_ok=True):
        self.send_ok = send_ok
        self.sent = []
        self.cs_list = cs_list
        self.move_ok = move_ok
        self.transfers = []

    async def send_text(self, uid, content):
        self.sent.append((uid, content))
        return self.send_ok

    async def get_assign_cs_list(self):
        return self.cs_list

    async def move_conversation(self, recipient_uid, cs_uid):
        self.transfers.append((recipient_uid, cs_uid))
        return self.move_ok


def _msg(content="在吗", uid="buyer-1"):
    return IncomingMessage(msg_id="m1", uid=uid, type=MsgType.TEXT, content=content, nickname="买家A")


def run(coro):
    return asyncio.run(coro)


def _make(ai_result, send_ok=True, sensitive=None, kb=None, cs_list=None, move_ok=True):
    ai = FakeAI(ai_result)
    api = FakeApi(send_ok=send_ok, cs_list=cs_list, move_ok=move_ok)
    sm = SessionManager()
    orch = Orchestrator(CONFIG, api, sm, ai, sensitive_words=sensitive, knowledge=kb)
    return orch, api, sm, ai


def _make_kb(tmp_path=None):
    import tempfile
    from pathlib import Path

    if tmp_path:
        p = tmp_path / "kb.md"
    else:
        tmp = tempfile.mkdtemp()
        p = Path(tmp) / "kb.md"
    p.write_text(KB_MD, encoding="utf-8")
    return KnowledgeBase(p)


def test_reply_flow_sends_message(tmp_path):
    kb = _make_kb(tmp_path)
    orch, api, sm, ai = _make({"action": "reply", "text": "亲，我们承诺 48 小时内发货"}, kb=kb)
    action = run(orch.handle_message(_msg(content="什么时候发货")))
    assert api.sent == [("buyer-1", "亲，我们承诺 48 小时内发货")]
    assert action["action"] == "reply"
    assert sm.get_state("buyer-1").value == "replied"
    # 检索到的话术注入 AI
    assert "48 小时内发货" in ai.calls[0][1]


def test_sensitive_triggers_handoff_no_send(tmp_path):
    kb = _make_kb(tmp_path)
    cs_list = [{"uid": "cs_111_222", "username": "客服A"}]
    orch, api, sm, ai = _make({"action": "reply", "text": "可以退款的亲"}, kb=kb, cs_list=cs_list)
    action = run(orch.handle_message(_msg(content="发货了吗")))
    assert api.sent == []  # 含"退款"被拦截，不发送 AI 回复
    assert api.transfers == [("buyer-1", "cs_111_222")]  # 转接给了客服
    assert action["action"] == "handoff"
    assert sm.get_state("buyer-1").value == "handoff"


def test_handoff_action_no_send(tmp_path):
    kb = _make_kb(tmp_path)
    cs_list = [{"uid": "cs_111_222", "username": "客服A"}]
    orch, api, sm, ai = _make({"action": "handoff", "text": "涉及退款"}, kb=kb, cs_list=cs_list)
    action = run(orch.handle_message(_msg(content="发货了吗")))
    assert api.sent == []
    assert api.transfers == [("buyer-1", "cs_111_222")]
    assert action["action"] == "handoff"
    assert sm.get_state("buyer-1").value == "handoff"


def test_unclear_no_send_no_state(tmp_path):
    kb = _make_kb(tmp_path)
    orch, api, sm, ai = _make({"action": "unclear", "text": ""}, kb=kb)
    action = run(orch.handle_message(_msg(content="发货了吗")))
    assert api.sent == []
    assert action["action"] == "unclear"
    assert sm.get_state("buyer-1").value == "processing"


def test_no_knowledge_hit_handoff_no_ai_call(tmp_path):
    """买家问题未命中任何话题 → 直接转人工，不调用 AI。"""
    kb = _make_kb(tmp_path)
    cs_list = [{"uid": "cs_111_222", "username": "客服A"}]
    orch, api, sm, ai = _make({"action": "reply", "text": "x"}, kb=kb, cs_list=cs_list)
    action = run(orch.handle_message(_msg(content="今天天气怎么样")))
    assert api.sent == []
    assert ai.calls == []  # 未调用 AI
    assert api.transfers == [("buyer-1", "cs_111_222")]
    assert action["action"] == "handoff"
    assert sm.get_state("buyer-1").value == "handoff"


def test_no_knowledge_base_all_handoff(tmp_path):
    """未配置知识库 → 所有消息直接转人工。"""
    cs_list = [{"uid": "cs_111_222", "username": "客服A"}]
    orch, api, sm, ai = _make({"action": "reply", "text": "x"}, cs_list=cs_list)  # kb=None
    action = run(orch.handle_message(_msg(content="什么时候发货")))
    assert api.sent == []
    assert ai.calls == []
    assert api.transfers == [("buyer-1", "cs_111_222")]
    assert action["action"] == "handoff"


def test_cooldown_skips_reply(tmp_path):
    kb = _make_kb(tmp_path)
    orch, api, sm, ai = _make({"action": "reply", "text": "x"}, kb=kb)
    run(orch.handle_message(_msg(uid="a", content="发货了吗")))  # 先回复一次
    action = run(orch.handle_message(_msg(uid="a", content="发货了吗")))  # 冷却期内
    assert action["action"] == "skip"
    assert len(api.sent) == 1


def test_send_failure_uses_fallback(tmp_path):
    kb = _make_kb(tmp_path)
    orch, api, sm, ai = _make({"action": "reply", "text": "正常回复"}, send_ok=False, kb=kb)
    action = run(orch.handle_message(_msg(content="发货了吗")))
    assert api.sent == [
        ("buyer-1", "正常回复"),
        ("buyer-1", "亲，客服正在为您处理，请稍等片刻。"),
    ]
    assert action["note"] == "send_failed_fallback"


# ===== 真实转人工 =====

def test_no_knowledge_hit_transfers_to_cs(tmp_path):
    """无命中 → 转人工 → 调 get_assign_cs_list + move_conversation。"""
    kb = _make_kb(tmp_path)
    cs_list = [{"uid": "cs_111_222", "username": "客服A"}, {"uid": "cs_333_444", "username": "客服B"}]
    orch, api, sm, ai = _make({"action": "reply", "text": "x"}, kb=kb, cs_list=cs_list)
    action = run(orch.handle_message(_msg(content="今天天气怎么样")))
    assert ai.calls == []  # 未调用 AI
    assert action["action"] == "handoff"
    # 转给了第一个非自己的客服
    assert ("buyer-1", "cs_111_222") in api.transfers
    assert sm.get_state("buyer-1").value == "handoff"


def test_no_available_cs_sends_hint(tmp_path):
    """无可用客服 → 不转接，发提示话术。"""
    kb = _make_kb(tmp_path)
    orch, api, sm, ai = _make({"action": "reply", "text": "x"}, kb=kb, cs_list=None)
    action = run(orch.handle_message(_msg(content="今天天气怎么样")))
    assert api.transfers == []
    assert action["action"] == "handoff"
    # 发送了"无客服在线"提示
    assert any("客服" in c for _, c in api.sent)
    assert sm.get_state("buyer-1").value == "handoff"


def test_transfer_failure_marks_handoff(tmp_path):
    """转接失败 → 标记 HANDOFF，不发提示（保持现状）。"""
    kb = _make_kb(tmp_path)
    cs_list = [{"uid": "cs_111_222", "username": "客服A"}]
    orch, api, sm, ai = _make({"action": "reply", "text": "x"}, kb=kb, cs_list=cs_list, move_ok=False)
    action = run(orch.handle_message(_msg(content="今天天气怎么样")))
    assert api.transfers == [("buyer-1", "cs_111_222")]  # 尝试了转接
    assert action["action"] == "handoff"
    assert sm.get_state("buyer-1").value == "handoff"


def test_sensitive_reply_triggers_transfer(tmp_path):
    """AI 回复含敏感词 → 转人工 → 转接。"""
    kb = _make_kb(tmp_path)
    cs_list = [{"uid": "cs_111_222", "username": "客服A"}]
    orch, api, sm, ai = _make({"action": "reply", "text": "可以退款的亲"}, kb=kb, cs_list=cs_list)
    action = run(orch.handle_message(_msg(content="发货了吗")))
    assert api.sent == []  # 敏感词回复不发送
    assert api.transfers == [("buyer-1", "cs_111_222")]
    assert action["action"] == "handoff"
