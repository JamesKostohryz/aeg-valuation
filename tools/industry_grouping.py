#!/usr/bin/env python3
"""industry_grouping.py — determine the industry groupings for the idiosyncratic risk score.

JAMES'S INSTRUCTION, 2026-08-21: "Determine what the industries are. Some industries within a
sector can be merged if their risk ratings are highly correlated. This makes the number of
industry groupings more manageable and provides higher samples within industry groups."

THE MERGE CRITERION IS FIXED HERE, BEFORE ANY RESULT IS SEEN, AND IT IS ECONOMIC RATHER THAN
STATISTICAL. "Highly correlated" is not sufficient on its own: two industries can co-move
perfectly and still sit at risk ratios of 0.7 and 1.4, and merging those destroys exactly the
ranking the score exists to produce. What matters is what merging COSTS.

    distance(A,B) = RMS over common months of ( ratio_A(t) - ratio_B(t) )

That single number captures both level and co-movement — two industries at the same level moving
together have a small RMS difference; two at different levels, or moving apart, do not. And it
converts directly into the unit that matters:

    cost in basis points  =  RMS difference  x  market_ERP  x  100

So a threshold is chosen as a tolerance on the idiosyncratic ERP, not as a correlation cutoff
somebody liked the look of. At a market ERP near 3.3pp, an RMS difference of 0.076 costs about
25bp of cost of equity.

CLUSTERING. Agglomerative, average linkage, CONSTRAINED WITHIN SECTOR — an industry never merges
across a sector boundary, because sector is the coarser grouping the score already carries as its
own leg. The full threshold-versus-group-count curve is reported so the tolerance is chosen with
the trade-off visible rather than asserted.

SMALL INDUSTRIES. An industry that cannot field MIN_FIRMS names has no risk series of its own —
its "industry risk" would be one or two companies' idiosyncratic risk wearing an industry's name,
which is the defect that produced Real Estate at 6.46 on three firms earlier this week. Those
industries are pooled into `<Sector> - Other` and the count is reported per sector, not hidden.

  python3 tools/industry_grouping.py --repo /tmp/aeg
  python3 tools/industry_grouping.py --repo /tmp/aeg --tolerance-bp 25

NOT A VALUATION.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import importlib.util
import json
import math
import os
import statistics as stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "outputs", "2026-08-21-industry-groups")

MIN_FIRMS = 6           # below this an industry has no series of its own
MIN_MONTHS = 60         # an industry needs this many scored months to take part in clustering
MARKET_ERP_PP = 3.2852  # Option B, tenor 30 spot, for converting distance into basis points
WINDOW = 700
START, END = "2003-01-01", "2026-08-12"

# EODHD carries a few legacy sector strings on former constituents; normalise to the live scheme.
SECTOR_FIX = {
    "Financials": "Financial Services",
    "Consumer Discretionary": "Consumer Cyclical",
}


def tierA():
    p = os.path.join(ROOT, "tools", "tierA_denominator_ratio.py")
    s = importlib.util.spec_from_file_location("tierA", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def load_labels():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import eodhd_store as st
    lab = {}
    for t in st.universe()["all"]:
        try:
            g = st.load(t).get("General") or {}
        except Exception:
            continue
        s, i = g.get("Sector"), g.get("Industry")
        if s and i:
            s = SECTOR_FIX.get(s, s)
            if s == "Other":
                continue
            lab[t] = (s.strip(), i.strip())
    return lab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tolerance-bp", type=float, default=25.0)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    sys.path.insert(0, os.path.join(a.repo, "idio"))
    import semidev as SD

    T = tierA()
    lab = load_labels()
    panel = T.load_panel()
    shares = T.load_shares()
    crsp, eod = T.load_membership()
    print("labels for %d names, %d distinct industries"
          % (len(lab), len({v for v in lab.values()})))

    cal = sorted({d for t in ("AAPL", "XOM", "JNJ") if t in panel for d in panel[t][0]})
    cal = [d for d in cal if START <= d <= END]
    idx = {t: {d: i for i, d in enumerate(panel[t][0])} for t in panel}

    inds = sorted({v for v in lab.values()})
    lvl = {k: 100.0 for k in inds}
    px = {k: [] for k in inds}
    mkt, mlvl = [], 100.0
    counts = collections.defaultdict(dict)

    for k, d in enumerate(cal):
        if k == 0:
            continue
        tickers, _, _ = T.members_as_of(d, crsp, eod)
        num = collections.defaultdict(float)
        den = collections.defaultdict(float)
        nf = collections.Counter()
        mnum = mden = 0.0
        for t in tickers:
            key = lab.get(t)
            if key is None or t not in panel:
                continue
            pdt, padj, pcl = panel[t]
            i = idx[t].get(d)
            if i is None or i == 0 or padj[i - 1] <= 0 or padj[i] <= 0:
                continue
            sh = T.shares_at(shares, t, int(d[:4]))
            if not sh or pcl[i] <= 0:
                continue
            w = sh * pcl[i]
            r = padj[i] / padj[i - 1] - 1.0
            num[key] += w * r
            den[key] += w
            nf[key] += 1
            mnum += w * r
            mden += w
        if mden <= 0:
            continue
        mlvl *= (1.0 + mnum / mden)
        mkt.append((d, mlvl))
        for key in inds:
            if den[key] > 0:
                lvl[key] *= (1.0 + num[key] / den[key])
            px[key].append((d, lvl[key]))
            counts[key][d[:7]] = nf[key]

    def cut(s, asof, n=WINDOW):
        ds = [x[0] for x in s]
        i = bisect.bisect_right(ds, asof)
        return s[max(0, i - n):i]

    def tsd(s, asof):
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
        if prev and d[:7] != prev[:7]:
            ends.append(prev)
        prev = d
    if prev:
        ends.append(prev)
    print("%d month-ends %s .. %s" % (len(ends), ends[0], ends[-1]))

    cache = os.path.join(OUT, "industry_ratio_cache.json")
    if os.path.exists(cache):
        raw = json.load(open(cache))
        series = {tuple(k.split("||")): v for k, v in raw.items()}
        print("loaded cached ratio series for %d industries" % len(series))
    else:
        mcache = {asof: tsd(mkt, asof) for asof in ends}
        series = {}
        for n_, key in enumerate(inds):
            s = {}
            for asof in ends:
                if counts[key].get(asof[:7], 0) < MIN_FIRMS:
                    continue
                m = mcache.get(asof)
                v = tsd(cut(px[key], asof), asof)
                if m and v:
                    s[asof] = v / m
            if len(s) >= MIN_MONTHS:
                series[key] = s
            if (n_ + 1) % 20 == 0:
                print("   scored %d/%d industries" % (n_ + 1, len(inds)), flush=True)
        json.dump({"||".join(k): v for k, v in series.items()}, open(cache, "w"))
    print("industries with a usable risk series (>=%d firms, >=%d months): %d of %d"
          % (MIN_FIRMS, MIN_MONTHS, len(series), len(inds)))

    small = [k for k in inds if k not in series]
    bysec_small = collections.Counter(k[0] for k in small)
    print("pooled into '<Sector> - Other': %d industries" % len(small))

    # ---------------------------------------------------------------- distance and clustering
    D = {}
    keys = sorted(series)
    for i, x in enumerate(keys):
        for y in keys[i + 1:]:
            if x[0] != y[0]:
                continue                                # within sector only
            common = sorted(set(series[x]) & set(series[y]))
            if len(common) < MIN_MONTHS:
                continue
            D[(x, y)] = D[(y, x)] = math.sqrt(
                sum((series[x][d] - series[y][d]) ** 2 for d in common) / len(common))
    print("distance matrix: %d within-sector pairs" % (len(D) // 2))

    bysec = collections.defaultdict(list)
    for k in series:
        bysec[k[0]].append(k)

    def cluster(sec_keys, thresh):
        groups = [[k] for k in sec_keys]
        while len(groups) > 1:
            best, bi, bj = None, None, None
            for i in range(len(groups)):
                for j in range(i + 1, len(groups)):
                    ds = [D[(x, y)] for x in groups[i] for y in groups[j] if (x, y) in D]
                    if not ds:
                        continue
                    d = sum(ds) / len(ds)              # average linkage
                    if best is None or d < best:
                        best, bi, bj = d, i, j
            if best is None or best > thresh:
                break
            groups[bi] += groups[bj]
            groups.pop(bj)
        return groups

    tol_ratio = a.tolerance_bp / 100.0 / MARKET_ERP_PP
    print("\ntolerance %.0fbp of cost of equity  ->  RMS ratio distance %.4f"
          % (a.tolerance_bp, tol_ratio))

    print("\nTRADE-OFF CURVE — how many groups at each tolerance")
    print("%10s %10s %8s %s" % ("tolerance", "RMS dist", "groups", "plus <Sector>-Other"))
    curve = []
    for bp in (10, 15, 20, 25, 30, 40, 50, 75, 100):
        t = bp / 100.0 / MARKET_ERP_PP
        n = sum(len(cluster(bysec[s], t)) for s in bysec)
        curve.append((bp, t, n))
        print("%9.0fbp %10.4f %8d %s" % (bp, t, n, "+%d" % len(bysec_small)))

    groups = {}
    for s in sorted(bysec):
        for g in cluster(bysec[s], tol_ratio):
            g = sorted(g)
            med = stat.median([stat.median(list(series[k].values())) for k in g])
            name = "%s - %s" % (s, g[0][1] if len(g) == 1 else "/".join(x[1].split()[0] for x in g[:3])[:44])
            groups[name] = dict(sector=s, industries=[x[1] for x in g], median_ratio=round(med, 4),
                                n_industries=len(g))
    for s, n in bysec_small.items():
        groups["%s - Other" % s] = dict(sector=s, industries=["<pooled small industries>"],
                                        median_ratio=None, n_industries=n)

    print("\nGROUPS AT %.0fbp TOLERANCE: %d, plus %d '<Sector> - Other' buckets"
          % (a.tolerance_bp, sum(1 for g in groups.values() if g["median_ratio"] is not None),
             len(bysec_small)))
    for name in sorted(groups, key=lambda x: (groups[x]["sector"],
                                              groups[x]["median_ratio"] or 9)):
        g = groups[name]
        mr = ("%.3f" % g["median_ratio"]) if g["median_ratio"] is not None else "  -  "
        print("  %-46s ratio %s  from %d industries" % (name[:46], mr, g["n_industries"]))
        if g["n_industries"] > 1 and g["median_ratio"] is not None:
            print("        %s" % "; ".join(g["industries"])[:150])

    json.dump(dict(tolerance_bp=a.tolerance_bp, min_firms=MIN_FIRMS, groups=groups,
                   curve=[dict(bp=b, rms=r, groups=n) for b, r, n in curve]),
              open(os.path.join(OUT, "industry_groups.json"), "w"), indent=1)
    with open(os.path.join(OUT, "industry_risk_series.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "sector", "industry", "ratio", "n_firms"])
        for k in sorted(series):
            for d in sorted(series[k]):
                w.writerow([d, k[0], k[1], "%.4f" % series[k][d], counts[k].get(d[:7], 0)])
    print("\nwrote %s/industry_groups.json and industry_risk_series.csv" % OUT)


if __name__ == "__main__":
    main()
