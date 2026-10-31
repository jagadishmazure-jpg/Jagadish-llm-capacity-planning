import copy
import json
import math
from pathlib import Path

import pytest
import yaml

from capplan import hosting as h
from capplan.cli import main

ROOT = Path(__file__).resolve().parents[1]
RAW = yaml.safe_load((ROOT / "assumptions" / "hosting.yaml").read_text())


@pytest.fixture
def raw():
    return copy.deepcopy(RAW)


@pytest.fixture
def a():
    return h.load()


def by_name(report, name):
    return next(o for o in report["options"] if o["name"] == name)


# ------------------------------------------------------------- labelled assumptions


def _leaves(node, path=""):
    if isinstance(node, dict) and "value" in node:
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, f"{path}.{k}" if path else k)


def test_every_number_in_the_yaml_is_labelled():
    leaves = list(_leaves(RAW))
    assert len(leaves) > 30
    assert all(n["basis"] in {"example", "reference"} for _, n in leaves)


def test_every_reference_number_has_a_date():
    refs = [(p, n) for p, n in _leaves(RAW) if n["basis"] == "reference"]
    assert len(refs) == 4
    for _, n in refs:
        assert n["as_of"] and n.get("note")


def test_reference_values_listed_in_report(a):
    refs = h.report(a)["reference_values"]
    assert {r["field"] for r in refs} == {p for p, n in _leaves(RAW) if n["basis"] == "reference"}


def test_no_price_forecast_words_in_yaml():
    text = (ROOT / "assumptions" / "hosting.yaml").read_text().lower()
    for word in ("btc price", "price target", "will reach", "buy ", "sell "):
        assert word not in text


def test_bare_number_rejected(raw):
    raw["utilisation"] = 0.6
    with pytest.raises(h.AssumptionError, match="bare number"):
        h.parse(raw)


def test_missing_basis_rejected(raw):
    del raw["utilisation"]["basis"]
    with pytest.raises(h.AssumptionError, match="basis"):
        h.parse(raw)


def test_unknown_basis_rejected(raw):
    raw["utilisation"]["basis"] = "guess"
    with pytest.raises(h.AssumptionError, match="basis"):
        h.parse(raw)


def test_reference_without_date_rejected_on_top_level_field(raw):
    raw["utilisation"]["basis"] = "reference"
    with pytest.raises(h.AssumptionError, match="as_of"):
        h.parse(raw)


def test_extra_link_key_on_reference_rejected(raw):
    raw["options"]["colo_converted_site"]["pue"] = {"value": 1.2, "basis": "reference", "as_of": "2024", "link": "x"}
    with pytest.raises(h.AssumptionError, match="unknown keys"):
        h.parse(raw)


def test_unknown_top_level_key_rejected(raw):
    raw["discount"] = {"value": 1, "basis": "example"}
    with pytest.raises(h.AssumptionError, match="unknown top-level"):
        h.parse(raw)


def test_unknown_option_key_rejected(raw):
    raw["options"]["cloud_on_demand"]["spot_discount"] = {"value": 0.5, "basis": "example"}
    with pytest.raises(h.AssumptionError, match="unknown keys"):
        h.parse(raw)


def test_missing_option_key_rejected(raw):
    del raw["options"]["colo_converted_site"]["pue"]
    with pytest.raises(h.AssumptionError, match="missing keys"):
        h.parse(raw)


def test_unknown_leaf_key_rejected(raw):
    raw["utilisation"]["confidence"] = "high"
    with pytest.raises(h.AssumptionError, match="unknown keys"):
        h.parse(raw)


def test_bad_kind_rejected(raw):
    raw["options"]["cloud_on_demand"]["kind"] = "spot"
    with pytest.raises(h.AssumptionError, match="kind"):
        h.parse(raw)


def test_missing_label_rejected(raw):
    del raw["options"]["cloud_on_demand"]["label"]
    with pytest.raises(h.AssumptionError, match="label"):
        h.parse(raw)


