# tests/test_pdd_api.py
import asyncio

import pytest

from pinduoduo_ai.pdd_api import PDDApi, SessionExpiredError
from pinduoduo_ai.cookie_store import CookieStoreError


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def json(self, content_type=None):
        return self._payload


class FakeSession:
    """记录 post 调用并回放预设响应。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, *, json=None, data=None, cookies=None, headers=None, timeout=None):
        self.calls.append((url, json, data, cookies))
        if callable(self.responses[0]):
            payload = self.responses[0](url, json, data, cookies)
        else:
            payload = self.responses[0]
        self.responses.pop(0)
        return FakeResponse(payload)


def _make_api(session):
    return PDDApi(session, {"PDDAccessToken": "tok"}, http_base="https://mms.pinduoduo.com")


def run(coro):
    return asyncio.run(coro)


def test_get_token_top_level():
    api = _make_api(FakeSession([{"token": "tok-1"}]))
    assert run(api.get_token()) == "tok-1"


def test_get_token_nested_result():
    api = _make_api(FakeSession([{"result": {"token": "tok-2"}}]))
    assert run(api.get_token()) == "tok-2"


def test_get_token_no_token_raises():
    api = _make_api(FakeSession([{"success": False}]))
    with pytest.raises(CookieStoreError):
        run(api.get_token())


def test_get_shop_info():
    api = _make_api(FakeSession([{"success": True, "result": {"mallId": "mall-1", "mallName": "测试店"}}]))
    info = run(api.get_shop_info())
    assert info == {"shop_id": "mall-1", "shop_name": "测试店"}


def test_get_user_info():
    api = _make_api(FakeSession([{"success": True, "result": {"id": 123, "username": "客服"}}]))
    info = run(api.get_user_info())
    assert info == {"user_id": 123, "username": "客服"}


def test_send_text_success():
    def handler(url, json, data, cookies):
        assert url.endswith("/plateau/chat/send_message")
        assert json["client"] == "WEB"
        assert json["data"]["cmd"] == "send_message"
        assert json["data"]["message"]["to"]["uid"] == "buyer-1"
        assert json["data"]["message"]["content"] == "你好"
        return {"success": True, "result": {"error_code": 0}}

    api = _make_api(FakeSession([handler]))
    assert run(api.send_text("buyer-1", "你好")) is True


def test_send_text_platform_error_returns_false():
    api = _make_api(FakeSession([{"success": True, "result": {"error_code": 10002}}]))
    assert run(api.send_text("buyer-1", "x")) is False


def test_send_text_failure_returns_false():
    api = _make_api(FakeSession([{"success": False}]))
    assert run(api.send_text("buyer-1", "x")) is False


def test_send_text_no_response_returns_false():
    api = _make_api(FakeSession([None]))
    assert run(api.send_text("buyer-1", "x")) is False


def test_session_expired_raises_on_get_token():
    payload = {"error_code": 43001, "error_msg": "会话已过期"}
    api = _make_api(FakeSession([payload]))
    with pytest.raises(SessionExpiredError):
        run(api.get_token())


def test_session_expired_raises_on_send_text():
    payload = {"error_code": 43001, "error_msg": "会话已过期"}
    api = _make_api(FakeSession([payload]))
    with pytest.raises(SessionExpiredError):
        run(api.send_text("buyer-1", "x"))


def test_requests_include_cookies():
    seen = {}

    def handler(url, json, data, cookies):
        seen["cookies"] = cookies
        return {"token": "tok"}

    api = _make_api(FakeSession([handler]))
    run(api.get_token())
    assert seen["cookies"] == {"PDDAccessToken": "tok"}
