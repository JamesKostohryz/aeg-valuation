#!/usr/bin/env python3
"""disclose.py — Option A disclosures layered on the tied base valuation.

The sealed engine values equity on a BOOK-net-debt basis and ties all four methods
(AEG=RIV=FCFE=FCFF) to machine precision. Two V1-Plus effects are surfaced as
explicit, disclosed lines that never disturb that tie:

  1. Debt capital gain (market value of debt). Because the engine subtracts BOOK net
     debt to bridge enterprise->equity, and the true claim ahead of equity is the
     MARKET value of debt, equity picks up (book NFO - market NFO). A one-time, anchor
     level adjustment, added straight to equity value.

REMOVED 2026-08-19 - THE OLD IDIOSYNCRATIC HAIRCUT. A second disclosed line used to sit here:
an option-implied, variance-based firm-specific premium, measured by bumping the engine's cost
of equity by a `finrate_idio` series and reading the equity-value difference. It is DELETED, on
James's explicit ruling of 2026-08-18 ("Get rid of that and implement what we decided").

Three reasons, and the third settles it:
  * It is not part of the company-premium design that was actually approved. That design is a
    downside-volatility level fading on a measured half-life, a de-meaned credit-curve
    steepening term, and an obsolescence shelf. None of it is this.
  * James did not recognise it. A line that removes 17% of Coca-Cola's value - $6.80 a share -
    and that the author of the methodology cannot account for, is not a disclosure.
  * It moved the disclosed figure while the tied base carried none of it. A number that changes
    one published total and not the other is indefensible whichever way round it runs, because
    the two are meant to be the same valuation seen from two angles.

It was NOT unified with the new construction and NOT kept as a diagnostic; both were considered
and both rejected in the same ruling. `repoint_rates.set_idio` survives only because
`apply_erp_override` uses it to ZERO the hook, which is now that hook's sole purpose.

Disclosed bridge (per share):
    base equity (book debt, tied)
      + debt capital gain            = (book NFO - market NFO) / shares
    = adjusted equity (market debt)

NOTE (V2, SCHEDULED — built and template-verified, committed 2026-08-12, not yet fleet-run):
this is the tie-preserving disclosure. The FULLER treatment — re-levering the cost of equity on
leverage (pure Modigliani-Miller Proposition II, no tax adjustment; r_u solved once at the
anchor; leverage via the anchor market-to-book multiple applied to the model's own driven book
equity, D(t)/(CSE(t) x E_market,0/CSE_0)) and re-establishing NOA=CSE+NFO on the disclosed
(market-debt-adjusted) figure — is V2. A working hook, `patch_relever_v2.py` (this repository,
root), has been built and proven, by a real LibreOffice recalculation of the template's own
base-company fixture, to leave the four-method tie unaffected hook-off vs. hook-on while equity
value moves. It has NOT yet been run on a real company. James ruled 2026-08-12: schedule it as
the next GATED item in the product plan (after D1 in the open defect register), not an
indefinite deferral. See `docs/AEG-V2-Relever-Proposal-2026-08-12.md` and
`docs/AEG-V2-Relever-BUILT-Verification-2026-08-12.md` (this repository) for the proposal, the
build, and the verification/decision record.
"""
import shutil, openpyxl
import aeg_engine as AE
import repoint_rates as RP


def _nm(wb, name):
    dn = wb.defined_names.get(name)
    if not dn:
        return None
    ref = str(dn.value if hasattr(dn, "value") else dn.attr_text).replace("$", "").replace("'", "")
    sh, cell = ref.split("!")
    try:
        return wb[sh][cell].value
    except Exception:
        return None


