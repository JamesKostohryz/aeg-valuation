#!/usr/bin/env python3
"""
idio_erp.py — THE idiosyncratic ERP term structure. One callable implementation.

Approved by James 2026-08-18 (session 18) from
`docs/AEG-Idio-ERP-TERM-STRUCTURE-DESIGN-2026-08-18.md` section 8, verbatim: solve MARGIN
at the front tenor; de-mean Region 2 but not Region 3; let Region 3 restore T4 on the
collapsed number; say plainly that T4 stays retired at the front.

Until this file existed there were ~90 one-shot `tools/*_prespec.py` measurement scripts and
no callable implementation of the formula, so nothing could be tested, versioned or wired.
This is that implementation. It is NOT wired into the pricing engine; landing it in
`real-yields` is a separate GATED decision and has not been made.

================================================================================
THE CONSTRUCTION
================================================================================

    idio_i(t) = D(t) x [ ERP_i(front) - market_ERP(front) ]              Region 1
              + Mc x COMMON(t)                                           Region 2a, EVERY company
              + M  x [ widen_i(t) - capw_mean_widen(t) ]                  Region 2b, de-meaned
              + STEP x 1{ t > obsolescence_year_i }                      Region 3, NOT de-meaned

    ERP_i(t)  = market_ERP(t) + idio_i(t)
    D(t)      = lam + (1 - lam) exp(-(t-1)/tau)
    widen_i(t)= spread_i(t) - spread_i(1)                                own curve, self-referenced
    COMMON(t) = ig_index_spread(t) - ig_index_spread(1)                  aggregate IG, observed
    M         = 1.5                                                      Region 2b pass-through
    Mc        = 1.0                                                      Region 2a pass-through
    STEP      = 1.0 pp, PROVISIONAL                                      pending the calibration

REGION 3 WAS REBUILT ON 2026-08-18 AND THE REBUILD MADE IT SHORTER. The previous version was a
Merton "elevator": the company slid toward distressed-credit status on a schedule set by three
durability categories, a rating-based ramp width and a spread cushion. Those parameters were
never calibrated -- elevator.py's own comments called them "illustrative placeholders" -- and
the construction implied that the average company needs somewhere between a quarter and all
over again of the entire equity risk premium purely for obsolescence, against the one good
direct measurement of that quantity (Siegel & Schwartz 2006) which runs the other way. It is
deleted. What replaces it is a MANDATORY analyst-declared year, a FLAT step beyond it, and a
one-directional bond-maturity override. Two numbers, each explicable in a sentence, neither
read from the defective credit-rating field.

REGION 1 AND WHY THE ANCHOR IS ABSENT. The SETTLED v1 states the front level as
`anchor_ERP x (semidev_i / semidev_anchor)` with `anchor_ERP` built from the anchor company's
own credit spread plus a solved MARGIN. Under the cap-weighted normalization that entire
apparatus cancels algebraically:

    ERP_i(front) = market_ERP(front) x semidev_i / capw_avg_semidev

The anchor, its spread and MARGIN do not appear. This was proven numerically in
`tools/idio_erp_anchor_calibration_v2.py` -- swapping the anchor to the runner-up and
quadrupling its spread moves the reported margin by 0.68pp and moves no premium by more than
8.9e-16 pp. It cancels. THE ANCHOR AND MARGIN MACHINERY IS THEREFORE DELETED FROM THIS MODULE
(2026-08-18, James's decision 1), not retained as a diagnostic. An elaborate apparatus that
enters no calculation is not free: it invites the reader to believe a number is driven by
something it is not, which is this project's standing suspicion #1 wearing a different hat.
The reduced form above is the whole of Region 1.

REGION 2 WAS FULLY DE-MEANED UNTIL 2026-08-19 AND THAT WAS WRONG. The argument for it ran:
an upward-sloping credit curve is mostly a common, market-wide term effect; the index's
constituents have upward-sloping curves too, so the AVERAGE widening is already inside
market_ERP(t) and adding it again double-counts.

IT IS NOT DOUBLE-COUNTING, AND THE REASON IS THE ONE THIS DESIGN ALREADY ACCEPTS FOR REGION 3.
The market ERP term structure is measured from INDEX options. The index is a diversified
portfolio: idiosyncratic risk cancels inside it and does not cancel inside a single company,
and idiosyncratic risk COMPOUNDS WITH HORIZON -- which is why credit curves slope up at all.
So the cap-weighted average COMPANY premium must sit ABOVE the INDEX premium, and the gap must
WIDEN WITH TENOR. That gap is the diversification benefit. Full de-meaning asserted it was
exactly zero at every tenor. Region 3's own comment block makes the identical argument for
obsolescence and was correctly exempted; Region 2 was not, and James caught it.

SO REGION 2 SPLITS IN TWO (James's ruling, 2026-08-19; SPEC-Region2-Credit-Term-Structure):

    Region 2_i(t) = Mc x COMMON(t)  +  M x [ widen_i(t) - capw_mean_widen(t) ]
                    ^^^^^^^^^^^^^      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                    charged to         unchanged: de-meaned, so relative ranking
                    EVERY name         between companies is exactly preserved

COMMON(t) is an OBSERVED quantity, not a parameter: the widening of the aggregate
investment-grade credit curve from one year to tenor t, read off the ICE BofA maturity buckets
that `real-yields/asfp/credit.py` already publishes every weekday. A forced zero is replaced by
a measurement, not by a different assumption.

WHAT THIS DOES TO T4. The identity changes SHAPE, and it is stated rather than discovered:

    capw avg company ERP(t) = market ERP(t) + Mc x COMMON(t) + capw avg obsolescence lift(t)

Region 1 still contributes exactly zero (cap-weighted average of D(t) x 0). Region 2's
DIFFERENTIAL still contributes exactly zero. What survives is two positive, named,
diversification terms instead of one. `t4_identity()` proves this holds at every tenor to
machine precision, and it is a PROOF of the construction rather than evidence about the world.
Any test asserting the cap-weighted average equals the market ERP beyond the front tenor is now
WRONG and must be updated, not worked around.

    RETIRED at the front tenor, where COMMON(1) = 0 exactly and widen(1) = 0 exactly, so the
      cap-weighted average equals the market ERP by construction and reporting it green would
      be standing suspicion #1 in its cleanest form. That half is UNCHANGED.
    RESTORED on the collapsed number, where `universe_wedge()` now returns the wedge SPLIT into
      its common-credit and obsolescence halves, because a single blended wedge would hide
      which of the two moved.

================================================================================
DERIVED CONSTANTS AND THE CHANGE LOG
================================================================================
Same discipline as `real-yields/vol_scale_v3.py`: constants that depend on each other are
DERIVED or ASSERTED at import, never typed twice and hoped to agree.

  2026-08-19  v2. Region 2 gains COMMON(t) (James's ruling; see above). Mc = 1.0 as decided.
              `region2()` now REQUIRES its `common` argument -- there is no default, because a
              default would let a caller silently reproduce the v1 behaviour and no test could
              see it. `t4_identity()` and `influence_check()` added.
  2026-08-18  v1. lam/tau adopted from tools/idio_mean_reversion.py. M = 1.5 reused from
              asfp/elevator.py::DEFAULT_MULTIPLE rather than re-invented. Front normalization
              target moved from the collapsed effective ERP (3.369) to the market ERP at the
              FRONT tenor (3.947) -- the v1 used the effective number, which was coherent only
              while the construction was flat in tenor.

Nothing here moves a valuation number. No company figure produced by this module may be
quoted for any company.
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import market_erp_live as mel  # noqa: E402

# ------------------------------------------------------------------ (0) constants

# MEASURED, not chosen: the fitted persistent floor and time constant of the cross-sectional
# semi-deviation differential. tools/idio_mean_reversion.py, 36 semi-annual anchors 1994-2011,
# ~178 names, horizons 1-25y, rmse 0.037.
LAM_MEASURED = 0.22
TAU_MEASURED = 4.9
MEAN_REVERSION_SOURCE = "outputs/2026-08-18-mean-reversion/mean_reversion.json"

# ADOPTED. Set ABOVE the measured floor on purpose. The measurement runs on today's surviving
# universe: a company whose risk stayed high and which then delisted is absent, so among
# initially-risky names only those whose risk subsided are observed. That biases the estimate
# toward more reversion than is real, which makes LAM_MEASURED a LOWER bound on persistence and
# makes the measurement anti-conservative in premium terms -- it understates what the risky tail
# should carry. 0.25 is a judgment, recorded as one, and it is the single knob to revisit if a
# survivorship-corrected estimate is ever produced.
LAM_ADOPTED = 0.25
TAU_ADOPTED = TAU_MEASURED

# Bond-to-equity pass-through. NOT a new number: asfp/elevator.py::DEFAULT_MULTIPLE, reused so
# the Region 2 -> Region 3 handoff at ORY is continuous rather than a jump.
M_PASSTHROUGH = 1.5

# THE COMMON-CREDIT PASS-THROUGH, AND THE ONE OPEN QUESTION IN THIS CHANGE.
#
# James's ruling of 2026-08-19 writes the construction as
#     Region 2_i(t) = COMMON(t) + 1.5 x [ widen_i(t) - capw_mean_widen(t) ]
# i.e. the common half enters at 1.0 and the differential half at 1.5. That is implemented
# exactly as decided, and it is named rather than left implicit so it is one line to revisit.
#
# THE ARGUMENT AGAINST 1.0, RECORDED BECAUSE IT IS NOT OBVIOUSLY WRONG. M = 1.5 is not a
# statement about idiosyncratic risk specifically; it is the bond-to-equity conversion --
# equity is junior, so a given widening of credit spread shows up about half again as large in
# the equity premium. COMMON(t) and widen_i(t) are the SAME physical quantity in the SAME units
# (percentage points of credit spread). Translating one at 1.5 and the other at 1.0 makes the
# conversion factor depend on whether the risk happens to be common or specific, which the
# leverage argument does not support. On that reading Mc should be 1.5, and COMMON(30) would be
# worth 0.80pp rather than 0.53pp on today's curve.
#
# THE ARGUMENT FOR 1.0 is conservatism: this term is charged to all 499 names with no company
# evidence behind it, and the smaller of two defensible numbers is the right place to start a
# term nobody has yet seen move a valuation. 1.0 ships. The question is flagged for James and
# the direction of the remaining uncertainty is known and it is UPWARD -- the same shape as
# OBSOLESCENCE_STEP_PP.
M_COMMON = 1.0
M_COMMON_IS_PROVISIONAL = True
M_COMMON_ALTERNATIVE = M_PASSTHROUGH          # the consistency-argument value, not adopted

# The front is where the semi-deviation statistic actually lives (1y/2y trailing blend), so it
# is where the level attaches and where the normalization target is read.
FRONT_TENOR = 1
GRID = list(range(1, 31))          # the published curve is 1..30

# THE GRID IS NOT A DETAIL, AND THIS IS THE FINDING THAT CAME OUT OF BUILDING IT.
# The earliest obsolescence onset of ANY durability category is ORY = 30 (exposed; moderate is
# 40, durable is 50). The published market ERP curve ends at year 30. So ON A 1..30 GRID REGION
# 3 IS IDENTICALLY ZERO FOR EVERY CATEGORY, the obsolescence wedge is exactly zero, and the
# "restored" T4 would be an identity all over again -- the same defect one level out, and it
# would have reported a clean pass. `selftest()` asserts this permanently so that nobody
# computes a wedge on a 30-year grid and reads the zero as evidence.
#
# Restoring T4 therefore REQUIRES a grid past year 30, which is what
# AEG-Idiosyncratic-Methodology-SETTLED-2026-08-13.md section 3 already says: run_company.py
# computes to 150 years and the terminal rate must be collapsed off that, because Region 3
# "mostly lives past year 30 for any durable or moderate company" and is currently invisible to
# the number that matters most for continuing value.
TERMINAL_GRID = list(range(1, 151))
MARKET_ERP_EXTENSION = "hold_last"   # see extend_market_erp(); an ASSUMPTION, declared as one

# ------------------------------------------------------------------ obsolescence (Region 3)
# REBUILT 2026-08-18 to James's settled design. The elevator, the durability categories and the
# rating-based ramp are DELETED, not deprecated -- see the header. What replaces all of it:
#
#   ONE analyst-declared year, a FLAT step beyond it, and a bond-maturity override.
#
# THE STEP SIZE. 1.0 percentage point, and it is now the MEASURED LOW END rather than a number
# somebody typed. tools/obsolescence_step_calibration.py (step 2a, run 2026-08-19) classified all
# 385 S&P 500 constituent exits on record by cause:
#
#     pays the shareholder out (acquired, merged, taken private)  48.7%   <- EXCLUDED
#     voids the thesis (bankruptcy, receivership, faded out)      41.2%
#     neither (spin-offs, redomiciles, renames)                   10.1%
#
# Applying the thesis-voiding share to the published ~4.5%/yr all-cause index exit rate gives a
# merger-stripped hazard of 1.85% a year, and a survivorship haircut of 0.55-0.85 -- because this
# premium is only ever charged to companies that have ALREADY survived to the analyst's horizon --
# brings it to 1.02 to 1.57 percentage points.
#
# SO 1.0 IS THE BOTTOM OF THE MEASURED RANGE, NOT THE MIDDLE. The central estimate is nearer 1.3.
# 1.0 is retained because the calibration is PARTIAL in one specific way that is stated rather
# than buried: the survivorship haircut is a declared range, not a measurement, since the change
# record does not carry addition dates for companies that predate it. Raising the step to the
# centre of the range moves every long-horizon valuation and is James's call, not this module's.
# The direction of the remaining uncertainty is known and it is UPWARD.
OBSOLESCENCE_STEP_PP = 1.0
OBSOLESCENCE_STEP_IS_PROVISIONAL = True     # partial calibration; see the range above
OBSOLESCENCE_STEP_MEASURED_RANGE_PP = (1.02, 1.57)
OBSOLESCENCE_STEP_CALIBRATION = "outputs/2026-08-19-obsolescence-step/obsolescence_step.json"

# The bond-maturity override's size threshold. Without it a residual stub moves a valuation by
# decades: Coca-Cola's longest bond matures 2093 with $96m left outstanding -- a leftover from
# 1993 -- while its longest bond above this threshold matures 2064 with $1.65bn. Verified against
# real-yields/outputs/bonds_used_*.csv 2026-08-18: the threshold binds on KO and on nothing else
# in the covered set, and it moves KO's governing date 29 years earlier, which is the whole point.
BOND_SIZE_THRESHOLD_USD = 250e6

# THE UNIVERSE NOW COMES FROM A FEED, NOT FROM THREE FROZEN RESEARCH OUTPUTS.
#
# Until 2026-08-19 this module read:
#     outputs/2026-08-17-rank-residual/rank_residual_scored.csv   (semi-deviation)
#     outputs/2026-08-16-universe-repair/price_test_flat_erp.csv  (price, for cap weights)
#     outputs/2026-08-16-validation2/price_test_validation2.csv   (price, for cap weights)
#     outputs/.eodhd_fund_cache/<T>.shares_annual.json            (shares, for cap weights)
#
# Every one of those is a DATED ONE-SHOT OUTPUT of a measurement script, in a working folder
# that is not a repository. Nothing recomputed any of them. Had this module been wired into the
# pricing engine as it stood, every company premium would have been pinned to its 17 August 2026
# value for good, and no test could have caught it, because a frozen number is arithmetically
# perfect. That is this project's signature failure, in the newest place it could appear.
#
# idio/feed.py rebuilds the universe monthly from EODHD; idio/universe.py reads it and REFUSES
# a stale one rather than falling back to the frozen files.
UNIVERSE_OUTDIR = os.environ.get("IDIO_OUTDIR", os.path.join(ROOT, "outputs"))


def _assert_constants_consistent():
    """Fires at import if anyone edits one constant without the others. The point is to make
    drift impossible rather than to document that it would be bad."""
    if LAM_ADOPTED < LAM_MEASURED - 1e-12:
        raise AssertionError(
            "LAM_ADOPTED=%.4f is BELOW the measured floor %.4f. The measurement is survivorship-"
            "biased toward more reversion than is real, so the adopted value may only be raised "
            "above it, never lowered below." % (LAM_ADOPTED, LAM_MEASURED))
    if not 0.0 <= LAM_ADOPTED <= 1.0:
        raise AssertionError("LAM_ADOPTED must lie in [0,1]; got %r" % (LAM_ADOPTED,))
    if TAU_ADOPTED <= 0:
        raise AssertionError("TAU_ADOPTED must be positive; got %r" % (TAU_ADOPTED,))
    if abs(decay(FRONT_TENOR) - 1.0) > 1e-12:
        raise AssertionError("D(front) must be exactly 1; got %r" % decay(FRONT_TENOR))
    prev = None
    for t in GRID:
        d = decay(t)
        if prev is not None and d > prev + 1e-15:
            raise AssertionError("D(t) must be non-increasing; rose at t=%d" % t)
        if d < LAM_ADOPTED - 1e-12:
            raise AssertionError("D(%d)=%r fell below the floor %r" % (t, d, LAM_ADOPTED))
        prev = d


# ------------------------------------------------------------------ (0b) dates

def _as_date(x):
    """ISO string or date -> date. Kept tiny and local so the module stays dependency-free."""
    if isinstance(x, _dt.date):
        return x
    return _dt.date.fromisoformat(str(x)[:10])


def _today():
    return _dt.datetime.now(_dt.timezone.utc).date()


# ------------------------------------------------------------------ (1) the decay

def decay(t, lam=None, tau=None):
    """D(t): the fraction of the FRONT idiosyncratic differential still expected at horizon t.

    D(1) = 1 exactly; D is monotone non-increasing; D(inf) = lam. lam = 1 reproduces the flat
    SETTLED v1 exactly and lam = 0 decays the whole differential away, so this is a strict
    generalization of the v1 rather than a competing claim.
    """
    lam = LAM_ADOPTED if lam is None else lam
    tau = TAU_ADOPTED if tau is None else tau
    return lam + (1.0 - lam) * math.exp(-(float(t) - float(FRONT_TENOR)) / tau)


# ------------------------------------------------------------------ (2) universe loading

def load_universe(outdir=None, asof=None):
    """(semidev, market_cap) from the live feed. Raises UniverseStale if the feed has stopped.

    RAISING IS THE FEATURE. The previous version read frozen research outputs and could not
    fail; that is precisely why the numbers were frozen. A company premium priced off a risk
    measure nobody has updated since August is not a conservative estimate of the right answer,
    it is a different answer wearing the right answer's name."""
    import universe as _uni
    r = _uni.load(outdir=outdir or UNIVERSE_OUTDIR, asof=asof)
    if r["stale"]:
        print("  WARNING: idio universe is %d days old (latest close %s). The monthly refresh "
              "has been missed." % (r["age_days"], r["asof"]))
    return r["semidev"], r["cap"]


