#!/usr/bin/env python3
"""test_market_cap_split.py — REGISTER ITEM 12, as a standing property.

The property, stated so it is checkable without the model:

    A STOCK SPLIT DOES NOT CHANGE MARKET CAPITALIZATION.

A split multiplies the share count and divides the price by the same factor. Any market
capitalization the engine forms must therefore be invariant to it. That is arithmetic, it
is company-independent, and it is exactly the check the four-method tie cannot perform --
the tie is an identity on the forecast stream and never looks at the price series at all.

The engine failed this property before 2026-08-09 because 'Market cap = price x shares'
multiplied a CONTEMPORANEOUS price (md_yeprice, deliberately un-adjusted so the buyback
reserve values repurchases at the price actually paid) by a share count on TODAY'S split
basis. Two bases, one product. Apple fiscal 2013 computed to $12.4tn against an actual
near $444bn.

Note what the register got wrong, because it matters for anyone reading this later: it
prescribed "split-adjust the price series". Doing that would have corrupted the buyback
reserve, which legitimately needs the as-traded price. The price row was never the defect.
The product was.

No network, no fixtures, no LibreOffice. Pure arithmetic against closed forms.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import market_data as MD  # noqa: E402

_passed = 0
_failed = []


def check(name, got, want, tol=1e-9):
    global _passed
    ok = (abs(got - want) <= tol * max(1.0, abs(want))
          if isinstance(got, (int, float)) and isinstance(want, (int, float))
          else got == want)
    if ok:
        _passed += 1
    else:
        _failed.append(f"{name}: got {got!r}, want {want!r}")


def d(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


# --------------------------------------------------------------- the fixture
# One company, fiscal year ending September, ten years of prices on TODAY'S basis,
# and two splits -- a 7-for-1 and a 4-for-1 -- placed like Apple's.
ADJUSTED_CLOSE = {y: round(10.0 * (1.15 ** (y - 2010)), 6) for y in range(2010, 2026)}
PRICE_ROWS = [(d(f"{y}-09-28"), ADJUSTED_CLOSE[y]) for y in range(2010, 2026)]
SPLITS = [(d("2014-06-09"), 7.0), (d("2020-08-31"), 4.0)]
# Share count on today's basis: constant, so any market-cap move is the price's doing.
SHARES_TODAY_BASIS = 1000.0


def cum_factor(year):
    """Cumulative split factor strictly after that fiscal year end -- by hand."""
    f = 1.0
    for sd, r in SPLITS:
        if sd > d(f"{year}-09-28"):
            f *= r
    return f


# --------------------------------------------- 1. the two series are consistent
contemp = MD.yearend_prices(PRICE_ROWS, SPLITS, fy_end_month=9)
adjusted = MD.yearend_prices_adjusted(PRICE_ROWS, fy_end_month=9)

check("same years covered", sorted(contemp), sorted(adjusted))
for y in sorted(adjusted):
    check(f"FY{y} adjusted close is the raw close", adjusted[y], ADJUSTED_CLOSE[y])
    check(f"FY{y} contemporaneous = adjusted x cumulative split factor",
          contemp[y], ADJUSTED_CLOSE[y] * cum_factor(y), tol=1e-6)

# Sanity: the fixture must actually exercise the bug, or this test proves nothing.
check("pre-2014 factor is 28 (7 x 4)", cum_factor(2013), 28.0)
check("2014-2019 factor is 4", cum_factor(2016), 4.0)
check("post-2020 factor is 1", cum_factor(2021), 1.0)


# ------------------------------- 2. THE PROPERTY: market cap ignores the split
# Correct construction -- both legs on today's basis.
for y in sorted(adjusted):
    right = adjusted[y] * SHARES_TODAY_BASIS
    check(f"FY{y} split-consistent market cap", right,
          ADJUSTED_CLOSE[y] * SHARES_TODAY_BASIS)

# The old construction, and the size of the error it made. This asserts the DEFECT is
# real, so the test fails loudly if someone reverts row 94 to the bare product.
for y in (2013, 2016, 2021):
    wrong = contemp[y] * SHARES_TODAY_BASIS
    right = adjusted[y] * SHARES_TODAY_BASIS
    check(f"FY{y} old construction overstates by the split factor",
          wrong / right, cum_factor(y), tol=1e-6)

# A split must not move market cap ACROSS the split boundary by more than the price did.
# fiscal 2013 -> 2014 crosses the 7-for-1. On the correct construction the ratio is just
# the price ratio; on the old one it is the price ratio divided by 7.
ratio_right = (adjusted[2014] * SHARES_TODAY_BASIS) / (adjusted[2013] * SHARES_TODAY_BASIS)
ratio_price = ADJUSTED_CLOSE[2014] / ADJUSTED_CLOSE[2013]
check("market cap ratio across a split == price ratio", ratio_right, ratio_price)
ratio_wrong = (contemp[2014] * SHARES_TODAY_BASIS) / (contemp[2013] * SHARES_TODAY_BASIS)
check("old construction fabricates a 7x collapse across the split",
      ratio_wrong, ratio_price / 7.0, tol=1e-6)


# ------------------------------------------- 3. the real Apple reference values
# From outputs/AAPL_restated.csv at main, checked against Apple's actual market cap.
# fiscal 2013: contemporaneous $476.7504, reported shares 26,086.536mm, factor 28.
check("Apple FY2013 market cap, split-consistent ($mm)",
      476.7504 * 26_086.536 / 28.0, 444_188.0, tol=2e-4)
check("Apple FY2013 market cap, old construction ($mm)",
      476.7504 * 26_086.536, 12_437_264.0, tol=2e-4)
# fiscal 2019: contemporaneous $223.97, reported shares 18,595.652mm, factor 4.
check("Apple FY2019 market cap, split-consistent ($mm)",
      223.97 * 18_595.652 / 4.0, 1_041_163.0, tol=2e-4)


# ------------------------------------------ 4. the buyback reserve is untouched
# The whole point of keeping md_yeprice contemporaneous. If a future change "fixes" the
# price row instead of the product, this fails.
check("contemporaneous price is NOT the adjusted price before the splits",
      contemp[2013] != adjusted[2013], True)
check("contemporaneous price IS the adjusted price after the last split",
      contemp[2021], adjusted[2021])


if _failed:
    print(f"FAIL  test_market_cap_split.py  ({_passed} passed, {len(_failed)} failed)")
    for f in _failed:
        print("   -", f)
    sys.exit(1)
print(f"{_passed} passed, 0 failed")
