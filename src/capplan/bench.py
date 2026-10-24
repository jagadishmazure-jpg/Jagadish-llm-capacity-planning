"""Every number in the README comes from here. ``capplan bench`` writes results.json."""

from __future__ import annotations

import random
from dataclasses import asdict

from . import corpus, tokens
from .capacity import Hardware, plan
from .cost import Prices, monthly_cost, request_cost, tokens_per_second
from .fixes import CapPolicy, DriftMonitor, TenantBudget, cap_request
from .simulator import TENANTS, Config, run
from .workloads import BIN_LABELS, MIXES, PROFILES, histogram, sample_mix, stats

PLAN_SAMPLE = 20_000
REQ_PER_DAY = 100 * 86_400


def talk_examples() -> dict:
    p = Prices()
    small = request_cost(20, 30, p)
    big = request_cost(8_000, 1_000, p)
    tin, tout = tokens_per_second(100, 4_000, 500)
    return {
        "small_request_usd": round(small, 7),
        "large_request_usd": round(big, 6),
        "large_over_small": round(big / small, 1),
        "input_tokens_per_s_at_100rps_4000in": tin,
        "output_tokens_per_s_at_100rps_500out": tout,
        "monthly_usd_100rps_4000in_500out": round(monthly_cost(100, 4_000, 500, p), 2),
    }


def ratio_study(prefer_bpe: bool = False) -> dict:
    out = {}
    for kind, texts in corpus.samples().items():
        words = sum(tokens.word_count(t) for t in texts)
        toks = sum(tokens.count(t, prefer_bpe) for t in texts)
        out[kind] = {"texts": len(texts), "words": words, "tokens": toks, "tokens_per_word": round(toks / words, 2)}
    return out


def workload_profiles() -> dict:
    out = {}
    for name in PROFILES:
        s = sample_mix({name: 1.0}, PLAN_SAMPLE, seed=3)
        ins, outs = [r.input_tokens for r in s], [r.output_tokens for r in s]
        out[name] = {"input": stats(ins), "output": stats(outs), "input_hist": histogram(ins), "output_hist": histogram(outs)}
    return out


def capacity_plans() -> dict:
    return {m: plan(100, sample_mix(mix, PLAN_SAMPLE, seed=5)).as_dict() for m, mix in MIXES.items()}


def exercise() -> dict:
    """The talk's homework: average input and output tokens for a few kinds of request."""
    rng = random.Random(21)
    texts = {
        "chat": [corpus.chat_message(rng) for _ in range(300)],
        "contract_qa": [corpus.contract(rng, rng.randint(20, 400)) + "\nWhat is the notice period?" for _ in range(300)],
        "code_gen": [corpus.code_file(rng, rng.randint(5, 60)) + "\n# add input validation" for _ in range(300)],
        "summarization": [corpus.article(rng, rng.randint(30, 300)) + "\nSummarise in five bullets." for _ in range(300)],
    }
    out = {}
    for kind, tx in texts.items():
        ins = [tokens.approx_tokens(t) for t in tx]
        outs = [r.output_tokens for r in sample_mix({kind: 1.0}, len(tx), seed=22)]
        mean_in, mean_out = sum(ins) / len(ins), sum(outs) / len(outs)
        out[kind] = {
            "requests": len(tx),
            "avg_input_tokens": round(mean_in, 1),
            "avg_output_tokens": round(mean_out, 1),
            "p99_input_tokens": stats(ins)["p99"],
            "avg_cost_usd": round(request_cost(mean_in, mean_out), 6),
            "output_share_of_cost_pct": round(100 * mean_out * 1.5 / (mean_in * 0.5 + mean_out * 1.5), 1),
        }
    return out


def scenarios() -> dict:
    after = dict(MIXES["month_after"])
    launch = plan(100, sample_mix(MIXES["launch_estimate"], PLAN_SAMPLE, seed=5))
    incident_plan = plan(100, sample_mix(after, PLAN_SAMPLE, seed=5))
    capped = [cap_request(r, CapPolicy())[0] for r in sample_mix(after, PLAN_SAMPLE, seed=5)]
    capped_plan = plan(100, capped)
    hw = Hardware()
    fleet = launch.replicas
    global_rate = round(fleet * hw.prefill_tokens_per_s * 0.6)
    runs = {
        "1_launch": Config(replicas=fleet),
        "2_incident": Config(mix=after, replicas=fleet),
        "3_incident_token_planned_fleet": Config(mix=after, replicas=incident_plan.replicas),
        "4_caps_rag_max_tokens": Config(mix=after, replicas=fleet, caps=CapPolicy()),
        "5_fair_share_only": Config(mix=after, replicas=fleet, fair_share=True),
        "6_caps_plus_fair_share": Config(mix=after, replicas=fleet, caps=CapPolicy(), fair_share=True),
        "7_per_user_token_bucket_only": Config(mix=after, replicas=fleet, per_user_tokens_per_s=500),
        "8_all_fixes": Config(
            mix=after, replicas=fleet, caps=CapPolicy(), per_user_tokens_per_s=500, global_tokens_per_s=global_rate, fair_share=True
        ),
        "9_caps_on_replanned_fleet": Config(mix=after, replicas=capped_plan.replicas, caps=CapPolicy()),
    }
    out = {k: run(c) for k, c in runs.items()}
    base, inc = out["1_launch"], out["2_incident"]
    return {
        "fleet_from_launch_plan": fleet,
        "replicas_token_planned": incident_plan.replicas,
        "replicas_after_caps": capped_plan.replicas,
        "global_tokens_per_s_limit": global_rate,
        "runs": out,
        "incident_bill_multiplier": round(inc["monthly_api_usd"] / base["monthly_api_usd"], 1),
        "incident_p99_multiplier": round(inc["latency_s"]["p99"] / base["latency_s"]["p99"], 1),
        "incident_avg_input_multiplier": round(inc["avg_input_tokens"] / base["avg_input_tokens"], 1),
    }