# ------------------------------------------------------------------ (3) Region 1

def front_increments(semidev, cap, market_erp_front):
    """idio_i(front) = ERP_i(front) - market_ERP(front), cap-weighted-average exactly zero.

    Returns (increments, diagnostics). The MARGIN normalization is solved here and it is solved
    at the FRONT tenor, not against the collapsed effective ERP -- the front is where the
    semi-deviation statistic lives.
    """
    covered = [t for t in semidev if t in cap]
    if not covered:
        raise ValueError("no name has both a semi-deviation and a market cap")
    total = sum(cap[t] for t in covered)
    capw = sum(cap[t] * semidev[t] for t in covered) / total
    erp = {t: market_erp_front * semidev[t] / capw for t in semidev}
    inc = {t: erp[t] - market_erp_front for t in semidev}
    check = sum(cap[t] * inc[t] for t in covered) / total
    if abs(check) > 1e-9:
        raise AssertionError("front normalization broken: cap-weighted mean increment = %.3e" % check)
    return inc, dict(capw_avg_semidev=capw, covered=len(covered), scored=len(semidev),
                     market_erp_front=market_erp_front, capw_mean_increment=check,
                     uncovered=sorted(set(semidev) - set(cap)))


# DELETED 2026-08-18: anchor_diagnostic(). The anchor company, its credit spread and the solved
# MARGIN were proven algebraically inert (see the header) and are deleted from the design rather
# than kept as a reported diagnostic. Nothing imports it; nothing computed from it was ever
# published. If a future reader wants the historical proof it is in
# tools/idio_erp_anchor_calibration_v2.py, which is retained as the record of the measurement.


