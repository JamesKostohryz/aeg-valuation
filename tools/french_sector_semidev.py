#!/usr/bin/env python3
"""french_sector_semidev.py — the sector idiosyncratic ERP on Kenneth French's daily industry
portfolios, 1926 to the present.

    ERP_sector(t) = market_ERP(t) x semidev_TOTAL_sector(t) / semidev_TOTAL_market(t)

WHY THIS SOURCE. The Global Financial Data route needed a weekly-to-daily bridge before 1989, had
five of ten sectors missing, and stopped in November 2014. French's industry portfolios are DAILY
from 1926-07-01, complete, value-weighted, free, and current. The market comparator is
`Mkt-RF + RF` from the same CRSP universe on the same calendar with the same return definition,
which is a like-for-like comparison the GFD route could not make.

THE STATISTIC IS THE PRODUCTION ONE AND IT IS NOT REIMPLEMENTED. French publishes simple daily
percentage returns; `idio/semidev.py` consumes a price series. So the returns are CUMULATED INTO
A PRICE INDEX and handed to the production functions unchanged, which reproduces
log(1 + r) exactly and keeps `clean_series`, `aligned_returns` and `_semidev_about` on the same
code path every company valuation uses. No special case, no second version of the statistic.

MISSING DATA IS NOT SILENTLY BRIDGED. French marks unavailable industry-days -99.99 or -999. A
price index cumulated through those is nonsense, so an industry's series starts AFTER its last
missing value and the truncation is reported per industry rather than absorbed.

  python3 tools/french_sector_semidev.py --repo /tmp/aeg --set 12
  python3 tools/french_sector_semidev.py --repo /tmp/aeg --set 49 --start 1930-01-01

NOT A VALUATION.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import os
import statistics as stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = os.path.join(ROOT, "outputs", "famafrench_raw")
OUT = os.path.join(ROOT, "outputs", "2026-08-20-sectors")
MISSING = (-99.99, -999.0)
WINDOW = 700


def iso(d):
    return "%s-%s-%s" % (d[:4], d[4:6], d[6:8])


def read_block(path, block="Average Value Weighted Returns -- Daily"):
    """(names, {date_iso: [returns]}) for one block of a French industry file."""
    lines = open(path).read().splitlines()
    start = next(i for i, x in enumerate(lines) if block in x)
    names = [c.strip() for c in lines[start + 1].split(",")[1:]]
    rows = {}
    for ln in lines[start + 2:]:
        p = ln.split(",")
        if not p[0].strip().isdigit() or len(p[0].strip()) != 8:
            break
        try:
            rows[iso(p[0].strip())] = [float(x) for x in p[1:]]
        except ValueError:
            break
    return names, rows


def read_factors(path):
    """{date_iso: market total return %} = Mkt-RF + RF."""
    lines = open(path).read().splitlines()
    start = next(i for i, x in enumerate(lines) if x.strip().startswith(",Mkt-RF"))
    cols = [c.strip() for c in lines[start].split(",")[1:]]
    im, ir = cols.index("Mkt-RF"), cols.index("RF")
    out = {}
    for ln in lines[start + 1:]:
        p = ln.split(",")
        if not p[0].strip().isdigit() or len(p[0].strip()) != 8:
            break
        try:
            v = [float(x) for x in p[1:]]
        except ValueError:
            break
        out[iso(p[0].strip())] = v[im] + v[ir]
    return out


def price_index(dates, rets):
    """Cumulate simple % returns into a price series. Truncates after the LAST missing value."""
    last_bad = -1
    for i, r in enumerate(rets):
        if r in MISSING or r is None:
            last_bad = i
    d, r = dates[last_bad + 1:], rets[last_bad + 1:]
    px, p = [], 100.0
    for x in r:
        p *= (1.0 + x / 100.0)
        px.append(p)
    return list(zip(d, px)), (d[0] if d else None), last_bad + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--set", default="12")
    ap.add_argument("--start", default="1928-07-01")
    ap.add_argument("--end", default="2026-06-30")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    sys.path.insert(0, os.path.join(a.repo, "idio"))
    import semidev as SD

    ind = os.path.join(FF, "%s_Industry_Portfolios_Daily.csv" % a.set)
    names, rows = read_block(ind)
    fac = read_factors(os.path.join(FF, "F-F_Research_Data_Factors_daily.csv"))
    dates = sorted(set(rows) & set(fac))
    print("%s industries, %d common days %s .. %s" % (a.set, len(dates), dates[0], dates[-1]))

    mkt, _, _ = price_index(dates, [fac[d] for d in dates])
    print("market (Mkt-RF + RF): %d days %s .. %s\n" % (len(mkt), mkt[0][0], mkt[-1][0]))

    series = {}
    for j, nm in enumerate(names):
        s, first, dropped = price_index(dates, [rows[d][j] for d in dates])
        series[nm] = s
        if dropped:
            print("   %-8s starts %s (%d leading/embedded missing days dropped)"
                  % (nm, first, dropped))

    def cut(s, asof, n=WINDOW):
        ds = [x[0] for x in s]
        i = bisect.bisect_right(ds, asof)
        return s[max(0, i - n):i]

    def total_semidev(s, asof):
        tot = 0.0
        for yrs, wt in zip(SD.BLEND_WINDOWS, SD.BLEND_WEIGHTS):
            rs, _ = SD.aligned_returns(s, cut(mkt, asof), yrs, asof)
            if rs is None:
                return None
            v = SD._semidev_about(rs, sum(rs) / len(rs))
            if v is None:
                return None
            tot += wt * v * 100.0
        return tot

    ends, prev = [], None
    for d, _ in mkt:
        if a.start <= d <= a.end:
            if prev and d[:7] != prev[:7]:
                ends.append(prev)
            prev = d
    if prev:
        ends.append(prev)
    print("\n%d month-ends %s .. %s" % (len(ends), ends[0], ends[-1]))

    out = []
    for asof in ends:
        m = total_semidev(mkt, asof)
        if m is None:
            continue
        rec = {"date": asof, "market_total": round(m, 4)}
        for nm in names:
            v = total_semidev(cut(series[nm], asof), asof)
            if v is not None:
                rec["%s_total" % nm] = round(v, 4)
                rec["%s_ratio" % nm] = round(v / m, 4)
        out.append(rec)

    cols = ["date", "market_total"] + [c for nm in names
                                       for c in ("%s_total" % nm, "%s_ratio" % nm)]
    p = os.path.join(OUT, "french_%s_sector_semidev.csv" % a.set)
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    print("wrote %s (%d months)\n" % (p, len(out)))

    print("SECTOR RISK RELATIVE TO THE MARKET, %s .. %s" % (out[0]["date"], out[-1]["date"]))
    print("%-8s %6s %8s %8s %8s %10s %12s"
          % ("industry", "n", "min", "median", "max", "% above 1", "ERP @4.13pp"))
    med = {}
    for nm in names:
        v = [r["%s_ratio" % nm] for r in out if "%s_ratio" % nm in r]
        if not v:
            continue
        med[nm] = stat.median(v)
        print("%-8s %6d %8.3f %8.3f %8.3f %9.0f%% %11.2fpp"
              % (nm, len(v), min(v), med[nm], max(v),
                 100 * sum(1 for x in v if x > 1) / len(v), 4.13 * med[nm]))
    eq = [stat.mean([r["%s_ratio" % nm] for nm in names if "%s_ratio" % nm in r]) for r in out]
    print("\nequal-weighted average industry ratio: median %.3f across %d months"
          % (stat.median(eq), len(eq)))

    print("\ncrisis and episode spot checks:")
    for d_ in ["1932-06", "1937-10", "1974-10", "1987-11", "2000-03", "2002-09",
               "2008-12", "2020-04", "2026-06"]:
        r = next((x for x in out if x["date"][:7] == d_), None)
        if r:
            top = sorted(((r["%s_ratio" % nm], nm) for nm in names if "%s_ratio" % nm in r),
                         reverse=True)
            print("   %s  riskiest %s %.2f   calmest %s %.2f"
                  % (r["date"], top[0][1], top[0][0], top[-1][1], top[-1][0]))


if __name__ == "__main__":
    main()
