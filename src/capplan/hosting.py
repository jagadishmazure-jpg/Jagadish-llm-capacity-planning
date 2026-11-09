"""Power-constrained AI hosting economics.

Compares the cost per GPU-hour and per million tokens of three ways to host a model:

(a) cloud GPUs rented on demand,
(b) your own servers in colocation at a converted power site (for example an old mining site),
(c) one small server bought once and run on-prem (the small-team model),

against a per-token API price. It also finds the break-even utilisation for each option, the payback
time of the owned options, how many GPUs and tokens a site's power connection allows, and a mechanical
what-if for a mining site facing the next block-subsidy halving.

Every input comes from a YAML file in which each number is labelled ``example`` or ``reference``
(a typical published figure with an as-of date). The loader rejects unknown keys, missing labels and out-of-range values.
This is a planning calculator, not investment advice, and it contains no price forecasts.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_ASSUMPTIONS = Path(__file__).resolve().parents[2] / "assumptions" / "hosting.yaml"
BASES = {"example", "reference"}
LEAF_KEYS = {"value", "basis", "as_of", "note"}

# name -> (low, high, low_inclusive). high is inclusive. None = no bound.
RANGES: dict[str, tuple[float | None, float | None, bool]] = {
    "hours_per_month": (1, 744, True),
    "utilisation": (0, 1, False),
    "input_usd_per_m": (0, None, True),
    "output_usd_per_m": (0, None, True),
    "output_token_share": (0, 1, True),
    "gpus": (1, None, True),
    "usd_per_gpu_hour": (0, None, True),
    "billed_hours_fraction": (0, 1, False),
    "other_usd_per_month": (0, None, True),
    "tokens_per_s_per_gpu": (0, None, False),
    "gpus_per_server": (1, None, True),
    "servers": (1, None, True),
    "server_capex_usd": (0, None, True),
    "amortisation_years": (0, 15, False),
    "cost_of_capital": (0, 1, True),
    "it_kw_per_server": (0, None, False),
    "idle_draw_fraction": (0, 1, True),
    "pue": (1, 3, True),
    "electricity_usd_per_kwh": (0, 2, True),
    "colo_usd_per_kw_month": (0, None, True),
    "ops_usd_per_month": (0, None, True),
    "rack_kw_limit": (0, None, False),
    "power_mw": (0, None, False),
    "hashprice_usd_per_ph_day": (0, None, True),
    "fleet_efficiency_j_per_th": (0, None, False),
    "fee_share_of_revenue": (0, 1, True),
    "mining_pue": (1, 3, True),
}
CLOUD_KEYS = {"gpus", "usd_per_gpu_hour", "billed_hours_fraction", "other_usd_per_month", "tokens_per_s_per_gpu"}
OWNED_KEYS = {
    "gpus_per_server",
    "servers",
    "server_capex_usd",
    "amortisation_years",
    "cost_of_capital",
    "it_kw_per_server",
    "idle_draw_fraction",
    "pue",
    "electricity_usd_per_kwh",
    "colo_usd_per_kw_month",
    "ops_usd_per_month",
    "tokens_per_s_per_gpu",
    "rack_kw_limit",
}
HALVING_KEYS = {"hashprice_usd_per_ph_day", "fleet_efficiency_j_per_th", "fee_share_of_revenue", "mining_pue"}
INTEGER_KEYS = {"gpus", "gpus_per_server", "servers"}


class AssumptionError(ValueError):
    """An assumptions file is missing a key, has an unknown key, an unlabelled number or a bad value."""


def _leaf(path: str, name: str, raw: Any) -> float:
    if not isinstance(raw, dict):
        raise AssumptionError(f"{path}: must be a mapping with value and basis, not a bare number")
    extra = set(raw) - LEAF_KEYS
    if extra:
        raise AssumptionError(f"{path}: unknown keys {sorted(extra)}")
    if raw.get("basis") not in BASES:
        raise AssumptionError(f"{path}: basis must be one of {sorted(BASES)}")
    if raw["basis"] == "reference" and not raw.get("as_of"):
        raise AssumptionError(f"{path}: a reference number needs an as_of date")
    v = raw.get("value")
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise AssumptionError(f"{path}: value must be a number")
    v = float(v)
    if not math.isfinite(v):
        raise AssumptionError(f"{path}: value must be finite")
    lo, hi, lo_incl = RANGES[name]
    if lo is not None and (v < lo or (v == lo and not lo_incl)):
        raise AssumptionError(f"{path}: {v} is below the allowed range ({'>=' if lo_incl else '>'} {lo})")
    if hi is not None and v > hi:
        raise AssumptionError(f"{path}: {v} is above the allowed range (<= {hi})")
    if name in INTEGER_KEYS and v != int(v):
        raise AssumptionError(f"{path}: must be a whole number")
    return v


def _section(path: str, raw: Any, keys: set[str], allowed_extra: set[str] = frozenset()) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise AssumptionError(f"{path}: must be a mapping")
    unknown = set(raw) - keys - allowed_extra
    if unknown:
        raise AssumptionError(f"{path}: unknown keys {sorted(unknown)}")
    missing = keys - set(raw)
    if missing:
        raise AssumptionError(f"{path}: missing keys {sorted(missing)}")
    return {k: _leaf(f"{path}.{k}", k, raw[k]) for k in sorted(keys)}


@dataclass(frozen=True)
class Option:
    name: str
    label: str
    kind: str  # "cloud" or "owned"
    p: dict[str, float]

    @property
    def gpus(self) -> int:
        return int(self.p["gpus"] if self.kind == "cloud" else self.p["gpus_per_server"] * self.p["servers"])


@dataclass(frozen=True)
class Assumptions:
    hours_per_month: float
    utilisation: float
    api: dict[str, float]
    options: tuple[Option, ...]
    site_power_mw: float
    halving: dict[str, float]
    references: tuple[tuple[str, str], ...]  # (path, as_of) for every reference number

    @property
    def api_blended_usd_per_m(self) -> float:
        s = self.api["output_token_share"]
        return (1 - s) * self.api["input_usd_per_m"] + s * self.api["output_usd_per_m"]

    def option(self, name: str) -> Option:
        for o in self.options:
            if o.name == name:
                return o
        raise KeyError(name)


def _references(node: Any, path: str = "") -> list[tuple[str, str]]:
    out = []
    if isinstance(node, dict):
        if node.get("basis") == "reference":
            out.append((path, str(node.get("as_of"))))
        for k, v in node.items():
            out.extend(_references(v, f"{path}.{k}" if path else str(k)))
    return out


def parse(data: Any) -> Assumptions:
    if not isinstance(data, dict):
        raise AssumptionError("assumptions must be a mapping")
    top = {"hours_per_month", "utilisation", "api", "options", "site", "halving"}
    unknown, missing = set(data) - top, top - set(data)
    if unknown:
        raise AssumptionError(f"unknown top-level keys {sorted(unknown)}")
    if missing:
        raise AssumptionError(f"missing top-level keys {sorted(missing)}")
    api = _section("api", data["api"], {"input_usd_per_m", "output_usd_per_m", "output_token_share"})
    opts_raw = data["options"]
    if not isinstance(opts_raw, dict) or not opts_raw:
        raise AssumptionError("options: must be a non-empty mapping")
    options = []
    for name, raw in opts_raw.items():
        if not isinstance(raw, dict):
            raise AssumptionError(f"options.{name}: must be a mapping")
        kind = raw.get("kind")
        if kind not in ("cloud", "owned"):
            raise AssumptionError(f"options.{name}.kind must be cloud or owned")
        label = raw.get("label")
        if not isinstance(label, str) or not label.strip():
            raise AssumptionError(f"options.{name}.label must be a non-empty string")
        p = _section(f"options.{name}", raw, CLOUD_KEYS if kind == "cloud" else OWNED_KEYS, {"kind", "label"})
        options.append(Option(str(name), label, kind, p))
    site = _section("site", data["site"], {"power_mw"})
    halving = _section("halving", data["halving"], HALVING_KEYS)
    return Assumptions(
        hours_per_month=_leaf("hours_per_month", "hours_per_month", data["hours_per_month"]),
        utilisation=_leaf("utilisation", "utilisation", data["utilisation"]),
        api=api,
        options=tuple(options),
        site_power_mw=site["power_mw"],
        halving=halving,
        references=tuple(_references(data)),
    )


def load(path: str | Path = DEFAULT_ASSUMPTIONS) -> Assumptions:
    return parse(yaml.safe_load(Path(path).read_text()))


# ---------------------------------------------------------------- the maths


def annuity_per_month(capex: float, yearly_rate: float, years: float) -> float:
    """Level monthly payment that pays back ``capex`` over ``years`` at ``yearly_rate`` (0 = straight line)."""
    if capex == 0:
        return 0.0
    if yearly_rate == 0:
        return capex / years / 12
    yearly = capex * yearly_rate / (1 - (1 + yearly_rate) ** -years)
    return yearly / 12


def _owned_parts(o: Option, u: float, hours: float) -> dict[str, float]:
    p = o.p
    it_kw_max = p["it_kw_per_server"] * p["servers"]
    draw = p["idle_draw_fraction"] + (1 - p["idle_draw_fraction"]) * u
    facility_kw = it_kw_max * draw * p["pue"]
    return {
        "capex": annuity_per_month(p["server_capex_usd"] * p["servers"], p["cost_of_capital"], p["amortisation_years"]),
        "electricity": facility_kw * hours * p["electricity_usd_per_kwh"],
        "colocation": p["colo_usd_per_kw_month"] * it_kw_max,
        "ops": p["ops_usd_per_month"],
    }


def monthly_parts(o: Option, u: float, hours: float) -> dict[str, float]:
    """Monthly cost broken into parts, at utilisation ``u``."""
    if o.kind == "cloud":
        billed = max(o.p["billed_hours_fraction"], 0.0)
        return {"gpu_rental": o.gpus * o.p["usd_per_gpu_hour"] * hours * billed, "other": o.p["other_usd_per_month"]}
    return _owned_parts(o, u, hours)


def monthly_tokens(o: Option, u: float, hours: float) -> float:
    return o.gpus * o.p["tokens_per_s_per_gpu"] * 3600 * hours * u


def break_even_utilisation(o: Option, a: Assumptions) -> float | None:
    """Utilisation at which this option costs the same per token as the API, or None if it never does (in 0-1].

    Monthly cost is linear in utilisation: cost(u) = fixed + slope * u. The API bill for the same tokens is api * u.
    """
    h = a.hours_per_month
    c0 = sum(monthly_parts(o, 0.0, h).values())
    c1 = sum(monthly_parts(o, 1.0, h).values())
    slope = c1 - c0
    api_at_full = monthly_tokens(o, 1.0, h) / 1e6 * a.api_blended_usd_per_m
    if api_at_full <= slope:
        return None
    u = c0 / (api_at_full - slope)
    return u if 0 < u <= 1 else None


def payback_months(o: Option, a: Assumptions) -> float | None:
    """Months until buying the server beats paying the API for the same tokens, at the set utilisation.

    Running costs (power, colocation, ops) are paid monthly; the purchase is paid up front, without financing.
    """
    if o.kind != "owned":
        return None
    parts = monthly_parts(o, a.utilisation, a.hours_per_month)
    running = parts["electricity"] + parts["colocation"] + parts["ops"]
    api = monthly_tokens(o, a.utilisation, a.hours_per_month) / 1e6 * a.api_blended_usd_per_m
    saving = api - running
    if saving <= 0:
        return None
    return o.p["server_capex_usd"] * o.p["servers"] / saving


@dataclass(frozen=True)
class Result:
    name: str
    label: str
    gpus: int
    monthly_usd: float
    parts_usd: dict[str, float]
    usd_per_gpu_hour: float
    usd_per_useful_gpu_hour: float
    tokens_per_month_b: float
    usd_per_m_tokens: float
    vs_api: float
    break_even_utilisation: float | None
    payback_months_vs_api: float | None
    facility_kw: float | None
    racks: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate(o: Option, a: Assumptions, u: float | None = None) -> Result:
    u = a.utilisation if u is None else u
    h = a.hours_per_month
    parts = monthly_parts(o, u, h)
    total = sum(parts.values())
    gpu_hours = o.gpus * h
    toks = monthly_tokens(o, u, h)
    per_m = total / toks * 1e6
    facility_kw = racks = None
    if o.kind == "owned":
        p = o.p
        draw = p["idle_draw_fraction"] + (1 - p["idle_draw_fraction"]) * u
        facility_kw = p["it_kw_per_server"] * p["servers"] * draw * p["pue"]
        per_rack = math.floor(p["rack_kw_limit"] / p["it_kw_per_server"])
        if per_rack == 0:
            raise AssumptionError(f"options.{o.name}: one server ({p['it_kw_per_server']} kW) does not fit a {p['rack_kw_limit']} kW rack")
        racks = math.ceil(p["servers"] / per_rack)
    be = break_even_utilisation(o, a)
    pb = payback_months(o, a)
    return Result(
        name=o.name,
        label=o.label,
        gpus=o.gpus,
        monthly_usd=round(total, 2),
        parts_usd={k: round(v, 2) for k, v in parts.items()},
        usd_per_gpu_hour=round(total / gpu_hours, 4),
        usd_per_useful_gpu_hour=round(total / (gpu_hours * u), 4),
        tokens_per_month_b=round(toks / 1e9, 3),
        usd_per_m_tokens=round(per_m, 4),
        vs_api=round(per_m / a.api_blended_usd_per_m, 3),
        break_even_utilisation=None if be is None else round(be, 4),
        payback_months_vs_api=None if pb is None else round(pb, 1),
        facility_kw=None if facility_kw is None else round(facility_kw, 3),
        racks=racks,
    )


def site_capacity(o: Option, a: Assumptions) -> dict[str, Any]:
    """How much an owned option can serve on the site's power connection. Power, not GPUs, sets the ceiling."""
    if o.kind != "owned":
        raise ValueError("site capacity applies to owned options only")
    p = o.p
    facility_kw_per_server_max = p["it_kw_per_server"] * p["pue"]  # plan for max draw, not average
    servers = math.floor(a.site_power_mw * 1000 / facility_kw_per_server_max)
    gpus = int(servers * p["gpus_per_server"])
    toks = gpus * p["tokens_per_s_per_gpu"] * 3600 * a.hours_per_month * a.utilisation
    return {
        "site_power_mw": a.site_power_mw,
        "it_mw": round(a.site_power_mw / p["pue"], 3),
        "servers": servers,
        "gpus": gpus,
        "racks": math.ceil(servers / math.floor(p["rack_kw_limit"] / p["it_kw_per_server"])),
        "tokens_per_month_b": round(toks / 1e9, 1),
        "tokens_per_month_b_per_mw": round(toks / 1e9 / a.site_power_mw, 2),
    }


