# src/pinduoduo_ai/pdd_api.py
"""拼多多商家后台 HTTP API 封装（基于登录态 Cookie）。"""
import time
from typing import Any

import aiohttp

from .cookie_store import CookieStoreError


class SessionExpiredError(CookieStoreError):
    """登录态失效（error_code=43001），需要重新导出 Cookie。"""


class PDDApi:
    """封装 mms.pinduoduo.com 的鉴权与消息接口。

    所有请求带 Cookie；43001（会话过期）抛 SessionExpiredError。
    """

    def __init__(self, session: aiohttp.ClientSession, cookies: dict, http_base: str = "https://mms.pinduoduo.com"):
        self._session = session
        self.cookies = cookies
        self.http_base = http_base.rstrip("/")

    async def _post(self, url: str, *, json_data: Any = None, data: Any = None, headers: dict | None = None) -> dict | None:
        merged_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if headers:
            merged_headers.update(headers)
        async with self._session.post(
            f"{self.http_base}{url}",
            json=json_data,
            data=data,
            cookies=self.cookies,
            headers=merged_headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            try:
                return await resp.json(content_type=None)
            except Exception:
                return None

    @staticmethod
    def _check_session_expired(result: dict | None) -> None:
        if result and result.get("error_code") == 43001 and "会话已过期" in str(result.get("error_msg", "")):
            raise SessionExpiredError("登录已过期，请重新打开 Chrome 登录后运行 scripts/export_cookies.py")

    async def get_token(self) -> str:
        result = await self._post("/chats/getToken", json_data={"version": "3"})
        self._check_session_expired(result)
        if not result:
            raise CookieStoreError("获取 token 失败：无响应")
        token = result.get("token") or (result.get("result") or {}).get("token")
        if not token:
            raise CookieStoreError("获取 token 失败：响应中无 token 字段")
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
