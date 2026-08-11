# The normalizer is blind to a multi-year cycle. Finding, evidence, and one gated proposal.

Written 2026-08-11, the session after the landing session. Everything below was reproduced
against the committed outputs of run #77 and, for the central claim, against the live
`pipeline/convergence.py` module itself.

---

## 1. What was verified first, briefly

Both open verification items from the close-out are settled, and neither needed the Actions log —
run #77 wrote its verdicts into the repository as `outputs/<TICKER>_REFUSED.csv`, which is better
evidence than a log line because it is what the run actually published.

The four refusals are all the funding gate, word for word. Apple, Costco, Coca-Cola and Walmart
each carry a refusal beginning "UNFUNDED DISTRIBUTION," with the implied dividend negative in
every forecast year for the first three and in eight of ten for Walmart. The inference in the
close-out was correct.

AutoZone, Home Depot and McDonald's were indeed convergence-review refusals before, so they
cleared for the right kind of reason. But the attribution in the close-out was wrong. It credited
the normalizer repair. The evidence says the canonical operating closure did most of the work,
because the earnings path itself changed and a normalizer cannot move an earnings path — only the
line drawn against it. Home Depot's earnings per share at the horizon went from 920.08 to 28.16;
AutoZone's first convergence year from 519.74 to 231.78; McDonald's from 66.88 to 19.69. Home
Depot's no-growth value per share barely moved across the same runs, 229.61 to 229.14, and the
anchor share count is identical at 997 million, so the old per-share path was running away from a
stable per-share base. Published values moved a great deal: Home Depot 2,173.77 to 313.49,
McDonald's 338.31 to 192.21, AutoZone 1,301.01 up to 1,996.44. They now sit in arguable places
against price where the old ones did not.

## 2. The method used for everything that follows

I rebuilt `converge_valuation` and `normalized_eps_at_N` outside the engine, reading the per-year
earnings, retention, cost of equity and inflation straight from the published
`<TICKER>_aeg_schedule.csv`, `<TICKER>_convergence.csv` and `<TICKER>_summary.csv` files. The
replica reproduces the published normalized level exactly and the published convergence abnormal
earnings growth to between 1e-9 and 1e-7 per share for all ten companies that valued. That
agreement is what licenses the counterfactuals below. The central finding was then re-confirmed by
calling the repository's own `convergence._normal_line_growth` directly, not the replica.

Nothing was changed, nothing was landed, and no published number was touched.

## 3. The finding

**The normalized line is estimated from a window that a real cycle contaminates, so the
normalizer detects a one-year spike and is close to blind to a cycle that builds over three or
more years — which is what an actual cyclical peak looks like.**

The mechanism is arithmetic and it is easy to see once stated. `_normal_line_growth` takes the
median of the year-over-year earnings growth rates across the last few forecast years, and
`normalized_eps_at_N` then walks the last four years forward at that rate and takes the median. At
the default window of four, the entire estimator lives inside years N−4 through N−1. A cycle that
has been building across those years is absorbed into the estimated trend, and the peak is then
declared normal.

Here is the live module's own arithmetic on a synthetic Home Depot path whose true trend is 5.27
percent a year, with a peak that puts terminal earnings 25 percent above trend. The correct
reading of the gap is 20.0 percent of earnings per share in every row.

| cycle builds over | window X | estimated trend | gap reported | guard |
|---|---|---|---|---|
| 1 year | 4 | 5.27% | 20.0% | REVIEW |
| 3 years | 4 | **13.37%** | **0.5%** | **PASS** |
| 3 years | 6 | 5.27% | 20.0% | REVIEW |
| 4 years | 4 | 11.46% | 0.7% | PASS |
| 4 years | 6 | 11.12% | 0.3% | PASS |
| 4 years | 8 | 5.27% | 20.0% | REVIEW |

The estimated trend of 13.37 percent against a true 5.27 percent is the whole story. The
estimator has eaten the cycle and called it growth.

The detection boundary is sharp and general: the gap is seen only when the window reaches back
past the cycle, roughly when X is at least the cycle length plus two. Sweeping cycle lengths of
one through six years against windows of three through ten reproduces that boundary in every
cell, at both a 25 percent and a 50 percent peak, and in both directions — a trough hides exactly
as well as a peak.

**What it costs.** On the Home Depot geometry, a 25 percent peak that builds over three years
books a convergence correction of +3.55 per share at the default window, against −45.64 per share
when the same peak is seen properly. Engine value is 313.26. So the engine would publish about
316.81 where the defensible number is about 267.62 — roughly eighteen percent too high — and it
would publish it with a green guard and no refusal, because the guard is fed by the same
contaminated estimate it is supposed to police.

