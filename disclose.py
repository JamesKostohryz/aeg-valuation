#!/usr/bin/env python3
"""disclose.py — Option A disclosures layered on the tied base valuation.

The sealed engine values equity on a BOOK-net-debt basis and ties all four methods
(AEG=RIV=FCFE=FCFF) to machine precision. Two V1-Plus effects are surfaced as
explicit, disclosed lines that never disturb that tie:

  1. Debt capital gain (market value of debt). Because the engine subtracts BOOK net
     debt to bridge enterprise->equity, and the true claim ahead of equity is the
     MARKET value of debt, equity picks up (book NFO - market NFO). A one-time, anchor
     level adjustment, added straight to equity value.

  2. Idiosyncratic premium (disclosed haircut). The rate feed's option-implied,
     firm-specific premium raises the cost of equity by `idiosyncratic` per tenor. Its
     value impact is measured by a SENSITIVITY run — the engine's COE bumped by the
     idiosyncratic series (finrate_idio) — reading the equity-value difference. The
     sensitivity run still ties internally; the base/headline stays idiosyncratic-free.

Disclosed bridge (per share):
    base equity (book debt, tied)
      + debt capital gain            = (book NFO - market NFO) / shares
      - idiosyncratic haircut        = base equity - equity(COE + idiosyncratic)
    = adjusted equity (market debt, idiosyncratic-disclosed)

NOTE (V2, deferred): this is the tie-preserving disclosure. The FULLER treatment —
re-levering the cost of equity on market leverage (market debt AND market equity) so
the leverage-on-COE channel is captured too, and re-establishing NOA=CSE+NFO — is a
planned V2. See AEG_SYSTEM_ARCHITECTURE_AND_BUILD.md, "V2 backlog".
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
    sens_path = sens_path or engine_path.replace(".xlsx", "_idiosens.xlsx")

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

    # --- 2) idiosyncratic premium (disclosed haircut) via a COE-bump sensitivity run
    shutil.copy(engine_path, sens_path)
    wb = openpyxl.load_workbook(sens_path)
    RP.set_idio(wb, feed["idiosyncratic"])
    wb.save(sens_path)
    recalc(sens_path)
    sens = _read_engine(sens_path, price)
    idio_haircut_ps = base["equity"] - sens["equity"]

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

    adjusted = base["equity"] + debt_gain_ps - idio_haircut_ps - (dep_anchor_penalty_ps or 0.0)
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
        "sens_equity_ps": sens["equity"],
        "sens_tie": sens["tie"],
        "idiosyncratic_haircut_ps": idio_haircut_ps,
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
            ("- idiosyncratic haircut", round(-idio_haircut_ps, 4)),
            ("= adjusted equity (design basis: dep+debt+idio)", round(adjusted, 4)),
        ],
    }


def format_bridge(d):
    lines = [f"Disclosed valuation bridge — {d['ticker']} ($/share):"]
    for label, val in d["bridge"]:
        lines.append(f"  {val:>10.4f}   {label}")
    lines.append(f"  (base tie {d['base_tie']:.1e}, sensitivity tie {d['sens_tie']:.1e}; "
                 f"engine units: book debt {d['book_debt']:.4f}, market debt {d['market_debt_engine']:.4f}, "
                 f"scale {d['debt_scale']:g}{' inferred' if d['debt_scale_inferred'] else ''})")
    return "\n".join(lines)
