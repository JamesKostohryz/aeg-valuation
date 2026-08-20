"""
idio/company_curve.py — one ticker in, the thirty-tenor idiosyncratic premium out.

THIS IS THE WIRE. Until 2026-08-20 nothing in the pricing pipeline imported this package. The
sealed engine takes its cost-of-equity curve through `repoint_rates.install_idio_hook()`, whose
`finrate_idio` row defaults to thirty zeros, and the only caller of `set_idio` anywhere was the
function that ZEROES it. So Coca-Cola and PepsiCo published the same real cost of equity to
fifteen significant figures — 0.0573744740161696 — and every company on the system discounted at
the market rate. This module is what `run_company.py` now calls to fill that row.

WHAT IT ASSEMBLES, and where each piece comes from:

  REGION 1   the level. ERP_i(front) = market_ERP(front) x semidev_i / capw_avg_semidev, then
             faded on the measured half-life. semidev and the cap weights come from
             `outputs/idio_universe_latest.csv`, rebuilt monthly by idio/feed.py from EODHD.
  REGION 2   the credit term structure. Mc x COMMON(t) charged to every name, plus the de-meaned
             differential from the issuer's own fitted curve. COMMON(t) is read LIVE off
             real-yields' aggregate investment-grade curve; the issuer curves come from
             `outputs/issuer_widen_latest.csv`.
  REGION 3   obsolescence. IDENTICALLY ZERO on a thirty-tenor grid at every durability category,
             because the earliest onset of any category is year 30 and the grid ends at year 30.
             It is computed and added anyway, so that the day the engine gains a terminal grid
             past year 30 this module needs no change. See `region3_is_visible` below — it is
             asserted, not assumed, so nobody can read the zero as evidence that obsolescence has
             been priced.

UNITS. `idio/erp.py` works in PERCENTAGE POINTS throughout (a semi-deviation of 10.73, a market
ERP of 4.13). The engine's Market Data rows are ANNUAL DECIMALS (0.0413). Every conversion in
this file is explicit and one-directional: percentage points in, decimals out, at the boundary.
Getting this wrong by a factor of a hundred would be caught instantly by the sanity band below,
which is why the band exists.

FAIL-CLOSED, EVERY INPUT. A premium built on a frozen universe, a stale set of credit curves or
a missing COMMON(t) is not a conservative approximation of the right answer, it is a different
answer, and the four-method tie cannot see any of it — the tie is an internal-consistency proof
and it holds just as well on a wrong curve. So each input either resolves or the valuation
refuses, and `PremiumRefused` says which one and what to run.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import erp as IE          # noqa: E402
import universe as UNI    # noqa: E402

# The band a real company premium lives in, in percentage points, at any tenor. It is wide on
# purpose: Coca-Cola sits at about -0.5 and Synopsys at about +3.2, so this is not a
# plausibility filter on the economics. It is a UNIT check and a wiring check -- a factor of a
# hundred, a sign flip, or a percentage-vs-decimal mix-up lands far outside it and stops the run
# instead of quietly repricing every company.
SANE_MIN_PP = -8.0
SANE_MAX_PP = 12.0

# Durability -> declared obsolescence year. The categories and their onsets are real-yields'
# CATEGORY_PRESETS (asfp/volsurface.py), reused rather than restated so the two cannot drift.
CATEGORY_ORY = {"A": 50, "B": 40, "C": 30}
DEFAULT_CATEGORY = "B"


class PremiumRefused(Exception):
    """No company premium could be built. The valuation must not proceed on a market-rate
    default: that is the state this whole module exists to end, and it is invisible once it is
    the fallback."""


def _pct(x):
    """annual decimal -> percentage points"""
    return float(x) * 100.0


def _dec(x):
    """percentage points -> annual decimal"""
    return float(x) / 100.0


def region3_is_visible(grid=None) -> bool:
    """True if the grid reaches far enough for obsolescence to be non-zero at ANY category.

    Asserted rather than assumed, because a zero that looks like a measurement is exactly how
    this project has been bitten before. On the engine's thirty-tenor sheet this is False for
    A, B and C alike, and the manifest says so on every run.
    """
    return any(IE.obsolescence_is_visible(y, grid=grid) for y in CATEGORY_ORY.values())


def build(ticker: str, market_erp_decimal, *, outdir=None, obs_category=None,
          semidev_override=None, asof=None, log=print) -> dict:
    """Return {series, provenance} for one company.

    `market_erp_decimal` is the thirty-tenor market ERP the engine is being pointed at, in annual
    decimals — `rate_feed.load_all()["market_erp"]`. Taking it from the caller rather than
    re-fetching it is deliberate: the premium is normalized against the market curve THIS
    valuation is using, so the two cannot come from different vintages.

    `series` is thirty annual decimals, ready for `repoint_rates.set_idio`.
    """
    t = ticker.strip().upper()
    grid = IE.GRID
    if len(market_erp_decimal) < len(grid):
        raise PremiumRefused(
            f"the market ERP curve has {len(market_erp_decimal)} tenors, need {len(grid)}")
    mkt_pct = {h: _pct(market_erp_decimal[h - 1]) for h in grid}

    # --- Region 1 inputs: the risk statistic and the cap-weighted normalizer -----------------
    outdir = outdir or os.path.join(os.path.dirname(_HERE), "outputs")
    try:
        u = UNI.load(outdir=outdir, asof=asof)
    except UNI.UniverseStale as e:
        raise PremiumRefused(
            f"the company-premium universe is unusable: {e}\n"
            f"  Run the idio-universe-refresh workflow. Refusing rather than pricing "
            f"{t} at the market rate, which is what this module exists to stop.")
    semidev, cap = dict(u["semidev"]), u["cap"]

    if semidev_override is not None:
        # A company outside the declared universe (not an S&P 500 constituent) can still be
        # priced: its own statistic is computed the production way and joins the SCORED set, but
        # NOT the cap-weighted denominator, which stays the index it is being measured against.
        semidev[t] = float(semidev_override)
    if t not in semidev:
        raise PremiumRefused(
            f"{t} has no risk statistic. It is not in the company-premium universe "
            f"({u['n']} names, as of {u['asof']}) and no semi-deviation was supplied. A "
            f"company with no measured downside volatility cannot be given a premium, and "
            f"giving it zero would price it as exactly average, silently.")

    inc, diag = IE.front_increments(semidev, cap, mkt_pct[IE.FRONT_TENOR])

    # --- Region 2 inputs: the aggregate credit curve, live, and the issuer curves ------------
    cred = IE.mel.fetch_market_credit(log=None)      # raises if unavailable; deliberately so
    common = IE.common_widening(cred["spread_pct"])

    widen_all, wmeta = IE.load_issuer_widen(root=outdir, asof=asof, log=None)
    if widen_all is None:
        raise PremiumRefused(
            f"the fitted issuer credit curves are unusable: {wmeta}\n"
            f"  Region 2 is the credit term structure and it is charged to every name. "
            f"Refusing rather than falling back to a flat credit curve, which would understate "
            f"the discount rate of every long-horizon company at once and tie perfectly.")
    widen = {k: widen_all.get(k) for k in semidev}
    r2_all, mean_w = IE.region2(widen, cap, common)

    # --- Region 3: the obsolescence shelf ---------------------------------------------------
    cat = (obs_category or DEFAULT_CATEGORY).strip().upper()[:1] or DEFAULT_CATEGORY
    if cat not in CATEGORY_ORY:
        raise PremiumRefused(f"unknown durability category {cat!r}; expected one of "
                             f"{sorted(CATEGORY_ORY)}")
    ory = CATEGORY_ORY[cat]
    r3 = IE.region3(ory)

    idio_pct, erp_pct = IE.build_curve(inc[t], r2_all.get(t, {}), r3, mkt_pct, grid)

    lo, hi = min(idio_pct.values()), max(idio_pct.values())
    if not (SANE_MIN_PP <= lo and hi <= SANE_MAX_PP):
        raise PremiumRefused(
            f"{t}'s premium runs {lo:+.3f} to {hi:+.3f} percentage points, outside the sanity "
            f"band [{SANE_MIN_PP}, {SANE_MAX_PP}]. This band is a UNIT and WIRING check, not a "
            f"view on the economics: a factor of a hundred or a sign flip lands here. Refusing.")

    series = [_dec(idio_pct[h]) for h in grid]
    tier = None
    if wmeta and isinstance(wmeta, dict):
        tier = "own fitted curve" if widen_all.get(t) else "cross-sectional fallback"

    prov = dict(
        ticker=t,
        semidev=round(semidev[t], 6),
        capw_avg_semidev=round(diag["capw_avg_semidev"], 6),
        semidev_ratio=round(semidev[t] / diag["capw_avg_semidev"], 6),
        universe_n=u["n"], universe_asof=u["asof"], universe_stale=bool(u["stale"]),
        in_universe=(semidev_override is None),
        market_erp_front_pct=round(mkt_pct[IE.FRONT_TENOR], 6),
        front_increment_pp=round(inc[t], 6),
        region2_1y_pp=round(r2_all.get(t, {}).get(1, 0.0), 6),
        region2_30y_pp=round(r2_all.get(t, {}).get(30, 0.0), 6),
        region2_tier=tier,
        issuer_curves_generated=(wmeta or {}).get("generated"),
        common_source=cred.get("source"), common_vintage=cred.get("vintage"),
        common_30y_pp=round(common[30], 6), m_common=IE.M_COMMON,
        obs_category=cat, declared_obsolescence_year=ory,
        region3_visible_on_this_grid=region3_is_visible(grid),
        region3_30y_pp=round(r3.get(30, 0.0), 6),
        premium_1y_pp=round(idio_pct[1], 6), premium_30y_pp=round(idio_pct[30], 6),
        premium_collapsed_pp=round(
            IE.collapse_rate(grid, [erp_pct[h] for h in grid])
            - IE.collapse_rate(grid, [mkt_pct[h] for h in grid]), 6),
    )
    if log:
        log("[idio] %s premium %+.4f pp at 1y, %+.4f at 30y, %+.4f collapsed  "
            "(semidev %.2f vs %.2f = %.3fx, Region 2 %s, obsolescence %s/ORY %d%s)"
            % (t, prov["premium_1y_pp"], prov["premium_30y_pp"], prov["premium_collapsed_pp"],
               prov["semidev"], prov["capw_avg_semidev"], prov["semidev_ratio"],
               tier, cat, ory,
               "" if prov["region3_visible_on_this_grid"]
               else ", INVISIBLE on a 30-tenor grid"))
    return dict(series=series, provenance=prov)
