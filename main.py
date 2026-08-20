"""拼多多 AI 自动客服 - 启动入口。

用法：
  1. 配置 .env（DEEPSEEK_API_KEY）
  2. 用 --remote-debugging-port=9222 --user-data-dir=H:\\ai_kfu\\data\\chrome_profile 启动调试 Chrome
  3. 在该 Chrome 中登录 https://mms.pinduoduo.com/ 客服后台
  4. 运行 python main.py
"""
from pinduoduo_ai.orchestrator import run

if __name__ == "__main__":
    run()
