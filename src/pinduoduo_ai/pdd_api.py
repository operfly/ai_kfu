# src/pinduoduo_ai/pdd_api.py
"""拼多多商家后台 HTTP API 封装。

鉴权绑定浏览器会话（脱离浏览器用 cookie 直连会 43001），因此所有 HTTP 请求
通过已连接的调试 Chrome 页面执行同源 fetch，天然带浏览器完整鉴权。
"""
import time
from typing import Any


class SessionExpiredError(RuntimeError):
    """登录态失效，需要重新登录浏览器会话。"""


class PDDApi:
    """通过 CDP 连接的浏览器页面执行 mms.pinduoduo.com 的 HTTP 接口。

    page 必须是 Playwright async Page，且已打开 mms.pinduoduo.com 域页面。
    """

    def __init__(self, page):
        self._page = page

    async def _post(self, url: str, *, json_data: Any = None, data: Any = None) -> dict | None:
        script = """(args) => {
            const {url, json_data, data} = args;
            const headers = {'Content-Type': 'application/json'};
            let body;
            if (data !== undefined && data !== null) body = data;
            else if (json_data !== undefined && json_data !== null) body = JSON.stringify(json_data);
            return fetch(url, {method: 'POST', headers, body}).then(r => r.json()).catch(() => null);
        }"""
        return await self._page.evaluate(script, {"url": url, "json_data": json_data, "data": data})

    @staticmethod
    def _check_session_expired(result: dict | None) -> None:
        if result and result.get("error_code") == 43001 and "会话已过期" in str(result.get("error_msg", "")):
            raise SessionExpiredError("登录已过期，请在调试 Chrome 中重新登录拼多多客服后台")

    async def get_token(self) -> str:
        result = await self._post("/chats/getToken", json_data={"version": "3"})
        self._check_session_expired(result)
        if not result:
            raise RuntimeError("获取 token 失败：无响应")
        token = result.get("token") or (result.get("result") or {}).get("token")
        if not token:
            raise RuntimeError("获取 token 失败：响应中无 token 字段")
        return token

    async def get_shop_info(self) -> dict:
        result = await self._post("/earth/api/merchant/queryMerchantInfoByMallId", json_data={})
        self._check_session_expired(result)
        data = (result or {}).get("result") or {}
        return {"shop_id": data.get("mallId"), "shop_name": data.get("mallName")}

    async def get_user_info(self) -> dict:
        result = await self._post("/janus/api/new/userinfo", data="")
        self._check_session_expired(result)
        data = (result or {}).get("result") or {}
        return {"user_id": data.get("id"), "username": data.get("username")}

    async def send_text(self, recipient_uid: str, content: str) -> bool:
        """发送文本消息，成功返回 True。"""
        payload = {
            "data": {
                "cmd": "send_message",
                "request_id": int(time.time() * 1000),
                "message": {
                    "to": {"role": "user", "uid": recipient_uid},
                    "from": {"role": "mall_cs"},
                    "content": content,
                    "msg_id": None,
                    "type": 0,
                    "is_aut": 0,
                    "manual_reply": 1,
                },
            },
            "client": "WEB",
        }
        result = await self._post("/plateau/chat/send_message", json_data=payload)
        self._check_session_expired(result)
        if not result:
            return False
        if result.get("success") is True:
            err = (result.get("result") or {}).get("error_code")
            if err == 10002:
                return False
            return True
        return False
