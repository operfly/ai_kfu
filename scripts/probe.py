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
