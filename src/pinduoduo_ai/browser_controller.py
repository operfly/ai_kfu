# src/pinduoduo_ai/browser_controller.py
from playwright.sync_api import sync_playwright
from .selectors import SELECTORS


class BrowserController:
    def __init__(self, cdp_port: int, url: str = ""):
        self.cdp_port = cdp_port
        self.url = url
        self._pw = None
        self._browser = None

    def connect(self) -> None:
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(
                f"http://localhost:{self.cdp_port}"
            )
        except Exception as e:
            self._pw = None
            self._browser = None
            raise RuntimeError(
                f"无法连接本地 Chrome (端口 {self.cdp_port})。"
                f"请确认已用 --remote-debugging-port={self.cdp_port} 启动 Chrome。"
            ) from e

    def close(self) -> None:
        if self._pw:
            self._pw.stop()
            self._pw = None
            self._browser = None

    def ensure_service_page(self):
        if not self._browser:
            raise RuntimeError("尚未连接浏览器，先调用 connect()")
        context = self._browser.contexts[0]
        for page in context.pages:
            if "mms.pinduoduo.com" in page.url:
                page.bring_to_front()
                return page
        page = context.new_page()
        page.goto(self.url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        return page

    def fill_and_send(self, page, text: str) -> bool:
        """在输入框输入 text 并点击发送。返回是否成功。"""
        if not page:
            raise AttributeError("page 为空，尚未获取客服页面")
        try:
            box = SELECTORS["input_box"]
            page.locator(box).click()
            page.keyboard.type(text, delay=40)
            page.wait_for_timeout(800)
            page.locator(SELECTORS["send_button"]).click()
            page.wait_for_timeout(500)
            return True
        except Exception:
            return False

    def get_conversations(self, page) -> list[dict]:
        """返回 [{name, has_unread}]。name 从会话项文本提取。"""
        items = page.locator(SELECTORS["conversation_item"]).all()
        result = []
        for it in items:
            try:
                name = (it.inner_text() or "").strip().split("\n")[0]
            except Exception:
                continue
            badge = it.locator(SELECTORS["conversation_unread_badge"]).count() > 0 if SELECTORS["conversation_unread_badge"] else False
            result.append({"name": name, "has_unread": badge})
        return result

    def open_conversation(self, page, name: str) -> bool:
        try:
            items = page.locator(SELECTORS["conversation_item"]).all()
            for it in items:
                if name in (it.inner_text() or ""):
                    it.click()
                    page.wait_for_timeout(1500)
                    return True
            return False
        except Exception:
            return False

    def read_last_messages(self, page, n: int = 20) -> list[str]:
        msgs = page.locator(SELECTORS["message_text"]).all()
        texts = []
        for m in msgs[-n:]:
            try:
                texts.append(m.inner_text().strip())
            except Exception:
                continue
        return texts