@pytest.mark.parametrize(
    ("path", "value", "msg"),
    [
        (("utilisation",), 0, "below"),
        (("utilisation",), 1.2, "above"),
        (("options", "colo_converted_site", "pue"), 0.9, "below"),
        (("options", "colo_converted_site", "electricity_usd_per_kwh"), -0.01, "below"),
        (("options", "cloud_on_demand", "gpus"), 2.5, "whole number"),
        (("options", "cloud_on_demand", "usd_per_gpu_hour"), float("nan"), "finite"),
        (("options", "cloud_on_demand", "usd_per_gpu_hour"), True, "must be a number"),
        (("options", "cloud_on_demand", "usd_per_gpu_hour"), "4", "must be a number"),
        (("options", "colo_converted_site", "amortisation_years"), 0, "below"),
        (("halving", "fee_share_of_revenue"), 1.5, "above"),
    ],
)
def test_out_of_range_values_rejected(raw, path, value, msg):
    node = raw
    for k in path:
        node = node[k]
    node["value"] = value
    with pytest.raises(h.AssumptionError, match=msg):
        h.parse(raw)


def test_server_larger_than_rack_rejected(raw):
    raw["options"]["colo_converted_site"]["rack_kw_limit"]["value"] = 5
    with pytest.raises(h.AssumptionError, match="does not fit"):
        h.report(h.parse(raw))


def test_no_site_option_rejected(raw):
    raw["options"]["colo_converted_site"]["colo_usd_per_kw_month"]["value"] = 0
    with pytest.raises(h.AssumptionError, match="no owned option"):
        h.report(h.parse(raw))


# ------------------------------------------------------------- the maths


def test_annuity_straight_line_when_rate_zero():
    assert h.annuity_per_month(120_000, 0, 5) == pytest.approx(2000)


def test_annuity_matches_textbook_formula():
    r, n, p = 0.08, 4, 300_000
    assert h.annuity_per_month(p, r, n) * 12 == pytest.approx(p * r / (1 - (1 + r) ** -n))


def test_annuity_costs_more_than_straight_line():
    assert h.annuity_per_month(300_000, 0.08, 4) > h.annuity_per_month(300_000, 0, 4)


def test_annuity_zero_capex():
    assert h.annuity_per_month(0, 0.08, 4) == 0


def test_api_blended_price(a):
    assert a.api_blended_usd_per_m == pytest.approx(0.8 * 0.5 + 0.2 * 1.5)


def test_cloud_monthly_cost_by_hand(a):
    o = a.option("cloud_on_demand")
    assert h.evaluate(o, a).monthly_usd == pytest.approx(8 * 4.0 * 730 + 1500)


def test_cloud_cost_independent_of_utilisation_when_always_on(a):
    o = a.option("cloud_on_demand")
    assert h.evaluate(o, a, 0.2).monthly_usd == h.evaluate(o, a, 0.9).monthly_usd


def test_colo_electricity_by_hand(a):
    o = a.option("colo_converted_site")
    kw = 10.2 * (0.35 + 0.65 * 0.6) * 1.25
    assert h.evaluate(o, a).parts_usd["electricity"] == pytest.approx(kw * 730 * 0.0721, abs=0.01)


def test_colo_fee_on_contracted_kw(a):
    assert h.evaluate(a.option("colo_converted_site"), a).parts_usd["colocation"] == pytest.approx(140 * 10.2)


def test_tokens_per_month(a):
    o = a.option("colo_converted_site")
    assert h.evaluate(o, a).tokens_per_month_b == pytest.approx(8 * 2500 * 3600 * 730 * 0.6 / 1e9, abs=1e-3)


def test_cost_per_token_falls_as_utilisation_rises(a):
    sw = h.report(a)["utilisation_sweep"]
    for name in ("cloud_on_demand", "colo_converted_site", "onprem_small_server"):
        assert sw[name] == sorted(sw[name], reverse=True)


def test_useful_gpu_hour_is_gpu_hour_over_utilisation(a):
    r = h.evaluate(a.option("colo_converted_site"), a)
    assert r.usd_per_useful_gpu_hour == pytest.approx(r.usd_per_gpu_hour / 0.6, rel=1e-3)


@pytest.mark.parametrize("name", ["cloud_on_demand", "colo_converted_site", "onprem_small_server"])
def test_break_even_utilisation_is_where_costs_meet(a, name):
    o = a.option(name)
    u = h.break_even_utilisation(o, a)
    assert u is not None
    assert h.evaluate(o, a, u).usd_per_m_tokens == pytest.approx(a.api_blended_usd_per_m, rel=1e-3)


def test_break_even_none_when_api_is_cheaper_at_full_load(raw):
    raw["api"]["input_usd_per_m"]["value"] = 0.01
    raw["api"]["output_usd_per_m"]["value"] = 0.02
    a = h.parse(raw)
    assert h.break_even_utilisation(a.option("cloud_on_demand"), a) is None
    assert h.payback_months(a.option("colo_converted_site"), a) is None


