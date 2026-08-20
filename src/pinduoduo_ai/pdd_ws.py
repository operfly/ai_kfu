# src/pinduoduo_ai/pdd_ws.py
"""拼多多 WebSocket 客户端：连接、自动重连、消息去重与分发。"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Callable

import websockets

from .message_types import IncomingMessage, parse_push
from .pdd_api import SessionExpiredError


@dataclass
class ReconnectConfig:
    max_attempts: int = 5
    initial_delay: float = 2.0
    backoff_factor: float = 2.0
    max_delay: float = 60.0


class PDDWebSocket:
    """连接 m-ws.pinduoduo.com，收到买家消息时解析并放入 queue。

    断线按指数退避重连；会话过期（SessionExpiredError）不重连，由 on_expired 通知。
    """

    def __init__(
        self,
        access_token: str,
        queue: asyncio.Queue,
        *,
        api_version: str = "202506091557",
        base_url: str = "wss://m-ws.pinduoduo.com/",
        reconnect: ReconnectConfig | None = None,
        dedup_window: float = 300.0,
        on_expired: Callable[[], None] | None = None,
    ):
        self.access_token = access_token
        self.queue = queue
        self.api_version = api_version
        self.base_url = base_url
        self.reconnect = reconnect or ReconnectConfig()
        self.on_expired = on_expired
        self._seen: set[str] = set()
        self._dedup_window = dedup_window
        self._last_cleanup = time.time()
        self._stop = False

    def stop(self):
        self._stop = True

    def _ws_url(self) -> str:
        return (
            f"{self.base_url}?access_token={self.access_token}"
            f"&role=mall_cs&client=web&version={self.api_version}"
        )

    def _is_duplicate(self, msg: IncomingMessage) -> bool:
        """msg_id 优先去重；无 msg_id 时用 uid+content 兜底。带时间窗清理。"""
        now = time.time()
        if now - self._last_cleanup > self._dedup_window:
            self._seen.clear()
            self._last_cleanup = now
        key = msg.msg_id if msg.msg_id else f"u:{msg.uid}:{msg.content}"
        if key in self._seen:
            return True
        if len(self._seen) > 10000:
            self._seen.clear()
        self._seen.add(key)
        return False

    async def run(self) -> None:
        """连接并循环接收消息，直到 stop 或会话过期。断线自动重连。"""
        attempt = 0
        while not self._stop:
            try:
                async with websockets.connect(
                    self._ws_url(),
                    ping_interval=60,
                    ping_timeout=30,
                    max_size=10**7,
                    compression=None,
                    close_timeout=10,
                ) as ws:
                    attempt = 0  # 连接成功后重置退避
                    print("[WS] 已连接拼多多客服通道", flush=True)
                    async for raw in ws:
                        if self._stop:
                            break
                        await self._handle_raw(raw)
            except SessionExpiredError:
                print("[WS] 会话已过期，停止重连。请重新登录后运行 scripts/export_cookies.py", flush=True)
                if self.on_expired:
                    self.on_expired()
                return
            except Exception as e:
                if self._stop:
                    return
                attempt += 1
                if attempt >= self.reconnect.max_attempts:
                    print(f"[WS] 连接失败达到 {self.reconnect.max_attempts} 次，停止重连: {type(e).__name__}", flush=True)
                    return
                delay = min(
                    self.reconnect.initial_delay * (self.reconnect.backoff_factor ** (attempt - 1)),
                    self.reconnect.max_delay,
                )
                print(f"[WS] 连接断开({type(e).__name__})，{delay:.1f}s 后重试 ({attempt}/{self.reconnect.max_attempts})", flush=True)
                await asyncio.sleep(delay)

    async def _handle_raw(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        msg = parse_push(data)
        if msg is None:
            return
        if self._is_duplicate(msg):
            return
        await self.queue.put(msg)
