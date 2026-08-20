# tests/test_cookie_store.py
import pytest

from pinduoduo_ai.cookie_store import CDPSession, CookieStoreError


class FakePage:
    def __init__(self, url="https://mms.pinduoduo.com/home/"):
        self._url = url

    @property
    def url(self):
        return self._url

    async def goto(self, *a, **k):
        self._url = "https://mms.pinduoduo.com/home/"
        return None


class FakeContext:
    def __init__(self, pages=None):
        self.pages = pages if pages is not None else [FakePage()]

    async def new_page(self):
        p = FakePage(url="about:blank")
        self.pages.append(p)
        return p


class FakeBrowser:
    def __init__(self, context):
        self.contexts = [context]


class FakeChromium:
    def __init__(self, browser):
        self._browser = browser

    async def connect_over_cdp(self, url):
        return self._browser


class FakePlaywright:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)

    async def stop(self):
        return None


def _fake_async_playwright(browser, playwright=None):
    """模拟 playwright.async_api.async_playwright()：同步函数返回带 .start() 的对象。

    默认构造 FakePlaywright(browser)；也可传 playwright 自定义对象（如带定制 chromium）。
    """

    class FakeContextManager:
        def __init__(self, browser, pw):
            self._browser = browser
            self._pw = pw

        async def start(self):
            return self._pw if self._pw is not None else FakePlaywright(self._browser)

    return lambda: FakeContextManager(browser, playwright)


@pytest.mark.asyncio
async def test_connect_uses_cdp_port(monkeypatch):
    captured = {}

    class FakeChromiumSub(FakeChromium):
        async def connect_over_cdp(self, url):
            captured["url"] = url
            return self._browser

    fake_browser = FakeBrowser(FakeContext())
    fake_pw = FakePlaywright(fake_browser)
    fake_pw.chromium = FakeChromiumSub(fake_browser)

    import pinduoduo_ai.cookie_store as cs

    monkeypatch.setattr(cs, "async_playwright", _fake_async_playwright(fake_browser, fake_pw))
    cdp = CDPSession(cdp_port=9222)
    await cdp.connect()
    assert captured["url"] == "http://localhost:9222"
    await cdp.close()


@pytest.mark.asyncio
async def test_connect_failure_raises(monkeypatch):
    def fake_start():
        raise ConnectionRefusedError("down")

    import pinduoduo_ai.cookie_store as cs

    monkeypatch.setattr(cs, "async_playwright", fake_start)
    cdp = CDPSession(cdp_port=9222)
    with pytest.raises(CookieStoreError):
        await cdp.connect()
    await cdp.close()


@pytest.mark.asyncio
async def test_get_page_reuses_mms_page(monkeypatch):
    existing = FakePage(url="https://mms.pinduoduo.com/chat-service/")
    context = FakeContext(pages=[existing])
    browser = FakeBrowser(context)

    import pinduoduo_ai.cookie_store as cs

    monkeypatch.setattr(cs, "async_playwright", _fake_async_playwright(browser))
    cdp = CDPSession()
    await cdp.connect()
    page = await cdp.get_page()
    assert page is existing  # 复用已打开的 mms 页
    await cdp.close()


@pytest.mark.asyncio
async def test_get_page_creates_when_missing(monkeypatch):
    context = FakeContext(pages=[])
    browser = FakeBrowser(context)

    import pinduoduo_ai.cookie_store as cs

    monkeypatch.setattr(cs, "async_playwright", _fake_async_playwright(browser))
    cdp = CDPSession()
    await cdp.connect()
    page = await cdp.get_page()
    assert page.url == "https://mms.pinduoduo.com/home/"
    await cdp.close()


@pytest.mark.asyncio
async def test_get_page_before_connect_raises(monkeypatch):
    cdp = CDPSession()
    with pytest.raises(CookieStoreError):
        await cdp.get_page()
