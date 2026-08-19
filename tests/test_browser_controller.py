# tests/test_browser_controller.py
import pytest
from pinduoduo_ai.browser_controller import BrowserController

def test_connect_fails_when_chrome_down():
    ctrl = BrowserController(cdp_port=9223)  # 故意用未监听端口
    with pytest.raises(RuntimeError):
        ctrl.connect()

def test_fill_and_send_returns_false_without_page():
    ctrl = BrowserController(cdp_port=9222)
    with pytest.raises(Exception):
        ctrl.fill_and_send(None, "hello")
