#!/usr/bin/env python3
"""
idio/market_coe_history.py — the market's real cost of equity, monthly, on the CURRENT method.

THIS SUPERSEDES `real-yields/history/FINAL_decomposition_v4_1877_2026.csv` AND EVERYTHING BUILT
ON IT. James's instruction, 2026-08-20: "whatever existed before will be completely superseded by
what we are doing now."

WHAT WAS WRONG WITH THE OLD SERIES, measured rather than asserted. For the same month, June 2026:

    FINAL_decomposition_v4_1877_2026.csv    eff_erp  3.887
    history/ERP_effective_latest.csv (live) eff_erp  3.370

**A 0.52 percentage point break between two published series describing the same object**, with
no splice logic anywhere and nothing to notice it. `outputs/coe_history_KO.csv` and the live
`coe_v2_KO_latest_annual.csv` were on two different equity-risk-premium levels at the same time.

Three further things about that file, all verified:
  * NOTHING BUILDS IT. It was committed once and never regenerated. The only code that mentions
    it reads it.
  * `coe_history.py` reads it from a hardcoded `/tmp/calib/` path.
  * Its pre-1995 `cost` column follows a straight line from 2.50 to 1.50 that exists nowhere in
    any code, and the live `cost_of_year()` returns a COMPLEX NUMBER for 1877 because it raises a
    negative base to a fractional power.

WHAT THIS BUILDS INSTEAD, from current components only:

    real_coe_market(t) = real_rf(t) + market_erp(t)

  real_rf   `real-yields/history/real_yield_curve_v3_MASTER.csv` — 1,698 monthly rows,
            1876-09 to 2026-06, five knots, with a `tips_source` provenance flag on EVERY cell
            (market TIPS, Groen synthetic, breakeven-implied, or regime-extrapolated). This is a
            RATE curve, not a risk construction, and it is reused unchanged: the supersession is
            of the ERP side.

  market_erp  from `idio/market_semidev_bridge.py` — the market's own downside semi-deviation
            mapped to a VIX-equivalent on the pre-registered two-moment bridge, then priced by
            the Martin variance form. Live VIX1Y is used wherever it exists (2007 onward), the
            bridge before, and a five-year blend between.

WHAT IS DELIBERATELY NOT HERE.

  THE TERM STRUCTURE BEYOND ONE YEAR. The bridge maps the one-year point. Mapping tenors 2..10
  needs a shape calibration on the overlap, which is a SECOND calibration and it has not been
  pre-registered. Doing it here, after seeing this data, is exactly the discipline this project
  keeps breaking. It is the declared next step, not a gap somebody forgot.

  THE COMPANY LEG. `real_coe_i = real_coe_market + company_premium_i` needs, at every historical
  date, that company's own semi-deviation AND the cap-weighted average across the index —
  which needs the whole universe's price history and historical index membership. The method is
  already correct (`idio/semidev.py` and `idio/erp.py` are the production statistic and already
  work backwards); it is the DATA that is the work. Scoped, not started.

    python3 idio/market_coe_history.py --write

NOT A VALUATION.
"""
from __future__ import annotations

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import market_semidev_bridge as BR      # noqa: E402


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


REAL_CURVE = _arg("--real-curve", os.path.join(
    ROOT, "data", "market_history", "real_yield_curve_v3_MASTER.csv"))
OUT = _arg("--out", os.path.join(ROOT, "outputs", "market_coe_history.csv"))
KNOTS = (1, 5, 10, 20, 30)

SUPERSEDES = "real-yields/history/FINAL_decomposition_v4_1877_2026.csv"


class HistoryInputMissing(RuntimeError):
    pass


def load_real_curve(path=None):
    """The reconstructed real-rate term structure, monthly, with its provenance flags kept."""
    p = path or REAL_CURVE
    if not os.path.exists(p):
        raise HistoryInputMissing(
            "%s is missing. It is real-yields' history/real_yield_curve_v3_MASTER.csv and it is "
            "the only historical real-rate curve with a provenance flag on every cell. Without "
            "it the real leg of the historical cost of equity has no honest source." % p)
    out = {}
    for r in csv.DictReader(open(p)):
        d = r["date"][:10]
        row = {}
        for k in KNOTS:
            try:
                row["real%d" % k] = float(r["real%d_tips" % k])
            except (KeyError, TypeError, ValueError):
                row["real%d" % k] = None
            row["src%d" % k] = r.get("tips_source%d" % k, "")
        out[d] = row
    return out


def month_end_pairs(rows):
    """One observation a month: the last available day of each calendar month."""
    by = {}
    for r in rows:
        by[r["date"][:7]] = r          # later days overwrite earlier ones
    return by


def build(log=print):
    res = BR.calibrate_and_validate(log=lambda *a: None)
    daily = BR.reconstruct(res)
    monthly = month_end_pairs(daily)
    curve = load_real_curve()

    rows = []
    for ym in sorted(set(monthly) & set(k[:7] for k in curve)):
        b = monthly[ym]
        # the real curve is stamped on the first of the month; match on year-month
        ck = next((k for k in curve if k[:7] == ym), None)
        if ck is None:
            continue
        c = curve[ck]
        erp = b["martin_erp_pct"]
        rec = dict(date=b["date"], month=ym,
                   market_semidev=b["market_semidev"],
                   vix_equiv=b["vix_equiv"], erp_source=b["source"],
                   market_erp_1y_pct=erp)
        for k in KNOTS:
            rec["real_rf_%dy_pct" % k] = c["real%d" % k]
            rec["real_rf_%dy_source" % k] = c["src%d" % k]
        # the cost of equity at the ONE-YEAR point only. See the module docstring: the term
        # structure beyond 1y is a second calibration and is not pre-registered.
        rec["real_coe_1y_pct"] = (None if c["real1"] is None else round(c["real1"] + erp, 6))
        rows.append(rec)

    if not rows:
        raise HistoryInputMissing("no overlap between the bridge and the real-rate curve")
    log("MARKET REAL COST OF EQUITY, monthly, on current components")
    log("  %d months, %s -> %s" % (len(rows), rows[0]["month"], rows[-1]["month"]))
    src = {}
    for r in rows:
        src[r["erp_source"]] = src.get(r["erp_source"], 0) + 1
    log("  ERP source: %s" % ", ".join("%s %d" % kv for kv in sorted(src.items())))
    prov = {}
    for r in rows:
        prov[r["real_rf_1y_source"]] = prov.get(r["real_rf_1y_source"], 0) + 1
    log("  real 1y source: %s" % ", ".join("%s %d" % kv for kv in sorted(prov.items())))
    log("  SUPERSEDES %s" % SUPERSEDES)
    return rows


def main():
    rows = build()
    print()
    print("  month     real_rf_1y   market_erp   real_coe_1y   erp source   rf source")
    for ym in ("1932-06", "1937-10", "1974-10", "1987-12", "2000-03", "2009-03",
               "2020-06", "2026-06"):
        m = [r for r in rows if r["month"] == ym]
        if m:
            r = m[0]
            print("  %-9s %10s   %10.2f   %11s   %-10s   %s"
                  % (ym,
                     ("%.2f" % r["real_rf_1y_pct"]) if r["real_rf_1y_pct"] is not None else "-",
                     r["market_erp_1y_pct"],
                     ("%.2f" % r["real_coe_1y_pct"]) if r["real_coe_1y_pct"] is not None else "-",
                     r["erp_source"], r["real_rf_1y_source"]))
    if "--write" in sys.argv:
        os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
        with open(OUT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("\nWROTE %s -- %d months" % (OUT, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
