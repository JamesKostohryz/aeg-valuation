"""
normalization_engine.py  —  unified earnings-normalization tool (v2)
====================================================================
One engine, three modes, two regimes. Works for an index (long history +
present forecast) and for a single stock (mainly the present forecast).

Concept
-------
Mid-cycle "normal" earnings lie on a NORMAL LINE growing at a constant real
rate g = b_norm * rho  (retention x normalized RORE; set rho = COE for the
value-neutral default). Any single on-trend anchor pins today's normal point;
we build it from anchors on one or both sides and reconcile.

The SAME primitive handles both directions: an anchor at offset k (months)
from the target is walked to the target by  E_anchor * exp(C[target]-C[anchor]),
where C is the cumulative log normal-growth. Past anchors (k<0) get GROWN
forward; future anchors (k>0) get DISCOUNTED back — automatically, by the sign
of the cumulative-growth difference.

Two regimes
-----------
#1 BACK-CAST (a time series), run in REAL-TIME MODE: stand at a past month t
   as an investor then would. Walk-back / two-sided are admissible ONLY where
   contemporaneous forecast data existed (`forecast_available[t] == True`);
   elsewhere the tool falls back to forward-only, since that is all a real
   investor there could have used. (Pure-hindsight back-cast is available by
   setting forecast_available=all-True, but that is NOT the default use.)

#2 FORECAST (a single 1-yr-forward point): stand at the present. Past anchors
   are realized EPS; the future anchor is analyst CONSENSUS (tested for
   normality). Produce the forward normalized eps1.

Three modes (identical in both regimes)
---------------------------------------
A forward   : median of X past-anchor walks (backward-looking; always valid).
B backward  : median of X future-anchor walks (forward-looking; needs future data).
C two_sided : combine both sides. Two flavors:
    'pooled'    -> one median over all past+future anchor walks (robust, centered).
    'reconcile' -> compute forward & backward medians separately, take the gap,
                   diagnose it (capital drawdown vs slope error), then select
                   the backward walk when a future anchor exists (else forward).
                   This flavor also carries the explicit capital charge.

Dependency: numpy only.
"""
from __future__ import annotations
import numpy as np


# --------------------------------------------------------------------------
# core: cumulative normal-growth
# --------------------------------------------------------------------------
def _cum_log_growth(b, r, retention_normalize=False, X_retention=4):
    """C[t] = sum_{k<=t} ln(1 + b_k r_k / 12).  Optionally normalize retention
    to a trailing X-anchor median before forming the growth factor."""
    b = np.asarray(b, float).copy()
    r = np.asarray(r, float)
    n = len(b)
    if retention_normalize:
        bn = np.full(n, np.nan)
        for t in range(n):
            anch = [b[t - 12 * a] for a in range(1, X_retention + 1)
                    if t - 12 * a >= 0 and np.isfinite(b[t - 12 * a])]
            if len(anch) >= 1:
                bn[t] = np.median(anch)
        b = bn
    mf = 1.0 + b * r / 12.0
    mf = np.where(np.isfinite(mf), mf, 1.0)
    return np.nancumsum(np.log(mf))


# --------------------------------------------------------------------------
# regime #1 — back-cast time series
# --------------------------------------------------------------------------
def normalize_series(
    E, b, r, X=4, mode="forward",
    forecast_available=None,          # bool mask; where False -> forced forward
    join_flavor="pooled",             # 'pooled' | 'reconcile'
    retention_normalize=False, X_retention=4,
    rho_cap=None,                     # for reconcile capital diagnosis (defaults to r)
    min_anchors=None,
):
    """
    Median-of-X walk normalization as a monthly time series.

    mode: 'forward' | 'backward' | 'two_sided'.
    forecast_available: per-month bool; where False the month is computed
        forward-only regardless of `mode` (REAL-TIME MODE). If None:
          - mode='forward'                -> fine (no future data used anyway)
          - mode in ('backward','two_sided') -> treated as all-True (HINDSIGHT);
            pass an explicit mask to run real-time.
    Returns: dict with 'normalized' (array) and, for reconcile, 'gap' and
             'implied_drawdown' arrays.
    """
    E = np.asarray(E, float); b = np.asarray(b, float); r = np.asarray(r, float)
    n = len(E)
    if not (len(b) == len(r) == n):
        raise ValueError("E,b,r must be same length")
    if min_anchors is None:
        min_anchors = X
    C = _cum_log_growth(b, r, retention_normalize, X_retention)
    fa = (np.ones(n, bool) if forecast_available is None
          else np.asarray(forecast_available, bool))

    norm = np.full(n, np.nan)
    gap = np.full(n, np.nan)
    idraw = np.full(n, np.nan)

    def walks(t, offsets):
        out = []
        for k in offsets:
            s = t + k
            if 0 <= s < n and np.isfinite(E[s]) and np.isfinite(C[t]) and np.isfinite(C[s]):
                out.append(E[s] * np.exp(C[t] - C[s]))
        return out

    past = [-12 * a for a in range(1, X + 1)]
    future = [12 * a for a in range(1, X + 1)]

    for t in range(n):
        if mode == "forward" or not fa[t]:
            est = walks(t, past)
            if len(est) >= min_anchors:
                norm[t] = float(np.median(est))
        elif mode == "backward":
            est = walks(t, future)
            if len(est) >= min_anchors:
                norm[t] = float(np.median(est))
        else:  # two_sided
            pe, fe = walks(t, past), walks(t, future)
            if join_flavor == "pooled":
                pool = pe + fe
                if len(pool) >= min_anchors:
                    norm[t] = float(np.median(pool))
            else:  # reconcile
                fwd = np.median(pe) if pe else np.nan
                back = np.median(fe) if fe else np.nan
                if np.isfinite(back):
                    norm[t] = back                     # backward preferred when available
                elif np.isfinite(fwd):
                    norm[t] = fwd
                if np.isfinite(fwd) and np.isfinite(back):
                    gap[t] = fwd - back
                    rc = r[t] if rho_cap is None else rho_cap
                    idraw[t] = gap[t] / rc if rc else np.nan
    return {"normalized": norm, "gap": gap, "implied_drawdown": idraw}