def halving_what_if(a: Assumptions, host: Option) -> dict[str, Any]:
    """Per MW of facility power: mining margin now, mining margin if only the block subsidy halves, and hosting revenue.

    Mechanical what-if: every input stays as written except the subsidy share of mining revenue, which halves.
    In reality coin price, network hashrate and fees all move; this does not forecast any of them.
    Hosting revenue is the colocation fee on the IT kW one MW supports, with power passed through to the tenant,
    before the cost of converting the site.
    """
    hv = a.halving
    price = host.p["electricity_usd_per_kwh"]
    days = a.hours_per_month / 24
    it_kw_mining = 1000 / hv["mining_pue"]
    ph_s = it_kw_mining * 1000 / hv["fleet_efficiency_j_per_th"] / 1000  # W / (J/TH) = TH/s; /1000 = PH/s
    revenue_now = ph_s * hv["hashprice_usd_per_ph_day"] * days
    after = revenue_now * (hv["fee_share_of_revenue"] + (1 - hv["fee_share_of_revenue"]) / 2)
    power = 1000 * a.hours_per_month * price
    hosting = host.p["colo_usd_per_kw_month"] * 1000 / host.p["pue"]
    return {
        "per_mw_facility_power_per_month": True,
        "electricity_usd_per_kwh": price,
        "hashrate_ph_s": round(ph_s, 2),
        "mining_revenue_now_usd": round(revenue_now),
        "mining_revenue_after_subsidy_halves_usd": round(after),
        "power_cost_usd": round(power),
        "mining_margin_now_usd": round(revenue_now - power),
        "mining_margin_after_usd": round(after - power),
        "hosting_colo_revenue_usd": round(hosting),
        "breakeven_hashprice_after_usd_per_ph_day": round(
            power / (ph_s * days * (hv["fee_share_of_revenue"] + (1 - hv["fee_share_of_revenue"]) / 2)), 2
        ),
    }


