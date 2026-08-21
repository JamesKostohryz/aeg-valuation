#!/usr/bin/env python3
"""partial_panel_degradation.py — how wrong is capw_avg_semidev on a partial panel?

RUNS THE PRE-REGISTERED PLAN IN docs/PREREG-Partial-Panel-Denominator-2026-08-20.md, committed as
aeg-valuation 7cc39f2 before the test was run.

Stage 1 (--dump) writes per-name (ticker, semidev, market_cap) at each quarterly date where the
panel effectively IS the universe. Stage 2 (--analyse) degrades that panel to historical
coverage levels and measures the error. The statistic comes from idio/semidev.py, imported.

  python3 tools/partial_panel_degradation.py --repo /tmp/aeg --dump
  python3 tools/partial_panel_degradation.py --repo /tmp/aeg --analyse

NOT A VALUATION.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import importlib.util
import json
import os
import statistics as stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "outputs", "2026-08-20-partial-panel")

# pre-registered, section 3 and 4
LEVELS = [50, 55, 60, 65, 70, 75, 80, 85, 90]
LEAVE_WITHIN_YEARS = 8
MEDIAN_LIMIT, P95_LIMIT = 0.03, 0.05
FALSIFIER_LEVEL = 60
CRISIS_RATIO_LIMIT = 2.0
MARKET_ERP_FRONT = 4.13
DECAY_LAM = 0.25


def _tierA():
    p = os.path.join(ROOT, "tools", "tierA_denominator_ratio.py")
    spec = importlib.util.spec_from_file_location("tierA", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def dump(repo):
    T = _tierA()
    sys.path.insert(0, os.path.join(repo, "idio"))
    import semidev as SD

    os.makedirs(OUTDIR, exist_ok=True)
    panel = T.load_panel()
    mdates, madj, mclose = T.load_px_cache("SPY_US_1950-01-01.json")
    crsp, eod = T.load_membership()
    shares = T.load_shares()
    ddays = T.drawdown_days(mdates, mclose)

    ends = [d for d in T.month_ends(mdates, "2013-01-01", "2026-08-12")
            if d[5:7] in ("03", "06", "09", "12")]
    print("%d quarterly dates %s .. %s" % (len(ends), ends[0], ends[-1]), flush=True)

    out = os.path.join(OUTDIR, "panel_detail.csv")
    done = set()
    if os.path.exists(out):
        for r in csv.DictReader(open(out)):
            done.add(r["date"])
        print("  resuming: %d dates present" % len(done), flush=True)
    fh = open(out, "a" if done else "w", newline="")
    w = csv.writer(fh)
    if not done:
        w.writerow(["date", "ticker", "semidev", "market_cap", "drawdown"])

    for asof in ends:
        if asof in done:
            continue
        tickers, n_true, _ = T.members_as_of(asof, crsp, eod)
        yr = int(asof[:4])
        n = 0
        for t in tickers:
            if t not in panel:
                continue
            pdt, padj, pcl = panel[t]
            v = SD.blended_semidev(T.slice_upto(pdt, padj, asof),
                                   T.slice_upto(mdates, madj, asof), asof=asof)
            if v is None:
                continue
            i = bisect.bisect_right(pdt, asof) - 1
            if i < 0:
                continue
            sh = T.shares_at(shares, t, yr)
            if not sh or pcl[i] <= 0:
                continue
            w.writerow([asof, t, "%.6f" % v, "%.4f" % (sh * pcl[i]),
                        1 if asof in ddays else 0])
            n += 1
        fh.flush()
        print("  %s  %d names" % (asof, n), flush=True)
    fh.close()


def analyse(repo):
    T = _tierA()
    _, eod = T.load_membership()
    leaves = {}
    for code, s, e in eod:
        if e and e < "2100-01-01":
            leaves[code] = e

    rows = {}
    for r in csv.DictReader(open(os.path.join(OUTDIR, "panel_detail.csv"))):
        rows.setdefault(r["date"], []).append(
            (r["ticker"], float(r["semidev"]), float(r["market_cap"]), int(r["drawdown"])))
    dates = sorted(rows)
    print("loaded %d dates, %s .. %s\n" % (len(dates), dates[0], dates[-1]))

    def capw(sel):
        tot = sum(c for _, _, c, _ in sel)
        return sum(c * s for _, s, c, _ in sel) / tot if tot else None

    def degrade(sel, level, drop_leavers, asof):
        s = sorted(sel, key=lambda x: -x[2])
        tot = sum(x[2] for x in s)
        keep, run = [], 0.0
        for x in s:
            if run >= level / 100.0 * tot:
                break
            keep.append(x)
            run += x[2]
        if drop_leavers:
            cut = "%04d%s" % (int(asof[:4]) + LEAVE_WITHIN_YEARS, asof[4:])
            keep = [x for x in keep if not (x[0] in leaves and asof < leaves[x[0]] <= cut)]
        return keep

    print("%-6s | %-28s | %-28s" % ("level", "D1 big names survive", "D2 minus future leavers"))
    print("%-6s | %8s %8s %8s | %8s %8s %8s" % ("", "median", "p95", "mean e", "median", "p95", "mean e"))
    results = {}
    for lv in LEVELS:
        line = ["%-4d%%" % lv]
        for tag, dl in (("D1", False), ("D2", True)):
            es = []
            for d in dates:
                full = capw(rows[d])
                deg = capw(degrade(rows[d], lv, dl, d))
                if full and deg:
                    es.append((d, deg / full - 1.0, rows[d][0][3]))
            a = sorted(abs(e) for _, e, _ in es)
            med, p95 = a[len(a) // 2], a[int(0.95 * len(a))]
            mean_signed = stat.mean(e for _, e, _ in es)
            results[(lv, tag)] = (med, p95, mean_signed, es)
            line.append("%7.2f%% %7.2f%% %+7.2f%%" % (100 * med, 100 * p95, 100 * mean_signed))
        print("%s | %s | %s" % (line[0], line[1], line[2]))

    print("\npre-registered limits: median <= %.0f%%, p95 <= %.0f%%  (BOTH models)"
          % (100 * MEDIAN_LIMIT, 100 * P95_LIMIT))
    passing = [lv for lv in LEVELS
               if all(results[(lv, t)][0] <= MEDIAN_LIMIT and results[(lv, t)][1] <= P95_LIMIT
                      for t in ("D1", "D2"))]
    lowest = min(passing) if passing else None
    print("levels that pass: %s" % (passing or "none"))
    print("FALSIFIER: fails before X falls to %d%%?  %s"
          % (FALSIFIER_LEVEL, "NO" if lowest is not None and lowest <= FALSIFIER_LEVEL else "YES"))

    print("\ncrisis conditioning falsifier (median |e| drawdown vs calm, limit %.1fx)"
          % CRISIS_RATIO_LIMIT)
    for lv in (55, 60, 70, 80):
        for tag in ("D1", "D2"):
            es = results[(lv, tag)][3]
            dd = [abs(e) for _, e, f in es if f]
            cl = [abs(e) for _, e, f in es if not f]
            if dd and cl:
                r = stat.median(dd) / stat.median(cl)
                print("  X=%d%% %s: drawdown %.2f%% vs calm %.2f%% -> %.2fx  %s"
                      % (lv, tag, 100 * stat.median(dd), 100 * stat.median(cl), r,
                         "PASS" if r <= CRISIS_RATIO_LIMIT else "FAIL"))

    print("\ndisplacement in the collapsed real cost of equity, by semi-deviation decile")
    print("(front = ERP_front x ratio x e ; collapsed >= %.2f x front)" % DECAY_LAM)
    last = rows[dates[-1]]
    cw = capw(last)
    sds = sorted(s for _, s, _, _ in last)
    print("  %-8s %8s %8s | %s" % ("decile", "semidev", "ratio",
                                   "  ".join("X=%d%%" % lv for lv in (55, 65, 75, 85))))
    for dec in (1, 5, 9):
        sd_i = sds[int(dec / 10.0 * (len(sds) - 1))]
        cells = []
        for lv in (55, 65, 75, 85):
            e = results[(lv, "D2")][1]
            front = MARKET_ERP_FRONT * (sd_i / cw) * e
            cells.append(">=%4.0fbp" % (100 * DECAY_LAM * front))
        print("  d%-7d %8.2f %8.3f | %s" % (dec, sd_i, sd_i / cw, "  ".join(cells)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args()
    if a.dump:
        dump(a.repo)
    if a.analyse:
        analyse(a.repo)


if __name__ == "__main__":
    main()
