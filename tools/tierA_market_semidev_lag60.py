#!/usr/bin/env python3
"""tierA_market_semidev_lag60.py — the denominator at the COMPANY lag, for the pre-registered
robustness check in section 4.3 of PREREG-Company-Leg-Denominator-2026-08-20.md.

Production runs the numerator at lag 60 and the denominator at lag 0. That is a ratio of two
statistics measured three months apart, and a three-month offset straddling a crash puts a calm
numerator over a violent denominator. This recomputes the DENOMINATOR ONLY at lag 60, using
`idio/market_semidev_bridge.py`'s own function — imported, not reimplemented — so k can be
formed on matched windows and the verdict tested for lag-dependence.

  python3 tools/tierA_market_semidev_lag60.py --repo /path/to/aeg-valuation --out /tmp/tierA

NOT A VALUATION.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", default="/tmp/tierA")
    ap.add_argument("--lag", type=int, default=60)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    sys.path.insert(0, os.path.join(a.repo, "idio"))
    import market_semidev_bridge as B

    dates, rets, _, _ = B.load_sp500(os.path.join(a.repo, "data", "market_history",
                                                  "sp500_daily_1927_2026.json"))
    print("sp500 returns: %d rows %s..%s" % (len(rets), dates[0], dates[-1]), flush=True)

    rows = []
    for i in range(len(rets)):
        v = B.market_semidev(rets, i, a.lag)
        if v is not None:
            rows.append((dates[i], v))
    p = os.path.join(a.out, "market_semidev_lag%d.csv" % a.lag)
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "market_semidev_lag%d" % a.lag])
        w.writerows(rows)
    print("wrote %s (%d rows) %s..%s" % (p, len(rows), rows[0][0], rows[-1][0]))


if __name__ == "__main__":
    main()
