# The convergence increment is retired. What it did, why it is gone, and what replaced it.

2026-08-12, on James's ruling. This is the record the ruling asked to be kept, so that the
arithmetic is recoverable if it is ever wanted again, and so that nobody rebuilds it by accident.

---

## What it did

From year `cfg_N`, the module built a normal continuation of earnings growing at the value-neutral
rate, cost of equity times retention, with inflation on top. It then glided actual earnings per
share geometrically onto a normalized level over `K` years, booked the resulting abnormal earnings
growth with the engine's own formulas, and **added the present value of that stream to the engine
value. The sum was the published headline.**

The arithmetic, preserved verbatim:

```
b        = ret[N] / eps[N]
ratio    = norm_eps_N / eps[N]
npath[N] = eps[N]
npath[t] = npath[t-1] * (1 + r_real(t) * b) * (1 + pi(t))     r_real = (1+rho_t)/(1+pi_t) - 1
glide[N] = eps[N]
glide[t] = npath[t] * ratio ** ((t - N) / K)
normal_t = (1 + pi_t) * glide[t-1] + (rho_t - pi_t) * b * glide[t-1]
aeg_t    = glide[t] - normal_t
dfE[t]   = dfE[t-1] / (1 + rho_t)
contrib  = aeg_t * dfE[t-1] / (rho_LR * (1 + pi_t))
value    = engine_intrinsic + sum(contrib)
```

It had one property worth recording: when the normalized level equaled actual earnings at
`cfg_N`, every convergence abnormal earnings growth was exactly zero and the corrected value
equaled the engine value to the penny. It only ever moved a number when the forecast stopped
off-trend.

## Why it is gone

**It was being read as an oracle of the business cycle. It never was one, and it cannot be one.**

Deciding whether a forecast stops at a cyclical peak is the forecaster's job, and the rule that
defines a legitimate horizon already implies it. The explicit forecast runs until there is no
projected abnormal earnings growth left. A reversion from a cyclical peak back to trend
*necessarily creates* abnormal earnings growth — that is what a reversion is, in this framework —
so a forecast truncated at a peak cannot satisfy the rule in the first place. The convergence tool
was only ever meant to correct a small residual inconsistency in where the forecaster stopped.

Once that is said plainly, the tool fails its own justification. A correction that only matters
when it is small is not worth having. A correction that is large means the forecast is wrong, and
the answer to a wrong forecast is to send it back, not to patch it into a number that is neither
the forecaster's view nor a corrected one, and that nobody owns.

**Deleting it also closes the only hole in the correctness oracle.** The increment was computed on
the equity leg alone and therefore sat outside the four-method tie — the one component of a
published value that the system's central check could not see. The published value is now the
engine value, wholly inside the tie. That hole is closed by deletion rather than by building the
operating-income and net-financial-expense legs to match it, which was the alternative and was a
gated spreadsheet change nobody had approved.

On the evidence, deleting it costs nothing: across the ten companies that valued on 2026-08-11 the
increment was under a quarter of one percent of value on every name.

## What replaced it: two gates on the truncation point

Both refuse. Neither adjusts. Both are cleared only by an explicit human assertion in the company
configuration, exactly as the horizon and funding gates are.

**Gate A — the terminal condition. Abnormal earnings growth must be spent at year N.**

The engine forces abnormal growth to zero from year `N+1`, because that is what the continuing
period means. That truncation is legitimate only if the forecast had already brought it to zero.
Forcing a small, declining residual to zero breaks nothing. Forcing a large or a *rising* one to
zero silently discards value the forecast itself says exists.

The test is read off the engine's own rows. With `d = AEG[N] / AEG[N-1]`:

- `d >= 1` — the stream is still growing at the stop year. The discarded tail does not converge at
  all, so there is no threshold to argue about: the horizon is simply too short. REFUSE.
- `d < 1` — the discarded tail is the geometric continuation, `contrib[N] * d / (1 - d)`, and it
  must be under `TAIL_FRAC_WARN`, one percent of value. Otherwise REFUSE.

The threshold is on the **value discarded**, not on the level of abnormal growth. That is what
makes it economically meaningful rather than arbitrary.

**Gate B — the neutral level. Earnings at year N must sit at the normalized level.**

Unchanged in substance from the old guard: `|eps[N] - norm[N]| / eps[N]` must be under
`GAP_FRAC_WARN`, fifteen percent. What changed is that failing it now refuses instead of
correcting.

`normalized_eps_at_N` survives, and only as this gate's input. It no longer moves any number, so
the properties of its estimator now set a refusal threshold rather than a published value.

## A ruling that must not be re-litigated

**A level a company has sustained for several years is the normal level.** The normalizer measures
departure from the recent sustained trend, over a four-year window, and looking back further is
speculative. It is not a judge of the business cycle and must not be made into one.

On 2026-08-11 this chat reported as a defect that the normalizer "absorbs" a cycle building over
three or more years and therefore fails to flag it. That framing was wrong. It graded the tool
against a "true trend" that existed only because the synthetic test was constructed with one. Under
the specification, three years of held earnings *is* the normal level and the tool reported it
correctly. The window is not to be widened. The finding document from that day,
`AEG-FINDING-Normalizer-Window-2026-08-11.md`, is superseded on that point and should be read only
with this correction attached.

## What was deleted, so it is not looked for

- `test_convergence_start.py` — its assertions were that a peak marks value down and a trough marks
  it up. There is no longer any mark. Property 8 is now the two refusals above, covered in
  `test_convergence.py`, and unlike the old increment it is fully inside the four-method tie.
- The convergence re-run on the idiosyncratic sensitivity workbook in `run_company.py` — a second
  full engine recalculation whose only purpose was to price an increment that is now identically
  zero.
- `trend_estimate=OK|SUSPECT` in the convergence output — it encoded the wrong framing above. The
  two trend rates remain, as information, with no verdict attached.

`convergence_value_ps` and `headline_value_pre_convergence_ps` are still written to
`<TICKER>_status.csv` so existing readers do not break, and are now identically zero and equal to
the headline respectively. They are marked with `convergence_adjustment,RETIRED_2026-08-12 (inert)`
alongside. Do not present them as live.

## The consequence to expect on the fleet

On 2026-08-11 measurements, **every one of the ten companies that valued fails gate A.** Eight have
an abnormal earnings stream that is still growing at the stop year; Nike and Pool are effectively
flat, so their discarded tails are sixteen and thirty-four times the whole company value; only AT&T
is decaying, and its tail is about ten percent of value. All fail.

This is the correct and honest state, and it is not evidence that the gate is too strict. Those are
payload-free default overlays with mechanical constant-growth drivers, and **a constant-growth
forecast can never satisfy the terminal condition by construction** — if the return on equity
exceeds the cost of equity and growth is constant and positive, abnormal earnings growth persists
forever. The gate makes the standing rule that no payload-free run may be quoted mechanical instead
of a convention someone has to remember.

Expect the valuation workflow to refuse the entire fleet until real forecasts exist. That is the
system working.
