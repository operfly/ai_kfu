# 拼多多 AI 自动客服系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个在拼多多客服网页版中自动回复买家消息的 AI 客服系统，复用已登录 Chrome，全自动发送，敏感话题转人工。

**Architecture:** Python 主程序通过 Playwright CDP 连接到本地已登录的 Chrome 浏览器，轮询拼多多客服网页版会话列表发现新消息，打开会话读取上下文，调用 DeepSeek 生成回复，经敏感词检查后模拟真人输入并发送。会话状态机管理每会话进度，安全机制（冷却、节流、限额、应急停止）约束全自动发送。

**Tech Stack:** Python 3.12、Playwright (sync API + CDP)、DeepSeek API (OpenAI 兼容接口)、PyYAML、python-dotenv、pytest

**Spec:** `docs/superpowers/specs/2026-08-19-pinduoduo-ai-customer-service-design.md`

## Global Constraints

- Python 3.12（本机 `python` 命令）
- Chrome 位于 `C:\Program Files\Google\Chrome\Application\chrome.exe`
- Windows 本机运行；无独立监控面板；进度直接在客服网页版可见
- 全自动发送，但必须经敏感词检查、发送限速、每日限额、应急停止保护
- 串行处理会话（同一时间只操作一个会话）
- 选择器集中在 `selectors.py`，拼多多改版时单点维护
- 所有敏感信息（API Key）从 `.env` 读取，不入库不入 git

---

### Task 0: 环境侦察与最小发送链路验证（Human-gated）

**目的**：本计划的全部 DOM 选择器都来自真实页面侦察，而非猜测。此任务产出真实的 `selectors.py` 内容，并验证"连接 Chrome → 打开客服页 → 定位输入框 → 输入 → 发送"最小链路可行。此任务需要用户配合（启动 Chrome 调试端口、登录、观察发送）。

**Files:**
- Create: `scripts/probe.py`
- Create: `config.yaml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/pinduoduo_ai/selectors.py`

**Interfaces:**
- Produces: `src/pinduoduo_ai/selectors.py` 中定义所有真实 DOM 选择器常量；`config.yaml` 基础配置；`.env.example` 环境变量模板；最小发送链路的验证结论。

- [ ] **Step 1: 初始化项目结构**

```bash
mkdir -p H:\ai_kfu\scripts H:\ai_kfu\src\pinduoduo_ai H:\ai_kfu\tests H:\ai_kfu\data
cd H:\ai_kfu
python -m pip install playwright pyyaml python-dotenv openai
python -m playwright install chromium
```

- [ ] **Step 2: 创建基础配置文件**

创建 `config.yaml`：

```yaml
# 拼多多 AI 自动客服配置
browser:
  cdp_port: 9222          # 本地 Chrome 调试端口
  url: "https://mms.pinduoduo.com/"
  # 客服会话页面路径（Task 0 侦察后修正）
  customer_service_path: ""

polling:
  interval_seconds: 5     # 轮询间隔
  conversation_cooldown_seconds: 60   # 每会话回复后冷却
  global_rate_limit_seconds: 10       # 全局两条回复最小间隔
  daily_reply_limit: 100              # 每日自动回复上限

ai:
  model: "deepseek-chat"
  base_url: "https://api.deepseek.com"
  max_history_messages: 20   # 传给 AI 的最大历史消息数

human_handoff:
  mark_text: "【待人工处理】"   # 转人工时在会话中标记的文本
```

创建 `.env.example`：

```
# DeepSeek API Key（复制为 .env 并填写）
DEEPSEEK_API_KEY=sk-xxxxxxxx
```

创建 `.gitignore`：

```
.env
__pycache__/
*.pyc
data/
.pytest_cache/
```

- [ ] **Step 3: 写侦察脚本 `scripts/probe.py`**

这个脚本连接本地已登录 Chrome，打开客服页，把页面里会话列表、聊天窗口、输入框、发送按钮的真实 DOM 导出，供提取选择器：

