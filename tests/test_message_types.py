# tests/test_message_types.py
from pinduoduo_ai.message_types import IncomingMessage, MsgType, parse_push


def _text_msg(content="在吗", uid="buyer-1", msg_id="m1"):
    return {
        "response": "push",
        "message": {
            "msg_id": msg_id,
            "type": MsgType.TEXT,
            "content": content,
            "from": {"role": "user", "uid": uid},
            "to": {"role": "mall_cs"},
            "nickname": "买家A",
            "time": 1700000000,
        },
    }


def test_parse_text_message():
    msg = parse_push(_text_msg())
    assert isinstance(msg, IncomingMessage)
    assert msg.content == "在吗"
    assert msg.uid == "buyer-1"
    assert msg.type == MsgType.TEXT
    assert msg.nickname == "买家A"
    assert msg.timestamp == 1700000000


def test_parse_image_message():
    raw = {
        "response": "push",
        "message": {
            "msg_id": "m2",
            "type": MsgType.IMAGE,
            "content": "https://img.example.com/x.png",
            "from": {"role": "user", "uid": "buyer-2"},
            "to": {"role": "mall_cs"},
        },
    }
    msg = parse_push(raw)
    assert msg is not None
    assert msg.type == MsgType.IMAGE
    assert msg.content.startswith("http")


def test_withdraw_returns_none():
    raw = {
        "response": "push",
        "message": {
            "msg_id": "m3",
            "type": MsgType.WITHDRAW,
            "info": {"withdraw_hint": "撤回了一条消息"},
        },
    }
    assert parse_push(raw) is None


def test_goods_spec_returns_none():
    raw = {
        "response": "push",
        "message": {"msg_id": "m4", "type": MsgType.GOODS_SPEC, "info": {"data": {}}},
    }
    assert parse_push(raw) is None


def test_non_push_returns_none():
    assert parse_push({"response": "auth", "auth": {"result": "ok"}}) is None
    assert parse_push({"response": "mall_system_msg", "message": {}}) is None


def test_missing_message_field_returns_none():
    assert parse_push({"response": "push"}) is None


def test_text_missing_content_empty():
    raw = _text_msg(content=None)
    msg = parse_push(raw)
    assert msg is not None
    assert msg.content == ""