def site_option(a: Assumptions) -> Option:
    """The option that models a power site: the first owned option that pays a colocation fee."""
    for o in a.options:
        if o.kind == "owned" and o.p["colo_usd_per_kw_month"] > 0:
            return o
    raise AssumptionError("no owned option with a colocation fee, so there is no power site to model")


UTILISATION_SWEEP = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
ELECTRICITY_SWEEP = (0.04, 0.0721, 0.10, 0.1447, 0.20, 0.30)


def report(a: Assumptions) -> dict[str, Any]:
    results = [evaluate(o, a) for o in a.options]
    owned = [o for o in a.options if o.kind == "owned"]
    site = site_option(a)
    sweep = {o.name: [evaluate(o, a, u).usd_per_m_tokens for u in UTILISATION_SWEEP] for o in a.options}
    elec = []
    for price in ELECTRICITY_SWEEP:
        row = {}
        for o in owned:
            o2 = Option(o.name, o.label, o.kind, {**o.p, "electricity_usd_per_kwh": price})
            row[o.name] = evaluate(o2, a).usd_per_m_tokens
        elec.append({"usd_per_kwh": price, **row})
    return {
        "api_blended_usd_per_m": round(a.api_blended_usd_per_m, 4),
        "utilisation": a.utilisation,
        "options": [r.as_dict() for r in results],
        "cheapest_per_token": min(results, key=lambda r: r.usd_per_m_tokens).name,
        "utilisation_sweep": {"utilisation": list(UTILISATION_SWEEP), **sweep},
        "electricity_sweep": elec,
        "site_option": site.name,
        "site_capacity": site_capacity(site, a),
        "halving_what_if": halving_what_if(a, site),
        "reference_values": [{"field": f, "as_of": d} for f, d in a.references],
    }
