# tests/test_cookie_store.py
import json

import pytest

from pinduoduo_ai.cookie_store import CookieStore, CookieStoreError


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "cookies.json"
    store = CookieStore(path)
    store.save({"PDDAccessToken": "abc", "user_id": "123"})
    assert store.load() == {"PDDAccessToken": "abc", "user_id": "123"}


def test_load_missing_file_raises(tmp_path):
    store = CookieStore(tmp_path / "nope.json")
    with pytest.raises(CookieStoreError):
        store.load()


def test_load_corrupt_json_raises(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text("{broken", encoding="utf-8")
    store = CookieStore(path)
    with pytest.raises(CookieStoreError):
        store.load()


def test_load_non_dict_raises(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    store = CookieStore(path)
    with pytest.raises(CookieStoreError):
        store.load()


def test_export_from_cdp(monkeypatch, tmp_path):
    """mock Playwright CDP 导出，验证 Cookie dict 转换与域名过滤。"""

    class FakeContext:
        def cookies(self, url):
            assert url == "https://mms.pinduoduo.com"
            return [
                {"name": "PDDAccessToken", "value": "tok", "domain": "mms.pinduoduo.com"},
                {"name": "other_cookie", "value": "x", "domain": "mms.pinduoduo.com"},
            ]

    class FakeBrowser:
        contexts = [FakeContext()]

        def connect_over_cdp(self, url):
            assert url == "http://localhost:9222"
            return self

    class FakePlaywright:
        chromium = FakeBrowser()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    import pinduoduo_ai.cookie_store as cs

    monkeypatch.setattr(cs, "sync_playwright", lambda: FakePlaywright())
    cookies = CookieStore.export_from_cdp(cdp_port=9222)
    assert cookies == {"PDDAccessToken": "tok", "other_cookie": "x"}


def test_export_from_cdp_no_cookies_raises(monkeypatch):
    class FakeContext:
        def cookies(self, url):
            return []

    class FakeBrowser:
        contexts = [FakeContext()]

        def connect_over_cdp(self, url):
            assert url == "http://localhost:9222"
            return self

    class FakePlaywright:
        chromium = FakeBrowser()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    import pinduoduo_ai.cookie_store as cs

    monkeypatch.setattr(cs, "sync_playwright", lambda: FakePlaywright())
    with pytest.raises(CookieStoreError):
        CookieStore.export_from_cdp(cdp_port=9222)
