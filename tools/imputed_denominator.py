#!/usr/bin/env python3
"""imputed_denominator.py — impute the missing names instead of ignoring them.

RUNS docs/PREREG-Imputed-Denominator-2026-08-20.md, committed as aeg-valuation edb9c16 before
this was run. TILT is fixed at 1.18 and is not adjusted after a result is seen.

  python3 tools/imputed_denominator.py

NOT A VALUATION.
"""
from __future__ import annotations

import csv
import os
import random
import statistics as stat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DETAIL = os.path.join(ROOT, "outputs", "2026-08-20-partial-panel", "panel_detail.csv")

MISS = {
    1985: [.41, .50, .52, .66, .62, .70, .82, .82, .86, 1.00],
    1995: [.28, .47, .47, .45, .60, .51, .66, .81, .79, .86],
    2000: [.21, .40, .38, .26, .30, .33, .50, .38, .57, .74],
    2005: [.07, .17, .22, .14, .17, .34, .33, .29, .44, .76],
    2010: [.02, .02, .05, .07, .02, .10, .00, .07, .12, .36],
}
TILT = 1.18                      # pre-registered, measured, not fitted
DRAWS = 200
MEDIAN_LIMIT, P95_LIMIT = 0.03, 0.05
CRISIS_LIMIT = 2.0
BRACKET_LIMIT = 0.08
SEED = 20260820
MARKET_ERP_FRONT, DECAY_LAM = 4.13, 0.25


def capw(sel):
    t = sum(c for _, _, c in sel)
    return sum(c * s for _, s, c in sel) / t if t else None


def split(sel, rates, mode, rng):
    """(kept, hidden) decile by decile at the given miss rates."""
    s = sorted(sel, key=lambda x: -x[2])
    n = len(s)
    kept, hidden = [], []
    for i in range(10):
        seg = s[int(i * n / 10):int((i + 1) * n / 10)]
        nd = int(round(rates[i] * len(seg)))
        if nd >= len(seg):
            hidden += [(i, x) for x in seg]
            continue
        if mode == "neutral":
            idx = set(rng.sample(range(len(seg)), nd))
            for j, x in enumerate(seg):
                (hidden if j in idx else kept).append((i, x))
        elif mode == "high":
            o = sorted(seg, key=lambda x: -x[1])
            hidden += [(i, x) for x in o[:nd]]
            kept += [(i, x) for x in o[nd:]]
        else:
            o = sorted(seg, key=lambda x: x[1])
            hidden += [(i, x) for x in o[:nd]]
            kept += [(i, x) for x in o[nd:]]
    return kept, hidden


def imputed(kept, hidden):
    """Cap weights of the hidden names are KNOWN (Compustat); only semidev is imputed."""
    med = {}
    for i in range(10):
        v = [x[1] for d, x in kept if d == i]
        if v:
            med[i] = stat.median(v)
    if not med:
        return None
    glob = stat.median(list(med.values()))
    num = sum(x[2] * x[1] for _, x in kept)
    den = sum(x[2] for _, x in kept)
    for d, x in hidden:
        num += x[2] * TILT * med.get(d, glob)
        den += x[2]
    return num / den if den else None


def main():
    rows, dd = {}, {}
    for r in csv.DictReader(open(DETAIL)):
        rows.setdefault(r["date"], []).append(
            (r["ticker"], float(r["semidev"]), float(r["market_cap"])))
        dd[r["date"]] = int(r["drawdown"])
    dates = sorted(rows)
    full = {d: capw(rows[d]) for d in dates}
    print("TILT = %.2f (pre-registered, measured)   %d dates %s .. %s\n"
          % (TILT, len(dates), dates[0], dates[-1]))

    print("%-6s | %-24s | %-20s | %-19s |"
          % ("target", "IMPUTED, neutral", "D3 for comparison", "bracket, mean e"))
    print("%-6s | %7s %7s %7s | %7s %7s | %8s %8s | %s"
          % ("year", "median", "p95", "mean e", "median", "p95", "high", "low", "verdict"))

    res = {}
    for y in sorted(MISS):
        rng = random.Random(SEED + y)
        ei, e3, by_date = [], [], {}
        for d in dates:
            per = []
            for _ in range(DRAWS):
                k, h = split(rows[d], MISS[y], "neutral", rng)
                per.append(imputed(k, h) / full[d] - 1.0)
                e3.append(capw([x for _, x in k]) / full[d] - 1.0)
            ei += per
            by_date[d] = per
        bh = bl = None
        for mode in ("high", "low"):
            v = []
            for d in dates:
                k, h = split(rows[d], MISS[y], mode, rng)
                v.append(imputed(k, h) / full[d] - 1.0)
            if mode == "high":
                bh = stat.mean(v)
            else:
                bl = stat.mean(v)

        a = sorted(abs(e) for e in ei)
        med, p95 = a[len(a) // 2], a[int(0.95 * len(a))]
        b = sorted(abs(e) for e in e3)
        med3, p953 = b[len(b) // 2], b[int(0.95 * len(b))]
        mdd = stat.median([abs(e) for d in dates if dd[d] for e in by_date[d]])
        mcl = stat.median([abs(e) for d in dates if not dd[d] for e in by_date[d]])
        cr = mdd / mcl if mcl else float("inf")
        beats = med < med3 and p95 < p953
        ok = med <= MEDIAN_LIMIT and p95 <= P95_LIMIT and cr <= CRISIS_LIMIT and beats
        res[y] = (med, p95, stat.mean(ei), bh, bl, cr, ok, beats, med3, p953)
        print("%-6d | %6.2f%% %6.2f%% %+6.2f%% | %6.2f%% %6.2f%% | %+7.2f%% %+7.2f%% | %s%s%s"
              % (y, 100 * med, 100 * p95, 100 * stat.mean(ei), 100 * med3, 100 * p953,
                 100 * bh, 100 * bl, "PASS" if ok else "FAIL",
                 "" if beats else " (no gain)",
                 "" if cr <= CRISIS_LIMIT else " (crisis %.1fx)" % cr))

    print("\nlimits: median <= %.0f%%, p95 <= %.0f%%, crisis <= %.1fx, and must beat D3"
          % (100 * MEDIAN_LIMIT, 100 * P95_LIMIT, CRISIS_LIMIT))
    p = [y for y in sorted(MISS) if res[y][6]]
    print("target years that pass: %s" % (p or "none"))
    if p:
        print("EARLIEST USABLE PROFILE: %d" % min(p))
    print("bracket limit +-%.0f%%: %s"
          % (100 * BRACKET_LIMIT,
             ", ".join("%d %s" % (y, "ok" if max(abs(res[y][3]), abs(res[y][4])) <= BRACKET_LIMIT
                                  else "WIDE") for y in sorted(MISS))))

    print("\ndisplacement in the collapsed real cost of equity at each year's p95 error")
    last = rows[dates[-1]]
    cw = full[dates[-1]]
    sds = sorted(s for _, s, _ in last)
    print("  %-8s %8s | %s" % ("decile", "ratio", " ".join("%6d" % y for y in sorted(MISS))))
    for dec in (1, 5, 9):
        sd_i = sds[int(dec / 10.0 * (len(sds) - 1))]
        cells = ["%5.0fbp" % (100 * DECAY_LAM * MARKET_ERP_FRONT * (sd_i / cw) * res[y][1])
                 for y in sorted(MISS)]
        print("  d%-7d %8.3f | %s" % (dec, sd_i / cw, " ".join(cells)))


if __name__ == "__main__":
    main()
