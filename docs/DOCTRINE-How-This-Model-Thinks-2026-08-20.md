# DOCTRINE — how this model thinks, and two mistakes not to repeat

**Written 2026-08-20 after making both of them in one session. Read this before touching a
forecast, a horizon, or any sentence describing where a company's value comes from.**

Both errors below were made by an assistant that had read the forecaster kit, the canonical
closure and the handoffs. Neither is subtle once stated. Both were corrected by James in
conversation, and neither correction was written down anywhere findable — which is why this file
exists.

---

## 1. THE TRUNCATION CONDITION IS A LEVEL, NOT A DIRECTION

**The rule, in James's words, 2026-08-20:**

> "Everything is a free forecaster choice except this: **AEG must be zero in the first year of
> the continuing period and beyond.** Leverage can change, buybacks can change, sales can
> change, margins can change. There are a whole bunch of levers which the forecaster controls.
> The forecaster decides all of them. The only restriction is that AEG must equal zero in the
> first year of the continuing period. The level of earnings must also be at a normalized level.
> That's it."

Two conditions. Nothing else is constrained.

**The mistake.** I read gate A's message — *"abnormal earnings growth is still GROWING at the
stop year"* — and inferred that the requirement was a **direction of travel**, something to be
made to decay. Then, being told the test is the return on incremental capital, I built an
elaborate solver that drove real return on incremental capital onto the real cost of equity by
year 7 and held it there, and treated that as the target.

It is not the target. It is a *steady-state consequence* of the target, and the engine does not
measure it. The engine measures abnormal earnings growth **per share**, which sits downstream of
distributions, buybacks and leverage. Return on incremental *operating* capital sitting exactly
on the cost of capital does **not** make AEG(EPS) zero.

Worse, I froze `target_flev` and `buyback_rate` as if they were given, then reported that they
"sat between me and the target". They are levers. When the second attempt came out worse than
the first, the answer was to use them, not to explain why they were in the way.

**What to do instead.** Aim at what is measured. Build the engine locally (see section 4), read
`<TICKER>_convergence.csv` and the `[truncation] gate A` line, and move whatever drivers you like
until `aeg_at_N` is approximately zero and the normalization gap is small. It takes minutes.

The two published gate outputs to satisfy:

```
[truncation] gate A, abnormal growth spent: AEG at cfg_N -0.0188/sh, ... discarded tail 0.49% of value
[convergence] guard PASS: truncation valid: gap 0.3% of EPS, discarded AEG tail 0.49% of value
```

The discarded-tail limit is 1% of value and the normalization gap limit is 15% of EPS.
`aeg_at_N` near zero from EITHER side is fine — Microsoft published at **−0.0188**.

**A worked example, so the shape is concrete.** Microsoft, N=12, everything else held: sweeping
one driver moves `aeg_at_N` straight through zero.

| terminal NOA growth | AEG at year 12 | verdict |
|---|---|---|
| 5.5% | +0.4071 | refused, tail +408% |
| 7.0% | +0.2559 | refused, tail +66% |
| 8.9% | +0.0339 | refused, tail 1.09% — *just* over the 1% limit |
| **9.3%** | **−0.0188** | **PUBLISHED**, tail 0.49% |
| 9.7% | −0.0733 | refused, overshot into negative and diverging |

The window is narrow and it is findable in three runs. There is no need to derive it.

---

## 2. VALUE IS NEUTRAL VALUE PLUS ABNORMAL EARNINGS GROWTH — NOT EXPLICIT PLUS TERMINAL

**The rule, in James's words:**

> "That is not how this model looks at things. X percent of the value is in the ANCHOR. Probably
> half of the anchor value is technically in the continuing period. But in this model we
> decompose value between neutral value and the value of abnormal earnings growth."

**The mistake.** I wrote *"ninety-three percent of the value sits in the continuing period"* and
built an argument on it — that the horizon was load-bearing for nearly the whole valuation and
the gate was therefore an alarming obstacle.

That sentence imports a discounted-cash-flow frame this model deliberately does not use. There is
no explicit-versus-terminal split here. Splitting on the year-N boundary is meaningless, because
a large part of the **anchor's** value is realised after year N too — the anchor is capitalised
over all time. Saying "93% is in the continuing period" is close to saying "most of a perpetuity
happens later", which is true and tells you nothing.

**The correct reading.** Microsoft, as published:

| | per share | share of value |
|---|---|---|
| **Neutral value** — worth at current normalized earning power, capitalised | **~272** | ~98.5% |
| **Value of abnormal earnings growth** — the entire forecast argument | **+3.99** | **1.5%** |
| adjusted equity | **276.30** | 100% |