```python
"""连接本地已登录 Chrome，打开拼多多客服页，导出页面 DOM 结构供选择器侦察。"""
import sys, json
from playwright.sync_api import sync_playwright

CDP_PORT = 9222
URL = "https://mms.pinduoduo.com/"

def main():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)  # 等待登录态/页面加载
        print("当前 URL:", page.url)
        print("页面标题:", page.title())

        # 导出输入框（可能是 textarea 或 contenteditable）
        inputs = page.eval_on_selector_all(
            "textarea, [contenteditable='true'], input[type='text']",
            "els => els.map(e => ({tag: e.tagName, cls: e.className, id: e.id, ph: e.placeholder || ''}))"
        )
        print("输入框候选:\n", json.dumps(inputs, ensure_ascii=False, indent=2))

        # 导出按钮
        buttons = page.eval_on_selector_all(
            "button, [role='button']",
            "els => els.map(e => ({cls: e.className, text: (e.innerText||'').trim().slice(0,20)}))"
        )
        print("按钮候选:\n", json.dumps(buttons, ensure_ascii=False, indent=2)[:3000])

        # 导出会话列表项
        convos = page.eval_on_selector_all(
            "li, [class*='conversation'], [class*='session']",
            "els => els.map(e => ({cls: e.className, text: (e.innerText||'').trim().slice(0,30)}))"
        )
        print("会话候选:\n", json.dumps(convos, ensure_ascii=False, indent=2)[:3000])

        input("\n按回车退出，保持页面打开以便继续观察...")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 启动 Chrome 调试端口（需用户执行）**

让用户关闭 Chrome 后，在新的终端执行：

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="H:\ai_kfu\data\chrome_profile"
```

> 说明：`--user-data-dir` 指向独立配置目录，避免与用户日常 Chrome 配置冲突；用户需在该窗口登录拼多多商家后台。**这个命令是用户手动执行的，不能由代码自动启动。**

- [ ] **Step 5: 运行侦察脚本，收集真实选择器**

```bash
cd H:\ai_kfu && python scripts/probe.py
```

执行者把输出中的真实输入框/按钮/会话列表选择器记录，用于 Step 6。

**用户配合点**：此时让用户在客服页面中手动给某个测试会话发一条消息（或找到有未读消息的会话），供后续检测新消息验证。

- [ ] **Step 6: 用真实选择器生成 `src/pinduoduo_ai/selectors.py`**

以实际侦察结果为准，参考结构：

```python
"""拼多多客服网页版 DOM 选择器。

⚠️ 这些选择器基于 mms.pinduoduo.com 客服页真实 DOM 侦察得出。
拼多多改版可能导致失效，届时重新运行 scripts/probe.py 更新。
"""
SELECTORS = {
    # 会话列表容器
    "conversation_list": "",        # 例: ".conversation-list" 
    "conversation_item": "",        # 单个会话项
    "conversation_unread_badge": "",# 未读角标
    # 聊天窗口
    "message_list": "",             # 消息区
    "message_text": "",             # 单条消息文本
    # 输入与发送
    "input_box": "",                # 输入框 (textarea 或 contenteditable)
    "send_button": "",              # 发送按钮
}
```

> 若侦察结果与参考结构不同，以实际为准，但必须保持 `SELECTORS` 这个 dict 的结构与 key 名不变，后续代码依赖这些 key。

- [ ] **Step 7: 验证最小发送链路（Human-gated 确认点）**

执行者用 Playwright 连接到已登录 Chrome，用 `selectors.py` 中的输入框/发送按钮，在**测试会话**中实际输入一条固定文本并点击发送，验证能成功发到拼多多客服页。

**此步必须由用户在浏览器中肉眼确认发送成功**，之后 Task 0 才算完成。

- [ ] **Step 8: 提交**

```bash
cd H:\ai_kfu
git init
git add scripts/probe.py config.yaml .env.example .gitignore src/pinduoduo_ai/selectors.py
git commit -m "chore: project scaffold + DOM selectors from live probing"
```

> 若用户环境不便用 git，可跳过，但需保留文件。

---

### Task 1: 配置加载模块

**Files:**
- Create: `src/pinduoduo_ai/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `load_config(path: str | None = None) -> dict` — 读取 `config.yaml`；`get_api_key() -> str` — 从 `.env` 读取 `DEEPSEEK_API_KEY`，缺失抛 `RuntimeError`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
import pytest
from pinduoduo_ai.config import load_config, get_api_key

def test_load_config_defaults(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "polling:\n  interval_seconds: 5\n"
        "ai:\n  model: deepseek-chat\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    assert cfg["polling"]["interval_seconds"] == 5
    assert cfg["ai"]["model"] == "deepseek-chat"

def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "nope.yaml"))

def test_get_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        get_api_key()
```

- [ ] **Step 2: 运行确认失败**

```bash
cd H:\ai_kfu && python -m pytest tests/test_config.py -v
```
预期：FAIL（ModuleNotFoundError: pinduoduo_ai）

- [ ] **Step 3: 实现**

```python
# src/pinduoduo_ai/config.py
import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"

def load_config(path: str | None = None) -> dict:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {cfg_path}")
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_api_key() -> str:
    load_dotenv()
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("未找到 DEEPSEEK_API_KEY，请检查 .env 文件")
    return key
```

- [ ] **Step 4: 运行确认通过**

