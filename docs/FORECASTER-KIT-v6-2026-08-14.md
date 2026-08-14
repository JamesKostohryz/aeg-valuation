# FORECASTER KIT — CURRENT VERSION (v6, 2026-08-14)

**This is the authoritative kit. Anything older is superseded — see section 11.** The copy in the repository at `docs/` is the source of truth; any other copy is a working copy. **There is no top-level copy and there must never be one again** — the stray `FORECASTER-KIT-CURRENT-v3-*` at the top of the project folder was archived on 2026-08-13 for exactly that reason.

> **Changing this document?** Follow `docs/KIT-CHANGE-PROCEDURE.md` first. A kit change is an end-to-end audit of the whole file plus four other places, not an edit to one section. Editing one section and leaving the rest is how this document went stale three times in a single day on 2026-08-12.

Valid against commit `90dbdc1` on `github.com/JamesKostohryz/aeg-valuation` — the commit that fixed
`run_scenarios.py`'s gate bypass (see "What changed in v6" below). Regression harness stages that
touch this change are green (`test_horizon_gating.py`, `test_terminal_payout.py`,
`test_convergence.py`, `test_run_scenarios.py`, all re-run 2026-08-14); the fleet CI (`valuation.yml`)
is red on this same commit, and that red is now MORE informative than it was, not less — see below.

> **A property of this system that is easy to mis-state, and was mis-stated in the first draft of this preamble.** PepsiCo's headline is *not* stable across runs. The pipeline repoints rates and price live on every run, so the same reviewed forecast produced `$116.2259` against a real price of `$144.3782` at commit `fb4927c` and `$115.7595` against `$146.3768` at `ecf6a58` — a move of 0.40% caused by the long-run real cost of equity going from `5.4877%` to `5.5279%`, four basis points. Nothing about the forecast changed. **Always quote a valuation together with the commit and the run that produced it**, and never carry a headline number forward from a document without re-reading `outputs/<TICKER>_summary.csv`. Four basis points on the long end is worth roughly half a dollar a share here, which is also a useful reminder of how much work that single rate does — standing failure mode two, visible in the ordinary operation of the system. **v6 adds a second, sharper instance of the same lesson**: on 2026-08-14 this same drift pushed PepsiCo's own already-published `bear` scenario past Gate A's tail threshold on a live re-dispatch, with no driver change at all. See "What changed in v6," item 1.

**What changed in v6.** One thing, from the Coca-Cola Round 3/4 guest-forecaster work on 2026-08-14 — a real gate that did not exist before, closing a defect this kit itself never described (it lived entirely in `run_scenarios.py`, and the session prompts that flagged it, not in this document).

1. **`run_scenarios.py` now applies Gate A, Gate B, the funding gate, and the terminal-payout gate to EVERY scenario in a multi-scenario dispatch, not just the primary.** Before this fix, only the scenario named `primary` in a `companies/<T>.forecast.json` ran through `run_company.py`'s ordinary single-scenario path (gates and all); every other scenario — bull, bear, whatever a forecaster named them — went through `run_scenarios._value_one()`, which checked only data completeness/provenance and the four-method tie. A truncation that discarded real value, a distribution plan that silently issued equity to fund a buyback, or a continuing period with no forecaster-owned payout policy would all have published for a non-primary scenario with every visible check green. Fixed by threading the company-level config through `run_scenarios.run_scenarios()` / `_value_one()` so every scenario now calls the same `convergence.converge_auto`, `funding_check.funding_report`, and `terminal_payout.terminal_payout_report` the primary path already calls, fail-closed, cleared by the same `reviewed: true` escape hatches — there is no per-scenario review flag; a company-level `reviewed: true` clears a gate for every scenario in that dispatch. Proven inert to value: `test_run_scenarios.py`'s AAPL fixture, properly reviewed, reproduces bit-identical intrinsic values, tie residuals, and expected-value math against the unpatched code. **The fix caught a real, live problem on its first production run**: the fleet CI dispatch immediately after this change showed PepsiCo's own published `bear` scenario (`companies/PEP.forecast.json`, cfg_N=12) now fails Gate A under 2026-08-14's rates — the discarded tail is 2.0% of value, over the 1% ceiling — even though `base` and `bull` still clear every gate cleanly and PepsiCo's tie is untouched. Nothing about `bear`'s drivers changed; the cost-of-equity curve moved enough between 2026-08-12 (when `bear` was last verified) and 2026-08-14 to push an already-marginal horizon (factor 0.899, a slow decay) over the tail threshold. **This is why the fleet CI is currently red, and that red is correct, not a regression** — it is the system reporting a truth about PepsiCo's `bear` scenario that the pre-fix code could not see and would have silently republished. `docs/HANDOFF-NEXT-SESSION.md` carries the open follow-up (a fresh horizon search for PepsiCo's `bear`); this kit does not resolve it.

