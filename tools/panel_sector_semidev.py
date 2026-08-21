#!/usr/bin/env python3
"""panel_sector_semidev.py — GICS sector risk built from the actual S&P 500 constituents.

WHY THIS EXISTS. The French route cannot produce GICS Real Estate: SIC 6798 (REIT) sits inside
French's `Fin` industry, and his `RlEst` is property operators and land developers with the
income vehicles removed. James's read is that the market treats property REITs as DEFENSIVE, and
that is testable directly rather than by proxy — the daily panel holds the real constituents,
their market caps and their EODHD sector labels.

This also supplies the modern leg the French series needs for a 2014-onward join, on the same
statistic, so the two are comparable rather than spliced on faith.

    sector index  = cap-weighted daily return of that sector's members, prior month-end weights
    market index  = cap-weighted daily return of ALL panel members (not SPY: same construction
                    on both sides, so the ratio is not measuring a vendor difference)
    ratio         = semidev_TOTAL_sector / semidev_TOTAL_market

The statistic is imported from idio/semidev.py and is not reimplemented.

  python3 tools/panel_sector_semidev.py --repo /tmp/aeg

NOT A VALUATION.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import importlib.util
import os
import statistics as stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "outputs", "2026-08-20-sectors")
MIN_FIRMS = 15          # a sector of a handful of names is not a sector; see french_gics_map.py
WINDOW = 700


def tierA():
    p = os.path.join(ROOT, "tools", "tierA_denominator_ratio.py")
    s = importlib.util.spec_from_file_location("tierA", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--start", default="2001-01-01")
    ap.add_argument("--end", default="2026-08-12")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    sys.path.insert(0, os.path.join(a.repo, "idio"))
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import semidev as SD
    import eodhd_store as st

    T = tierA()
    panel = T.load_panel()
    shares = T.load_shares()
    crsp, eod = T.load_membership()

    u = st.universe()
    sector = {k: (v.get("sector") or "").strip() for k, v in u["current"].items()}
    hist = u["historical"]
    for k, v in hist.items():
        sector.setdefault(k, "")
    names = sorted({s for s in sector.values() if s})
    print("sector labels: %s\n" % ", ".join(names))

    # trading calendar from the panel's most complete name
    cal = sorted({d for t in ("AAPL", "XOM", "JNJ") if t in panel for d in panel[t][0]})
    cal = [d for d in cal if a.start <= d <= a.end]
    print("calendar %d days %s .. %s" % (len(cal), cal[0], cal[-1]))

    # per-day cap-weighted sector returns
    idx = {t: {d: i for i, d in enumerate(panel[t][0])} for t in panel}
    sec_px, mkt_px = {s: [] for s in names}, []
    lvl = {s: 100.0 for s in names}
    mlvl = 100.0
    counts = {s: {} for s in names}

    prev_members = None
    for k, d in enumerate(cal):
        if k == 0:
            continue
        ym = d[:7]
        tickers, _, _ = T.members_as_of(d, crsp, eod)
        num = collections.defaultdict(float)
        den = collections.defaultdict(float)
        mnum = mden = 0.0
        nfirm = collections.Counter()
        for t in tickers:
            s = sector.get(t)
            if not s or t not in panel:
                continue
            pdt, padj, pcl = panel[t]
            i = idx[t].get(d)
            if i is None or i == 0:
                continue
            p0, p1 = padj[i - 1], padj[i]
            if p0 <= 0 or p1 <= 0:
                continue
            sh = T.shares_at(shares, t, int(d[:4]))
            if not sh or pcl[i] <= 0:
                continue
            w = sh * pcl[i]
            r = p1 / p0 - 1.0
            num[s] += w * r
            den[s] += w
            mnum += w * r
            mden += w
            nfirm[s] += 1
        if mden <= 0:
            continue
        mlvl *= (1.0 + mnum / mden)
        mkt_px.append((d, mlvl))
        for s in names:
            if den[s] > 0:
                lvl[s] *= (1.0 + num[s] / den[s])
            sec_px[s].append((d, lvl[s]))
            counts[s][ym] = nfirm[s]

    def cut(series, asof, n=WINDOW):
        ds = [x[0] for x in series]
        i = bisect.bisect_right(ds, asof)
        return series[max(0, i - n):i]

    def tsd(series, asof):
        tot = 0.0
        for yrs, wt in zip(SD.BLEND_WINDOWS, SD.BLEND_WEIGHTS):
            rs, _ = SD.aligned_returns(series, cut(mkt_px, asof), yrs, asof)
            if rs is None:
                return None
            v = SD._semidev_about(rs, sum(rs) / len(rs))
            if v is None:
                return None
            tot += wt * v * 100.0
        return tot

    ends, prev = [], None
    for d, _ in mkt_px:
        if prev and d[:7] != prev[:7]:
            ends.append(prev)
        prev = d
    if prev:
        ends.append(prev)

    rows = []
    for asof in ends:
        m = tsd(mkt_px, asof)
        if m is None:
            continue
        rec = {"date": asof, "market_total": round(m, 4)}
        for s in names:
            nf = counts[s].get(asof[:7], 0)
            rec["%s_firms" % s] = nf
            v = tsd(cut(sec_px[s], asof), asof)
            if v is not None and nf >= MIN_FIRMS:
                rec["%s_total" % s] = round(v, 4)
                rec["%s_ratio" % s] = round(v / m, 4)
        rows.append(rec)

    cols = ["date", "market_total"] + [c for s in names
                                       for c in ("%s_total" % s, "%s_ratio" % s, "%s_firms" % s)]
    p = os.path.join(OUT, "panel_sector_semidev.csv")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print("wrote %s (%d months %s .. %s)\n" % (p, len(rows), rows[0]["date"], rows[-1]["date"]))

    print("S&P 500 SECTOR RISK RELATIVE TO THE INDEX — built from the actual constituents")
    print("%-24s %6s %10s %9s %9s %9s %8s"
          % ("sector", "n", "from", "median", "min", "max", "today"))
    res = []
    for s in names:
        v = [r["%s_ratio" % s] for r in rows if "%s_ratio" % s in r]
        if not v:
            continue
        first = next(r["date"] for r in rows if "%s_ratio" % s in r)
        today = rows[-1].get("%s_ratio" % s)
        res.append((stat.median(v), s, len(v), first, min(v), max(v), today))
    for med, s, n, first, lo, hi, today in sorted(res):
        print("%-24s %6d %10s %9.3f %9.3f %9.3f %8s"
              % (s, n, first[:7], med, lo, hi, ("%.3f" % today) if today else "-"))

    print("\nREAL ESTATE, the question that prompted this — its rank among sectors by year:")
    for y in range(2003, 2027, 2):
        r = next((x for x in rows if x["date"][:4] == str(y) and x["date"][5:7] == "12"), None)
        if not r:
            r = next((x for x in rows if x["date"][:4] == str(y)), None)
        if not r or "Real Estate_ratio" not in r:
            continue
        rk = sorted((r["%s_ratio" % s], s) for s in names if "%s_ratio" % s in r)
        pos = [i for i, (_, s) in enumerate(rk) if s == "Real Estate"][0] + 1
        print("   %s  Real Estate %.3f — rank %d of %d (1 = calmest)   calmest %s %.2f"
              % (r["date"], r["Real Estate_ratio"], pos, len(rk), rk[0][1][:16], rk[0][0]))


if __name__ == "__main__":
    main()
