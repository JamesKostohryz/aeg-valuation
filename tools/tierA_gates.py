#!/usr/bin/env python3
"""tierA_gates.py — apply the five gates of PREREG-Company-Leg-Denominator-2026-08-20.md.

No threshold in this file may differ from the pre-registration. They are repeated as constants
so a diff against the document is one glance.

  python3 tools/tierA_gates.py --k /tmp/tierA/tierA_k_spy.csv --repo /path/to/aeg-valuation

NOT A VALUATION.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import os
import statistics as stat
import sys

# ------------------------------------------------------- pre-registered, do not edit
G1_P95_BP, G1_MAX_BP = 15.0, 30.0
G2_DRIFT = 0.10
G3_CRISIS = 0.10
G4_DISP = 0.08
G5_COUNT_FLOOR = 0.80
DECAY_LAM = 0.25          # idio/erp.py LAM_ADOPTED; D(t) in [LAM, 1]


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", required=True)
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(a.k))]
    for r in rows:
        for c in ("count_cov", "cap_cov", "capw_avg_semidev", "market_semidev", "k"):
            r[c] = f(r[c])
        r["drawdown"] = int(r["drawdown"])
    rows = [r for r in rows if r["k"]]
    print("loaded %d monthly observations %s .. %s" % (len(rows), rows[0]["date"], rows[-1]["date"]))

    # ---------------------------------------------------------------- G5 first: what may speak
    ok = [r for r in rows if (r["count_cov"] or 0) >= G5_COUNT_FLOOR]
    first_ok = ok[0]["date"] if ok else None
    print("\nG5  panel validity, count coverage >= %.0f%%" % (100 * G5_COUNT_FLOOR))
    print("    dates passing: %d of %d; earliest %s" % (len(ok), len(rows), first_ok))
    for y in range(1995, 2027, 2):
        sel = [r for r in rows if r["date"][:4] == str(y)]
        if sel:
            r = sel[len(sel) // 2]
            print("      %s  count %.0f%%  cap %s" % (
                r["date"], 100 * (r["count_cov"] or 0),
                ("%.0f%%" % (100 * r["cap_cov"])) if r["cap_cov"] else "n/a"))

    capok = [r for r in rows if (r["cap_cov"] or 0) >= G5_COUNT_FLOOR or r["date"] > "2012-12-31"]
    print("    SECONDARY (not the pre-registered gate): cap-weighted coverage >= 80%% from %s"
          % (capok[0]["date"] if capok else "never"))

    def report(tag, sel):
        if len(sel) < 24:
            print("\n%s: only %d observations; not reported" % (tag, len(sel)))
            return
        ks = [r["k"] for r in sel]
        m, sd = stat.mean(ks), stat.pstdev(ks)
        print("\n%s  n=%d  %s .. %s" % (tag, len(sel), sel[0]["date"], sel[-1]["date"]))
        print("    k: mean %.4f  sd %.4f  min %.4f  max %.4f  max/min %.2fx"
              % (m, sd, min(ks), max(ks), max(ks) / min(ks)))

        # G4 dispersion
        d4 = sd / m
        print("    G4 dispersion sd/mean = %.1f%%   limit %.0f%%   %s"
              % (100 * d4, 100 * G4_DISP, "PASS" if d4 <= G4_DISP else "FAIL"))

        # G2 drift, first decade vs last decade
        span = (int(sel[-1]["date"][:4]) - int(sel[0]["date"][:4]))
        w = 10 if span >= 20 else max(3, span // 3)
        y0, y1 = int(sel[0]["date"][:4]), int(sel[-1]["date"][:4])
        a_ = [r["k"] for r in sel if int(r["date"][:4]) < y0 + w]
        b_ = [r["k"] for r in sel if int(r["date"][:4]) > y1 - w]
        d2 = abs(stat.mean(a_) - stat.mean(b_)) / m
        print("    G2 drift first %dy %.4f vs last %dy %.4f -> %.1f%%   limit %.0f%%   %s"
              % (w, stat.mean(a_), w, stat.mean(b_), 100 * d2, 100 * G2_DRIFT,
                 "PASS" if d2 <= G2_DRIFT else "FAIL"))

        # G3 crisis conditioning
        dd = [r["k"] for r in sel if r["drawdown"]]
        cl = [r["k"] for r in sel if not r["drawdown"]]
        if dd and cl:
            d3 = abs(stat.mean(dd) - stat.mean(cl)) / m
            print("    G3 drawdown %.4f (n=%d) vs calm %.4f (n=%d) -> %.1f%%   limit %.0f%%   %s"
                  % (stat.mean(dd), len(dd), stat.mean(cl), len(cl), 100 * d3, 100 * G3_CRISIS,
                     "PASS" if d3 <= G3_CRISIS else "FAIL"))
        else:
            print("    G3 not computable: drawdown n=%d calm n=%d" % (len(dd), len(cl)))
        return m, sd, ks

    prim = report("PRIMARY  (G5-passing dates only)", ok)
    report("SECONDARY (full 1995-2026, G5 IGNORED - exploratory)", rows)
    post = [r for r in rows if r["date"] >= "2000-01-01"]
    report("HANDOFF WINDOW (2000-2026, G5 ignored - comparable to the proposal)", post)

    # ---------------------------------------------------------------- G1 displacement
    print("\nG1  displacement, on the G5-passing window, using k-bar = mean(k) there")
    if not prim:
        return
    kbar = prim[0]
    uni = os.path.join(a.repo, "outputs", "idio_universe_latest.csv")
    u = [r for r in csv.DictReader(open(uni)) if r["semidev"] and f(r["market_cap"])]
    sds = sorted(f(r["semidev"]) for r in u)
    tot = sum(f(r["market_cap"]) for r in u)
    capw_today = sum(f(r["market_cap"]) * f(r["semidev"]) for r in u) / tot

    def pick(p):
        target = sds[int(p * (len(sds) - 1))]
        return min(u, key=lambda r: abs(f(r["semidev"]) - target))

    tests = []
    for t in ("MSFT", "PEP"):
        m_ = [r for r in u if r["ticker"] == t]
        if m_:
            tests.append((t, f(m_[0]["semidev"])))
    for p, lbl in ((0.10, "p10"), (0.50, "p50"), (0.90, "p90")):
        r = pick(p)
        tests.append(("%s (%s)" % (r["ticker"], lbl), f(r["semidev"])))

    MARKET_ERP_FRONT = 4.13   # implied by MSFT's published -0.8104pp at ratio 0.804x
    print("    k-bar = %.4f ; market_ERP(front) = %.2fpp ; capw today = %.4f"
          % (kbar, MARKET_ERP_FRONT, capw_today))
    print("    %-18s %8s %10s %10s %10s" % ("company", "semidev", "ratio", "front bp", "collapsed"))
    for name, sd_i in tests:
        worst = 0.0
        for r in ok:
            e = r["k"] / kbar - 1.0                      # capw_true / capw_hat - 1
            d = MARKET_ERP_FRONT * (sd_i / capw_today) * e   # pp at the front tenor
            worst = max(worst, abs(d))
        print("    %-18s %8.2f %10.3f %10.0f %10s"
              % (name, sd_i, sd_i / capw_today, 100 * worst,
                 ">= %.0f bp" % (100 * DECAY_LAM * worst)))
    print("    (collapsed displacement is bounded below by LAM_ADOPTED = %.2f times the front "
          "displacement, since D(t) in [%.2f, 1])" % (DECAY_LAM, DECAY_LAM))
    print("    G1 limits: p95 %.0fbp, max %.0fbp" % (G1_P95_BP, G1_MAX_BP))


if __name__ == "__main__":
    main()
