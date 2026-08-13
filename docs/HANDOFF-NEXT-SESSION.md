# Handoff — PepsiCo is verified. Two jobs remain: prove the system is general, and catch the cockpit up.

Written 2026-08-12, end of day. Paste this whole file into the next chat as its first message.
Supersedes every earlier version of this document.

---

## What James wants next, in his own terms

"My goal is to get the AEG valuation system to the finish line, so that I can use it to value any
company." Two explicit jobs:

1. **Assess whether the valuation system is in fact ready** to value any company — not just
   PepsiCo. PepsiCo passing is one data point, not proof of general readiness. See "Job 1" below
   for exactly what "ready" needs to mean and what to check before answering that question.
2. **Update the Cockpit** to reflect what changed in the last few days — specifically the ERP
   (equity risk premium) and COE (cost of equity) module work. See "Job 2" below for exactly what
   changed and what is already prepared and waiting to be applied.

---

## What is true right now

Tip of `main` on `github.com/JamesKostohryz/aeg-valuation` is `3311ca3` (2026-08-12). Confirm with
`git log` before trusting this — several sessions have pushed to this repo in parallel today.

**PepsiCo is genuinely verified, not just claimed.** A prior session (and a forwarded forecaster
document) asserted PepsiCo "clears every gate... for base, bull and bear alike." That claim was
checked directly this session, scenario by scenario, against the real gate-enforcing pipeline
(`run_valuation.yml` → `run_company.py`, which calls the truncation gates, the funding gate, and
the terminal-payout gate) — not the multi-scenario shortcut that actually produced the published
file (see Job 1, first bullet, for why that distinction matters). All three came back bit-identical
to what is committed in `outputs/PEP_scenarios.csv` and all three genuinely pass every gate:

| Scenario | N | AEG at N | Decay factor | Tail | Funding | Terminal payout | Tied value | Headline |
|---|---|---|---|---|---|---|---|---|
| Base | 12 | −$0.0082/sh | 0.378 | 0.64% | positive all 12 yrs | 78% of $9.29 EPS | $110.98 | $116.23 |
| Bull | 11 | −$0.0017/sh | 0.082 | 0.13% | positive all 11 yrs | 78% of $10.26 EPS | $124.40 | $129.64 |
| Bear | 12 | −$0.0996/sh | 0.898 | 0.96% | positive all 12 yrs | 78% of $5.60 EPS | $75.80 | $80.99 |

Probability-weighted (50/20/30) expected value: $103.11 tied / $108.34 headline, against a real
price of $144.38 — about 29% (24% headline-basis) overvalued. This matches `00-START-HERE.md` and
the forecaster's Round 4 document.

**Resolved since the first version of this handoff:** `companies/PEP.yaml` attributed a ruling to
James, written by a different concurrent session, that had not been independently confirmed. Asked
directly; James confirmed it in his own words, and the config comment was corrected to quote him
rather than paraphrase a secondhand attribution: *"N is not moat length. It is simply the explicit
forecast period. And forecasters must forecast through year 1 of the continuing period, where AEG
must equal zero and the level of EPS must be normalized or neutral."* Both conditions — this maps
exactly onto gates A and B (kit v4 section 7) and is now settled doctrine, not something to
re-litigate. `horizon_N` is chosen by extending the forecast until both conditions hold in the
final year, never by a competitive-durability judgment alone.

---

## Job 1 — is the system actually ready for any company?

PepsiCo passing does not by itself answer this. Three specific gaps to close before answering yes:

**1. `run_scenarios.py` structurally bypasses every substantive gate.** Traced this session: the
multi-scenario path that produced the published `PEP_scenarios.csv` calls only
`validate_load.py::validate()` (data completeness/provenance) and the four-method tie check. It
never calls `convergence.py` (truncation gates A/B), `funding_check.py`, or `terminal_payout.py`.
PepsiCo's numbers only turned out to be gate-clean because this session manually re-ran each
scenario one at a time through the single-scenario path (which does call the gates) and checked
the numbers matched. That is not a repeatable process — it is a manual workaround performed once.
**Before any second company goes through the scenario path, wire `run_scenarios.py`'s per-scenario
loop to call the same three gate modules `run_company.py` calls, and fail the scenario (not just
the batch) on any gate refusal.** This is GATED — propose the change, get James's OK, prove the
four-method tie is unaffected, before it lands. Until it's fixed, treat every multi-scenario
`_scenarios.csv` file for any company as unverified until independently spot-checked the way this
session checked PepsiCo.

**2. The onboarding path has never been proven end-to-end on a company that wasn't already deeply
studied by hand.** PepsiCo benefited from four rounds of forecaster work. Pick a second company —
ideally one of the ten currently refused on the truncation gate with only a default overlay
(`companies/*.yaml` with no reviewed forecast) — and run it through `onboard.py` and a real driver
build from scratch, timing how much of it required undocumented manual intervention. If onboarding
a second company takes materially more hand-holding than the kit and gates imply it should, that is
the actual measure of whether the system is "ready," not whether PepsiCo alone can be quoted.

