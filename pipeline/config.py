#!/usr/bin/env python3
"""config.py — the per-company statement-adjustment config: load + fail-loud validate.

Every judgment call that shapes a company's restated statements — fiscal-year end,
minority-interest inclusion, finance-lease add-back, R&D capitalization and life, the
operating-income adjustment, spinoff factors, the cost-of-debt source, the price source
— lives in a committed `companies/<TICKER>.yaml`. That makes the adjustment fully
specified and reproducible: re-run it and you get the same restated statements, or a diff
you can see and explain. No settings live in a notebook or a chat scrollback any more.

This module turns that YAML into the exact `config` dict `aeg_engine.build_model` expects,
after validating it loudly. A malformed or under-specified config aborts the run before any
data is touched — the same fail-loud discipline as the loader gates.
"""
import json, hashlib
import yaml

MONTHS = set(range(1, 13))


class ConfigError(Exception):
    """Raised on any config-contract violation. Fail loud; never guess a judgment."""


class AwaitingReview(ConfigError):
    """The company has no AUTHORIZED forecast horizon, so no valuation is produced.

    A SUBCLASS, so every existing `except ConfigError` still catches it and the gate is exactly
    as hard as it was. It exists only so a caller that wants to can tell two different things
    apart, because they are not the same event:

        AwaitingReview   nobody has forecast this company yet. Under rule D1 forecasting is
                         permanently human-in-the-loop, so this is the system WORKING. There
                         was never going to be a number, and there is nothing to fix.
        ConfigError      a company somebody DID authorize will not value. Something is broken.

    Before 2026-08-19 the fleet workflow treated both as failure. Fourteen of sixteen companies
    on file have never been forecast, so the AEG valuation pipeline was red on every run and
    could not have been anything else -- which is how it came to be red for six days with a
    real crash (pyarrow) hiding inside the noise, on the only two companies that could publish.
    """


def _req(d, key, types, where):
    if key not in d:
        raise ConfigError(f"[{where}] missing required key '{key}'")
    if not isinstance(d[key], types):
        raise ConfigError(f"[{where}] '{key}' must be {types}, got {type(d[key]).__name__}")
    return d[key]


def _opt(d, key, types, default):
    if key not in d or d[key] is None:
        return default
    if not isinstance(d[key], types):
        raise ConfigError(f"'{key}' must be {types} or null, got {type(d[key]).__name__}")
    return d[key]


