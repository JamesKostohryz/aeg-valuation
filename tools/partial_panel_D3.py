#!/usr/bin/env python3
"""partial_panel_D3.py — the decile-matched degradation model.

RUNS docs/PREREG-Partial-Panel-AMENDMENT-D3-2026-08-20.md, committed as aeg-valuation a3d1599
before this was run. Reads the per-name dump written by partial_panel_degradation.py --dump.

  python3 tools/partial_panel_D3.py --repo /tmp/aeg

NOT A VALUATION.
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import statistics as stat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DETAIL = os.path.join(ROOT, "outputs", "2026-08-20-partial-panel", "panel_detail.csv")

# pre-registered
MISS = {
    1985: [.41, .50, .52, .66, .62, .70, .82, .82, .86, 1.00],
    1995: [.28, .47, .47, .45, .60, .51, .66, .81, .79, .86],
    2000: [.21, .40, .38, .26, .30, .33, .50, .38, .57, .74],
    2005: [.07, .17, .22, .14, .17, .34, .33, .29, .44, .76],
    2010: [.02, .02, .05, .07, .02, .10, .00, .07, .12, .36],
}
DRAWS = 200
MEDIAN_LIMIT, P95_LIMIT = 0.03, 0.05
CRISIS_RATIO_LIMIT = 2.0
MARKET_ERP_FRONT = 4.13
DECAY_LAM = 0.25
SEED = 20260820


def capw(sel):
    tot = sum(c for _, _, c in sel)
    return sum(c * s for _, s, c in sel) / tot if tot else None


def deciles(sel):
    s = sorted(sel, key=lambda x: -x[2])
    n = len(s)
    return [s[int(i * n / 10):int((i + 1) * n / 10)] for i in range(10)]


def degrade(sel, rates, mode, rng):
    keep = []
    for i, seg in enumerate(deciles(sel)):
        ndrop = int(round(rates[i] * len(seg)))
        if ndrop >= len(seg):
            continue
        if mode == "neutral":
            idx = set(rng.sample(range(len(seg)), ndrop))
            keep += [x for j, x in enumerate(seg) if j not in idx]
        elif mode == "high":
            keep += sorted(seg, key=lambda x: x[1])[:len(seg) - ndrop]
        else:
            keep += sorted(seg, key=lambda x: -x[1])[:len(seg) - ndrop]
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()

    rows, dd = {}, {}
    for r in csv.DictReader(open(DETAIL)):
        rows.setdefault(r["date"], []).append(
            (r["ticker"], float(r["semidev"]), float(r["market_cap"])))
        dd[r["date"]] = int(r["drawdown"])
    dates = sorted(rows)
    full = {d: capw(rows[d]) for d in dates}
    print("%d quarterly dates, %s .. %s   (%d drawdown, %d calm)\n"
          % (len(dates), dates[0], dates[-1], sum(dd.values()), len(dates) - sum(dd.values())))

    print("%-6s | %-26s | %-9s %-9s | %s"
          % ("target", "D3-neutral (200 draws)", "D3-high", "D3-low", "verdict"))
    print("%-6s | %7s %7s %8s | %9s %9s |" % ("year", "median", "p95", "mean e", "mean e", "mean e"))
    out = {}
    for y in sorted(MISS):
        rng = random.Random(SEED + y)
        es, es_by_date = [], {}
        for d in dates:
            per = []
            for _ in range(DRAWS):
                k = degrade(rows[d], MISS[y], "neutral", rng)
                per.append(capw(k) / full[d] - 1.0)
            es += per
            es_by_date[d] = per
        hi = stat.mean(capw(degrade(rows[d], MISS[y], "high", rng)) / full[d] - 1.0 for d in dates)
        lo = stat.mean(capw(degrade(rows[d], MISS[y], "low", rng)) / full[d] - 1.0 for d in dates)
        aa = sorted(abs(e) for e in es)
        med, p95 = aa[len(aa) // 2], aa[int(0.95 * len(aa))]
        ok = med <= MEDIAN_LIMIT and p95 <= P95_LIMIT
        # crisis conditioning
        mdd = stat.median([abs(e) for d in dates if dd[d] for e in es_by_date[d]])
        mcl = stat.median([abs(e) for d in dates if not dd[d] for e in es_by_date[d]])
        cr = mdd / mcl if mcl else float("inf")
        okc = cr <= CRISIS_RATIO_LIMIT
        out[y] = (med, p95, stat.mean(es), hi, lo, cr, ok and okc)
        print("%-6d | %6.2f%% %6.2f%% %+7.2f%% | %+8.2f%% %+8.2f%% | %s%s"
              % (y, 100 * med, 100 * p95, 100 * stat.mean(es), 100 * hi, 100 * lo,
                 "PASS" if ok else "FAIL",
                 "" if okc else "  (crisis %.2fx FAIL)" % cr))

    print("\nlimits, unchanged from the original: median <= %.0f%%, p95 <= %.0f%%, crisis <= %.1fx"
          % (100 * MEDIAN_LIMIT, 100 * P95_LIMIT, CRISIS_RATIO_LIMIT))
    passing = [y for y in sorted(MISS) if out[y][6]]
    print("target years that pass: %s" % (passing or "none"))
    if passing:
        print("EARLIEST USABLE PROFILE: %d" % min(passing))

    print("\ncrisis conditioning detail (median |e| drawdown / calm)")
    for y in sorted(MISS):
        print("  %d: %.2fx  %s" % (y, out[y][5], "PASS" if out[y][5] <= CRISIS_RATIO_LIMIT else "FAIL"))

    print("\ndisplacement in the collapsed real cost of equity, at each target year's p95 error")
    last = rows[dates[-1]]
    cw = full[dates[-1]]
    sds = sorted(s for _, s, _ in last)
    print("  %-8s %8s %8s | %s" % ("decile", "semidev", "ratio",
                                   " ".join("%d" % y for y in sorted(MISS))))
    for dec in (1, 5, 9):
        sd_i = sds[int(dec / 10.0 * (len(sds) - 1))]
        cells = [">=%3.0fbp" % (100 * DECAY_LAM * MARKET_ERP_FRONT * (sd_i / cw) * out[y][1])
                 for y in sorted(MISS)]
        print("  d%-7d %8.2f %8.3f | %s" % (dec, sd_i, sd_i / cw, " ".join(cells)))


if __name__ == "__main__":
    main()
