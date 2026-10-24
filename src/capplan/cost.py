"""Token-priced cost model with separate input (prefill) and output (decode) prices.

Prices are illustrative list-style numbers for a fictional hosted model, not a quote.
Every input is validated: negative, NaN or infinite values raise ``ValueError``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SECONDS_PER_MONTH = 30 * 24 * 3600


def _check(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a number")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must be finite")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return float(value)


@dataclass(frozen=True)
class Prices:
    """US dollars per million tokens. Output defaults to 3x input, as in the talk."""

    input_per_m: float = 0.50
    output_per_m: float = 1.50
    as_of: str = "2026-10 (illustrative)"

    def __post_init__(self) -> None:
        _check("input_per_m", self.input_per_m)
        _check("output_per_m", self.output_per_m)


def request_cost(input_tokens: float, output_tokens: float, prices: Prices = Prices()) -> float:
    i = _check("input_tokens", input_tokens)
    o = _check("output_tokens", output_tokens)
    return (i * prices.input_per_m + o * prices.output_per_m) / 1_000_000


def monthly_cost(rps: float, avg_input: float, avg_output: float, prices: Prices = Prices()) -> float:
    r = _check("rps", rps)
    return r * SECONDS_PER_MONTH * request_cost(avg_input, avg_output, prices)


def tokens_per_second(rps: float, avg_input: float, avg_output: float) -> tuple[float, float]:
    r, i, o = _check("rps", rps), _check("avg_input", avg_input), _check("avg_output", avg_output)
    return r * i, r * o
