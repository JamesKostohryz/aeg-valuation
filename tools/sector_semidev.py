#!/usr/bin/env python3
"""sector_semidev.py — sector risk against market risk, on the production statistic.

THE CONSTRUCTION UNDER TEST (James's sector question, 2026-08-20):

    ERP_sector(front) = market_ERP(front) x semidev_TOTAL_sector / semidev_TOTAL_market

The market's own ratio is exactly 1.0 by construction, so the market carries no premium against
itself. Every sector should land ABOVE 1.0, because a sector is a less diversified portfolio than
the index that contains it. THAT IS THE CLAIM AND IT IS WHAT THIS MEASURES. It is not assumed.

No anchor parameter. No universe. No cap weights. Two price series per sector.

BOTH READINGS ARE COMPUTED. `total` is the raw downside semi-deviation, which is what the market
ERP itself is built on and therefore like-for-like. `residual` strips the market factor first, the
way the COMPANY leg does. They answer different questions and the difference is reported rather
than chosen here.

THE STATISTIC IS IMPORTED. idio/semidev.py supplies the primitives; there is no second
implementation.

  python3 tools/sector_semidev.py --repo /tmp/aeg

NOT A VALUATION.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import json
import math
import os
import statistics as stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "outputs", "2026-08-20-sectors")
SECT = os.path.join(OUT, "gfd_sector_daily.csv")
WINDOW = 700


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--start", default="1991-01-01")
    ap.add_argument("--end", default="2014-10-31")
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(a.repo, "idio"))
    import semidev as SD

    # ---- the market, on the SAME basis as the sector series: a price index, not total return
    d = json.load(open(os.path.join(a.repo, "data", "market_history",
                                    "sp500_daily_1927_2026.json")))
    mdates = d["dates"]
    mclose = [float(x) for x in d["close"]]
    print("market: S&P 500 price index, %d rows %s .. %s" % (len(mdates), mdates[0], mdates[-1]))

    sec = collections.defaultdict(list)
    names = {}
    for r in csv.DictReader(open(SECT)):
        sec[r["gics"]].append((r["date"], float(r["close"])))
        names[r["gics"]] = r["sector"]
    for g in sec:
        sec[g].sort()
    print("sectors: %s\n" % ", ".join("%s %s" % (g, names[g]) for g in sorted(sec)))

    def slice_upto(series, asof, n=WINDOW):
        ds = [x[0] for x in series]
        i = bisect.bisect_right(ds, asof)
        return series[max(0, i - n):i]

    mseries = list(zip(mdates, mclose))

    def total_semidev(series, asof):
        """Raw downside semi-deviation, production blend and lag, via semidev.py's primitives."""
        tot = 0.0
        for yrs, wt in zip(SD.BLEND_WINDOWS, SD.BLEND_WEIGHTS):
            rs, _ = SD.aligned_returns(series, slice_upto(mseries, asof), yrs, asof)
            if rs is None:
                return None
            v = SD._semidev_about(rs, sum(rs) / len(rs))
            if v is None:
                return None
            tot += wt * v * 100.0
        return tot

    # month-ends on the market calendar
    ends, prev = [], None
    for x in mdates:
        if a.start <= x <= a.end:
            if prev and x[:7] != prev[:7]:
                ends.append(prev)
            prev = x
    if prev:
        ends.append(prev)
    print("%d month-ends %s .. %s" % (len(ends), ends[0], ends[-1]))

    rows = []
    for asof in ends:
        m = total_semidev(mseries, asof)
        if m is None:
            continue
        rec = {"date": asof, "market_total": round(m, 4)}
        for g in sorted(sec):
            s = slice_upto(sec[g], asof)
            if len(s) < 500:
                continue
            t = total_semidev(s, asof)
            if t is None:
                continue
            rec["%s_total" % g] = round(t, 4)
            rec["%s_ratio" % g] = round(t / m, 4)
            rr = SD.blended_semidev(s, slice_upto(mseries, asof), asof=asof)
            if rr is not None:
                rec["%s_resid" % g] = round(rr, 4)
        rows.append(rec)

    cols = ["date", "market_total"]
    for g in sorted(sec):
        cols += ["%s_total" % g, "%s_ratio" % g, "%s_resid" % g]
    p = os.path.join(OUT, "sector_semidev_monthly.csv")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print("wrote %s (%d rows)\n" % (p, len(rows)))

    # ---------------------------------------------------------------- the claim
    print("THE CLAIM: every sector's total downside deviation exceeds the market's.")
    print("%-4s %-24s %8s %8s %8s %8s %10s" % ("gics", "sector", "n", "min", "median", "max",
                                               "% above 1"))
    med = {}
    for g in sorted(sec):
        v = [r["%s_ratio" % g] for r in rows if "%s_ratio" % g in r]
        if not v:
            continue
        above = sum(1 for x in v if x > 1.0) / len(v)
        med[g] = stat.median(v)
        print("%-4s %-24s %8d %8.3f %8.3f %8.3f %9.0f%%"
              % (g, names[g], len(v), min(v), stat.median(v), max(v), 100 * above))

    allr = [r["%s_ratio" % g] for r in rows for g in sorted(sec) if "%s_ratio" % g in r]
    print("\npooled: %d sector-months, %.1f%% above 1.0, median %.3f"
          % (len(allr), 100 * sum(1 for x in allr if x > 1) / len(allr), stat.median(allr)))
    print("equal-weighted average sector ratio, median across dates: %.3f"
          % stat.median([stat.mean([r["%s_ratio" % g] for g in sorted(sec)
                                    if "%s_ratio" % g in r])
                         for r in rows if any("%s_ratio" % g in r for g in sec)]))

    print("\nWhat that means for the premium, at market_ERP(front) = 4.13pp:")
    for g in sorted(med, key=lambda x: med[x]):
        print("   %-24s ratio %.3f -> ERP %.2fpp  (%+.2fpp vs the market)"
              % (names[g], med[g], 4.13 * med[g], 4.13 * (med[g] - 1)))

    print("\nTOTAL vs RESIDUAL, median across dates — they are different questions:")
    print("%-24s %10s %10s %10s" % ("sector", "total", "residual", "resid/total"))
    for g in sorted(sec):
        t = [r["%s_total" % g] for r in rows if "%s_total" % g in r]
        rr = [r["%s_resid" % g] for r in rows if "%s_resid" % g in r]
        if t and rr:
            print("%-24s %10.2f %10.2f %10.3f"
                  % (names[g], stat.median(t), stat.median(rr), stat.median(rr) / stat.median(t)))

    print("\ncrisis spot checks, ratio to market:")
    for d_ in ["1998-09-30", "2000-03-31", "2002-09-30", "2008-09-30", "2008-12-31",
               "2009-03-31", "2011-09-30"]:
        r = next((x for x in rows if x["date"][:7] == d_[:7]), None)
        if r:
            print("   %s  %s" % (r["date"], "  ".join(
                "%s %.2f" % (names[g][:12], r["%s_ratio" % g])
                for g in sorted(sec) if "%s_ratio" % g in r)))


if __name__ == "__main__":
    main()
