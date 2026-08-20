# scripts/export_cookies.py
"""从已登录的调试 Chrome 导出拼多多 mms.pinduoduo.com Cookie 到 data/.pdd_cookies.json。

用法：
  1. 用 --remote-debugging-port=9222 --user-data-dir=H:\\ai_kfu\\data\\chrome_profile 启动 Chrome
  2. 登录 https://mms.pinduoduo.com/ 客服后台
  3. 运行 python scripts/export_cookies.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pinduoduo_ai.cookie_store import CookieStore, CookieStoreError  # noqa: E402

DEFAULT_COOKIE_FILE = Path(__file__).resolve().parent.parent / "data" / ".pdd_cookies.json"
CDP_PORT = 9222


def main() -> int:
    try:
        cookies = CookieStore.export_from_cdp(cdp_port=CDP_PORT)
    except CookieStoreError as e:
        print(f"[错误] {e}")
        return 1
    CookieStore(DEFAULT_COOKIE_FILE).save(cookies)
    print(f"已导出 {len(cookies)} 个 Cookie 到 {DEFAULT_COOKIE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