**Why the tests did not catch it.** `test_convergence.py` asserts that the normalizer must fire on
a genuine peak, and it does test that. But the synthetic peak it uses is `_peak[8] *= 1.35` — a
one-year spike at the terminal year, which is precisely the one shape every window detects. The
test is right about the property and unlucky about the shape.

This is the same failure mode the close-out named as a standing suspicion, in a third location. It
was a single-year rate driving a permanent line in the forecast anchor, then again in the
value-neutral walk, and it is now a short contaminated window driving the permanent normal line.

## 4. Items 4 and 5 re-assessed, with evidence

**Item 4, the rolling normalized level, should not be built as described.** I tested it. Rolling
the normal line forward at the company's own trend growth rather than the value-neutral rate books
186.33 per share of convergence value for AutoZone, 32.91 for Home Depot and 18.61 for Merck — on
companies whose actual off-trend gap is approximately zero. The reason is structural: the module's
faithfulness property, that an on-trend company books exactly zero convergence abnormal earnings
growth, holds only because the continuation grows at the value-neutral rate. Roll it at trend and
you inject abnormal earnings growth into a period defined to have none, and the continuing-period
value behind it would have to be re-derived. The current behavior is correct. I recommend closing
item 4 rather than building it.

**Item 5, the single-year retention residual, is immaterial on current evidence.** Across all ten
companies, replacing `ret[N]/eps[N]` with the median retention across the forecast changes the
convergence value by at most 0.0021 per share, on AutoZone, against an engine value of 1,998.73.
Retention is stable year to year on this fleet — the full range is under a percentage point of
earnings for every name. The worry was reasonable and the fleet does not support it. The honest
qualification is that these are smooth mechanical overlays; a real forecast with a lumpy capital
plan could still make retention swing, so this is worth re-testing on the first genuine forecast
rather than closing outright.

**Item 6, the guard thresholds, are not the unstudied knob that matters.** The two thresholds
behave sensibly wherever the gap is measured correctly. The unstudied number is the lookback
window X, hard-coded to four, which decides whether there is a gap to measure at all. Across the
ten live companies, moving the window from four to six changes the convergence correction by a
factor of four on Home Depot, halves it on Pool, and doubles it on Procter & Gamble. No one has
ever chosen that number deliberately.

## 5. What I propose, and it is gated

I propose nothing that moves a published number yet, because the right repair is not obvious and
the wrong one is worse than the defect. Widening the window does not fix this — it only moves the
blind spot, and a cycle as long as the window defeats any fixed window.

**Step one, which is safe and which I recommend doing first: make the failure visible.** Add a
diagnostic that reports, alongside the normalized level, the estimated normal-line growth next to
a long-window growth rate taken across the whole forecast and across the restated history the
engine already holds. When the short-window estimate sits far above the long-run rate, the
estimator has absorbed a cycle, and a person can see it in one line of a comma-separated file.
This changes no valuation and refuses nothing; it only makes the contaminated case legible.

**Step two, gated, once you have seen step one on real names:** decide whether the normal line
should be estimated from the forecast path at all, or from the restated history, which is where
mid-cycle is actually observable and where a cycle cannot be confused with the analyst's terminal
judgment. That is the structurally right answer and it is a real build, not a tweak.

**Step three, also gated:** whatever is decided, X should become an explicit reviewed input in the
company configuration, the way `horizon_N` already is, rather than a default nobody chose.

Before anything in steps two or three lands, the four-method tie gets recalculated and proven
green, and `test_convergence.py` gains a multi-year hump case in both directions so this shape can
never pass again.

## 6. One small correction to the record

The docstring of `normalized_eps_at_N` states that Valuation row 7 "is constant-dollar." It is
not; it is nominal. Dividing row 7 by the engine's cumulative inflation index reproduces the real
earnings row exactly, to the last digit, on Home Depot, Procter & Gamble and AT&T. The decision
the docstring justifies — removing the inflation re-index — is still correct, but for a different
reason than the one written down: the growth rate is measured on that same nominal row, so the
walk is already nominal and re-indexing would double count. A comment that misstates the frame is
how the next person reintroduces the bug, so it should be corrected when the file is next opened.

---

## Standing state

Nothing landed this session. Commit `2c7401a` plus the outputs commit `39a2777` remain the tip.
The four funding-gated companies stay gated, per your instruction. The regression suite is
untouched and green as of the landing session.
