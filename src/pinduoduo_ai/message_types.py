# src/pinduoduo_ai/message_types.py
"""解析拼多多 WebSocket 推送报文为结构化消息。"""
from dataclasses import dataclass, field
from typing import Any


class MsgType:
    TEXT = 0
    IMAGE = 1
    EMOTION = 5
    VIDEO = 14
    GOODS_SPEC = 64
    WITHDRAW = 1002


@dataclass
class IncomingMessage:
    msg_id: str
    uid: str          # 买家 uid（from.uid）
    type: int
    content: str
    nickname: str = ""
    timestamp: float = 0.0
    raw: dict = field(default_factory=dict)


def _safe_get(data: dict, *keys, default=None) -> Any:
    result: Any = data
    for key in keys:
        if not isinstance(result, dict):
            return default
        result = result.get(key)
        if result is None:
            return default
    return result


def parse_push(raw: dict) -> IncomingMessage | None:
    """解析 response=='push' 的报文，返回 IncomingMessage；无法解析返回 None。

    仅提取文本/图片/规格等有 content 可回应的消息，撤回/系统消息返回 None。
    """
    if raw.get("response") != "push":
        return None
    msg = raw.get("message")
    if not isinstance(msg, dict):
        return None

    msg_type = msg.get("type")
    content = msg.get("content")
    if msg_type == MsgType.TEXT:
        content = content if isinstance(content, str) else ""
    elif msg_type == MsgType.IMAGE:
        content = content if isinstance(content, str) else ""
    else:
        # 规格/视频/表情/撤回等：目前不自动回复
        return None

    return IncomingMessage(
        msg_id=str(_safe_get(msg, "msg_id", default="")),
        uid=str(_safe_get(msg, "from", "uid", default="")),
        type=msg_type,
        content=content,
        nickname=str(_safe_get(msg, "nickname", default="")),
        timestamp=float(_safe_get(msg, "time", default=0.0) or 0.0),
        raw=raw,
    )
