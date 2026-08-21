# 拼多多 AI 自动客服

在拼多多客服网页版（mms.pinduoduo.com）中自动回复买家消息的 AI 客服工具。复用已登录的本地 Chrome（通过 CDP 连接），通过拼多多商家后台 WebSocket 实时接收买家消息，调用 DeepSeek 生成回复，经知识库检索与敏感词检查后自动发送，敏感话题自动转人工。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                   本地已登录 Chrome                       │
│           (--remote-debugging-port=9222)                 │
│  ┌───────────────────────────────────────────────────┐  │
│  │  mms.pinduoduo.com 页面（浏览器会话，承载鉴权）      │  │
│  └───────────────┬──────────────────┬────────────────┘  │
└──────────────────┼──────────────────┼───────────────────┘
                   │ CDP fetch        │ token 获取
                   ▼                  ▼
        ┌─────────────────┐   ┌────────────────┐
        │   PDDApi        │   │  PDDWebSocket  │
        │  HTTP 接口调用   │   │  实时消息接收   │
        └────────┬────────┘   └───────┬────────┘
                 │  send_text        │ 买家消息
                 ▼                   ▼
        ┌─────────────────────────────────────────┐
        │   Orchestrator（asyncio 主循环）          │
        │   队列 → 知识库检索 → AI → 敏感词 → 转人工 │
        └─────────────────────────────────────────┘
```

**关键点**：拼多多的 HTTP 接口鉴权绑定浏览器会话，因此所有 HTTP 请求通过 CDP 让浏览器页面执行同源 fetch（而非导出 Cookie 后直连，那样会返回 43001 会话过期）。WebSocket 使用从浏览器会话获取的 token 连接。

## 功能特性

- **实时消息接收**：拼多多商家后台 WebSocket 推送，无需轮询
- **AI 智能回复**：DeepSeek 生成客服话术（OpenAI 兼容接口）
- **知识库检索**：按买家问题检索话术库相关话题注入 AI；无命中自动转人工
- **真实转人工**：敏感词/无知识命中时调用 API 把会话转给其他在线客服，无客服在线时发送提示话术
- **敏感词自动转人工**：退款/投诉/法律等话题不自动回复，转人工
- **发送失败兜底**：AI 回复发送失败时自动补发兜底话术
- **会话状态机**：每会话冷却、全局发送节流、每日回复限额
- **断线自动重连**：WebSocket 指数退避重连
- **消息去重**：避免重复处理同一消息

## 环境要求

- **Windows 10/11**（脚本与 CDP 基于 Windows 设计）
- **Python 3.10+**
- **Google Chrome**（已安装，默认路径 `C:\Program Files\Google\Chrome\Application\chrome.exe`）
- **DeepSeek API Key**（[获取地址](https://platform.deepseek.com/)）

## 使用方式

### 首次使用（一次性配置）

**第 1 步：安装依赖**

```bash
python -m pip install -r requirements.txt
```

**第 2 步：配置 API Key**

```bash
copy .env.example .env
```

用编辑器打开 `.env`，把 `DEEPSEEK_API_KEY=sk-xxxxxxxx` 替换为你的真实 Key。

**第 3 步：启动调试 Chrome 并登录拼多多**

双击根目录的 **`start_chrome.bat`**（或运行 `start_chrome.bat`）。脚本会自动：

1. 检测端口 9222 是否被占用（已占用则提示，直接跳到下一步）
2. 用独立的 `--user-data-dir` 启动 Chrome 调试实例
3. 自动打开拼多多客服后台 `https://mms.pinduoduo.com/`

在打开的 Chrome 窗口中**登录拼多多商家账号**，进入客服工作台。此 Chrome 窗口**必须保持打开**，程序依赖它的登录态。

**第 4 步：验证登录态（可选）**

```bash
python scripts/export_cookies.py
```

预期输出"登录态有效"和店铺信息，说明登录正常。

### 日常使用（每次运行前）

**第 1 步：确保调试 Chrome 已启动**

双击 `start_chrome.bat`（若已在运行会提示，无需重复操作），确认客服后台已登录。

**第 2 步：运行程序**

```bash
python main.py
```

看到以下输出即启动成功：

```
拼多多 AI 客服已启动，Ctrl+C 停止。
[WS] 已连接拼多多客服通道
```