The four-round forecasting protocol itself — the qualitative brief, the driver build, the review — is unchanged and still lives in `archive/PEP_Guest_Forecaster_Package_2026-08-10.md`. Use that document for the *process* and this one for the *rules the engine now enforces*. Where the two conflict, this one wins. **Note that its Round 1 instruction to end in a "moat length" is superseded**: N is not moat length, it is simply the explicit forecast period, and it is found mechanically by extending the forecast until section 8's two gates both hold (James, 2026-08-12).

---

## 1. There is now one forecast closure, and it is the operating one

Net operating assets and operating income are driven. Financing absorbs. The equity view is a
presentation choice, not a second way of forecasting.

The reason is not tidiness. In the old equity closure, net operating assets were derived from
common equity — net operating assets equals common shareholders' equity times one plus financial
leverage — so any equity transaction moved the operating assets. Making share repurchases live in
that closure collapsed Apple's net operating assets forty-three percent in the first forecast year
and broke the four-method tie at `1.98e+01`. Nothing about the operating business had changed; a
financing transaction had happened. Under the canonical closure the same experiment leaves net
operating assets bit-identical at a zero and a three percent buyback rate.

## 2. The two-of-three rule — state this first, it explains everything else

The balance sheet identity plus clean surplus gives:

> net financial obligations at t = net operating assets at t − common equity at t−1 − net income
> at t + distributions at t

So of the following three, **a forecaster may set any two, and the third is implied**: the
operating plan (net operating assets and operating income), the distribution policy (dividends and
buybacks), and the financing structure (leverage).

Stated for the forecaster: *choose your operating plan and your distribution policy, and the
financing follows; or choose your operating plan and your target leverage, and distributions
follow. You do not get all three, because the balance sheet has to balance.*

This is not a limitation of this engine. It is arithmetic. An over-determined payload is rejected
loudly at the seam, before any cell is written.

This is the rule for the **explicit** forecast, years 1 through cfg_N. Section 6 states the
separate, parallel rule for what happens after it.

## 3. The payout seed is no longer accepted, and `payout_ratio` means dividends only

`payout` is rejected outright by the payload seam. Under the canonical closure it feeds exactly one
cell — the equity branch of Forecast row 29 — which is inert. Accepting it would write a number
that changes nothing while reporting itself as applied, the same silent-ignore failure as the
horizon and leverage bugs before it.

Separately and permanently: now that share repurchases are live, any payout figure means
**dividends only**. The clean-surplus roll subtracts dividends and repurchases separately, so a
payout number folding buybacks in gets counted twice. Express the buyback through `buyback_rate`.

The new `terminal.payout_ratio` in section 6 follows this same rule: dividends only, buybacks
never folded in. One meaning for "payout" across the whole kit, not two.

Note also that the buyback rate is **valuation-inert** under this closure. Valuation row 7 is
expressed per anchor share, so a repurchase is a distribution to the anchor shareholder rather than
a shrinking denominator, and total distributions are pinned by the operating plan and the
financing. Only the split between dividends and buybacks is free. Do not expect a buyback
assumption to move the value; expect it to move the funding verdict in section 5.

## 4. Both readings are shown, and they agree by identity

The equity read and the enterprise read are computed side by side and their agreement row reads
exactly `0.000000e+00` — not within tolerance, exactly zero. The enterprise discount rate is
leverage-implied, so enterprise value less financing equals equity value as an identity.

## 5. The funding gate

The engine inspects the implied distribution path and returns PASS, REVIEW or NOT_APPLICABLE,
reading the workbook's own row 29 rather than recomputing it. **This covers the explicit forecast
only, years 1 through cfg_N** — see section 6 for the parallel question about what comes after.

What it catches is an incoherent capital plan. On the default Apple overlay, net income of
`0.118257` less the increase in common equity of `0.002308` leaves `0.115948` of distribution
capacity, while a three percent buyback demands `0.147602`. The residual dividend is negative —
`−2.1748` per share in year one, negative in every year out to `−2.4310`. Read plainly, the plan
asserts the company issues equity to fund a buyback it cannot afford while simultaneously retiring
shares. That is arithmetically valid and economically a capital raise, and nothing else in the
engine distinguishes the two.

A dividend of exactly zero is admissible. Only a genuinely negative residual trips the gate, beyond
a `1e-9` numerical floor that **must never be widened to make a company pass**. A REVIEW verdict
refuses the valuation and is cleared only by a human writing `funding: reviewed: true` in the
company configuration:

