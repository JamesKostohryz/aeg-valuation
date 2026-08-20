#!/usr/bin/env python3
"""
idio/market_semidev_bridge.py — the market's risk input, before options existed.

RUNS THE PRE-REGISTERED PLAN IN
AEG-Project/docs/PREREG-Semidev-ERP-Bridge-2026-08-20.md. Every choice below — the statistic,
the zero lag, the two-moment form, the tenor range, the splice, the test design and the five
falsifiers — was written down before the out-of-sample test was run.

THE PROBLEM. Historical abnormal-earnings-growth valuation needs a historical cost of equity,
which needs a historical market equity risk premium. The live method takes its risk input from
options, and options do not exist historically: CBOE VIX1Y begins 2007-01-03 (verified by direct
download, 4,933 rows). Single-name implied vol term structures are a live scrape with no history
at all.

ONLY THE MARKET LEG NEEDS A BRIDGE. The idiosyncratic leg is ALREADY a semi-deviation method —
`idio/semidev.py` is the production statistic and `idio/erp.py` prices Region 1 off it. Going
backwards changes only the market proxy and each company's own price history. Nothing about the
idiosyncratic construction is replaced here.

WHAT IS BRIDGED, AND WHY IT IS THE INPUT AND NOT THE PREMIUM. This maps
`semidev_market -> VIX1Y_equivalent`, NOT `semidev_market -> ERP`. The ERP methodology is going
to be superseded. A bridge fitted to today's ERP OUTPUT would have to be rebuilt when that
happens; a bridge fitted to the VOL INPUT does not — whatever model replaces the current one
consumes the reconstructed VIX-equivalent exactly as it consumes VIX1Y today. Recalibrating is
two numbers, not a rebuilt history.

THE STATISTIC IS IMPORTED, NEVER REIMPLEMENTED. `idio/semidev.py` supplies `_semidev_about`, the
annualization and the per-cent scaling. There is no second version of the market's risk measure
in this repository and there must never be one. The market has no market-model residual, so the
raw index log return stands in for the residual; that is the only difference and it is a
definition rather than a choice.

THE LAG IS ZERO, AND THAT IS A DEPARTURE FROM PRODUCTION. The company statistic ends its window
sixty trading days before the as-of date so that a company is not charged for its own last three
months of price action. That rationale is about idiosyncratic reflexivity and does not apply to
the market aggregate, and it costs eighteen points of correlation: 0.622 at lag 60 against 0.806
at lag 0. Looking FORWARD was tested and rejected — a quarter-ahead window scores 0.802, worse
than lag 0, so there is no case for accepting look-ahead bias for a fit it does not improve.

    python3 idio/market_semidev_bridge.py --report          # calibrate, validate, print
    python3 idio/market_semidev_bridge.py --write           # + emit the reconstruction

NOT A VALUATION.
"""
from __future__ import annotations

import csv
import json
import math
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import semidev as SD           # noqa: E402  THE statistic. Imported, not copied.


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


D = os.path.join(ROOT, "data", "market_history")
SP500 = _arg("--sp500", os.path.join(D, "sp500_daily_1927_2026.json"))
VIX1Y = _arg("--vix1y", os.path.join(D, "vix1y_2007_2026.csv"))
OUT = _arg("--out", os.path.join(ROOT, "outputs", "market_semidev_history.csv"))

MARKET_LAG = 0                 # pre-registered, section 3.3
BLEND_WINDOWS = (1, 2)         # same as the company statistic
BLEND_WEIGHTS = (0.5, 0.5)
BRIDGE_TENOR_MAX = 10          # pre-registered, section 3.5
SPLICE_START, SPLICE_END = "2007-01-03", "2012-01-03"

# falsifiers, pre-registered section 5
F1_MIN_OOS_CORR = 0.60
F2_MAX_COND_SD_RATIO = 2.0
F4_MAX_SPLICE_STEP = 5.0
F5_VIX_LO, F5_VIX_HI = 5.0, 100.0


class BridgeFalsified(RuntimeError):
    """A pre-registered falsifier fired. This goes to James, not into the engine."""


# ================================================================= inputs

def load_sp500(path=None):
    d = json.load(open(path or SP500))
    dates, close = d["dates"], [float(x) for x in d["close"]]
    rets = [math.log(close[i] / close[i - 1]) for i in range(1, len(close))]
    return dates[1:], rets, dates, close


def load_vix1y(path=None):
    out = {}
    for r in csv.DictReader(open(path or VIX1Y)):
        k = (r.get("DATE") or r.get("date") or "").strip()
        v = (r.get("CLOSE") or r.get("close") or "").strip()
        if not k or not v:
            continue
        if "/" in k:
            m, dd, y = k.split("/")
            k = "%s-%s-%s" % (y, m.zfill(2), dd.zfill(2))
        try:
            out[k] = float(v)
        except ValueError:
            continue
    return out


# ================================================================= the statistic

