#!/usr/bin/env python3
"""fact_sheet.py — emit <T>_fact_sheet.csv: trailing growth (5/10y CAGR) + return metrics
+ DuPont, assembled from a recalculated engine workbook. Feeds cockpit tab 9 / the AI Fact
Sheet (COCKPIT blueprint 20260721-2203, task 3c).

Reuses dupont_extract for the ratios (no second implementation of DuPont / RNOA / ROCE) and
adds the trailing CAGRs + a reported-basis ROIC. Output is a long field,value file (like
company_<T>.csv); rates are decimals.

Fail-SOFT per metric: a metric that cannot be computed (CAGR across a sign change or a
non-positive base, too little history, a missing line) is emitted BLANK rather than aborting
the run. A fact-sheet metric being unavailable is not a data-integrity break — unlike the
four-method tie, which stays fail-loud upstream.
"""
import csv
import os

import dupont_extract as DP


def _cagr(series, y_latest, years_back):
    """Compound annual growth from year (y_latest - years_back) to y_latest, or None.
    Undefined (None) across a sign change or a non-positive base — never a fabricated rate."""
    if y_latest is None:
        return None
    v0 = series.get(y_latest)
    vb = series.get(y_latest - years_back)
    if not (isinstance(v0, (int, float)) and isinstance(vb, (int, float))):
        return None
    if v0 <= 0 or vb <= 0:
        return None
    return (v0 / vb) ** (1.0 / years_back) - 1.0


def compute_fact_sheet(engine_path, ticker):
    import openpyxl
    wb = openpyxl.load_workbook(engine_path, data_only=True)
    IS, BS = wb["Income Statement"], wb["Balance Sheet"]

    rev = DP._year_series(IS, DP.IS_HDR, "Total Revenue")
    oi = DP._year_series(IS, DP.IS_HDR, "Operating Income")
    eps = DP._year_series(IS, DP.IS_HDR, "Diluted EPS")
    ebt = DP._year_series(IS, DP.IS_HDR, "Pretax Income")
    tax = DP._year_series(IS, DP.IS_HDR, "Tax Provision")
    assets = DP._year_series(BS, DP.BS_HDR, "Total Assets")   # noqa: F841 (kept for clarity/parity)
    equity = DP._year_series(BS, DP.BS_HDR, "Common Stock Equity")
    debt = DP._year_series(BS, DP.BS_HDR, "Total Debt")

    yrs = sorted(rev)
    y = yrs[-1] if yrs else None

    dd = DP.compute_dupont(engine_path, ticker)
    cl, rf = dd["classic"], dd["reformulated"]

    def _last(block, key):
        vals = block.get(key) or []
        return vals[-1] if vals else None

    # reported-basis ROIC (latest): NOPAT / (total debt + equity), NOPAT = OI * (1 - eff_tax)
    roic = None
    if y is not None and isinstance(oi.get(y), (int, float)):
        eff_tax = None
        if isinstance(ebt.get(y), (int, float)) and ebt.get(y) not in (None, 0) \
                and isinstance(tax.get(y), (int, float)):
            eff_tax = tax[y] / ebt[y]
        if eff_tax is not None:
            nopat = oi[y] * (1.0 - eff_tax)
            ic = (debt.get(y) or 0.0) + (equity.get(y) or 0.0)
            roic = (nopat / ic) if ic else None

    return [
        ("ticker", ticker),
        ("fiscal_year", y),
        ("rev_cagr_5y", _cagr(rev, y, 5)),
        ("rev_cagr_10y", _cagr(rev, y, 10)),
        ("eps_cagr_5y", _cagr(eps, y, 5)),
        ("eps_cagr_10y", _cagr(eps, y, 10)),
        ("oi_cagr_5y", _cagr(oi, y, 5)),
        ("oi_cagr_10y", _cagr(oi, y, 10)),
        ("roe_reported", _last(cl, "roe_3step")),
        ("rnoa_econ", _last(rf, "rnoa")),
        ("roce_econ", _last(rf, "roce")),
        ("roic_reported", roic),
        ("net_profit_margin", _last(cl, "net_profit_margin")),
        ("asset_turnover", _last(cl, "asset_turnover")),
        ("equity_multiplier", _last(cl, "equity_multiplier")),
        ("flev_econ", _last(rf, "flev")),
        ("nbc_econ", _last(rf, "nbc")),
        ("spread_econ", _last(rf, "spread")),
    ]


def write_fact_sheet(engine_path, ticker, out_dir):
    fields = compute_fact_sheet(engine_path, ticker)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{ticker}_fact_sheet.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "value"])
        for k, v in fields:
            w.writerow([k, "" if v is None else v])
    return f"{ticker}_fact_sheet.csv"


if __name__ == "__main__":
    import sys
    eng = sys.argv[1]
    tk = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
    print("wrote", write_fact_sheet(eng, tk, "outputs"))
    for k, v in compute_fact_sheet(eng, tk):
        print(f"  {k:20s} {v}")
