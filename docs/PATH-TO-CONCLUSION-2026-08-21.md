# THE PATH TO CONCLUSION — historical ERP and cost of equity, for companies and sectors

**2026-08-21. What "done" means, what is already done, what blocks the rest, and the two
decisions only James can make. Written because the last two days produced a lot of findings and
not an obvious ordering.**

---

## WHAT "DONE" LOOKS LIKE

One function, reproducible, with a stated error:

```
real_cost_of_equity(company_or_sector, date)  =  real_rf(date)  +  market_ERP(date) × relative_risk(date)
```

Three components. **Two of the three are finished.** All the difficulty is in the third, and one
unresolved defect sits underneath all three.

| component | state |
|---|---|
| `real_rf(t)` | **done** — monthly 1929–2026 |
| `market_ERP(t)` | **built, but on the wrong basis.** See the blocker. |
| `relative_risk(t)`, companies | numerator always available; denominator measurable to ~1985 at 7–17bp — **or unnecessary, depending on decision 1** |
| `relative_risk(t)`, sectors | panel 2003–2026 on the right taxonomy; French 1928–2003 on a different one |

---

## THE BLOCKER, NOW QUANTIFIED — two published market ERPs, 1.36pp apart, today

| | 1-year real rf | 1-year market ERP | 1-year real COE |
|---|---|---|---|
| `outputs/market_coe_history.csv`, 2026-06 — **the historical series** | 1.070% | **5.304%** | **6.373%** |
| `TODAY_forward_curve_latest.csv`, Option B — **what live valuations use** | 1.380% | **3.948%** | **5.328%** |
| difference | 0.31pp | **1.36pp** | **1.05pp** |

**A valuation dated 2026 from the historical series and one from the live engine differ by more
than a percentage point of discount rate — roughly 16% of a neutral value.** Historical and
current numbers are in different currencies, which defeats the entire purpose of building a
history.

**The fix is the one the bridge was designed for, and it was written down in advance.**
`idio/market_semidev_bridge.py` states it in its own header: *"It targets the risk INPUT, not the
premium… whatever model replaces the current one consumes the reconstructed VIX-equivalent exactly
as it consumes VIX1Y today. Recalibrating later is two numbers, not a rebuilt history."*

So: take the reconstructed VIX-equivalent series, 1929–2026, and feed it through the **Option B**
ERP construction rather than the Martin bound that `market_coe_history.csv` currently uses. The
history does not need rebuilding; the premium layer on top of it does. **Nothing else in this
document should be done first**, because every sector and company premium is a multiple of this
number.

---

## DECISION 1 — GATED, JAMES ONLY, AND IT DELETES OR CREATES A WEEK OF WORK

Two constructions for `relative_risk`. They are not a technical preference; they answer different
questions about *whose* cost of equity this is.

| | **A — today's construction** | **B — total risk** |
|---|---|---|
| formula | residual semidev ÷ cap-weighted universe average | total semidev ÷ market total semidev |
| prices idiosyncratic risk | only cross-sectionally; the average company's is **not priced at all** | **fully** |
| values for | someone holding the index | someone holding **that one position** |
| needs a universe? | **yes** — the denominator is the whole problem | **no** — two price series, any date |
| historical reach | ~1985, at 7–17bp of measured error | **any date the security traded** |
| Microsoft today | 0.805× → front premium ≈3.3pp, real COE 6.27% | 1.77× → front premium ≈7.3pp, real COE ≈10% |
| effect on the published $276.30 | none | **cuts it substantially** |

**B also unifies companies and sectors.** Under B a sector is just a portfolio measured the same
way as a company — the taxonomy problem, the French-versus-panel problem and the denominator
problem all collapse into one construction with no reference universe at all.

**Textbook portfolio theory favours A. A method built for concentrated value investors arguably
wants B**, and Real Value Analysis is aimed at people making concentrated bets, not index holders.
This is the single highest-leverage decision left and it should be made **before** any more
building.

**If B: skip step 3 entirely, and step 4 gets much simpler.**
**If A: step 3 is required, and the sector taxonomy problem stays.**

---

## DECISION 2 — SMALLER, ALSO JAMES

Is **7 to 17 basis points** of denominator error acceptable on a valuation dated 1995? That is the
measured cost of computing the company denominator directly from the panel we have. My view: yes
for historical analysis, no for a live published number. **Only relevant if decision 1 is A.**

---

## THE STEPS, IN ORDER, WITH HONEST EFFORT

| # | step | blocked by | effort |
|---|---|---|---|
| **1** | **Rebuild the historical market ERP on the Option B basis.** Feed the reconstructed VIX-equivalent through the ERP engine's construction instead of the Martin bound. | nothing | half a day |
| **2** | **Decision 1**, then **decision 2** if needed. | James | a conversation |
| **3** | *If A only:* run the company denominator monthly back to 1985 from the panel; attach the measured error. | 1, 2 | a day |
| **4** | Build the sector relative-risk series. *If B:* one construction, panel 2003+ and French before, both on total risk. *If A:* panel 2003+ on the right taxonomy, French before it labelled as SIC industry, **not spliced**, offset stated at 15.6%. | 1, 2 | a day |
| **5** | **Assemble and publish.** `real_rf(t) + market_ERP(t) × relative_risk(t)`, monthly, for every sector and any company with price history. Ship the CSV and the reproduction script. | 1–4 | a day |
| **6** | Verification pass: reproduce two known points, check the four-method tie is untouched, confirm no series was spliced silently. | 5 | half a day |

**Roughly a week of work, of which about a day is genuinely blocked on James.**

---

## WHAT IS DELIBERATELY NOT ON THIS PATH

- **The sector term structure, `D(t)`, Region 2 and Region 3 for sectors.** Everything measured so
  far is the front-tenor level. A full sector term structure is a separate project and is not
  needed for a headline cost of equity.
- **Objective 4**, behind its pre-registration. Two unmade choices swing it 3.8bp to 100bp.
- **Financials restatement.** Real and wrong — JPMorgan's economic net income comes out −$14.5bn
  against a reported +$55.7bn — but it is a design conversation, not on this path.
- **Resolving GFD versus panel.** Two validations of the French series disagree. It matters only
  if French is used for a GICS-labelled number, which recommendation 4 above avoids.

---

## THE STANDING SUSPICION, FOR THIS PATH SPECIFICALLY

Three defects in the last two days were caught because **a number looked wrong**, not because a
test failed: Real Estate at 6.46 on three firms, Real Estate mislabelled as REITs when it holds
land developers, and a market ERP 1.36pp from the one live valuations use. None of them would have
tripped a gate.

**Before step 5 publishes anything, the check is not "does it tie" — it is "does an analyst who
knows these sectors recognise the ordering."** That test has found three defects and the gates
have found none.
