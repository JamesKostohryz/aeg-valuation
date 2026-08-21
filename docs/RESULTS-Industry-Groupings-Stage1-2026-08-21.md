# RESULTS — determining the industries: the vendor taxonomy is too fine, and the fix is two-stage

**2026-08-21, step 1 of the idiosyncratic risk score. The merge criterion was committed as
`e82b60f` before it was run. The result is not the one expected and the reason is worth having.**

---

## 1. WHAT CAME BACK

James's expectation was that many industries would merge because their risk ratings co-move. Run
against the criterion committed in advance — RMS difference between two industries' monthly risk
ratios, clustered within sector, with the threshold expressed as basis points of cost of equity:

| tolerance | groups formed | plus catch-alls |
|---|---|---|
| 10bp | 31 | +11 |
| 25bp | 31 | +11 |
| 50bp | 24 | +11 |
| 100bp | 16 | +11 |

**Merging barely does anything until the tolerance is absurd**, and the reason is the line above
the table: **only 31 of 134 industries could produce a risk series at all.** The other 103 —
77% of the taxonomy — never had six constituent names in sixty months, so they were pooled into
eleven `<Sector> — Other` buckets.

**The problem is the opposite of the one we set out to solve.** It is not that we have too many
measurable industries that should be merged. It is that **most industries are too small to measure
in the first place**, so there is nothing to correlate. EODHD's taxonomy carries **134 industries
across roughly 800 names, a median of four names each**, and 42 of them hold two names or fewer.

**Merging on measured risk distance cannot be step one, because the measurement requires the
merge to have already happened.**

---

## 2. THE FIX — merge on structure first, then on measured risk

The vendor's industry names are, in practice, hierarchical: `Oil & Gas E&P`, `Oil & Gas Drilling`,
`Oil & Gas Midstream`; `Banks - Regional`, `Banks - Diversified`; `REIT - Office`, `REIT - Retail`;
`Software - Application`, `Software - Infrastructure`; `Utilities - Regulated Electric`,
`Utilities - Regulated Gas`. **The families are already in the labels.** Consolidating on them is
a judgment written down once and auditable forever, and it is what makes the risk measurement
possible.

**Stage 1 — structural families, proposed below.** Every group holds at least six names and most
hold twelve or more, which is what both the industry risk rating and James's new fifth leg, the
within-industry rank, need.

**Stage 2 — the committed risk-distance criterion, applied to the stage-1 groups**, merging
further only where the data shows two families are not distinguishable as risk buckets. That is
the test that has already been built; it just needs groups large enough to be measurable.

---

## 3. THE PROPOSED STAGE-1 TABLE — 43 groups, every one at n ≥ 6