**3. Confirm the regression harness is still green after today's parallel-session commits.** Several
sessions pushed to `main` today (`4ceed06`, `9cb0c05`, `196b69d`, `010e744`, the PEP round commits).
Each was individually tested by its author, but no single run has confirmed the harness green on
the actual current tip `3311ca3`. Push nothing until this is confirmed; if it's not green, that is
the first thing to fix, not a new company.

Only after those three are resolved is "ready to value any company" an honest answer rather than a
hope resting on one company's worth of manual checking.

---

## Job 2 — catch the Cockpit up

The Cockpit (`AEG_Cockpit_LIVE_stage18`, Google Apps Script, outside this repository) reads output
CSVs directly and has no gate of its own — it silently shows whatever the CSV headers say, correct
or not. Three concrete things changed underneath it in the last few days:

**1. ERP/COE work — landed, disclosure-only, does not touch the tie.** Full detail and reading
order in `ERP/00-ERP-INDEX.md` in this folder — read that file first, it is the index. Summary:
the wrong ERP collapse function was retired, the `erp_override` payload-validation hole was closed
(this was the actual mechanism behind the bad 2026-08-10 PepsiCo run that used a flat 154.69bp ERP
at every tenor instead of the real curve), preset B (2.90% total plateau) is confirmed the default,
the effective-ERP collapse now uses each company's own real distribution stream instead of a
synthetic growth guess, and every effective-rate number now publishes its methodology profile
alongside it. None of this touches the four-method tie (proven against the golden AAPL test, 32/32
cases, 8.0e-16). **Check whether any Cockpit field displays an ERP or COE number, a methodology
label, or a "flat ERP" style figure — if so it may now be reading a stale field name or missing the
new profile disclosure.**

**2. Cockpit Hole B — a fix is written and ready to paste, not yet applied.** `Control!C9` was not
being reset between tickers, a live Cockpit bug (not an engine bug). The corrected Apps Script
(v2.5, override block removed) is already written: `patches/AEG_Cockpit_AppsScript_v2.5_HoleB_Fix.gs`
in this folder. Full click-by-click paste instructions: `ERP/AEG-ERP-HoleB-Cockpit-Fix-2026-08-12.md`.
Earlier sessions could not apply this themselves because they had no way to reach an authenticated
Google session. **This Cowork session may be able to — if the connected Chrome browser is signed
into James's Google account, use the Claude-in-Chrome tools to open the Apps Script editor and paste
the fix directly, following the same instructions.** Try that first; fall back to walking James
through the doc's manual steps only if browser access isn't available or isn't signed in.

**3. The truncation-gate CSV schema change (2026-08-12) breaks any Cockpit field still labeled
"convergence-corrected."** The old `PEP_convergence.csv`-style file now has a `# truncation gates`
header and carries `aeg_at_N`, `aeg_decay`, `discarded_tail_frac`, and
`convergence_adjustment=RETIRED_2026-08-12` instead of the old glide-to-normal numbers. Any Cockpit
cell reading the old field names will now silently show blank, zero, or a stale cached value rather
than erroring. Audit every Cockpit reference to the convergence/truncation CSV and retire or rename
anything using pre-2026-08-12 field names.

**Not yet relevant to the Cockpit:** the V2 re-lever hook (`patch_relever_v2.py`, proposed and
LibreOffice-proven this week, see `docs/AEG-V2-Relever-Proposal-2026-08-12.md` and
`docs/AEG-V2-Relever-BUILT-Verification-2026-08-12.md` in the repository) has been built and proven
not to break the tie, but has **not been run on a real company and is not wired into any live
pipeline**. It produces no published numbers yet, so the Cockpit has nothing to catch up on there —
just be aware it's coming, scheduled as the next GATED engine item after this product-finishing work.

---

## Rulings closed. Do not re-litigate.

- Gates refuse; they do not correct. Nothing silently adjusts a forecaster's number.
- A level a company has sustained for several years IS the normal level (four-year window); looking
  further back is speculative and must not be made a business-cycle judge.
- The convergence increment is retired. The published value is the engine value, full stop.
- `terminal.payout_ratio` (dividends-only, mandatory, no default) is proven not to move published
  value and does not change which companies are currently gated.
- `funding.reviewed`'s config-parsing bug (fixed 2026-08-12) affected no published number.
- The four funding-gated companies (AAPL, COST, KO, WMT) stay gated until they have real forecasts.
- PepsiCo's base/bull/bear numbers above are independently gate-verified, not merely asserted. Do
  not re-run them from scratch; do use them as the reference values if anything looks different.
