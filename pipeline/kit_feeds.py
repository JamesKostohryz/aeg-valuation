#!/usr/bin/env python3
"""kit_feeds.py — the Forecaster-Kit per-ticker data feeds that aren't already produced
elsewhere. EXEC publishes the CSVs to aeg-valuation/outputs; the cockpit assembler renders
them into the Kit markdown. Three feeds:

  <TICKER>_analyst_estimates.csv  (Kit §9)  EODHD Highlights + AnalystRatings. Headline
      fields (target price, rating + buy/hold/sell distribution, consensus EPS current/next
      FY + current/next quarter) are required; granular fields (consensus revenue, per-line
      analyst counts, revision detail) are nullable — emitted blank, never fail-closed.
  <TICKER>_aeg_momentum.csv       (Kit §11) Ohlson-Juettner abnormal-earnings-growth history
      against the ticker's own time-varying nominal COE (coe_history_<T>_annual.csv). GATED
      fail-closed: if that COE series is absent the feed is not produced (raises -> the extract
      fail-soft loop skips it -> the cockpit gate renders "not yet available").
  <TICKER>_growth_trend.csv       (Kit §7+§12) mechanical CAGRs + rolling-window averages off
      the reported statements, plus a TTM snapshot from EODHD Highlights (best-effort).

Every feed carries a data_as_of stamp, same freshness convention as the other cockpit feeds.
Fail-soft per feed at the extract layer; internally each metric is fail-soft (blank, never a
fabricated number) EXCEPT the AEG coe_history gate, which is deliberately fail-closed.
"""
import csv
import os

import dupont_extract as DP

IS_HDR = DP.IS_HDR   # reported Income Statement header row (3)
BS_HDR = DP.BS_HDR   # reported Balance Sheet header row (3)
CF_HDR = 3           # reported Cash Flow header row (matches extract STATEMENT_DUMPS)


def _safe(n, d):
    return (n / d) if (isinstance(n, (int, float)) and isinstance(d, (int, float)) and d) else None


def _cagr(series, y_latest, years_back):
    """Compound annual growth from (y_latest - years_back) to y_latest, or None. Undefined
    across a sign change or a non-positive base — never a fabricated rate (mirrors fact_sheet)."""
    if y_latest is None:
        return None
    v0, vb = series.get(y_latest), series.get(y_latest - years_back)
    if not (isinstance(v0, (int, float)) and isinstance(vb, (int, float))):
        return None
    if v0 <= 0 or vb <= 0:
        return None
    return (v0 / vb) ** (1.0 / years_back) - 1.0


def _mean(vals):
    xs = [v for v in vals if isinstance(v, (int, float))]
    return (sum(xs) / len(xs)) if xs else None


def _window(series_by_year, years_sorted, n):
    """The last n values of a {year:val} series over the sorted year axis (skips missing)."""
    yrs = years_sorted[-n:] if n else years_sorted
    return [series_by_year.get(y) for y in yrs]


def _load_statements(engine_path):
    """Return the reported IS/BS/CF year-series needed by the kit feeds, straight from the
    recalculated workbook (same source dupont_extract reads — no second implementation)."""
    import openpyxl
    wb = openpyxl.load_workbook(engine_path, data_only=True)
    IS, BS, CF = wb["Income Statement"], wb["Balance Sheet"], wb["Cash Flow"]
    d = {
        "revenue": DP._year_series(IS, IS_HDR, "Total Revenue"),
        "gross_profit": DP._year_series(IS, IS_HDR, "Gross Profit"),
        "operating_income": DP._year_series(IS, IS_HDR, "Operating Income"),
        "net_income": DP._year_series(IS, IS_HDR, "Net Income Common Stockholders"),
        "diluted_eps": DP._year_series(IS, IS_HDR, "Diluted EPS"),
        "assets": DP._year_series(BS, BS_HDR, "Total Assets"),
        "equity": DP._year_series(BS, BS_HDR, "Common Stock Equity"),
    }
    # dividends to common: prefer the positive "Cash Dividends Paid"; fall back to the signed
    # "Common Stock Dividend Paid" (take magnitude). Blank years -> absent (treated as 0 by AEG).
    div = DP._year_series(CF, CF_HDR, "Cash Dividends Paid")
    if not div:
        signed = DP._year_series(CF, CF_HDR, "Common Stock Dividend Paid")
        div = {y: abs(v) for y, v in signed.items()}
    d["dividends"] = {y: abs(v) for y, v in div.items()}
    return d