# ------------------------------------------------------------------ (4) Region 2

def widening(spread_pct, grid=None):
    """widen_i(t) = spread_i(t) - spread_i(front), the SELF-REFERENCED widening of the issuer's
    own real credit curve. Not a comparison against a market-average spread -- that is the
    construction `asfp/idio_ts.py` computes and it is explicitly NOT what this design uses
    (AEG-Idiosyncratic-Methodology-SETTLED-2026-08-13.md section 4)."""
    grid = grid or GRID
    base = spread_pct.get(FRONT_TENOR)
    if base is None:
        return None
    return {t: spread_pct.get(t, spread_pct[max(k for k in spread_pct if k <= t)]) - base
            for t in grid}


def common_widening(ig_spread_pct, grid=None):
    """COMMON(t) = ig_index_spread(t) - ig_index_spread(front), the AGGREGATE investment-grade
    credit curve's own widening. Charged to every company (see the header).

    This is a MEASUREMENT and it is read live, never typed. `market_erp_live.fetch_market_credit`
    supplies `ig_spread_pct` from real-yields `outputs/market_credit_latest_annual.csv`, which
    the weekday close rewrites, and refuses rather than falling back if that stops.

    COMMON(front) = 0 EXACTLY, by construction and by assertion, which is what preserves the
    front-tenor T4 identity unchanged through this change.
    """
    grid = grid or GRID
    base = ig_spread_pct.get(FRONT_TENOR)
    if base is None:
        raise ValueError("the aggregate credit curve has no tenor %d" % FRONT_TENOR)
    out = {}
    for h in grid:
        v = ig_spread_pct.get(h)
        if v is None:
            keys = [k for k in ig_spread_pct if k <= h]
            if not keys:
                raise ValueError("the aggregate credit curve starts after tenor %d" % h)
            v = ig_spread_pct[max(keys)]
        out[h] = v - base
    if abs(out[FRONT_TENOR]) > 1e-12:
        raise AssertionError("COMMON(front) must be exactly zero; got %r" % out[FRONT_TENOR])
    neg = [h for h in grid if out[h] < -1e-9]
    if neg:
        print("  WARNING: the aggregate IG credit curve INVERTS at tenors %s. COMMON(t) is "
              "negative there, so the average company is being charged LESS than the index at "
              "those horizons. That is what the curve says; it is reported, not clipped."
              % neg[:6])
    return out