def market_semidev(rets, end_index, lag=MARKET_LAG):
    """The market's own downside semi-deviation, on the company statistic's primitives.

    `end_index` indexes the return series. Returns per cent, annualized, or None on short
    history. The 0.5/0.5 one- and two-year blend is the production convention.
    """
    end = end_index - lag
    total = 0.0
    for years, weight in zip(BLEND_WINDOWS, BLEND_WEIGHTS):
        n = int(round(years * SD.TRADING_DAYS))
        s = end - n
        if s < 0 or end > len(rets):
            return None
        w = rets[s:end]
        if len(w) < n * 0.8:
            return None
        v = SD._semidev_about(w, sum(w) / len(w))
        if v is None:
            return None
        total += weight * v * 100.0
    return total


def series(dates, rets, lag=MARKET_LAG):
    """(date, semidev) for every day the statistic can be computed."""
    out = []
    for i in range(len(rets)):
        v = market_semidev(rets, i, lag)
        if v is not None:
            out.append((dates[i], v))
    return out


# ================================================================= the bridge

def two_moment(x, y):
    """b matches the SPREAD, a matches the MEAN. Pre-registered section 3.4: least squares would
    shrink the historical range toward the average and flatten every crisis."""
    bx, by = st.pstdev(x), st.pstdev(y)
    if bx <= 0:
        raise BridgeFalsified("the semi-deviation series has zero spread")
    b = by / bx
    return st.mean(y) - b * st.mean(x), b


def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else float("nan")


def stats(err):
    a = sorted(abs(e) for e in err)
    return dict(n=len(err), mean=st.mean(err), sd=st.pstdev(err),
                p95=a[int(0.95 * len(a))] if a else float("nan"), max=a[-1] if a else float("nan"))


# ================================================================= drawdown conditioning

def drawdown_days(dates, close, threshold=0.20, tail=252):
    """Pre-registered section 4.2, fixed IN ADVANCE: any day more than 20% below the trailing
    252-day maximum, PLUS the 252 trading days after the last such day. A realized-vol proxy
    fails by lagging, and most days are calm, so a pooled statistic hides exactly the episodes
    an analyst would want to look at."""
    n = len(close)
    peak = []
    for i in range(n):
        peak.append(max(close[max(0, i - 252):i + 1]))
    inside = [close[i] < (1.0 - threshold) * peak[i] for i in range(n)]
    out = set()
    last = None
    for i in range(n):
        if inside[i]:
            last = i
        if last is not None and i - last <= tail:
            out.add(dates[i])
    return out


# ================================================================= main

def calibrate_and_validate(log=print):
    rdates, rets, adates, aclose = load_sp500()
    vix = load_vix1y()
    sd_by_date = dict(series(rdates, rets))
    pairs = [(d, sd_by_date[d], vix[d]) for d in sorted(vix) if d in sd_by_date]
    if not pairs:
        raise BridgeFalsified("no overlap between the semi-deviation series and VIX1Y")
    dd = drawdown_days(adates, aclose)

    log("OVERLAP: %d days, %s -> %s" % (len(pairs), pairs[0][0], pairs[-1][0]))
    log("  of which within 12 months of a >20%% drawdown: %d (%.0f%%)"
        % (sum(1 for p in pairs if p[0] in dd), 100.0 * sum(1 for p in pairs if p[0] in dd) / len(pairs)))

    X = [p[1] for p in pairs]
    Y = [p[2] for p in pairs]
    a_full, b_full = two_moment(X, Y)
    log("\nFULL-SAMPLE BRIDGE (in-sample; the form was chosen on this window and it is declared)")
    log("  VIX_equiv = %.4f + %.4f x semidev      corr %.4f" % (a_full, b_full, corr(X, Y)))

    splits = [("fit 2007-2016 -> test 2017-2026", lambda d: d < "2017-01-01"),
              ("fit 2017-2026 -> test 2007-2016", lambda d: d >= "2017-01-01")]
    log("\nOUT-OF-SAMPLE, BOTH DIRECTIONS (pre-registered section 4.1)")
    results = []
    for name, in_fit in splits:
        fit = [p for p in pairs if in_fit(p[0])]
        tst = [p for p in pairs if not in_fit(p[0])]
        a, b = two_moment([p[1] for p in fit], [p[2] for p in fit])
        err = [(a + b * p[1]) - p[2] for p in tst]
        c = corr([a + b * p[1] for p in tst], [p[2] for p in tst])
        s_all = stats(err)
        cond = [(a + b * p[1]) - p[2] for p in tst if p[0] in dd]
        calm = [(a + b * p[1]) - p[2] for p in tst if p[0] not in dd]
        s_cond = stats(cond) if cond else None
        s_calm = stats(calm) if calm else None
        results.append((name, a, b, c, s_all, s_cond, s_calm))
        log("  %s" % name)
        log("     a %+.4f  b %+.4f   test n=%d  corr %.4f" % (a, b, s_all["n"], c))
        log("     VIX-equivalent error   mean %+.3f  sd %.3f  p95 %.3f  max %.3f"
            % (s_all["mean"], s_all["sd"], s_all["p95"], s_all["max"]))
        if s_cond:
            log("       within 12m of a drawdown (n=%d)  mean %+.3f  sd %.3f  p95 %.3f"
                % (s_cond["n"], s_cond["mean"], s_cond["sd"], s_cond["p95"]))
        if s_calm:
            log("       calm days               (n=%d)  mean %+.3f  sd %.3f  p95 %.3f"
                % (s_calm["n"], s_calm["mean"], s_calm["sd"], s_calm["p95"]))
    return dict(pairs=pairs, a=a_full, b=b_full, results=results, drawdown=dd,
                rdates=rdates, rets=rets, sd_by_date=sd_by_date, vix=vix)


