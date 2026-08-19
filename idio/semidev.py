"""
idio/semidev.py — THE risk statistic behind the company premium, and nothing else.

    semidev_i(asof) = 0.5 x resid_semidev(i, 1y, asof) + 0.5 x resid_semidev(i, 2y, asof)

where resid_semidev is the downside semi-deviation, about its own mean, of the residual from a
market-model regression of the stock's daily log returns on the market's, measured on a trailing
window ending `LAG` trading days before `asof`.

WHY THIS FILE EXISTS. Until now this statistic lived in `AEG-Project/tools/relative_semidev.py`
— a working folder that is not a repository, alongside roughly ninety one-shot measurement
scripts. The company premium that comes out of it was frozen at whatever the run of 2026-08-17
produced, because nothing recomputed it and nothing could: the code was not anywhere a scheduled
job could reach. This is that code, moved somewhere it can run, with the incidental research
apparatus left behind.

IT IS A PORT, NOT A REWRITE, AND THAT IS CHECKED RATHER THAN ASSERTED. `tests/test_semidev.py`
recomputes ten names from a committed price fixture and requires them to match the 2026-08-17
scored file to 1e-3. Verified across the FULL 228-name universe before the port: median absolute
error 2.3e-5, worst 5.0e-5, which is the rounding in the scored file's own four-decimal column.

THREE DETAILS THAT LOOK LIKE STYLE AND ARE NOT:

  * THE MARKET PROXY IS SPY, NOT ^GSPC. A total-return proxy on the same adjusted-close basis as
    the stock series. Using the price index against total-return stock series would put a
    dividend yield into every residual. `idio_stability_T6_production.py` used GSPC for a
    stability TEST, where a common factor cancels; the production statistic uses SPY. Verified:
    SPY reproduces the scored file to 1e-5, and the GSPC cache does not exist at all.

  * THE 60-TRADING-DAY LAG IS DELIBERATE. The window ends sixty trading days before the as-of
    date, so the premium charged today is not a function of the last three months of price
    action. Note `s[:-0]` is the empty list, not the whole series — hence the explicit `if lag`.

  * `clean_series` TRUNCATES AT THE LAST ADJUSTMENT DISCONTINUITY. Vendor `adjusted_close` is
    corrupt on a handful of long histories: Constellation Brands posts a single-day -100% return
    in March 1992, Schlumberger has five such breaks. Left in, they produced a full-history
    semi-deviation of 201% for a company that has compounded positively for forty years. Any
    |one-day log return| above 0.9 is treated as a back-adjustment failure and everything before
    it is dropped.
"""
from __future__ import annotations

import math

TRADING_DAYS = 252.0
LAG_TRADING_DAYS = 60
ADJUSTMENT_BREAK = 0.9      # |one-day log return| above this is an adjustment artefact
MARKET = "SPY"

BLEND_WINDOWS = (1, 2)
BLEND_WEIGHTS = (0.5, 0.5)

MIN_PAIRED_OBS = 50
WINDOW_COVERAGE = 0.9       # a window shorter than 90% of what was asked for is refused


def clean_series(series, threshold=ADJUSTMENT_BREAK):
    """Truncate [(date, px)] at the LAST split/adjustment discontinuity. See the header."""
    if not series:
        return [], 0, None
    last_break = None
    for i in range(1, len(series)):
        a, b = series[i - 1][1], series[i][1]
        if a > 0 and b > 0 and abs(math.log(b / a)) > threshold:
            last_break = i
    if last_break is None:
        return series, 0, None
    return series[last_break:], last_break, series[last_break][0]


def aligned_returns(stock, market, years, asof=None, lag=LAG_TRADING_DAYS):
    """Paired daily log returns over the trailing `years`, as of `asof`, on the standing lag.

    Alignment is on DATE, and the window length is ENFORCED — a series shorter than the window
    asked for is refused rather than silently returned whole, which is how a two-year statistic
    quietly becomes a six-month one for a recent listing."""
    if not stock or not market:
        return None, None
    s, m = stock, market
    if asof is not None:
        s = [x for x in s if x[0] <= asof]
        m = [x for x in m if x[0] <= asof]
    s, _, _ = clean_series(s)
    m, _, _ = clean_series(m)
    if not s or not m or len(s) <= lag or len(m) <= lag:
        return None, None
    if lag:                     # s[:-0] is the EMPTY list, not the whole series
        s = s[:-lag]
        m = m[:-lag]
    mdict = dict(m)
    pairs = [(d, p, mdict[d]) for d, p in s if d in mdict]
    if not pairs:
        return None, None
    n = int(round(years * TRADING_DAYS))
    if len(pairs) < int(round(n * WINDOW_COVERAGE)):
        return None, None
    pairs = pairs[-n:] if len(pairs) > n else pairs
    rs, rm = [], []
    for i in range(1, len(pairs)):
        a, b = pairs[i - 1], pairs[i]
        if a[1] > 0 and b[1] > 0 and a[2] > 0 and b[2] > 0:
            rs.append(math.log(b[1] / a[1]))
            rm.append(math.log(b[2] / a[2]))
    if len(rs) < MIN_PAIRED_OBS:
        return None, None
    return rs, rm


def _semidev_about(rets, centre=0.0):
    """Downside semi-deviation about `centre`. Denominator is the FULL sample count, not the
    count of downside observations — halving the denominator would make a name that rarely falls
    look riskier than one that falls constantly."""
    if not rets:
        return None
    lo = [r - centre for r in rets if r < centre]
    if not lo:
        return 0.0
    return math.sqrt(sum(x * x for x in lo) / len(rets)) * math.sqrt(TRADING_DAYS)


def _ols_beta(y, x):
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    if sxx <= 0:
        return None
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / sxx


def resid_semidev(stock, market, years, asof=None):
    """Downside semi-deviation of the MARKET-MODEL RESIDUAL, in per cent. None on short history.

    The residual, not the raw return: stripping the common market factor is what makes this an
    idiosyncratic measure rather than a restatement of market beta."""
    rs, rm = aligned_returns(stock, market, years, asof)
    if rs is None:
        return None
    beta = _ols_beta(rs, rm)
    if beta is None:
        return None
    resid = [rs[i] - beta * rm[i] for i in range(len(rs))]
    sd = _semidev_about(resid, sum(resid) / len(resid))
    return None if sd is None else sd * 100.0


def blended_semidev(stock, market, asof=None):
    """THE production statistic. None if ANY window is unavailable — a one-year-only figure is a
    different statistic wearing the same name, and substituting it silently is the failure this
    project keeps having."""
    total = 0.0
    for years, weight in zip(BLEND_WINDOWS, BLEND_WEIGHTS):
        v = resid_semidev(stock, market, years, asof)
        if v is None:
            return None
        total += weight * v
    return total
