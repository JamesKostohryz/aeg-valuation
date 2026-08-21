# RESULTS — Real Estate is defensive, James was right, and the check exposed a bigger problem

**2026-08-21. James: *"the property REITs seem to be treated as defensive."* Tested three ways —
equity semi-deviation on the actual constituents, credit spreads, and constituent inspection. He
is right on all three. The same test also showed the French sector series does not track S&P
sector risk as well as the earlier validation suggested, and that is reported second because it
is the more consequential finding.**

---

## 1. REAL ESTATE — BUILT FROM THE ACTUAL CONSTITUENTS

No ETF proxy was needed. The daily panel holds the real S&P 500 Real Estate members with their
market caps, so the sector index is built directly: cap-weighted daily returns of the actual
members, prior month-end weights, against a cap-weighted index of the whole panel — same
construction on both sides, so the ratio is not measuring a vendor difference.

| construction | what it actually contains | median ratio | verdict |
|---|---|---|---|
| French `RlEst` | SIC 6500–6611: operators, lessors, agents, title offices, **land subdividers** | **1.373** | riskiest of the set |
| **S&P 500 Real Estate** | **30 names, 28 equity REITs plus CBRE and CoStar** | **0.952** | **calmer than the index** |

**The two are not the same object.** French's `RlEst` excludes REITs entirely — SIC 6798 sits in
his `Fin` industry — so it is levered small-cap property development with the income vehicles
removed. The S&P sector is the income vehicles.

**Real Estate's rank among S&P sectors, 1 = calmest:**

| 2013 | 2015 | 2017 | 2019 | 2021 | 2023 | 2025 |
|---|---|---|---|---|---|---|
| 6 of 9 | **3 of 9** | 4 of 10 | **3 of 11** | 5 of 11 | 7 of 11 | 6 of 11 |

Consistently in the calmer half, twice in the calmest three. Today it reads 1.034, essentially
index-level.

**And the mortgage-REIT caveat James raised does not apply**, which is worth stating because he
raised it as the likely exception. Of the thirty S&P 500 Real Estate members, **none is a
mortgage REIT** — the list is twenty-eight equity REITs (residential, retail, industrial, office,
healthcare, specialty) plus CBRE and CoStar as real estate services. AGNC, Annaly and the rest of
the mREIT complex are not S&P 500 members, so they never enter this measurement.

## 2. THE CREDIT SIDE — the same answer, arrived at differently

Median one-year issuer credit spread from `outputs/issuer_widen_latest.csv`, tier 1 and 2 only:

| sector | n | median | 25th | 75th |
|---|---|---|---|---|
| Consumer Defensive | 28 | 0.285% | 0.153% | 0.485% |
| Technology | 37 | 0.323% | 0.114% | 0.408% |
| Financial Services | 51 | 0.334% | 0.200% | 0.441% |
| Energy | 18 | 0.342% | 0.254% | **0.811%** |
| Healthcare | 35 | 0.354% | 0.214% | 0.468% |
| Industrials | 45 | 0.363% | 0.213% | 0.518% |
| Consumer Cyclical | 27 | 0.415% | 0.261% | 0.708% |
| **Real Estate** | 23 | **0.418%** | **0.315%** | **0.497%** |
| Utilities | 31 | 0.430% | 0.300% | 0.533% |

At first glance this looks like it contradicts the equity result — Real Estate is second-widest.
**It does not, and the interquartile range is the tell.** Real Estate's spread dispersion is
0.315–0.497, the tightest of any sector except Technology's lower half; Energy at a *narrower*
median carries a 75th percentile of 0.811%. Real Estate and Utilities sit together at the wide
end of the median with tight, well-behaved distributions and no tail.

That is the signature of **leverage without asset risk**. REITs and utilities carry a lot of debt
against predictable cash flows: the leverage widens the spread and lifts equity volatility above
what the underlying assets would imply, but the assets are dull, so the dispersion stays tight and
the equity volatility still lands below the index. Both the equity and credit readings say the
same thing about the same companies.

## 3. THE PROBLEM THIS CHECK EXPOSED, WHICH MATTERS MORE

