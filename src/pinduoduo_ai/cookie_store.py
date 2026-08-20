# src/pinduoduo_ai/cookie_store.py
"""拼多多 CDP 会话管理：连接调试 Chrome 并提供一个已打开 mms 域的页面。

HTTP 接口通过浏览器同源 fetch 调用（鉴权绑定浏览器会话），因此这里不再导出
cookie 文件，而是直接管理 CDP 连接与页面。
"""
from playwright.async_api import async_playwright

PDD_HOME = "https://mms.pinduoduo.com/home/"


class CookieStoreError(RuntimeError):
    pass


class CDPSession:
    """管理调试 Chrome 的 CDP 连接，提供 mms 域页面供 fetch 与 WS token 获取。"""

    def __init__(self, cdp_port: int = 9222):
        self.cdp_port = cdp_port
        self._pw = None
        self._browser = None

    async def connect(self) -> None:
        try:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.connect_over_cdp(
                f"http://localhost:{self.cdp_port}"
            )
        except Exception as e:
            await self.close()
            raise CookieStoreError(
                f"无法连接调试 Chrome（端口 {self.cdp_port}）。"
                f"请确认已用 --remote-debugging-port={self.cdp_port} "
                f"--user-data-dir=H:\\ai_kfu\\data\\chrome_profile 启动 Chrome 并登录拼多多客服后台。"
                f"({type(e).__name__})"
            ) from e

    async def get_page(self):
        """返回一个已打开 mms.pinduoduo.com 域的页面；无则新建并导航过去。"""
        if not self._browser:
            raise CookieStoreError("尚未连接调试 Chrome，先调用 connect()")
        context = self._browser.contexts[0]
        for page in context.pages:
            if "mms.pinduoduo.com" in page.url:
                return page
        page = await context.new_page()
        await page.goto(PDD_HOME, wait_until="domcontentloaded")
        return page

    async def close(self) -> None:
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
            self._browser = None
