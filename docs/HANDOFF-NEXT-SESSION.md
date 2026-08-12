# Handoff — the engine is finished. Do not improve it. Finish the product.

Written 2026-08-12. Paste this whole file into the next chat as its first message.

---

## The instruction, and why it is right

James's instruction is that the tinkering stops and the product gets finished. He is right, and the
reason is worth stating so you do not drift back into the pattern.

Every defect found in the last week was found in a component that only a real forecast exercises,
using mechanical default overlays nobody is allowed to quote. The engine was being polished against
inputs that are not the product. **The binding constraint on finishing is not engine quality. It is
that no company has a real forecast in it.** Do not go looking for the next defect. There will
always be one.

## What is true right now

Tip of `main` is `451e33b` (as of 2026-08-12, after landing the terminal-payout gate --
see `docs/FORECASTER-KIT-v4-2026-08-12.md`). Prior to that, tip was `8d04369`. **Regression harness
green.** Four-method tie `8.396062e-16`, and the published value is wholly inside it -- the new gate
is provably outside anything that could move it (kit v4 section 6).

**The convergence increment was retired on 2026-08-12.** It used to glide earnings onto a normalized
level and add the booked abnormal earnings growth to the value. It is gone, and with it the only
published component the four-method tie could not see. Record and retired arithmetic:
`docs/AEG-CONVERGENCE-RETIRED-2026-08-12.md`.

**Two gates replaced it, and they refuse rather than adjust.** Gate A: abnormal earnings growth must
be spent at the stop year — still growing means refuse outright, since the discarded tail does not
converge and the horizon is simply too short; decaying means the tail must be under one percent of
value. Gate B: earnings at the stop year within fifteen percent of the normalized level.

**All fourteen companies refuse and nothing publishes.** Four on funding (`AAPL`, `COST`, `KO`,
`WMT`), ten on truncation. This is correct: a constant-growth default overlay can never satisfy the
terminal condition, so the gate has made "no payload-free run may be quoted" mechanical instead of a
convention. The valuation workflow is red and stays red until a real forecast exists. **Do not
investigate the red X. Do not clear any gate to make a company publish.** The health check is the
regression harness.

## The documents, and which is authoritative

- `docs/FORECASTER-KIT-v4-2026-08-12.md` — **the kit. The repository copy is the source of truth**;
  the copy in `C:\Users\james\AEG-Project\` is a working copy. Section 6 is the rule that matters.
- `docs/KIT-CHANGE-PROCEDURE.md` — **read this before changing anything a forecaster relies on.** A
  kit change is an end-to-end audit of the whole file plus four other places, not a section edit.
- `docs/AEG-CONVERGENCE-RETIRED-2026-08-12.md` — what was retired, why, and the ruling.
- `docs/AEG-FINDING-Normalizer-Window-2026-08-11.md` — **superseded on its central point.** Read only
  with the correction in the retirement document attached.

## Rulings that are closed. Do not re-litigate any of these.

- **A level a company has sustained for several years IS the normal level.** The normalizer measures
  departure from the recent sustained trend over a four-year window; looking further back is
  speculative. It is not a judge of the business cycle and must not be made into one. A finding on
  2026-08-11 claimed otherwise and was overruled.
- **Ruling out a truncation at a cyclical peak or trough is the forecaster's job**, enforced by gate
  A, not by any algorithm reading the cycle. None is to be built.
- **Gates refuse; they do not correct.** Nothing silently adjusts a forecaster's number.
- The four funding-gated companies stay gated.
- The rolling normalized level: tested and closed — rolling at trend growth injects abnormal growth
  into a period defined to have none, and books $186/share of phantom value on AutoZone.
- The single-year retention residual: measured, moves the answer by at most $0.0021/share across ten
  companies. Revisit only if a real forecast makes retention swing.
- **New 2026-08-12: `terminal.payout_ratio`, kit v4 section 6.** A mandatory, dividends-only,
  no-default input stating what fraction of normalized net income a company distributes once it
  reaches the continuing period (year cfg_N+1 onward) -- closing the gap where those columns held an
  unexamined legacy scenario overlay. Provably does not move published value (Valuation row 24 zeros
  every contribution past cfg_N; test_terminal_payout.py pins bit-identical intrinsic value at ratio
  0.0/0.5/1.0). Does not change the currently gated set -- every company already refuses at the
  funding or truncation gate first. No company config carries it yet.
- **Bug fixed 2026-08-12: `funding.reviewed` was inert from 2026-08-11 until now.** The config loader
  never parsed the `funding` block, so `funding: reviewed: true` had no effect on any run. No
  published number was affected. Fixed and pinned in pipeline/test_config.py.

## What "finished" means. Work only on this list.

**1. Put one real forecast through end to end and publish it.** PepsiCo is the candidate. Start with
`companies/PEP.yaml`, which says `horizon_N: 12` with `reviewed: true` while carrying a comment
saying it was never studied, when Round 1 concluded and James approved N = 4. **Note that N = 4 now
has to be re-tested against gate A rather than assumed** — under the new rule the horizon must run
until abnormal earnings growth is spent, and four years may not reach it. Then the rework: payout
restated on a dividends-only basis, and the capital-honesty conclusions re-derived rather than
resubmitted, since they leaned on `noa_growth` and `target_flev` while both were dead. Forecasting
is permanently human-in-the-loop, rule D1: bring James the judgment, automate only the plumbing.

**2. Settle the operating-income question, because it changes every number.** The vendor feed reports
fiscal-2025 operating income of $13,491m for PepsiCo against a reported GAAP $11,498m, the difference
being the Rockstar impairment, and the anchor-representativeness guard cannot see it because it tests
the margin the distortion was removed from. Verify against primary source before acting — the defect
register that raised it had its own top-ranked item collapse under checking.

**3. The cockpit.** Equity and enterprise side by side; the mode control becomes a presentation
control. Apps Script in `AEG_Cockpit_LIVE_stage18`, outside the repository. **It reads the output
CSVs directly, so the 2026-08-12 change breaks it silently rather than loudly**: the convergence file
header now reads `# truncation gates` and carries `aeg_at_N`, `aeg_decay`, `discarded_tail_frac` and
`convergence_adjustment=RETIRED_2026-08-12`. Any cockpit field labeled "convergence-corrected" must
be retired with the thing it names.