```yaml
funding:
  reviewed: true
  note: <which of the three causes it was, and why the capital raise is intended>
```

**Corrected 2026-08-12: this escape hatch did not work before this version.** The config loader
never read the `funding` block, so `funding: reviewed: true` had no effect on any run before this
kit. It is fixed now — see `pipeline/test_config.py`, "funding review flag" section, for the pinned
regression.

Be honest about what this is: a plan-coherence guard, not a valuation-integrity guard. It does not
protect a number. It refuses to publish a forecast whose capital plan does not hang together.

## 6. THE TERMINAL PAYOUT RATIO — what the company does after cfg_N

**New in v4.** Sections 1 through 5 govern the explicit forecast. This section governs the one
sentence the kit had never made anyone say: what does this company do once it reaches the
continuing period?

**Why this was a gap, concretely.** The Forecast tab has thirty columns; a real payload only ever
writes columns 1 through cfg_N (`pipeline/apply_payload.py` writes `for t in range(N)`, nothing
past it). The columns from cfg_N+1 to 30 keep whatever formula the template shipped with — the
legacy three-scenario overlay, unrelated to anything the forecaster set for the explicit years.
Measured on a real forecast for the first time on 2026-08-12 (PepsiCo, cfg_N=4, the actual Round 2R
driver build): the overlay's buyback assumption is 3% of shares a year, against the forecaster's
actual 0.35%, and it implies a modeled dividend of **−$2.96/share in year 5**, worsening to
**−$7.15/share by year 16**. Nobody chose that. It was never examined, because nothing read those
columns.

**Why it does not move the published value, and how you can check that yourself.** Valuation row 24
(`contrib EPS [t<=N] = dRI^E_t x A^E_t`) is `=IF(C4<=cfg_N, C63*C62, 0)` — every abnormal-earnings
contribution past cfg_N is forced to zero before it is summed. The terminal capitalization itself
(row 43, `Normal value = BPS0 + (normal EPS1 - rho*E1 x BPS0) x A^E1`) is built from year-0 and
year-1 data only. So the garbage in columns cfg_N+1..30 was always inert to the four-method tie and
the two truncation gates (`test_horizon_gating.py` already proved this generally, for any
perturbation of those columns; `test_terminal_payout.py` proves it specifically for this gate: the
published intrinsic value is bit-identical whether `terminal.payout_ratio` is 0.0, 0.5 or 1.0).
Nobody's valuation was silently wrong. But nobody's continuing period was examined either, and a
company can now clear every existing gate on an implicit capital plan that would issue equity
forever to fund a buyback nobody asked for.

**What to provide.** A single number, `terminal.payout_ratio`, between 0.0 and 1.0: the fraction of
**normalized** net income — the same `normalized_eps_N` gate B already computes, section 8 — that
this company distributes as dividends once it reaches the continuing period. Retention is the
residual, `1 − the ratio`. Dividends only, per section 3's rule; do not fold a buyback assumption
in here.

```yaml
terminal:
  payout_ratio: 0.55
  reviewed: true
  note: <why this ratio>
```

**Why it cannot fail the way section 5's gate does.** That gate catches a *negative* implied
dividend, because the explicit-year dividend is a residual after an independently-chosen buyback
rate and financing target — an unbounded quantity that can overshoot capacity. `terminal.payout_ratio`
is bounded to `[0,1]` at the config seam, so it can never itself demand more than the company earns.
What this gate catches instead is the case beneath that: a normalized earnings level that is zero,
negative, or unavailable, where no payout ratio is a coherent assertion about the continuing period
at all. `REVIEW`, cleared the usual way with `terminal.reviewed: true`.

**The one case with no escape hatch.** A ratio that was never set at all — `terminal.payout_ratio`
absent — refuses unconditionally, in deliberate parallel to `forecast.horizon_N`: an assertion
nobody made cannot be reviewed into existence by writing `terminal.reviewed: true` with no ratio
behind it. There is no default and there never will be.

**What this is not.** It is disclosure and a boundary check on a number that was previously
undefined, not a new lever on value. Do not expect changing it to move the headline. If you want to
know why a company's value is what it is, that is sections 1 through 5, 7 and 8 below; this section
only says what happens to the cash once the story is over.

## 7. THE AEG VALUE TEST — the bar your forecast has to clear, and how to compute it

**New in v5.** Sections 1 to 6 tell you what you may set and what the engine will refuse. This section tells
you the one thing the kit had never stated: **what your earnings path actually has to beat for abnormal earnings
growth to be positive at all.** It adds no gate and moves no published number. It exists because a forecaster
worked this out from first principles on 2026-08-13, got it wrong by about 1.5 percentage points of real growth,
and only found the error by opening the workbook — with every input in front of them and the code already read.
If that is the failure rate on derivation, the formula belongs in the kit.