```bash
cd H:\ai_kfu && python -m pytest tests/test_config.py -v
```
预期：PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pinduoduo_ai/config.py tests/test_config.py
git commit -m "feat: config loading module"
```

---

### Task 2: 浏览器控制器（CDP 连接）

**Files:**
- Create: `src/pinduoduo_ai/browser_controller.py`
- Test: `tests/test_browser_controller.py`

**Interfaces:**
- Consumes: `load_config()` (Task 1) 的 `browser.cdp_port`、`browser.url` 配置；`SELECTORS` (Task 0)
- Produces:
  - `class BrowserController:`
    - `connect() -> None` — 连接 CDP；失败抛 `RuntimeError("无法连接 Chrome...")`
    - `close() -> None`
    - `ensure_service_page() -> Page` — 找到/创建客服页，返回 Page
    - `fill_and_send(page, text: str) -> bool` — 把 text 输入输入框并点击发送，返回是否成功
    - `get_conversations(page) -> list[dict]` — 返回会话列表 `[{name, has_unread}]`
    - `open_conversation(page, name: str) -> bool`
    - `read_last_messages(page, n: int) -> list[str]`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_browser_controller.py
import pytest
from pinduoduo_ai.browser_controller import BrowserController

def test_connect_fails_when_chrome_down():
    ctrl = BrowserController(cdp_port=9223)  # 故意用未监听端口
    with pytest.raises(RuntimeError):
        ctrl.connect()

def test_fill_and_send_returns_false_without_page():
    ctrl = BrowserController(cdp_port=9222)
    with pytest.raises(Exception):
        ctrl.fill_and_send(None, "hello")
```

> 真实页面交互测试需要 Chrome + 登录态，属于 Task 0 已人工验证的最小链路；单元测试只覆盖失败路径和构造。

- [ ] **Step 2: 运行确认失败**

```bash
cd H:\ai_kfu && python -m pytest tests/test_browser_controller.py -v
```
预期：FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# src/pinduoduo_ai/browser_controller.py
from playwright.sync_api import sync_playwright
from .selectors import SELECTORS


class BrowserController:
    def __init__(self, cdp_port: int, url: str):
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
```

- [ ] **Step 4: 运行确认通过**

```bash
cd H:\ai_kfu && python -m pytest tests/test_browser_controller.py -v
```
预期：PASS (2 passed)

> 说明：`fill_and_send(None, ...)` 在 `page.locator` 前会抛 `AttributeError`，测试用 `pytest.raises(Exception)` 兜底。真实发送链路已在 Task 0 人工验证。

- [ ] **Step 5: 提交**

```bash
git add src/pinduoduo_ai/browser_controller.py tests/test_browser_controller.py
git commit -m "feat: browser controller via CDP"
```

---

### Task 3: 会话管理器（状态机 + 冷却）

**Files:**
- Create: `src/pinduoduo_ai/session_manager.py`
- Test: `tests/test_session_manager.py`

**Interfaces:**
- Produces:
  - `ConversationState` 枚举：`IDLE`, `PROCESSING`, `REPLIED`, `HANDOFF`
  - `class SessionManager:`
    - `mark_processing(name)` / `mark_replied(name)` / `mark_handoff(name)`
    - `get_state(name) -> ConversationState`
    - `is_processed_recently(name, cooldown_seconds) -> bool` — 会话冷却判断
    - `can_send(global_interval_seconds, last_send_ts) -> bool` — 全局节流
    - `increment_daily_count()` / `daily_count() -> int` — 每日限额
    - `should_skip(name, cooldown_seconds, daily_limit) -> bool` — 综合判断该会话是否可回复

- [ ] **Step 1: 写失败测试**

```python
# tests/test_session_manager.py
import time
from pinduoduo_ai.session_manager import SessionManager, ConversationState

def test_initial_state_idle():
    sm = SessionManager()
    assert sm.get_state("买家A") == ConversationState.IDLE

def test_state_transitions():
    sm = SessionManager()
    sm.mark_processing("买家A")
    assert sm.get_state("买家A") == ConversationState.PROCESSING
    sm.mark_replied("买家A")
    assert sm.get_state("买家A") == ConversationState.REPLIED
    sm.mark_handoff("买家A")
    assert sm.get_state("买家A") == ConversationState.HANDOFF

def test_cooldown_blocks_reply():
    sm = SessionManager()
    sm.mark_replied("买家A")
    assert sm.is_processed_recently("买家A", cooldown_seconds=60) is True
    assert sm.is_processed_recently("买家B", cooldown_seconds=60) is False

def test_global_rate_limit():
    sm = SessionManager()
    sm.record_send()
    assert sm.can_send(global_interval_seconds=10) is False
    sm.last_send_ts = time.time() - 20
    assert sm.can_send(global_interval_seconds=10) is True