That is the honest statement, and it changes the temperature completely. The forecast is arguing
about 1.5% of Microsoft. The horizon choice moves that slice and essentially nothing else.

`<TICKER>_periods.csv` reports this directly as `pv_contribution_ps` and
`pct_of_corrected_value`. **Quote those. Do not compute a percentage against the year-N
boundary.**

**Phrases that are wrong here and should never appear in a document, a commit message or a
message to James:** "X% of the value is in the terminal period"; "X% of the value is in the
continuing period"; "the explicit forecast is worth X% of the value" — that last one is
*arithmetically* what `periods.csv` prints, but it means the AEG contribution, not a period
split, and calling it a period split is what caused the error.

---

## 3. WHAT THE LEVERS ACTUALLY DO — measured, not assumed

Measured on Microsoft 2026-08-20 by running the engine and diffing the output:

| lever | effect on VALUE | effect on the forecast |
|---|---|---|
| `revenue_growth` (tail) | large | 2.2% terminal growth also drives AEG to zero — a different, equally valid forecast |
| `noa_growth` (tail) | moderate | the cleanest single lever for landing AEG at zero |
| `gross_margin`, `sga_ratio`, `tax_rate` | direct | ordinary |
| `target_flev` | **real**: 268.92 at 0.10, 276.30 at 0.35, 288.21 at 1.20 | changes value AND funding capacity |
| `buyback_rate` | **NONE — value identical to the last digit at 0%, 1% and 5%** | changes the IMPLIED DIVIDEND: +11.21/sh at zero buyback, −13.99 and UNFUNDED at 5% |

**`buyback_rate` being value-neutral is correct, not a defect**, and I briefly reported it as one.
Under the canonical closure distributions are implied; the buyback rate sets the *form* of the
distribution, not its amount, so it cannot move equity value. It correctly drives the funding
guard to flag an unfunded distribution when set too high. **Do not "fix" it.**

**The two-of-three rule is why the levers behave this way.** A forecaster may set any two of the
operating plan, the distribution policy and the financing structure — the third is implied.
Setting the operating drivers AND `target_flev` AND `buyback_rate` means the **dividend** is what
gives. If a forecast needs more retention, that comes from the operating plan or the leverage,
not from asking for it directly.

---

## 4. BUILD THE ENGINE LOCALLY. DO NOT ITERATE THROUGH CI.

A previous handoff said a cloud session cannot recalculate the workbook because the raw statement
feeds are not in the repository. **They are — in a separate repository.**

```bash
git clone --depth 1 https://<token>@github.com/JamesKostohryz/market-data.git
export MARKET_DATA_DIR=/path/to/market-data
export EODHD_API_KEY=...  GITHUB_TOKEN=...
python3 pipeline/run_company.py companies/MSFT.yaml --rate-feed-live \
    --payload payload.json --out-dir /tmp/out --vintage local
```

**Forty seconds a run, and it reproduces CI to the last digit** — verified against three CI runs
on 2026-08-20. Iterating a forecast through the RUN button at two minutes a dispatch, reading
gate output out of workflow logs, is how a three-run search becomes an afternoon.

**Also, and it cost this session a failed run: SOMEONE ELSE MAY BE WORKING THE SAME REPOSITORY.**
A parallel session landed `8f5230f` mid-solve, re-fitting every issuer credit curve. Microsoft's
premium moved from `+0.1749` collapsed to `+0.1379`, its cost of capital fell, and a driver set
that passed locally at a 0.94% discarded tail came back from CI at 1.09%, over the 1% limit, and
refused. **`git fetch` and check `HEAD..FETCH_HEAD` before dispatching anything you solved
against local state.**

---

## 5. THE STANDING SUSPICION, RESTATED FOR FORECASTS

The register is about numbers that are silently wrong while every gate reports success. The
forecasting analogue is a driver set that **ties perfectly and asserts something absurd**.

The four-method tie holds for any forecast. It held for every refused Microsoft run. It holds —
verified 2026-08-20 — for Bank of America at a **negative $263 billion** enterprise value with
operating flows discounted at **−0.09%**.

**The tie is a bookkeeping identity. It is never evidence a forecast is sensible.** The gates
are: gate A on truncation, the normalization check, the funding guard. Those are the ones that
look at the economics, and when one refuses, the first assumption should be that it is right.

On 2026-08-20 gate A refused Microsoft twice and was correct both times — the first time
catching that the target cost of capital had been taken from a published column the engine does
not use (6.699% from `coe_v2`, when the engine builds `real_rf 3.700% + fwd_erp 2.037% +
premium` and drops that file's idiosyncratic term entirely).