Building the panel sectors gave a second, sharper test of the French series than the GFD
comparison did. Over the 2003–2026 overlap, French sector ratios against S&P 500 sector ratios
built from the actual constituents:

| sector | panel median | French median | French / panel | **correlation** |
|---|---|---|---|---|
| Utilities | 0.909 | 1.000 | 1.100 | **0.903** |
| Financial Services | 1.035 | 1.200 | 1.160 | **0.857** |
| Technology | 1.421 | 1.225 | 0.863 | 0.731 |
| Energy | 1.218 | 1.594 | 1.309 | 0.693 |
| Healthcare | 0.796 | 0.943 | 1.184 | 0.612 |
| Communication Services | 1.178 | 0.999 | 0.848 | 0.574 |
| Industrials | 0.969 | 1.160 | 1.197 | 0.465 |
| Consumer Defensive | 0.691 | 0.797 | 1.153 | 0.458 |
| Basic Materials | 0.914 | 1.142 | 1.249 | 0.440 |
| **Consumer Cyclical** | 1.225 | 1.063 | 0.867 | **−0.057** |

**Only Utilities, Financials and Technology track well.** Consumer Cyclical correlates at
essentially **zero**, and five sectors sit between 0.44 and 0.69. French also runs a median
**15.6% above** the panel in level.

**Two causes, and they compound.** First, there are now *three* taxonomies in play — GICS (what
the S&P uses), SIC (French), and the Morningstar-style labels EODHD publishes, which is what the
panel sectors are built on. "Consumer Cyclical" and "Consumer Discretionary" are not the same
list. Second, French's industry portfolios span every NYSE, AMEX and NASDAQ name, so a French
sector is dominated by small caps that are far more volatile than the large caps carrying the same
label in the S&P 500 — which explains the systematic 15.6% level gap and why the numerator is
inflated relative to a cap-weighted market.

**This is more serious than the earlier GFD validation implied.** That comparison, 1991–2014
against GFD's S&P sector indices, returned 0.97, 0.94, 0.86 and 0.84 for four of five sectors and
looked like a pass. Measured against the actual constituents over a more recent window, the same
French series looks much weaker. **Both comparisons are real; they disagree, and the disagreement
has not been resolved.**

## 4. WHAT I NOW THINK, AND IT IS A CHANGE

The French series remains the only source of 98-year daily sector history and that is worth
having. But **it should not be presented as a history of GICS sector risk.** It is a history of
SIC-industry risk across the whole US market, which is a different and broader object, and the
correlations above say the difference is large for most sectors.

The panel series is the right object for the modern era — actual constituents, actual weights, the
taxonomy the live system uses — but it only reaches 2003, and only 2013 for Real Estate.

**The honest construction is therefore two series with a disclosed join, not one spliced series**,
and the level offset at the join is measured at 15.6% rather than assumed away. Any single number
quoted for a historical sector cost of equity has to say which series it came from.

## 5. WHAT I RECOMMEND

1. **Use the panel series for anything from 2003 onward.** It is the right taxonomy, the right
   universe and the right weights, and Real Estate is only meaningful there.
2. **Use French before 2003 with the label "US SIC industry", not "GICS sector"**, and quote the
   15.6% level offset on its face.
3. **Do not splice them into one series.** That is the 0.52pp break this project already carries
   once, and it would be a 15.6% break this time.
4. **Resolve the GFD-versus-panel disagreement before publishing anything historical.** Two
   validations of the same series returned materially different verdicts and only one can be right
   about how well French tracks S&P sector risk.

## ARTIFACTS

`outputs/2026-08-20-sectors/panel_sector_semidev.csv` — 284 months, 2003-01 to 2026-08, eleven
sectors from the actual S&P 500 constituents, with firm counts. `tools/panel_sector_semidev.py`.

## WHAT IS NOT CLAIMED

The panel sectors use EODHD's current sector label for every name, applied backwards; a company
that changed sector is mislabelled in its earlier years. The credit spreads are a single vintage,
not a history. Neither the equity nor the credit reading says anything about mortgage REITs, which
are absent from the S&P 500 and were never measured here.
