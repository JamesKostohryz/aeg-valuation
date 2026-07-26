"""
synthetic_rating.py — zero-touch credit rating for ANY ticker, from its OWN fundamentals.
The cost-of-debt analog of the generalized-COE universal-K: derive the rating from a primitive
available for every company (interest coverage) instead of a spotty external rating lookup.

rating -> the cod curve column real_cod_<rating> (AAA..CCC). Priority ladder the caller should use:
  1. issuer's own bonds (modal S&P rating + fit_offset)         -> cod_source=issuer_bonds   GREEN
  2. a published issuer credit rating, if present (EODHD/map)   -> cod_source=published       GREEN
  3. THIS synthetic coverage rating                             -> cod_source=synthetic       AMBER
Never silently defaults to BBB.

Inputs are the fundamentals EXEC already pulls for company_<T>.csv (EBIT + interest expense; and
total debt to catch the de-minimis-debt case). Coarse large-cap interest-coverage table (Damodaran-
style), mapped to the curve's buckets. Calibration is a starting point; refine with size/sector later.
"""
# interest-coverage (EBIT / interest expense) -> coarse rating bucket matching the cod curve
_ICR_TABLE = [ (8.5,"AAA"), (6.5,"AA"), (4.25,"A"), (3.0,"BBB"), (2.25,"BB"), (1.25,"B") ]  # else CCC

def synthetic_rating(ebit, interest_expense, total_debt=None, assets=None):
    """Return (rating, meta). meta: coverage, source='synthetic', flags[]."""
    flags=[]
    debt = abs(total_debt) if total_debt is not None else None
    # de-minimis debt -> cost of debt is ~ the risk-free; no meaningful spread
    if (interest_expense is None or abs(interest_expense) < 1e-9) or (debt is not None and debt < 1e-9) \
       or (debt is not None and assets not in (None,0) and debt/assets < 0.05):
        return "AAA", {"coverage": float("inf"), "source":"synthetic", "flags":["de_minimis_debt"]}
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
