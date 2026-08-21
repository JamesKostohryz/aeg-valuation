#!/usr/bin/env python3
"""tierA_denominator_ratio.py — measure k(t) = capw_avg_semidev(t) / market_semidev(t).

RUNS THE PRE-REGISTERED PLAN IN docs/PREREG-Company-Leg-Denominator-2026-08-20.md, committed as
aeg-valuation a6ff42f BEFORE any date of k other than 2026-08 was computed.

THE STATISTIC IS IMPORTED, NEVER REIMPLEMENTED. `idio/semidev.py` supplies blended_semidev and
everything under it. The denominator is READ from `outputs/market_semidev_history.csv`, the
published reconstruction, and is not recomputed here.

  python3 tools/tierA_denominator_ratio.py --repo /path/to/aeg-valuation --out /tmp/tierA

NOT A VALUATION.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import datetime as dt
import glob
import json
import os
import statistics as stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ------------------------------------------------------------------ inputs, all pre-registered

PANEL = os.path.join(ROOT, "outputs", "eodhd_store", "prices_adj_close_v2", "*.parquet")
PXCACHE = os.path.join(ROOT, "outputs", ".px_cache")
FUNDCACHE = os.path.join(ROOT, "outputs", ".eodhd_fund_cache")
CRSP = os.path.join(ROOT, "outputs", "crsp_store", "parsed_windows.json")
COMPUSTAT_CAPS = "/tmp/cap_panel.csv"          # extracted from outputs/compustat_raw/all_data.csv

CRSP_CUTOFF = "2012-12-31"
WINDOW_DAYS = 700          # >= 2y (504) + lag (60) + slack; see note in slice_upto()
G5_COUNT_FLOOR = 0.80      # pre-registered
DRAWDOWN_THRESHOLD = 0.20  # reused verbatim from the semi-deviation bridge
DRAWDOWN_TAIL = 252


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ price panel

def load_panel():
    """{ticker: (dates[iso], adj_close[float], close[float])}, each sorted ascending."""
    import pandas as pd
    parts = collections.defaultdict(list)
    for f in sorted(glob.glob(PANEL)):
        df = pd.read_parquet(f, columns=["ticker", "date", "close", "adjusted_close"])
        df["ticker"] = df.ticker.astype(str)
        for t, g in df.groupby("ticker", observed=True):
            g = g.sort_values("date")
            parts[t].append(g)
    out = {}
    for t, gs in parts.items():
        g = gs[0] if len(gs) == 1 else __import__("pandas").concat(gs).sort_values("date")
        out[t] = ([d.isoformat() for d in g.date],
                  [float(x) for x in g.adjusted_close],
                  [float(x) for x in g.close])
    return out


def load_px_cache(name):
    d = json.load(open(os.path.join(PXCACHE, name)))
    dates = [r["date"] for r in d]
    adj = [float(r["adjusted_close"]) for r in d]
    close = [float(r["close"]) for r in d]
    return dates, adj, close


def slice_upto(dates, values, asof, n=WINDOW_DAYS):
    """The last <= n observations dated <= asof, as [(date, px)].

    WHY THIS IS THE SAME ANSWER as passing the whole series with asof=. `aligned_returns`
    filters to <= asof, then `clean_series` truncates at the LAST adjustment discontinuity, then
    the last `years x 252` pairs are taken. A break BEFORE this window leaves the window
    untouched; a break INSIDE it is seen identically here. Verified numerically in
    check_slicing_equivalence() below rather than argued."""
    i = bisect.bisect_right(dates, asof)
    if i == 0:
        return []
    lo = max(0, i - n)
    return list(zip(dates[lo:i], values[lo:i]))


# ------------------------------------------------------------------ membership

def load_membership():
    """(crsp_windows, eodhd_windows). CRSP is authoritative to 2012-12-31, EODHD after."""
    d = json.load(open(CRSP))
    pt = {int(k): v for k, v in d["permno_ticker"].items()}
    crsp = []
    for permno, name, s, e in d["all_windows"]:
        t = pt.get(int(permno))
        crsp.append((t, name, s, e, int(permno)))

    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import eodhd_store as st
    eod = []
    for code, c in st.universe()["historical"].items():
        eod.append((code, c.get("start") or "1900-01-01", c.get("end") or "2100-01-01"))
    return crsp, eod


def members_as_of(day, crsp, eod):
    """(tickers_in_index, n_true_members) at `day`, on the pre-registered splice."""
    if day <= CRSP_CUTOFF:
        rows = [(t, p) for t, n, s, e, p in crsp if s <= day <= e]
        return [t for t, p in rows if t], len(rows), [p for t, p in rows]
    ts = [c for c, s, e in eod if s <= day <= e]
    return ts, len(ts), []


# ------------------------------------------------------------------ cap weights

def load_shares():
    """{ticker: [(year:int, shares:float)]} from EODHD shares_annual, ascending."""
    out = {}
    for f in glob.glob(os.path.join(FUNDCACHE, "*.shares_annual.json")):
        t = os.path.basename(f).split(".")[0]
        try:
            d = json.load(open(f))
        except Exception:
            continue
        rows = []
        for v in d.values():
            y = str(v.get("date") or "")
            if not y.isdigit():
                continue
            try:
                s = float(v.get("shares") or 0)
            except (TypeError, ValueError):
                continue
            if s > 0:
                rows.append((int(y), s))
        if rows:
            out[t] = sorted(rows)
    return out


def shares_at(shares, t, year):
    L = shares.get(t)
    if not L:
        return None
    i = bisect.bisect_right(L, (year, float("inf"))) - 1
    return L[i][1] if i >= 0 else None


# ------------------------------------------------------------------ compustat cap coverage

def load_compustat_caps():
    caps = collections.defaultdict(list)
    if not os.path.exists(COMPUSTAT_CAPS):
        return caps
    for r in csv.DictReader(open(COMPUSTAT_CAPS)):
        v = None
        try:
            if r["mkvaltq"]:
                v = float(r["mkvaltq"])
            elif r["cshoq"] and r["prccq"]:
                v = float(r["cshoq"]) * float(r["prccq"])
        except ValueError:
            v = None
        if v and v > 0:
            caps[int(r["permno"])].append((r["datadate"], v))
    for k in caps:
        caps[k].sort()
    return caps


def compustat_cap_at(caps, permno, day, max_stale_days=400):
    L = caps.get(permno)
    if not L:
        return None
    i = bisect.bisect_right(L, (day, float("inf"))) - 1
    if i < 0:
        return None
    age = (dt.date.fromisoformat(day) - dt.date.fromisoformat(L[i][0])).days
    return None if age > max_stale_days else L[i][1]


# ------------------------------------------------------------------ the denominator

def load_market_semidev(repo):
    p = os.path.join(repo, "outputs", "market_semidev_history.csv")
    out = {}
    for r in csv.DictReader(open(p)):
        try:
            out[r["date"]] = float(r["market_semidev"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


# ------------------------------------------------------------------ drawdown days, reused

def drawdown_days(dates, close, threshold=DRAWDOWN_THRESHOLD, tail=DRAWDOWN_TAIL):
    n = len(close)
    peak, out, last = [], set(), None
    for i in range(n):
        peak.append(max(close[max(0, i - 252):i + 1]))
    for i in range(n):
        if close[i] < (1.0 - threshold) * peak[i]:
            last = i
        if last is not None and i - last <= tail:
            out.add(dates[i])
    return out


# ------------------------------------------------------------------ main

def month_ends(dates, start, end):
    out, prev = [], None
    for d in dates:
        if d < start or d > end:
            continue
        if prev is not None and d[:7] != prev[:7]:
            out.append(prev)
        prev = d
    if prev:
        out.append(prev)
    return out


def check_slicing_equivalence(SD, panel, market, dates_to_check, tickers):
    """Prove the WINDOW_DAYS shortcut equals the full-series call. Not asserted, run."""
    worst, n = 0.0, 0
    for t in tickers:
        if t not in panel:
            continue
        pd_, padj, _ = panel[t]
        for asof in dates_to_check:
            full = SD.blended_semidev(list(zip(pd_, padj)), list(zip(market[0], market[1])),
                                      asof=asof)
            cut = SD.blended_semidev(slice_upto(pd_, padj, asof),
                                     slice_upto(market[0], market[1], asof), asof=asof)
            if full is None and cut is None:
                continue
            if full is None or cut is None:
                return float("inf"), n
            worst = max(worst, abs(full - cut))
            n += 1
    return worst, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", default="/tmp/tierA")
    ap.add_argument("--start", default="1995-01-01")
    ap.add_argument("--end", default="2026-08-12")
    ap.add_argument("--proxy", default="SPY", choices=["SPY", "GSPC"])
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    sys.path.insert(0, os.path.join(a.repo, "idio"))
    import semidev as SD
    log("semidev.py: LAG=%d BLEND=%s MARKET=%s" % (SD.LAG_TRADING_DAYS, SD.BLEND_WINDOWS,
                                                   SD.MARKET))

    log("loading price panel ...")
    panel = load_panel()
    log("  %d tickers" % len(panel))

    mkt_name = "SPY_US_1950-01-01.json" if a.proxy == "SPY" else "GSPC_INDX_1950-01-01.json"
    mdates, madj, mclose = load_px_cache(mkt_name)
    market = (mdates, madj)
    log("  market proxy %s: %d rows %s..%s" % (a.proxy, len(mdates), mdates[0], mdates[-1]))

    crsp, eod = load_membership()
    shares = load_shares()
    ccaps = load_compustat_caps()
    msd = load_market_semidev(a.repo)
    ddays = drawdown_days(mdates, mclose)
    log("  membership: %d crsp windows, %d eodhd windows; shares for %d tickers; "
        "compustat caps for %d permnos" % (len(crsp), len(eod), len(shares), len(ccaps)))

    ends = month_ends(mdates, a.start, a.end)
    log("  %d month-ends %s .. %s" % (len(ends), ends[0], ends[-1]))

    # equivalence proof, before any result is used
    worst, nchk = check_slicing_equivalence(
        SD, panel, market, ends[::40][:8], ["MSFT", "PEP", "KO", "XOM", "GE"])
    log("  slicing shortcut vs full-series: worst |diff| = %.3e over %d calls" % (worst, nchk))
    if worst > 1e-9:
        raise SystemExit("slicing shortcut is NOT equivalent; refusing to continue")

    # ---- resume. Rows already written stand; the run is idempotent per date.
    out = os.path.join(a.out, "tierA_k_%s.csv" % a.proxy.lower())
    rows, done = [], set()
    if os.path.exists(out):
        for r in csv.DictReader(open(out)):
            rows.append(r)
            done.add(r["date"])
        log("  resuming: %d dates already computed" % len(done))

    fields = ["date", "n_true", "n_scored", "n_weighted", "count_cov", "cap_cov",
              "capw_avg_semidev", "eqw_avg_semidev", "market_semidev", "k", "drawdown"]
    fh = open(out, "a" if done else "w", newline="")
    wtr = csv.DictWriter(fh, fieldnames=fields)
    if not done:
        wtr.writeheader()

    for asof in ends:
        if asof in done:
            continue
        tickers, n_true, permnos = members_as_of(asof, crsp, eod)
        yr = int(asof[:4])
        sd_i, cap_i = {}, {}
        for t in tickers:
            if t not in panel:
                continue
            pdt, padj, pcl = panel[t]
            v = SD.blended_semidev(slice_upto(pdt, padj, asof),
                                   slice_upto(market[0], market[1], asof), asof=asof)
            if v is None:
                continue
            sd_i[t] = v
            i = bisect.bisect_right(pdt, asof) - 1
            if i < 0:
                continue
            sh = shares_at(shares, t, yr)
            if sh and pcl[i] > 0:
                cap_i[t] = sh * pcl[i]

        cov = [t for t in sd_i if t in cap_i]
        if not cov:
            continue
        tot = sum(cap_i[t] for t in cov)
        capw = sum(cap_i[t] * sd_i[t] for t in cov) / tot
        eqw = stat.mean(sd_i[t] for t in cov)

        # compustat cap coverage of the TRUE roster, diagnostic
        cap_cov = None
        if permnos and ccaps:
            tt = hh = 0.0
            tick_by_permno = {}
            for t_, n_, s_, e_, p_ in crsp:
                if s_ <= asof <= e_:
                    tick_by_permno[p_] = t_
            for p in permnos:
                c = compustat_cap_at(ccaps, p, asof)
                if c is None:
                    continue
                tt += c
                if tick_by_permno.get(p) in sd_i:
                    hh += c
            cap_cov = hh / tt if tt > 0 else None

        row = dict(
            date=asof, n_true=n_true, n_scored=len(sd_i), n_weighted=len(cov),
            count_cov=len(sd_i) / n_true if n_true else None,
            cap_cov=cap_cov,
            capw_avg_semidev=capw, eqw_avg_semidev=eqw,
            market_semidev=msd.get(asof),
            k=(capw / msd[asof]) if asof in msd and msd[asof] else None,
            drawdown=1 if asof in ddays else 0,
        )
        rows.append(row)
        wtr.writerow(row)
        fh.flush()
        if len(rows) % 12 == 0:
            log("  %s  n=%3d/%3d  capw=%.3f  msd=%s  k=%s"
                % (asof, len(sd_i), n_true, capw,
                   ("%.3f" % row["market_semidev"]) if row["market_semidev"] else "-",
                   ("%.4f" % row["k"]) if row["k"] else "-"))

    fh.close()
    log("wrote %s (%d rows)" % (out, len(rows)))


if __name__ == "__main__":
    main()
