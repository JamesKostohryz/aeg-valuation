"""
svix_slices.py -- turn one day's raw option chain into clean per-expiry slices.

Shared by svix_layer1.py (the fleet run) and svix_validate.py (the validation
harness), so that both see exactly the same quote screens, the same forward, the same
discount factor and the same (k, w) points. Two code paths computing "the same"
number slightly differently is how a valuation engine ends up internally consistent
and externally wrong, and this project has been bitten by that six times.

MEASUREMENT ONLY.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from svix_core import fit_forwards_given_rate, svix2_from_strip
from svix_surface import implied_total_variance

# A quote below this fraction of the forward carries no information: the price is
# smaller than the smallest tick anyone can trade, and inverting it to an implied
# volatility amplifies rounding into nonsense. Applied consistently to live quotes
# and to the synthetic ladders in the tests.
MIN_QUOTE_FRACTION = 1e-5


@dataclass
class Slice:
    ticker: str
    date: str
    exp_date: str
    days: int
    forward: float
    discount: float
    otm_puts: list                   # [(K, price)] strictly below the forward
    otm_calls: list                  # [(K, price)] at or above the forward
    kw: list                         # [(k, w)] invertible quotes, log-moneyness
    n_listed: int                    # contracts the exchange listed
    n_quoted: int                    # contracts with a usable two-sided quote
    n_usable: int                    # out-of-the-money strikes that survived screens
    k_lo: float
    k_hi: float
    parity_agreement: float
    svix2_trapezoid: float | None
    notes: list = field(default_factory=list)
    # populated by svix_layer1's checkpoint: the full-freedom SVI fit
    full: dict | None = None

    @property
    def span_lo(self):
        return math.exp(self.k_lo)

    @property
    def span_hi(self):
        return math.exp(self.k_hi)

    def is_dense(self, min_strikes=50, lo=0.4, hi=1.7):
        """The spec's section 6 definition of a slice dense enough to be a truth
        case: at least 50 usable strikes spanning [0.4F, 1.7F]."""
        return (self.n_usable >= min_strikes
                and self.span_lo <= lo and self.span_hi >= hi)


def usable_mid(row, max_rel_spread=1.2):
    """
    Bid-ask midpoint with the quote-quality screens, or None.

    Midpoints rather than last-trade prices, because a stale last trade on an
    illiquid strike is exactly the kind of silently-wrong number that passes every
    gate. Untraded contracts are kept: the vendor supplies a real end-of-day bid and
    ask for them, and the whole reason the first pilot was biased is that they were
    thrown away.
    """
    bid, ask = row.get("bid"), row.get("ask")
    if bid is None or ask is None:
        return None
    try:
        bid, ask = float(bid), float(ask)
    except (TypeError, ValueError):
        return None
    if ask <= 0 or ask < bid:
        return None
    if bid <= 0:
        # A zero bid means nobody will pay anything. Keep it as a genuine near-zero
        # only when the ask is also tiny; otherwise the midpoint is meaningless.
        return 0.5 * ask if ask <= 0.10 else None
    if (ask - bid) / (0.5 * (ask + bid)) > max_rel_spread:
        return None
    return 0.5 * (bid + ask)


def group_chain(rows, trade_date, min_days=7):
    """Group raw chain rows into {exp_date: {'call': {K: mid}, 'put': {K: mid},
    'listed': n}}."""
    td = dt.date.fromisoformat(trade_date)
    by_exp = {}
    for r in rows:
        exp = r.get("exp_date")
        k = r.get("strike")
        typ = (r.get("type") or "").lower()
        if not exp or k is None or typ not in ("call", "put"):
            continue
        if (dt.date.fromisoformat(exp) - td).days < min_days:
            continue
        d = by_exp.setdefault(exp, {"call": {}, "put": {}, "listed": 0})
        d["listed"] += 1
        mid = usable_mid(r)
        if mid is not None:
            d[typ][float(k)] = mid
    return by_exp


def build_slices(ticker, trade_date, rows, rate_fn, min_strikes=8):
    """
    Full pipeline for one (ticker, date): raw chain -> list of Slice.

    The forward comes from put-call parity near the money; the discount factor is
    imposed from `rate_fn`, a live rate curve. See fit_forwards_given_rate() for why
    the discount factor cannot be fitted from American option quotes.
    """
    td = dt.date.fromisoformat(trade_date)
    by_exp = group_chain(rows, trade_date)

    pairs_by_days, meta = [], {}
    for exp, d in sorted(by_exp.items()):
        days = (dt.date.fromisoformat(exp) - td).days
        both = sorted(set(d["call"]) & set(d["put"]))
        if len(both) < 3:
            continue
        pairs_by_days.append((days, [(k, d["call"][k], d["put"][k]) for k in both]))
        meta[days] = (exp, d)

    fits = fit_forwards_given_rate(pairs_by_days, rate_fn)

    out = []
    for days, _ in pairs_by_days:
        fit = fits.get(days)
        if fit is None or not fit.ok:
            continue
        exp, d = meta[days]
        F, disc = fit.forward, fit.discount
        floor = MIN_QUOTE_FRACTION * F

        puts = sorted((k, v) for k, v in d["put"].items() if k < F and v >= floor)
        calls = sorted((k, v) for k, v in d["call"].items() if k >= F and v >= floor)

        kw = []
        for K, px in puts + calls:
            k = math.log(K / F)
            w = implied_total_variance(px / (disc * F), k)
            if w is not None and w > 0:
                kw.append((k, w))
        kw.sort()

        res = svix2_from_strip(puts, calls, F, disc, min_strikes=min_strikes)
        n_usable = len(puts) + len(calls)
        if n_usable == 0:
            continue
        ks = [math.log(k / F) for k, _ in puts + calls]

        out.append(Slice(
            ticker=ticker, date=trade_date, exp_date=exp, days=days,
            forward=F, discount=disc, otm_puts=puts, otm_calls=calls, kw=kw,
            n_listed=d["listed"],
            n_quoted=len(d["call"]) + len(d["put"]),
            n_usable=n_usable, k_lo=min(ks), k_hi=max(ks),
            parity_agreement=fit.r2,
            svix2_trapezoid=res.svix2 if res.ok else None,
            notes=list(res.notes) + ([res.reason] if not res.ok else []),
        ))
    return out


# ------------------------------------------------------------------- thinning

def thin_slice(sl, target_n, target_lo, target_hi, seed=0):
    """
    Discard strikes from a dense slice until its coverage matches a thin name's.

    Spec section 6 step 3: "Do this by discarding strikes, not by simulating." So no
    prices are invented and no distribution is assumed -- the thinned ladder is a
    strict subset of quotes that really traded on that day.

    target_lo, target_hi are multiples of the forward. target_n is the number of
    out-of-the-money strikes to keep. Strikes are kept evenly in LOG-moneyness,
    because that is how real ladders thin out: dense near the money, sparse in the
    wings.

    Returns a new Slice, or None if the dense slice does not cover the target span.
    """
    k_lo, k_hi = math.log(target_lo), math.log(target_hi)
    if sl.k_lo > k_lo + 1e-9 or sl.k_hi < k_hi - 1e-9:
        return None

    inside = [(k, K, v, typ)
              for typ, arr in (("put", sl.otm_puts), ("call", sl.otm_calls))
              for K, v in arr
              for k in [math.log(K / sl.forward)]
              if k_lo - 1e-9 <= k <= k_hi + 1e-9]
    if len(inside) < target_n:
        return None
    inside.sort()

    # Pick target_n positions evenly spaced in k, then snap each to the nearest
    # available strike, without repeats.
    wanted = [k_lo + (k_hi - k_lo) * i / (target_n - 1) for i in range(target_n)]
    chosen, used = [], set()
    for wk in wanted:
        best, bi = None, None
        for i, (k, K, v, typ) in enumerate(inside):
            if i in used:
                continue
            dd = abs(k - wk)
            if best is None or dd < best:
                best, bi = dd, i
        if bi is not None:
            used.add(bi)
            chosen.append(inside[bi])
    chosen.sort()

    puts = sorted((K, v) for k, K, v, typ in chosen if typ == "put")
    calls = sorted((K, v) for k, K, v, typ in chosen if typ == "call")
    if not puts or not calls:
        return None

    kw = []
    for K, px in puts + calls:
        k = math.log(K / sl.forward)
        w = implied_total_variance(px / (sl.discount * sl.forward), k)
        if w is not None and w > 0:
            kw.append((k, w))
    kw.sort()

    res = svix2_from_strip(puts, calls, sl.forward, sl.discount, min_strikes=6)
    ks = [k for k, _, _, _ in chosen]
    return Slice(
        ticker=sl.ticker, date=sl.date, exp_date=sl.exp_date, days=sl.days,
        forward=sl.forward, discount=sl.discount, otm_puts=puts, otm_calls=calls,
        kw=kw, n_listed=sl.n_listed, n_quoted=sl.n_quoted,
        n_usable=len(puts) + len(calls), k_lo=min(ks), k_hi=max(ks),
        parity_agreement=sl.parity_agreement,
        svix2_trapezoid=res.svix2 if res.ok else None,
        notes=[f"thinned from {sl.n_usable} strikes spanning "
               f"[{sl.span_lo:.2f}F, {sl.span_hi:.2f}F]"],
    )


def vega_weights(kw):
    """
    Weights for the SVI fit, proportional to Black-Scholes vega in (k, w) space.

    Near-the-money quotes are tight and carry real information about the level; deep
    wing quotes are a penny wide and carry almost none. Weighting by vega is the
    standard way to stop the fit being dragged around by the least informative
    points. Vega in total-variance units is d(price)/d(w), which is
    phi(d2) / (2 sqrt(w)) in units of D*F -- up to constants, exp(-d2^2/2)/sqrt(w).
    """
    out = []
    for k, w in kw:
        if w <= 0:
            out.append(0.0)
            continue
        sw = math.sqrt(w)
        d2 = (-k - 0.5 * w) / sw
        out.append(math.exp(-0.5 * d2 * d2) / sw)
    s = sum(out)
    return [x / s for x in out] if s > 0 else [1.0 / len(out)] * len(out)
