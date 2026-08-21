"""
svix_core.py -- the mathematics of the Layer 1 idiosyncratic premium.

Pure functions, no network, no file input. Everything here is testable against a
closed form, and test_svix_math.py does exactly that.

WHAT THIS COMPUTES
------------------
SVIX squared, in the sense of Martin (2017) and Martin-Wagner (2019):

    SVIX^2_i,t  =  var*_t ( R_i,t+1 / R_f,t+1 )
                =  (2 * R_f / F^2) * [ integral_0^F put(K) dK + integral_F^inf call(K) dK ]

where the integrals run over OUT-OF-THE-MONEY options only (puts below the
forward, calls above it), F is the forward price of the underlying to the option
expiry, and R_f is the gross risk-free return to that same expiry.

This is Breeden-Litzenberger (1978): a portfolio of options spanning the strike
range prices the squared contract, and the risk-neutral variance falls out of it.
It uses option PRICES, not implied volatilities -- no Black-Scholes assumption is
made anywhere in the estimator. Black-Scholes appears only in the TEST, as a case
whose answer is known in closed form.

The idiosyncratic premium is then, per Martin-Wagner:

    pi_i,t  =  0.5 * ( SVIX^2_i,t  -  SVIXbar^2_t )

with SVIXbar^2_t the VALUE-WEIGHTED average of the single-name SVIX^2 across the
universe. The value weighting is not a taste: it is what forces the firm-specific
terms to sum to zero across the market, which is the aggregation constraint the
derivation rests on. See docs/AEG-Idiosyncratic-Premium-Proposal-2026-08-12.md
section 4.

CONVENTIONS
-----------
* Everything is per-expiry and CUMULATIVE over the horizon to that expiry. It is
  not annualized inside this module. Annualization is a presentation choice and is
  done explicitly, once, in annualize().
* The FORWARD is extracted from the option prices themselves by put-call parity, so
  it embeds the market's own dividend expectation and no external dividend forecast
  is needed.

* The DISCOUNT FACTOR is NOT. This corrects a claim made in the first version of
  this module, which asserted that parity supplies both and therefore no rate feed
  is needed at all. That is true of European options and false of the listed
  American options this actually runs on: their deep in-the-money quotes sit near
  immediate-exercise intrinsic value, which drags the parity slope toward minus one
  and the implied rate toward zero. Measured on live Apple quotes at a 492-day
  expiry on 12 August 2026, parity implied 1.4 per cent against a Treasury curve at
  4.2 per cent. Use fit_forwards_given_rate() with a rate curve read LIVE at run
  time. fit_forward_discount() and fit_forward_curve() are kept because the tests
  and the closed-form proofs are built on them, and they remain correct for European
  options -- but they must not be used on a live American chain.

  This is not the "stale curve pasted out of a prose document" failure the project
  warns about: the curve is pulled at run time and the read date is disclosed on
  every row that uses it.
* Nothing here reads or writes the sealed workbook, and nothing here can move a
  published valuation. This module is measurement only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# ----------------------------------------------------------------------------
# 1. Forward and discount factor, extracted from the chain itself
# ----------------------------------------------------------------------------

@dataclass
class ParityFit:
    forward: float
    discount: float          # D = exp(-rT); gross risk-free over horizon is 1/D
    n_strikes: int
    r2: float                # fit quality of the parity regression
    ok: bool
    reason: str = ""


def fit_forward_discount(pairs, atm_band=(0.80, 1.20), spot_hint=None):
    """
    Extract the forward price F and the discount factor D from put-call parity.

    For every strike K where both a call and a put trade,

        C(K) - P(K) = D * (F - K)

    which is linear in K with slope -D and intercept D*F. Ordinary least squares on
    the near-the-money strikes gives both, with no external interest rate and no
    external spot price.

    pairs: iterable of (strike, call_mid, put_mid)
    atm_band: keep strikes within this multiple of the rough at-the-money level.
              Deep in- and out-of-the-money parity pairs are noisy because one leg
              is nearly all intrinsic value and quoted wide.

    Returns a ParityFit. ok=False means do not use this expiry.
    """
    pts = [(float(k), float(c) - float(p)) for k, c, p in pairs
           if k is not None and c is not None and p is not None and k > 0]
    if len(pts) < 4:
        return ParityFit(0.0, 0.0, len(pts), 0.0, False, "fewer than 4 parity pairs")

    # Rough at-the-money level: the strike where |C-P| is smallest is close to F.
    if spot_hint is not None and spot_hint > 0:
        atm = float(spot_hint)
    else:
        atm = min(pts, key=lambda t: abs(t[1]))[0]

    lo, hi = atm * atm_band[0], atm * atm_band[1]
    band = [(k, y) for k, y in pts if lo <= k <= hi]
    if len(band) < 4:
        band = pts  # fall back to the whole set rather than refusing outright

    n = len(band)
    sx = sum(k for k, _ in band)
    sy = sum(y for _, y in band)
    sxx = sum(k * k for k, _ in band)
    sxy = sum(k * y for k, y in band)
    denom = n * sxx - sx * sx
    if denom == 0:
        return ParityFit(0.0, 0.0, n, 0.0, False, "degenerate strike grid")

    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n

    # slope must be negative: it is -D, and 0 < D <= 1 (plus a little slack for
    # quote noise; a discount factor above 1 means a negative rate, which we allow
    # only marginally before refusing).
    discount = -slope
    if not (0.5 < discount < 1.05):
        return ParityFit(0.0, 0.0, n, 0.0, False,
                         f"implied discount factor {discount:.4f} out of bounds")
    forward = intercept / discount
    if not (forward > 0):
        return ParityFit(0.0, 0.0, n, 0.0, False, "non-positive implied forward")

    ybar = sy / n
    ss_tot = sum((y - ybar) ** 2 for _, y in band)
    ss_res = sum((y - (intercept + slope * k)) ** 2 for k, y in band)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

    return ParityFit(forward, discount, n, r2, True)


def fit_forwards_given_rate(expiries, rate_fn, atm_band=0.07, wide_band=0.15):
    """
    Forward price for every expiry with the DISCOUNT FACTOR IMPOSED from an external
    rate, recovering only the forward from the option quotes.

        F = K + (C(K) - P(K)) / D,   averaged over near-the-money strikes

    WHY THE DISCOUNT FACTOR IS NOT FITTED HERE
    ------------------------------------------
    Listed single-stock options in the United States are AMERICAN. Their deep
    in-the-money quotes sit at or near immediate-exercise intrinsic value, not at the
    discounted forward value a European option would carry, which drags the slope of
    C - P against strike toward minus one and so drags the implied discount factor
    toward one. On Apple's 492-day expiry on 12 August 2026 the parity regression
    implies a 1.4 per cent rate against a Treasury curve near 4.2 per cent and a
    forward-to-spot carry that independently says 4.2 per cent. The regression is not
    noisy there, it is biased, and it is biased worse the longer the expiry.

    Since SVIX^2 = 2 * integral / (D * F^2), an error in D passes straight into the
    answer -- roughly three to four per cent of SVIX^2 at a 500-day expiry, which is
    of the same order as the whole premium being measured. So the discount factor is
    imposed from a live rate curve read at run time, and the fact is disclosed on
    every row.

    The forward IS still taken from the options, because it embeds the market's own
    dividend expectation, which no rate curve knows. Near-the-money strikes are used
    because that is where the early-exercise distortion is smallest.

    expiries: list of (days, pairs), pairs = [(strike, call_mid, put_mid), ...]
    rate_fn:  days -> continuously compounded rate as a decimal
    Returns {days: ParityFit}.
    """
    out = {}
    for days, pairs in expiries:
        pts = [(float(k), float(c) - float(p)) for k, c, p in pairs
               if k is not None and c is not None and p is not None and k > 0]
        if len(pts) < 3 or rate_fn is None:
            out[days] = ParityFit(0.0, 0.0, len(pts), 0.0, False,
                                  "too few parity pairs or no rate curve")
            continue
        T = days / 365.0
        disc = math.exp(-rate_fn(days) * T)
        atm = min(pts, key=lambda t: abs(t[1]))[0]
        band = [(k, y) for k, y in pts if abs(k / atm - 1.0) <= atm_band]
        if len(band) < 3:
            band = [(k, y) for k, y in pts if abs(k / atm - 1.0) <= wide_band]
        if len(band) < 3:
            band = pts
        fwds = [k + y / disc for k, y in band]
        fwd = sum(fwds) / len(fwds)
        if not fwd > 0:
            out[days] = ParityFit(0.0, 0.0, len(band), 0.0, False,
                                  "non-positive implied forward")
            continue
        spread = (max(fwds) - min(fwds)) / fwd
        out[days] = ParityFit(
            fwd, disc, len(band), max(0.0, 1.0 - spread), True,
            f"discount imposed from live rate curve "
            f"({100 * rate_fn(days):.3f}% continuous); forward from "
            f"{len(band)} near-the-money strikes, spread {100 * spread:.2f}%")
    return out


def fit_forward_curve(expiries, min_days_for_rate=90, min_r2=0.995,
                      atm_band=0.07, wide_band=0.15):
    """
    Forward and discount factor for EVERY expiry of one underlying on one date,
    using the whole chain jointly.

    WHY THE SINGLE-EXPIRY FIT IS NOT ENOUGH
    ---------------------------------------
    fit_forward_discount() estimates the discount factor from the SLOPE of C - P
    against strike. At long horizons that slope is well identified. At short ones it
    is not, and the failure is not subtle. Live PepsiCo quotes on 12 August 2026, 23
    days to expiry, imply a slope of -1.06 -- a discount factor above one, which is
    impossible for a European option and simply reflects the bid-ask spreads. Over 23
    days the true discount factor differs from one by about a quarter of a percent,
    while the midpoints carry several percent of noise, so there is nothing to fit.

    The fix keeps the promise that no external rate curve is used: the rate still
    comes from the option prices, just from the expiries where it is identifiable.

      Pass 1  ordinary parity regression on every expiry.
      Pass 2  keep the long, well-fitting ones; convert each to a continuously
              compounded rate, and interpolate that rate across all expiries
              (flat outside the fitted range).
      Pass 3  with the discount factor imposed, recover the forward from parity
              directly, F = K + (C - P) / D, averaged over near-the-money strikes.

    expiries: list of (days, pairs) with pairs = [(strike, call_mid, put_mid), ...]
    Returns {days: ParityFit}. `reason` records which pass produced each one.
    """
    first = {}
    for days, pairs in expiries:
        first[days] = fit_forward_discount(pairs)

    anchors = []
    for days, fit in first.items():
        if fit.ok and days >= min_days_for_rate and fit.r2 >= min_r2 and fit.discount < 1.0:
            T = days / 365.0
            anchors.append((days, -math.log(fit.discount) / T))
    anchors.sort()

    def rate_at(days):
        if not anchors:
            return None
        if len(anchors) == 1 or days <= anchors[0][0]:
            return anchors[0][1]
        if days >= anchors[-1][0]:
            return anchors[-1][1]
        for (da, ra), (db, rb) in zip(anchors[:-1], anchors[1:]):
            if da <= days <= db:
                u = (days - da) / (db - da)
                return ra + u * (rb - ra)
        return anchors[-1][1]

    out = {}
    for days, pairs in expiries:
        pts = [(float(k), float(c) - float(p)) for k, c, p in pairs
               if k is not None and c is not None and p is not None and k > 0]
        r = rate_at(days)
        if r is None or len(pts) < 4:
            out[days] = first[days]
            if out[days].ok:
                out[days].reason = "single-expiry parity fit (no rate anchor available)"
            continue
        T = days / 365.0
        disc = math.exp(-r * T)
        atm = min(pts, key=lambda t: abs(t[1]))[0]
        band = [(k, y) for k, y in pts if abs(k / atm - 1.0) <= atm_band]
        if len(band) < 3:
            band = [(k, y) for k, y in pts if abs(k / atm - 1.0) <= wide_band]
        if len(band) < 3:
            band = pts
        fwds = [k + y / disc for k, y in band]
        fwd = sum(fwds) / len(fwds)
        spread = (max(fwds) - min(fwds)) / fwd if fwd else 1.0
        # r2 here is the agreement AMONG the strike-by-strike forward estimates,
        # which is the quantity that actually matters downstream. It is not the
        # regression r2 of pass 1 and is labelled so in `reason`.
        out[days] = ParityFit(fwd, disc, len(band), max(0.0, 1.0 - spread), fwd > 0,
                              f"rate {100 * r:.3f}% imposed from long-expiry anchors; "
                              f"forward averaged over {len(band)} near-the-money "
                              f"strikes, spread {100 * spread:.2f}%")
    return out


# ----------------------------------------------------------------------------
# 2. The out-of-the-money strip and its integral
# ----------------------------------------------------------------------------

@dataclass
class SvixResult:
    svix2: float                 # var*(R_i/R_f) over the horizon, cumulative
    forward: float
    discount: float
    n_strikes: int
    k_min: float
    k_max: float
    lower_tail_share: float      # share of the integral from 0 to the lowest strike
    upper_tail_flag: float       # call price at the highest strike, scaled -- a
                                 # truncation warning, not a correction
    ok: bool
    reason: str = ""
    notes: list = field(default_factory=list)


def svix2_from_strip(strikes_puts, strikes_calls, forward, discount,
                     min_strikes=8):
    """
    Integrate the out-of-the-money option strip into SVIX^2.

        SVIX^2 = (2 / (D * F^2)) * [ int_0^F put(K) dK + int_F^inf call(K) dK ]

    (using R_f = 1/D).

    strikes_puts:  sorted list of (K, put_price)  -- used for K < F
    strikes_calls: sorted list of (K, call_price) -- used for K >= F

    Integration is trapezoidal on the observed strike grid. Two boundary
    treatments, both deliberate:

    * LOWER TAIL. Put prices go to zero as K goes to zero, so we close the
      integral with a trapezoid from (0, 0) to the lowest observed strike. This is
      an interpolation, not an extrapolation, and it is essentially exact because
      deep puts are worth almost nothing. Its share of the total is reported so it
      can be checked rather than trusted.

    * UPPER TAIL. Call prices go to zero as K goes to infinity, but we cannot
      observe where. We TRUNCATE at the highest observed strike and report the
      call price there. We do NOT extrapolate. Truncation biases SVIX^2 DOWNWARD,
      and since the premium is a difference against a value-weighted average that
      is truncated the same way, most of that bias differences out -- but a name
      with an unusually thin strike ladder will still read low, so the flag exists
      to catch it.

    The value at exactly K = F is taken as the average of the nearest put above and
    call below, which is the parity-consistent choice: at K = F a put and a call are
    worth the same.
    """
    puts = sorted([(float(k), float(v)) for k, v in strikes_puts
                   if k is not None and v is not None and k > 0 and v >= 0 and k < forward])
    calls = sorted([(float(k), float(v)) for k, v in strikes_calls
                    if k is not None and v is not None and k > 0 and v >= 0 and k >= forward])

    n = len(puts) + len(calls)
    if n < min_strikes or not puts or not calls:
        return SvixResult(0, forward, discount, n, 0, 0, 0, 0, False,
                          f"only {n} usable out-of-the-money strikes "
                          f"({len(puts)} puts, {len(calls)} calls)")

    notes = []

    # Value at the forward: parity says put(F) == call(F). Interpolate from the two
    # nearest observations, one on each side.
    k_lo, v_lo = puts[-1]
    k_hi, v_hi = calls[0]
    if k_hi > k_lo:
        w = (forward - k_lo) / (k_hi - k_lo)
        v_fwd = v_lo + w * (v_hi - v_lo)
    else:
        v_fwd = 0.5 * (v_lo + v_hi)
    v_fwd = max(v_fwd, 0.0)

    def trapz(points):
        total = 0.0
        for (ka, va), (kb, vb) in zip(points[:-1], points[1:]):
            total += 0.5 * (va + vb) * (kb - ka)
        return total

    # Lower branch: (0,0) -> observed puts -> (F, v_fwd)
    lower_pts = [(0.0, 0.0)] + puts + [(forward, v_fwd)]
    lower = trapz(lower_pts)
    lower_stub = 0.5 * (0.0 + puts[0][1]) * (puts[0][0] - 0.0)

    # Upper branch: (F, v_fwd) -> observed calls -> truncate at the last strike
    upper_pts = [(forward, v_fwd)] + calls
    upper = trapz(upper_pts)

    integral = lower + upper
    if integral <= 0:
        return SvixResult(0, forward, discount, n, puts[0][0], calls[-1][0], 0, 0,
                          False, "non-positive strip integral")

    svix2 = 2.0 * integral / (discount * forward * forward)

    lower_tail_share = lower_stub / integral if integral > 0 else 0.0
    # Truncation flag: what the last observed call is worth, expressed in the same
    # units as the integrand, relative to the whole integral. Large means the strip
    # was cut off while the calls still had real value.
    k_last, v_last = calls[-1]
    upper_flag = (v_last * k_last) / integral if integral > 0 else 0.0

    if lower_tail_share > 0.05:
        notes.append(f"lower-tail closure is {lower_tail_share:.1%} of the integral")
    if upper_flag > 0.05:
        notes.append(f"strip truncated with the top call still worth {v_last:.4f} "
                     f"at strike {k_last:.2f}; SVIX^2 biased low")

    return SvixResult(svix2, forward, discount, n, puts[0][0], calls[-1][0],
                      lower_tail_share, upper_flag, True, "", notes)


# ----------------------------------------------------------------------------
# 3. Term-structure interpolation and annualization
# ----------------------------------------------------------------------------

def interpolate_variance(observations, target_days):
    """
    Interpolate cumulative SVIX^2 to a target horizon.

    observations: list of (days_to_expiry, svix2_cumulative), days > 0
    Interpolation is LINEAR IN TOTAL VARIANCE against calendar days, which is the
    standard convention (it is what the VIX methodology does between the two
    bracketing expiries) and is exact under any model with independent increments.

    Returns (value, mode) where mode is one of "interp", "extrap_short",
    "extrap_long", or None if it cannot be done. Extrapolation is FLAGGED, never
    silent: beyond the longest listed expiry it holds the annualized rate flat
    rather than extending the line, because extending a variance line past the last
    traded expiry is exactly the kind of quietly-wrong number this project keeps
    getting bitten by.
    """
    obs = sorted([(float(d), float(v)) for d, v in observations if d and d > 0 and v is not None])
    if not obs:
        return None, None
    if len(obs) == 1:
        d0, v0 = obs[0]
        return v0 * (target_days / d0), "extrap_short" if target_days < d0 else "extrap_long"

    if target_days <= obs[0][0]:
        d0, v0 = obs[0]
        return v0 * (target_days / d0), "extrap_short"
    if target_days >= obs[-1][0]:
        d0, v0 = obs[-1]
        # hold the per-day variance rate flat past the last expiry
        return v0 * (target_days / d0), "extrap_long"

    for (da, va), (db, vb) in zip(obs[:-1], obs[1:]):
        if da <= target_days <= db:
            w = (target_days - da) / (db - da)
            return va + w * (vb - va), "interp"
    return None, None


def annualize(cumulative_premium, days):
    """
    Turn a cumulative expected excess return over `days` into a per-annum rate.

    Martin-Wagner's formula delivers E[R_i - R_f]/R_f OVER THE HORIZON. A discount
    rate path wants a per-annum number, so compound it down:

        annual = (1 + cumulative)^(365/days) - 1
    """
    if days is None or days <= 0:
        return None
    return (1.0 + cumulative_premium) ** (365.0 / days) - 1.0


# ----------------------------------------------------------------------------
# 4. The cross-section: the actual Martin-Wagner premium
# ----------------------------------------------------------------------------

def cross_section_premium(svix2_by_name, weights_by_name, coefficient=0.5):
    """
    pi_i = coefficient * ( SVIX^2_i - SVIXbar^2 ),  SVIXbar^2 = sum_j w_j SVIX^2_j

    Returns (premiums_by_name, svixbar2, diagnostics).

    THE INVARIANT: the value-weighted mean of pi_i across the universe is zero by
    construction. diagnostics["vw_mean_premium"] must come out at machine zero. If
    it does not, the weights and the variances have gone out of alignment and the
    whole cross-section is untrustworthy. This is the checkable identity that
    section 7 of the proposal asks for, and the caller must assert on it.
    """
    names = [n for n in svix2_by_name if n in weights_by_name
             and svix2_by_name[n] is not None and weights_by_name[n] is not None
             and weights_by_name[n] > 0]
    if not names:
        return {}, None, {"n": 0, "reason": "no names with both a variance and a weight"}

    wsum = sum(weights_by_name[n] for n in names)
    w = {n: weights_by_name[n] / wsum for n in names}
    svixbar2 = sum(w[n] * svix2_by_name[n] for n in names)

    premiums = {n: coefficient * (svix2_by_name[n] - svixbar2) for n in names}
    vw_mean = sum(w[n] * premiums[n] for n in names)

    # The median-benchmarked variant, published alongside as a disclosed
    # alternative (proposal section 4). It is NOT the default: swapping the
    # benchmark shifts every firm by the same constant and breaks the identity
    # above.
    srt = sorted(svix2_by_name[n] for n in names)
    m = len(srt)
    median_svix2 = srt[m // 2] if m % 2 else 0.5 * (srt[m // 2 - 1] + srt[m // 2])
    premiums_median_bench = {n: coefficient * (svix2_by_name[n] - median_svix2)
                             for n in names}

    diagnostics = {
        "n": len(names),
        "svixbar2_value_weighted": svixbar2,
        "svix2_median": median_svix2,
        "vw_mean_premium": vw_mean,
        "median_minus_vw_benchmark": median_svix2 - svixbar2,
        "premiums_median_benchmark": premiums_median_bench,
    }
    return premiums, svixbar2, diagnostics
