"""Capacity planner: requests per second x token mix -> prefill and decode load, KV-cache memory,
replica count, latency percentiles and the monthly bill.

The hardware is a simulated accelerator ("sim-gpu-80") serving a simulated 8B-class model with
grouped-query attention. All throughput and price figures are assumptions, listed in one place.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .cost import SECONDS_PER_MONTH, Prices, _check, request_cost
from .workloads import Request, percentile, stats


@dataclass(frozen=True)
class Hardware:
    name: str = "sim-gpu-80"
    memory_gb: float = 80.0
    weights_gb: float = 16.0
    reserved_fraction: float = 0.10  # activations, fragmentation
    kv_bytes_per_token: int = 2 * 32 * 8 * 128 * 2  # K and V x layers x kv heads x head dim x fp16 = 131,072
    prefill_tokens_per_s: float = 12_000.0  # one parallel pass, compute bound
    tpot_s: float = 0.025  # time per output token for one sequence in a batch
    max_batch: int = 64  # sequences decoded together
    hourly_usd: float = 2.50  # illustrative on-demand rate

    @property
    def kv_capacity_tokens(self) -> int:
        free = self.memory_gb * (1 - self.reserved_fraction) - self.weights_gb
        return int(free * 1e9 // self.kv_bytes_per_token)

    @property
    def decode_tokens_per_s(self) -> float:
        return self.max_batch / self.tpot_s


@dataclass(frozen=True)
class Plan:
    rps: float
    requests_sampled: int
    input_tokens: dict
    output_tokens: dict
    prefill_tokens_per_s: float
    decode_tokens_per_s: float
    concurrent_sequences: float
    kv_cache_gb: float
    largest_request_kv_gb: float
    replicas_by_prefill: int
    replicas_by_decode: int
    replicas_by_memory: int
    replicas: int
    service_latency_s: dict
    cost_per_request: dict
    monthly_api_usd: float
    monthly_gpu_usd: float
    fits_one_replica: bool

    def as_dict(self) -> dict:
        return asdict(self)


def service_time(inp: int, out: int, hw: Hardware = Hardware()) -> float:
    """Unloaded latency: one prefill pass, then one decode step per output token."""
    return inp / hw.prefill_tokens_per_s + out * hw.tpot_s


def plan(rps: float, sample: list[Request], hw: Hardware = Hardware(), prices: Prices = Prices(), target_util: float = 0.6) -> Plan:
    _check("rps", rps)
    if not sample:
        raise ValueError("sample is empty")
    if not 0 < target_util <= 1:
        raise ValueError("target_util must be in (0, 1]")
    ins = [r.input_tokens for r in sample]
    outs = [r.output_tokens for r in sample]
    mean_in, mean_out = sum(ins) / len(ins), sum(outs) / len(outs)
    prefill_tps, decode_tps = rps * mean_in, rps * mean_out
    # Little's law: sequences in decode at once = arrival rate x time spent decoding.
    concurrent = rps * mean_out * hw.tpot_s
    # Each live sequence holds KV for its prompt plus, on average, half its output.
    mean_ctx = sum(i + o / 2 for i, o in zip(ins, outs, strict=True)) / len(ins)
    kv_bytes = concurrent * mean_ctx * hw.kv_bytes_per_token
    largest = max(i + o for i, o in zip(ins, outs, strict=True))
    by_prefill = math.ceil(prefill_tps / (hw.prefill_tokens_per_s * target_util))
    by_decode = math.ceil(concurrent / (hw.max_batch * target_util))
    by_memory = math.ceil(concurrent * mean_ctx / (hw.kv_capacity_tokens * target_util))
    replicas = max(1, by_prefill, by_decode, by_memory)
    lat = [service_time(i, o, hw) for i, o in zip(ins, outs, strict=True)]
    costs = [request_cost(i, o, prices) for i, o in zip(ins, outs, strict=True)]
    return Plan(
        rps=rps,
        requests_sampled=len(sample),
        input_tokens=stats(ins),
        output_tokens=stats(outs),
        prefill_tokens_per_s=round(prefill_tps),
        decode_tokens_per_s=round(decode_tps),
        concurrent_sequences=round(concurrent, 1),
        kv_cache_gb=round(kv_bytes / 1e9, 2),
        largest_request_kv_gb=round(largest * hw.kv_bytes_per_token / 1e9, 2),
        replicas_by_prefill=by_prefill,
        replicas_by_decode=by_decode,
        replicas_by_memory=by_memory,
        replicas=replicas,
        service_latency_s={k: round(percentile(lat, q), 3) for k, q in (("p50", 50), ("p95", 95), ("p99", 99))},
        cost_per_request={
            "mean": round(sum(costs) / len(costs), 7),
            "p50": round(percentile(costs, 50), 7),
            "p95": round(percentile(costs, 95), 7),
            "p99": round(percentile(costs, 99), 7),
        },
        monthly_api_usd=round(rps * SECONDS_PER_MONTH * sum(costs) / len(costs), 2),
        monthly_gpu_usd=round(replicas * hw.hourly_usd * 24 * 30, 2),
        fits_one_replica=largest <= hw.kv_capacity_tokens,
    )
