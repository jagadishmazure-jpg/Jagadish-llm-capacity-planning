"""Discrete-time simulator of an LLM serving fleet.

Requests arrive as a Poisson stream at a fixed requests-per-second rate. Each replica, every
time step, spends part of its compute on decoding the live batch (one token per sequence per
``tpot_s``) and the rest on chunked prefill of admitted prompts. A request is admitted to a
replica only if its prompt plus its output fit in the free KV cache and the batch has room.
Everything is seeded, so results are reproducible and checked in CI.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .capacity import Hardware
from .cost import SECONDS_PER_MONTH, Prices, request_cost
from .fixes import CapPolicy, FairShareQueue, FifoQueue, TokenBucket, cap_request
from .workloads import MIXES, PROFILES, Request, percentile, validate_mix

TENANTS = ["orchard-row-legal", "pinecrest-mutual", "tidewater-clinics", "juniper-freight"]


@dataclass
class Item:
    req: Request
    arrival: float
    prefill_left: float = 0.0
    out_left: float = 0.0
    first_token: float | None = None


@dataclass
class Config:
    rps: float = 100.0
    duration_s: float = 60.0
    mix: dict = field(default_factory=lambda: dict(MIXES["launch_estimate"]))
    replicas: int = 3
    users: int = 2_000
    heavy_users: int = 100  # who send whole documents
    seed: int = 11
    dt: float = 0.01
    caps: CapPolicy | None = None
    per_user_tokens_per_s: float | None = None
    per_user_burst: float = 40_000
    global_tokens_per_s: float | None = None
    global_burst: float = 200_000
    fair_share: bool = False
    fair_by: str = "user"  # or "tenant"
    fair_inflight_tokens: float = 8_000
    rps_limit: float = 100.0
    max_sim_s: float = 3_600.0


def arrivals(cfg: Config) -> list[tuple[float, Request]]:
    validate_mix(cfg.mix)
    rng = random.Random(cfg.seed)
    kinds, weights = list(cfg.mix), list(cfg.mix.values())
    t, out = 0.0, []
    while True:
        t += rng.expovariate(cfg.rps)
        if t >= cfg.duration_s:
            return out
        k = rng.choices(kinds, weights)[0]
        p = PROFILES[k]
        if k == "chat":
            user = rng.randrange(cfg.heavy_users, cfg.users)
            tenant = TENANTS[user % len(TENANTS)]
        else:
            user = rng.randrange(cfg.heavy_users)
            tenant = TENANTS[0]
        out.append((t, Request(k, p.inp.sample(rng), p.out.sample(rng), user, tenant)))


def run(cfg: Config, hw: Hardware = Hardware(), prices: Prices = Prices()) -> dict:
    stream = arrivals(cfg)
    queue = FairShareQueue(key=_flow(cfg)) if cfg.fair_share else FifoQueue()
    flow = _flow(cfg)
    user_buckets: dict[int, TokenBucket] = {}
    global_bucket = TokenBucket(cfg.global_tokens_per_s, cfg.global_burst) if cfg.global_tokens_per_s else None
    rps_bucket = TokenBucket(cfg.rps_limit, cfg.rps_limit)
    reps = [{"prefill": [], "decode": [], "kv": 0} for _ in range(cfg.replicas)]
    kv_cap = hw.kv_capacity_tokens
    done: list[Item] = []
    inflight: dict[str, int] = {}
    rejected = {"rps": 0, "user_tokens": 0, "global_tokens": 0, "too_large": 0}
    actions: dict[str, int] = {}
    sent_in = sent_out = 0
    cost = 0.0
    i, now = 0, 0.0
    while now < cfg.max_sim_s:
        while i < len(stream) and stream[i][0] <= now:
            t, r = stream[i]
            i += 1
            if not rps_bucket.allow(1, t):
                rejected["rps"] += 1
                continue
            if cfg.caps:
                r, a = cap_request(r, cfg.caps)
                actions[a] = actions.get(a, 0) + 1
            need = r.input_tokens + r.output_tokens
            if need > kv_cap:
                rejected["too_large"] += 1
                continue
            if cfg.per_user_tokens_per_s:
                b = user_buckets.setdefault(r.user, TokenBucket(cfg.per_user_tokens_per_s, cfg.per_user_burst))
                if not b.allow(need, t):
                    rejected["user_tokens"] += 1
                    continue
            if global_bucket and not global_bucket.allow(need, t):
                rejected["global_tokens"] += 1
                continue
            sent_in += r.input_tokens
            sent_out += r.output_tokens
            cost += request_cost(r.input_tokens, r.output_tokens, prices)
            queue.push(Item(r, t, r.input_tokens, r.output_tokens))
        if isinstance(queue, FairShareQueue):
            queue.tick(now)
        # dispatch: each queued request goes to the replica with the least pending prefill work
        while len(queue):
            blocked = frozenset()
            if cfg.fair_share:
                limit = cfg.fair_inflight_tokens
                blocked = frozenset(k for k, v in inflight.items() if v >= limit)
            head = queue.peek(blocked)
            if head is None:
                break
            need = head.req.input_tokens + head.req.output_tokens
            fits = [r for r in reps if r["kv"] + need <= kv_cap and len(r["prefill"]) + len(r["decode"]) < hw.max_batch]
            if not fits:
                break
            rep = min(fits, key=lambda r: (sum(x.prefill_left for x in r["prefill"]), len(r["decode"])))
            queue.pop(blocked)
            inflight[flow(head.req)] = inflight.get(flow(head.req), 0) + head.req.input_tokens
            rep["kv"] += need
            rep["prefill"].append(head)
        for rep in reps:
            decode_share = len(rep["decode"]) / hw.max_batch
            budget = cfg.dt * (1 - decode_share) * hw.prefill_tokens_per_s
            # chunked prefill: the budget is shared equally by the prompts in flight
            while rep["prefill"] and budget > 1e-9:
                share = budget / len(rep["prefill"])
                left = []
                for it in rep["prefill"]:
                    use = min(share, it.prefill_left)
                    it.prefill_left -= use
                    budget -= use
                    if it.prefill_left <= 1e-9:
                        inflight[flow(it.req)] -= it.req.input_tokens
                        it.first_token = now + cfg.dt
                        rep["decode"].append(it)
                    else:
                        left.append(it)
                rep["prefill"] = left
            step_tokens = cfg.dt / hw.tpot_s
            still = []
            for it in rep["decode"]:
                if it.first_token > now:
                    still.append(it)
                    continue
                it.out_left -= step_tokens
                if it.out_left <= 1e-9:
                    it.finish = now + cfg.dt
                    rep["kv"] -= it.req.input_tokens + it.req.output_tokens
                    done.append(it)
                else:
                    still.append(it)
            rep["decode"] = still
        now += cfg.dt
        if i >= len(stream) and not len(queue) and all(not r["prefill"] and not r["decode"] for r in reps):
            break
    lat = [it.finish - it.arrival for it in done]
    chat = [it.finish - it.arrival for it in done if it.req.kind == "chat"]
    ttft = [it.first_token - it.arrival for it in done]
    served = len(done)
    scale = SECONDS_PER_MONTH / cfg.duration_s
    return {
        "arrived": len(stream),
        "served": served,
        "unfinished": len(stream) - served - sum(rejected.values()),
        "rejected": rejected,
        "cap_actions": actions,
        "avg_input_tokens": round(sent_in / max(1, served + len(queue)), 1),
        "avg_output_tokens": round(sent_out / max(1, served + len(queue)), 1),
        "latency_s": _pct(lat),
        "chat_latency_s": _pct(chat),
        "ttft_s": _pct(ttft),
        "monthly_api_usd": round(cost * scale, 2),
        "monthly_gpu_usd": round(cfg.replicas * hw.hourly_usd * 24 * 30, 2),
        "replicas": cfg.replicas,
        "sim_end_s": round(now, 2),
    }


def _flow(cfg: Config):
    if cfg.fair_by not in ("user", "tenant"):
        raise ValueError("fair_by must be 'user' or 'tenant'")
    return (lambda r: r.user) if cfg.fair_by == "user" else (lambda r: r.tenant)


def _pct(v: list[float]) -> dict:
    if not v:
        return {"p50": None, "p95": None, "p99": None}
    return {k: round(percentile(v, q), 3) for k, q in (("p50", 50), ("p95", 95), ("p99", 99))}