def _read_engine(path, price):
    r = AE.read_results(path, price=price)
    wb = openpyxl.load_workbook(path, data_only=True)
    return {
        "equity": r["equity_value"],
        "enterprise": r["enterprise_value"],
        "tie": r["max_identity_tie"],
        "audit": r["audit_status"],
        "shares": _nm(wb, "anchor_shares0"),
        "book_nfo": _nm(wb, "anchor_real_nfo0"),   # real book NFO used in the bridge
        "book_debt": _nm(wb, "in_debt"),           # book (carrying) value of debt, engine units
        "cash": _nm(wb, "in_cash"),
        "sti": _nm(wb, "in_sti"),
        "coe_lr": _nm(wb, "val_rhoe_lr"),          # long-run real COE (INDEX(finrate_coe, 30) - the 30y tenor point on the term structure). The neutral cap rate/anchor P/E is DERIVED from this, not the reverse.
    }


def _resolve_debt_scale(market_debt_feed, book_debt_engine, scale):
    """Bring the feed's market value of debt into the engine's monetary units. The
    engine's scale is company-agnostic but not $1 (e.g. $ trillions); the feed is in
    its own units ($ millions). If `scale` (feed units per engine unit) is given, use
    it; else infer the nearest power of 10 that lands market debt near book debt. A
    fail-loud gate then rejects any residual unit error (or an implausible mark)."""
    import math
    if scale is None:
        ratio = market_debt_feed / book_debt_engine
        scale = 10.0 ** round(math.log10(ratio)) if ratio > 0 else 1.0
        inferred = True
    else:
        inferred = False
    market_debt_engine = market_debt_feed / scale
    r = market_debt_engine / book_debt_engine
    if not (0.3 <= r <= 1.3):
        raise ValueError(
            f"[disclose] market/book debt ratio {r:.3f} implausible after unit scaling "
            f"(scale={scale:g}, {'inferred' if inferred else 'explicit'}). "
            f"Check that market_value_of_debt units match the engine, or pass debt_scale.")
    return market_debt_engine, scale, inferred