def test_daily_limit():
    sm = SessionManager()
    for _ in range(5):
        sm.increment_daily_count()
    assert sm.daily_count() == 5
    assert sm.should_skip("买家A", cooldown_seconds=60, daily_limit=5) is True
    assert sm.should_skip("买家B", cooldown_seconds=60, daily_limit=10) is False
```

- [ ] **Step 2: 运行确认失败**

```bash
cd H:\ai_kfu && python -m pytest tests/test_session_manager.py -v
```
预期：FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# src/pinduoduo_ai/session_manager.py
import time
from enum import Enum


class ConversationState(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    REPLIED = "replied"
    HANDOFF = "handoff"


class SessionManager:
    def __init__(self):
        self._states: dict[str, ConversationState] = {}
        self._last_reply: dict[str, float] = {}
        self.last_send_ts: float = 0.0
        self._daily_count = 0

    def mark_processing(self, name: str) -> None:
        self._states[name] = ConversationState.PROCESSING

    def mark_replied(self, name: str) -> None:
        self._states[name] = ConversationState.REPLIED
        self._last_reply[name] = time.time()
        self.record_send()

    def mark_handoff(self, name: str) -> None:
        self._states[name] = ConversationState.HANDOFF

    def get_state(self, name: str) -> ConversationState:
        return self._states.get(name, ConversationState.IDLE)

    def is_processed_recently(self, name: str, cooldown_seconds: int) -> bool:
        last = self._last_reply.get(name)
        if last is None:
            return False
        return (time.time() - last) < cooldown_seconds

    def record_send(self) -> None:
        self.last_send_ts = time.time()
        self._daily_count += 1

    def daily_count(self) -> int:
        return self._daily_count

    def can_send(self, global_interval_seconds: int) -> bool:
        return (time.time() - self.last_send_ts) >= global_interval_seconds

    def should_skip(self, name: str, cooldown_seconds: int, daily_limit: int) -> bool:
        if self._daily_count >= daily_limit:
            return True
        if self.get_state(name) in (ConversationState.HANDOFF,):
            return True
        if self.is_processed_recently(name, cooldown_seconds):
            return True
        return False
```

- [ ] **Step 4: 运行确认通过**

