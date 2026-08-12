# FORECASTER KIT — CURRENT VERSION (v4, 2026-08-12)

**This is the authoritative kit. Anything older is superseded — see section 10.** The copy in the repository at `docs/` is the source of truth; any other copy is a working copy.

> **Changing this document?** Follow `docs/KIT-CHANGE-PROCEDURE.md` first. A kit change is an end-to-end audit of the whole file plus four other places, not an edit to one section. Editing one section and leaving the rest is how this document went stale three times in a single day on 2026-08-12.

Valid against commit `451e33b` on `github.com/JamesKostohryz/aeg-valuation`. Regression harness green; four-method tie `8.396062e-16`, and as of v3 the published value is **wholly inside that tie** — there is no longer any component sitting outside it. v4 adds a gate; it does not touch the tie or move any published number (see section 6).

**What changed in v4.** Two things, both James's, both 2026-08-12, both scoped to the continuing period and its distribution policy — not the tie, not the truncation gates, not any published number.

1. **A new mandatory input: `terminal.payout_ratio`, section 6.** Sections 1-5 and 7-9 below describe the explicit forecast, years 1 through cfg_N. Nothing previously described what the company does once it reaches the continuing period, year cfg_N+1 onward — the raw Forecast-tab driver cells there hold a legacy scenario overlay unrelated to the forecaster's judgment, and it was never anyone's job to say what actually happens. It still isn't priced (see section 6 for why not), but it is now a deliberate, disclosed forecaster assertion instead of an unexamined default.
2. **A bug fix: `funding.reviewed` now actually works.** Section 5's escape hatch — write `funding: reviewed: true` to clear a REVIEW verdict — has been documented since 2026-08-11 but had no effect: the config loader never read the `funding` block from the YAML. Silent and inert, caught while wiring section 6's gate. No published number was affected (the four funding-gated companies were never meant to clear it), but the mechanism itself did not work until this version.

The four-round forecasting protocol itself — the qualitative brief, the moat-length judgment, the driver build, the review — is unchanged and still lives in `archive/PEP_Guest_Forecaster_Package_2026-08-10.md`. Use that document for the *process* and this one for the *rules the engine now enforces*. Where the two conflict, this one wins.

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
**normalized** net income — the same `normalized_eps_N` gate B already computes, section 7 — that
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
know why a company's value is what it is, that is sections 1 through 5 and 7 below; this section
only says what happens to the cash once the story is over.

## 7. WHERE YOUR FORECAST IS ALLOWED TO STOP — read this before you choose a horizon

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

## 8. Companies currently gated — all of them

As of `5069bc8`, **every one of the fourteen companies is refused and none publishes a valuation.**
Four are refused by the funding gate (`AAPL`, `COST`, `KO`, `WMT`); the other ten are refused by the
truncation gates described in section 7.

This is the system working, not a fault. Every one of those ten is a mechanical default overlay with
constant-growth drivers, and a constant-growth forecast can never satisfy the terminal condition:
if return on equity exceeds the cost of equity and growth is constant and positive, abnormal
earnings growth persists forever. Eight of the ten have an abnormal earnings stream that is still
*growing* at their stop year. Nike and Pool are flat, so what their truncation discards is worth
sixteen and thirty-four times the entire company value. Only AT&T's is decaying.

**v4 note.** None of the fourteen carries a `terminal.payout_ratio` yet, so section 6's gate would
refuse every one of them too — but it never gets the chance to say so: every company already stops
at the funding gate or the truncation gates first, whichever it hits, and gates refuse in that
order. The gated set is unchanged by v4. The first company to clear both of the existing gates will
be the first to actually see section 6's refusal, and will need a chosen, reviewed payout ratio
before it can publish.

**Do not clear any of these with `reviewed: true`.** The four funding refusals carry a three percent
buyback the plan cannot fund; the ten truncation refusals have not been forecast by anyone. They
need real forecasts, which is what this kit is for. Clearing a gate to make a company publish is
exactly the failure the gates were built to prevent.

The practical consequence: the valuation workflow shows a red X and will keep showing one until a
real forecast exists. That red X means "companies are awaiting human review," which is the signal it
was built to give. The check that indicates health is the regression harness, and it is green.

No payload-free number on this system should be quoted for any company, gated or not — and now
the engine enforces that rather than relying on anyone remembering it.

## 9. Still outstanding for PepsiCo

Round 2 has not been reworked. Its payout of 0.84 was explicitly "dividends plus net repurchases"
and needs restating on a dividends-only basis with the buyback expressed through `buyback_rate`.
Its capital-honesty conclusions leaned on `noa_growth` and `target_flev` while both were dead — one
inert, one silently discarded — so they need re-deriving rather than resubmitting. Its published
reference figures (no-growth anchor 131.47 per share, headline 274.65, cumulative abnormal-growth
contributions of 8.80 at year two, 18.21 at year four, 144.36 at year thirty) came from a run
carrying the thirty-year horizon defect and must be re-run before Round 3 reasons against them.

**Tested against gate A on 2026-08-12, cfg_N=4, the actual Round 2R driver build (not a default
overlay): REFUSED.** Abnormal earnings growth is negative and still diverging at year 4 (−$0.086 to
−$0.124/share, a 44% worsening, year-on-year factor 1.442 — factors at or above 1 refuse outright,
section 7). Four years is not long enough on this build; the horizon needs to be re-examined against
the actual driver path, not assumed from Round 1's qualitative moat-length judgment. Funding passed
cleanly at cfg_N=4 (implied dividend $6.03–$6.69/share, all four years) — the open question is the
truncation point, not the capital plan for the explicit years.

**v4 adds one more item to the rework list.** Once a horizon is found that clears gate A, PepsiCo
will also need a `terminal.payout_ratio` — a deliberate answer to what fraction of normalized
earnings PepsiCo pays out once its story is finished, distinct from and not derived by carrying
forward the explicit years' buyback assumption.

And the moat-length question needs settling on its own, separately from this submission.

## 10. What this supersedes

- `docs/FORECASTER-KIT-v3-2026-08-12.md`, archived at
  `archive/FORECASTER-KIT-v3-2026-08-12-SUPERSEDED.md`. Everything in it is carried forward except
  the version number, the preamble, and the renumbering of what were sections 6-9 (now 7-10) to make
  room for the new section 6.
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
  looking back further is speculative. Ruling out a cyclical truncation is your job, and section 7
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

*v4, 2026-08-12. Section 6 (terminal payout ratio) is new; section 5 documents a bug fix (funding.*
*reviewed now actually works); former sections 6-9 are renumbered 7-10 with no other content change.*
*v3 is superseded.*
