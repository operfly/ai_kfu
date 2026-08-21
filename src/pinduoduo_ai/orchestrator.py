# src/pinduoduo_ai/orchestrator.py
"""事件驱动主循环：WS 接收消息 → 状态机 → AI 回复 → 敏感词检查 → 发送。"""
import asyncio
from pathlib import Path

from .ai_reply_engine import AIReplyEngine
from .config import get_api_key, load_config
from .cookie_store import CDPSession, CookieStoreError
from .knowledge import KnowledgeBase
from .message_types import IncomingMessage
from .pdd_api import PDDApi, SessionExpiredError
from .pdd_ws import PDDWebSocket, ReconnectConfig
from .safety import check_sensitive, default_sensitive_words
from .session_manager import SessionManager


class Orchestrator:
    """组装 WS 接收与 AI 回复消费，串行处理买家消息。"""

    def __init__(
        self,
        config: dict,
        api: PDDApi,
        session_mgr: SessionManager,
        ai: AIReplyEngine,
        sensitive_words: list[str] | None = None,
        knowledge: KnowledgeBase | None = None,
    ):
        self.config = config
        self.api = api
        self.sm = session_mgr
        self.ai = ai
        self.sensitive_words = sensitive_words or default_sensitive_words()
        self.kb = knowledge or self._load_knowledge()

    def _load_knowledge(self) -> KnowledgeBase | None:
        path = self.config.get("shop_context", {}).get("file")
        if not path:
            return None
        try:
            return KnowledgeBase(path)
        except (OSError, FileNotFoundError):
            return None

    async def handle_message(self, msg: IncomingMessage) -> dict:
        """处理一条买家消息，返回动作描述。串行调用（由消费端保证）。"""
        p = self.config["polling"]
        uid = msg.uid
        if self.sm.should_skip(uid, p["conversation_cooldown_seconds"], p["daily_reply_limit"]):
            return {"uid": uid, "action": "skip", "text": ""}
        if not self.sm.can_send(p["global_rate_limit_seconds"]):
            return {"uid": uid, "action": "skip", "text": "rate_limited"}

        self.sm.mark_processing(uid)
        history = [f"买家: {msg.content}"]

        # 知识库检索：无命中则转人工，不调用 AI
        related = self.kb.retrieve(msg.content) if self.kb else []
        if not related:
            self.sm.mark_handoff(uid)
            return {"uid": uid, "action": "handoff", "text": "未找到相关知识，转人工"}

        shop_context = "\n".join(related)
        try:
            result = self.ai.generate_reply(history, shop_context)
        except Exception:
            result = {"action": "handoff", "text": "AI 服务暂时不可用"}

        if result["action"] == "reply":
            hit = check_sensitive(result["text"], self.sensitive_words)
            if hit:
                result = {"action": "handoff", "text": f"回复命中敏感词[{hit}]，已转人工"}
            else:
                ok = await self.api.send_text(uid, result["text"])
                if ok:
                    self.sm.mark_replied(uid)
                    return {"uid": uid, "action": "reply", "text": result["text"]}
                fallback = self.config.get("fallback_text", "亲，感谢您的咨询！客服正在为您处理，请稍等片刻。")
                await self.api.send_text(uid, fallback)
                return {"uid": uid, "action": "reply", "text": fallback, "note": "send_failed_fallback"}

        if result["action"] == "handoff":
            self.sm.mark_handoff(uid)
            return {"uid": uid, "action": "handoff", "text": result["text"]}

        # unclear：不发送，不标记，等后续消息
        return {"uid": uid, "action": "unclear", "text": ""}


async def _consume_loop(queue: asyncio.Queue, orch: Orchestrator, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        msg = await queue.get()
        try:
            action = await orch.handle_message(msg)
            print(f"[{msg.nickname or msg.uid}] {action['action']}: {action.get('text', '')}", flush=True)
        except SessionExpiredError as e:
            print(f"[错误] {e}", flush=True)
            stop_event.set()
        except Exception as e:
            print(f"[错误] 处理消息失败: {type(e).__name__}: {e}", flush=True)


async def _run_app(config: dict, cdp: CDPSession, stop_event: asyncio.Event) -> int:
    await cdp.connect()
    page = await cdp.get_page()
    api = PDDApi(page)
    token = await api.get_token()
    sm = SessionManager()
    ai = AIReplyEngine(
        api_key=get_api_key(),
        base_url=config["ai"]["base_url"],
        model=config["ai"]["model"],
        max_history=config["ai"].get("max_history_messages", 20),
    )
    orch = Orchestrator(config, api, sm, ai)
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    r = config.get("reconnect", {})
    ws = PDDWebSocket(
        token,
        queue,
        api_version=config["pdd"].get("api_version", "202506091557"),
        base_url=config["pdd"].get("base_ws_url", "wss://m-ws.pinduoduo.com/"),
        reconnect=ReconnectConfig(
            max_attempts=r.get("max_attempts", 5),
            initial_delay=r.get("initial_delay", 2.0),
            backoff_factor=r.get("backoff_factor", 2.0),
            max_delay=r.get("max_delay", 60.0),
        ),
        on_expired=stop_event.set,
    )

    ws_task = asyncio.create_task(ws.run())
    consumer_task = asyncio.create_task(_consume_loop(queue, orch, stop_event))
    stop_task = asyncio.create_task(stop_event.wait())
    print("拼多多 AI 客服已启动，Ctrl+C 停止。", flush=True)

    try:
        await asyncio.wait(
            [ws_task, consumer_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for task in (ws_task, consumer_task, stop_task):
            task.cancel()
        await asyncio.gather(ws_task, consumer_task, stop_task, return_exceptions=True)
        await cdp.close()
    return 0


def run(config_path: str | None = None) -> int:
    """顶层入口：加载配置 → 连接调试 Chrome → 启动 WS 主循环。Ctrl+C 停止。"""
    config = load_config(config_path)
    cdp = CDPSession(config.get("pdd", {}).get("cdp_port", 9222))
    stop_event = asyncio.Event()
    try:
        return asyncio.run(_run_app(config, cdp, stop_event))
    except CookieStoreError as e:
        print(f"[错误] {e}")
        return 1
    except KeyboardInterrupt:
        print("\n收到停止信号，正在退出...")
        stop_event.set()
        return 0