### 7.1 The formula, verbatim

`MODEL_TEMPLATE.xlsx`, Valuation rows 22 and 23:

```
normal EPS_t  =  (1 + pi_t) * EPS_(t-1)  +  (rhoE_nom_t - pi_t) * retained_(t-1)
AEG(EPS)_t    =  EPS_t - normal EPS_t
```

Read it in two beats, because the order is the whole point. **First**, last year's earnings are carried forward
at inflation — a company that merely keeps pace with inflation creates nothing. **Then**, and only then, the
**real** cost of equity is charged on last year's retained earnings. Abnormal earnings growth is whatever is
left.

The inflation carry is the part that gets dropped when people reason about this from memory, and it is not
small: it is the entire hurdle for a company that retains nothing.

### 7.2 The hurdle, in the two forms you will actually want

Both are exactly equivalent to `AEG(EPS)_t > 0`. Use whichever fits the question.

**The return-on-retained-earnings form.** *Return on retained earnings, in real terms, must exceed the real cost
of equity.*

```
RORE_real_t  =  ( EPS_t/(1+pi_t) - EPS_(t-1) ) / retained_(t-1)
rho_real_t   =  ( rhoE_nom_t - pi_t ) / (1 + pi_t)
                                                        AEG > 0   <=>   RORE_real > rho_real
```

**The growth form.** *Real earnings-per-share growth must exceed the real cost of equity times the PRIOR year's
retention rate.*

```
g_real_t  >  rho_real_t  x  b_(t-1)                     where b = retained / EPS
```

The growth form is the one to carry in your head when you are setting drivers, because it says something
useful and slightly counter-intuitive: **a company that pays most of its earnings out has a low hurdle.** It
retains little, so little is charged. A business with no incremental returns at all can still produce positive
abnormal earnings growth if it distributes enough — and a high-retention compounder has to run very fast simply
to stand still. Retention is the lever on the bar, not on the business.

But note what does **not** scale with retention: the inflation carry. Real growth of zero fails at any payout
ratio. The floor is real, not nominal, and no distribution policy lowers it.

### 7.3 The trap — do NOT compare the published `rore` column to the published `coe` column

Every company's `<TICKER>_aeg_schedule.csv` carries a `rore` column and a `coe` column. **Comparing them
directly gives the wrong answer, and it gave the wrong answer in eight of Coca-Cola's twelve forecast years on
2026-08-13.** `rore` is built on nominal earnings while its retained-earnings denominator carries no inflation
uplift, and `coe` is the nominal cost of equity. Stated on those nominal columns the real bar is

```
rore_t  >  (rhoE_nom_t - pi_t)  +  pi_t / b_(t-1)
```

and it is the second term — roughly three times inflation for a company retaining a third of its earnings, about
seven percentage points for Coca-Cola — that the naive comparison drops. On Coca-Cola the naive test reported
that reinvestment created value in years 5 through 12; the engine booked negative abnormal earnings growth in
every one of them.

The module docstring that told forecasters to make that comparison was corrected on 2026-08-13, and the identity
is now pinned by `pipeline/test_aeg_schedule.py` check 6, which recomputes rows 22 and 23 from the CSV's own
columns and asserts `sign(aeg_eps) == sign(RORE_real - rho_real)` in every explicit forecast year. It cannot
drift from the workbook again without a build going red.

### 7.4 Worked example — Coca-Cola, on the payload-free default overlay

Not quotable as a valuation (no payload-free number ever is). Quotable as arithmetic.

| Forecast year | 1 | 2 | 4 | 5 | 8 | 12 |
|---|---|---|---|---|---|---|
| Real cost of equity | 5.36% | 6.19% | 7.42% | 8.00% | 7.46% | 7.13% |
| Prior-year retention `b` | 0.0005 | 0.3287 | 0.3287 | 0.3287 | 0.3287 | 0.3287 |
| **Hurdle on real EPS growth** | **0.00%** | **2.04%** | **2.44%** | **2.63%** | **2.45%** | **2.34%** |
| Engine's `aeg_eps` | +0.2410 | +0.0293 | +0.0081 | −0.0012 | −0.0194 | −0.0163 |

Two lessons sit in that table and both generalize.

**Year one is a free year whenever the anchor distributed nearly everything it earned.** The hurdle uses the
*prior* year's retention, and Coca-Cola's anchor retained $0.00112 per share against $2.1246 of earnings — a
retention rate of five hundredths of one per cent. So year one has to beat inflation and nothing else, and its
abnormal earnings growth is by far the largest in the schedule for a reason that has nothing to do with the
company. **Do not read year one's contribution as evidence about the business.** Check your anchor's retention
before you believe your first forecast year.