def zero_common(grid=None):
    """An explicitly zero COMMON(t), for tests and for reproducing the pre-2026-08-19 v1.

    IT EXISTS SO THAT SWITCHING THE TERM OFF HAS TO BE TYPED. `region2()` deliberately has no
    default for `common`: a default would let a caller drop the term and reproduce the old
    behaviour with every gate still green, which is this project's standing failure mode.
    """
    return {h: 0.0 for h in (grid or GRID)}


ISSUER_WIDEN_MAX_AGE_DAYS = 45      # bond curves move slowly, but not for ever


def load_issuer_widen(root=None, grid=None, asof=None, log=print):
    """widen_i(t) for EVERY name, from the fitted issuer credit curves.

    Reads `outputs/2026-08-19-region2-coverage/issuer_widen.csv`, produced by
    AEG-Project `tools/region2_issuer_curves_2026-08-19.py` to the plan pre-registered in
    `docs/PREREG-Region2-Issuer-Curves-and-Tier3-2026-08-19.md`.

    WHAT CHANGED, AND WHY IT IS NOT THE SAME THING AS THE OLD `fetch_issuer_credit` PATH. The
    nine curves in production are the AGGREGATE investment-grade shape scaled by one number per
    issuer -- verified 2026-08-19 by dividing cod_<T>_annual.csv by ig_index_spread and finding
    the ratio constant to about one percent across all thirty tenors. Every company had the same
    shape and only the height differed. These curves are fitted to each issuer's OWN bonds, so
    the shape is the issuer's, which is what James asked for.

    Returns (widen_by_ticker, meta) or (None, reason) if the file is absent or stale. It does
    NOT fall back silently: a caller that gets None must decide, in the open, what to do.
    """
    grid = grid or GRID
    home = os.path.dirname(ROOT)
    bases = ([root] if root else []) + [
        os.path.join(ROOT, "outputs"),
        os.path.join(home, "AEG-Project", "outputs", "2026-08-19-region2-coverage"),
        os.path.join(home, "outputs", "2026-08-19-region2-coverage"),
    ]
    path = meta = None
    for b in bases:
        for name in ("issuer_widen.csv", "issuer_widen_latest.csv"):
            q = os.path.join(b, name)
            if os.path.exists(q):
                path = q
                break
        if path:
            mp = os.path.join(os.path.dirname(path), "tier3_fit.json")
            if os.path.exists(mp):
                try:
                    meta = json.load(open(mp))
                except ValueError:
                    meta = None
            break
    if path is None:
        return None, "no issuer_widen.csv found under %s" % bases

    gen = (meta or {}).get("generated")
    if gen:
        age = (_as_date(asof) if asof else _today()) - _as_date(gen)
        if age.days > ISSUER_WIDEN_MAX_AGE_DAYS:
            return None, ("issuer_widen.csv was generated %s, %d days ago (limit %d). The bond "
                          "pull and curve fit have not been re-run." % (gen, age.days,
                                                                        ISSUER_WIDEN_MAX_AGE_DAYS))
    out, tiers = {}, {}
    for r in csv.DictReader(open(path)):
        t = r["ticker"].strip()
        try:
            out[t] = {h: float(r["widen_%d" % h]) for h in grid}
            tiers[t] = int(r["tier"])
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        return None, "issuer_widen.csv parsed to zero names (%s)" % path
    m = dict(path=path, generated=gen, n=len(out),
             tier_counts={k: sum(1 for v in tiers.values() if v == k) for k in (1, 2, 3, 4)},
             tier3_adopted=(meta or {}).get("adopted"),
             mean_slope_fallback=(meta or {}).get("mean_slope_fallback"))
    if log:
        log("  issuer widening: %d names, generated %s, tiers %s"
            % (m["n"], gen or "unknown", m["tier_counts"]))
    return out, m


def region2(widen_by_ticker, cap, common, grid=None):
    """Mc x COMMON(t), charged to everyone, PLUS the de-meaned differential widening x M.

    `common` is REQUIRED and has no default -- see zero_common() for why.

    Names with no issuer curve are assigned the cap-weighted average widening -- the honest
    no-information default -- so their DIFFERENTIAL contribution is exactly zero rather than a
    fabricated number. They still carry COMMON(t), which is the whole point of the change: a
    company with no bond data is no longer assumed to be flat-credit relative to the index.

    Returns (contribution_by_ticker, mean_widen_by_tenor).
    """
    grid = grid or GRID
    if common is None:
        raise ValueError(
            "region2() requires COMMON(t). Pass common_widening(...) for the live aggregate "
            "credit curve, or zero_common() if you explicitly want the retired v1 behaviour. "
            "There is no default because a default would silently restore the defect.")
    missing = [h for h in grid if h not in common]
    if missing:
        raise ValueError("COMMON(t) is missing tenors %s" % missing[:6])
    have = [t for t in widen_by_ticker if t in cap and widen_by_ticker[t]]
    mean = {}
    for h in grid:
        if have:
            tot = sum(cap[t] for t in have)
            mean[h] = sum(cap[t] * widen_by_ticker[t][h] for t in have) / tot
        else:
            mean[h] = 0.0
    out = {}
    for t, w in widen_by_ticker.items():
        base = {h: M_COMMON * common[h] for h in grid}
        if not w:
            out[t] = base
        else:
            out[t] = {h: base[h] + M_PASSTHROUGH * (w[h] - mean[h]) for h in grid}
    return out, mean


# ------------------------------------------------------------------ (5) Region 3

class ObsolescenceNotDeclared(Exception):
    """Raised when a company is valued without a declared obsolescence year. It is a REFUSAL,
    not a warning, and there is deliberately no default to fall back to."""


def load_bonds(ticker, root=None):
    """Real bonds outstanding for `ticker` from real-yields/outputs/bonds_used_<T>.csv.

    Returns a list of dicts with `maturity` (ISO date), `outstanding` (USD) and `description`,
    or None if no bond file exists for this issuer. A missing file means NO OVERRIDE -- the
    declared year stands. That is the correct behaviour: the override only ever fires where the
    bond market is demonstrably lending, and silence is not an opinion.
    """
    home = os.path.dirname(ROOT)          # AEG-Project sits directly under the user's home
    for base in ([root] if root else []) + [
            os.path.join(ROOT, "repo-files"), ROOT,
            os.path.join(ROOT, "outputs"),
            # James's Windows layout, and the sandbox mount layout, in that order.
            os.path.join(home, "Documents", "GitHub", "real-yields", "outputs"),
            os.path.join(home, "GitHub", "real-yields", "outputs")]:
        p = os.path.join(base, "bonds_used_%s.csv" % ticker)
        if os.path.exists(p):
            out = []
            for r in csv.DictReader(open(p)):
                try:
                    out.append(dict(maturity=r["maturity"],
                                    outstanding=float(r["outstanding"]),
                                    description=r.get("description", ""),
                                    cusip=r.get("cusip", "")))
                except (KeyError, TypeError, ValueError):
                    continue
            return out or None
    return None


