#!/usr/bin/env python3
"""terminal_payout.py — the terminal (continuing-period) distribution-policy gate.

WHY THIS EXISTS (2026-08-12). Nothing before this described what a company does once it
reaches the continuing period, year cfg_N+1 onward. The Forecast tab's own driver cells past
cfg_N are never written by a real payload -- they hold whatever the legacy 3-scenario overlay
says, unrelated to the forecaster's judgment. Confirmed on a real forecast (PEP, cfg_N=4,
2026-08-12): that overlay's buyback assumption (3%/yr, against the forecaster's actual 0.35%)
implies a modeled dividend of -$2.96/sh in year 5, worsening to -$7.15/sh by year 16.

None of that reaches the published value. Valuation row 24 (`contrib EPS [t<=N]`) zeroes
every AEG contribution for t>cfg_N, and the terminal capitalization (row 43, "Normal value")
is built entirely from year-1 and anchor (year-0) data -- so the four-method tie and the two
truncation gates (pipeline/convergence.py) are provably unaffected by anything past cfg_N.
See test_terminal_payout.py, which pins that property directly: identical value at
payout_ratio 0.0, 0.5 and 1.0.

But nothing forecaster-owned governed the transition either, and that is its own gap: a
company can pass every gate with an implicit, un-inspected assumption about its continuing-
period capital policy that nobody chose and nobody would sign.

WHAT THIS ASKS FOR. A DIVIDENDS-ONLY fraction of normalized net income (the same
normalized_eps_N gate B already computes) that the forecaster asserts this company
distributes once it reaches the continuing period. Retention is the residual (1 - the
ratio), exactly as "payout" already means dividends only everywhere else in the kit --
buybacks are never folded in here.

WHY IT CANNOT FAIL THE WAY THE EXPLICIT-YEAR FUNDING GATE DOES. That gate (funding_check.py)
catches a NEGATIVE implied dividend, because dividends there are a RESIDUAL after an
independently-set buyback rate and financing target -- an unbounded quantity that can
overshoot capacity. Here the ratio is bounded to [0,1] at the config seam, so a payout ratio
can never itself demand more than the company earns. What this module catches instead is the
case beneath that: a normalized earnings level that is zero, negative, or unavailable, where
no payout ratio is a coherent assertion about the continuing period at all -- and, in
run_company.py, a ratio nobody ever set (that case has no reviewed:true escape hatch, in
deliberate parallel to forecast.horizon_N: an assertion nobody made cannot be reviewed into
existence).
"""


def terminal_payout_report(ratio, normalized_eps_N):
    """Report the implied terminal (continuing-period) dividend and retention.

    ratio            : dividends-only payout ratio from companies/<T>.yaml terminal.payout_ratio,
                        or None if never set.
    normalized_eps_N : gate B's normalized EPS benchmark at year cfg_N (same figure the
                        neutral-level truncation gate already computes).

    Returns a dict with verdict MISSING | REVIEW | PASS. Callers that want the "no escape
    hatch for a ratio nobody set" behavior should check for MISSING themselves -- this
    function only reports, it does not raise or exit.
    """
    if ratio is None:
        return {"verdict": "MISSING", "ratio": None, "normalized_eps_N": normalized_eps_N,
                "implied_dps": None, "implied_retained_ps": None,
                "reason": ("terminal.payout_ratio is not set — the continuing period has no "
                           "forecaster-owned distribution policy")}

    if not (isinstance(normalized_eps_N, (int, float)) and normalized_eps_N > 0):
        return {"verdict": "REVIEW", "ratio": ratio, "normalized_eps_N": normalized_eps_N,
                "implied_dps": None, "implied_retained_ps": None,
                "reason": (f"normalized EPS at the stop year is {normalized_eps_N!r} — zero, "
                           "negative, or unavailable — so no payout ratio is a coherent "
                           "assertion about the continuing period")}

    dps = ratio * normalized_eps_N
    retained = normalized_eps_N - dps
    return {"verdict": "PASS", "ratio": ratio, "normalized_eps_N": normalized_eps_N,
            "implied_dps": dps, "implied_retained_ps": retained,
            "reason": (f"dividends-only payout {ratio:.1%} of normalized EPS "
                       f"{normalized_eps_N:.4f}/sh -> terminal DPS {dps:.4f}/sh, "
                       f"retained {retained:.4f}/sh")}


def format_report(rep, reviewed=False):
    tag = "  [REVIEWED by analyst]" if reviewed and rep["verdict"] != "PASS" else ""
    return f"[terminal] payout guard {rep['verdict']}: {rep['reason']}{tag}"
