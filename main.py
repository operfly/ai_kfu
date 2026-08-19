"""拼多多 AI 自动客服 - 启动入口。

用法：
  1. 启动 Chrome 调试端口（见 README）
  2. 配置 .env（DEEPSEEK_API_KEY）
  3. 运行 python main.py
"""
from pinduoduo_ai.orchestrator import run

if __name__ == "__main__":
    run()