def governing_obsolescence_year(declared_year, bonds=None, asof=None,
                                size_threshold=BOND_SIZE_THRESHOLD_USD):
    """Apply the bond-maturity override to a declared obsolescence year.

    THE RULE, AND IT IS ONE-DIRECTIONAL BY DESIGN. Where a company has real bonds outstanding
    maturing AFTER the declared year, the step is postponed until the last of those bonds
    matures. Where the bond market is actually lending this company money it has an opinion and
    the analyst should not overrule it -- only supplement it where the bond market goes silent.
    A bond can push the adjustment LATER. It can never pull it EARLIER, and the max() below is
    the whole of that guarantee.

    Only bonds at or above `size_threshold` count. See BOND_SIZE_THRESHOLD_USD.

    Returns (effective_year, governing) where `governing` is None if the declared year stands,
    or a dict naming the bond that set the date. The governing bond is RETURNED so it can be
    PRINTED: a valuation whose horizon was moved thirty years by one bond must say which bond.
    """
    if declared_year is None:
        raise ObsolescenceNotDeclared(
            "no obsolescence year declared. It is a mandatory forecaster input, exactly like "
            "the explicit forecast period: the year beyond which the analyst has no visibility. "
            "It is never defaulted, never inferred from a durability category, and never "
            "skipped -- the system refuses to value the company instead (rule D1).")
    declared_year = float(declared_year)
    if declared_year <= 0:
        raise ValueError("declared obsolescence year must be positive; got %r" % declared_year)
    if not bonds:
        return declared_year, None

    asof_d = _as_date(asof) if asof else _today()
    best = None
    for b in bonds:
        if float(b.get("outstanding") or 0.0) < size_threshold:
            continue
        try:
            yrs = (_as_date(b["maturity"]) - asof_d).days / 365.25
        except (KeyError, ValueError, TypeError):
            continue
        if yrs > declared_year and (best is None or yrs > best[0]):
            best = (yrs, b)
    if best is None:
        return declared_year, None
    yrs, b = best
    return yrs, dict(years=yrs, maturity=b["maturity"], outstanding=b["outstanding"],
                     description=b.get("description", ""), cusip=b.get("cusip", ""),
                     declared_year=declared_year, postponed_by_years=yrs - declared_year)


def region3(declared_year, bonds=None, step_pp=None, grid=None, asof=None):
    """OBSOLESCENCE. A single permanent shelf beyond the declared (or bond-postponed) year.

    FLAT. Not a ramp, not a rising function, not compounding. It represents an annual chance
    that the thesis is simply void with no way to know when, and a constant hazard is exactly a
    constant addition to the discount rate. Anything rising would be asserting that the analyst
    knows the hazard grows, which is the thing the declared year already says he does not know.

    NOT DE-MEANED, and that asymmetry is the entire reason this term exists: the index survives
    by replacing its dying constituents and an individual company cannot replace itself.

    Returns {tenor: pp}. Zero at and below the effective year, `step_pp` above it.
    """
    grid = grid or GRID
    step = OBSOLESCENCE_STEP_PP if step_pp is None else float(step_pp)
    eff, _gov = governing_obsolescence_year(declared_year, bonds, asof=asof)
    return {h: (step if float(h) > eff else 0.0) for h in grid}


# ------------------------------------------------------------------ (6) assembly + collapse

def build_curve(front_increment, r2, r3, market_erp_curve, grid=None):
    """idio_i(t) and ERP_i(t) = market_ERP(t) + idio_i(t)."""
    grid = grid or GRID
    idio = {h: decay(h) * front_increment + r2.get(h, 0.0) + r3.get(h, 0.0) for h in grid}
    return idio, {h: market_erp_curve[h] + idio[h] for h in grid}


def collapse_rate(grid, rate_pct, cashflows=None, growth=2.0, lo=-5.0, hi=60.0, tol=1e-10):
    """Single flat rate repricing `cashflows` identically to the term structure.

    Vendored from `real-yields/asfp/collapse.py::collapse_rate`, algorithm for algorithm, so
    this module runs without a checkout. `selftest()` asserts the defining invariant (a flat
    curve collapses to itself) -- if the two ever diverge that is what catches it.
    """
    g = [float(x) for x in grid]
    if cashflows is None:
        cashflows = [(1.0 + growth / 100.0) ** t for t in g]
    df, acc = [], 1.0
    for r in rate_pct:
        acc *= 1.0 / (1.0 + float(r) / 100.0)
        df.append(acc)
    target = sum(c * d for c, d in zip(cashflows, df))
    for _ in range(400):
        mid = 0.5 * (lo + hi)
        pv = sum(c / (1.0 + mid / 100.0) ** t for c, t in zip(cashflows, g))
        if pv > target:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


# ------------------------------------------------------------------ (7) T4

def extend_market_erp(mkt, grid=None, method=None):
    """Extend the published 1..30 market ERP curve out to the terminal grid.

    AN ASSUMPTION, DECLARED AS ONE. Nothing trades past a year, let alone past thirty, so any
    extension is a modelling choice rather than a measurement. `hold_last` carries the year-30
    forward ERP flat, which is the only zero-information choice: it asserts no further decay and
    no further rise. It is used ONLY for the obsolescence-wedge diagnostic, never for a
    company's discount rate, and the wedge should be re-reported if the extension changes.
    """
    grid = grid or TERMINAL_GRID
    method = method or MARKET_ERP_EXTENSION
    if method != "hold_last":
        raise ValueError("unknown market ERP extension %r" % (method,))
    last = max(mkt)
    return {h: (mkt[h] if h in mkt else mkt[last]) for h in grid}


# DELETED 2026-08-18: extend_credit_grid(). It existed solely to carry the market credit grid out
# to the terminal grid for the elevator to board on. The elevator is gone and nothing else reads
# a credit grid at long tenors, so this is orphaned rather than merely unused.


def t4_front_is_an_identity(inc, cap, tol=1e-9):
    """PROOF, not a claim: the cap-weighted mean front increment is zero by construction, so a
    'T4 pass' at the front tenor is an identity and must never be reported as evidence."""
    covered = [t for t in inc if t in cap]
    tot = sum(cap[t] for t in covered)
    m = sum(cap[t] * inc[t] for t in covered) / tot
    return abs(m) < tol, m


def universe_wedge(inc, r2_all, r3_all, cap, market_erp_curve, grid=None, growth=2.0,
                   common=None):
    """T4, RESTORED, AND NOW SPLIT IN TWO. The collapsed cap-weighted average assigned ERP minus
    the collapsed market ERP.

    Region 1 contributes exactly zero (D(t) x 0) and Region 2's DIFFERENTIAL contributes exactly
    zero (de-meaned). What is left is two named, positive diversification terms:

        wedge = collapsed[ Mc x COMMON(t) ]  +  collapsed[ average obsolescence lift(t) ]

    BOTH HALVES ARE REPORTED SEPARATELY ON PURPOSE. A single blended wedge would move when
    either half moved and say nothing about which, and "a number that changed for a reason
    nobody can name" is how this engine has been bitten before. Pass `common` to get the split;
    without it only the total is returned.

    Neither half was fitted to anything, so asking whether each is plausible is a real test.
    """
    grid = grid or GRID
    covered = [t for t in inc if t in cap]
    tot = sum(cap[t] for t in covered)
    avg = []
    for h in grid:
        s = sum(cap[t] * (decay(h) * inc[t] + r2_all.get(t, {}).get(h, 0.0)
                          + r3_all.get(t, {}).get(h, 0.0)) for t in covered) / tot
        avg.append(market_erp_curve[h] + s)
    mkt = [market_erp_curve[h] for h in grid]
    c_all = collapse_rate(grid, avg, growth=growth)
    c_mkt = collapse_rate(grid, mkt, growth=growth)
    out = dict(collapsed_universe_erp=c_all, collapsed_market_erp=c_mkt,
               wedge_pp=c_all - c_mkt,
               front_check=avg[0] - mkt[0])
    if common is not None:
        c_com = collapse_rate(grid, [market_erp_curve[h] + M_COMMON * common[h] for h in grid],
                              growth=growth) - c_mkt
        avg_r3 = {h: sum(cap[t] * r3_all.get(t, {}).get(h, 0.0) for t in covered) / tot
                  for h in grid}
        c_obs = collapse_rate(grid, [market_erp_curve[h] + avg_r3[h] for h in grid],
                              growth=growth) - c_mkt
        out.update(common_wedge_pp=c_com, obsolescence_wedge_pp=c_obs,
                   split_residual_pp=(c_all - c_mkt) - c_com - c_obs)
    return out


