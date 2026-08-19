from pinduoduo_ai.safety import check_sensitive, default_sensitive_words

def test_hits_known_words():
    words = ["退款", "投诉", "12315"]
    assert check_sensitive("我要申请退款", words) == "退款"
    assert check_sensitive("我要投诉你", words) == "投诉"
    assert check_sensitive("我要拨打12315", words) == "12315"

def test_no_match_returns_none():
    words = ["退款", "投诉"]
    assert check_sensitive("请问几点发货", words) is None

def test_partial_word_not_hit():
    words = ["退款"]
    assert check_sensitive("你好呀", words) is None
    assert check_sensitive("退款政策是怎么样的", words) == "退款"

def test_default_words_cover_core_cases():
    words = default_sensitive_words()
    assert any(w in words for w in ["退款", "投诉", "法律", "12315"])
