"""拼多多 AI 自动客服 - 启动入口。

用法：
  1. 配置 .env（DEEPSEEK_API_KEY）
  2. 启动调试 Chrome 登录拼多多客服后台，运行 scripts/export_cookies.py 导出 Cookie
  3. 运行 python main.py
"""
from pinduoduo_ai.orchestrator import run

if __name__ == "__main__":
    run()