def check_falsifiers(res, log=print):
    """Pre-registered section 5. Reported whichever way they come out."""
    fired = []
    for name, a, b, c, s_all, s_cond, s_calm in res["results"]:
        if c < F1_MIN_OOS_CORR:
            fired.append("F1 %s: out-of-sample correlation %.4f below %.2f" % (name, c, F1_MIN_OOS_CORR))
        if b <= 0:
            fired.append("F3 %s: fitted slope %.4f is not positive" % (name, b))
        if s_cond and s_calm and s_calm["sd"] > 0:
            r = s_cond["sd"] / s_calm["sd"]
            if r > F2_MAX_COND_SD_RATIO:
                fired.append("F2 %s: drawdown-conditional error sd is %.2fx the calm-day sd "
                             "(limit %.1fx)" % (name, r, F2_MAX_COND_SD_RATIO))
            else:
                log("  F2 %s: conditional/calm error sd ratio %.2fx (limit %.1f) - does not fire"
                    % (name, r, F2_MAX_COND_SD_RATIO))
    # F4: the splice step, measured BEFORE any blend
    first = [p for p in res["pairs"] if p[0] >= SPLICE_START][:1]
    if first:
        d, sd_, actual = first[0]
        step = (res["a"] + res["b"] * sd_) - actual
        log("  F4 splice step at %s: reconstructed %.2f vs actual VIX1Y %.2f = %+.2f points"
            % (d, res["a"] + res["b"] * sd_, actual, step))
        if abs(step) > F4_MAX_SPLICE_STEP:
            fired.append("F4: splice step %+.2f VIX points exceeds %.1f" % (step, F4_MAX_SPLICE_STEP))
    return fired


def reconstruct(res):
    """The full history: date, semidev, VIX-equivalent, and which side of the splice it is on."""
    a, b = res["a"], res["b"]
    rows = []
    for d, sd_ in series(res["rdates"], res["rets"]):
        ve = a + b * sd_
        if d < SPLICE_START:
            src, w = "bridge", 1.0
        elif d >= SPLICE_END:
            src, w = "live", 0.0
        else:
            span = (_ord(SPLICE_END) - _ord(SPLICE_START)) or 1
            w = max(0.0, min(1.0, (_ord(SPLICE_END) - _ord(d)) / span))
            src = "blend"
        live = res["vix"].get(d)
        val = ve if live is None else (w * ve + (1.0 - w) * live)
        rows.append(dict(date=d, market_semidev=round(sd_, 6),
                         vix_equiv_bridge=round(ve, 6),
                         vix1y_live=("" if live is None else round(live, 4)),
                         bridge_weight=round(w, 6), source=src,
                         vix_equiv=round(val, 6),
                         martin_erp_pct=round(val * val / 100.0, 6)))
    return rows


def _ord(d):
    import datetime as dt
    return dt.date.fromisoformat(d).toordinal()


def main():
    res = calibrate_and_validate()
    print("\nFALSIFIERS (pre-registered section 5)")
    fired = check_falsifiers(res)
    if fired:
        print("  ** FIRED:")
        for f in fired:
            print("     " + f)
    else:
        print("  none fired.")

    rows = reconstruct(res)
    bad = [r for r in rows if not (F5_VIX_LO <= r["vix_equiv"] <= F5_VIX_HI)
           or r["martin_erp_pct"] < 0]
    print("  F5 impossible levels: %d of %d rows outside [%.0f, %.0f] VIX points"
          % (len(bad), len(rows), F5_VIX_LO, F5_VIX_HI))
    if bad:
        print("     worst: %s" % sorted(bad, key=lambda r: r["vix_equiv"])[-1])

    print("\nRECONSTRUCTION: %d days, %s -> %s" % (len(rows), rows[0]["date"], rows[-1]["date"]))
    for label, d in (("1932-06 depression", "1932-06-01"), ("1937-10", "1937-10-01"),
                     ("1974-10 bear trough", "1974-10-01"), ("1987-12 post-crash", "1987-12-01"),
                     ("2000-03 bubble peak", "2000-03-01"), ("2009-03 GFC trough", "2009-03-02"),
                     ("2020-06 post-COVID", "2020-06-01"), ("2026-08 today", "2026-08-12")):
        m = [r for r in rows if r["date"] <= d]
        if m:
            r = m[-1]
            print("    %-22s semidev %6.2f  VIX-equiv %6.2f  Martin ERP %6.2f%%  [%s]"
                  % (label, r["market_semidev"], r["vix_equiv"], r["martin_erp_pct"], r["source"]))

    if "--write" in sys.argv:
        os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
        with open(OUT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("\nWROTE %s" % OUT)
    return 1 if fired else 0


if __name__ == "__main__":
    raise SystemExit(main())
