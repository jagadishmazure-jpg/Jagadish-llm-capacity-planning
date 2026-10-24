import pytest

from capplan.fixes import CapPolicy
from capplan.simulator import Config, arrivals, run
from capplan.workloads import MIXES

SHORT = 10.0


@pytest.fixture(scope="module")
def launch():
    return run(Config(duration_s=SHORT))


@pytest.fixture(scope="module")
def incident():
    return run(Config(duration_s=SHORT, mix=dict(MIXES["month_after"])))


def test_arrivals_near_rps():
    n = len(arrivals(Config(duration_s=SHORT)))
    assert 900 <= n <= 1100


def test_rps_limit_holds_in_both(launch, incident):
    for r in (launch, incident):
        assert r["rejected"]["rps"] < 0.02 * r["arrived"]


def test_everyone_served_at_launch(launch):
    assert launch["unfinished"] == 0 and launch["served"] + launch["rejected"]["rps"] == launch["arrived"]


def test_incident_same_rps_bigger_bill(launch, incident):
    assert abs(incident["arrived"] - launch["arrived"]) < 50
    assert incident["monthly_api_usd"] > 10 * launch["monthly_api_usd"]


def test_incident_p99_grows(launch, incident):
    assert incident["latency_s"]["p99"] > 10 * launch["latency_s"]["p99"]


def test_bigger_fleet_restores_chat_latency(incident):
    big = run(Config(duration_s=SHORT, mix=dict(MIXES["month_after"]), replicas=47))
    assert big["chat_latency_s"]["p99"] < incident["chat_latency_s"]["p99"] / 10


def test_caps_cut_bill(incident):
    c = run(Config(duration_s=SHORT, mix=dict(MIXES["month_after"]), caps=CapPolicy()))
    assert c["monthly_api_usd"] < incident["monthly_api_usd"] / 4
    assert c["cap_actions"]["retrieved"] > 0


def test_global_token_bucket_sheds_load():
    r = run(Config(duration_s=SHORT, mix=dict(MIXES["month_after"]), global_tokens_per_s=20_000))
    assert r["rejected"]["global_tokens"] > 0


def test_per_user_bucket_rejects_heavy_users():
    r = run(Config(duration_s=SHORT, mix=dict(MIXES["month_after"]), per_user_tokens_per_s=500, per_user_burst=10_000))
    assert r["rejected"]["user_tokens"] > 0


def test_fair_share_protects_chat(incident):
    f = run(Config(duration_s=SHORT, mix=dict(MIXES["month_after"]), caps=CapPolicy(), fair_share=True))
    assert f["chat_latency_s"]["p99"] < incident["chat_latency_s"]["p99"]


def test_fair_by_validation():
    with pytest.raises(ValueError):
        run(Config(duration_s=1, fair_share=True, fair_by="planet"))


def test_simulation_is_deterministic():
    assert run(Config(duration_s=3)) == run(Config(duration_s=3))


def test_percentiles_ordered(incident):
    lat = incident["latency_s"]
    assert lat["p50"] <= lat["p95"] <= lat["p99"]
