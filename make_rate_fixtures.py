#!/usr/bin/env python3
"""Generate offline fixtures matching the LOCKED rate CSV contract, so rate_feed.py
can be unit-tested without hitting the live repo (whose per-company emitters the
rate chat has not finished wiring). Values are realistic annual decimals; the
coe_ fixture satisfies the exact-additive decomposition to machine precision."""
import os

OUT = os.path.join(os.path.dirname(__file__), "rate_fixtures")
os.makedirs(OUT, exist_ok=True)
N = 30
TEN = range(1, N + 1)


def _w(fname, header, rows):
    with open(os.path.join(OUT, fname), "w", newline="") as fh:
        fh.write(",".join(header) + "\n")
        for r in rows:
            fh.write(",".join(str(x) for x in r) + "\n")


# ---- global curve: real (TIPS), forward, expected inflation, breakeven -------
# smooth, monotone-ish term structures in annual decimals
def curve_val(t, a, b, hl):
    # a at t=1 rising toward b with horizon-decay half-life hl
    return round(a + (b - a) * (1 - 0.5 ** (t / hl)), 6)

real_spot = {t: curve_val(t, 0.0103, 0.0205, 8) for t in TEN}
inf_spot = {t: curve_val(t, 0.0300, 0.0235, 6) for t in TEN}      # expected inflation (Cleveland-style)
be_spot = {t: curve_val(t, 0.0300, 0.0250, 6) for t in TEN}       # breakeven (incl infl risk prem), >= exp infl

def fwd(spot):  # 1yr-forward from a spot term structure, annual compounding
    f = {}
    for t in TEN:
        if t == 1:
            f[t] = spot[1]
        else:
            f[t] = round((1 + spot[t]) ** t / (1 + spot[t - 1]) ** (t - 1) - 1, 6)
    return f

real_fwd = fwd(real_spot); inf_fwd = fwd(inf_spot); be_fwd = fwd(be_spot)

# NOTE: the live curve file also carries two EXTRA trailing columns (nominal, nominal_fwd1y)
# beyond our contract list. Our by-name reader ignores them; the fixture includes them so the
# test proves extra columns are tolerated (no strict column-count assertion).
nom_spot = {t: round((1 + real_spot[t]) * (1 + be_spot[t]) - 1, 6) for t in TEN}
nom_fwd = {t: round((1 + real_fwd[t]) * (1 + be_fwd[t]) - 1, 6) for t in TEN}
_w("curve_latest_annual.csv",
   ["tenor", "real", "real_fwd1y", "exp_inflation", "exp_inflation_fwd1y",
    "breakeven", "breakeven_fwd1y", "nominal", "nominal_fwd1y"],
   [[t, real_spot[t], real_fwd[t], inf_spot[t], inf_fwd[t], be_spot[t], be_fwd[t],
     nom_spot[t], nom_fwd[t]] for t in TEN])

# ---- global market ERP term structure (decays toward corp-bond risk premium) --
mkt_erp = {t: curve_val(t, 0.0520, 0.0410, 10) for t in TEN}
_w("erp_market_latest_annual.csv", ["tenor", "market_erp"],
   [[t, mkt_erp[t]] for t in TEN])

# ---- per-company COE components (AAPL), exact-additive to machine precision ----
# base real_rf == the global real forward (that is what the engine adds ERP onto)
cr = {t: round(0.0035 * 0.5 ** (t / 20), 8) for t in TEN}     # credit_relative (Merton, small for AAPL)
idio = {t: round(0.0120 * 0.5 ** (t / 15), 8) for t in TEN}   # idiosyncratic (option-implied)
coe_rows = []
for t in TEN:
    rf = real_fwd[t]; erp = mkt_erp[t]
    real_coe = rf + erp + cr[t] + idio[t]        # define total as the exact sum
    company_erp = real_coe - rf                  # assembled ERP = total - rf
    coe_rows.append([t, rf, erp, cr[t], idio[t], round(company_erp, 8), round(real_coe, 8)])
_w("coe_AAPL_annual.csv",
   ["tenor", "real_rf", "market_erp", "credit_relative", "idiosyncratic",
    "company_erp", "real_coe"], coe_rows)

# ---- per-company REAL cost of debt (AAPL) -------------------------------------
cod_rows = []
for t in TEN:
    real_cod = round(real_fwd[t] + 0.0075 + 0.0004 * t / 30, 6)  # real fwd + credit spread
    spread = round(0.0075 + 0.0004 * t / 30, 6)
    cod_rows.append([t, real_cod, spread, "AA+", 0.92, round(real_cod / 0.92, 6)])
_w("cod_AAPL_annual.csv",
   ["tenor", "real_cod", "spread", "rating", "offset", "real_cod_AA+"], cod_rows)

# ---- per-company scalars ------------------------------------------------------
_w("company_AAPL.csv", ["field", "value"], [
    ["market_value_of_debt", 98650.0],
    ["portfolio_ytm", 0.0488],
    ["wavg_mod_duration", 7.9],
    ["wavg_coupon", 0.0355],
    ["wavg_years", 9.4],
])

# ---- AT&T (T): mirrors the REAL contract the rate team confirmed --------------
#   * idiosyncratic MEASURED (Martin-Wagner) -> legitimately NEGATIVE at long tenors
#     for a lower-than-average-vol name; exercises the widened (-0.05) floor.
#   * cost of debt rating = BBB (dynamic real_cod_BBB column).
#   * market_value_of_debt in ABSOLUTE USD (not millions): 116,047,846,974.
cr_t = {t: round(0.0060 * 0.5 ** (t / 25), 8) for t in TEN}      # higher Merton credit (BBB, levered)
idio_t = {t: round(0.0060 - 0.0009 * t, 8) for t in TEN}         # starts +, goes negative past ~t7
coe_t_rows = []
for t in TEN:
    rf = real_fwd[t]; erp = mkt_erp[t]
    real_coe = rf + erp + cr_t[t] + idio_t[t]
    coe_t_rows.append([t, rf, erp, cr_t[t], idio_t[t], round(real_coe - rf, 8), round(real_coe, 8)])
_w("coe_T_annual.csv",
   ["tenor", "real_rf", "market_erp", "credit_relative", "idiosyncratic",
    "company_erp", "real_coe"], coe_t_rows)

cod_t_rows = []
for t in TEN:
    real_cod = round(real_fwd[t] + 0.0150 + 0.0006 * t / 30, 6)   # BBB spread, wider than AAPL
    spread = round(0.0150 + 0.0006 * t / 30, 6)
    cod_t_rows.append([t, real_cod, spread, "BBB", 1.0, round(real_cod / 1.0, 6)])
_w("cod_T_annual.csv",
   ["tenor", "real_cod", "spread", "rating", "offset", "real_cod_BBB"], cod_t_rows)

_w("company_T.csv", ["field", "value"], [
    ["market_value_of_debt", 116047846974],   # absolute USD, per the rate team
    ["portfolio_ytm", 0.0593],
    ["wavg_mod_duration", 8.4],
    ["wavg_coupon", 0.0410],
    ["wavg_years", 12.1],
])

print(f"fixtures written to {OUT}")
for f in sorted(os.listdir(OUT)):
    print("  ", f)