def t4_identity(inc, r2_all, r3_all, cap, market_erp_curve, common, grid=None, tol=1e-9):
    """PROOF, at every tenor, that

        capw avg company ERP(t) = market ERP(t) + Mc x COMMON(t) + capw avg obsolescence(t)

    This is the new shape of T4 and it is an IDENTITY OF THE CONSTRUCTION, not evidence about
    the world -- exactly like `t4_front_is_an_identity()`, and it must be read the same way. It
    is asserted because the two things it can catch are real: a COMMON(t) that failed to reach
    every name (a company silently missing from `r2_all`), and a differential that stopped
    de-meaning (which would tilt the average and be invisible in any single company's number).

    Returns (ok, worst_abs_error_pp, worst_tenor).
    """
    grid = grid or GRID
    covered = [t for t in inc if t in cap]
    tot = sum(cap[t] for t in covered)
    worst, worst_h = 0.0, None
    for h in grid:
        lhs = market_erp_curve[h] + sum(
            cap[t] * (decay(h) * inc[t] + r2_all.get(t, {}).get(h, 0.0)
                      + r3_all.get(t, {}).get(h, 0.0)) for t in covered) / tot
        rhs = (market_erp_curve[h] + M_COMMON * common[h]
               + sum(cap[t] * r3_all.get(t, {}).get(h, 0.0) for t in covered) / tot)
        e = abs(lhs - rhs)
        if e > worst:
            worst, worst_h = e, h
    return worst < tol, worst, worst_h


# ------------------------------------------------------------------ (8) self-test

def obsolescence_is_visible(declared_year, grid=None, bonds=None, asof=None):
    """Does a declaration at `declared_year` produce ANY nonzero Region 3 on this grid?

    THE POINT OF THIS FUNCTION IS TO STOP A ZERO BEING MISREAD AS A RESULT. If the effective
    year sits at or past the end of the grid, Region 3 is identically zero -- not because
    obsolescence does not matter for this company but because the grid cannot see it. That
    distinction is invisible in the output number and has already cost this project one clean
    'pass' that was an artifact (the 1..30 grid against an earliest onset of year 30). Anything
    computing a wedge must call this first and refuse the zero rather than report it.
    """
    grid = grid or GRID
    eff, _ = governing_obsolescence_year(declared_year, bonds, asof=asof)
    return max(float(h) for h in grid) > eff


def wedge_sensitivity(market_erp_curve, declared_years=(20, 30, 40, 50),
                      steps=(0.5, 1.0, 1.5, 2.0), grid=None, growth=2.0):
    """How much does the obsolescence shelf move a COLLAPSED discount rate?

    REPLACES the old rating x durability-category sweep, which measured the elevator and the
    credit-rating field -- both of which are now deleted. The two things that survive are the
    only two the new design has: WHEN the shelf starts and HOW BIG it is. Neither is read from
    a data field, so neither can be corrupted by the rating defect; the declared year is the
    analyst's and the step is a calibrated constant.

    Returns {(declared_year, step_pp): collapsed_lift_pp}, plus the collapsed base under
    ("_base_collapsed_market", "").
    """
    grid = grid or TERMINAL_GRID
    mkt = [market_erp_curve[h] for h in grid]
    base = collapse_rate(grid, mkt, growth=growth)
    out = {}
    for y in declared_years:
        for s in steps:
            if not obsolescence_is_visible(y, grid):
                out[(y, s)] = None      # explicitly NOT zero -- the grid cannot see it
                continue
            e = region3(y, step_pp=s, grid=grid)
            out[(y, s)] = collapse_rate(grid, [market_erp_curve[h] + e[h] for h in grid],
                                        growth=growth) - base
    out[("_base_collapsed_market", "")] = base
    return out


