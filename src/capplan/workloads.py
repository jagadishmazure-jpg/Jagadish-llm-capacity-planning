"""Workload profiles: token distributions per request type, mixes, histograms and SVG charts.

Each profile draws input and output token counts from a clipped log-normal distribution.
The shapes are assumptions for a fictional legal-help chatbot (Kestrel Lane Software's
"Brightdesk"), chosen to resemble the talk's scenario; they are not measured from real traffic.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class Dist:
    median: float
    sigma: float
    lo: int
    hi: int

    def sample(self, rng: random.Random) -> int:
        v = rng.lognormvariate(math.log(self.median), self.sigma)
        return int(min(self.hi, max(self.lo, round(v))))


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    inp: Dist
    out: Dist


PROFILES: dict[str, Profile] = {
    "chat": Profile("chat", "short questions and answers", Dist(20, 0.5, 3, 400), Dist(30, 0.5, 5, 400)),
    "contract_qa": Profile(
        "contract_qa", "a whole contract pasted in, then a question", Dist(20_000, 0.9, 2_000, 90_000), Dist(400, 0.5, 50, 2_000)
    ),
    "code_gen": Profile("code_gen", "code context in, code out", Dist(1_500, 0.7, 100, 16_000), Dist(600, 0.6, 50, 4_000)),
    "summarization": Profile(
        "summarization", "a long document in, a short summary out", Dist(6_000, 0.7, 500, 60_000), Dist(250, 0.4, 50, 1_000)
    ),
}

# Request mixes (share of requests per profile).
MIXES: dict[str, dict[str, float]] = {
    "launch_estimate": {"chat": 1.0},
    "month_after": {"chat": 0.88, "contract_qa": 0.12},
    "code_assistant": {"code_gen": 0.8, "chat": 0.2},
    "doc_summarizer": {"summarization": 0.9, "chat": 0.1},
}


@dataclass(frozen=True)
class Request:
    kind: str
    input_tokens: int
    output_tokens: int
    user: int = 0
    tenant: str = "default"


def validate_mix(mix: dict[str, float]) -> None:
    if not mix:
        raise ValueError("mix is empty")
    for k, v in mix.items():
        if k not in PROFILES:
            raise ValueError(f"unknown profile {k!r}")
        if v < 0 or math.isnan(v):
            raise ValueError("mix shares must be non-negative")
    if abs(sum(mix.values()) - 1.0) > 1e-9:
        raise ValueError("mix shares must sum to 1")


def sample_mix(mix: dict[str, float], n: int, seed: int = 1) -> list[Request]:
    validate_mix(mix)
    rng = random.Random(seed)
    kinds, weights = list(mix), list(mix.values())
    out = []
    for _ in range(n):
        k = rng.choices(kinds, weights)[0]
        p = PROFILES[k]
        out.append(Request(k, p.inp.sample(rng), p.out.sample(rng)))
    return out


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile, q in [0, 100]."""
    if not values:
        raise ValueError("no values")
    s = sorted(values)
    k = max(0, min(len(s) - 1, math.ceil(q / 100 * len(s)) - 1))
    return s[k]


def stats(values: list[float]) -> dict[str, float]:
    return {
        "mean": round(sum(values) / len(values), 1),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
    }


BINS = [0, 50, 200, 1_000, 4_000, 16_000, 64_000, 10**9]
BIN_LABELS = ["<50", "50-199", "200-999", "1K-4K", "4K-16K", "16K-64K", "64K+"]


def histogram(values: list[int]) -> list[int]:
    counts = [0] * (len(BINS) - 1)
    for v in values:
        for i in range(len(BINS) - 1):
            if BINS[i] <= v < BINS[i + 1]:
                counts[i] += 1
                break
    return counts


def svg_bars(title: str, labels: list[str], series: dict[str, list[float]], unit: str = "") -> str:
    """A small grouped bar chart as standalone SVG (no plotting library needed)."""
    colors = ["#2563eb", "#f59e0b", "#10b981", "#ef4444"]
    w, h, left, bottom, top = 760, 340, 60, 60, 40
    peak = max((v for vals in series.values() for v in vals), default=1) or 1
    group_w = (w - left - 20) / len(labels)
    bar_w = group_w * 0.8 / max(1, len(series))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="sans-serif" font-size="11">',
        f'<rect width="{w}" height="{h}" fill="white"/>',
        f'<text x="{w / 2}" y="20" text-anchor="middle" font-size="14">{escape(title)}</text>',
    ]
    plot_h = h - top - bottom
    for gi, label in enumerate(labels):
        gx = left + gi * group_w + group_w * 0.1
        for si, (_name, vals) in enumerate(series.items()):
            v = vals[gi]
            bh = plot_h * v / peak
            x, y = gx + si * bar_w, top + plot_h - bh
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w - 2:.1f}" height="{bh:.1f}" fill="{colors[si % 4]}"/>')
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{y - 3:.1f}" text-anchor="middle">{v:g}{unit}</text>')
        parts.append(f'<text x="{gx + group_w * 0.4:.1f}" y="{h - bottom + 16}" text-anchor="middle">{escape(label)}</text>')
    for si, name in enumerate(series):
        parts.append(f'<rect x="{left + si * 170}" y="{h - 24}" width="12" height="12" fill="{colors[si % 4]}"/>')
        parts.append(f'<text x="{left + si * 170 + 16}" y="{h - 14}">{escape(name)}</text>')
    parts.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{w - 20}" y2="{top + plot_h}" stroke="black"/>')
    parts.append("</svg>")
    return "\n".join(parts)
