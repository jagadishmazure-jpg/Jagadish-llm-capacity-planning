"""Token counting.

Two counters:

* ``approx_tokens`` - an offline, dependency-free approximation of a byte-pair-encoding tokenizer.
  A word of up to 8 letters is one token and longer words add one token per extra 8 letters,
  every group of up to 3 digits is one token, every run of punctuation is one token and every
  line break is one token.
  It is deterministic, so CI uses it.
* ``bpe_tokens`` - the real ``cl100k_base`` encoding from the free ``tiktoken`` library, used when
  it is installed and its encoding file is cached locally. It returns ``None`` otherwise.

``docs/tokens.md`` reports how close the approximation is on the repo's own corpus.
"""

from __future__ import annotations

import math
import re

_PIECE = re.compile(r"[A-Za-z]+|\d{1,3}|[^\sA-Za-z\d]+|\n")
_WORD = re.compile(r"\S+")


def approx_tokens(text: str) -> int:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    total = 0
    for piece in _PIECE.findall(text):
        total += math.ceil(len(piece) / 8) if piece[0].isalpha() else 1
    return total


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


_ENC = None
_ENC_TRIED = False


def bpe_available() -> bool:
    global _ENC, _ENC_TRIED
    if not _ENC_TRIED:
        _ENC_TRIED = True
        try:
            import tiktoken

            _ENC = tiktoken.get_encoding("cl100k_base")
        except Exception:  # noqa: BLE001 - missing package or no cached encoding offline
            _ENC = None
    return _ENC is not None


def bpe_tokens(text: str) -> int | None:
    if not bpe_available():
        return None
    return len(_ENC.encode(text))


def count(text: str, prefer_bpe: bool = False) -> int:
    if prefer_bpe:
        n = bpe_tokens(text)
        if n is not None:
            return n
    return approx_tokens(text)