def selftest(verbose=True):
    def say(*a):
        if verbose:
            print(*a)
    _assert_constants_consistent()
    say("  constants consistent: lam=%.3f (>= measured %.3f), tau=%.2f, M=%.2f"
        % (LAM_ADOPTED, LAM_MEASURED, TAU_ADOPTED, M_PASSTHROUGH))

    # D(t) invariants
    assert abs(decay(1) - 1.0) < 1e-15
    assert abs(decay(10 ** 6) - LAM_ADOPTED) < 1e-9
    assert decay(1, lam=1.0) == 1.0 and abs(decay(30, lam=1.0) - 1.0) < 1e-15, \
        "lam=1 must reproduce the flat SETTLED v1 exactly"
    say("  D(t): D(1)=1 exact, monotone, D(inf)=lam, lam=1 reproduces the flat v1")

    # collapse: a flat curve must collapse to itself
    for flat in (2.0, 5.5, 9.25):
        c = collapse_rate(GRID, [flat] * len(GRID))
        assert abs(c - flat) < 1e-6, "flat %r collapsed to %r" % (flat, c)
    say("  collapse_rate: flat curves reprice to themselves to 1e-6")

    # REGION 2, NEW SHAPE (2026-08-19). The cap-weighted mean is no longer zero -- it is
    # exactly Mc x COMMON(t). Asserting the old zero is now asserting the DEFECT, so the test
    # is rewritten rather than relaxed.
    cap = {"A": 3.0, "B": 1.0}
    w = {"A": {h: 0.01 * h for h in GRID}, "B": {h: 0.03 * h for h in GRID}}
    common = {h: 0.02 * (h - 1) for h in GRID}
    r2, mean = region2(w, cap, common)
    for h in GRID:
        m = (cap["A"] * r2["A"][h] + cap["B"] * r2["B"][h]) / 4.0
        assert abs(m - M_COMMON * common[h]) < 1e-12, (
            "region2's cap-weighted mean must equal Mc x COMMON(t); at t=%d it is %r, expected %r"
            % (h, m, M_COMMON * common[h]))
    say("  region2: cap-weighted mean is exactly Mc x COMMON(t) at every tenor")

    # THE DIFFERENTIAL MUST STILL DE-MEAN EXACTLY. Same test, run with COMMON switched off, so
    # that a bug in the differential cannot hide inside a nonzero common term.
    r2z, _ = region2(w, cap, zero_common())
    for h in GRID:
        m = (cap["A"] * r2z["A"][h] + cap["B"] * r2z["B"][h]) / 4.0
        assert abs(m) < 1e-12, "the differential is not de-meaned at t=%d: %r" % (h, m)
    say("  region2: with COMMON off, the differential still de-means to exactly zero")

    # RELATIVE RANKING IS PRESERVED. COMMON(t) is a level shift common to every name, so no
    # pair of companies may change order because of it. This is the property James was
    # protecting when he kept the de-meaning on the differential.
    for h in GRID:
        assert abs((r2["A"][h] - r2["B"][h]) - (r2z["A"][h] - r2z["B"][h])) < 1e-12, \
            "COMMON(t) altered the SPREAD between two companies at t=%d -- it must not" % h
    say("  region2: COMMON(t) shifts every name equally; no pair changes order")

    # region2 must REFUSE a missing COMMON rather than defaulting it to zero.
    try:
        region2(w, cap, None)
        raise AssertionError("region2 accepted a missing COMMON(t)")
    except ValueError:
        pass
    say("  region2: refuses a missing COMMON(t); switching it off has to be typed")

    # COMMON(front) is zero exactly, whatever the aggregate curve looks like.
    c = common_widening({1: 0.49, 5: 0.77, 10: 0.98, 20: 1.02, 30: 1.02})
    assert c[1] == 0.0 and abs(c[30] - 0.53) < 1e-12
    say("  common_widening: COMMON(front)=0 exactly, COMMON(30)=%.4fpp on the sample curve"
        % c[30])

    # Region 3 must REFUSE an undeclared obsolescence year. No default exists to fall back to.
    try:
        region3(None)
        raise AssertionError("region3 accepted an undeclared obsolescence year")
    except ObsolescenceNotDeclared:
        pass
    say("  region3: refuses an undeclared obsolescence year (no default, rule D1)")

    # The step is FLAT: exactly two distinct values, zero and the step, and it never rises again.
    e = region3(40, grid=TERMINAL_GRID)
    assert e[40] == 0.0 and e[41] == OBSOLESCENCE_STEP_PP, "step must switch on just past the year"
    assert set(e.values()) == {0.0, OBSOLESCENCE_STEP_PP}, (
        "obsolescence must take exactly two values -- zero and the step. A third value means a "
        "ramp has crept back in, and a ramp is the thing that was deleted.")
    assert all(e[h + 1] >= e[h] - 1e-12 for h in TERMINAL_GRID[:-1]), "step must be non-decreasing"
    say("  region3: FLAT -- exactly {0, step}, switches just past the year, never rises again")

    # THE BOND OVERRIDE IS ONE-DIRECTIONAL. This is the guarantee that matters most, so it is
    # asserted over a range rather than at one convenient point.
    bonds = [dict(maturity="2126-02-13", outstanding=1e9, description="99y", cusip="X"),
             dict(maturity="2093-07-29", outstanding=96e6, description="stub", cusip="Y")]
    for dy in (5, 20, 40, 80, 200):
        eff, gov = governing_obsolescence_year(dy, bonds, asof="2026-08-18")
        assert eff >= dy - 1e-9, "the bond override pulled the year EARLIER at declared=%r" % dy
    say("  bond override: never advances the year, at any declared horizon")

    # THE SIZE THRESHOLD. The $96m stub must not be able to govern; the $1bn bond must.
    eff, gov = governing_obsolescence_year(40, bonds, asof="2026-08-18")
    assert gov is not None and gov["maturity"] == "2126-02-13", (
        "the $96m stub governed the date -- the size threshold is not binding, which is the "
        "defect that would move a $300bn company's valuation by thirty years")
    assert abs(eff - 99.5) < 1.0, "governing year should be ~99.5y out; got %r" % eff
    stub_only = [b for b in bonds if b["outstanding"] < BOND_SIZE_THRESHOLD_USD]
    eff2, gov2 = governing_obsolescence_year(40, stub_only, asof="2026-08-18")
    assert eff2 == 40 and gov2 is None, "a sub-threshold bond must leave the declared year alone"
    say("  bond override: $1bn bond governs, $96m stub cannot; declared year stands when silent")

    # THE GRID GUARD, RESTATED FOR THE NEW DESIGN. Region 3 is identically zero whenever the
    # effective year sits at or past the end of the grid. That is no longer a property of fixed
    # presets -- it now depends on the DECLARED year, so it cannot be asserted once and forgotten.
    # It is asserted as a DETECTION rule instead: computing the wedge on a grid that ends at or
    # before the effective year yields exactly zero, and that zero must never be read as evidence.
    z = region3(40, grid=GRID)
    assert max(z.values()) == 0.0, "a year-40 declaration must be invisible on a 1..30 grid"
    assert obsolescence_is_visible(40, GRID) is False
    assert obsolescence_is_visible(40, TERMINAL_GRID) is True
    say("  region3 GRID GUARD: a declaration past the end of the grid is identically zero; "
        "obsolescence_is_visible() detects it rather than letting the zero pass as a result")

    # T10, correctly scoped: the INCREMENT is monotone where it should be, the TOTAL need not be
    idio, _tot = build_curve(2.0, zero_common(), e, {h: 3.0 for h in GRID})
    assert idio[1] > idio[5], "a positive front differential must decay"
    say("  T10 scoping: monotonicity is asserted on the increment, never on the total")

    # THE NEW T4 IDENTITY, ON A TOY UNIVERSE. Proven, not asserted: the cap-weighted average
    # must equal market + Mc x COMMON + average obsolescence, at every tenor.
    mkt3 = {h: 3.0 for h in GRID}
    inc3 = {"A": -0.5, "B": 1.5}                       # cap-weighted mean zero at 3:1
    r3_all = {"A": region3(10, grid=GRID), "B": region3(20, grid=GRID)}
    ok, worst, wh = t4_identity(inc3, r2, r3_all, cap, mkt3, common)
    assert ok, "T4 identity broken by %.3e pp at tenor %r" % (worst, wh)
    say("  T4 identity: capw avg = market + Mc x COMMON + avg obsolescence, worst error %.2e pp"
        % worst)

    # INFLUENCE. The standing suspicion is a term that is arithmetically perfect and inert.
    ok_i, det = influence_check(inc3, w, cap, mkt3, r3_all, grid=GRID)
    assert ok_i, "COMMON(t) is INERT: %r" % (det,)
    say("  influence: +%.2fpp on COMMON moves the collapsed universe ERP by %.4fpp and every "
        "single name by %.4fpp" % (det["bump_pp"], det["universe_move_pp"], det["min_name_move_pp"]))
    return True


# ------------------------------------------------------------------ (8b) the influence guard

def influence_check(inc, widen_by_ticker, cap, market_erp_curve, r3_all=None, grid=None,
                    bump_pp=0.10, growth=2.0, min_move_pp=1e-4):
    """PERTURB COMMON(t) AND DEMAND THAT A PUBLISHED NUMBER MOVES.

    WHY THIS EXISTS AND WHY IT IS NOT A UNIT TEST. Twice in the last session this engine landed
    a term that was arithmetically correct and completely inert -- a volatility term structure
    that was never adopted, and a seed reported as live while nothing read it. Every identity
    check passed both times, because an inert term is internally consistent. Identity checks
    cannot see influence; only a perturbation can.

    Region 2 is the same shape of risk. It has been ZERO for 490 of 499 names, and no test in
    this module could have detected that, because zero is a perfectly consistent value.

    The check: raise COMMON(t) by `bump_pp` at every tenor past the front, and require BOTH
      (a) the collapsed cap-weighted universe ERP to move, and
      (b) EVERY individual company's collapsed ERP to move -- not just the ones with bonds,
          which is the specific failure this whole workstream exists to fix.

    Returns (ok, detail). Callers should assert on `ok` rather than reading the detail.
    """
    grid = grid or GRID
    r3_all = r3_all or {}
    base_c = zero_common(grid)
    bump_c = {h: (0.0 if h == FRONT_TENOR else float(bump_pp)) for h in grid}

    def _run(common):
        r2, _ = region2({t: widen_by_ticker.get(t) for t in inc}, cap, common, grid)
        per = {}
        for t in inc:
            _idio, erp_i = build_curve(inc[t], r2.get(t, {}), r3_all.get(t, {}),
                                       market_erp_curve, grid)
            per[t] = collapse_rate(grid, [erp_i[h] for h in grid], growth=growth)
        u = universe_wedge(inc, r2, r3_all, cap, market_erp_curve, grid, growth=growth)
        return per, u["collapsed_universe_erp"]

    per0, u0 = _run(base_c)
    per1, u1 = _run(bump_c)
    moves = {t: abs(per1[t] - per0[t]) for t in per0}
    detail = dict(bump_pp=float(bump_pp), universe_move_pp=u1 - u0,
                  min_name_move_pp=min(moves.values()) if moves else 0.0,
                  max_name_move_pp=max(moves.values()) if moves else 0.0,
                  inert_names=sorted(t for t, m in moves.items() if m < min_move_pp))
    ok = (abs(detail["universe_move_pp"]) >= min_move_pp and not detail["inert_names"])
    return ok, detail


# ------------------------------------------------------------------ (9) run

