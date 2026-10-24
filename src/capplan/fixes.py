"""The fixes from the talk, as small composable parts.

* ``TokenBucket`` - rate limit in tokens per second, per user and globally.
* ``cap_request`` - input size cap: oversized documents go through retrieval (top-k chunks) instead
  of being sent whole; output is bounded by ``max_tokens``.
* ``TenantBudget`` - monthly spend per tenant with 50/80/100% alerts and a hard stop.
* ``DriftMonitor`` - alerts when average tokens per request drift from the planning baseline.
* ``FifoQueue`` / ``FairShareQueue`` - admission order; fair share serves the tenant that has used
  the fewest tokens recently, so one heavy tenant cannot starve everyone else.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field, replace

from .cost import Prices, _check, request_cost
from .workloads import Request


class TokenBucket:
    def __init__(self, rate_per_s: float, burst: float):
        self.rate = _check("rate_per_s", rate_per_s)
        self.burst = _check("burst", burst)
        self.level = self.burst
        self.t = 0.0

    def allow(self, tokens: float, now: float) -> bool:
        _check("tokens", tokens)
        if now < self.t:
            raise ValueError("time went backwards")
        self.level = min(self.burst, self.level + (now - self.t) * self.rate)
        self.t = now
        if tokens <= self.level:
            self.level -= tokens
            return True
        return False


@dataclass(frozen=True)
class CapPolicy:
    max_input_tokens: int = 8_000
    chunk_tokens: int = 512
    top_k: int = 4
    question_tokens: int = 60
    max_output_tokens: int = 512


def cap_request(r: Request, p: CapPolicy) -> tuple[Request, str]:
    """Return the request as it would be sent to the model, and what was done to it."""
    action = "unchanged"
    inp = r.input_tokens
    if inp > p.max_input_tokens:
        chunks = math.ceil(inp / p.chunk_tokens)
        inp = min(chunks, p.top_k) * p.chunk_tokens + p.question_tokens
        action = "retrieved"
    out = min(r.output_tokens, p.max_output_tokens)
    if out < r.output_tokens:
        action = "output_capped" if action == "unchanged" else action + "+output_capped"
    return replace(r, input_tokens=inp, output_tokens=out), action


def chunk_text(tokens: list[str], size: int, overlap: int = 0) -> list[list[str]]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("need size > overlap >= 0")
    step = size - overlap
    return [tokens[i : i + size] for i in range(0, max(1, len(tokens) - overlap), step)]


@dataclass
class TenantBudget:
    monthly_usd: float
    prices: Prices = field(default_factory=Prices)
    spent: float = 0.0
    alerts: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        _check("monthly_usd", self.monthly_usd)

    def charge(self, r: Request) -> bool:
        """Charge a request. Returns False (and charges nothing) once the budget is used up."""
        return self.charge_usd(request_cost(r.input_tokens, r.output_tokens, self.prices))

    def charge_usd(self, c: float) -> bool:
        _check("charge", c)
        if self.spent + c > self.monthly_usd:
            if 100 not in self.alerts:
                self.alerts.append(100)
            return False
        self.spent += c
        for level in (50, 80):
            if self.spent >= self.monthly_usd * level / 100 and level not in self.alerts:
                self.alerts.append(level)
        return True


class DriftMonitor:
    """Rolling mean of tokens per request against the planning baseline."""

    def __init__(self, baseline_tokens: float, window: int = 500, ratio: float = 2.0):
        if baseline_tokens <= 0 or window <= 0 or ratio <= 1:
            raise ValueError("baseline > 0, window > 0 and ratio > 1 required")
        self.baseline, self.ratio = baseline_tokens, ratio
        self.window: deque[int] = deque(maxlen=window)
        self.total = 0

    def observe(self, r: Request) -> bool:
        t = r.input_tokens + r.output_tokens
        if len(self.window) == self.window.maxlen:
            self.total -= self.window[0]
        self.window.append(t)
        self.total += t
        return len(self.window) == self.window.maxlen and self.mean > self.baseline * self.ratio

    @property
    def mean(self) -> float:
        return self.total / len(self.window) if self.window else 0.0


class FifoQueue:
    def __init__(self) -> None:
        self.q: deque = deque()

    def push(self, item) -> None:
        self.q.append(item)

    def peek(self, blocked: frozenset = frozenset()):
        return self.q[0] if self.q else None

    def pop(self, blocked: frozenset = frozenset()):
        return self.q.popleft()

    def __len__(self) -> int:
        return len(self.q)


class FairShareQueue:
    """Serve the flow (tenant or user) with the least decayed token usage first, FIFO within a flow.

    The simulator also passes ``blocked``: flows that already hold more than their share of
    in-flight prefill work, so one heavy flow cannot fill every batch slot.
    """

    def __init__(self, half_life_s: float = 60.0, key=lambda r: r.tenant):
        self.key = key
        self.queues: dict[str, deque] = {}
        self.usage: dict[str, float] = {}
        self.decay = math.log(2) / half_life_s
        self.t = 0.0
        self.n = 0

    def tick(self, now: float) -> None:
        """Advance the clock. Usage is stored scaled by exp(decay * t), so decaying every flow
        is implicit: all flows share the same factor and their order is unchanged."""
        if now < self.t:
            raise ValueError("time went backwards")
        self.t = now

    def decayed_usage(self, key) -> float:
        return self.usage.get(key, 0.0) * math.exp(-self.decay * self.t)

    def push(self, item) -> None:
        k = self.key(item.req)
        self.queues.setdefault(k, deque()).append(item)
        self.usage.setdefault(k, 0.0)
        self.n += 1

    def _pick(self, blocked: frozenset = frozenset()):
        live = [k for k, q in self.queues.items() if q and k not in blocked]
        return min(live, key=lambda k: (self.usage[k], k)) if live else None

    def peek(self, blocked: frozenset = frozenset()):
        k = self._pick(blocked)
        return self.queues[k][0] if k is not None else None

    def pop(self, blocked: frozenset = frozenset()):
        k = self._pick(blocked)
        item = self.queues[k].popleft()
        self.usage[k] += (item.req.input_tokens + item.req.output_tokens) * math.exp(self.decay * self.t)
        self.n -= 1
        return item

    def __len__(self) -> int:
        return self.n
