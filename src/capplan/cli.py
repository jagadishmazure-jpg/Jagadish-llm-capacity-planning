"""capplan - command line.

capplan count FILE...                  tokens and words in text files
capplan estimate --rps 100 --mix chat=0.88,contract_qa=0.12 [--input-price 0.5 --output-price 1.5]
capplan estimate --rps 100 --avg-input 4000 --avg-output 500
capplan simulate --mix month_after [--fixes]
capplan bench [--write results.json | --check results.json]
capplan charts                          regenerate docs/charts/*.svg
capplan demo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bench, tokens
from .capacity import plan
from .cost import Prices, monthly_cost, tokens_per_second
from .fixes import CapPolicy
from .simulator import Config, run
from .workloads import MIXES, PROFILES, sample_mix


def _mix(text: str) -> dict[str, float]:
    if text in MIXES:
        return dict(MIXES[text])
    out = {}
    for part in text.split(","):
        k, _, v = part.partition("=")
        out[k.strip()] = float(v)
    return out


def _estimate(a) -> int:
    prices = Prices(a.input_price, a.output_price)
    if a.avg_input is not None:
        tin, tout = tokens_per_second(a.rps, a.avg_input, a.avg_output or 0)
        print(f"input tokens/s:  {tin:,.0f}\noutput tokens/s: {tout:,.0f}")
        print(f"monthly bill:    ${monthly_cost(a.rps, a.avg_input, a.avg_output or 0, prices):,.2f}")
        return 0
    p = plan(a.rps, sample_mix(_mix(a.mix), a.samples, seed=a.seed), prices=prices)
    d = p.as_dict()
    if a.json:
        print(json.dumps(d, indent=2))
        return 0
    print(f"RPS {a.rps} with mix {a.mix} ({a.samples:,} sampled requests)")
    for k in ("input_tokens", "output_tokens", "service_latency_s", "cost_per_request"):
        v = d[k]
        print(f"  {k:<22} " + "  ".join(f"{q}={v[q]}" for q in ("p50", "p95", "p99")) + (f"  mean={v['mean']}" if "mean" in v else ""))
    print(f"  prefill tokens/s       {p.prefill_tokens_per_s:,}")
    print(f"  decode tokens/s        {p.decode_tokens_per_s:,}")
    print(f"  KV cache in use        {p.kv_cache_gb} GB")
    print(
        f"  replicas               {p.replicas} "
        f"(prefill {p.replicas_by_prefill}, decode {p.replicas_by_decode}, memory {p.replicas_by_memory})"
    )
    print(f"  monthly API bill       ${p.monthly_api_usd:,.2f}")
    print(f"  monthly GPU bill       ${p.monthly_gpu_usd:,.2f} (self-hosted, simulated rate)")
    return 0


def _charts(results: dict, out: Path) -> list[Path]:
    from .workloads import svg_bars

    out.mkdir(parents=True, exist_ok=True)
    labels = results["hist_bins"]
    files = []
    for name, w in results["workloads"].items():
        f = out / f"hist_{name}.svg"
        f.write_text(svg_bars(f"{name}: requests per token-count bucket", labels, {"input": w["input_hist"], "output": w["output_hist"]}))
        files.append(f)
    ex = results["exercise"]
    f = out / "exercise_avg_tokens.svg"
    f.write_text(
        svg_bars(
            "Exercise: average tokens per request",
            list(ex),
            {"avg input": [v["avg_input_tokens"] for v in ex.values()], "avg output": [v["avg_output_tokens"] for v in ex.values()]},
        )
    )
    files.append(f)
    sw = results["share_sweep"]
    f = out / "bill_multiplier_by_contract_share.svg"
    f.write_text(
        svg_bars(
            "Bill multiplier vs share of whole-contract requests",
            [f"{r['contract_share_pct']}%" for r in sw],
            {"x launch bill": [r["bill_multiplier"] for r in sw]},
        )
    )
    files.append(f)
    runs = results["scenarios"]["runs"]
    f = out / "chat_p99_by_scenario.svg"
    f.write_text(
        svg_bars(
            "Chat p99 latency (s) by scenario",
            [k.split("_", 1)[0] for k in runs],
            {"chat p99 s": [v["chat_latency_s"]["p99"] for v in runs.values()]},
        )
    )
    files.append(f)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="capplan", description="Plan LLM capacity and cost from tokens, not requests.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("count")
    c.add_argument("files", nargs="+")
    c.add_argument("--bpe", action="store_true", help="use tiktoken cl100k_base if available")
    e = sub.add_parser("estimate")
    e.add_argument("--rps", type=float, required=True)
    e.add_argument("--mix", default="launch_estimate", help=f"named mix ({', '.join(MIXES)}) or k=v,... over {', '.join(PROFILES)}")
    e.add_argument("--avg-input", type=float)
    e.add_argument("--avg-output", type=float)
    e.add_argument("--input-price", type=float, default=0.50)
    e.add_argument("--output-price", type=float, default=1.50)
    e.add_argument("--samples", type=int, default=20_000)
    e.add_argument("--seed", type=int, default=5)
    e.add_argument("--json", action="store_true")
    s = sub.add_parser("simulate")
    s.add_argument("--mix", default="month_after")
    s.add_argument("--rps", type=float, default=100)
    s.add_argument("--replicas", type=int, default=3)
    s.add_argument("--duration", type=float, default=60)
    s.add_argument("--fixes", action="store_true")
    b = sub.add_parser("bench")
    g = b.add_mutually_exclusive_group()
    g.add_argument("--write")
    g.add_argument("--check")
    sub.add_parser("charts")
    sub.add_parser("demo")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "count":
            for f in a.files:
                t = Path(f).read_text(errors="ignore")
                print(f"{f}: words={tokens.word_count(t)} tokens={tokens.count(t, a.bpe)}")
            return 0
        if a.cmd == "estimate":
            return _estimate(a)
        if a.cmd == "simulate":
            extra = {"caps": CapPolicy(), "fair_share": True} if a.fixes else {}
            r = run(Config(rps=a.rps, mix=_mix(a.mix), replicas=a.replicas, duration_s=a.duration, **extra))
            print(json.dumps(r, indent=2))
            return 0
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    if a.cmd == "bench":
        r = bench.all_results()
        if a.check:
            old = json.loads(Path(a.check).read_text())
            if old != json.loads(json.dumps(r)):
                diff = [k for k in r if json.loads(json.dumps(r[k])) != old.get(k)]
                print(f"results differ from {a.check} in: {diff}", file=sys.stderr)
                return 1
            print(f"bench matches {a.check}")
            return 0
        text = json.dumps(r, indent=1)
        if a.write:
            Path(a.write).write_text(text + "\n")
            print(f"wrote {a.write}")
        else:
            print(text)
        return 0
    if a.cmd == "charts":
        r = json.loads(Path("results.json").read_text())
        for f in _charts(r, Path("docs/charts")):
            print(f"wrote {f}")
        return 0
    if a.cmd == "demo":
        print("Talk example: 20 in / 30 out vs 8,000 in / 1,000 out")
        print(json.dumps(bench.talk_examples(), indent=2))
        for m in ("launch_estimate", "month_after"):
            print(f"\n== {m} ==")
            _estimate(
                argparse.Namespace(
                    rps=100, mix=m, avg_input=None, avg_output=None, input_price=0.5, output_price=1.5, samples=20_000, seed=5, json=False
                )
            )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
