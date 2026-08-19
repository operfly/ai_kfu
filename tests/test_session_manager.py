# tests/test_session_manager.py
import time
from pinduoduo_ai.session_manager import SessionManager, ConversationState

def test_initial_state_idle():
    sm = SessionManager()
    assert sm.get_state("买家A") == ConversationState.IDLE

def test_state_transitions():
    sm = SessionManager()
    sm.mark_processing("买家A")
    assert sm.get_state("买家A") == ConversationState.PROCESSING
    sm.mark_replied("买家A")
    assert sm.get_state("买家A") == ConversationState.REPLIED
    sm.mark_handoff("买家A")
    assert sm.get_state("买家A") == ConversationState.HANDOFF

def test_cooldown_blocks_reply():
    sm = SessionManager()
    sm.mark_replied("买家A")
    assert sm.is_processed_recently("买家A", cooldown_seconds=60) is True
    assert sm.is_processed_recently("买家B", cooldown_seconds=60) is False

def test_global_rate_limit():
    sm = SessionManager()
    sm.record_send()
    assert sm.can_send(global_interval_seconds=10) is False
    sm.last_send_ts = time.time() - 20
    assert sm.can_send(global_interval_seconds=10) is True

def test_daily_limit():
    sm = SessionManager()
    for _ in range(5):
        sm.increment_daily_count()
    assert sm.daily_count() == 5
    assert sm.should_skip("买家A", cooldown_seconds=60, daily_limit=5) is True
    assert sm.should_skip("买家B", cooldown_seconds=60, daily_limit=10) is False