## How to work

James is a market analyst, not a programmer. Plain language, click-by-click when he must act, one
complete file rather than diffs, American spelling, prose over bullet lists, acronyms written out on
first use. One question with a recommendation, never a menu. Say plainly when he, the consensus, or
you are wrong — and when he pushes back, take it seriously: on 2026-08-12 he was right and the engine
chat was wrong about something it had ranked as its top finding.

Anything touching the tie, the anchor, or a published number is GATED: propose, get approval, build,
prove the tie green. Display and plumbing are safe.

**Verify before claiming.** Three confident attributions in three sessions were wrong, each one
command away from being caught. Read `cfg_N` off both vintages before comparing anything.

## Practical

**You can push, and you should do it yourself rather than asking James to.** There is no `git` and no
`gh` on the machine, but the token is at `C:\Users\james\Documents\GitHub\.claude-github-token` and
Python 3.14 is at `C:\Users\james\AppData\Local\Programs\Python\Python314\python.exe`. Python's TLS
rejects the network's intercepting certificate authority; **PowerShell works**, because it uses the
Windows certificate store. `UPLOAD-2026-08-12\push2.ps1` commits several files and deletions as one
commit via the GitHub Git Data API — edit the file list, the delete list and the message, and run it.
Never ask James for a token.

**Encoding trap:** PowerShell's `Get-Content` without `-Encoding UTF8` reads UTF-8 as ANSI and
silently mangles every em dash in a document. Use Python for text assembly.

**Running the suite:** the sandbox caps tool calls at about 178 seconds, so the full suite will not
finish in one call. Push and let the `AEG regression harness` workflow prove it, which is what was
done three times on 2026-08-11 and 2026-08-12. A stale `/tmp` fakes seven failures; run inside
`unshare --map-root-user -m sh -c 'mount -t tmpfs tmpfs /tmp && ...'`.

**Reproducing convergence arithmetic without recalculating:** `tools/study_recon.py` rebuilds it from
published CSVs and matches the engine to 1e-9.

## The finish line

The product is finished when one company has a real, reviewed forecast that passes both truncation
gates and the funding gate, published at a value James will put his name on, and the cockpit shows
it. Everything else is maintenance. If you find yourself proposing an improvement to a component no
live company exercises, stop and go do item 1.
