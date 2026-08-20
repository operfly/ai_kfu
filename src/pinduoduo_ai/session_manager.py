# src/pinduoduo_ai/session_manager.py
import time
from enum import Enum


class ConversationState(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    REPLIED = "replied"
    HANDOFF = "handoff"


class SessionManager:
    """会话状态机。所有方法的 key 参数为买家 uid（WS 方案下天然以 uid 标识会话）。"""

    def __init__(self):
        self._states: dict[str, ConversationState] = {}
        self._last_reply: dict[str, float] = {}
        self.last_send_ts: float = 0.0
        self._daily_count = 0

    def mark_processing(self, name: str) -> None:
        self._states[name] = ConversationState.PROCESSING

    def mark_replied(self, name: str) -> None:
        self._states[name] = ConversationState.REPLIED
        self._last_reply[name] = time.time()
        self.record_send()

    def mark_handoff(self, name: str) -> None:
        self._states[name] = ConversationState.HANDOFF

    def get_state(self, name: str) -> ConversationState:
        return self._states.get(name, ConversationState.IDLE)

    def is_processed_recently(self, name: str, cooldown_seconds: int) -> bool:
        last = self._last_reply.get(name)
        if last is None:
            return False
        return (time.time() - last) < cooldown_seconds

    def record_send(self) -> None:
        self.last_send_ts = time.time()
        self._daily_count += 1

    def increment_daily_count(self) -> None:
        self._daily_count += 1

    def daily_count(self) -> int:
        return self._daily_count

    def can_send(self, global_interval_seconds: int) -> bool:
        return (time.time() - self.last_send_ts) >= global_interval_seconds

    def should_skip(self, name: str, cooldown_seconds: int, daily_limit: int) -> bool:
        if self._daily_count >= daily_limit:
            return True
        if self.get_state(name) in (ConversationState.HANDOFF,):
            return True
        if self.is_processed_recently(name, cooldown_seconds):
            return True
        return False