# --------------------------------------------------------------------------
# regime #2 — present forecast (single forward-normalized eps1)
# --------------------------------------------------------------------------
def normalize_forecast(
    past_anchors,        # list of (years_before_now, E_real_on_trend)
    future_anchors,      # list of (years_after_now,  E_real_consensus_on_trend)
    g,                   # normal real growth = b_norm * rho
    target_years_forward=1.0,   # +1y => forward eps1
    mode="two_sided", join_flavor="reconcile",
    rho_cap=None, capital_drawdown=0.0,   # explicit dis-saving charge (forward route)
):
    """
    Build a single forward-normalized EPS at `target_years_forward` from now,
    from past (realized) and future (consensus) anchors on the normal line.

    Returns dict: normEPS (used), normEPS_fwd, normEPS_back, gap,
    implied_drawdown, slope_gap_vs_g.
    """
    if rho_cap is None:
        rho_cap = g
    tgt = target_years_forward

    # forward route: grow each past anchor to the target, then capital charge
    fwd_raws = [E * (1 + g) ** (p + tgt) for (p, E) in past_anchors]
    normEPS_fwd_raw = float(np.median(fwd_raws)) if fwd_raws else np.nan
    normEPS_fwd = normEPS_fwd_raw - rho_cap * capital_drawdown

    # backward route: discount each future anchor to the target
    back_est = [E / (1 + g) ** (a - tgt) for (a, E) in future_anchors]
    normEPS_back = float(np.median(back_est)) if back_est else np.nan

    have_future = np.isfinite(normEPS_back)
    if mode == "forward" or not have_future:
        used = normEPS_fwd
    elif mode == "backward":
        used = normEPS_back
    else:  # two_sided
        if join_flavor == "pooled":
            used = float(np.median(fwd_raws + back_est))   # note: raw fwd (no cap charge) in pool
        else:  # reconcile: prefer backward when a future anchor exists
            used = normEPS_back if have_future else normEPS_fwd

    gap = (normEPS_fwd_raw - normEPS_back
           if np.isfinite(normEPS_fwd_raw) and have_future else np.nan)
    idraw = gap / rho_cap if np.isfinite(gap) and rho_cap else np.nan

    # slope check: anchor-to-anchor implied growth vs g (nearest past & future)
    slope = np.nan
    if past_anchors and future_anchors:
        p, Ep = min(past_anchors, key=lambda x: x[0])
        a, Ef = min(future_anchors, key=lambda x: x[0])
        span = a + p
        if span > 0 and Ep > 0 and Ef > 0:
            slope = (Ef / Ep) ** (1.0 / span) - 1.0 - g   # >0 => anchors imply faster than g

    return {"normEPS": used, "normEPS_fwd": normEPS_fwd, "normEPS_back": normEPS_back,
            "gap": gap, "implied_drawdown": idraw, "slope_gap_vs_g": slope}


# backward-compat: original forward-only helper
def walk_forward_normalized(E, b, r, X=4, min_anchors=None):
    return normalize_series(E, b, r, X=X, mode="forward",
                            min_anchors=min_anchors)["normalized"]


if __name__ == "__main__":
    # --- self-tests on a perfectly-normal synthetic series ---
    n = 400
    r = np.full(n, 0.06); b = np.full(n, 0.5)
    g = 0.5 * 0.06
    E = 100 * (1 + g / 12) ** np.arange(n)     # exactly on the normal line
    fwd = normalize_series(E, b, r, X=4, mode="forward")["normalized"]
    back = normalize_series(E, b, r, X=4, mode="backward")["normalized"]
    two = normalize_series(E, b, r, X=4, mode="two_sided", join_flavor="pooled")["normalized"]
    lo, hi = 48, n - 48
    for nm, arr in [("forward", fwd), ("backward", back), ("two_sided", two)]:
        err = np.nanmax(np.abs(arr[lo:hi] - E[lo:hi]) / E[lo:hi])
        print(f"{nm:10s} max rel err on normal series = {err:.2e}  (should be ~0)")
    Enow = 100.0
    fc = normalize_forecast(
        past_anchors=[(1, Enow / (1 + g) ** 1), (2, Enow / (1 + g) ** 2)],
        future_anchors=[(3, Enow * (1 + g) ** 3), (4, Enow * (1 + g) ** 4)],
        g=g, target_years_forward=1.0, mode="two_sided", join_flavor="reconcile")
    print(f"forecast eps1 = {fc['normEPS']:.4f}  expected {Enow*(1+g):.4f}")
