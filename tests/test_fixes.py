import math

import pytest

from capplan.fixes import CapPolicy, DriftMonitor, FairShareQueue, FifoQueue, TenantBudget, TokenBucket, cap_request, chunk_text
from capplan.simulator import Item
from capplan.workloads import Request


def test_bucket_allows_burst_then_refills():
    b = TokenBucket(100, 1000)
    assert b.allow(1000, 0)
    assert not b.allow(1, 0)
    assert b.allow(100, 1.0)


def test_bucket_never_exceeds_burst():
    b = TokenBucket(100, 500)
    assert not b.allow(501, 1000)


def test_bucket_time_must_not_go_back():
    b = TokenBucket(1, 1)
    b.allow(0, 5)
    with pytest.raises(ValueError):
        b.allow(0, 4)


@pytest.mark.parametrize("args", [(-1, 1), (1, -1), (math.nan, 1)])
def test_bucket_rejects_bad_config(args):
    with pytest.raises(ValueError):
        TokenBucket(*args)


def test_bucket_rejects_negative_request():
    with pytest.raises(ValueError):
        TokenBucket(1, 1).allow(-5, 0)


def test_cap_leaves_small_requests():
    r = Request("chat", 20, 30)
    assert cap_request(r, CapPolicy()) == (r, "unchanged")


def test_cap_retrieves_instead_of_whole_document():
    r, a = cap_request(Request("contract_qa", 90_000, 400), CapPolicy())
    assert a == "retrieved" and r.input_tokens == 4 * 512 + 60


def test_cap_bounds_output():
    r, a = cap_request(Request("code_gen", 100, 4000), CapPolicy())
    assert r.output_tokens == 512 and a == "output_capped"


def test_cap_both():
    _, a = cap_request(Request("contract_qa", 50_000, 2000), CapPolicy())
    assert a == "retrieved+output_capped"


def test_chunk_text_overlap():
    chunks = chunk_text(list(range(10)), 4, 1)
    assert chunks[0] == [0, 1, 2, 3] and chunks[1][0] == 3


@pytest.mark.parametrize("size,overlap", [(0, 0), (4, 4), (4, -1)])
def test_chunk_text_bad(size, overlap):
    with pytest.raises(ValueError):
        chunk_text([1], size, overlap)


def test_budget_alerts_and_hard_stop():
    b = TenantBudget(1.0)
    assert b.charge_usd(0.5) and b.alerts == [50]
    assert b.charge_usd(0.3) and b.alerts == [50, 80]
    assert not b.charge_usd(0.3) and b.alerts == [50, 80, 100]
    assert b.spent == pytest.approx(0.8)


def test_budget_rejects_negative():
    with pytest.raises(ValueError):
        TenantBudget(-1)
    with pytest.raises(ValueError):
        TenantBudget(1).charge_usd(-0.1)


def test_budget_charges_requests():
    b = TenantBudget(1.0)
    assert b.charge(Request("chat", 20, 30))
    assert b.spent == pytest.approx(0.000055)


def test_drift_monitor_quiet_on_baseline():
    m = DriftMonitor(50, window=10, ratio=2)
    assert not any(m.observe(Request("chat", 20, 30)) for _ in range(100))


def test_drift_monitor_fires_on_shift():
    m = DriftMonitor(50, window=10, ratio=2)
    for _ in range(10):
        m.observe(Request("chat", 20, 30))
    fired = [m.observe(Request("contract_qa", 20_000, 400)) for _ in range(10)]
    assert fired[0] and m.mean > 100


def test_drift_monitor_needs_full_window():
    m = DriftMonitor(50, window=10, ratio=2)
    assert not m.observe(Request("contract_qa", 20_000, 400))


@pytest.mark.parametrize("args", [(0, 10, 2), (50, 0, 2), (50, 10, 1)])
def test_drift_monitor_bad_config(args):
    with pytest.raises(ValueError):
        DriftMonitor(*args)


def _item(tenant, t=0.0, size=10):
    return Item(Request("chat", size, 1, tenant=tenant), t)


def test_fifo_order():
    q = FifoQueue()
    for x in "abc":
        q.push(_item(x))
    assert [q.pop().req.tenant for _ in range(3)] == list("abc")


def test_fair_share_interleaves_heavy_and_light():
    q = FairShareQueue()
    for _ in range(5):
        q.push(_item("heavy", size=10_000))
    q.push(_item("light"))
    first_two = [q.pop().req.tenant for _ in range(2)]
    assert "light" in first_two


def test_fair_share_respects_blocked():
    q = FairShareQueue()
    q.push(_item("a"))
    q.push(_item("b"))
    assert q.peek(frozenset({"a"})).req.tenant == "b"
    assert q.peek(frozenset({"a", "b"})) is None


def test_fair_share_handles_falsy_keys():
    q = FairShareQueue(key=lambda r: r.user)
    q.push(Item(Request("chat", 1, 1, user=0), 0))
    assert q.peek() is not None and len(q) == 1


def test_fair_share_clock_monotonic():
    q = FairShareQueue()
    q.tick(5)
    with pytest.raises(ValueError):
        q.tick(4)


def test_fair_share_usage_decays():
    q = FairShareQueue(half_life_s=10)
    q.push(_item("a", size=1000))
    q.pop()
    q.tick(10)
    assert q.decayed_usage("a") == pytest.approx(500.5, rel=1e-6)
