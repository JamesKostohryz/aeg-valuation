# AEG V2 relever — built and template-verified, not yet fleet-verified

**2026-08-12. Approved recommendation (docs/AEG-V2-Relever-Proposal-2026-08-12.md) is built:
`patch_relever_v2.py` (repo root, matching the `patch_template_*.py` naming convention). This
cloud session CAN recalculate — LibreOffice is installed here —
so I ran the base template through it, not just openpyxl formula inspection. What follows is
what that recalc actually showed, not a description of what it should show.**

## What was tested and what it proved

**1. Idempotent install, correctly wired.** Ran `install_relever_hook()` twice on a copy of
`MODEL_TEMPLATE.xlsx`; the second call made no further change. `COE` (Market Data row 26)
picked up exactly one `+G37`-style tag per column, appended after the existing formula — not
duplicated, not overwriting anything already there.

**2. The tie survives a real recalc, hook off vs. on, on the template's own base-company
fixture** (the AT&T-shaped placeholder data the template ships with — the same fixture the
repo's own regression tests run against):

| | hook OFF (baseline) | hook ON |
|---|---:|---:|
| Audit status | PASS — all identities tie | PASS — all identities tie |
| `max_identity_tie` | 1.89174897968769e-09 | 1.89174897968769e-09 |
| Equity value / share | 43.8126476791177 | 43.2819475502893 |

The tie residual is bit-identical between the two runs, while the price moved about 53 cents —
meaning the hook is genuinely live (AEG/ReOI/FCFE/FCFF all shifted together) and the four
methods stayed in agreement with each other at the same precision as before. That is the
result "prove the tie stays green" was asking for, on this fixture.

**3. The numbers move the direction MM would predict, and by a plausible amount.** At the
anchor, `L0` (leverage proxy) came out to 1.28 — a heavily levered proxy, consistent with this
being AT&T's balance sheet. `r_u` (unlevered) sits well below the baseline levered rate at
short tenors (3.13% vs 5.03% at tenor 1) and closer to it at long tenors, which is the expected
shape when stripping a real leverage effect out of a levered rate. The re-levered COE moved by
−27 to +13 basis points across the curve versus the un-re-levered baseline — a real, tenor-
varying adjustment, not a rounding artifact and not an explosion.

**4. Stress test: forced a forecast-period CSE to zero, to check the exact failure mode the
proposal was written to avoid (Apple-style near-zero book equity).** The `IFERROR` guard on the
period leverage proxy did what it was written to do — it did not throw or propagate an error
into the tie by itself. The overall tie DID fail once CSE was forced to zero, but running the
identical stress test against the **unpatched, un-relevered baseline template** produced the
exact same failure. That isolates the cause: forcing a balance-sheet line to zero breaks this
model's own pre-existing NOA/NFO/CSE mechanics regardless of whether this hook exists. The
relever hook does not introduce a new fragility here; it also does not fix a pre-existing one,
which was never its job.

## What this does NOT yet prove

This is the template's own placeholder company, not a real one, and definitely not Apple or
any of the fleet names on file. `AAPL` and the rest still need a real build with real EODHD
statement data, which this cloud session cannot fetch or recalculate against (no raw feeds
here — same limitation noted throughout this project). The mechanism is proven sound in
principle; a company-level number from it is not yet real and should not be quoted.

## What's staged, and what isn't

`patch_relever_v2.py` is written and template-tested. **As of 2026-08-12 it, this proposal, and
this verification/decision record are committed to the repository at `patch_relever_v2.py` and
`docs/`.** Per the gate: propose (done), get
sign-off (done), build (done), prove the tie (done on the template fixture) — the remaining
step before this lands is a real fleet re-run, which needs a session with the EODHD feeds. Next
session should: run `aeg_engine.build_model(..., resolve_debt_basis=...)` for each onboarded
company, apply `patch_relever_v2.install_relever_hook` + `turn_on_relever` after `repoint_rates.repoint`,
recalc, and confirm `max_identity_tie` stays at machine precision company by company before
calling any of it done — and before anyone quotes a re-levered number for Apple, PepsiCo, or
anyone else on the fleet.

## Decision, recorded 2026-08-12

James ruled: **schedule it, don't defer.** Not "considered and rejected," not "never reached" —
approved, built, and template-verified this session; the remaining work (a real fleet re-run
against EODHD data, then a landing decision on whether the re-levered COE is a disclosed line or
the new headline) is scheduled as the next GATED item in the product plan, sequenced after D1 in
`docs/AEG-Open-Defect-Register-2026-08-11.md` — not written off as an indefinite backlog note.
`disclose.py`'s docstring has been updated in the repository to say this (built, template-verified,
scheduled, pointing at this file and the proposal instead of the nonexistent
`AEG_SYSTEM_ARCHITECTURE_AND_BUILD.md`). This closes the open loop; no further ruling needed unless
the plan changes.

## One thing worth your read, not mine to decide

`Forecast!G60:AJ60` — the formula this session identified as the "dormant DCF re-lever layer"
`disclose.py` refers to — is left untouched, in place, still unreferenced by anything. It's the
right shape (no-tax MM) but the wrong leverage measure (raw book FLEV, period by period, which
is exactly what breaks on a buyback-shrunk balance sheet). I built the corrected version
alongside it rather than editing it in place, so the original is preserved for reference. Worth
deciding, at some point, whether that row should be deleted, relabeled as historical, or left
alone — not urgent, and not part of this landing.
