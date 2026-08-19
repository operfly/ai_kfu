# src/pinduoduo_ai/orchestrator.py
import time
from .browser_controller import BrowserController
from .session_manager import SessionManager, ConversationState
from .ai_reply_engine import AIReplyEngine
from .safety import check_sensitive, default_sensitive_words
from .config import load_config, get_api_key


class Orchestrator:
    def __init__(self, config, browser, session_mgr, ai, sensitive_words=None):
        self.config = config
        self.browser = browser
        self.sm = session_mgr
        self.ai = ai
        self.sensitive_words = sensitive_words or default_sensitive_words()
        self.shop_context = config.get("shop_context", "")

    def run_once(self):
        """执行一轮扫描，返回动作列表。"""
        page = self.browser.ensure_service_page()
        convos = self.browser.get_conversations(page)
        actions = []
        p = self.config["polling"]
        for convo in convos:
            name = convo["name"]
            if not convo["has_unread"]:
                continue
            if self.sm.should_skip(
                name,
                p["conversation_cooldown_seconds"],
                p["daily_reply_limit"],
            ):
                continue
            if not self.sm.can_send(p["global_rate_limit_seconds"]):
                continue
            self.sm.mark_processing(name)
            self.browser.open_conversation(page, name)
            history = self.browser.read_last_messages(
                page, self.config["ai"].get("max_history_messages", 20)
            )
            result = self.ai.generate_reply(history, self.shop_context)

            # 安全检查：AI 的回复若含敏感词则转人工
            if result["action"] == "reply":
                hit = check_sensitive(result["text"], self.sensitive_words)
                if hit:
                    result = {"action": "handoff", "text": f"回复命中敏感词[{hit}]，已转人工"}
                else:
                    ok = self.browser.fill_and_send(page, result["text"])
                    if ok:
                        self.sm.mark_replied(name)
                        actions.append({"session": name, "action": "reply", "text": result["text"]})
                        continue
                    else:
                        result = {"action": "handoff", "text": "发送失败，请人工检查"}

            if result["action"] == "handoff":
                self.sm.mark_handoff(name)
                # 转人工：不在会话中自动发消息，仅标记状态，留给人工处理
                actions.append({"session": name, "action": "handoff", "text": result["text"]})
                continue

            # unclear：不发送，也不标记，留给后续轮询再看
            actions.append({"session": name, "action": "unclear", "text": ""})
        return actions

    def shutdown(self):
        self.browser.close()


def run(config_path: str | None = None):
    """顶层入口：加载配置 → 连接浏览器 → 主循环。Ctrl+C 停止。"""
    config = load_config(config_path)
    browser = BrowserController(
        config["browser"]["cdp_port"], config["browser"]["url"]
    )
    browser.connect()
    sm = SessionManager()
    ai = AIReplyEngine(
        api_key=get_api_key(),
        base_url=config["ai"]["base_url"],
        model=config["ai"]["model"],
        max_history=config["ai"].get("max_history_messages", 20),
    )
    orch = Orchestrator(config, browser, sm, ai)
    print("拼多多 AI 客服已启动，Ctrl+C 停止。")
    try:
        while True:
            actions = orch.run_once()
            for a in actions:
                print(f"[{a['session']}] {a['action']}: {a.get('text','')}")
            time.sleep(config["polling"]["interval_seconds"])
    except KeyboardInterrupt:
        print("\n收到停止信号，正在退出...")
    finally:
        orch.shutdown()