def disclose(engine_path, feed, price=None, recalc=None, sens_path=None, debt_scale=None):
    """Run the base + idiosyncratic-sensitivity valuations and assemble the disclosed
    bridge. `engine_path` must already be built + re-pointed (idio hook installed, 0).
    `recalc` is the LibreOffice recalc callable (recalc_lo.recalc). `debt_scale` is the
    feed-units-per-engine-unit divisor for market value of debt (auto-inferred if None).
    Returns a dict."""
    if recalc is None:
        from recalc_lo import recalc as recalc
    # `sens_path` is retained in the signature so existing callers do not break, but it is
    # UNUSED since the idiosyncratic sensitivity run was deleted (2026-08-19). Nothing writes a
    # _idiosens workbook any more.
    _ = sens_path

    # --- base (idiosyncratic = 0): the tied headline
    recalc(engine_path)
    base = _read_engine(engine_path, price)
    if base["shares"] in (None, 0):
        raise ValueError("[disclose] could not read anchor_shares0 from engine")

    # --- 1) debt capital gain (market value of debt), anchor level, per share.
    #   Marking touches only the DEBT; cash and ST-investments are identical on the book
    #   and market NFO, so they cancel and the gain is simply (book debt - market debt).
    if "company" not in feed or "market_value_of_debt" not in feed.get("company", {}):
        raise ValueError("[disclose] feed has no market_value_of_debt (bonded issuer required)")
    market_debt_engine, scale_used, inferred = _resolve_debt_scale(
        feed["company"]["market_value_of_debt"], float(base["book_debt"]), debt_scale)
    debt_gain_agg = float(base["book_debt"]) - market_debt_engine   # +ve when debt below book
    debt_gain_ps = debt_gain_agg / float(base["shares"])
    market_nfo = market_debt_engine - float(base["cash"]) - float(base["sti"])

    # --- 2) DELETED 2026-08-19: the idiosyncratic-haircut sensitivity run. See the header.
    #   The entire second workbook recalculation goes with it, so this function now recalculates
    #   once rather than twice.

    # --- 3) depreciation penalty to the anchor (Increment 1: the measurement defect).
    #   Historical-cost depreciation understates the real cost of maintaining capacity, so
    #   normal (distributable) earnings are OVERSTATED by (t x shortfall)/shares each year.
    #   That is a perpetual real shortfall; capitalize it at the long-run real COE c (= the
    #   neutral cap rate, which is derived FROM this rate, not the reverse) and take it straight off the anchor. Anchor-level and
    #   tie-preserving, exactly like the debt mark — it never disturbs the four-method tie.
    import scorecard as SC
    _dp = SC.depreciation_penalty(engine_path)          # engine already recalced just above
    penalty_annual = _dp.get("penalty_annual")
    c = base.get("coe_lr")
    dep_anchor_penalty_ps = None
    dep_basis = None

    #  Stage B1: if the engine forecasts cash tax on the historical-cost depreciation basis,
    #  years 1..N are already inside the tied valuation via EPS -> AEG. Charging the old flat
    #  perpetuity on top would DOUBLE-COUNT. All that is missing is the permanent step from
    #  the year-N wedge to the steady-state wedge, because the engine truncates at N and so
    #  assumes the year-N wedge persists for ever. Charge only that step.
    #  On a pre-Stage-B1 engine the helper returns None and we fall back to the flat
    #  perpetuity, so this is backward compatible.
    _ts = SC.depreciation_terminal_step(engine_path)
    if _ts.get("terminal_step_ps") is not None:
        dep_anchor_penalty_ps = _ts["terminal_step_ps"]
        dep_basis = "terminal-step (years 1..N priced in-engine)"
    elif penalty_annual is not None and c and base["shares"]:
        dep_anchor_penalty_ps = (penalty_annual / float(base["shares"])) / c
        dep_basis = "flat perpetuity at anchor (pre-Stage-B1 engine)"

    adjusted = base["equity"] + debt_gain_ps - (dep_anchor_penalty_ps or 0.0)
    return {
        "ticker": feed.get("ticker"),
        "base_equity_ps": base["equity"],
        "base_tie": base["tie"],
        "base_audit": base["audit"],
        "shares": base["shares"],
        "book_nfo": base["book_nfo"],
        "book_debt": base["book_debt"],
        "market_debt_engine": market_debt_engine,
        "market_nfo": market_nfo,
        "debt_scale": scale_used,
        "debt_scale_inferred": inferred,
        "debt_capital_gain_ps": debt_gain_ps,
        "debt_capital_gain_agg": debt_gain_agg,
        "depreciation_penalty_annual": penalty_annual,
        "depreciation_anchor_penalty_ps": dep_anchor_penalty_ps,
        "depreciation_basis": dep_basis,
        "depreciation_wedge_N": _ts.get("wedge_N"),
        "depreciation_wedge_steadystate": _ts.get("wedge_ss"),
        "coe_longrun": c,
        "adjusted_equity_ps": adjusted,
        "bridge": [
            ("base equity (book debt, tied)", round(base["equity"], 4)),
            (f"- depreciation penalty [{dep_basis or 'n/a'}]", round(-(dep_anchor_penalty_ps or 0.0), 4)),
            ("+ debt capital gain (MV debt)", round(debt_gain_ps, 4)),
            ("= adjusted equity (design basis: dep+debt)", round(adjusted, 4)),
        ],
    }


def format_bridge(d):
    lines = [f"Disclosed valuation bridge — {d['ticker']} ($/share):"]
    for label, val in d["bridge"]:
        lines.append(f"  {val:>10.4f}   {label}")
    lines.append(f"  (base tie {d['base_tie']:.1e}; "
                 f"engine units: book debt {d['book_debt']:.4f}, market debt {d['market_debt_engine']:.4f}, "
                 f"scale {d['debt_scale']:g}{' inferred' if d['debt_scale_inferred'] else ''})")
    return "\n".join(lines)