**The hurdle is not a fixed property of the company.** Under the canonical closure Valuation row 8 is *total*
distribution — dividends plus buybacks — and it is **implied**, not set. Retention is therefore an output of the
two-of-three rule, so the hurdle path belongs to the distribution policy your run implies rather than to the
business. Read it off your own run. And do not go looking for a payout ratio that makes the hurdle low: abnormal
earnings growth is designed to be invariant to the payout split when retained capital earns exactly its cost.
Moving the split moves the bar and the earnings together.

### 7.5 The engine does not value the earnings series a company reports as "comparable"

This is the same warning from the other direction, and it is the one most likely to cost you a whole round.

The engine values **reported operating income, after a replacement-cost charge for economic depreciation,
restated to constant dollars, per anchor share.** Nearly every large company also publishes a "comparable",
"adjusted" or "underlying" earnings series that excludes impairments, acquisition remeasurements, restructuring
and refranchising charges, and it is that series management guides on and the sell side models.

The two can diverge enormously over a decade. Measured on 2026-08-13, Coca-Cola's own comparable earnings per
share had compounded at mid-single digits while its real operating profit per share on the engine's basis had
compounded at **+0.24 per cent a year**, a gap of roughly four percentage points annually. Neither series is
dishonest. They differ by the write-downs — which, for a company that grows by acquisition, are a recurring cost
of the strategy rather than unusual items — and by replacement-cost depreciation.

**If you build your drivers to reproduce management's algorithm, you are forecasting a series this engine does
not value, and the gates will not tell you so.** Every gate can stay green on a well-formed forecast of the wrong
quantity. State the reconciliation explicitly in your Round 2 document: here is management's number, here is the
engine's basis, here is what accounts for the difference, and here is which one my driver path is built on.


## 8. WHERE YOUR FORECAST IS ALLOWED TO STOP — read this before you choose a horizon

**This is the most important rule in the kit, and it is your responsibility, not the engine's.**

The explicit forecast period does not end until BOTH of these are true in your final year:

1. **Projected abnormal earnings growth is spent.** Not small. Not fading. Spent — meaning that
   from the following year onward it is zero and stays zero.
2. **Earnings are at a normalized, neutral level** — the level you would be willing to call this
   company's ordinary earning power, not a good year and not a bad one.

Both. Not either.

**Why both, and why this is not negotiable.** The continuing period is defined as the stretch where
no further value is created, so abnormal earnings growth there is exactly zero. The engine enforces
that by construction: from year N+1 it books zero, always. If your forecast still shows abnormal
growth being created in year N, the engine does not argue with you — it simply throws that stream
away. You have not made a judgment; you have had one made for you, silently, and it will not appear
anywhere in the valuation.

**The implication you must not miss: you cannot truncate at a cyclical peak or trough.** A
reversion from a peak back to trend *creates* abnormal earnings growth, by definition — that is
what a reversion is in this framework. So if your forecast ends at a peak, abnormal growth is not
spent, and rule 1 is broken. Ruling that out is your job. There is no algorithm behind you checking
whether the company is at a cyclical high, and there must not be: that judgment is the analyst's
and it is most of what you are for.

**You have thirty years of horizon. Use them.** `forecast.horizon_N` accepts any integer from 1 to
30. If abnormal growth is still running at year 12, the answer is year 15, or 20. There is no prize
for a short forecast and no penalty for a long one — beyond the point where abnormal growth is
spent, extra years contribute nothing to value anyway, so a horizon that is too long is harmless
and a horizon that is too short is a silent error.

**A practical way to satisfy the rule.** Forecast one year past where you think the forecast ends,
and make that final year the first year of the continuing period: abnormal earnings growth zero,
and a level you are prepared to assert is neutral. If you can write that year down and defend it,
your truncation is legitimate. If you cannot, you have not finished forecasting.

**What "spent" means in practice, since abnormal growth approaches zero rather than arriving.** A
small residual that is *declining* is fine — forcing it to zero the following year breaks nothing.
What is not fine is a residual that is large, or one that is still *rising*. Rising abnormal growth
at your stop year means the forecast was cut off mid-stream, and no tolerance can make that
acceptable.

### The two gates, and what they will tell you

The engine checks your truncation and refuses if it fails. **It does not correct you.** There is no
adjustment, no glide, no increment — those were retired on 2026-08-12, and the reason matters: a
correction that only matters when it is small is not worth having, and one that is large means the
forecast is wrong and belongs back with you. See `docs/AEG-CONVERGENCE-RETIRED-2026-08-12.md`.