# ---------------------------------------------------------------- §11 AEG momentum
def _read_coe_history(out_dir, ticker):
    """{year:int -> nominal COE as a DECIMAL} from coe_history_<T>_annual.csv (col coe_nom_dec,
    stored in PERCENT points e.g. 11.5 -> 0.115). Returns {} if the file is absent."""
    path = os.path.join(out_dir, f"coe_history_{ticker}_annual.csv")
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                out[int(str(row["yr"]).strip())] = float(row["coe_nom_dec"]) / 100.0
            except (TypeError, ValueError, KeyError):
                continue
    return out


def compute_aeg_momentum(engine_path, ticker, out_dir):
    """Ohlson-Juettner AEG history vs the ticker's own time-varying nominal COE. GATED: raises
    if coe_history_<T>_annual.csv is absent (fail-closed, per COCKPIT §11)."""
    coe = _read_coe_history(out_dir, ticker)
    if not coe:
        raise FileNotFoundError(
            f"coe_history_{ticker}_annual.csv not in {out_dir}: AEG momentum is gated on the "
            f"time-varying nominal COE series (dispatch real-yields coe-history for {ticker}).")
    st = _load_statements(engine_path)
    E, D = st["net_income"], st["dividends"]
    years = sorted(y for y in E if (y - 1) in E and y in coe)
    rows = []
    for y in years:
        e_t, e_p = E[y], E[y - 1]
        d_p = D.get(y - 1, 0.0) or 0.0
        r = coe[y]
        normal_e = (1 + r) * e_p - r * d_p
        aeg = (e_t + r * d_p) - (1 + r) * e_p
        rows.append({
            "period": y, "E": e_t, "E_prev": e_p, "D_prev": d_p, "r_nom": r,
            "nominal_growth_pct": _safe(e_t, e_p) - 1 if _safe(e_t, e_p) is not None else None,
            "normal_growth_pct": _safe(normal_e, e_p) - 1 if _safe(normal_e, e_p) is not None else None,
            "aeg": aeg, "aeg_pct_prior": _safe(aeg, e_p),
            "rore": _safe(e_t - e_p, e_p - d_p),
            "rore_minus_r": (_safe(e_t - e_p, e_p - d_p) - r) if _safe(e_t - e_p, e_p - d_p) is not None else None,
        })
    return rows


_AEG_COLS = ["table", "period", "n_years", "E", "E_prev", "D_prev", "r_nom",
             "nominal_growth_pct", "normal_growth_pct", "aeg", "aeg_pct_prior",
             "rore", "rore_minus_r", "cum_aeg", "data_as_of"]


def write_aeg_momentum(engine_path, ticker, out_dir, data_as_of):
    """Write <TICKER>_aeg_momentum.csv: one single_year row per fiscal year plus trailing_5y /
    trailing_10y summary rows (window means; cum_aeg = summed abnormal $ over the window)."""
    rows = compute_aeg_momentum(engine_path, ticker, out_dir)  # raises if coe_history absent
    out_rows = []
    for r in rows:
        out_rows.append({"table": "single_year", "period": r["period"], "n_years": "",
                         "E": r["E"], "E_prev": r["E_prev"], "D_prev": r["D_prev"],
                         "r_nom": r["r_nom"], "nominal_growth_pct": r["nominal_growth_pct"],
                         "normal_growth_pct": r["normal_growth_pct"], "aeg": r["aeg"],
                         "aeg_pct_prior": r["aeg_pct_prior"], "rore": r["rore"],
                         "rore_minus_r": r["rore_minus_r"], "cum_aeg": "",
                         "data_as_of": data_as_of})
    for n in (5, 10):
        w = rows[-n:] if len(rows) >= 1 else []
        if not w:
            continue
        cum = _mean([r["aeg"] for r in w])
        cum_sum = sum(r["aeg"] for r in w if isinstance(r["aeg"], (int, float)))
        out_rows.append({"table": f"trailing_{n}y", "period": f"trailing_{n}y",
                         "n_years": len(w), "E": "", "E_prev": "", "D_prev": "",
                         "r_nom": _mean([r["r_nom"] for r in w]),
                         "nominal_growth_pct": _mean([r["nominal_growth_pct"] for r in w]),
                         "normal_growth_pct": _mean([r["normal_growth_pct"] for r in w]),
                         "aeg": cum, "aeg_pct_prior": _mean([r["aeg_pct_prior"] for r in w]),
                         "rore": _mean([r["rore"] for r in w]),
                         "rore_minus_r": _mean([r["rore_minus_r"] for r in w]),
                         "cum_aeg": cum_sum, "data_as_of": data_as_of})
    path = os.path.join(out_dir, f"{ticker}_aeg_momentum.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_AEG_COLS)
        w.writeheader()
        for row in out_rows:
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in _AEG_COLS})
    return f"{ticker}_aeg_momentum.csv"


