# NOTE — James is right about the anchor, and there is a way to measure it instead of choosing it

**2026-08-20. Written in response to James's challenge. This is a design note, not a result: it
contains one concession, one measurement, and one GATED proposal that has not been built.**

---

## 1. THE CONCESSION

I wrote that normalizing sectors against the average sector "understates every sector's risk
relative to the market, because the average sector gets a zero premium by construction."

James: *"Why do you say that? One can say that the least volatile sector will get 75% of the
market ERP, which will likely put the average sector above the market ERP."*

**He is right and I was wrong.** The zero-mean is a *normalization convention*, not a property of
the world. The current company construction pins the cap-weighted average to exactly the market
premium, and that pinning is a choice — it is the reason `erp.py` was able to delete the anchor
and MARGIN machinery as algebraically inert, because under a cap-weighted normalization any anchor
cancels. Drop the pinning and the anchor stops cancelling and starts mattering. James's
construction is coherent and it produces exactly the behaviour he describes.

---

## 2. WHAT THE ANCHOR ACTUALLY COSTS, WHICH IS THE REAL OBJECTION

Under `ERP_s = A × market_ERP × semidev_s / semidev_min`, the ratios `semidev_s / semidev_min`
are **measured** — they give the ordering and the spacing of the sectors, and they are free from
Global Financial Data back to 1926. `A`, the 75%, is **not measured by anything**. It is a pure
level parameter, it multiplies every sector's premium at every tenor at every date, and nothing in
the sector cross-section can pin it: a cross-section gives relative position, never level.

That is the shape of the failure this project's standing register already names — *"a single
anchor year's rate driving a permanent line… it has twice determined the SIGN of the abnormal
earnings stream."* Not an argument against James's construction, but an argument for measuring `A`
rather than choosing it, if measuring it is possible.

**It is possible, and the data for it is already here.**

---

## 3. THE MEASURED ANCHOR — compare the sector to the MARKET, not to the average sector

```
ERP_s(front) = market_ERP(front) × semidev_TOTAL_s / semidev_TOTAL_market
```

Three properties, none of them chosen:

- **The market's own ratio is exactly 1.0**, so the market carries zero idiosyncratic premium.
  That is correct rather than convenient: `market_ERP` *is* the market's premium, and the market
  should not be charged a premium against itself.
- **Every sector comes out above 1.0 automatically**, because a sector is a less diversified
  portfolio than the index it sits inside. The direction James wanted falls out; it is not
  imposed.
- **The cap-weighted average sector lands above the market by a MEASURED amount** — the
  cross-sector diversification benefit, read off the data at each date rather than set by an
  anchor. `A` disappears entirely.

It is also dimensionally consistent with the market leg. `market_ERP` comes from the Martin
variance bound on the market's **total** risk, so comparing a sector's **total** downside
deviation against the market's total downside deviation is like against like. The market-model
residual is the right object for a single name whose common factor you want stripped; it is not
obviously the right object for a portfolio being compared to another portfolio.

**And it needs no universe, no membership, no cap weights, and no panel.** Two price series: the
sector index and the market. GFD supplies both daily from 1990 and weekly from 1926.

---

## 4. THE SAME IDEA DISSOLVES THE COMPANY PROBLEM — AND THIS PART IS GATED

Applied to a single stock, `ERP_i = market_ERP × semidev_TOTAL_i / semidev_TOTAL_market` needs only
that company's own price history and the market's. **No denominator, no universe, no imputation, no
coverage gate, at any date the stock traded.** Everything this session has been fighting would
stop being a problem.

**It is also a large change to the pricing core and must not be slipped in.** Measured at
2026-08-12, on the same statistic and the same 60-day lag, market total semi-deviation 10.36:

| | residual semidev | total semidev | **total / market** | current `residual / capw` |
|---|---|---|---|---|
| KO | 10.71 | 10.70 | **1.033** | 0.544 |
| JNJ | 11.83 | 11.85 | 1.144 | 0.601 |
| PEP | 13.87 | 13.91 | 1.343 | 0.705 |
| AAPL | 13.29 | 17.43 | 1.683 | 0.675 |
| XOM | 17.30 | 17.73 | 1.711 | 0.879 |
| **MSFT** | 15.84 | 18.33 | **1.770** | **0.805** |
| NVDA | 21.98 | 29.83 | 2.880 | 1.117 |
| TSLA | 31.06 | 38.08 | 3.677 | 1.578 |
| INTC | 39.51 | 45.00 | 4.345 | 2.007 |

**It roughly doubles every premium.** Microsoft's front-tenor equity risk premium would go from
about 3.3pp to about 7.3pp, and its real cost of equity from 6.27% to something near 10%. That
would cut the published $276.30 by a very large fraction. **Nothing here should be built without
James's explicit decision and a four-method tie proved afterwards.**

---

## 5. THE QUESTION UNDERNEATH, STATED PLAINLY

The two constructions are not a technical choice. They embody different answers to *whose* cost of
equity this is.

- **Residual semi-deviation against the cap-weighted average** prices idiosyncratic risk only
  **cross-sectionally**. The average company's idiosyncratic risk is not priced at all — the
  cap-weighted mean premium is exactly zero by construction. It implicitly values for an investor
  who holds the whole index and is compensated only for a name's deviation from typical.
- **Total semi-deviation against the market** prices idiosyncratic risk **fully**. It values for an
  investor holding that one position.

Standard portfolio theory favours the first. **A methodology built for concentrated value
investors arguably wants the second**, and Real Value Analysis is aimed at people making
concentrated bets, not index holders. That is James's call and it is not a small one: it moves
every number the system produces.

A middle option exists and should be on the table — price a stated fraction `λ` of the total
rather than all of it, with `λ = 0` reproducing something close to today's construction and
`λ = 1` the full total-risk view. That reintroduces a chosen parameter, which is what section 2
argues against, so it is a worse answer than either pure case unless `λ` can itself be measured.

---

## 6. A MARKET FACT FOUND WHILE CHECKING THIS, WORTH KNOWING ON ITS OWN

Two-year betas to the S&P 500, measured 2026-08-12:

| | beta | total vol | residual vol |
|---|---|---|---|
| **KO** | **0.025** | 16.30 | 16.29 |
| **JNJ** | **0.019** | 17.89 | 17.89 |
| **PEP** | **0.088** | 20.57 | 20.51 |
| XOM | 0.309 | 23.93 | 23.38 |
| MSFT | 0.919 | 24.75 | 19.51 |
| NVDA | 2.000 | 48.58 | 35.51 |

**Coca-Cola's beta to the index is 0.025 and Johnson & Johnson's is 0.019.** Defensive staples
have decoupled almost completely from an index driven by a handful of names. Two consequences.
The market-model residual and the total volatility are now *the same number* for those companies,
so the choice in section 4 barely affects them and matters almost entirely for high-beta names.
And any construction that leans on beta — for these names, at this moment — is leaning on
approximately nothing.

`tools/constant_denominator_test.py` holds the semi-deviation plumbing; the total-semidev figures
above were computed with `idio/semidev.py`'s own primitives and are reproducible from it.
