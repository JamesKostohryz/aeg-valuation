"""
idio/company_curve_v2.py -- one ticker in, the thirty-tenor idiosyncratic premium out, built from
the FOUR-BLOCK v2 score (idio/score_ticker.py) instead of company_curve.py's Region 1/2/3.

THIS IS A REPLACEMENT CANDIDATE, NOT YET WIRED. James, 2026-08-21, already ruled the four-block
score should replace the older approach ("Do not reopen this... The scoring system is the
decision, not a proposal"). What is new here is making that swap real and provably safe: same
call signature as company_curve.build(), so run_company.py's call site needs a small, reviewable
change -- but nothing calls this module yet. GATED, pending the before/after comparison this
build produces and James's explicit sign-off, per the standing project discipline.

THE TERM STRUCTURE, STATED RATHER THAN HIDDEN. The v2 score produces ONE suggested premium
(score_ticker's suggested_idio_erp_pct), calibrated against the market's duration-collapsed
EFFECTIVE ERP -- not a per-tenor curve. company_curve.py's Region 1 faded its premium by a
measured half-life and Region 2 added a roughly-flat credit differential; nothing in the v2 score
build measured an analogous decay shape. THIS MODULE THEREFORE APPLIES THE SAME PREMIUM AT EVERY
TENOR, 1 THROUGH 30, RATHER THAN INVENT A DECAY CURVE WITH NO EVIDENCE BEHIND IT. This is a
disclosed design choice, not a placeholder -- revisit it only with a specific, evidenced reason a
company's idiosyncratic risk should differ by tenor.

THE MARKET ERP VINTAGE. `market_erp_decimal` (the caller's own 30-tenor curve, from
`rate_feed.load_all()`) is accepted for signature compatibility and used ONLY for the sanity-band
context in provenance -- the actual premium is calibrated using `market_erp_live.py`'s live
EFFECTIVE erp fetch, because that is the exact object the snapshot's calibration constant `k` was
fit against (`outputs/idio_universe... cap_weighted_avg_combined_score` vs `eff_erp`, duration
~25). Mixing a per-tenor forward curve into that ratio would use two different definitions of
"the market ERP" on the two sides of the same division. Both objects publish from the same daily
`real-yields` job, so day-to-day they should not disagree by more than the sub-basis-point noise
of two reads seconds apart -- but this is a real, disclosed simplification, not a resolved
question, and it echoes the still-open Martin-bound-vs-Option-B market ERP construction question
(docs/RESULTS-Market-ERP-Reconciliation-2026-08-21.md). Flagged here rather than quietly assumed.

NOT A VALUATION until wired and signed off.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import score_ticker as ST          # noqa: E402
import snapshot_build as SB        # noqa: E402 -- staleness policy (check_staleness, MAX_AGE_DAYS)
from company_curve import PremiumRefused, SANE_MIN_PP, SANE_MAX_PP  # noqa: E402 -- reused, not redefined


def build(ticker: str, market_erp_decimal, *, outdir=None, obs_category=None,
          semidev_override=None, asof=None, log=print) -> dict:
    """Same contract as company_curve.build(): returns {series, provenance}. `obs_category` and
    `asof` are accepted for signature compatibility and unused -- the v2 score has no
    obsolescence region and no historical replay mode yet."""
    t = ticker.strip().upper()
    snap_path = os.path.join(os.path.dirname(_HERE), "outputs", "idio_snapshot_latest.json")
    try:
        snap = ST.load_snapshot(snap_path)
    except FileNotFoundError as e:
        raise PremiumRefused(
            f"the v2 idio snapshot is unusable: {e}\n"
            f"  Run idio/snapshot_build.py --write. Refusing rather than pricing {t} at the "
            f"market rate.")

    try:
        result = ST.score_ticker(t, snap, semidev=semidev_override, log=log)
    except ST.OutOfCoverageError as e:
        raise PremiumRefused(
            f"{t} could not be scored by the v2 system: {e}\n"
            f"  A risk group (and at minimum a semi-deviation) is required for any ticker "
            f"outside the {snap['n_universe']}-name coverage universe -- see "
            f"idio/score_ticker.suggest_group().")

    if result.get("refused"):
        raise PremiumRefused(
            f"{t}: {result.get('reason')} -- fewer than two of the four blocks were available. "
            f"Refusing rather than pricing on a single measure silently.")

    # STALENESS GATE (task 22, 2026-08-21). A cadence promise (semidev/put-IV monthly, credit
    # quarterly) is only real if something checks it was kept -- see snapshot_build.py's own
    # docstring on this. Gated on the legs THIS ticker's score actually used: a ticker with no
    # credit block is unaffected by a stale credit leg; a ticker scored purely on semi-deviation
    # (no options traded) is unaffected by a stale put-IV leg. semidev and credit_spread are
    # FATAL when stale and in use -- both are structural inputs to a published number. put_iv is
    # ADVISORY only: it is explicitly optional per the score's own design (blend adjustment, not
    # a required leg), and idio_live_fetch.py already documents why it cannot be cheaply
    # refreshed for one ticker on demand.
    stale = SB.check_staleness(snap)
    fatal = []
    blocks_used = result.get("blocks", {})
    if "volatility" in blocks_used and stale["semidev"]["stale"]:
        s = stale["semidev"]
        fatal.append("semi-deviation is %s days old (cadence limit %d) -- run idio/feed.py "
                     "(idio_universe.yml)" % (s["age_days"], s["max_age_days"]))
    if "credit" in blocks_used and stale["credit_spread"]["stale"]:
        s = stale["credit_spread"]
        fatal.append("the credit spread leg is %s days old (cadence limit %d) -- run "
                     "idio/bond_reprice.py + idio/issuer_curves.py + idio/credit_block.py "
                     "(idio_credit_quarterly.yml)" % (s["age_days"], s["max_age_days"]))
    if fatal:
        raise PremiumRefused(
            f"{t}: the v2 snapshot is stale on a leg this score depends on -- refusing rather "
            f"than pricing on data past its own promised refresh cadence.\n  "
            + "\n  ".join(fatal)
            + f"\n  Or rebuild the whole snapshot: idio/snapshot_build.py --write.")
    if stale["put_iv"]["stale"] and log:
        s = stale["put_iv"]
        log("[idio-v2] WARNING: put-IV data is %s days old (cadence limit %d) -- advisory "
            "only, not blocking. Run idio_putiv_monthly.yml to refresh."
            % (s["age_days"], s["max_age_days"]))

    premium_pp = result["suggested_idio_erp_pct"]
    if not (SANE_MIN_PP <= premium_pp <= SANE_MAX_PP):
        raise PremiumRefused(
            f"{t}'s v2 premium is {premium_pp:+.3f} percentage points, outside the sanity band "
            f"[{SANE_MIN_PP}, {SANE_MAX_PP}]. This band is a unit/wiring check, not a view on "
            f"the economics. Refusing.")

    series = [premium_pp / 100.0] * 30    # FLAT across tenors -- see module docstring

    prov = dict(
        ticker=t, method="idio_v2_four_block",
        risk_group=result["risk_group"], in_coverage=result["in_coverage"],
        exact_frozen_lookup=result.get("exact", False),
        n_blocks=result["n_blocks"], blocks=result["blocks"],
        combined_score=result["combined_score"],
        market_erp_pct_used=result["market_erp_pct"],
        market_erp_source=result["market_erp_source"],
        market_erp_date=result["market_erp_date"],
        market_erp_age_days=result["market_erp_age_days"],
        calibration_k=result["calibration_k"],
        snapshot_vintage=result["snapshot_vintage"],
        premium_pp_flat=premium_pp,
        floor_applied=result.get("floor_applied", ""),
        reliability=result["reliability"],
        decomposition=result["decomposition"],
        term_structure_note="flat across all 30 tenors -- no decay shape evidenced for the v2 score",
    )
    if log:
        log("[idio-v2] %s premium %+.4f pp, flat 1-30y  (combined score %.2f, group %s, "
            "%d/4 blocks, reliability: %s)"
            % (t, premium_pp, result["combined_score"], result["risk_group"],
               result["n_blocks"], result["reliability"]))
    return dict(series=series, provenance=prov)
