#!/usr/bin/env python3
"""french_gics_map.py — aggregate Kenneth French's 49 industries into GICS sectors, and price
the sector idiosyncratic ERP off the result, daily, 1926 to 2026.

WHY 49 AND NOT 12. The twelve-industry set does not line up with GICS: over the 1991-2014 overlap
French "Manuf" correlates with the S&P Industrials sector at only 0.430, because Manuf straddles
GICS Industrials AND Materials. The well-matched pairs run 0.77 to 0.94. The 49-industry set has
the granularity to build the GICS sectors properly, and that is what this does.

THE WEIGHTS ARE REAL, NOT EQUAL. French publishes "Number of Firms in Portfolios" and "Average
Firm Size" monthly for every industry back to 1926-07. Their product is the industry's aggregate
market capitalisation, so sectors are built CAP-WEIGHTED from their constituent industries, using
the PRIOR month-end weights held fixed within the month. Equal-weighting 49 industries into
sectors would have made Gold and Coal count as much as Banks.

EVERY JUDGMENT CALL IS IN THE TABLE BELOW WITH ITS REASON. There are seven of them and they are
the whole content of this file; the arithmetic is trivial. They are flagged JUDGMENT so a reader
can disagree with a specific line rather than with the idea.

  python3 tools/french_gics_map.py --repo /tmp/aeg
  python3 tools/french_gics_map.py --repo /tmp/aeg --show-map

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

# A SECTOR OF THREE COMPANIES IS NOT A SECTOR, AND THE FIRST RUN OF THIS FILE PUBLISHED ONE.
# Before this guard existed, Real Estate read 6.46 in September 1941 — a number that is
# arithmetically perfect and externally absurd, because French's real estate industry held
# TWO TO THREE FIRMS from 1926 to the late 1950s. At that size the "sector" downside deviation
# is one company's idiosyncratic risk wearing a sector's name, which is this project's standing
# suspicion in its purest form.
#
# For an N-name portfolio with average pairwise correlation rho, the surviving single-name share
# of variance goes as (1-rho)/N: about 5% at N=20, about 33% at N=3. Cap weighting lowers the
# EFFECTIVE count below the nominal one, so 20 is a floor and not a comfort.
#
# The count is written on every row so a stricter filter can be applied downstream without
# recomputing anything.
MIN_FIRMS = 20      # below this the sector-month is REFUSED, not published
WARN_FIRMS = 50     # below this it is published with the count visible

GICS = {
    "10": "Energy", "15": "Materials", "20": "Industrials", "25": "Consumer Discretionary",
    "30": "Consumer Staples", "35": "Health Care", "40": "Financials",
    "45": "Information Technology", "50": "Communication Services", "55": "Utilities",
    "60": "Real Estate",
}

# industry -> (GICS code, note). "JUDGMENT" marks a call a reasonable person could make
# differently; everything else is a direct correspondence.
MAP = {
    # ---- 10 Energy
    "Oil":   ("10", "Petroleum and Natural Gas"),
    "Coal":  ("10", "JUDGMENT: GICS puts thermal coal in Energy and metallurgical coal in "
                    "Materials; French does not split them. Energy, on weight."),
    # ---- 15 Materials
    "Chems": ("15", "Chemicals"),
    "Steel": ("15", "Steel Works"),
    "Gold":  ("15", "Precious Metals"),
    "Mines": ("15", "Non-Metallic and Industrial Metal Mining"),
    "Paper": ("15", "Paper and Forest Products"),
    "Boxes": ("15", "Shipping Containers -> Containers & Packaging"),
    "Rubbr": ("15", "JUDGMENT: Rubber and Plastic Products. GICS splits these between Chemicals "
                    "(Materials) and auto components (Consumer Discretionary). Materials, on the "
                    "chemical-input reading."),
    "BldMt": ("15", "JUDGMENT: Construction Materials is GICS Materials, but French's BldMt also "
                    "carries building PRODUCTS, which GICS puts in Industrials."),
    "FabPr": ("15", "JUDGMENT: Fabricated Products. Metal fabrication sits close to both "
                    "Materials and Industrials; assigned Materials as an input industry."),
    # ---- 20 Industrials
    "Mach":  ("20", "Machinery"),
    "ElcEq": ("20", "Electrical Equipment"),
    "Aero":  ("20", "Aircraft -> Aerospace & Defense"),
    "Ships": ("20", "Shipbuilding, Railroad Equipment"),
    "Guns":  ("20", "Defense"),
    "Cnstr": ("20", "Construction -> Construction & Engineering"),
    "Trans": ("20", "Transportation"),
    "BusSv": ("45", "CORRECTED 2026-08-20, and the correction is a fact about GICS rather than a "
                    "preference. I first assigned Business Services to Industrials on the "
                    "advertising/printing/personnel reading. But GICS classified Data Processing "
                    "& Outsourced Services under INFORMATION TECHNOLOGY (45102020) until the "
                    "March 2023 restructure moved it to Industrials and Financials — so for "
                    "almost the whole period this data covers, IT is the correct GICS home for "
                    "the bulk of this industry. Found while running a mapping sensitivity test; "
                    "the correlation effect is small (Industrials 0.392 -> 0.405), so this is a "
                    "correctness fix, not the thing that fixes Industrials."),
    "Whlsl": ("20", "JUDGMENT: Wholesale -> Trading Companies & Distributors (Industrials). Food "
                    "and drug wholesale would be Consumer Staples Distribution under GICS."),
    # ---- 25 Consumer Discretionary
    "Toys":  ("25", "Recreation -> Leisure Products"),
    "Autos": ("25", "Automobiles and Trucks"),
    "Clths": ("25", "Apparel"),
    "Txtls": ("25", "Textiles"),
    "Rtail": ("25", "Retail. GICS moves food and drug retail to Staples; French does not split."),
    "Meals": ("25", "Restaurants, Hotels, Motels"),
    "PerSv": ("25", "JUDGMENT: Personal Services -> Consumer Services (Consumer Discretionary); "
                    "GICS routes education and some staffing elsewhere."),
    # ---- 30 Consumer Staples
    "Food":  ("30", "Food Products"),
    "Soda":  ("30", "Candy and Soda -> Beverages"),
    "Beer":  ("30", "Beer and Liquor -> Beverages"),
    "Smoke": ("30", "Tobacco Products"),
    "Agric": ("30", "Agriculture -> Agricultural Products"),
    "Hshld": ("30", "JUDGMENT: French's Consumer Goods carries household products and cosmetics "
                    "(GICS Staples) alongside housewares (GICS Discretionary). Staples, on "
                    "weight."),
    # ---- 35 Health Care
    "Hlth":  ("35", "Healthcare services"),
    "MedEq": ("35", "Medical Equipment"),
    "Drugs": ("35", "Pharmaceutical Products"),
    # ---- 40 Financials
    "Banks": ("40", "Banking"),
    "Insur": ("40", "Insurance"),
    "Fin":   ("40", "Trading -> Capital Markets"),
    # ---- 45 Information Technology
    "Hardw": ("45", "Computers"),
    "Softw": ("45", "Computer Software"),
    "Chips": ("45", "Electronic Equipment -> Semiconductors"),
    "LabEq": ("45", "JUDGMENT: Measuring and Control Equipment -> Electronic Equipment & "
                    "Instruments (IT). GICS routes life-science instruments to Health Care."),
    # ---- 50 Communication Services
    "Telcm": ("50", "Communication"),
    "Fun":   ("50", "JUDGMENT, AND IT DEPENDS ON THE YEAR. Entertainment was Consumer "
                    "Discretionary until the 2018 GICS restructure moved it to Communication "
                    "Services. Assigned on the CURRENT definition so historical and modern "
                    "numbers are comparable."),
    "Books": ("50", "JUDGMENT: Printing and Publishing -> Media, moved to Communication Services "
                    "in the same 2018 restructure."),
    # ---- 55 Utilities
    "Util":  ("55", "Utilities"),
    # ---- 60 Real Estate
    "RlEst": ("60", "JUDGMENT: Real Estate became a GICS sector in its own right in 2016; before "
                    "that it sat inside Financials. Assigned on the CURRENT definition, for the "
                    "same reason as Fun."),
    # ---- unassigned
    "Other": (None, "French's own catch-all, labelled 'Almost Nothing'. NOT assigned to any "
                    "sector and reported separately. Folding a catch-all into a real sector is "
                    "how a number becomes quietly wrong."),
}


def iso(d):
    return "%s-%s-%s" % (d[:4], d[4:6], d[6:8])


def read_block(path, marker):
    lines = open(path).read().splitlines()
    s = next(i for i, x in enumerate(lines) if marker in x)
    names = [c.strip() for c in lines[s + 1].split(",")[1:]]
    rows = {}
    for ln in lines[s + 2:]:
        p = ln.split(",")
        k = p[0].strip()
        if not k.isdigit() or len(k) not in (6, 8):
            break
        try:
            rows[k] = [float(x) for x in p[1:]]
        except ValueError:
            break
    return names, rows


def read_factors(path):
    lines = open(path).read().splitlines()
    s = next(i for i, x in enumerate(lines) if x.strip().startswith(",Mkt-RF"))
    cols = [c.strip() for c in lines[s].split(",")[1:]]
    im, ir = cols.index("Mkt-RF"), cols.index("RF")
    out = {}
    for ln in lines[s + 1:]:
        p = ln.split(",")
        if not p[0].strip().isdigit() or len(p[0].strip()) != 8:
            break
        try:
            v = [float(x) for x in p[1:]]
        except ValueError:
            break
        out[iso(p[0].strip())] = v[im] + v[ir]
    return out


def to_px(dates, rets):
    last_bad = -1
    for i, r in enumerate(rets):
        if r is None or r in MISSING:
            last_bad = i
    d, r = dates[last_bad + 1:], rets[last_bad + 1:]
    px, p = [], 100.0
    for x in r:
        p *= (1.0 + x / 100.0)
        px.append(p)
    return list(zip(d, px))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--show-map", action="store_true")
    ap.add_argument("--start", default="1928-07-01")
    ap.add_argument("--end", default="2026-06-30")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    if a.show_map:
        by = {}
        for ind, (g, note) in MAP.items():
            by.setdefault(g, []).append((ind, note))
        for g in sorted(by, key=lambda x: (x is None, x)):
            print("\n%s %s" % (g or "--", GICS.get(g, "UNASSIGNED")))
            for ind, note in sorted(by[g]):
                flag = "JUDGMENT" if note.startswith("JUDGMENT") else "        "
                print("   %-7s %s %s" % (ind, flag, note.replace("JUDGMENT: ", "")
                                         .replace("JUDGMENT, ", "")[:150]))
        return

    sys.path.insert(0, os.path.join(a.repo, "idio"))
    import semidev as SD

    dpath = os.path.join(FF, "49_Industry_Portfolios_Daily.csv")
    mpath = os.path.join(FF, "49_Industry_Portfolios.csv")
    names, dret = read_block(dpath, "Average Value Weighted Returns -- Daily")
    _, nfirm = read_block(mpath, "Number of Firms in Portfolios")
    nm2, asize = read_block(mpath, "Average Firm Size")
    fac = read_factors(os.path.join(FF, "F-F_Research_Data_Factors_daily.csv"))
    unknown = [n for n in names if n not in MAP]
    if unknown:
        raise SystemExit("industries with no mapping entry: %s — refusing" % unknown)

    # industry aggregate market cap and firm count by month
    cap, firms = {}, {}
    for m in nfirm:
        if m not in asize:
            continue
        cap[m], firms[m] = {}, {}
        for j, n in enumerate(names):
            f, s = nfirm[m][j], asize[m][j]
            firms[m][n] = int(f) if f > 0 else 0
            if f > 0 and s not in MISSING and s > 0:
                cap[m][n] = f * s
    months = sorted(cap)

    def sector_firms(g, ym):
        i = bisect.bisect_right(months, ym) - 1
        if i < 0:
            return 0
        f = firms[months[i]]
        return sum(f.get(n, 0) for n in names if MAP[n][0] == g)
    print("industry caps: %d months %s .. %s" % (len(months), months[0], months[-1]))

    days = sorted(set(dret) & set(iso_d for iso_d in [k for k in dret]))
    days = sorted(k for k in dret if iso(k) in fac)
    print("daily returns: %d days %s .. %s" % (len(days), iso(days[0]), iso(days[-1])))

    sectors = sorted({g for g, _ in MAP.values() if g})
    sec_ret = {g: [] for g in sectors}
    sec_dates = []
    for d in days:
        m = d[:6]
        i = bisect.bisect_right(months, m) - 2      # PRIOR month-end weights
        w = cap[months[max(0, i)]] if months else {}
        vals = dret[d]
        sec_dates.append(iso(d))
        for g in sectors:
            num = den = 0.0
            for j, n in enumerate(names):
                if MAP[n][0] != g:
                    continue
                v, cw = vals[j], w.get(n, 0.0)
                if cw > 0 and v not in MISSING:
                    num += cw * v
                    den += cw
            sec_ret[g].append(num / den if den > 0 else None)

    mkt = to_px(sec_dates, [fac[x] for x in sec_dates])
    series = {}
    for g in sectors:
        s = to_px(sec_dates, sec_ret[g])
        series[g] = s
        print("   %-2s %-24s starts %s" % (g, GICS[g], s[0][0] if s else "n/a"))

    def cut(s, asof, n=WINDOW):
        ds = [x[0] for x in s]
        return s[max(0, bisect.bisect_right(ds, asof) - n):bisect.bisect_right(ds, asof)]

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
        if a.start <= d <= a.end:
            if prev and d[:7] != prev[:7]:
                ends.append(prev)
            prev = d
    if prev:
        ends.append(prev)

    out = []
    for asof in ends:
        m = tsd(mkt, asof)
        if m is None:
            continue
        rec = {"date": asof, "market_total": round(m, 4)}
        ym = asof[:4] + asof[5:7]
        for g in sectors:
            nf = sector_firms(g, ym)
            rec["%s_firms" % g] = nf
            v = tsd(cut(series[g], asof), asof)
            if v is not None and nf >= MIN_FIRMS:
                rec["%s_total" % g] = round(v, 4)
                rec["%s_ratio" % g] = round(v / m, 4)
        out.append(rec)

    cols = ["date", "market_total"] + [c for g in sectors
                                       for c in ("%s_total" % g, "%s_ratio" % g, "%s_firms" % g)]
    p = os.path.join(OUT, "french_gics_sector_semidev.csv")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    print("\nwrote %s (%d months %s .. %s)" % (p, len(out), out[0]["date"], out[-1]["date"]))

    print("\nGICS SECTOR RISK RELATIVE TO THE MARKET   (firm-count guard: refuse below %d)"
          % MIN_FIRMS)
    print("%-4s %-24s %6s %10s %8s %8s %8s %9s %11s"
          % ("gics", "sector", "n", "usable from", "min", "median", "max", "%>1", "ERP @4.13pp"))
    for g in sectors:
        v = [r["%s_ratio" % g] for r in out if "%s_ratio" % g in r]
        first = next((r["date"] for r in out if "%s_ratio" % g in r), None)
        if not v:
            print("%-4s %-24s %6d %10s  REFUSED AT EVERY DATE" % (g, GICS[g], 0, "-"))
            continue
        print("%-4s %-24s %6d %10s %8.3f %8.3f %8.3f %8.0f%% %10.2fpp"
              % (g, GICS[g], len(v), first[:7], min(v), stat.median(v), max(v),
                 100 * sum(1 for x in v if x > 1) / len(v), 4.13 * stat.median(v)))
    refused = sum(1 for r in out for g in sectors if "%s_ratio" % g not in r)
    print("   %d of %d sector-months refused on the firm-count guard"
          % (refused, len(out) * len(sectors)))
    eq = [stat.mean([r["%s_ratio" % g] for g in sectors if "%s_ratio" % g in r]) for r in out]
    print("\nequal-weighted average sector ratio: median %.3f" % stat.median(eq))

    print("\ncrisis spot checks — riskiest and calmest GICS sector:")
    for d_ in ["1932-06", "1974-10", "1987-11", "2000-03", "2002-09", "2008-12", "2020-04",
               "2026-06"]:
        r = next((x for x in out if x["date"][:7] == d_), None)
        if r:
            t = sorted(((r["%s_ratio" % g], GICS[g]) for g in sectors if "%s_ratio" % g in r),
                       reverse=True)
            print("   %s  %-24s %.2f   |  %-24s %.2f"
                  % (r["date"], t[0][1], t[0][0], t[-1][1], t[-1][0]))


if __name__ == "__main__":
    main()
