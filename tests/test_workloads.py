import pytest

from capplan import workloads as w


def test_profiles_cover_four_workloads():
    assert set(w.PROFILES) == {"chat", "contract_qa", "code_gen", "summarization"}


@pytest.mark.parametrize("name", list(w.PROFILES))
def test_samples_respect_bounds(name):
    p = w.PROFILES[name]
    for r in w.sample_mix({name: 1.0}, 2000):
        assert p.inp.lo <= r.input_tokens <= p.inp.hi
        assert p.out.lo <= r.output_tokens <= p.out.hi


def test_contract_qa_reaches_90k():
    assert max(r.input_tokens for r in w.sample_mix({"contract_qa": 1.0}, 5000)) == 90_000


def test_chat_matches_talk_short_request():
    s = w.stats([r.input_tokens for r in w.sample_mix({"chat": 1.0}, 5000)])
    assert 15 <= s["p50"] <= 25


@pytest.mark.parametrize("mix", [{}, {"chat": 0.5}, {"chat": 1.2, "code_gen": -0.2}, {"nope": 1.0}])
def test_bad_mixes_rejected(mix):
    with pytest.raises(ValueError):
        w.validate_mix(mix)


@pytest.mark.parametrize("name", list(w.MIXES))
def test_named_mixes_valid(name):
    w.validate_mix(w.MIXES[name])


def test_sampling_is_seeded():
    assert w.sample_mix(w.MIXES["month_after"], 100, 3) == w.sample_mix(w.MIXES["month_after"], 100, 3)


def test_percentile_nearest_rank():
    v = list(range(1, 101))
    assert (w.percentile(v, 50), w.percentile(v, 99), w.percentile(v, 100)) == (50, 99, 100)


def test_percentile_empty():
    with pytest.raises(ValueError):
        w.percentile([], 50)


def test_histogram_counts_everything():
    vals = [1, 60, 300, 2000, 5000, 20000, 90000]
    assert w.histogram(vals) == [1, 1, 1, 1, 1, 1, 1]


def test_stats_p99_above_mean_for_heavy_tail():
    s = w.stats([r.input_tokens for r in w.sample_mix(w.MIXES["month_after"], 5000)])
    assert s["p50"] < s["mean"] < s["p99"]


def test_svg_chart_is_valid_markup():
    svg = w.svg_bars("t <x>", ["a", "b"], {"s": [1, 2]})
    assert svg.startswith("<svg") and svg.endswith("</svg>") and "&lt;x&gt;" in svg
