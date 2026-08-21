# tests/test_knowledge.py
import pytest

from pinduoduo_ai.knowledge import KnowledgeBase

SAMPLE_MD = """# 测试话术库

## 问候
- 买家说"在吗"：亲，在的哦～请问有什么可以帮您？😊
- 开场问候：亲，您好！欢迎光临本店

## 发货
- 问发货时间：亲，我们承诺 48 小时内发货的哦～
- 问加急：非常抱歉亲，目前暂不支持加急发货呢

## 物流
- 问物流进度：亲，您可以在【我的订单】里查看物流单号
"""


@pytest.fixture
def kb(tmp_path):
    p = tmp_path / "kb.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    return KnowledgeBase(p)


def test_parse_topics(kb):
    assert set(kb.topics()) == {"问候", "发货", "物流"}


def test_parse_entries(kb):
    entries = kb.entries("发货")
    assert len(entries) == 2
    assert "48 小时内发货" in entries[0]


def test_retrieve_matches_related_topic(kb):
    related = kb.retrieve("你们什么时候发货呀？")
    assert len(related) >= 1
    assert "48 小时内发货" in related[0]


def test_retrieve_no_match_returns_empty(kb):
    assert kb.retrieve("今天天气怎么样") == []


def test_match_true_when_keyword_hit(kb):
    assert kb.match("我的快递到哪了") is True


def test_match_false_when_no_keyword(kb):
    assert kb.match("随便聊聊") is False


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        KnowledgeBase(tmp_path / "nope.md")
