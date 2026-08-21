"""
svix_surface.py -- the synthetic surface completion.

Implements docs/AEG-Synthetic-Surface-SPEC-2026-08-12.md sections 2, 3 and 8.
Pure functions, standard library only, no network, no files -- so it can be tested
against closed forms exactly the way svix_core.py is.

MEASUREMENT ONLY. Nothing here reads or writes the sealed workbook.

WHAT PROBLEM THIS SOLVES
------------------------
SVIX^2 is an integral over the whole strike axis, zero to infinity. Real strike
ladders stop. The trapezoidal estimator in svix_core.py integrates only what is
quoted, so it is biased by whatever the ladder does not cover -- and the ladders are
worst for exactly the low-volatility staples the AEG fleet is full of.

The fix is to fit a smooth, arbitrage-respecting curve to the quoted implied
volatilities, then integrate THAT curve from zero to infinity analytically. There is
no truncation point left to be biased by.

WHY BLACK-SCHOLES APPEARS HERE AND WHY IT IS NOT AN ASSUMPTION
--------------------------------------------------------------
Prices are converted to implied volatilities and back again. The conversion is
exactly invertible, so it carries no information and imposes no model: a price maps
to one implied volatility and that implied volatility maps back to the same price.
Black-Scholes is used as a CHANGE OF VARIABLE, in the same way log-moneyness is a
change of variable for the strike. The model content of this module lies entirely in
the SVI functional form assumed for the SMILE, not in Black-Scholes.

COORDINATES
-----------
    k = log(K / F)                 log-moneyness
    w = sigma_BS(K, T)^2 * T       TOTAL implied variance to expiry

Total variance rather than volatility because w is what must be non-decreasing in T
for no calendar arbitrage, and because it makes slices at different expiries directly
comparable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

SQRT2 = math.sqrt(2.0)


# ---------------------------------------------------------------- Black-Scholes

def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def bs_otm_normalized(k, w):
    """
    Price of the OUT-OF-THE-MONEY option at log-moneyness k, in units of D*F.

    k < 0  -> put,  k >= 0 -> call. Returns (price / (D * F)).

    This is the natural unit: it depends only on (k, w), never on the level of the
    forward or the interest rate, which is what makes the surface comparable across
    names and dates.
    """
    if w <= 0:
        return max(math.exp(k) - 1.0, 0.0) if k >= 0 else max(1.0 - math.exp(k), 0.0)
    sw = math.sqrt(w)
    d1 = (-k + 0.5 * w) / sw
    d2 = d1 - sw
    if k >= 0:
        return ncdf(d1) - math.exp(k) * ncdf(d2)          # call
    return math.exp(k) * ncdf(-d2) - ncdf(-d1)            # put


def implied_total_variance(price_over_DF, k, lo=1e-8, hi=25.0, tol=1e-12):
    """
    Invert bs_otm_normalized in w by bisection.

    price_over_DF: OTM option mid divided by (discount * forward).
    Returns total variance w, or None if the price is outside the no-arbitrage range
    (below intrinsic, or above the upper bound the option can be worth).

    Bisection rather than Newton: it cannot diverge, and the function is monotone in
    w, so a hundred halvings gets machine precision. Speed is irrelevant here --
    correctness is not.
    """
    if price_over_DF is None or price_over_DF <= 0:
        return None
    # An out-of-the-money option has NO forward intrinsic value by construction:
    # for k >= 0 the option is a call struck above the forward, for k < 0 a put
    # struck below it. So the only lower bound is zero.
    #
    # The upper bounds are the standard ones, expressed in units of D*F:
    #   call <= forward            -> 1
    #   put  <= strike             -> exp(k)
    upper = 1.0 if k >= 0 else math.exp(k)
    if price_over_DF >= upper:
        return None
    a, b = lo, hi
    fa = bs_otm_normalized(k, a) - price_over_DF
    fb = bs_otm_normalized(k, b) - price_over_DF
    if fa > 0 or fb < 0:
        return None
    for _ in range(200):
        m = 0.5 * (a + b)
        fm = bs_otm_normalized(k, m) - price_over_DF
        if fm < 0:
            a = m
        else:
            b = m
        if b - a < tol:
            break
    return 0.5 * (a + b)


# ------------------------------------------------------------- SVI slice model

@dataclass
class SVI:
    """Gatheral's raw stochastic-volatility-inspired slice.

        w(k) = a + b * ( rho * (k - m) + sqrt( (k - m)^2 + s^2 ) )
    """
    a: float
    b: float
    rho: float
    m: float
    s: float

    def w(self, k):
        x = k - self.m
        return self.a + self.b * (self.rho * x + math.sqrt(x * x + self.s * self.s))

    def wings_ok(self):
        return (self.b > 0 and abs(self.rho) < 1 and self.s > 0
                and self.a + self.b * self.s * math.sqrt(1 - self.rho ** 2) >= -1e-12)

    def as_tuple(self):
        return (self.a, self.b, self.rho, self.m, self.s)


def butterfly_violations(svi, k_lo=-3.0, k_hi=3.0, n=121):
    """
    Gatheral-Jacquier durrleman condition, evaluated on a grid.

        g(k) = (1 - k w'/(2w))^2 - (w'/4)^2 (1/w + 1/4) + w''/2   >= 0

    A negative g means the implied risk-neutral density goes negative somewhere,
    which is a butterfly arbitrage. Returns (n_violations, worst_g). We report rather
    than silently repair: a slice that cannot be fitted arbitrage-free should be
    refused, not fudged.
    """
    h = 1e-4
    worst = float("inf")
    bad = 0
    for i in range(n):
        k = k_lo + (k_hi - k_lo) * i / (n - 1)
        w0 = svi.w(k)
        if w0 <= 0:
            bad += 1
            worst = min(worst, -abs(w0) - 1.0)
            continue
        wp = (svi.w(k + h) - svi.w(k - h)) / (2 * h)
        wpp = (svi.w(k + h) - 2 * w0 + svi.w(k - h)) / (h * h)
        g = ((1 - k * wp / (2 * w0)) ** 2
             - (wp / 4.0) ** 2 * (1.0 / w0 + 0.25)
             + wpp / 2.0)
        if g < 0:
            bad += 1
        worst = min(worst, g)
    return bad, worst


# --------------------------------------------------------- Nelder-Mead (stdlib)

def nelder_mead(f, x0, step=0.1, tol=1e-10, max_iter=1500):
    """
    Derivative-free simplex minimizer. Written out rather than imported so this
    module keeps the same dependency profile as svix_core.py: standard library only,
    runnable anywhere, no version drift in a numerical result.
    """
    n = len(x0)
    pts = [list(x0)]
    for i in range(n):
        p = list(x0)
        p[i] += step if p[i] == 0 else step * abs(p[i])
        pts.append(p)
    vals = [f(p) for p in pts]
    for _ in range(max_iter):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        pts = [pts[i] for i in order]
        vals = [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) <= tol * (abs(vals[0]) + tol):
            break
        cen = [sum(p[i] for p in pts[:-1]) / n for i in range(n)]
        xr = [cen[i] + 1.0 * (cen[i] - pts[-1][i]) for i in range(n)]
        fr = f(xr)
        if fr < vals[0]:
            xe = [cen[i] + 2.0 * (cen[i] - pts[-1][i]) for i in range(n)]
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = [cen[i] + 0.5 * (pts[-1][i] - cen[i]) for i in range(n)]
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]
                    vals[i] = f(pts[i])
    best = min(range(n + 1), key=lambda i: vals[i])
    return pts[best], vals[best]


# ------------------------------------------------------------------ slice fitting

@dataclass
class SliceFit:
    svi: SVI | None
    mode: str                        # full | borrowed_wings | refused
    rmse_w: float
    n_points: int
    k_lo: float
    k_hi: float
    butterfly_bad: int
    butterfly_worst: float
    ok: bool
    reason: str = ""
    notes: list = field(default_factory=list)


def _params_from_free(free, fixed):
    """Map the optimizer's unconstrained vector onto valid SVI parameters.

    Constraints are imposed by construction rather than by penalty, which is what
    stops the optimizer wandering into an arbitrageable region and reporting a good
    fit from it:
        b > 0        via exp
        |rho| < 1    via tanh
        s > 0        via exp
    """
    if fixed is None:
        a, lb, zr, m, ls = free
        return SVI(a, math.exp(lb), math.tanh(zr), m, math.exp(ls))
    b, rho, s = fixed
    a, m = free
    return SVI(a, b, rho, m, s)


def fit_svi_slice(points, weights=None, fixed_wings=None, seed=None):
    """
    Fit an SVI slice to observed (k, w) pairs.

    points: list of (k, w) with w > 0.
    weights: optional list, same length. Use vega-like weights so that near-the-money
             quotes -- which are tight and informative -- count more than deep wings
             quoted a penny wide.
    fixed_wings: (b, rho, s) borrowed from a peer group; then only a and m are fitted.
                 This is the middle row of the spec's section 3 table: keep your own
                 level and position, borrow the wings and the skew.

    Returns a SliceFit.
    """
    pts = [(float(k), float(w)) for k, w in points if w is not None and w > 0]
    if len(pts) < (3 if fixed_wings else 5):
        return SliceFit(None, "refused", float("nan"), len(pts), 0, 0, 0, 0, False,
                        f"only {len(pts)} usable (k, w) points")
    ks = [k for k, _ in pts]
    ws = [w for _, w in pts]
    if weights is None:
        weights = [1.0] * len(pts)
    wsum = sum(weights)
    weights = [x / wsum for x in weights]

    def obj(free):
        try:
            svi = _params_from_free(free, fixed_wings)
        except (OverflowError, ValueError):
            return 1e12
        if not svi.wings_ok():
            return 1e12
        tot = 0.0
        for (k, w), q in zip(pts, weights):
            d = svi.w(k) - w
            tot += q * d * d
        return tot

    atm = min(range(len(pts)), key=lambda i: abs(ks[i]))
    w_atm = ws[atm]
    if fixed_wings is None:
        if seed is None:
            seed = [w_atm * 0.5, math.log(max(w_atm, 1e-6)), -0.5, 0.0,
                    math.log(0.25)]
        best, val = nelder_mead(obj, seed, step=0.25)
        # A second start from a flatter, more symmetric smile, in case the first
        # landed in a local minimum. Cheap insurance; the objective is not convex.
        alt = [w_atm * 0.8, math.log(max(w_atm * 0.5, 1e-6)), 0.0, 0.0, math.log(0.5)]
        best2, val2 = nelder_mead(obj, alt, step=0.25)
        if val2 < val:
            best, val = best2, val2
    else:
        best, val = nelder_mead(obj, [w_atm * 0.5, 0.0], step=0.2)

    svi = _params_from_free(best, fixed_wings)
    if not svi.wings_ok():
        return SliceFit(None, "refused", float("nan"), len(pts), min(ks), max(ks),
                        0, 0, False, "no arbitrage-free parameters found")
    rmse = math.sqrt(max(val, 0.0))
    bad, worst = butterfly_violations(svi, min(ks) - 1.0, max(ks) + 1.0)
    mode = "borrowed_wings" if fixed_wings else "full"
    notes = []
    if bad:
        notes.append(f"butterfly condition violated at {bad} grid points "
                     f"(worst g = {worst:.4g})")
    return SliceFit(svi, mode, rmse, len(pts), min(ks), max(ks), bad, worst, True,
                    "", notes)


# --------------------------------------------- integrating the fitted surface

def svix2_from_svi(svi, k_lo=-9.0, k_hi=9.0, n=1201):
    """
    SVIX^2 implied by a fitted slice, integrated over the WHOLE strike axis.

        SVIX^2 = 2 * [ int_{-inf}^{0} e^k * put~(k) dk
                     + int_{0}^{inf}  e^k * call~(k) dk ]

    where put~ and call~ are the out-of-the-money prices in units of D*F, i.e.
    bs_otm_normalized. This is the same Breeden-Litzenberger integral svix_core
    computes trapezoidally on the observed strikes -- the only difference is that the
    integrand is now available everywhere, so there is no truncation.

    The change of variable is K = F e^k, dK = F e^k dk, which is why the e^k appears.

    Simpson's rule on a fixed grid wide enough that the integrand is numerically zero
    at both ends. With a flat w this must return exp(w) - 1 exactly; the test checks
    that.
    """
    if svi is None:
        return None
    h = (k_hi - k_lo) / (n - 1)
    total = 0.0
    for i in range(n):
        k = k_lo + i * h
        w = svi.w(k)
        if w <= 0:
            v = 0.0
        else:
            v = math.exp(k) * bs_otm_normalized(k, w)
        c = 1.0 if i in (0, n - 1) else (4.0 if i % 2 else 2.0)
        total += c * v
    return 2.0 * total * h / 3.0


def synthetic_variance_share(svi, k_obs_lo, k_obs_hi, k_lo=-9.0, k_hi=9.0,
                             n=1201):
    """
    Fraction of the SVIX^2 integral contributed by strike regions where nothing was
    quoted. This is the disclosure field the spec's section 7 requires, and the thing
    the 0.35 refusal threshold is applied to.
    """
    if svi is None:
        return None
    h = (k_hi - k_lo) / (n - 1)
    tot = 0.0
    out = 0.0
    for i in range(n):
        k = k_lo + i * h
        w = svi.w(k)
        v = math.exp(k) * bs_otm_normalized(k, w) if w > 0 else 0.0
        c = 1.0 if i in (0, n - 1) else (4.0 if i % 2 else 2.0)
        tot += c * v
        if k < k_obs_lo or k > k_obs_hi:
            out += c * v
    return out / tot if tot > 0 else None


# ------------------------------------------------------ the expiry dimension

def calendar_violations(slices, k_grid=None):
    """
    Check the calendar-spread condition: total variance w(k, T) must be non-decreasing
    in T at every k. A violation is a bad slice fit, not a bad market.

    slices: list of (days, SVI), any order.
    Returns list of (k, days_a, days_b, w_a, w_b) for every violation found.
    """
    if k_grid is None:
        k_grid = [-1.5 + 3.0 * i / 60.0 for i in range(61)]
    srt = sorted((d, s) for d, s in slices if s is not None)
    out = []
    for (da, sa), (db, sb) in zip(srt[:-1], srt[1:]):
        for k in k_grid:
            wa, wb = sa.w(k), sb.w(k)
            if wb < wa - 1e-9:
                out.append((k, da, db, wa, wb))
    return out


def interpolate_slice_variance(slices, target_days, k):
    """
    Total variance at (k, target_days), linear in T at fixed k between fitted slices.

    Returns (w, mode) with mode in {interp, extrap_short, extrap_long}. Beyond the
    longest listed expiry this holds the ANNUALIZED variance flat rather than
    extending the line, and labels it extrap_long -- the spec forbids silent
    extrapolation past the last listed expiry.
    """
    srt = sorted((d, s) for d, s in slices if s is not None)
    if not srt:
        return None, None
    if len(srt) == 1:
        d0, s0 = srt[0]
        return s0.w(k) * (target_days / d0), ("extrap_short" if target_days < d0
                                              else "extrap_long")
    if target_days <= srt[0][0]:
        d0, s0 = srt[0]
        return s0.w(k) * (target_days / d0), "extrap_short"
    if target_days >= srt[-1][0]:
        d0, s0 = srt[-1]
        return s0.w(k) * (target_days / d0), "extrap_long"
    for (da, sa), (db, sb) in zip(srt[:-1], srt[1:]):
        if da <= target_days <= db:
            u = (target_days - da) / (db - da)
            return (1 - u) * sa.w(k) + u * sb.w(k), "interp"
    return None, None