- **N IS NOT MOAT LENGTH** (James, 2026-08-12), verbatim: "N is not moat length. It is simply the
  explicit forecast period. And forecasters must forecast through year 1 of the continuing period,
  where AEG must equal zero and the level of EPS must be normalized or neutral." Round 1 of the
  protocol therefore ends in a qualitative view, not a horizon; N is found mechanically in Round 2
  by extending the forecast until Gate A and Gate B both hold. Evidence:
  `docs/FORECASTER-KIT-v5-2026-08-13.md` section 8, and the Coca-Cola Round 1 brief.
- **The AEG value test is real RoRE against the real cost of equity** — equivalently, real EPS
  growth against the real cost of equity times the PRIOR year's retention rate. It is NOT nominal
  `rore` against nominal `coe`; that comparison disagreed with the engine in 8 of Coca-Cola's 12
  forecast years. Settled 2026-08-13 by reading MODEL_TEMPLATE Valuation rows 22 and 23 directly.
  Evidence: kit v5 section 7, pinned by `pipeline/test_aeg_schedule.py` check 6.
- **The thirteen unforecast companies are `forecast.reviewed: false` and stay that way** until each
  has a real forecast. They now refuse at the horizon gate rather than the funding or truncation
  gates. This moved no published number. Do not flip any of them back to clear a red build; the
  fleet-wide test now checks `forecast.reviewed` against the presence of a reviewed forecast file in
  both directions, so flipping one back will fail the build for the right reason.
- **The engine does not value a company's "comparable"/adjusted earnings series.** It values
  reported operating income after replacement-cost depreciation, in real terms, per anchor share.
  For Coca-Cola the two diverged by about four percentage points a year over a decade. Kit v5
  section 7.5.

## Still open, not yet resolved

- `run_scenarios.py`'s gate bypass (Job 1, item 1) — the most important open item.
- The vendor-vs-GAAP PepsiCo operating income question (fiscal-2025 $13,491m vendor vs $11,498m
  GAAP, the Rockstar impairment) — flagged in an earlier handoff, not yet independently resolved
  against a primary source this session.
- Cockpit Hole B — written, not applied (Job 2, item 2).
- **Coca-Cola Round 2** — the driver build. Round 1 landed 2026-08-13
  (`KO-Round1-Qualitative-Brief-2026-08-13.md` in the project folder). Round 2 must set a fundable
  buyback rate (Coca-Cola's disclosed policy is anti-dilution only, ~0.1% of shares, against the
  default overlay's 3%), must not treat the 2025 anchor balance sheet as a representative operating
  base (a $6.1bn contingent-consideration settlement inflates net operating assets by 15.3%), and
  must find N mechanically rather than inheriting the config's unreviewed 12.
- **Whether the Cockpit displays `rore` or `coe` in a way that invites the retired comparison.** The
  kit v5 change corrected the module docstring and pinned the identity, but step 4 of
  `KIT-CHANGE-PROCEDURE.md` (the Cockpit) was NOT checked this session, because the Cockpit is Apps
  Script outside the repository. If any tab shows a RoRE-versus-COE comparison, it is showing the
  wrong test. Check before the next forecaster reads it.

## How to work

James is a market analyst, not a programmer. Plain language; click-by-click steps with the exact
page, the exact click, and what success looks like when he must act himself; one complete file
rather than diffs; American spelling; prose over bullet lists in anything meant for him to read as
a document (this handoff uses a table and lists because it is a working handoff, not a deliverable).
One question with a recommendation, never a menu. Say plainly when he, a forwarded document, or you
are wrong — this session found a forwarded "PEP clears every gate" claim was true in outcome but
false in process, and said so rather than taking it at face value.

Anything touching the tie, the anchor, or a published number is GATED: propose, get approval, build,
prove the tie green. Display and plumbing (including the Cockpit fixes in Job 2) are safe to do
directly.

**Verify before claiming.** This session caught a claim ("PEP clears every gate") that was true in
its numbers but false about the process that produced them — check the code path, not just the
output file, before repeating any completeness claim from a forwarded document.

## Practical

Push using the token at `C:\Users\james\Documents\GitHub\.claude-github-token` (classic PAT, repo +
workflow scope) against a sandbox clone — `C:\Users\james\Documents\GitHub\aeg-valuation` is a
**stale local checkout**; always reclone into the sandbox or check `git log` against the remote
before trusting it. Multiple sessions have pushed to this repo the same day — `git fetch` and
rebase before pushing, expect occasional conflicts.

The sandbox caps tool calls at roughly 178 seconds, so the full test suite will not finish in one
call — push and let the "AEG regression harness" GitHub Actions workflow prove it instead.

---

## The finish line

Unchanged: the product is finished when one company has a real, reviewed forecast that passes every
gate, published at a value James signs off on, and the Cockpit shows it correctly. PepsiCo now
satisfies the first half, verified rather than assumed. The two jobs above — proving the system
generalizes past one company, and catching the Cockpit up to what changed underneath it — are what
stand between here and being able to say the system is ready for any company, which is the actual
goal.