def load_config(path, require_forecast=True):
    """Parse + validate a companies/<TICKER>.yaml. Returns a normalized dict with a
    canonical `config_for_build` sub-dict ready for aeg_engine.build_model (minus the
    file paths + resolved price/cost-of-debt, which the pipeline stages fill in).

    require_forecast=False validates EVERYTHING EXCEPT the forecast horizon and its
    confirmation, and is for exactly one caller: onboard.py, checking the config it has just
    generated.

    WHY IT HAD TO EXIST (2026-08-19). The forecast gate is about publishing a VALUATION -- a
    horizon nobody chose must never reach a number. It is not about whether a config may exist.
    Onboarding cannot supply horizon_N, because horizon_N is the judgment onboarding exists to
    make possible. So onboard.py round-tripped its generated file through the full validator,
    the validator refused it for want of the one field onboarding cannot know, and onboard
    DELETED the file and exited non-zero.

    The effect was that NO NEW COMPANY COULD BE ADDED TO THIS SYSTEM AT ALL. It broke silently
    when the horizon gate landed and stayed broken because nobody onboarded a ticker between
    2026-08-03 and 2026-08-19; the existing companies kept valuing perfectly the whole time.
    The gate is unchanged and just as hard -- the onboarded company sits in AWAITING FORECAST,
    produces no valuation, and is listed by name on every fleet run until a human forecasts it.
    """
    with open(path, "r") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ConfigError(f"[{path}] top level must be a mapping")

    company = _req(raw, "company", str, "root")
    ticker = _req(raw, "ticker", str, "root").upper()
    fy_end_month = _opt(raw, "fy_end_month", int, 0)   # 0 = auto-detect from statement dates
    if fy_end_month != 0 and fy_end_month not in MONTHS:
        raise ConfigError(f"fy_end_month must be 0 (auto) or 1..12, got {fy_end_month}")

    j = raw.get("judgments", {}) or {}
    if not isinstance(j, dict):
        raise ConfigError("'judgments' must be a mapping")
    judgments = {
        "minority_include": _opt(j, "minority_include", bool, False),
        "finlease":         float(_opt(j, "finlease", (int, float), 0.0)),
        "oi_adj_override":  (None if j.get("oi_adj_override") is None
                             else float(j["oi_adj_override"])),
        "rd_capitalize":    _opt(j, "rd_capitalize", bool, False),
        "rd_life":          float(_opt(j, "rd_life", (int, float), 0.0)),
        "dps_override":     (None if j.get("dps_override") is None
                             else float(j["dps_override"])),
        # P1/P3 escape hatches. Both inputs are derived from the filings by default; an
        # override is for the case where the filings cannot support a derivation (a loss
        # year for the payout, a missing Gross PP&E line for the plant life) or where the
        # analyst has a better estimate. Leaving them null is the normal case.
        "payout_override":   (None if j.get("payout_override") is None
                              else float(j["payout_override"])),
        "ppe_life_override": (None if j.get("ppe_life_override") is None
                              else float(j["ppe_life_override"])),
    }
    if judgments["rd_capitalize"] and judgments["rd_life"] <= 0:
        raise ConfigError("rd_capitalize=true requires rd_life > 0")
    if judgments["payout_override"] is not None and not 0.0 <= judgments["payout_override"] <= 2.0:
        raise ConfigError(f"judgments.payout_override must be between 0 and 2.0, "
                          f"got {judgments['payout_override']}")
    if judgments["ppe_life_override"] is not None and not 2.0 <= judgments["ppe_life_override"] <= 50.0:
        raise ConfigError(f"judgments.ppe_life_override must be between 2 and 50 years, "
                          f"got {judgments['ppe_life_override']}")

    # P2 — the explicit forecast horizon. MANDATORY INPUT. NO DEFAULT. EVER.
    #
    # James's standing rule, restated 2026-08-09 after being asked about this too many
    # times: "There is no limit to the forecast period. And there is no default. It is a
    # free input. It is a mandatory input. The analyst must select the forecast period.
    # There is no valuation without an explicit selection of a forecast period."
    #
    # cfg_N is the competitive-advantage period: how many years abnormal earnings growth
    # is forecast to persist. It moves the Apple fixture 31% between 4 and 30 years, so
    # it is a first-order forecasting judgment — the single most powerful one in the
    # model — and it belongs to the analyst under rule D1.
    #
    # This is enforced HERE, in code, and not as a warning. A warning that does not stop
    # a run is how a 4 nobody chose ended up on fourteen companies, and how the question
    # kept coming back. Both conditions below ABORT. Do not soften either of them, and do
    # not suggest a value anywhere in this file — suggesting one is how the last default
    # got established.
    fc = raw.get("forecast", {}) or {}
    if not isinstance(fc, dict):
        raise ConfigError("'forecast' must be a mapping")
    # THE FORECAST GATE. It is about publishing a VALUATION -- a horizon nobody chose must
    # never reach a number. It is not about whether a config may EXIST. See load_config's
    # docstring for what conflating those two cost.
    if fc.get("horizon_N") is None and not require_forecast:
        horizon_N, horizon_reviewed = None, False
    else:
        if fc.get("horizon_N") is None:
            # AwaitingReview, not a bare ConfigError. "No horizon at all" and "a horizon nobody
            # confirmed" are the SAME EVENT -- nobody has forecast this company -- and a freshly
            # onboarded config is the first case by construction. Classifying it as a hard
            # refusal turned every newly onboarded company into a red fleet run, which is the
            # problem the AwaitingReview bucket was created to end, arriving from the other side.
            # A horizon that is present but MALFORMED stays a hard ConfigError below: that is a
            # broken config, not an unforecast company.
            raise AwaitingReview(
                "missing 'forecast.horizon_N' — this company has NO FORECAST HORIZON AT ALL, "
                "so no valuation will be produced. It is AWAITING FORECAST.\n"
                "  cfg_N is the competitive-advantage period: the number of years YOU judge "
                "abnormal earnings growth to persist for this company. There is no default "
                "and there never will be. Any integer from 1 upward is accepted.\n"
                "  To authorize a valuation, add:\n"
                "      forecast:\n        horizon_N: <your judgment>\n        reviewed: true")
        try:
            horizon_N = int(fc["horizon_N"])
        except (TypeError, ValueError):
            raise ConfigError(f"forecast.horizon_N must be an integer 1..30, "
                              f"got {fc['horizon_N']!r}")
        if not 1 <= horizon_N <= 30:
            # 30 is a STRUCTURAL ceiling, not a judgment: the Forecast tab of MODEL_TEMPLATE
            # carries thirty forecast columns. It is not a policy limit on how long an
            # advantage period may be. Extending the template is a separate piece of work.
            raise ConfigError(
                f"forecast.horizon_N must be between 1 and 30, got {horizon_N}. Note that 30 "
                f"is a STRUCTURAL limit — the Forecast tab has thirty columns — not a cap on "
                f"your judgment. Extending it is a template change.")
        # MANDATORY CONFIRMATION. A horizon that no human deliberately chose is not a valid
        # horizon, so an unreviewed config produces NO VALUATION. This is a hard gate, not a
        # warning; see the block above for why.
        if _opt(fc, "reviewed", bool, False) is not True:
            raise AwaitingReview(
                f"forecast.reviewed is not true — this company has NO AUTHORIZED FORECAST "
                f"HORIZON, so no valuation will be produced.\n"
                f"  The config currently carries horizon_N: {horizon_N}. If that value was "
                f"not deliberately chosen by the analyst for THIS company, it is an artifact "
                f"and must not be inherited.\n"
                f"  cfg_N is the competitive-advantage period — the number of years you judge "
                f"abnormal earnings growth to persist. It is the most powerful single judgment "
                f"in the model (31% on the Apple fixture between 4 and 30 years).\n"
                f"  To authorize a valuation, set forecast.horizon_N deliberately and add:\n"
                f"      forecast:\n        reviewed: true\n"
                f"  There is no default and there is no way around this gate. That is intended.")
        horizon_reviewed = True

    # --- CONVERGENCE REVIEW (James, 2026-08-09). The convergence reconciliation guard reports
    # REVIEW when the explicit forecast ends at an earnings level far from its own neutral line.
    # That verdict now REFUSES the valuation, and this flag is the analyst's escape hatch, in
    # deliberate parallel to forecast.reviewed above: the gate is cleared by a written human
    # assertion, never by a code change or a threshold tweak.
    #
    # Unlike forecast.reviewed this is NOT mandatory, because the gate only engages when the
    # guard actually trips. A company whose forecast lands near its neutral line never needs it.
    # Absent means false, which is the safe direction.
    #
    # `note` is free text recording WHAT the analyst concluded — which of the four causes it was
    # — so the review is a recorded answer per company rather than a rubber stamp. It is optional
    # and carries no logic.
    cv = raw.get("convergence", {}) or {}
    if not isinstance(cv, dict):
        raise ConfigError("'convergence' must be a mapping")
    convergence_reviewed = _opt(cv, "reviewed", bool, False) is True
    convergence_note = _opt(cv, "note", str, "")

    # --- FUNDING REVIEW (James, 2026-08-11). The unfunded-distribution guard
    # (pipeline/funding_check.py) reports REVIEW when the implied dividend in the explicit
    # forecast goes negative. That verdict REFUSES the valuation, cleared only by a human
    # writing funding.reviewed: true here -- in deliberate parallel to convergence.reviewed
    # above.
    #
    # BUG FOUND 2026-08-12: this block did not exist. run_company.py has always read
    # cfg.get("funding_reviewed") and cfg.get("funding_note"), but load_config never put
    # those keys in the normalized dict, so a company config carrying `funding: reviewed:
    # true` had no effect whatsoever -- the escape hatch documented in the kit since
    # 2026-08-11 could not be exercised by any company. Silent and inert, the same failure
    # class as the horizon bug: a written assertion that changes nothing. No company has
    # relied on it yet (AAPL/COST/KO/WMT are deliberately left funding-gated), so no
    # published number was affected, but the mechanism itself was dead on arrival.
    fu = raw.get("funding", {}) or {}
    if not isinstance(fu, dict):
        raise ConfigError("'funding' must be a mapping")
    funding_reviewed = _opt(fu, "reviewed", bool, False) is True
    funding_note = _opt(fu, "note", str, "")

    # --- TERMINAL PAYOUT RATIO (James, 2026-08-12). Nothing previously described what this
    # company does once it reaches the continuing period (year cfg_N+1 onward). The Forecast
    # tab's own driver cells past cfg_N are never written by a real payload; they hold
    # whatever the legacy scenario overlay says, unrelated to the forecaster's judgment, and
    # that overlay's buyback assumption can imply a deeply negative modeled dividend there
    # (confirmed on a real forecast, 2026-08-12). None of that reaches the published value --
    # Valuation row 24 zeroes every contribution for t>cfg_N, so the four-method tie and the
    # two truncation gates are untouched by it -- but nothing forecaster-owned governs the
    # transition either.
    #
    # terminal.payout_ratio closes that: a DIVIDENDS-ONLY fraction of normalized net income
    # the forecaster asserts this company distributes once it reaches the continuing period.
    # Retention is the residual (1 - the ratio), exactly as "payout" already means dividends
    # only everywhere else in this kit (buybacks are never folded in here). There is no
    # default. Optional at the config-parse stage -- the run still executes and the OTHER
    # gates still get their diagnostics -- but pipeline/run_company.py refuses to publish
    # without it, with no reviewed:true escape hatch for a ratio that was never set at all
    # (same discipline as forecast.horizon_N: an assertion nobody made cannot be reviewed
    # into existence).
    te = raw.get("terminal", {}) or {}
    if not isinstance(te, dict):
        raise ConfigError("'terminal' must be a mapping")
    terminal_payout_ratio = te.get("payout_ratio")
    if terminal_payout_ratio is not None:
        try:
            terminal_payout_ratio = float(terminal_payout_ratio)
        except (TypeError, ValueError):
            raise ConfigError(f"terminal.payout_ratio must be a number, "
                              f"got {te['payout_ratio']!r}")
        if not 0.0 <= terminal_payout_ratio <= 1.0:
            raise ConfigError(
                f"terminal.payout_ratio must be between 0.0 and 1.0 (a DIVIDENDS-ONLY "
                f"fraction of normalized net income -- retention is 1 minus this), "
                f"got {terminal_payout_ratio}")
    terminal_reviewed = _opt(te, "reviewed", bool, False) is True
    terminal_note = _opt(te, "note", str, "")

    sp = raw.get("spinoff", {}) or {}
    spinoff = {"factor": float(_opt(sp, "factor", (int, float), 1.0)),
               "before_year": int(_opt(sp, "before_year", int, 0))}

    price = raw.get("price", {}) or {}
    price_source = _opt(price, "source", str, "market")   # "market" | "override"
    price_override = (None if price.get("override") is None else float(price["override"]))
    if price_source not in ("market", "override"):
        raise ConfigError(f"price.source must be 'market' or 'override', got {price_source!r}")
    if price_source == "override" and price_override is None:
        raise ConfigError("price.source='override' requires price.override")

    cod = raw.get("cost_of_debt", {}) or {}
    cod_source = _opt(cod, "source", str, "bond_list")
    valid_cod = ("bond_list", "ytw_points", "single_ytw", "interest_implied")
    if cod_source not in valid_cod:
        raise ConfigError(f"cost_of_debt.source must be one of {valid_cod}, got {cod_source!r}")
    cod_norm = {"source": cod_source}
    # seed_ytw: the throwaway COD used for the initial build when source=bond_list (the
    # rate re-point overrides it with real_cod). If the feed is not yet live, this seed
    # is the provisional COD and the run is flagged. Default 0.05.
    cod_norm["seed_ytw"] = float(_opt(cod, "seed_ytw", (int, float), 0.05))
    if cod_source == "ytw_points":
        pts = cod.get("ytw_points")
        if not isinstance(pts, list) or not pts:
            raise ConfigError("cost_of_debt.source='ytw_points' requires a non-empty ytw_points list")
        cod_norm["ytw_points"] = [(float(t), float(y)) for t, y in pts]
    elif cod_source == "single_ytw":
        cod_norm["single_ytw"] = float(_req(cod, "single_ytw", (int, float), "cost_of_debt"))
    # bond_list -> resolved from the rate-infra cod_<TICKER> CSV at pipeline time
    # interest_implied -> loader computes interest_expense/total_debt fallback (flagged)

    bonded = bool(_opt(raw, "bonded", bool, cod_source == "bond_list"))
    # for names with no R&D and no other reported-vs-economic opex wedge (e.g. AT&T),
    # assert Forecast row 61 is ~0. Leave false for names that legitimately carry a wedge.
    expect_zero_rd_wedge = _opt(raw, "expect_zero_rd_wedge", bool, False)

    normalized = {
        "company": company, "ticker": ticker, "fy_end_month": fy_end_month,
        "forecast_horizon_N": horizon_N, "horizon_reviewed": horizon_reviewed,
        "convergence_reviewed": convergence_reviewed, "convergence_note": convergence_note,
        "funding_reviewed": funding_reviewed, "funding_note": funding_note,
        "terminal_payout_ratio": terminal_payout_ratio, "terminal_reviewed": terminal_reviewed,
        "terminal_note": terminal_note,
        "judgments": judgments, "spinoff": spinoff,
        "price_source": price_source, "price_override": price_override,
        "cost_of_debt": cod_norm, "bonded": bonded,
        "expect_zero_rd_wedge": expect_zero_rd_wedge,
    }
    normalized["config_hash"] = config_hash(normalized)
    return normalized


