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
