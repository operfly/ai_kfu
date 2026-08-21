# src/pinduoduo_ai/knowledge.py
"""知识库检索：解析话术库 md，按话题关键词匹配买家问题，返回相关话术。"""
from pathlib import Path

# 话题 → 关键词（买家消息含任一关键词即命中该话题）
TOPIC_KEYWORDS = {
    "问候": ["在吗", "你好", "在不在", "hi", "hello", "哈喽", "亲"],
    "发货": ["发货", "什么时候发", "加急", "发了吗", "几天发"],
    "物流": ["物流", "快递", "单号", "到哪", "运输", "签收", "派送"],
    "尺码材质": ["尺码", "大小", "材质", "面料", "成分", "尺寸", "多大", "几个码"],
    "价格优惠": ["价格", "优惠", "便宜", "打折", "活动", "多少钱", "怎么卖", "贵"],
    "售后退换": ["退货", "退款", "换货", "售后", "退", "质量问题", "坏了", "破损"],
    "支付": ["支付", "付款", "怎么付", "支付宝", "微信", "下单"],
    "发票": ["发票", "开票", "报销"],
    "优惠券": ["优惠券", "领券", "券"],
    "客服身份": ["人工", "真人", "客服在吗", "转人工"],
}


class KnowledgeBase:
    """从 markdown 话术库构建 {话题: [话术]} 索引，按关键词检索。"""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._topics: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"话术库不存在: {self._path}")
        current: str | None = None
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("## "):
                current = line[3:].strip()
                self._topics.setdefault(current, [])
            elif line.startswith("- ") and current:
                self._topics[current].append(line[2:].strip())

    def topics(self) -> list[str]:
        return list(self._topics.keys())

    def entries(self, topic: str) -> list[str]:
        return list(self._topics.get(topic, []))

    def _match_topics(self, question: str) -> list[str]:
        q = question.lower()
        hits = []
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(k.lower() in q for k in keywords):
                hits.append(topic)
        return hits

    def match(self, question: str) -> bool:
        """买家问题是否命中任一话题。"""
        return bool(self._match_topics(question))

    def retrieve(self, question: str) -> list[str]:
        """返回买家问题命中的话题下所有话术；未命中返回空列表。"""
        hits = self._match_topics(question)
        result = []
        for topic in hits:
            result.extend(self.entries(topic))
        return result