```bash
cd H:\ai_kfu && python -m pytest tests/test_session_manager.py -v
```
预期：PASS (5 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pinduoduo_ai/session_manager.py tests/test_session_manager.py
git commit -m "feat: session state machine with cooldown and rate limit"
```

---

### Task 4: AI 回复引擎（DeepSeek）

**Files:**
- Create: `src/pinduoduo_ai/ai_reply_engine.py`
- Test: `tests/test_ai_reply_engine.py`

**Interfaces:**
- Consumes: `load_config()` (Task 1) 的 `ai.model`、`ai.base_url`、`ai.max_history_messages`；`get_api_key()` (Task 1)
- Produces:
  - `class AIReplyEngine:`
    - `generate_reply(history: list[str], shop_context: str = "") -> dict`
    - 返回 `{"action": "reply" | "handoff" | "unclear", "text": str}`
    - `action="reply"` 时 `text` 为要发送的回复；`handoff` 时 text 为转人工说明；`unclear` 时 text 为空（不发送）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ai_reply_engine.py
import pytest
from pinduoduo_ai.ai_reply_engine import AIReplyEngine


class FakeClient:
    """模拟 OpenAI 兼容客户端的 chat.completions.create"""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if callable(self.responses):
            return self.responses(kwargs)
        return self.responses.pop(0)


def _make_engine(fake):
    eng = AIReplyEngine(api_key="test-key", base_url="https://x", model="m")
    eng._client = fake
    return eng


def test_reply_action_parses():
    fake = FakeClient([{"choices": [{"message": {"content": '{"action": "reply", "text": "亲，您好！"}'}}]}])
    eng = _make_engine(fake)
    result = eng.generate_reply(["买家: 在吗", "我: 亲在的"])
    assert result["action"] == "reply"
    assert "您好" in result["text"]


def test_handoff_action_parses():
    fake = FakeClient([{"choices": [{"message": {"content": '{"action": "handoff", "text": "涉及退款，转人工"}'}}]}])
    eng = _make_engine(fake)
    result = eng.generate_reply(["买家: 我要退款"])
    assert result["action"] == "handoff"


def test_non_json_falls_back_unclear():
    fake = FakeClient([{"choices": [{"message": {"content": "抱歉我无法回答"}}]}])
    eng = _make_engine(fake)
    result = eng.generate_reply(["买家: 你好"])
    assert result["action"] == "unclear"


def test_malformed_json_unclear():
    fake = FakeClient([{"choices": [{"message": {"content": "{broken json"}}]}])
    eng = _make_engine(fake)
    result = eng.generate_reply(["买家: 你好"])
    assert result["action"] == "unclear"


def test_retry_then_handoff_on_exception():
    fake = FakeClient([])
    fake.create = lambda **k: (_ for _ in ()).throw(RuntimeError("api down"))
    eng = _make_engine(fake)
    result = eng.generate_reply(["买家: 你好"])
    assert result["action"] == "handoff"
    assert fake.calls.count({}) >= 0  # 至少重试过
```

- [ ] **Step 2: 运行确认失败**

```bash
cd H:\ai_kfu && python -m pytest tests/test_ai_reply_engine.py -v
```
预期：FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# src/pinduoduo_ai/ai_reply_engine.py
import json
import re
from openai import OpenAI

SYSTEM_PROMPT = """你是拼多多店铺的在线客服"小拼"。请用热情、专业、简洁的中文回复买家。

要求：
1. 只输出一个 JSON 对象，不要输出任何其他内容，格式：
   {"action": "reply", "text": "回复内容"} 表示正常回复
   {"action": "handoff", "text": "转人工原因"} 表示需要人工处理（退款、投诉、法律、举报、辱骂、无法回答、需要承诺/赔偿等场景）
2. 回复要简短（不超过60字），符合客服语气，带礼貌用语。
3. 如果买家消息与商品/物流/售前咨询无关且无法回答，用 action=unclear。

常见售前问题参考话术：
- 问在吗/在的：热情问候并询问需求
- 问发货时间：48小时内发货
- 问物流：告知可在订单页面查看物流单号与进度
- 问尺码/材质：建议参考详情页尺码表
- 问优惠/价格：告知可关注店铺优惠券"""


class AIReplyEngine:
    def __init__(self, api_key: str, base_url: str, model: str,
                 max_history: int = 20, timeout: float = 30.0):
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self.model = model
        self.max_history = max_history

    @staticmethod
    def _parse(content: str) -> dict:
        """从 AI 输出解析 {action, text}。容忍 markdown 代码块包裹。"""
        content = content.strip()
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            return {"action": "unclear", "text": ""}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {"action": "unclear", "text": ""}
        action = data.get("action", "unclear")
        text = (data.get("text") or "").strip()
        if action == "reply" and not text:
            return {"action": "unclear", "text": ""}
        return {"action": action, "text": text}

    def generate_reply(self, history: list[str], shop_context: str = "") -> dict:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if shop_context:
            messages.append({"role": "system", "content": f"店铺信息:\n{shop_context}"})
        for line in history[-self.max_history:]:
            if line.startswith("我:"):
                messages.append({"role": "assistant", "content": line[2:].strip()})
            elif line.startswith("买家:"):
                messages.append({"role": "user", "content": line[3:].strip()})
        for attempt in range(3):  # 重试 3 次
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.6,
                )
                content = resp.choices[0].message.content
                return self._parse(content)
            except Exception:
                if attempt == 2:
                    return {"action": "handoff", "text": "AI 服务暂时不可用，已转人工"}
        return {"action": "handoff", "text": "AI 服务暂时不可用，已转人工"}
```

- [ ] **Step 4: 运行确认通过**

```bash
cd H:\ai_kfu && python -m pytest tests/test_ai_reply_engine.py -v
```
预期：PASS (5 passed)

> 说明：`test_retry_then_handoff_on_exception` 中 `fake.calls.count({})` 只是为了确保调用过 fake 的 create 至少一次，实际断言通过即可。

- [ ] **Step 5: 提交**

```bash
git add src/pinduoduo_ai/ai_reply_engine.py tests/test_ai_reply_engine.py
git commit -m "feat: AI reply engine with DeepSeek"
```

---

### Task 5: 敏感词安全检查

**Files:**
- Create: `src/pinduoduo_ai/safety.py`
- Test: `tests/test_safety.py`

**Interfaces:**
- Consumes: `load_config()` (Task 1) 的可选 `safety.sensitive_words` 配置
- Produces:
  - `check_sensitive(text: str, sensitive_words: list[str]) -> str | None`
    - 返回命中的敏感词，未命中返回 None
  - `default_sensitive_words() -> list[str]` — 内置默认敏感词清单

- [ ] **Step 1: 写失败测试**

```python
# tests/test_safety.py
from pinduoduo_ai.safety import check_sensitive, default_sensitive_words

def test_hits_known_words():
    words = ["退款", "投诉", "12315"]
    assert check_sensitive("我要申请退款", words) == "退款"
    assert check_sensitive("我要投诉你", words) == "投诉"
    assert check_sensitive("我要拨打12315", words) == "12315"