| sector | group | n | consolidated from |
|---|---|---|---|
| **Basic Materials** | Chemicals | 20 | Specialty Chemicals, Chemicals, Agricultural Inputs |
| | Metals, Mining & Materials | 11 | Steel, Copper, Gold, Other Metals, Building Materials, Paper |
| **Communication Services** | Media & Entertainment | 26 | Entertainment, Internet Content, Advertising, Gaming, Broadcasting |
| | Telecom Services | 9 | — |
| **Consumer Cyclical** | Retail | 27 | Apparel/Specialty/Internet/Department/Home Improvement Retail |
| | Autos | 21 | Auto Parts, Manufacturers, Dealerships, Components, RVs |
| | Travel & Leisure | 20 | Travel Services, Resorts & Casinos, Lodging, Leisure, Gambling, Personal Services |
| | Apparel & Luxury | 15 | Apparel Manufacturing, Luxury Goods, Footwear |
| | Homebuilding & Furnishings | 8 | Residential Construction, Furnishings |
| | Packaging & Containers | 8 | — |
| | Restaurants | 7 | — |
| **Consumer Defensive** | Food Products | 17 | Packaged Foods, Farm Products, Confectioners, Food Distribution, Grocery |
| | Household & Personal Products | 9 | — |
| | Beverages & Tobacco | 9 | Non-Alcoholic, Brewers, Wineries, Tobacco |
| | Discount Stores | 6 | — |
| **Energy** | Oil & Gas Producers | 28 | E&P, Integrated, Thermal Coal |
| | Oil & Gas Services & Drilling | 12 | Equipment & Services, Drilling |
| | Refining & Midstream | 11 | Refining & Marketing, Midstream |
| **Financial Services** | Insurance | 27 | P&C, Life, Brokers, Diversified, Reinsurance |
| | Asset Management & Capital Markets | 25 | Asset Management, Capital Markets, Investment Banking |
| | Banks | 21 | Regional, Diversified |
| | Credit Services | 11 | — |
| | Financial Data & Exchanges | 10 | — |
| **Healthcare** | Medical Devices & Instruments | 27 | Medical Instruments, Medical Devices, Healthcare Equipment |
| | Biotech & Diagnostics | 22 | Diagnostics & Research, Biotechnology |
| | Healthcare Providers & Services | 20 | Plans, Distribution, Care Facilities, Retailers, Health IT |
| | Pharmaceuticals | 19 | Drug Manufacturers General & Specialty, Pharmaceuticals |
| **Industrials** | Machinery & Equipment | 32 | Specialty Industrial Machinery, Electrical Equipment, Farm & Heavy Machinery, Tools, Metal Fabrication |
| | Transportation | 18 | Freight & Logistics, Railroads, Airlines, Trucking |
| | Commercial & Professional Services | 15 | Specialty Business Services, Consulting, Waste, Security, Staffing |
| | Aerospace & Defense | 14 | — |
| | Construction & Building Products | 12 | Building Products, Engineering & Construction |
| | Distribution & Leasing | 10 | Industrial Distribution, Rental & Leasing, Conglomerates |
| **Real Estate** | REIT — Residential & Diversified | 12 | Residential, Diversified |
| | REIT — Specialty & Industrial | 11 | Specialty, Industrial |
| | REIT — Office, Healthcare & Services | 11 | Office, Healthcare Facilities, Real Estate Services |
| | REIT — Retail & Hotel | 8 | Retail, Hotel & Motel |
| **Technology** | Software | 39 | Application, Infrastructure |
| | Semiconductors & Equipment | 23 | Semiconductors, Semiconductor Equipment |
| | Hardware & Components | 21 | Communication Equipment, Computer Hardware, Electronic Components, Consumer Electronics |
| | IT Services | 14 | — |
| | Instruments & Solar | 11 | Scientific & Technical Instruments, Solar |
| **Utilities** | Regulated Utilities | 31 | Regulated Electric, Gas, Water, Diversified, Independent Power |

**43 groups, smallest n = 6, median n ≈ 14.** Stage 2 will reduce this — on the merge behaviour
already measured, a 50bp tolerance took 31 measurable industries to 24, so 43 structural groups
should land somewhere in the **high twenties to mid thirties**. That is more than James's guess of
twenty, and the difference is worth a conversation rather than being forced.

---

## 4. THREE JUDGMENT CALLS IN THAT TABLE WORTH ARGUING WITH

- **Utilities collapses to one group.** Twenty-three of thirty-one names are Regulated Electric,
  and the rest cannot field six names between them. A single Utilities group may be right, but it
  means the within-industry rank for a utility is a rank against every other utility, which is
  probably what you want anyway.
- **Software stays as one group of 39** rather than splitting Application from Infrastructure.
  Both are large enough to stand alone, so stage 2 should decide this on measured distance, not me.
- **Tobacco is folded into Beverages.** Two names, and tobacco's risk character is genuinely
  unlike beverages. The alternative is leaving it in a catch-all. Neither is good.

---

## 5. WHAT THIS MEANS FOR THE FIFTH LEG