此时程序开始实时监听买家消息。**在拼多多客服后台用另一个账号给店铺发消息**，程序会自动回复，终端会打印处理日志：

```
[买家昵称] reply: 亲，我们承诺 48 小时内发货的哦～
[买家昵称] handoff: 未找到相关知识，转人工
```

按 `Ctrl+C` 停止程序。

## 使用说明要点

### 程序会如何处理买家消息

| 买家消息 | 程序行为 |
|---|---|
| 命中知识库话题（发货/物流/尺码/退款等） | 检索相关话术 → AI 生成回复 → 自动发送 |
| 未命中任何知识库话题 | 转人工（转给其他在线客服；无客服则发提示话术） |
| AI 回复含敏感词（退款/投诉/法律等） | 不发送，转人工 |
| AI 服务不可用 / 发送失败 | 发送兜底话术"亲，感谢您的咨询…" |

### 话术库如何扩充

编辑 `data/knowledge_base.md`，按 `## 话题名` + `- 话术` 格式新增条目。话题关键词映射在 `src/pinduoduo_ai/knowledge.py` 的 `TOPIC_KEYWORDS`，新增话题时需同步添加关键词。

## 配置说明（config.yaml）

| 配置项 | 说明 |
|---|---|
| `pdd.cdp_port` | 调试 Chrome 端口（默认 9222） |
| `pdd.api_version` | 拼多多 WebSocket API 版本 |
| `polling.conversation_cooldown_seconds` | 每会话回复后冷却时间（秒） |
| `polling.global_rate_limit_seconds` | 全局两条回复最小间隔（秒） |
| `polling.daily_reply_limit` | 每日自动回复上限 |
| `reconnect.*` | WebSocket 断线重连参数（退避） |
| `ai.model` / `ai.base_url` | DeepSeek 模型与接口地址 |
| `shop_context.file` | 客服话术库文件（按买家问题检索相关话题注入 AI） |
| `fallback_text` | 发送失败时的兜底话术 |
| `business_hours` | 营业时间（预留，暂未启用） |

## 故障排查

| 现象 | 原因与解决 |
|---|---|
| `[错误] Cookie 文件不存在` 或 `无法连接调试 Chrome` | 调试 Chrome 未启动。双击 `start_chrome.bat` |
| `[错误] 未找到 DEEPSEEK_API_KEY` | 未配置 `.env`。复制 `.env.example` 为 `.env` 并填入 Key |
| `[WS] 会话已过期` | 拼多多登录态失效。在调试 Chrome 中重新登录客服后台 |
| 启动报错 `Event loop is closed` | 程序被强制终止（如直接关终端）。正常用 `Ctrl+C` 退出 |
| 一直无买家消息处理日志 | 确认调试 Chrome 客服后台已登录、`[WS] 已连接` 已出现 |

## 安全机制

- 敏感词自动转人工（退款/投诉/法律等，见 `src/pinduoduo_ai/safety.py`）
- 每会话回复冷却 60s
- 全局发送节流
- 每日自动回复限额
- Ctrl+C 应急停止
- 会话过期（43001）时停止自动回复，提示重新登录

## 测试

```bash
python -m pytest tests/ -v
```

全部为 mock 测试，不依赖真实网络。

## 项目结构

```
├── main.py                      # 启动入口
├── start_chrome.bat             # 启动调试 Chrome（双击即用）
├── config.yaml                  # 配置文件
├── requirements.txt             # Python 依赖
├── scripts/
│   └── export_cookies.py        # 验证调试 Chrome 登录态
├── src/pinduoduo_ai/
│   ├── orchestrator.py          # asyncio 主循环（队列 + 状态机）
│   ├── pdd_api.py               # HTTP 接口（CDP 浏览器 fetch）
│   ├── pdd_ws.py                # WebSocket 客户端（重连 + 去重）
│   ├── message_types.py         # WS 消息解析
│   ├── cookie_store.py          # CDP 会话管理
│   ├── knowledge.py             # 知识库检索
│   ├── ai_reply_engine.py       # DeepSeek 回复生成
│   ├── safety.py                # 敏感词检查
│   ├── session_manager.py       # 会话状态机
│   └── config.py                # 配置加载
├── data/
│   └── knowledge_base.md        # 客服话术库
└── tests/                       # 单元测试
```

## 免责声明

本项目为自动化工具，使用前请确认符合拼多多平台规则。请合理使用，避免触发平台风控。
