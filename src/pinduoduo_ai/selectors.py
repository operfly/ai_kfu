"""拼多多客服网页版 DOM 选择器。

⚠️ 这些选择器基于 mms.pinduoduo.com 客服页真实 DOM 侦察得出。
当前为空占位结构 —— Task 0（环境侦察）完成后，运行 scripts/probe.py
提取真实选择器填入。拼多多改版可能导致失效，届时重新侦察更新。
"""
SELECTORS = {
    # 会话列表容器
    "conversation_list": "",
    # 单个会话项
    "conversation_item": "",
    # 未读角标
    "conversation_unread_badge": "",
    # 消息区
    "message_list": "",
    # 单条消息文本
    "message_text": "",
    # 输入框 (textarea 或 contenteditable)
    "input_box": "",
    # 发送按钮
    "send_button": "",
}