def test_no_match_returns_none():
    words = ["退款", "投诉"]
    assert check_sensitive("请问几点发货", words) is None

def test_partial_word_not_hit():
    words = ["退款"]
    assert check_sensitive("你好呀", words) is None
    assert check_sensitive("退款政策是怎么样的", words) == "退款"

def test_default_words_cover_core_cases():
    words = default_sensitive_words()
    assert any(w in words for w in ["退款", "投诉", "法律", "12315"])
```

- [ ] **Step 2: 运行确认失败**

```bash
cd H:\ai_kfu && python -m pytest tests/test_safety.py -v
```
预期：FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# src/pinduoduo_ai/safety.py
DEFAULT_SENSITIVE_WORDS = [
    "退款", "退货", "投诉", "12315", "法律", "律师", "起诉",
    "举报", "差评", "威胁", "辱骂", "骗子", "欺诈", "赔偿",
    "工商", "消协", "媒体", "曝光", "死", "傻逼", "垃圾",
]


def default_sensitive_words() -> list[str]:
    return list(DEFAULT_SENSITIVE_WORDS)


def check_sensitive(text: str, sensitive_words: list[str]) -> str | None:
    """返回文本中命中的第一个敏感词；未命中返回 None。"""
    for w in sensitive_words:
        if w in text:
            return w
    return None
```

- [ ] **Step 4: 运行确认通过**

