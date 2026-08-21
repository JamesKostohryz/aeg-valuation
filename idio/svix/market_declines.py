#!/usr/bin/env python3
"""
market_declines.py -- the market-decline episode table, and the two Layer 2 measures.

MEASUREMENT ONLY. Nothing here touches the sealed workbook or a published valuation.

PART 1 -- THE EPISODE TABLE
Every peak-to-trough decline in the index of at least a threshold (default 10%),
with peak date, trough date, depth, duration and recovery date. An episode runs
from a running-maximum peak to the lowest point reached before the index regains
that peak. This is the standard drawdown decomposition and it produces
non-overlapping episodes by construction.

PART 2 -- CRASH CAPTURE, CC_i
Over each market episode's peak-to-trough window, the stock's return divided by the
market's return. CC_i is the MEDIAN across episodes -- median, not mean, so that one
2008 or one 2020 cannot own the number.

PART 3 -- SOLO-CRASH INTENSITY, SC_i
James's definition, set 12 August 2026. A solo-crash event is a peak-to-trough
window in the STOCK where all three hold at once:

    (1) the stock's own decline is at least 10%;
    (2) the stock underperforms the market by at least 10 percentage points;
    (3) the market's own decline over that same window is less than 10%.

His worked example: stock down 16%, market down 5%. Decline 16% clears (1);
underperformance of 11 points clears (2); a 5% market decline clears (3). Triggers.

Condition (1) is the one that does the real work. Underperformance alone is not a
loss -- a stock flat while the market rallies 15% has underperformed by 15 and cost
its holder nothing.

    SC_i = (events per year) x (average depth of those events)

CORRECTED 12 August 2026, after the first live run. SC_i is NOT an annualized
expected loss and must not be read as a premium: a drawdown that recovers has cost a
buy-and-hold owner nothing, so summing depths counts round trips as one-way tickets.
On real data it produces absurdities (PepsiCo 6.88% a year). Two numbers are
reported instead -- intensity_all, which ranks firms but has no meaningful level,
and intensity_permanent, restricted to events not recovered within five years, which
is much closer to an expected permanent impairment. See solo_crashes() for the full
correction note.

DATA
----
Daily closes. Adjusted for splits and dividends for the stock (total return);
the index series is price-only unless a total-return series is supplied, and the
comparison must be like-for-like -- see --index-is-total-return. Nominal, not real:
over a window of weeks or months the inflation adjustment is immaterial, and
mixing a monthly deflator into a daily series adds more error than it removes.

USAGE
  export EODHD_API_KEY=...
  python3 tools/market_declines.py --index GSPC.INDX --from 1950-01-01 \\
      --tickers PEP,AAPL,KO,WMT,COST --out outputs/declines

  python3 tools/market_declines.py --self-test     # no key needed
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import urllib.parse
import urllib.request

BASE = "https://eodhd.com/api"


# ------------------------------------------------------------------ episode core

def drawdown_episodes(dates, closes, threshold=0.10):
    """
    Non-overlapping peak-to-trough episodes of at least `threshold`.

    Walks the series once. A peak is a running maximum. From a peak, the episode's
    trough is the minimum reached before the series regains the peak. If that
    trough is at least `threshold` below the peak, the episode is recorded.

    Returns a list of dicts. The final episode may be unrecovered, in which case
    recovery_date is None -- that is a real state of the world, not a defect, and it
    is reported rather than dropped.
    """
    eps = []
    n = len(closes)
    i = 0
    while i < n:
        peak_i = i
        peak = closes[i]
        # advance while making new highs
        j = i + 1
        while j < n and closes[j] >= peak:
            peak, peak_i = closes[j], j
            j += 1
        if j >= n:
            break
        # from peak_i, find the trough before recovery to `peak`
        trough_i, trough = j, closes[j]
        k = j
        while k < n and closes[k] < peak:
            if closes[k] < trough:
                trough, trough_i = closes[k], k
            k += 1
        depth = (trough - peak) / peak
        if -depth >= threshold:
            eps.append({
                "peak_date": dates[peak_i], "peak": peak,
                "trough_date": dates[trough_i], "trough": trough,
                "decline_pct": 100.0 * depth,
                "days_to_trough": trough_i - peak_i,
                "recovery_date": dates[k] if k < n else None,
                "days_to_recover": (k - peak_i) if k < n else None,
                "_pi": peak_i, "_ti": trough_i,
            })
            i = trough_i + 1 if k >= n else k
        else:
            i = k if k > peak_i else peak_i + 1
    return eps


def ret_between(series, d0, d1):
    """Total return between two dates using the nearest available close at or
    before each date. Returns None if either side is unavailable."""
    a = _at_or_before(series, d0)
    b = _at_or_before(series, d1)
    if a is None or b is None or a <= 0:
        return None
    return b / a - 1.0


def _at_or_before(series, d):
    """series: sorted list of (date_str, close)."""
    lo, hi, best = 0, len(series) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= d:
            best = series[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return best


# ----------------------------------------------------------- the two Layer 2 stats

def crash_capture(stock, market_episodes, min_episodes=3):
    """
    CC_i = median over market episodes of (stock decline / market decline), measured
    over the market's own peak-to-trough dates.

    A value of 1.0 means the stock falls exactly with the market in market declines.
    Above 1.0 means it falls more. Below 1.0 means it falls less -- and note a
    NEGATIVE value means it ROSE while the market fell, which is real information
    and is kept, not clipped.
    """
    ratios = []
    for e in market_episodes:
        mr = e["decline_pct"] / 100.0
        sr = ret_between(stock, e["peak_date"], e["trough_date"])
        if sr is None or mr >= -1e-9:
            continue
        ratios.append(sr / mr)
    if len(ratios) < min_episodes:
        return None, len(ratios), ratios
    return statistics.median(ratios), len(ratios), ratios


def solo_crashes(stock, market, own_threshold=0.10, underperf_threshold=0.10,
                 market_max_decline=0.10, permanent_years=5.0):
    """
    James's three-condition solo-crash test.

    Returns (stats, events) where stats is a dict with BOTH intensity measures --
    see the correction note below, which matters.

    ATTRIBUTION CORRECTION, 13 August 2026. James proposed the THREE-CONDITION TEST
    ONLY -- own decline of 10% or more, underperformance of 10% or more, market down
    less than 10% over the same window. He did NOT propose `intensity_permanent`, and
    on 13 August he rejected it outright: "I never proposed a permanent measure at
    all. That was never my idea." The five-year-recovery restriction below was
    invented by the 12 August session as a repair to its OWN erroneous claim that
    solo-crash intensity was already in the units of a required return.

    It is also WRONG on its merits. "Did not regain its own peak within five years"
    is a momentum filter: Nvidia compounded at 38% a year and recovered from
    everything, so it scored SAFER than PepsiCo, which the measure reported as 2.5
    times riskier. Do not use `intensity_permanent`. It is retained only so old
    outputs remain reproducible.

    THE REPLACEMENT is James's cost-basis definition -- risk is being underwater
    relative to what you paid -- in `tools/underwater_risk.py`. Use that.

    Candidate windows are the stock's own peak-to-trough episodes of at least
    `own_threshold`. Each is then tested against the market over the SAME window.

    --------------------------------------------------------------------------
    CORRECTION, 12 August 2026. The proposal originally claimed that solo-crash
    intensity is "already denominated in the units of the answer" -- a required
    return in percent per year. Run against real data, that claim is WRONG, and
    obviously so: PepsiCo shows twenty qualifying events since 1972 averaging
    -18.6%, which annualizes to 6.88% a year. Nobody is charging PepsiCo a 688
    basis point idiosyncratic premium.

    The error is that a DRAWDOWN IS NOT A LOSS. A stock that falls 20% and
    recovers within a year has cost a buy-and-hold owner nothing. Summing
    drawdown depth as though each were permanent counts a round trip as a
    one-way ticket.

    So two numbers are reported instead of one:

      intensity_all      -- frequency x depth over every qualifying event. This is
                            a RANKING statistic. Its cross-sectional ordering is
                            meaningful; its LEVEL is not a premium and must never
                            be quoted as one.

      intensity_permanent-- frequency x depth over only those events where the
                            stock had NOT regained its pre-event peak within
                            `permanent_years`. This one is closer to an expected
                            permanent impairment, which is the thing a discount
                            rate is entitled to charge for.

    Neither is used at its face value. Both enter the Layer 2 estimator centered
    on the median firm, with a coefficient fitted against the Layer 1
    option-implied premium, exactly as the proposal's section 4 specifies. That
    calibration is what supplies the scale; these statistics supply the ordering.
    --------------------------------------------------------------------------
    """
    sdates = [d for d, _ in stock]
    scloses = [c for _, c in stock]
    cand = drawdown_episodes(sdates, scloses, own_threshold)
    idx = {d: i for i, d in enumerate(sdates)}

    events = []
    for e in cand:
        stock_ret = e["decline_pct"] / 100.0                       # negative
        mkt_ret = ret_between(market, e["peak_date"], e["trough_date"])
        if mkt_ret is None:
            continue
        cond1 = -stock_ret >= own_threshold
        cond2 = (stock_ret - mkt_ret) <= -underperf_threshold
        cond3 = mkt_ret > -market_max_decline
        if not (cond1 and cond2 and cond3):
            continue

        # Did it get the money back, and how fast?
        peak_i = idx.get(e["peak_date"])
        rec_date, rec_years = e.get("recovery_date"), None
        if rec_date and peak_i is not None:
            rec_years = _year(rec_date) - _year(e["peak_date"])
        permanent = (rec_date is None) or (rec_years is not None
                                           and rec_years > permanent_years)

        events.append({
            "peak_date": e["peak_date"], "trough_date": e["trough_date"],
            "stock_decline_pct": 100.0 * stock_ret,
            "market_return_pct": 100.0 * mkt_ret,
            "underperformance_pct": 100.0 * (stock_ret - mkt_ret),
            "days_to_trough": e["days_to_trough"],
            "recovery_date": rec_date or "",
            "years_to_recover": round(rec_years, 2) if rec_years is not None else "",
            "unrecovered_in_window": "YES" if permanent else "no",
        })

    if not sdates:
        return {}, []
    years = _year(sdates[-1]) - _year(sdates[0])
    if years <= 0:
        return {}, events

    def _intensity(evs):
        if not evs:
            return 0.0
        depth = statistics.fmean([-e["stock_decline_pct"] / 100.0 for e in evs])
        return (len(evs) / years) * depth

    perm = [e for e in events if e["unrecovered_in_window"] == "YES"]
    return {
        "years_of_history": round(years, 1),
        "n_events": len(events),
        "n_permanent": len(perm),
        "intensity_all": _intensity(events),
        "intensity_permanent": _intensity(perm),
        "median_years_to_recover": (
            statistics.median([e["years_to_recover"] for e in events
                               if e["years_to_recover"] != ""])
            if any(e["years_to_recover"] != "" for e in events) else None),
    }, events


def _year(dstr):
    y, m, d = (int(x) for x in dstr.split("-"))
    return y + (m - 1) / 12.0 + (d - 1) / 365.0


# ------------------------------------------------------------------------ fetch

def eod(token, symbol, dfrom, cache="outputs/.px_cache"):
    os.makedirs(cache, exist_ok=True)
    p = os.path.join(cache, f"{symbol.replace('.', '_')}_{dfrom}.json")
    if os.path.exists(p):
        rows = json.load(open(p))
    else:
        q = urllib.parse.urlencode({"api_token": token, "fmt": "json",
                                    "from": dfrom, "period": "d"})
        with urllib.request.urlopen(f"{BASE}/eod/{symbol}?{q}", timeout=120) as r:
            rows = json.loads(r.read().decode())
        json.dump(rows, open(p, "w"))
    out = []
    for r in rows:
        c = r.get("adjusted_close", r.get("close"))
        if r.get("date") and c:
            out.append((r["date"], float(c)))
    out.sort()
    return out


# -------------------------------------------------------------------- self-test

def _synthetic_dates(n, start_year=2000):
    """n strictly increasing ISO dates, roughly 252 per year."""
    out = []
    for i in range(n):
        y = start_year + i // 252
        doy = i % 252
        out.append(f"{y:04d}-{doy // 21 + 1:02d}-{doy % 21 + 1:02d}")
    return out


PASSES, FAILS = [0], [0]


def _ck(cond, msg):
    print(f"{'PASS' if cond else 'FAIL'}  {msg}")
    (PASSES if cond else FAILS)[0] += 1


def self_test():
    print("-- episode detection --")
    # Up to 100, down to 85 (-15%), recover to 110, down to 99 (-10%), recover.
    closes = []
    for a, b, n in [(80, 100, 20), (100, 85, 15), (85, 110, 25),
                    (110, 99, 11), (99, 130, 30)]:
        for i in range(n):
            closes.append(a + (b - a) * i / max(n - 1, 1))
    dates = _synthetic_dates(len(closes))

    eps = drawdown_episodes(dates, closes, 0.10)
    _ck(len(eps) == 2, f"found {len(eps)} episodes, expected 2")
    for e in eps:
        print(f"      {e['peak_date']} {e['peak']:.1f} -> {e['trough_date']} "
              f"{e['trough']:.1f}  {e['decline_pct']:.2f}%")
    _ck(bool(eps) and abs(eps[0]["decline_pct"] + 15.0) < 0.01, "first episode is -15.00%")
    _ck(len(eps) > 1 and abs(eps[1]["decline_pct"] + 10.0) < 0.01, "second episode is -10.00%")
    _ck(all(eps[i]["trough_date"] <= eps[i + 1]["peak_date"] for i in range(len(eps) - 1)),
        "episodes do not overlap")

    print("\n-- James's worked example: stock -16%, market -5% --")

    def scenario(stock_move, market_move, n=60, flat_years=2):
        """Stock and market glide linearly to the given total move, then go flat."""
        total = n + 252 * flat_years
        ds = _synthetic_dates(total, 2010)
        s, m = [], []
        for i, d in enumerate(ds):
            f = min(i, n - 1) / (n - 1)
            s.append((d, 100.0 * (1 + stock_move * f)))
            m.append((d, 100.0 * (1 + market_move * f)))
        return s, m

    stock, market = scenario(-0.16, -0.05)
    st, events = solo_crashes(stock, market)
    sc = st.get('intensity_all')
    _ck(len(events) == 1, f"exactly one solo-crash event detected ({len(events)})")
    if events:
        e = events[0]
        print(f"      stock {e['stock_decline_pct']:.2f}%  market "
              f"{e['market_return_pct']:.2f}%  underperf "
              f"{e['underperformance_pct']:.2f}%")
        _ck(abs(e["stock_decline_pct"] + 16.0) < 0.6
            and abs(e["market_return_pct"] + 5.0) < 0.6,
            "matches James's -16% / -5% example")
    print(f"      SC = {100 * sc:.2f}% per year" if sc else "      SC = n/a")

    print("\n-- each of the three conditions must bind --")

    def case(sd, md, label, expect):
        s, m = scenario(sd, md)
        _st, ev = solo_crashes(s, m)
        got = len(ev) > 0
        _ck(got == expect,
            f"{label}: {'triggered' if got else 'no trigger'} "
            f"(expected {'trigger' if expect else 'no trigger'})")

    case(-0.16, -0.05, "stock -16%, market -5%                       ", True)
    case(-0.08, +0.05, "stock -8%, fails the 10% own-decline floor   ", False)
    case(-0.30, -0.25, "stock -30%, market -25%, market crashed too  ", False)
    case(-0.12, -0.05, "stock -12%, market -5%, underperf only 7 pts ", False)
    case(-0.25, +0.02, "stock -25%, market +2%                       ", True)
    case(-0.11, +0.01, "stock -11%, market +1%, just clears all three", True)

    print("\n" + "=" * 60)
    print(f"{PASSES[0]} passed, {FAILS[0]} failed")
    return 1 if FAILS[0] else 0


# ------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="GSPC.INDX")
    ap.add_argument("--index-is-total-return", action="store_true")
    ap.add_argument("--tickers", default="")
    ap.add_argument("--from", dest="dfrom", default="1950-01-01")
    ap.add_argument("--threshold", type=float, default=0.10)
    ap.add_argument("--out", default="outputs/declines")
    ap.add_argument("--token", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return self_test()

    token = a.token or os.environ.get("EODHD_API_KEY")
    if not token:
        cand = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), ".eodhd-token")
        if os.path.exists(cand):
            token = open(cand).read().strip()
            print("token: read from .eodhd-token (never printed)")
    if not token:
        print("ERROR: no API token. Set EODHD_API_KEY or pass --token.")
        return 2

    market = eod(token, a.index, a.dfrom)
    if not market:
        print(f"ERROR: no data for {a.index}")
        return 1
    print(f"{a.index}: {len(market)} daily closes, {market[0][0]} .. {market[-1][0]}")
    if not a.index_is_total_return:
        print("NOTE: index series is price-only; stock series are total return. "
              "Crash capture over short windows is barely affected, but say so "
              "wherever the number is published.")

    eps = drawdown_episodes([d for d, _ in market], [c for _, c in market], a.threshold)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    f1 = a.out + "_market_episodes.csv"
    cols = ["peak_date", "peak", "trough_date", "trough", "decline_pct",
            "days_to_trough", "recovery_date", "days_to_recover"]
    with open(f1, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(eps)
    print(f"\n{len(eps)} market declines of {100 * a.threshold:.0f}% or more")
    for e in eps:
        print(f"  {e['peak_date']} -> {e['trough_date']}  {e['decline_pct']:7.2f}%  "
              f"{e['days_to_trough']:5d} days down, "
              f"recovered {e['recovery_date'] or 'NOT YET'}")

    tickers = [t.strip().upper() for t in a.tickers.split(",") if t.strip()]
    rows, solo_rows = [], []
    for t in tickers:
        try:
            s = eod(token, t if "." in t else t + ".US", a.dfrom)
        except Exception as ex:
            print(f"  {t}: fetch failed -- {type(ex).__name__}")
            continue
        if not s:
            continue
        cc, n_ep, ratios = crash_capture(s, eps)
        st, ev = solo_crashes(s, market)
        rows.append({
            "ticker": t, "history_from": s[0][0],
            "years_of_history": st.get("years_of_history", ""),
            "n_market_episodes": n_ep,
            "crash_capture_median": f"{cc:.4f}" if cc is not None else "",
            "crash_capture_mean": f"{statistics.fmean(ratios):.4f}" if ratios else "",
            "solo_crash_events": st.get("n_events", 0),
            "solo_crash_unrecovered": st.get("n_permanent", 0),
            "intensity_all_pct_pa_RANKING_ONLY":
                f"{100 * st['intensity_all']:.3f}" if st else "",
            "intensity_permanent_pct_pa":
                f"{100 * st['intensity_permanent']:.3f}" if st else "",
            "median_years_to_recover": st.get("median_years_to_recover", ""),
        })
        for e in ev:
            solo_rows.append(dict(ticker=t, **e))
        print(f"  {t:5s} crash capture {'   n/a' if cc is None else f'{cc:6.3f}'} "
              f"over {n_ep:2d} episodes | {st.get('n_events',0):2d} solo crashes, "
              f"{st.get('n_permanent',0):2d} unrecovered in 5y | "
              f"intensity(all) {100*st.get('intensity_all',0):5.2f}%/yr "
              f"intensity(permanent) {100*st.get('intensity_permanent',0):5.2f}%/yr")

    if rows:
        f2 = a.out + "_stock_measures.csv"
        with open(f2, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {f1}\nwrote {f2}")
    if solo_rows:
        f3 = a.out + "_solo_crash_events.csv"
        with open(f3, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(solo_rows[0].keys()))
            w.writeheader()
            w.writerows(solo_rows)
        print(f"wrote {f3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