# ---------------------------------------------------------------- §7 + §12 growth / trend
def _ratio_series(st, key):
    """Derived per-year ratio {year:val} for the rolling-trajectory metrics."""
    rev, gp, oi, ni = st["revenue"], st["gross_profit"], st["operating_income"], st["net_income"]
    assets, eq = st["assets"], st["equity"]
    if key == "revenue_growth":
        yrs = sorted(rev)
        return {y: _safe(rev[y], rev.get(y - 1)) - 1
                for y in yrs if _safe(rev.get(y), rev.get(y - 1)) is not None}
    src = {"gross_margin": (gp, rev), "operating_margin": (oi, rev), "net_margin": (ni, rev),
           "roe": (ni, eq), "asset_turnover": (rev, assets), "equity_multiplier": (assets, eq)}[key]
    num, den = src
    return {y: _safe(num.get(y), den.get(y)) for y in sorted(num) if _safe(num.get(y), den.get(y)) is not None}


def _eodhd_ttm(ticker, api_key):
    """Best-effort TTM snapshot from EODHD Highlights. Returns {} on any failure (§7 TTM is a
    convenience overlay, not a gate)."""
    if not api_key:
        return {}
    try:
        import eodhd_puller as EP
        h = EP._http_json(f"{EP.EODHD_BASE}/fundamentals/{EP._eodhd_symbol(ticker)}"
                          f"?api_token={api_key}&fmt=json&filter=Highlights") or {}
    except Exception as e:
        print(f"[growth_trend] TTM snapshot skipped ({type(e).__name__}: {e})")
        return {}
    rev_ttm, gp_ttm = h.get("RevenueTTM"), h.get("GrossProfitTTM")
    return {"revenue_ttm": rev_ttm, "eps_ttm": h.get("DilutedEpsTTM"),
            "gross_margin_ttm": _safe(gp_ttm, rev_ttm), "operating_margin_ttm": h.get("OperatingMarginTTM"),
            "net_margin_ttm": h.get("ProfitMargin"), "roe_ttm": h.get("ReturnOnEquityTTM"),
            "roa_ttm": h.get("ReturnOnAssetsTTM")}


_CAGR_METRICS = ["revenue", "gross_profit", "operating_income", "net_income", "diluted_eps"]
_ROLL_METRICS = ["revenue_growth", "gross_margin", "operating_margin", "net_margin",
                 "roe", "asset_turnover", "equity_multiplier"]