def main():
    print("idiosyncratic ERP term structure -- reference implementation")
    print()
    print("SELF-TEST")
    selftest()
    print()

    m = mel.fetch_market_erp()
    rows, _ = mel.fetch_forward_curve()
    mkt = {r["tenor"]: r["fwd_erp"] for r in rows}
    mkt_front = mkt[FRONT_TENOR]

    semidev, cap = load_universe()
    inc, diag = front_increments(semidev, cap, mkt_front)
    ok, mval = t4_front_is_an_identity(inc, cap)
    print()
    print("REGION 1 -- front, normalized at tenor %d" % FRONT_TENOR)
    print("  market ERP at the front  : %.4f%%   (collapsed effective was %.4f%%, NOT the target)"
          % (mkt_front, m["eff_erp"]))
    print("  cap-weighted avg semidev : %.4f   coverage %d/%d names"
          % (diag["capw_avg_semidev"], diag["covered"], diag["scored"]))
    print("  T4 AT THE FRONT: cap-weighted mean increment = %.3e -- an IDENTITY, %s" %
          (mval, "retired as evidence" if ok else "BROKEN"))

    # Region 2 for EVERY name. Primary: the per-issuer fits over each company's own bonds.
    widen, wmeta = load_issuer_widen()
    if widen is None:
        print("  ** no fitted issuer curves (%s)" % wmeta)
        print("  ** falling back to the retired nine rating-shaped cod_<T> curves. Those are the")
        print("  ** aggregate IG shape scaled by one number each, NOT issuer shapes.")
        widen = {}
        for t in ["AAPL", "HD", "JNJ", "KO", "MRK", "PEP", "T", "WMT"]:
            c = mel.fetch_issuer_credit(t)
            if c and c["has_real_fit"]:
                widen[t] = widening(c["spread_pct"])
    else:
        widen = {t: widen[t] for t in semidev if t in widen}
    cred = mel.fetch_market_credit(log=print)
    common = common_widening(cred["spread_pct"])
    r2, mean_w = region2({t: widen.get(t) for t in semidev}, cap, common)
    print()
    tc = (wmeta or {}).get("tier_counts") if isinstance(wmeta, dict) else None
    print("REGION 2 -- COMMON(t) for everyone + the de-meaned differential over %d curves%s"
          % (len(widen), ("   tiers %s" % tc) if tc else ""))
    print("  COMMON(t), aggregate IG widening   1y %.4f  10y %.4f  30y %.4f (pp)   [%s, %s]"
          % (common[1], common[10], common[30], cred["source"], cred["vintage"] or "no vintage"))
    print("  x%.1f -> EVERY name now carries a credit term structure. Before 2026-08-19, 490 of"
          % M_COMMON)
    print("     499 carried exactly zero. Tier 1 is the issuer's OWN fitted shape; tiers 2-4 take")
    print("     the cross-sectional slope, which is a declared fallback and not a per-name fit.")
    print("  cap-weighted mean differential widening   1y %.4f  10y %.4f  30y %.4f (pp)"
          % (mean_w[1], mean_w[10], mean_w[30]))
    print("  x%.1f -> de-meaned, so relative ranking between companies is unchanged"
          % M_PASSTHROUGH)

    ok_i, det = influence_check(inc, widen, cap, mkt, grid=GRID)
    print("  INFLUENCE GUARD: +%.2fpp on COMMON moves the collapsed universe ERP by %+.4fpp; "
          "%s" % (det["bump_pp"], det["universe_move_pp"],
                  "no name is inert" if ok_i else "INERT NAMES: %s" % det["inert_names"][:8]))
    if not ok_i:
        raise SystemExit("COMMON(t) is inert -- refusing to report a term that moves nothing")

    print()
    print("REGION 3 -- OBSOLESCENCE. Rebuilt 2026-08-18: one declared year, one flat step, and")
    print("  a one-directional bond-maturity override. The elevator, the durability categories")
    print("  and the rating-based ramp are DELETED.")
    print()
    print("  THE RATING DEFECT NO LONGER MATTERS, and that is the main practical gain. The old")
    print("  elevator boarded on a credit-rating field that is defaulted rather than sourced --")
    print("  7 of the 11 names with a real bond fit read BBB, including AA-band issuers. Nothing")
    print("  in the new construction reads that field, so the defect can be recorded and closed")
    print("  rather than fixed. Same for the five fake credit curves and the thirty names")
    print("  missing size data: none of them can corrupt an obsolescence premium now.")
    print()
    print("  THE BOND OVERRIDE, ON REAL NAMES. Longest bond at or above $%.0fm outstanding:"
          % (BOND_SIZE_THRESHOLD_USD / 1e6))
    for tkr in ("GOOG", "AAPL", "KO", "MSFT", "T"):
        bl = load_bonds(tkr)
        if not bl:
            print("    %-5s no bond file -- NO OVERRIDE, the declared year would stand" % tkr)
            continue
        eff, gov = governing_obsolescence_year(40, bl)
        if gov is None:
            print("    %-5s declared year 40 stands; no qualifying bond matures past it" % tkr)
        else:
            print("    %-5s declared 40 -> %.1f  governed by %s ($%.0fm)  [+%.1f years]"
                  % (tkr, eff, gov["maturity"], gov["outstanding"] / 1e6,
                     gov["postponed_by_years"]))
    kob = load_bonds("KO")
    if kob:
        longest = max(kob, key=lambda b: b["maturity"])
        print("    THE THRESHOLD EARNS ITS KEEP: KO's single longest bond matures %s with only"
              % longest["maturity"])
        print("    $%.0fm outstanding. Without the size threshold that stub would govern."
              % (longest["outstanding"] / 1e6))
    print()
    print("  HOW MUCH A SHELF IS WORTH ON A COLLAPSED RATE. Grid 1..%d, market ERP held flat"
          % TERMINAL_GRID[-1])
    print("  past year 30 (an assumption, declared, used only here and never for a discount")
    print("  rate). Rows are the declared year, columns the step size in pp.")
    mkt_long = extend_market_erp(mkt)
    steps = (0.5, 1.0, 1.5, 2.0)
    sens = wedge_sensitivity(mkt_long, declared_years=(20, 30, 40, 50), steps=steps)
    base = sens.pop(("_base_collapsed_market", ""))
    print()
    print("    collapsed market ERP over 1..%d = %.4f%%" % (TERMINAL_GRID[-1], base))
    print("    %-8s %s" % ("year", " ".join("%-9s" % ("step %.1f" % s) for s in steps)))
    for y in (20, 30, 40, 50):
        cells = []
        for s in steps:
            v = sens[(y, s)]
            cells.append("%-9s" % ("n/a" if v is None else "%.4f" % v))
        print("    %-8d %s" % (y, " ".join(cells)))
    print()
    print("    Read the column for the step you are using, not the whole table. At the")
    print("    provisional 1.0 the shelf is worth well under a point on the collapsed rate even")
    print("    when it starts at year 20, because the collapse weights the near tenors most.")
    print("    THE STEP, CALIBRATED 2026-08-19: measured range %.2f to %.2f pp; shipping %.2f,"
          % (OBSOLESCENCE_STEP_MEASURED_RANGE_PP[0], OBSOLESCENCE_STEP_MEASURED_RANGE_PP[1],
             OBSOLESCENCE_STEP_PP))
    print("    which is the BOTTOM of that range. The remaining uncertainty points UPWARD.")
    print("    See tools/obsolescence_step_calibration.py for the cause split it came from.")
    print()
    print("Nothing above is wired. No company figure produced here may be quoted.")


# DELETED 2026-08-18: _fetch_credit_grid(). Same reason as extend_credit_grid() -- it fetched the
# market credit grid purely so the elevator could board on it. Region 2 reads ISSUER curves via
# market_erp_live.fetch_issuer_credit() and is untouched by this.


if __name__ == "__main__":
    main()
