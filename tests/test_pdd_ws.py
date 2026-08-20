# tests/test_pdd_ws.py
import asyncio
import json

import pytest
import websockets

from pinduoduo_ai.message_types import MsgType
from pinduoduo_ai.pdd_ws import PDDWebSocket, ReconnectConfig


def _text_raw(content="在吗", uid="buyer-1", msg_id="m1"):
    return {
        "response": "push",
        "message": {
            "msg_id": msg_id,
            "type": MsgType.TEXT,
            "content": content,
            "from": {"role": "user", "uid": uid},
            "to": {"role": "mall_cs"},
            "nickname": "买家A",
            "time": 1700000000,
        },
    }


async def _serve_one(frames, capture_conn=None):
    """启动一个只回放给定帧后关闭的 WS server，返回端口。"""
    async def handler(ws):
        if capture_conn is not None:
            capture_conn["path"] = ws.request.path
        for frame in frames:
            await ws.send(json.dumps(frame))
        await asyncio.sleep(0.2)
        await ws.close()

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port


async def _collect(queue, timeout=1.0):
    out = []
    while True:
        try:
            out.append(await asyncio.wait_for(queue.get(), timeout))
        except asyncio.TimeoutError:
            return out


@pytest.mark.asyncio
async def test_connects_and_dispatches_text():
    server, port = await _serve_one([_text_raw()])
    queue = asyncio.Queue()
    ws = PDDWebSocket("tok", queue, base_url=f"ws://127.0.0.1:{port}", reconnect=ReconnectConfig(max_attempts=1))
    task = asyncio.create_task(ws.run())
    await asyncio.sleep(0.5)
    msgs = await _collect(queue)
    ws.stop()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    server.close()
    await server.wait_closed()
    assert len(msgs) == 1
    assert msgs[0].content == "在吗"
    assert msgs[0].uid == "buyer-1"


@pytest.mark.asyncio
async def test_duplicate_msg_id_dropped():
    frames = [_text_raw(msg_id="dup-1"), _text_raw(msg_id="dup-1")]
    server, port = await _serve_one(frames)
    queue = asyncio.Queue()
    ws = PDDWebSocket("tok", queue, base_url=f"ws://127.0.0.1:{port}", reconnect=ReconnectConfig(max_attempts=1))
    task = asyncio.create_task(ws.run())
    await asyncio.sleep(0.5)
    msgs = await _collect(queue)
    ws.stop()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    server.close()
    await server.wait_closed()
    assert len(msgs) == 1


@pytest.mark.asyncio
async def test_auth_and_system_messages_ignored():
    frames = [
        {"response": "auth", "auth": {"result": "ok"}, "status": 0},
        {"response": "mall_system_msg", "message": {"data": {"user_id": 1}}},
        _text_raw(content="你好呀", uid="b2", msg_id="m2"),
    ]
    server, port = await _serve_one(frames)
    queue = asyncio.Queue()
    ws = PDDWebSocket("tok", queue, base_url=f"ws://127.0.0.1:{port}", reconnect=ReconnectConfig(max_attempts=1))
    task = asyncio.create_task(ws.run())
    await asyncio.sleep(0.5)
    msgs = await _collect(queue)
    ws.stop()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    server.close()
    await server.wait_closed()
    assert len(msgs) == 1
    assert msgs[0].content == "你好呀"


@pytest.mark.asyncio
async def test_ws_url_has_access_token_and_params():
    captured = {}

    async def handler(ws):
        captured["path"] = ws.request.path
        await asyncio.sleep(0.1)
        await ws.close()

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    queue = asyncio.Queue()
    ws = PDDWebSocket(
        "secret-token",
        queue,
        base_url=f"ws://127.0.0.1:{port}",
        api_version="202506091557",
        reconnect=ReconnectConfig(max_attempts=1),
    )
    task = asyncio.create_task(ws.run())
    await asyncio.sleep(0.4)
    ws.stop()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    server.close()
    await server.wait_closed()
    path = captured.get("path", "")
    assert "access_token=secret-token" in path
    assert "role=mall_cs" in path
    assert "client=web" in path
    assert "version=202506091557" in path


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts(monkeypatch):
    """连接连续失败时按退避重试，最终放弃（不抛异常）。"""

    attempts = {"n": 0}

    class FakeConn:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            attempts["n"] += 1
            raise ConnectionRefusedError("refused")

        async def __aexit__(self, *a):
            return None

    def fake_connect(*a, **k):
        return FakeConn()

    monkeypatch.setattr("pinduoduo_ai.pdd_ws.websockets.connect", fake_connect)

    queue = asyncio.Queue()
    ws = PDDWebSocket(
        "tok",
        queue,
        base_url="ws://127.0.0.1:1",
        reconnect=ReconnectConfig(max_attempts=3, initial_delay=0.01, backoff_factor=1.0, max_delay=0.02),
    )
    await asyncio.wait_for(ws.run(), timeout=5)
    assert attempts["n"] == 3  # 恰好尝试 3 次后放弃
