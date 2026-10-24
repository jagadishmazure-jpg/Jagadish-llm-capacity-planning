import json
from pathlib import Path

from capplan import bench
from capplan.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_estimate_avg(capsys):
    assert main(["estimate", "--rps", "100", "--avg-input", "4000", "--avg-output", "500"]) == 0
    out = capsys.readouterr().out
    assert "400,000" in out and "50,000" in out


def test_estimate_mix_json(capsys):
    assert main(["estimate", "--rps", "10", "--mix", "chat=0.5,code_gen=0.5", "--samples", "500", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["rps"] == 10


def test_estimate_rejects_negative_price(capsys):
    assert main(["estimate", "--rps", "1", "--avg-input", "1", "--avg-output", "1", "--input-price", "-1"]) == 2
    assert "must not be negative" in capsys.readouterr().err


def test_estimate_rejects_bad_mix(capsys):
    assert main(["estimate", "--rps", "1", "--mix", "chat=0.4"]) == 2


def test_count(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("hello world")
    assert main(["count", str(f)]) == 0
    assert "tokens=2" in capsys.readouterr().out


def test_simulate_short(capsys):
    assert main(["simulate", "--mix", "launch_estimate", "--duration", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["served"] > 0


def test_talk_examples():
    t = bench.talk_examples()
    assert t["large_over_small"] == 100.0 and t["input_tokens_per_s_at_100rps_4000in"] == 400_000


def test_exercise_has_four_scenarios():
    e = bench.exercise()
    assert set(e) == {"chat", "contract_qa", "code_gen", "summarization"}
    assert e["contract_qa"]["avg_input_tokens"] > 100 * e["chat"]["avg_input_tokens"]


def test_committed_results_have_expected_sections():
    r = json.loads((ROOT / "results.json").read_text())
    for k in ("talk_examples", "workloads", "capacity_plans", "scenarios", "month", "exercise", "share_sweep"):
        assert k in r


def test_committed_incident_multiplier_is_measured_not_forced():
    r = json.loads((ROOT / "results.json").read_text())["scenarios"]
    runs = r["runs"]
    assert r["incident_bill_multiplier"] == round(runs["2_incident"]["monthly_api_usd"] / runs["1_launch"]["monthly_api_usd"], 1)


def test_month_drift_alert_before_budget_alert():
    r = json.loads((ROOT / "results.json").read_text())["month"]
    assert r["drift_alert"]["day"] < r["global_budget_alert_day"]["50"]


def test_charts_committed():
    names = {p.name for p in (ROOT / "docs" / "charts").glob("*.svg")}
    assert {"hist_chat.svg", "exercise_avg_tokens.svg", "chat_p99_by_scenario.svg"} <= names