def write_growth_trend(engine_path, ticker, out_dir, data_as_of, api_key=None):
    """Write <TICKER>_growth_trend.csv in tidy long form (block, metric, window, value): §7
    CAGRs (3/5/10y) + a best-effort TTM snapshot, and §12 rolling-window averages (1/5/10y).
    Workbook-only blocks always emit; the TTM block is skipped if EODHD is unreachable."""
    st = _load_statements(engine_path)
    if api_key is None:
        api_key = os.environ.get("EODHD_API_KEY")
    out = []  # (block, metric, window, value)

    # §7 CAGRs
    for m in _CAGR_METRICS:
        s = st[m]
        y = max(s) if s else None
        for n in (3, 5, 10):
            out.append(("cagr", m, f"{n}y", _cagr(s, y, n)))

    # §7 TTM snapshot (best-effort)
    for m, v in _eodhd_ttm(ticker, api_key).items():
        out.append(("ttm", m, "ttm", v))

    # §12 rolling-window averages
    for m in _ROLL_METRICS:
        s = _ratio_series(st, m)
        yrs = sorted(s)
        for n in (1, 5, 10):
            out.append(("rolling", m, f"{n}y", _mean(_window(s, yrs, n))))

    path = os.path.join(out_dir, f"{ticker}_growth_trend.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["block", "metric", "window", "value", "data_as_of"])
        for block, metric, window, value in out:
            w.writerow([block, metric, window, "" if value is None else value, data_as_of])
    return f"{ticker}_growth_trend.csv"


# ---------------------------------------------------------------- §9 analyst estimates
def write_analyst_estimates(ticker, out_dir, data_as_of, api_key=None):
    """Write <TICKER>_analyst_estimates.csv (field,value,data_as_of). Headline fields required;
    granular consensus-revenue / revision fields are nullable (emitted blank). Raises if EODHD
    is unreachable (the extract fail-soft loop then skips it)."""
    if api_key is None:
        api_key = os.environ.get("EODHD_API_KEY")
    if not api_key:
        raise RuntimeError("EODHD_API_KEY not set: cannot build analyst-estimate feed.")
    import eodhd_puller as EP
    sym = EP._eodhd_symbol(ticker)
    base = f"{EP.EODHD_BASE}/fundamentals/{sym}?api_token={api_key}&fmt=json&filter="
    gen = EP._http_json(base + "General") or {}
    hl = EP._http_json(base + "Highlights") or {}
    ar = EP._http_json(base + "AnalystRatings") or {}

    dist = {k: ar.get(k) for k in ("StrongBuy", "Buy", "Hold", "Sell", "StrongSell")}
    n_analysts = sum(v for v in dist.values() if isinstance(v, (int, float))) or None
    fields = [
        ("ticker", ticker), ("company", gen.get("Name")), ("source", "eodhd:Highlights+AnalystRatings"),
        ("eodhd_updated_at", gen.get("UpdatedAt")),
        ("rating", ar.get("Rating")),
        ("target_price", ar.get("TargetPrice") if ar.get("TargetPrice") is not None
         else hl.get("WallStreetTargetPrice")),
        ("wall_street_target_price", hl.get("WallStreetTargetPrice")),
        ("strong_buy", dist["StrongBuy"]), ("buy", dist["Buy"]), ("hold", dist["Hold"]),
        ("sell", dist["Sell"]), ("strong_sell", dist["StrongSell"]), ("analyst_count", n_analysts),
        ("eps_est_current_year", hl.get("EPSEstimateCurrentYear")),
        ("eps_est_next_year", hl.get("EPSEstimateNextYear")),
        ("eps_est_current_quarter", hl.get("EPSEstimateCurrentQuarter")),
        ("eps_est_next_quarter", hl.get("EPSEstimateNextQuarter")),
        ("most_recent_quarter", hl.get("MostRecentQuarter")),
        ("eps_ttm", hl.get("DilutedEpsTTM")), ("pe_ratio", hl.get("PERatio")),
        # granular / nullable — emitted blank when EODHD has no value on our plan tier
        ("consensus_revenue_current_year", hl.get("RevenueEstimateCurrentYear")),
        ("consensus_revenue_next_year", hl.get("RevenueEstimateNextYear")),
    ]
    path = os.path.join(out_dir, f"{ticker}_analyst_estimates.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "value", "data_as_of"])
        for k, v in fields:
            w.writerow([k, "" if v is None else v, data_as_of])
    return f"{ticker}_analyst_estimates.csv"


if __name__ == "__main__":
    import sys
    eng = sys.argv[1] if len(sys.argv) > 1 else "SLIM_OUT.xlsx"
    tk = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
    od = sys.argv[3] if len(sys.argv) > 3 else "outputs"
    stamp = "run-standalone"
    print("growth_trend:", write_growth_trend(eng, tk, od, stamp))
    try:
        print("aeg_momentum:", write_aeg_momentum(eng, tk, od, stamp))
    except Exception as e:
        print("aeg_momentum SKIPPED:", e)
    try:
        print("analyst_estimates:", write_analyst_estimates(tk, od, stamp))
    except Exception as e:
        print("analyst_estimates SKIPPED:", e)


# 2026-07-31 (EXEC#6): coe_history_{POOL,HD}_annual.csv published to outputs/ (from real-yields
# runs #4/#5) -> unlocks the §11 AEG-momentum feed for POOL and HD (previously AAPL-only gate).
