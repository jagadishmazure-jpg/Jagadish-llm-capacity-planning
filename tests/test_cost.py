import math

import pytest

from capplan.cost import SECONDS_PER_MONTH, Prices, monthly_cost, request_cost, tokens_per_second


def test_talk_small_request():
    assert request_cost(20, 30) == pytest.approx(0.000055)


def test_talk_large_request_is_100x():
    assert request_cost(8000, 1000) / request_cost(20, 30) == pytest.approx(100)


def test_output_priced_3x_input_by_default():
    p = Prices()
    assert p.output_per_m == 3 * p.input_per_m


def test_tokens_per_second_talk_example():
    assert tokens_per_second(100, 4000, 500) == (400_000, 50_000)


def test_monthly_cost():
    assert monthly_cost(1, 1_000_000, 0) == pytest.approx(0.5 * SECONDS_PER_MONTH)


def test_zero_is_allowed():
    assert request_cost(0, 0) == 0


@pytest.mark.parametrize("bad", [-1, -0.001, math.nan, math.inf, -math.inf, "5", None, True])
def test_request_cost_rejects_bad_input_tokens(bad):
    with pytest.raises(ValueError):
        request_cost(bad, 1)


@pytest.mark.parametrize("bad", [-1, math.nan, math.inf])
def test_request_cost_rejects_bad_output_tokens(bad):
    with pytest.raises(ValueError):
        request_cost(1, bad)


@pytest.mark.parametrize("field", ["input_per_m", "output_per_m"])
@pytest.mark.parametrize("bad", [-0.5, math.nan, math.inf])
def test_prices_reject_bad_values(field, bad):
    with pytest.raises(ValueError):
        Prices(**{field: bad})


@pytest.mark.parametrize("args", [(-1, 1, 1), (1, -1, 1), (1, 1, -1)])
def test_tokens_per_second_rejects_negative(args):
    with pytest.raises(ValueError):
        tokens_per_second(*args)


def test_monthly_cost_rejects_negative_rps():
    with pytest.raises(ValueError):
        monthly_cost(-1, 1, 1)


def test_custom_prices_change_cost():
    assert request_cost(1_000_000, 0, Prices(2.0, 6.0)) == pytest.approx(2.0)