def config_hash(normalized):
    """Stable hash of the judgment-bearing config, for the run manifest. Excludes any
    volatile resolved fields (price, live rates) so the hash identifies the *decisions*."""
    # forecast_horizon_N belongs here: cfg_N is a decision, and a first-order one — it
    # moves the Apple fixture 31% between 4 and 30 years. A hash that ignored it would
    # report two materially different valuations as the same set of decisions.
    # horizon_reviewed is deliberately EXCLUDED: it is a bookkeeping flag about whether
    # a human has looked at the horizon, and toggling it changes no number. convergence_reviewed
    # and convergence_note are excluded for exactly the same reason — they gate whether a number
    # is published, not what the number is.
    # terminal_payout_ratio belongs here alongside forecast_horizon_N: it is a first-order
    # judgment about what the company does forever after cfg_N, not bookkeeping about whether
    # someone looked. terminal_reviewed/terminal_note are excluded for the same reason
    # horizon_reviewed and convergence_reviewed/note are: they gate whether a number is
    # published, not what the number is.
    core = {k: normalized[k] for k in
            ("company", "ticker", "fy_end_month", "forecast_horizon_N", "terminal_payout_ratio",
             "judgments", "spinoff", "cost_of_debt", "bonded") if k in normalized}
    blob = json.dumps(core, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


if __name__ == "__main__":
    import sys
    c = load_config(sys.argv[1])
    print(json.dumps(c, indent=2, default=str))
