"""Combined evidence board for the capacity-planning incident, drawn only from the committed results.json.

python scripts/evidence_board.py          # writes docs/img/evidence_board.png and docs/evidence_board.json
python scripts/evidence_board.py --check  # re-renders to a temp file; fails if docs/evidence_board.json drifts

Labels: panels (a)-(c) are simulated (seeded fleet simulator and planner, illustrative prices). Panel (d) input
tokens are measured with the offline token counter on synthetic texts; outputs are sampled from the profiles.
The 80x reference line is quoted from the source talk, for comparison only. PNG bytes vary by font and
platform, so the JSON is what CI compares. Needs the optional "board" extra (matplotlib).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results.json"
PNG = ROOT / "docs/img/evidence_board.png"
JSON = ROOT / "docs/evidence_board.json"
QUOTED_TALK_BILL_MULTIPLIER = 80  # the talk's figure, shown as a reference line only
SCENARIOS = {
    "1_launch": "1\nlaunch",
    "2_incident": "2\nincident",
    "3_incident_token_planned_fleet": "3 planned\nfleet",
    "5_fair_share_only": "5 fair\nshare",
    "6_caps_plus_fair_share": "6 caps +\nfair share",
    "8_all_fixes": "8 all fixes",
    "9_caps_on_replanned_fleet": "9 caps,\nreplanned",
}


def numbers(r: dict | None = None) -> dict:
    r = r if r is not None else json.loads(RESULTS.read_text())
    runs = r["scenarios"]["runs"]
    m = r["month"]
    return {
        "note": "Copied from results.json. (a)-(c) simulated; (d) inputs measured with the offline counter, "
        "outputs sampled; the 80x line is quoted from the talk. Prices illustrative " + r["prices"]["as_of"] + ".",
        "a_share_sweep": [{k: p[k] for k in ("contract_share_pct", "bill_multiplier", "replicas")} for p in r["share_sweep"]],
        "a_quoted_talk_multiplier": QUOTED_TALK_BILL_MULTIPLIER,
        "b_chat_p99_s": {k: runs[k]["chat_latency_s"]["p99"] for k in SCENARIOS},
        "b_replicas": {k: runs[k]["replicas"] for k in SCENARIOS},
        "c_monthly_api_usd": {k: runs[k]["monthly_api_usd"] for k in SCENARIOS},
        "c_month": {
            "estimate_usd": m["monthly_estimate_usd"],
            "without_fixes_usd": m["month_bill_usd_without_fixes"],
            "multiplier": m["month_bill_multiplier"],
            "drift_alert_day": m["drift_alert"]["day"],
        },
        "d_exercise": {
            k: {f: v[f] for f in ("avg_input_tokens", "avg_output_tokens", "output_share_of_cost_pct")} for k, v in r["exercise"].items()
        },
    }


def draw(n: dict, path: Path) -> None:
    import logging

    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["text.parse_math"] = False
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    red, green, grey = "#d62728", "#2ca02c", "#bbbbbb"
    fig, ax = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(
        "Brightdesk (Kestrel Lane Software): same 100 RPS, very different tokens - simulated, labels per panel",
        fontsize=15,
    )
    # (a) share sweep
    sw = n["a_share_sweep"]
    xs = [p["contract_share_pct"] for p in sw]
    ax[0, 0].plot(xs, [p["bill_multiplier"] for p in sw], marker="o", color=red, label="bill multiplier (simulated)")
    for p in sw:
        ax[0, 0].annotate(
            f"{p['bill_multiplier']}x / {p['replicas']} rep",
            (p["contract_share_pct"], p["bill_multiplier"]),
            textcoords="offset points",
            xytext=(-10, 8),
            fontsize=8,
        )
    ax[0, 0].axhline(n["a_quoted_talk_multiplier"], color="grey", linestyle="--", label=f"talk's {n['a_quoted_talk_multiplier']}x (quoted)")
    ax[0, 0].set_xlabel("% of requests that paste a whole contract")
    ax[0, 0].set_ylabel("monthly bill vs launch estimate")
    ax[0, 0].legend(fontsize=8, loc="upper left")
    ax[0, 0].set_title("(a) bill and replicas grow with contract share (simulated)")
    # (b) chat p99
    keys = list(SCENARIOS)
    labels = [SCENARIOS[k] for k in keys]
    p99 = [n["b_chat_p99_s"][k] for k in keys]
    colours = [green if v < 10 else red for v in p99]
    ax[0, 1].bar(labels, p99, color=colours)
    for i, k in enumerate(keys):
        ax[0, 1].text(i, p99[i] * 1.15, f"{p99[i]:,.1f}s\n{n['b_replicas'][k]} rep", ha="center", fontsize=8)
    ax[0, 1].set_yscale("log")
    ax[0, 1].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax[0, 1].set_ylim(0.5, max(p99) * 6)
    ax[0, 1].tick_params(axis="x", labelsize=8)
    ax[0, 1].set_ylabel("chat p99 seconds (log)")
    ax[0, 1].set_title("(b) chat p99 per scenario (simulated, 60 s at 100 RPS)")
    # (c) monthly bill
    bills = [n["c_monthly_api_usd"][k] / 1000 for k in keys]
    ax[1, 0].bar(labels, bills, color=[grey if b < 100 else red for b in bills])
    for i, b in enumerate(bills):
        ax[1, 0].text(i, b + 8, f"${b:,.0f}k", ha="center", fontsize=8)
    cm = n["c_month"]
    ax[1, 0].text(
        3.6,
        max(bills) * 0.75,
        f"simulated month, no fixes: ${cm['without_fixes_usd']:,.0f}\n= {cm['multiplier']}x the "
        f"${cm['estimate_usd']:,.0f} estimate;\ntoken-drift alert fires on day {cm['drift_alert_day']}",
        fontsize=9,
        ha="left",
    )
    ax[1, 0].set_ylim(0, max(bills) * 1.2)
    ax[1, 0].tick_params(axis="x", labelsize=8)
    ax[1, 0].set_ylabel("monthly API bill, $k (illustrative prices)")
    ax[1, 0].set_title("(c) monthly API bill per scenario (simulated)")
    # (d) exercise
    ex = n["d_exercise"]
    names = list(ex)
    import numpy as np

    x = np.arange(len(names))
    ax[1, 1].bar(x - 0.2, [ex[k]["avg_input_tokens"] for k in names], width=0.4, color="#8da0cb", label="avg input (measured)")
    ax[1, 1].bar(x + 0.2, [ex[k]["avg_output_tokens"] for k in names], width=0.4, color="#fc8d62", label="avg output (sampled)")
    for i, k in enumerate(names):
        ax[1, 1].text(
            i, ex[k]["avg_input_tokens"] * 1.2 + 1, f"output = {ex[k]['output_share_of_cost_pct']}%\nof cost", ha="center", fontsize=8
        )
    ax[1, 1].set_yscale("log")
    ax[1, 1].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax[1, 1].set_ylim(1, 60000)
    ax[1, 1].set_xticks(x, names)
    ax[1, 1].set_ylabel("tokens per request (log)")
    ax[1, 1].legend(fontsize=8, loc="upper left")
    ax[1, 1].set_title("(d) the exercise: 300 requests per type")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def main(argv: list[str]) -> int:
    n = numbers()
    js = json.dumps(n, indent=2) + "\n"
    if "--check" in argv:
        tmp = ROOT / "evidence_board.check.png"
        draw(n, tmp)
        tmp.unlink()
        if not JSON.exists() or JSON.read_text() != js:
            print("drift: docs/evidence_board.json - run python scripts/evidence_board.py")
            return 1
        print("evidence board numbers up to date; figure renders")
        return 0
    JSON.write_text(js)
    draw(n, PNG)
    print(f"wrote {PNG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