def test_payback_by_hand(a):
    o = a.option("onprem_small_server")
    r = h.evaluate(o, a)
    running = r.parts_usd["electricity"] + r.parts_usd["ops"]
    api = r.tokens_per_month_b * 1000 * 0.7
    assert r.payback_months_vs_api == pytest.approx(60_000 / (api - running), abs=0.1)


def test_cloud_has_no_payback(a):
    assert h.payback_months(a.option("cloud_on_demand"), a) is None


def test_electricity_is_a_small_share_of_owned_cost_per_token(a):
    sweep = h.report(a)["electricity_sweep"]
    cheap, dear = sweep[0]["colo_converted_site"], sweep[-1]["colo_converted_site"]
    assert dear > cheap
    assert dear / cheap < 1.25  # 7.5x the power price moves cost per token by under 25%


def test_site_capacity_power_sets_the_ceiling(a):
    s = h.site_capacity(a.option("colo_converted_site"), a)
    assert s["servers"] == math.floor(20_000 / (10.2 * 1.25))
    assert s["gpus"] == s["servers"] * 8
    assert s["it_mw"] == pytest.approx(16.0)


def test_better_pue_fits_more_gpus(raw):
    base = h.site_capacity(h.parse(raw).option("colo_converted_site"), h.parse(raw))["gpus"]
    raw["options"]["colo_converted_site"]["pue"]["value"] = 1.1
    a2 = h.parse(raw)
    assert h.site_capacity(a2.option("colo_converted_site"), a2)["gpus"] > base


def test_site_capacity_rejects_cloud(a):
    with pytest.raises(ValueError):
        h.site_capacity(a.option("cloud_on_demand"), a)


def test_halving_halves_only_the_subsidy(a):
    w = h.halving_what_if(a, a.option("colo_converted_site"))
    assert w["mining_revenue_after_subsidy_halves_usd"] == pytest.approx(w["mining_revenue_now_usd"] * (0.05 + 0.95 / 2), abs=1)


def test_halving_hashrate_from_efficiency(a):
    w = h.halving_what_if(a, a.option("colo_converted_site"))
    assert w["hashrate_ph_s"] == pytest.approx(1000 / 1.05 / 18, abs=0.01)


def test_halving_breakeven_hashprice_covers_power(a):
    w = h.halving_what_if(a, a.option("colo_converted_site"))
    days = 730 / 24
    revenue = w["hashrate_ph_s"] * w["breakeven_hashprice_after_usd_per_ph_day"] * days * (0.05 + 0.95 / 2)
    assert revenue == pytest.approx(w["power_cost_usd"], rel=1e-3)


def test_all_fees_means_halving_changes_nothing(raw):
    raw["halving"]["fee_share_of_revenue"]["value"] = 1.0
    a = h.parse(raw)
    w = h.halving_what_if(a, a.option("colo_converted_site"))
    assert w["mining_revenue_after_subsidy_halves_usd"] == w["mining_revenue_now_usd"]


# ------------------------------------------------------------- the example outputs


def test_example_ranking(a):
    r = h.report(a)
    assert r["cheapest_per_token"] == "colo_converted_site"
    assert by_name(r, "cloud_on_demand")["vs_api"] > 1 > by_name(r, "colo_converted_site")["vs_api"]


def test_results_file_matches_a_fresh_run(a):
    committed = json.loads((ROOT / "docs" / "hosting_results.json").read_text())
    assert committed == json.loads(json.dumps(h.report(a)))


def test_report_is_deterministic(a):
    assert h.report(a) == h.report(h.load())


# ------------------------------------------------------------- CLI


def test_cli_table(capsys):
    assert main(["hosting"]) == 0
    out = capsys.readouterr().out
    assert "(b) Colocation at a converted power site" in out
    assert "not investment advice" in out
    assert "-$14,612" in out


def test_cli_json(capsys):
    assert main(["hosting", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["cheapest_per_token"] == "colo_converted_site"


def test_cli_check_passes():
    assert main(["hosting", "--check", str(ROOT / "docs" / "hosting_results.json")]) == 0


def test_cli_check_detects_drift(tmp_path):
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"utilisation": 0.1}))
    assert main(["hosting", "--check", str(f)]) == 1


def test_cli_bad_assumptions_exit_2(tmp_path, capsys, raw):
    raw["utilisation"] = 0.6
    f = tmp_path / "bad.yaml"
    f.write_text(yaml.safe_dump(raw))
    assert main(["hosting", "--assumptions", str(f)]) == 2
    assert "bare number" in capsys.readouterr().err
