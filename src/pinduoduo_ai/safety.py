DEFAULT_SENSITIVE_WORDS = [
    "退款", "退货", "投诉", "12315", "法律", "律师", "起诉",
    "举报", "差评", "威胁", "辱骂", "骗子", "欺诈", "赔偿",
    "工商", "消协", "媒体", "曝光", "死", "傻逼", "垃圾",
]


def default_sensitive_words() -> list[str]:
    return list(DEFAULT_SENSITIVE_WORDS)


def check_sensitive(text: str, sensitive_words: list[str]) -> str | None:
    """返回文本中命中的第一个敏感词；未命中返回 None。"""
    for w in sensitive_words:
        if w in text:
            return w
    return None