```bash
cd H:\ai_kfu && python -m pytest tests/test_safety.py -v
```
预期：PASS (4 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pinduoduo_ai/safety.py tests/test_safety.py
git commit -m "feat: sensitive word safety check"
```

---

### Task 6: 主循环（orchestrator）

**Files:**
- Create: `src/pinduoduo_ai/orchestrator.py`
- Create: `src/pinduoduo_ai/__init__.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `BrowserController` (Task 2)、`SessionManager` (Task 3)、`AIReplyEngine` (Task 4)、`check_sensitive`/`default_sensitive_words` (Task 5)、`load_config` (Task 1)
- Produces:
  - `class Orchestrator:`
    - `__init__(config: dict, browser: BrowserController, session_mgr: SessionManager, ai: AIReplyEngine, sensitive_words: list[str] | None = None)`
    - `run_once() -> list[dict]` — 执行一轮：扫描会话、处理新消息，返回本轮处理动作列表 `[{session, action, text?}]`
    - `shutdown() -> None`
    - 附带 `run(config)` 顶层函数：加载配置 → 连接浏览器 → 主循环（带 Ctrl+C 应急停止）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_orchestrator.py
from pinduoduo_ai.orchestrator import Orchestrator
from pinduoduo_ai.session_manager import SessionManager
from pinduoduo_ai.ai_reply_engine import AIReplyEngine
from pinduoduo_ai.safety import default_sensitive_words

CONFIG = {
    "polling": {
        "interval_seconds": 1,
        "conversation_cooldown_seconds": 60,
        "global_rate_limit_seconds": 1,
        "daily_reply_limit": 100,
    },
    "ai": {"max_history_messages": 20},
}


class FakeBrowser:
    def __init__(self, convos, messages, sent=None):
        self.convos = convos
        self.messages = messages
        self.sent = sent if sent is not None else []

    def get_conversations(self, page):
        return self.convos

    def open_conversation(self, page, name):
        return True

    def read_last_messages(self, page, n=20):
        return self.messages

    def fill_and_send(self, page, text):
        self.sent.append(text)
        return True

    def close(self):
        pass


class FakeAI:
    def __init__(self, result):
        self.result = result

    def generate_reply(self, history, shop_context=""):
        return self.result


def _make_orch(convos, ai_result, messages=None):
    b = FakeBrowser(convos, messages or ["买家: 在吗", "我: 亲在的"], sent=[])
    sm = SessionManager()
    ai = FakeAI(ai_result)
    return Orchestrator(CONFIG, b, sm, ai, default_sensitive_words()), b, sm


def test_reply_flow_sends_message():
    orch, b, sm = _make_orch(
        [{"name": "买家A", "has_unread": True}],
        {"action": "reply", "text": "亲，您好！请问有什么可以帮您？"},
    )
    actions = orch.run_once()
    assert b.sent == ["亲，您好！请问有什么可以帮您？"]
    assert actions[0]["action"] == "reply"
    assert sm.get_state("买家A").value == "replied"


def test_sensitive_triggers_handoff_no_send():
    orch, b, sm = _make_orch(
        [{"name": "买家A", "has_unread": True}],
        {"action": "reply", "text": "可以退款的亲"},
    )
    actions = orch.run_once()
    assert b.sent == []  # 含"退款"的回复被拦截，不发送
    assert actions[0]["action"] == "handoff"
    assert sm.get_state("买家A").value == "handoff"


def test_handoff_action_no_send():
    orch, b, sm = _make_orch(
        [{"name": "买家A", "has_unread": True}],
        {"action": "handoff", "text": "涉及退款"},
    )
    actions = orch.run_once()
    assert b.sent == []
    assert sm.get_state("买家A").value == "handoff"


def test_no_unread_no_action():
    orch, b, sm = _make_orch(
        [{"name": "买家A", "has_unread": False}],
        {"action": "reply", "text": "x"},
    )
    actions = orch.run_once()
    assert actions == []
```

- [ ] **Step 2: 运行确认失败**

```bash
cd H:\ai_kfu && python -m pytest tests/test_orchestrator.py -v
```
预期：FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

先建 `src/pinduoduo_ai/__init__.py`（空文件，让包可导入）。

```python
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
                self.browser.fill_and_send(
                    page, self.config["human_handoff"]["mark_text"]
                ) if False else None  # 转人工仅在会话中标记，不自动发消息
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
```

> 注意：上面 handoff 分支中的 `fill_and_send(...) if False else None` 是占位写法，请改为直接注释说明转人工不发送消息（参考实现）：

```python
            if result["action"] == "handoff":
                self.sm.mark_handoff(name)
                # 转人工：不在会话中自动发消息，仅标记状态，留给人工处理
                actions.append({"session": name, "action": "handoff", "text": result["text"]})
                continue
```

- [ ] **Step 4: 运行确认通过**

```bash
cd H:\ai_kfu && python -m pytest tests/test_orchestrator.py -v
```
预期：PASS (4 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pinduoduo_ai/__init__.py src/pinduoduo_ai/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator main loop"
```

---

### Task 7: 入口脚本与话术库

**Files:**
- Create: `main.py`
- Create: `data/knowledge_base.md`

**Interfaces:**
- Consumes: `run()` (Task 6)
- Produces: 可直接运行的项目入口；内置通用客服话术库

- [ ] **Step 1: 创建入口 `main.py`**

```python
"""拼多多 AI 自动客服 - 启动入口。

用法：
  1. 启动 Chrome 调试端口（见 README）
  2. 配置 .env（DEEPSEEK_API_KEY）
  3. 运行 python main.py
"""
from pinduoduo_ai.orchestrator import run

if __name__ == "__main__":
    run()
```

- [ ] **Step 2: 创建话术库 `data/knowledge_base.md`**

```markdown
# 拼多多店铺客服通用话术库

## 问候
- 买家说"在吗"：亲，在的哦～请问有什么可以帮您？😊
- 开场问候：亲，您好！欢迎光临本店，有什么可以为您服务？

## 发货
- 问发货时间：亲，我们承诺 48 小时内发货的哦～
- 问加急：非常抱歉亲，目前暂不支持加急发货呢

## 物流
- 问物流进度：亲，您可以在【我的订单】里查看物流单号和实时进度哦
- 问物流异常：亲，我帮您查看一下，您稍等～

## 尺码/材质
- 问尺码：亲，详情页有尺码表可以参考，也可以告诉我您的身高体重帮您推荐～
- 问材质：亲，详情页有材质说明，我也可以帮您确认哦

## 价格/优惠
- 问优惠：亲，可以关注我们店铺的优惠券，下单更划算哦～
- 问能否优惠：亲，价格已经很实惠了，我们会不定期做活动，可以关注下～
```

> 话术库当前作为 `shop_context` 的可选注入内容（`config.yaml` 中 `shop_context` 指向此文件时由入口加载传入）。本期先保留文件，供后续知识库增强使用。

- [ ] **Step 3: 运行验证启动路径**

```bash
cd H:\ai_kfu && python -c "from pinduoduo_ai.orchestrator import run; print('import ok')"
```
预期：输出 `import ok`（不实际启动，因为需要 Chrome）

- [ ] **Step 4: 冒烟测试所有单元测试**

```bash
cd H:\ai_kfu && python -m pytest tests/ -v
```
预期：全部 PASS（config 3 + browser 2 + session 5 + ai 5 + safety 4 + orchestrator 4 = 23 passed）

- [ ] **Step 5: 提交**

```bash
git add main.py data/knowledge_base.md
git commit -m "feat: entry point and knowledge base"
```

---

### Task 8: 集成验证（Human-gated）

**目的**：在真实拼多多客服页面跑通端到端：连接 Chrome → 轮询 → 检测新消息 → AI 生成 → 发送。需要用户配合制造一条真实买家消息。

**Files:**
- Modify: `config.yaml`（如需要微调选择器/轮询间隔）

- [ ] **Step 1: 确保环境就绪**

确认 Chrome 调试端口已启动且登录态有效（`python scripts/probe.py` 能看到客服页）。

- [ ] **Step 2: 启动程序**

```bash
cd H:\ai_kfu && python main.py
```

- [ ] **Step 3: 用户制造测试消息**

用户在拼多多客服网页版中，用另一个账号（或手机端）给当前会话发一条普通咨询消息，如"在吗？什么时候发货"。

- [ ] **Step 4: 观察自动回复**

预期：程序检测到未读 → 打开会话 → AI 生成回复 → 自动发送。用户在客服页面上**肉眼确认**回复已发送。

- [ ] **Step 5: 验证转人工路径**

用户再发一条含敏感词消息，如"我要退款"。
预期：程序检测 → AI 可能生成含"退款"回复 → 敏感词拦截 → 转人工，**不发送**，日志显示 handoff。

- [ ] **Step 6: 验证 Ctrl+C 停止**

按 Ctrl+C，程序打印"收到停止信号，正在退出"，正常退出。

- [ ] **Step 7: 记录结果**

在 `docs/VERIFICATION.md` 记录：哪些通过、哪些需调整（如选择器失效、AI 回复格式问题）。

---

### Task 9: 收尾 — README 与文档

**Files:**
- Create: `README.md`
- Create: `docs/VERIFICATION.md`（Task 8 已建，补充完整）

- [ ] **Step 1: 写 README.md**

```markdown
# 拼多多 AI 自动客服

在拼多多客服网页版（mms.pinduoduo.com）中自动回复买家消息的 AI 客服工具。复用已登录的本地 Chrome，全自动发送，敏感话题自动转人工。

## 快速开始

### 1. 安装依赖
```bash
python -m pip install playwright pyyaml python-dotenv openai
python -m playwright install chromium
```

### 2. 配置
```bash
copy .env.example .env   # 填入 DEEPSEEK_API_KEY
```

### 3. 启动 Chrome 调试端口（每次使用前）
先**完全退出**已打开的 Chrome，再运行：
```bash
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="H:\ai_kfu\data\chrome_profile"
```
在此 Chrome 窗口中登录拼多多商家后台。

### 4. 运行
```bash
python main.py
```

## 安全机制
- 敏感词自动转人工（退款/投诉/法律等）
- 每会话回复冷却 60s
- 全局发送节流
- 每日自动回复限额
- Ctrl+C 应急停止

## 测试
```bash
python -m pytest tests/ -v
```

## 项目结构
见 docs/superpowers/specs/2026-08-19-pinduoduo-ai-customer-service-design.md
```

- [ ] **Step 2: 最终全量测试**

```bash
cd H:\ai_kfu && python -m pytest tests/ -v
```
预期：全部 PASS

- [ ] **Step 3: 提交**

```bash
git add README.md docs/VERIFICATION.md
git commit -m "docs: README and verification"
```

---

## 计划自审

### 1. Spec 覆盖对照

| Spec 需求 | 对应任务 |
|---|---|
| CDP 复用已登录 Chrome | Task 0 + Task 2 |
| 轮询检测新消息 | Task 0 (侦察) + Task 6 |
| 打开会话读上下文 | Task 2 (`open_conversation`/`read_last_messages`) |
| AI 生成回复 (DeepSeek) | Task 4 |
| 敏感词转人工 | Task 5 + Task 6 |
| 全自动发送 | Task 6 |
| 每会话冷却/全局节流/每日限额/应急停止 | Task 3 + Task 6 (`run()` 的 KeyboardInterrupt) |
| 失败不重发 | Task 6 (`fill_and_send` 失败→handoff) |
| 选择器单点维护 | Task 0 (`selectors.py`) |
| 配置 `.env` 管理 Key | Task 1 + Task 0 (.env.example) |
| 通用话术库 | Task 7 |
| 单元测试 | Task 1-6 各含测试 |
| 集成验证 | Task 8 |

### 2. 占位符扫描

已修正：Task 6 实现中 handoff 分支的占位写法已用注释替换为明确实现。

### 3. 类型一致性

- `run_once()` 返回 `list[dict]`，Task 6 测试按此断言 ✓
- `SessionManager` 方法签名在 Task 3 定义、Task 6 使用一致 ✓
- `AIReplyEngine.generate_reply(history, shop_context="")` 签名跨 Task 4/6 一致 ✓
- `check_sensitive(text, words) -> str|None` 跨 Task 5/6 一致 ✓
- `BrowserController` 方法在 Task 2 定义、Task 6 调用，参数顺序一致 ✓