**Gate A, the terminal condition.** Reads abnormal earnings growth at year N and its year-on-year
factor. If the stream is still growing, it refuses outright — there is nothing to size. If it is
declining, the discarded tail is priced and must be under one percent of value.

**Gate B, the neutral level.** Compares earnings at year N against a normalized level built from
your own forecast path: the last four years walked forward and the median taken. The gap must be
under fifteen percent of earnings per share. This is the same `normalized_eps_N` section 6's
terminal payout ratio is applied against.

Note what gate B does and does not do. It measures departure from the trend your forecast has
recently sustained. **A level your company has held for three or more years IS the normal level**
as far as this check is concerned, and looking further back than four years is speculative. Gate B
catches a stop year that sits out of line with its own neighbors. It does not, and is not meant to,
tell you the company is at a cyclical high — that is gate A's business, and before gate A it is
yours.

Both gates are cleared only by an explicit human assertion in the company configuration:

```yaml
convergence:
  reviewed: true
  note: <which condition you accepted breaking, and why>
```

Nothing else clears them. That is intended. If you are typing that block, be sure you are asserting
a judgment rather than getting past a red light.

### Consequence, so it does not surprise you

Every payload-free default overlay on the system fails gate A today. Those forecasts use constant
growth drivers, and a constant-growth forecast can *never* satisfy the terminal condition — if
return on equity exceeds the cost of equity and growth is constant and positive, abnormal earnings
growth persists forever. This is why no payload-free run has ever been quotable, and the gate now
makes that mechanical rather than a convention someone has to remember.

### Multi-scenario dispatch — every scenario gets these same gates (fixed 2026-08-14)

If you are building bull and bear cases for a `companies/<T>.forecast.json` machine file, know that
**every scenario in it, not just the one named `primary`, now goes through the identical gates
described in this section**, plus the funding gate (section 5) and the terminal-payout gate
(section 6). That was not always true — see "What changed in v6" in the preamble for the defect and
the fix — but as of commit `90dbdc1` it is, and it is pinned by `test_run_scenarios.py`.

Practically, this means: find each scenario's own horizon the same way you find the primary
case's — dispatch it, read the real Gate A/B figures, do not inherit N from another scenario. That
was already the right discipline (Coca-Cola Round 3 did exactly this, independently, before the fix
landed, precisely *because* the fix did not exist yet and dispatching through the broken
multi-scenario path could not be trusted). Now that the fix is in, dispatching the combined machine
file will enforce it for you — but a scenario's gate-worthiness is still not a permanent property.
It was found to be sensitive to live rate movement on this exact date: PepsiCo's `bear` scenario
passed cleanly on 2026-08-12 and failed the same gate, same drivers, on 2026-08-14, purely from the
cost-of-equity curve moving. **A scenario that passed once should be re-verified before being relied
on again, not assumed permanent** — this is standing failure mode two (a single day's rate reading
setting a permanent line) showing up in a new place.

## 9. Companies currently gated — and why the reason changed on 2026-08-13

**Thirteen of the fourteen companies are refused and publish no valuation. PepsiCo publishes.**

Until 2026-08-13 the thirteen were refused by the funding gate (`AAPL`, `COST`, `KO`, `WMT`) or by
the truncation gates in section 8 (the other nine). **They are now refused earlier than that, by the
horizon gate**, because all thirteen carried `forecast.reviewed: true` on a horizon their own
configuration comment said had never been studied:

> HORIZON PROVENANCE: not studied. Value selected by Claude and authorized by James on 2026-08-09
> ("You select the numbers. I don't care what they are... If I ever decide to do a valuation of
> those companies I will study the matter."). MUST be revisited before this company is published.

A blanket authorization is not a review. The flag was reporting one that had not happened, on the
single input this project's own notes say has twice determined the **sign** of the abnormal earnings
stream rather than merely its length — and the fleet-wide test asserted that every shipped config
must be authorized, which made saying so a build failure. That test now asserts the true invariant
instead: `forecast.reviewed: true` and a `companies/<TICKER>.forecast.json` on disk must agree, in
both directions. Neither is valid without the other.

**No published number moved.** All thirteen were already refused by a later gate, so the change
alters which refusal message you see, not which companies publish. What it buys is that the
configuration no longer asserts something untrue.

The practical consequence for a forecaster: a company you pick up will now refuse at the *first*
gate rather than the third, and the refusal will tell you to choose a horizon. That is the correct
order — there is no point diagnosing a funding plan for a forecast period nobody has chosen.

This is the system working, not a fault. Every one of the thirteen is a mechanical default overlay
with constant-growth drivers, and a constant-growth forecast can never satisfy section 8's terminal
condition: if return on equity exceeds the cost of equity and growth is constant and positive,
abnormal earnings growth persists forever. Behind the horizon gate, those refusals are all still
waiting.

**Do not clear any of these with `reviewed: true`.** Not the horizon flag, not the funding flag, not
the convergence flag. The four funding refusals carry a three percent buyback the plan cannot fund —
and in Coca-Cola's case the company's own disclosure says it repurchases only enough stock to offset
employee option dilution, roughly a thirtieth of that. The rest have not been forecast by anyone.
They need real forecasts, which is what this kit is for. Clearing a gate to make a company publish is
exactly the failure the gates were built to prevent.

The valuation workflow shows a red X and will keep showing one until each company has a real
forecast. That red X means "companies are awaiting human review," which is the signal it was built
to give. The check that indicates health is the regression harness, and it is green.

No payload-free number on this system should be quoted for any company, gated or not — and the
engine enforces that rather than relying on anyone remembering it.

## 10. Where the two forecast companies stand

**PepsiCo — published and reproducible, EXCEPT `bear`, which needs a fresh horizon (2026-08-14).**
The whole four-round protocol was completed on 2026-08-12 and the reviewed forecast became a
repository artifact on 2026-08-13 (`companies/PEP.forecast.json`). `base` (N=12) and `bull` still
pass every gate cleanly as of the 2026-08-14 fleet run: Gate A/B, funding, and terminal payout all
PASS, four-method tie held to machine precision. **`bear` (N=12) now fails Gate A** on a live
re-dispatch — the fix described in "What changed in v6" caught this; the pre-fix code could not.
Its discarded tail is 2.0% of value against the 1% ceiling, on a slow decay factor of 0.899 — the
same drivers that passed on 2026-08-12 no longer clear the gate on 2026-08-14's rates, with nothing
about the forecast itself changed. Do not quote `bear`'s $75.7993 figure as currently reproducible;
it was correct on the day it was verified and is not correct today. A fresh horizon search for
`bear` is open work — see `docs/HANDOFF-NEXT-SESSION.md`. **`base`'s $110.980452128219 tied /
$116.2259 headline and `bull`'s $124.4046 remain live and reproducible**, subject always to the
standing warning that headline values move with live rates and should be re-read from
`outputs/PEP_summary.csv` / `outputs/PEP_scenarios.csv` rather than quoted from this document.

Section 9 of v4 listed PepsiCo rework that has since been done: the horizon was re-examined against
the actual driver path and landed at N=12, and `terminal.payout_ratio: 0.78` was chosen and
reviewed. That list is closed. **What is NOT closed** is that Round 2's original payout of 0.84 was
stated as "dividends plus net repurchases", and section 3's dividends-only rule means any future
restatement of that build has to express the buyback through `buyback_rate` instead.

**Coca-Cola — Rounds 1, 2 and 3 done (2026-08-13/14). Round 4 next, now that the multi-scenario fix
is in.** Round 1 landed 2026-08-13 as a qualitative brief. Round 2 found the base case's horizon
mechanically at N=14 (`docs/KO-Round2-Base-Case-Drivers-2026-08-13.md`): tied $36.2656, headline
$32.7108 at the time it was published (re-verify before quoting — see the standing live-rate
warning above; a same-driver re-dispatch on 2026-08-14 read $39.2291 tied / $35.0060 headline,
purely from rate movement). Round 3 found bull's own horizon at N=15 and bear's at N=14, each
independently dispatched through the single-scenario path rather than the (at the time) broken
multi-scenario one (`docs/KO-Round3-Bull-Bear-2026-08-14.md`): bull tied $48.1358 / headline
$42.0646; bear tied $24.5075 / headline $23.3063, both as of their own verification runs. Round 4 —
the combined `companies/KO.forecast.json` machine file — can now be dispatched through the fixed
multi-scenario path per the addendum in section 8, with the same expectation the PepsiCo finding
sets: verify it live, do not assume the Round 2/3 figures are still current.

Three things from Coca-Cola's Round 1 a forecaster should still know before picking up any further
company:

- It is refused by the **funding gate** rather than the truncation gates on the payload-free
  default overlay, and the fix is a real distribution policy: Coca-Cola's own investor disclosure
  states it repurchases only enough stock to offset employee option dilution, net repurchases were
  $0.4bn in 2025 against $8.8bn of dividends, and the share count is *higher* than it was in 2018.
  The default overlay's three percent is roughly thirty times the company's stated policy.
- Its 2025 anchor balance sheet is **not** a representative operating base: net operating assets
  jump 15.3% year on year almost entirely because a $6.1bn contingent-consideration liability was
  paid. Nothing in the outputs flags it. Check your anchor's balance sheet for one-off settlements
  before you set asset intensity.
- Its anchor year retained essentially nothing, which makes its first forecast year's abnormal
  earnings growth the largest in the schedule for a reason that has nothing to do with the business.
  See section 7.4.

## 11. What this supersedes

- **`docs/FORECASTER-KIT-v5-2026-08-13.md`**, archived at
  `archive/FORECASTER-KIT-v5-2026-08-13-SUPERSEDED.md`. Everything in it is carried forward except
  the version number, the preamble, the new subsection under section 8, and section 10 (Coca-Cola's
  status and PepsiCo's `bear` scenario, both of which moved since v5).
- **The claim that `run_scenarios.py`'s multi-scenario path checks only completeness and the tie.**
  It now also checks Gate A, Gate B, funding, and terminal payout, per scenario. See "What changed
  in v6" and section 8's addendum.
- **`docs/FORECASTER-KIT-v4-2026-08-12.md`**, archived at
  `archive/FORECASTER-KIT-v4-2026-08-12-SUPERSEDED.md`. Everything in it is carried forward except
  the version number, the preamble, section 9 (gated companies — the refusal reason changed), section
  10 (PepsiCo's outstanding list, now largely closed), and the renumbering of what were sections 7-10
  (now 8-11) to make room for the new section 7.
- **The instruction to compare the `rore` column against the `coe` column**, which lived in
  `pipeline/aeg_schedule.py` rather than in the kit and which no version of the kit ever repeated.
  It is wrong for the nominal series that file publishes. Section 7.3 states the correct test and
  `pipeline/test_aeg_schedule.py` check 6 pins it.
- **The fleet-wide assertion that every shipped company configuration must carry an authorized
  horizon.** Replaced by a two-way consistency check between `forecast.reviewed` and the presence of
  a reviewed forecast file. This is a strengthening: the old assertion could only be satisfied by
  authorizing horizons nobody had chosen.
- `docs/FORECASTER-KIT-v3-2026-08-12.md`, archived at
  `archive/FORECASTER-KIT-v3-2026-08-12-SUPERSEDED.md`, and every earlier version.
- **The claim that `funding: reviewed: true` clears the funding gate.** It did not, before this
  version — see section 5. It does now.
- `archive/PEP_Guest_Forecaster_Package_2026-08-10.md` **section 0 only** — the warning that
  PepsiCo's retention is "pinned at 6.3%" and the instruction to override it deliberately. Under
  the canonical closure retention is not an input at all; it is the residual. Replace that section
  with the two-of-three rule in section 2 above. **The rest of that package — the four-round
  protocol, the moat reasoning, the evidence on persistence — remains current and should still be
  read in full.**
- `docs/FORECASTER-KIT-UPDATE-2026-08-11.md` — folded into this document long since; that file is
  now just a pointer here.
- **v2 of this kit, section 6 in particular.** It told you the convergence period would make your
  truncation right for you, gliding earnings onto the normalized line and booking the difference.
  It no longer does anything of the kind. See `docs/AEG-CONVERGENCE-RETIRED-2026-08-12.md`.
- **Any claim that the engine detects a cyclical peak.** It does not, and it is not meant to. A
  level a company has sustained for several years is, as far as the normalizer is concerned, the
  normal level; it measures departure from the recent sustained trend over a four-year window and
  looking back further is speculative. Ruling out a cyclical truncation is your job, and section 8
  is where the rule is stated.

The underlying worry in that struck section was correct and was vindicated. It flagged a return on
retained earnings distorted by a single anchor year as the most consequential unreviewed number in
the engine, because it can determine the *sign* of the abnormal earnings stream rather than merely
its length. That is exactly the defect found on 2026-08-11 in the normalized-earnings benchmark, in
a second and unrelated location, and it did determine a sign: `+11.7263` to `−6.3403` per share
with nothing about the company changing. (Those figures are historical: they were convergence
increments, and increments no longer exist. The lesson stands; the numbers cannot recur.) Single-year rates driving permanent lines are a recurring
failure mode in this engine and should be treated as a standing suspicion. **The same standing
suspicion is why section 6 exists**: a company's continuing-period capital plan was, until v4, an
unexamined default rather than anyone's assertion — not because it moved the value (it provably
does not, see section 6), but because "unexamined and green" is exactly the shape every prior
instance of this failure took.

---

*v5, 2026-08-13. Section 7 (the AEG value test) is new; section 9 (gated companies) and section 10*
*(where the two forecast companies stand) are rewritten; former sections 7-10 are renumbered 8-11 with*
*no other content change. v4 is superseded and archived. No published number moves in this version.*
