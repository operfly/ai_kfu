# src/pinduoduo_ai/cookie_store.py
"""拼多多 mms.pinduoduo.com 登录态 Cookie 的保存、加载与 CDP 导出。"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


class CookieStoreError(RuntimeError):
    pass


class CookieStore:
    """管理 mms.pinduoduo.com 的 Cookie dict 与本地文件。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, cookies: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> dict:
        if not self.path.exists():
            raise CookieStoreError(
                f"Cookie 文件不存在: {self.path}。请先运行 python scripts/export_cookies.py"
            )
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise CookieStoreError(f"Cookie 文件损坏: {self.path} ({e})") from e
        if not isinstance(data, dict):
            raise CookieStoreError(f"Cookie 文件格式错误: {self.path}")
        return data

    @staticmethod
    def export_from_cdp(cdp_port: int = 9222) -> dict:
        """通过 Playwright CDP 连接已登录 Chrome，导出 mms.pinduoduo.com 域名的 Cookie。"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://localhost:{cdp_port}")
                context = browser.contexts[0]
                cookies = context.cookies("https://mms.pinduoduo.com")
        except Exception as e:
            raise CookieStoreError(
                f"无法连接调试 Chrome（端口 {cdp_port}）。"
                f"请确认已用 --remote-debugging-port={cdp_port} --user-data-dir=H:\\ai_kfu\\data\\chrome_profile "
                f"启动 Chrome 并登录拼多多客服后台。({type(e).__name__})"
            ) from e
        if not cookies:
            raise CookieStoreError(
                f"未找到 mms.pinduoduo.com 的 Cookie。"
                f"请确认已用 --remote-debugging-port={cdp_port} 启动 Chrome 并登录拼多多客服后台。"
            )
        return {c["name"]: c["value"] for c in cookies}