James's new within-industry rank needs enough peers to rank against. At the vendor's taxonomy,
**42 industries hold two names or fewer** — a within-industry rank there is meaningless or
undefined. At the stage-1 table the smallest group holds six and the median holds fourteen, which
makes the leg computable for every name in the universe. **The grouping work is a precondition for
leg 5, not a parallel task.**

---

## 5b. CROSS-SECTOR MERGING — James's correction, and it changes the result immediately

**James, 2026-08-21: *"individual stock and/or industries can be taken out of their sectors to
merge with stock in a different sector. For example, some communications and tech stocks can be
merged. Some utilities and industrials could be merged."***

He is right and the first version of the tool was wrong to forbid it. **This is a risk grouping,
not a taxonomy.** If regulated utilities and telecom services carry the same risk character they
belong in one bucket whatever GICS calls them, and forcing them apart injects a distinction the
score is not trying to measure. The constraint is removed.

**Lifting it changes the answer at once.** The same criterion, cross-sector allowed, at a 50bp
tolerance gives **17 groups instead of 24**, and three of them span sectors:

| ratio | group | members |
|---|---|---|
| **0.783** | **the defensive bucket** | Telecom Services *(Comm Svcs)*, Household & Personal Products, Packaged Foods *(Cons Def)*, Drug Manufacturers — General *(Healthcare)* |
| **0.959** | **quality cyclicals** | Specialty Chemicals *(Materials)*, Financial Data & Exchanges, Insurance P&C *(Financials)*, Medical Devices *(Healthcare)*, Aerospace & Defense *(Industrials)* |
| **1.043** | **market-like** | Packaging & Containers *(Cons Cyc)*, Diagnostics & Research, Medical Instruments *(Healthcare)*, Specialty Industrial Machinery *(Industrials)*, REIT Residential, REIT Specialty *(Real Estate)*, IT Services *(Tech)* |

**The first of those is James's own example arriving unprompted** — Telecom Services leaves
Communication Services and lands with consumer staples and large-cap pharma, at 0.783. That is
what the market thinks a regulated telecom is: a defensive cash-flow business, not a
communications-and-media stock.

The third spans **five sectors** and puts residential REITs alongside industrial machinery and IT
services at 1.043 — all businesses the market prices at roughly index risk.

Stage 2 also answers a question I flagged as mine to not decide: **Software — Application and
Software — Infrastructure merge**, at 1.151. They are one risk bucket.

**One consequence to watch, and it is not an objection.** Grouping on measured risk and then
feeding the group's risk into the score is mildly circular — members are similar by construction,
and the resulting groups line up almost perfectly as a risk ladder from 0.783 to 1.743. That is
the intent of the leg. But it means **stability is the thing to test**: groups formed on one
period must still cohere out of sample, or the score jumps whenever the grouping is refreshed.
That test is not yet built and should be part of the next step.

**It also means leg 4 will correlate with leg 1**, for the same reason put-option implied
volatility does. Worth measuring before the equal weighting is finalised.

---

## 6. WHAT I NEED

**Sign-off on the stage-1 table**, or corrections to it. It is a judgment call about business
similarity and James's domain sense has already caught two defects this week that no gate found.
Once it is agreed I will land it as a committed mapping file, rerun the risk series on the merged
groups, and apply the stage-2 distance criterion that is already committed.

## ARTIFACTS

`outputs/2026-08-21-industry-groups/industry_risk_series.csv` — monthly risk ratio for the 31
industries that were individually measurable, 2003–2026. `industry_groups.json` — the run output
and the trade-off curve. `tools/industry_grouping.py`.

## WHAT IS NOT CLAIMED

The stage-1 table is structural judgment, not a measurement. Names are assigned on EODHD's current
industry label applied to the whole history, so a company that changed industry is mislabelled in
its earlier years. The 31 measurable industries were measured on S&P 500 members only, 2003–2026.
