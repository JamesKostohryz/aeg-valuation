# Procedure: changing anything the forecaster relies on

**If you are editing the forecaster kit, or changing a rule the engine enforces on a forecast, stop
and follow this. It is short and it is mandatory.**

Written 2026-08-12, after a kit update that rewrote one section correctly and left three others
asserting things that had stopped being true the same day. That is the failure this exists to
prevent, and it is not an unlikely one: the kit is a single document describing a system that
changes underneath it, so a section-level edit is almost always an incomplete edit.

---

## The single source of truth

`docs/FORECASTER-KIT-v<N>-<date>.md` **in the repository** is authoritative. The copy in
`C:\Users\james\AEG-Project\` is a working copy. If they differ, the repository wins, and the
working copy should be refreshed from it rather than merged.

Never edit only the working copy. A kit change that is not pushed did not happen.

## When this procedure applies

Any time you change something a forecaster would act on differently. That includes a new or removed
gate, a changed threshold, a changed input name or meaning, a changed default, a changed refusal
message, a ruling about whose judgment something is, or a change in which companies are gated. It
also applies when the engine changes in a way that makes an existing sentence in the kit false,
even if nobody touched the kit.

It does **not** apply to internal refactoring, display plumbing, or anything a forecaster cannot
observe.

## The five places a change must land, in this order

**1. The engine, and the test that pins it.** The rule must be enforced in code and asserted in a
test before it is written down anywhere as true. A kit that describes a rule the engine does not
enforce is worse than no kit.

**2. The kit, audited end to end.** Bump the version, and then read the *whole document*, not the
section you changed. Specifically re-check every time:

- the **preamble**: the "valid against commit" line, and whether the headline statement of what the
  engine does is still accurate
- the **gated-companies section**: which companies are refused and for what reason — this goes stale
  faster than anything else in the document
- the **supersedes section**: what this version strikes, named explicitly, including previous
  sections of the kit itself
- any **worked figures**: a number quoted from a run that no longer exists must be marked historical
  or removed
- any sentence saying the engine will **do something for the forecaster** that it no longer does

A grep for the terms your change touches, across the whole file, takes thirty seconds and would
have caught all three misses on 2026-08-12.

**3. The company configurations**, if the change alters what a `reviewed: true` assertion means or
adds a new one. An assertion written under an old rule does not carry forward silently.

**4. The cockpit**, if the change alters a published field or a field's meaning. It is Apps Script
in `AEG_Cockpit_LIVE_stage18`, outside the repository, and it reads the output CSVs directly — so a
renamed or retired field breaks it silently rather than loudly. Anything the cockpit displays as a
label ("convergence-corrected", for instance) must be retired with the thing it names.

**5. The handoff**, `docs/HANDOFF-NEXT-SESSION.md`. Any ruling that must not be re-litigated goes in
its closed-rulings list, in one sentence, with the document that carries the evidence. This is what
stops the next session reopening a settled question.

## Archive, do not delete

Move the superseded kit to `archive/FORECASTER-KIT-v<N>-<date>-SUPERSEDED.md`. Forecasts were built
against it and their reasoning has to remain readable. But it must not be findable as current — one
current kit, everything else archived.

## Push it in the same commit

The engine change, the test, the kit and the handoff go up together. A commit that changes a rule
without changing the document that states the rule is the thing this procedure exists to stop.
`UPLOAD-2026-08-12\push2.ps1` commits several files and deletions as one commit.

## The check that closes it

After pushing, read the pushed kit — not the local one — and confirm the preamble's "valid against"
line names **the most recent commit that changed engine behavior**. Documentation-only commits made
after it do not need to bump it, and an outputs refresh certainly does not: the line answers "which
engine does this document describe," not "when was this file last touched."

So the failure to look for is a preamble naming a commit older than the last behavioral change. If
you find one, the audit in step 2 was not done, and the rest of the document is probably stale too —
go back and read the whole thing.

(This check was itself wrong when first written on 2026-08-12: it said the hash had to be the commit
just made or the one before, which flags a false positive the moment a documentation commit lands on
top. Corrected the same hour, by running it.)

## Standing rules that a kit change may not quietly overturn

These are settled. Changing any of them is a decision for James, not a documentation edit:

- The explicit forecast does not end until projected abnormal earnings growth is spent **and**
  earnings are at a normalized level. Both.
- Ruling out a truncation at a cyclical peak or trough is the **forecaster's** job. No algorithm
  does it, and none is to be built to do it.
- A level a company has sustained for several years **is** the normal level. The normalizer's window
  is four years and looking further back is speculative.
- Gates refuse; they do not correct. Nothing silently adjusts a forecaster's number.
- No gate is ever cleared by loosening a threshold. Only by a human assertion in the company
  configuration, with a note saying what was accepted and why.
- No payload-free run is quotable, for any company, gated or not.