def share_sweep() -> list[dict]:
    """How large a share of whole-contract requests produces a given bill multiplier."""
    base = plan(100, sample_mix(MIXES["launch_estimate"], PLAN_SAMPLE, seed=5)).monthly_api_usd
    rows = []
    for pct in (0, 2, 5, 10, 12, 20, 30, 40):
        mix = {"chat": 1 - pct / 100, "contract_qa": pct / 100} if pct else {"chat": 1.0}
        p = plan(100, sample_mix(mix, PLAN_SAMPLE, seed=5))
        rows.append(
            {
                "contract_share_pct": pct,
                "avg_input_tokens": p.input_tokens["mean"],
                "bill_multiplier": round(p.monthly_api_usd / base, 1),
                "replicas": p.replicas,
            }
        )
    return rows


def month_monitoring() -> dict:
    """A simulated month: contract share ramps from 0% to 12% over the first 10 days."""
    base_sample = sample_mix(MIXES["launch_estimate"], PLAN_SAMPLE, seed=5)
    baseline_tokens = sum(r.input_tokens + r.output_tokens for r in base_sample) / len(base_sample)
    estimate = plan(100, base_sample).monthly_api_usd
    mon = DriftMonitor(baseline_tokens, window=500, ratio=2.0)
    tenant_budgets = {t: TenantBudget(estimate / len(TENANTS)) for t in TENANTS}
    stopped: dict[str, int] = {}
    drift_alert = None
    budget_alert_day: dict[int, int] = {}
    seen = 0
    spent = 0.0
    for day in range(1, 31):
        share = min(0.12, 0.12 * (day - 1) / 9)
        mix = {"chat": 1 - share, "contract_qa": share} if share else {"chat": 1.0}
        reqs = sample_mix(mix, 2_000, seed=100 + day)
        for r in reqs:
            seen += 1
            if mon.observe(r) and drift_alert is None:
                drift_alert = {"day": day, "sampled_request": seen, "rolling_mean_tokens": round(mon.mean, 1)}
        scale = REQ_PER_DAY / len(reqs)
        day_cost = sum(request_cost(r.input_tokens, r.output_tokens) for r in reqs) * scale
        spent += day_cost
        for level in (50, 80, 100):
            if spent >= estimate * level / 100 and level not in budget_alert_day:
                budget_alert_day[level] = day
        # per tenant: whole-contract traffic belongs to one tenant, chat is spread evenly
        per_t = {t: 0.0 for t in TENANTS}
        for r in reqs:
            c = request_cost(r.input_tokens, r.output_tokens) * scale
            if r.kind == "chat":
                for t in TENANTS:
                    per_t[t] += c / len(TENANTS)
            else:
                per_t[TENANTS[0]] += c
        for t, c in per_t.items():
            if t not in stopped and not tenant_budgets[t].charge_usd(c):
                stopped[t] = day
    return {
        "baseline_tokens_per_request": round(baseline_tokens, 1),
        "monthly_estimate_usd": estimate,
        "drift_alert": drift_alert,
        "global_budget_alert_day": {str(k): v for k, v in sorted(budget_alert_day.items())},
        "tenant_hard_stop_day": stopped,
        "tenants_never_stopped": [t for t in TENANTS if t not in stopped],
        "month_bill_usd_without_fixes": round(spent, 2),
        "month_bill_multiplier": round(spent / estimate, 1),
    }


def all_results() -> dict:
    return {
        "prices": asdict(Prices()),
        "hardware": {**asdict(Hardware()), "kv_capacity_tokens": Hardware().kv_capacity_tokens},
        "talk_examples": talk_examples(),
        "ratio_study_approx": ratio_study(False),
        "workloads": workload_profiles(),
        "hist_bins": BIN_LABELS,
        "capacity_plans": capacity_plans(),
        "share_sweep": share_sweep(),
        "scenarios": scenarios(),
        "month": month_monitoring(),
        "exercise": exercise(),
    }
