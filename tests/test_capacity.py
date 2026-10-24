import pytest

from capplan.capacity import Hardware, plan, service_time
from capplan.workloads import MIXES, Request, sample_mix


def test_kv_bytes_per_token():
    assert Hardware().kv_bytes_per_token == 131_072


def test_kv_capacity_positive():
    assert Hardware().kv_capacity_tokens > 90_000


def test_service_time_prefill_cheaper_than_decode_per_token():
    hw = Hardware()
    assert service_time(1000, 0) < service_time(0, 1000)
    assert service_time(12_000, 0, hw) == pytest.approx(1.0)


def test_plan_tokens_per_second_equals_rps_times_mean():
    s = [Request("chat", 4000, 500)] * 10
    p = plan(100, s)
    assert (p.prefill_tokens_per_s, p.decode_tokens_per_s) == (400_000, 50_000)


def test_bigger_requests_need_more_replicas_at_same_rps():
    a = plan(100, sample_mix(MIXES["launch_estimate"], 5000))
    b = plan(100, sample_mix(MIXES["month_after"], 5000))
    assert b.replicas > 10 * a.replicas
    assert b.monthly_api_usd > 20 * a.monthly_api_usd


def test_plan_reports_percentiles():
    p = plan(100, sample_mix(MIXES["month_after"], 5000))
    lat = p.service_latency_s
    assert lat["p50"] <= lat["p95"] <= lat["p99"]
    assert p.cost_per_request["p99"] > p.cost_per_request["mean"]


def test_plan_rejects_bad_input():
    s = [Request("chat", 10, 10)]
    with pytest.raises(ValueError):
        plan(-1, s)
    with pytest.raises(ValueError):
        plan(1, [])
    with pytest.raises(ValueError):
        plan(1, s, target_util=0)


def test_largest_request_fits():
    assert plan(100, sample_mix(MIXES["month_after"], 5000)).fits_one_replica


def test_gpu_bill_scales_with_replicas():
    p = plan(100, sample_mix(MIXES["month_after"], 5000))
    assert p.monthly_gpu_usd == p.replicas * Hardware().hourly_usd * 720
