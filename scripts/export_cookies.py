# scripts/export_cookies.py
"""验证调试 Chrome 的拼多多登录会话是否有效。

程序运行时通过 CDP 直接复用已登录浏览器会话（HTTP 走同源 fetch），无需导出
cookie 文件。本脚本仅用于检查登录态是否有效。

用法：
  1. 用 --remote-debugging-port=9222 --user-data-dir=H:\\ai_kfu\\data\\chrome_profile 启动 Chrome
  2. 登录 https://mms.pinduoduo.com/ 客服后台
  3. 运行 python scripts/export_cookies.py
"""
import asyncio
import sys

from pinduoduo_ai.cookie_store import CDPSession, CookieStoreError
from pinduoduo_ai.pdd_api import PDDApi, SessionExpiredError


async def main() -> int:
    cdp = CDPSession(cdp_port=9222)
    try:
        await cdp.connect()
        page = await cdp.get_page()
        api = PDDApi(page)
        token = await api.get_token()
        shop = await api.get_shop_info()
        print(f"登录态有效: token 获取成功")
        print(f"店铺: {shop.get('shop_name')} (mallId={shop.get('shop_id')})")
        print(f"WebSocket 地址: wss://m-ws.pinduoduo.com/")
        return 0
    except CookieStoreError as e:
        print(f"[错误] {e}")
        return 1
    except SessionExpiredError as e:
        print(f"[错误] {e}")
        return 1
    finally:
        await cdp.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
