# 拼多多 AI 自动客服

在拼多多客服网页版（mms.pinduoduo.com）中自动回复买家消息的 AI 客服工具。复用已登录的本地 Chrome（通过 CDP 连接），通过拼多多商家后台 WebSocket 实时接收买家消息，调用 DeepSeek 生成回复，经敏感词检查后自动发送，敏感话题自动转人工。

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
        │   队列 → 状态机 → AI 生成 → 敏感词检查 → 发送 │
        └─────────────────────────────────────────┘
```

**关键点**：拼多多的 HTTP 接口鉴权绑定浏览器会话，因此所有 HTTP 请求通过 CDP 让浏览器页面执行同源 fetch（而非导出 Cookie 后直连，那样会返回 43001 会话过期）。WebSocket 使用从浏览器会话获取的 token 连接。

## 功能特性

- **实时消息接收**：拼多多商家后台 WebSocket 推送，无需轮询
- **AI 智能回复**：DeepSeek 生成客服话术（OpenAI 兼容接口）
- **敏感词自动转人工**：退款/投诉/法律等话题不自动回复，标记转人工
- **发送失败兜底**：AI 回复发送失败时自动补发兜底话术
- **会话状态机**：每会话冷却、全局发送节流、每日回复限额
- **断线自动重连**：WebSocket 指数退避重连
- **消息去重**：避免重复处理同一消息

## 快速开始

### 1. 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
copy .env.example .env    # 填入 DEEPSEEK_API_KEY
```

### 3. 启动调试 Chrome 并登录

先**完全退出**已打开的 Chrome，再运行：

```bash
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="H:\ai_kfu\data\chrome_profile"
```

在此 Chrome 窗口中登录 `https://mms.pinduoduo.com/` 客服后台。

> `--user-data-dir` 指向独立配置目录，避免与日常 Chrome 配置冲突。此目录含登录态，已被 .gitignore 排除。

### 4. 验证登录态

```bash
python scripts/export_cookies.py
```

预期输出店铺信息即登录有效。

### 5. 运行

```bash
python main.py
```

启动后程序连接 WebSocket 实时监听买家消息，自动回复。按 `Ctrl+C` 停止。

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
| `shop_context.file` | 客服话术库文件（作为 AI 店铺上下文） |
| `fallback_text` | 发送失败时的兜底话术 |
| `business_hours` | 营业时间（预留） |

## 安全机制

- 敏感词自动转人工（退款/投诉/法律等，见 `src/pinduoduo_ai/safety.py`）
- 每会话回复冷却 60s
- 全局发送节流
- 每日自动回复限额
- Ctrl+C 应急停止
- 会话过期（43001）时停止自动回复，提示重新登录

## 话术库

`data/knowledge_base.md` 为通用客服话术库，作为 `shop_context` 注入 AI 提示词，可编辑扩充以提升回复准确性。

## 测试

```bash
python -m pytest tests/ -v
```

全部为 mock 测试，不依赖真实网络。

## 项目结构

```
├── main.py                      # 启动入口
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
