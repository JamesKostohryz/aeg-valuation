#!/usr/bin/env python3
"""constant_denominator_test.py — James's proposal, tested rather than argued.

THE PROPOSAL (James, 2026-08-20): we do not need the universe measured at every historical date.
Calibrate on the last ~20 years, then apply the same model backwards, comparing the stock's own
1y/2y downside semi-deviation to a LONG-RUN weighted average or median rather than to the
contemporaneous cross-sectional average -- provided that long-run average is stationary, meaning
mean-reverting.

THIS IS NOT TIER A. Tier A scaled the denominator off the market's own semi-deviation at each
date, and failed because that scaling factor is average correlation and moves by 3x. James's
proposal uses NO market series: the denominator is one number.

THE CRITERION IS NOT NEW AND IS NOT CHOSEN HERE. It is G1 from
PREREG-Company-Leg-Denominator-2026-08-20.md, fixed on 2026-08-20 before any of this:
displacement in the COLLAPSED real cost of equity, p95 <= 15bp, max <= 30bp.

  python3 tools/constant_denominator_test.py --repo /tmp/aeg

NOT A VALUATION.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import importlib.util
import math
import os
import statistics as stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KFILE = os.path.join(ROOT, "outputs", "2026-08-20-tierA-denominator", "tierA_k_full.csv")
OUT = os.path.join(ROOT, "outputs", "2026-08-20-constant-denominator")

G1_P95_BP, G1_MAX_BP = 15.0, 30.0
MARKET_ERP_FRONT, DECAY_LAM = 4.13, 0.25
NAMES = ["MSFT", "PEP", "KO", "XOM", "JNJ", "GE", "INTC", "WMT"]


def ar1(x):
    """AR(1) coefficient, half-life in months, and the implied unconditional sd."""
    m = stat.mean(x)
    num = sum((x[i] - m) * (x[i - 1] - m) for i in range(1, len(x)))
    den = sum((v - m) ** 2 for v in x[:-1])
    rho = num / den
    hl = math.log(0.5) / math.log(rho) if 0 < rho < 1 else float("inf")
    return rho, hl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    rows = list(csv.DictReader(open(KFILE)))
    dates = [r["date"] for r in rows]
    capw = [float(r["capw_avg_semidev"]) for r in rows]
    dd = [int(r["drawdown"]) for r in rows]

    # ------------------------------------------------ 1. is it mean-reverting?
    rho, hl = ar1(capw)
    lc = [math.log(v) for v in capw]
    rho_l, hl_l = ar1(lc)
    print("1. IS THE DENOMINATOR MEAN-REVERTING?  (monthly, 1995-06 .. 2026-08, n=%d)" % len(capw))
    print("   level: AR(1) rho = %.4f  half-life = %.1f months (%.1f years)" % (rho, hl, hl / 12))
    print("   log  : AR(1) rho = %.4f  half-life = %.1f months (%.1f years)" % (rho_l, hl_l, hl_l / 12))
    print("   mean %.2f  median %.2f  sd %.2f (%.1f%% of mean)  range %.2f-%.2f"
          % (stat.mean(capw), stat.median(capw), stat.pstdev(capw),
             100 * stat.pstdev(capw) / stat.mean(capw), min(capw), max(capw)))
    n5 = 60
    print("   rolling 5-year means: %s"
          % "  ".join("%.1f" % stat.mean(capw[i:i + n5]) for i in range(0, len(capw) - n5, n5)))
    print("   VERDICT: %s" % ("mean-reverting, but slowly - half-life %.1f years"
                              % (hl_l / 12) if 0 < rho_l < 1 else "not mean-reverting"))

    # ------------------------------------------------ 2. error from a constant
    C_mean, C_med = stat.mean(capw), stat.median(capw)
    print("\n2. HOW BIG IS THE ERROR FROM A CONSTANT DENOMINATOR?")
    print("   e = capw(t)/C - 1, which passes ONE-FOR-ONE into every company's premium")
    for lbl, C in (("long-run mean %.2f" % C_mean, C_mean), ("long-run median %.2f" % C_med, C_med)):
        e = [v / C - 1.0 for v in capw]
        aa = sorted(abs(x) for x in e)
        print("   %-24s median |e| %5.1f%%  p95 %5.1f%%  max %5.1f%%  (min %+.0f%%, max %+.0f%%)"
              % (lbl, 100 * aa[len(aa) // 2], 100 * aa[int(.95 * len(aa))], 100 * aa[-1],
                 100 * min(e), 100 * max(e)))
    e = [v / C_med - 1.0 for v in capw]
    edd = [abs(x) for x, f in zip(e, dd) if f]
    ecl = [abs(x) for x, f in zip(e, dd) if not f]
    print("   crisis conditioning: drawdown median |e| %.1f%% vs calm %.1f%%  -> %.2fx"
          % (100 * stat.median(edd), 100 * stat.median(ecl),
             stat.median(edd) / stat.median(ecl)))

    print("\n3. WHAT THAT COSTS, ON THE PRE-REGISTERED G1 CRITERION")
    aa = sorted(abs(x) for x in e)
    p95e, maxe = aa[int(.95 * len(aa))], aa[-1]
    print("   %-10s %8s | %-22s | %-22s" % ("decile", "ratio", "p95 displacement", "max displacement"))
    for lbl, ratio in (("calm d1", 0.674), ("median d5", 0.939), ("volatile d9", 1.536)):
        f95 = MARKET_ERP_FRONT * ratio * p95e
        fmx = MARKET_ERP_FRONT * ratio * maxe
        print("   %-10s %8.3f | front %6.0fbp, coll >=%4.0fbp | front %6.0fbp, coll >=%4.0fbp"
              % (lbl, ratio, 100 * f95, 100 * DECAY_LAM * f95, 100 * fmx, 100 * DECAY_LAM * fmx))
    print("   G1 limits: p95 <= %.0fbp, max <= %.0fbp on the COLLAPSED rate" % (G1_P95_BP, G1_MAX_BP))

    # ------------------------------------------------ 4. the double-count check
    print("\n4. THE DOUBLE-COUNT CHECK - what a constant does to a real company in a crisis")
    T = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location("t", os.path.join(ROOT, "tools",
                                                                 "tierA_denominator_ratio.py")))
    importlib.util.spec_from_file_location(
        "t", os.path.join(ROOT, "tools", "tierA_denominator_ratio.py")).loader.exec_module(T)
    sys.path.insert(0, os.path.join(a.repo, "idio"))
    import semidev as SD

    panel = T.load_panel()
    mdates, madj, _ = T.load_px_cache("SPY_US_1950-01-01.json")
    capw_at = dict(zip(dates, capw))

    hdr = ("   %-10s %7s | %8s %8s | %8s %8s | %8s"
           % ("date", "capw", "sd(MSFT)", "sd/capw", "sd/C", "prem@capw", "prem@C"))
    per = {}
    for t in NAMES:
        if t not in panel:
            continue
        pdt, padj, _ = panel[t]
        s = {}
        for asof in dates:
            v = SD.blended_semidev(T.slice_upto(pdt, padj, asof),
                                   T.slice_upto(mdates, madj, asof), asof=asof)
            if v is not None:
                s[asof] = v
        if len(s) > 200:
            per[t] = s
    print("   names resolved: %s" % ", ".join(sorted(per)))

    print("\n   Ratio stability per company - sd of (semidev_i / denominator) over time,")
    print("   as a share of its own mean. LOWER IS BETTER: it means the company's relative")
    print("   risk is a stable characteristic rather than noise.")
    print("   %-8s %14s %14s %10s" % ("ticker", "vs capw(t)", "vs constant C", "better"))
    winA = winB = 0
    for t in sorted(per):
        s = per[t]
        ra = [s[d] / capw_at[d] for d in s]
        rb = [s[d] / C_med for d in s]
        va, vb = stat.pstdev(ra) / stat.mean(ra), stat.pstdev(rb) / stat.mean(rb)
        w = "capw(t)" if va < vb else "constant"
        winA += va < vb
        winB += vb <= va
        print("   %-8s %13.1f%% %13.1f%% %10s" % (t, 100 * va, 100 * vb, w))
    print("   contemporaneous denominator gives the more stable relative measure for %d of %d names"
          % (winA, winA + winB))

    print("\n   Crisis behaviour, MSFT, the premium multiplier semidev_i/denominator:")
    if "MSFT" in per:
        s = per["MSFT"]
        for d in ["1999-12-31", "2002-09-30", "2007-06-29", "2008-12-31", "2009-06-30",
                  "2019-12-31", "2020-04-30", "2020-09-30", "2026-06-30"]:
            if d in s and d in capw_at:
                print("     %s  semidev %6.2f  capw %6.2f | vs capw %.3f | vs C %.3f  %s"
                      % (d, s[d], capw_at[d], s[d] / capw_at[d], s[d] / C_med,
                         "<-- crisis" if dd[dates.index(d)] else ""))

    with open(os.path.join(OUT, "capw_series.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "capw_avg_semidev", "err_vs_constant_median", "drawdown"])
        for d, v, x, f_ in zip(dates, capw, e, dd):
            w.writerow([d, "%.4f" % v, "%.4f" % x, f_])
    print("\nwrote %s/capw_series.csv" % OUT)


if __name__ == "__main__":
    main()
