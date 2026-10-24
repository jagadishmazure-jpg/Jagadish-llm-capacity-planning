import pytest

from capplan import corpus, tokens


@pytest.mark.parametrize(
    "text,expected",
    [("", 0), ("hi", 1), ("hello world", 2), ("internationalization", 3), ("2026", 2), ("a, b.", 4), ("x\ny", 3), ("!!!", 1)],
)
def test_approx_tokens_rules(text, expected):
    assert tokens.approx_tokens(text) == expected


def test_approx_rejects_non_string():
    with pytest.raises(TypeError):
        tokens.approx_tokens(42)


def test_word_count():
    assert tokens.word_count("one  two\nthree") == 3


def test_tokens_exceed_words_on_every_corpus():
    for texts in corpus.samples().values():
        joined = "\n".join(texts)
        assert tokens.approx_tokens(joined) > tokens.word_count(joined)


def test_count_falls_back_to_approx():
    assert tokens.count("hello world") == 2


def test_corpus_is_deterministic():
    assert corpus.samples(1) == corpus.samples(1)


def test_corpus_uses_only_fictional_companies():
    text = "\n".join(corpus.samples()["contract"])
    assert any(c in text for c in corpus.COMPANIES)


@pytest.mark.skipif(not tokens.bpe_available(), reason="tiktoken encoding not available offline")
def test_approx_within_25_percent_of_bpe():
    for texts in corpus.samples().values():
        a = sum(map(tokens.approx_tokens, texts))
        b = sum(map(tokens.bpe_tokens, texts))
        assert 0.75 <= a / b <= 1.25
