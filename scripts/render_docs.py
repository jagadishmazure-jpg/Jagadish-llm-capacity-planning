"""Regenerate the README results block and docs/results.md from results.json and the real test count.

python scripts/render_docs.py          # rewrite
python scripts/render_docs.py --check  # fail if committed docs are stale (CI)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from count_tests import count  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
START, END = "<!-- results:start -->", "<!-- results:end -->"
LABELS = {
    "1_launch": "1. Launch: chat-only mix, 3 replicas (the estimate)",
    "2_incident": "2. Incident: same RPS, 12% whole contracts, same 3 replicas",
    "3_incident_token_planned_fleet": "3. Incident mix on the token-planned fleet",
    "4_caps_rag_max_tokens": "4. Input cap + retrieval + max_tokens (3 replicas)",
    "5_fair_share_only": "5. Fair-share admission only (3 replicas)",
    "6_caps_plus_fair_share": "6. Caps + fair share (3 replicas)",
    "7_per_user_token_bucket_only": "7. Per-user token bucket only (3 replicas)",
    "8_all_fixes": "8. Caps + per-user and global token buckets + fair share (3 replicas)",
    "9_caps_on_replanned_fleet": "9. Caps on the fleet the planner sizes after caps",
}


def money(x: float) -> str:
    return f"${x:,.0f}"


def block(r: dict, tests: int) -> str:
    t, s, m = r["talk_examples"], r["scenarios"], r["month"]
    runs = s["runs"]
    rows = []
    for k, label in LABELS.items():
        v = runs[k]
        rej = sum(v["rejected"].values()) - v["rejected"]["rps"]
        rows.append(
            f"| {label} | {v['replicas']} | {v['avg_input_tokens']:,} | {money(v['monthly_api_usd'])} | "
            f"{v['latency_s']['p99']} | {v['chat_latency_s']['p50']} / {v['chat_latency_s']['p99']} | {rej} |"
        )
    plans = r["capacity_plans"]
    prow = "\n".join(
        f"| {k} | {p['input_tokens']['mean']:,} / {p['input_tokens']['p99']:,} | {p['output_tokens']['mean']:,} / {p['output_tokens']['p99']:,} | "
        f"{p['prefill_tokens_per_s']:,} | {p['decode_tokens_per_s']:,} | {p['kv_cache_gb']} | {p['replicas']} | {money(p['monthly_api_usd'])} | "
        f"{money(p['monthly_gpu_usd'])} |"
        for k, p in plans.items()
    )
    ex = "\n".join(
        f"| {k} | {v['requests']} | {v['avg_input_tokens']:,} | {v['avg_output_tokens']:,} | {v['p99_input_tokens']:,} | ${v['avg_cost_usd']:.6f} | {v['output_share_of_cost_pct']}% |"
        for k, v in r["exercise"].items()
    )
    sweep = " | ".join(f"{x['contract_share_pct']}%: {x['bill_multiplier']}x" for x in r["share_sweep"])
    ga = m["global_budget_alert_day"]
    return f"""{START}
**Tests: {tests}** (pytest, all passing). Every number below is produced by `capplan bench` from seeded
simulations and checked in CI against `results.json`. The models, GPUs and prices are simulated or
illustrative; the point is the method and the ratios, not the dollar amounts.

**The talk's arithmetic, recomputed.** 20 in / 30 out costs ${t["small_request_usd"]:.6f}; 8,000 in / 1,000 out costs
${t["large_request_usd"]:.4f}, **{t["large_over_small"]}x** more. 100 RPS x 4,000 input = {t["input_tokens_per_s_at_100rps_4000in"]:,.0f} input
tokens/s and x 500 output = {t["output_tokens_per_s_at_100rps_500out"]:,.0f} output tokens/s.

**The incident, reproduced (60 s of traffic at 100 RPS, measured, not forced).** Same request rate, same users,
average input up **{s["incident_avg_input_multiplier"]}x**, monthly bill up **{s["incident_bill_multiplier"]}x**, p99 latency up
**{s["incident_p99_multiplier"]}x** (from {runs["1_launch"]["latency_s"]["p99"]} s to {runs["2_incident"]["latency_s"]["p99"]} s, a
queue that keeps growing for as long as the mix stays shifted). The talk's 80x needs about 30-40% whole-contract
traffic in this model: {sweep}.

| Scenario | Replicas | Avg input tokens | Monthly API bill | p99 all (s) | Chat p50 / p99 (s) | Rejected by token limits |
| --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(rows)}

**Capacity plans at 100 RPS** (20,000 sampled requests each; mean / p99 tokens):

| Mix | Input | Output | Prefill tok/s | Decode tok/s | KV cache GB | Replicas | API bill / month | GPU bill / month |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
{prow}

**Monitoring over a simulated month** (contract share ramps 0% to 12% over 10 days): the token-drift monitor
fires on day {m["drift_alert"]["day"]} (rolling mean {m["drift_alert"]["rolling_mean_tokens"]} tokens vs a {m["baseline_tokens_per_request"]} baseline);
the spend alerts fire at 50% on day {ga["50"]}, 80% on day {ga["80"]} and 100% on day {ga["100"]}; per-tenant budgets hard-stop
{", ".join(f"{k} on day {v}" for k, v in m["tenant_hard_stop_day"].items())} while {", ".join(m["tenants_never_stopped"])} never stop.
Without any fix the month would cost {money(m["month_bill_usd_without_fixes"])}, **{m["month_bill_multiplier"]}x** the estimate.

**The talk's exercise** (inputs measured with the offline token counter on synthetic texts; outputs sampled from the profiles):

| Request type | Requests | Avg input | Avg output | p99 input | Avg cost | Output share of cost |
| --- | --- | --- | --- | --- | --- | --- |
{ex}
{END}"""


def render(check: bool) -> int:
    r = json.loads((ROOT / "results.json").read_text())
    b = block(r, count())
    stale = []
    readme = ROOT / "README.md"
    text = readme.read_text()
    new = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _m: b, text, flags=re.S)
    res = ROOT / "docs" / "results.md"
    new_res = "# Results\n\nGenerated by `python scripts/render_docs.py` from `results.json`. Do not edit by hand.\n\n" + b + "\n"
    exf = ROOT / "docs" / "exercise.md"
    ex_rows = "\n".join(
        f"| {k} | {v['requests']} | {v['avg_input_tokens']:,} | {v['avg_output_tokens']:,} | {v['p99_input_tokens']:,} | "
        f"${v['avg_cost_usd']:.6f} | {v['output_share_of_cost_pct']}% |"
        for k, v in r["exercise"].items()
    )
    ex_block = (
        "<!-- exercise:start -->\n| Request type | Requests | Avg input tokens | Avg output tokens | p99 input | Avg cost | "
        "Output share of cost |\n| --- | --- | --- | --- | --- | --- | --- |\n" + ex_rows + "\n<!-- exercise:end -->"
    )
    new_ex = re.sub(r"<!-- exercise:start -->.*?<!-- exercise:end -->", lambda _m: ex_block, exf.read_text(), flags=re.S)
    for path, content in ((readme, new), (res, new_res), (exf, new_ex)):
        if not path.exists() or path.read_text() != content:
            stale.append(str(path.relative_to(ROOT)))
            if not check:
                path.write_text(content)
    if check and stale:
        print("stale docs (run python scripts/render_docs.py):", ", ".join(stale))
        return 1
    print("docs up to date" if check else f"rendered {stale or 'nothing'}")
    return 0


if __name__ == "__main__":
    sys.exit(render("--check" in sys.argv))
