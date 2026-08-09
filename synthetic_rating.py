"""
synthetic_rating.py — zero-touch credit rating for ANY ticker, from its OWN fundamentals.
The cost-of-debt analog of the generalized-COE universal-K: derive the rating from a primitive
available for every company (interest coverage) instead of a spotty external rating lookup.

rating -> the cod curve column real_cod_<rating> (AAA..CCC). Priority ladder the caller should use:
  1. issuer's own bonds (modal S&P rating + fit_offset)         -> cod_source=issuer_bonds   GREEN
  2. a published issuer credit rating, if present (EODHD/map)   -> cod_source=published       GREEN
  3. THIS synthetic coverage rating                             -> cod_source=synthetic       AMBER
Never silently defaults to BBB, and never awards a rating built on an absent input.

Inputs are the fundamentals EXEC already pulls for company_<T>.csv (EBIT + interest expense; and
total debt to catch the de-minimis-debt case). Coarse large-cap interest-coverage table (Damodaran-
style), mapped to the curve's buckets. Calibration is a starting point; refine with size/sector later.

DE MINIMIS IS A FACT ABOUT THE DEBT (fixed 2026-08-09, defect 1 of the article-12 work order).
This module previously treated a missing or zero interest expense as one of three ALTERNATIVE
grounds for the de-minimis short-circuit, so an empty interest-expense field alone was sufficient
to return AAA carrying the flag "de_minimis_debt" — asserting a finding about the debt that had
never been checked. Fed Apple's committed FY2025 figures (total debt $119,059m against $364,980m
of assets, interest expense reading zero) the function returned AAA, coverage=inf, de_minimis_debt.
Because AAA is the cheapest row of the credit curve and that row becomes real_cod in the financing
leg of the valuation, the error ran in one direction only: it understated the cost of debt and
overstated value, by roughly 73bp at the ten-year tenor against BBB and by roughly 1,300bp against
CCC. The de-minimis test now requires that the DEBT be small. A missing or zero interest expense in
the presence of material — or unknown — debt is a data gap, and this module raises rather than
resolve a gap into a rating. Fail-loud matches build_cockpit.set_cost_of_debt, which already
raises rather than fabricate a rate from a zero interest expense.
"""
# interest-coverage (EBIT / interest expense) -> coarse rating bucket matching the cod curve
_ICR_TABLE = [ (8.5,"AAA"), (6.5,"AA"), (4.25,"A"), (3.0,"BBB"), (2.25,"BB"), (1.25,"B") ]  # else CCC

# de-minimis debt threshold: debt below this share of assets carries no meaningful credit spread
_DE_MINIMIS_DEBT_TO_ASSETS = 0.05


class SyntheticRatingError(ValueError):
    """A rating cannot be derived because a required input is absent. Subclasses ValueError so
    the existing `except ValueError` convention in cod_fallback/run_company still catches it."""


def synthetic_rating(ebit, interest_expense, total_debt=None, assets=None):
    """Return (rating, meta). meta: coverage, source='synthetic', flags[].

    Raises SyntheticRatingError when the interest expense is missing or zero and the debt is
    NOT established as de minimis — that is a hole in the data, not a credit finding, and a
    fabricated rating flows straight into the financing leg of the valuation.
    """
    flags=[]
    debt = abs(total_debt) if total_debt is not None else None
    # --- de-minimis debt -> cost of debt is ~ the risk-free; no meaningful spread.
    # This is a test on the DEBT only. A missing interest expense is NOT evidence of it.
    de_minimis = (debt is not None and debt < 1e-9) or \
                 (debt is not None and assets not in (None,0)
                  and debt/abs(float(assets)) < _DE_MINIMIS_DEBT_TO_ASSETS)
    if de_minimis:
        return "AAA", {"coverage": float("inf"), "source":"synthetic", "flags":["de_minimis_debt"]}
    # --- interest expense absent, and the debt is material or unknown -> DATA GAP, fail loud.
    if interest_expense is None or abs(interest_expense) < 1e-9:
        if debt is None:
            raise SyntheticRatingError(
                "synthetic_rating: interest expense is missing or zero and total debt is unknown, "
                "so de-minimis debt cannot be established. Refusing to synthesize a rating from an "
                "absent input. Supply total_debt (and assets), or resolve the cost of debt from the "
                "issuer's bonds or a published rating.")
        raise SyntheticRatingError(
            f"synthetic_rating: interest expense is missing or zero while total debt is material "
            f"(debt={debt:,.0f}"
            + (f", debt/assets={debt/abs(float(assets)):.3f}" if assets not in (None,0) else "")
            + "). This is a data gap, not de-minimis debt. Refusing to synthesize a rating from an "
              "absent input — supply the interest expense (a committed analyst override in "
              "companies/<TICKER>.yaml is acceptable), or resolve the cost of debt from the "
              "issuer's bonds or a published rating.")
    if ebit is None:
        return "BBB", {"coverage": None, "source":"synthetic", "flags":["ebit_missing_default_BBB"]}
    icr = float(ebit)/abs(float(interest_expense))
    if ebit < 0 or icr < 0:                      # loss-making: distress floor, do not award IG
        return "CCC", {"coverage": round(icr,2), "source":"synthetic", "flags":["negative_ebit_distress_floor"]}
    rating="CCC"
    for thr,r in _ICR_TABLE:
        if icr >= thr: rating=r; break
    # guardrail: a synthetic AAA is rare — flag for review but keep (curve still prices it sensibly)
    if rating=="AAA": flags.append("synthetic_AAA_review")
    return rating, {"coverage": round(icr,2), "source":"synthetic", "flags":flags}

if __name__=="__main__":
    tests=[("hi-cov",120e9,3e9,120e9,400e9),("mid",8e9,2e9,60e9,300e9),("lo",3e9,2.2e9,90e9,200e9),
           ("weak",1.0e9,1.5e9,40e9,80e9),("loss",-2e9,3e9,50e9,100e9),("nodebt",50e9,0,0,300e9)]
    for nm,e,i,d,a in tests:
        r,m=synthetic_rating(e,i,d,a); print(f"{nm:8s} EBIT={e/1e9:+.0f}bn int={i/1e9:.1f}bn -> {r:4s}  cov={m['coverage']}  {m['flags']}")
    # the defect this module was fixed for: material debt, no interest figure -> loud, not AAA
    for nm,e,i,d,a in [("AAPL-gap",127e9,0.0,119.059e9,364.98e9),("gap-nodebtinfo",50e9,0.0,None,None)]:
        try:
            r,m=synthetic_rating(e,i,d,a); print(f"{nm:8s} -> {r} {m}   <-- REGRESSION: should have raised")
        except SyntheticRatingError as ex:
            print(f"{nm:8s} raised SyntheticRatingError as designed: {str(ex)[:88]}...")
