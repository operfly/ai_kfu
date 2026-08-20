# tests/test_pdd_api.py
import pytest

from pinduoduo_ai.pdd_api import PDDApi, SessionExpiredError


class FakePage:
    """模拟 Playwright async Page.evaluate，回放预设响应。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def evaluate(self, script, arg=None):
        self.calls.append((script, arg))
        if callable(self.responses[0]):
            payload = self.responses[0](arg)
        else:
            payload = self.responses[0]
        self.responses.pop(0)
        return payload


def run(coro):
    import asyncio

    return asyncio.run(coro)


def _make_api(page):
    return PDDApi(page)


def test_get_token_top_level():
    api = _make_api(FakePage([{"token": "tok-1"}]))
    assert run(api.get_token()) == "tok-1"


def test_get_token_nested_result():
    api = _make_api(FakePage([{"result": {"token": "tok-2"}}]))
    assert run(api.get_token()) == "tok-2"


def test_get_token_no_token_raises():
    api = _make_api(FakePage([{"success": False}]))
    with pytest.raises(RuntimeError):
        run(api.get_token())


def test_get_shop_info():
    api = _make_api(FakePage([{"success": True, "result": {"mallId": "mall-1", "mallName": "测试店"}}]))
    info = run(api.get_shop_info())
    assert info == {"shop_id": "mall-1", "shop_name": "测试店"}


def test_get_user_info():
    api = _make_api(FakePage([{"success": True, "result": {"id": 123, "username": "客服"}}]))
    info = run(api.get_user_info())
    assert info == {"user_id": 123, "username": "客服"}


def test_send_text_success():
    def handler(arg):
        payload = arg["json_data"]
        assert payload["client"] == "WEB"
        assert payload["data"]["cmd"] == "send_message"
        assert payload["data"]["message"]["to"]["uid"] == "buyer-1"
        assert payload["data"]["message"]["content"] == "你好"
        return {"success": True, "result": {"error_code": 0}}

    api = _make_api(FakePage([handler]))
    assert run(api.send_text("buyer-1", "你好")) is True


def test_send_text_platform_error_returns_false():
    api = _make_api(FakePage([{"success": True, "result": {"error_code": 10002}}]))
    assert run(api.send_text("buyer-1", "x")) is False


def test_send_text_failure_returns_false():
    api = _make_api(FakePage([{"success": False}]))
    assert run(api.send_text("buyer-1", "x")) is False


def test_send_text_no_response_returns_false():
    api = _make_api(FakePage([None]))
    assert run(api.send_text("buyer-1", "x")) is False


def test_session_expired_raises_on_get_token():
    payload = {"error_code": 43001, "error_msg": "会话已过期"}
    api = _make_api(FakePage([payload]))
    with pytest.raises(SessionExpiredError):
        run(api.get_token())


def test_session_expired_raises_on_send_text():
    payload = {"error_code": 43001, "error_msg": "会话已过期"}
    api = _make_api(FakePage([payload]))
    with pytest.raises(SessionExpiredError):
        run(api.send_text("buyer-1", "x"))


def test_post_uses_relative_url():
    def handler(arg):
        assert arg["url"] == "/chats/getToken"
        return {"token": "tok"}

    api = _make_api(FakePage([handler]))
    run(api.get_token())
