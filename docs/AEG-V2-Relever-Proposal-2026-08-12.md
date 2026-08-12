# AEG V2 Proposal — Re-levering the cost of equity on leverage, and NOA = CSE + NFO

**Filed 2026-08-12. GATED — proposal only, nothing built. Needs James's decision before any code
changes.**

Verified against `github.com/JamesKostohryz/aeg-valuation` at head `3937d5e`, by reading
`disclose.py`, `rate_feed.py`, `repoint_rates.py` and `pipeline/dupont_extract.py` directly.

---

## 1. What the live cost-of-equity path actually is today (confirmed by reading the code)

`repoint_rates.py` writes the Market Data cost-of-equity row as:

```
COE = real_rf + market_erp        (per tenor, both from the rate feed)
```

`idiosyncratic` is added afterward, but only inside `install_idio_hook()`, whose own docstring
says the hook defaults to zero and is populated only for a disclosure **sensitivity run** — the
tied headline valuation runs with it at zero. There is no `beta` anywhere in the codebase (checked
every `.py` file, including tests — zero matches). `market_erp` is sourced from
`erp_market_latest_annual.csv`, listed in `rate_feed.py` as a **global, market-wide** series, and
the module's own bounds comment says it is "VIX²-based near the anchor." It is the same number for
every company on a given day — it has no channel to respond to any one company's debt or equity
mix.

`repoint_rates.py`'s `install_idio_hook()` states this in so many words: *"COE — not the dormant
DCF re-lever layer — is the lever the headline valuation actually consumes."* There is a re-lever
layer in the workbook (referenced as "MM un/re-lever" in comments in both `rate_feed.py` and
`repoint_rates.py`), but the code explicitly says it is dormant and the headline number does not
read from it.

So: your premise is correct on every point. Today, a company can double its debt or retire all of
it and the discount rate does not move. What keeps that from being a value-neutrality problem is
the four-method tie plus the canonical operating closure (`patch_template_canonical_closure.py`):
net operating assets and operating income are driven independent of financing, and financing
absorbs as a residual, so a leverage change reallocates the same enterprise value between debt and
equity claims rather than creating or destroying value. That is Modigliani-Miller irrelevance
holding **by construction**, not because a risk premium is doing any work — there is no leverage
term in the risk premium to do that work. V2 is the fix: give the discount rate a channel that
actually responds to leverage, without breaking the tie that currently keeps the model honest in
its absence.

## 2. The recommendation (one path, not a menu)

**A. Re-levering rule: pure Modigliani-Miller Proposition II, no tax adjustment.**

```
r_e = r_u + (r_u − r_d) × (D/E)
```

Not the Hamada version with a `(1 − tax)` term. The engine already carries a `tax_rate` input, but
the AEG/residual-income valuation is built on **pre-financing operating income** — the canonical
closure drives operating income independent of financing, so there is no explicit interest tax
shield in the enterprise-side cash flow the discount rate is applied to. Multiplying the leverage
term by `(1 − tax)` would price a tax shield into the discount rate that has no matching cash flow
anywhere else in the model — a mismatch, not a refinement. It also matches how cost of debt is
already fed: `rate_feed.py` consumes `real_cod` directly, pre-tax, with no nominal or tax step. Add
a tax-shield question later, as its own gated item, rather than bundling it into this one.

**B. Unlevered rate: solved once at the anchor, held fixed across the forecast.**

Back out `r_u` a single time, at the anchor year, from what the model already has: today's actual
levered rate (`real_rf + market_erp + idiosyncratic`, i.e., the honest current cost of equity
including the disclosed idiosyncratic premium) and today's actual leverage. Then hold `r_u` fixed
as the company's business-risk premium for the whole horizon. This is standard MM: business risk
doesn't change year to year under a closure that drives operating assets and income; only
financial risk does, through the leverage path. Only the leverage term should move period to
period, not the whole rate.

**C. Leverage measure: market value at the anchor, then a fixed market-to-book multiple applied to
the model's own driven book equity for every forecast year — not raw book leverage throughout, and
not a period-by-period market solve.**

This is the part with a real trade-off, so here it is plainly:

- **Raw book leverage throughout** (using the engine's own `CSE`/`NFO` from `NOA = CSE + NFO`,
  which already drives `FLEV` in the DuPont decomposition) is simplest and introduces no
  circularity — but it breaks on exactly the companies this project cares about most. Apple's book
  equity has been driven toward zero, and at points negative, by a decade of buybacks (that is
  the subject the buyback-study file this session was pointed at was going to document — it isn't
  in the folder as filed; see the note below). Book `D/E` for a company like that is either
  enormous or a division by a near-zero or negative number, which would send the re-levered cost
  of equity to an unusable extreme. This isn't a hypothetical edge case for this project; it's the
  central one.
- **True market leverage, solved period by period** is the theoretically clean answer — market
  value of debt and market value of equity, MM's own units — but future market equity is the
  valuation's own output. Re-levering the discount rate on it every forecast year makes the model
  circular: the discount rate would depend on the equity value, which depends on the discount
  rate. Excel can iterate to a circular solve, but it means turning on iterative calculation in a
  workbook this project has deliberately kept single-pass and deterministic, specifically because
  every prior defect here has come from an added channel doing something silently wrong while the
  tie still reports green. I don't recommend opening that door for this change.
- **The recommended middle path:** compute the ratio of today's actual market equity value to
  today's book `CSE` at the anchor — a single observed number, not a solved one, since today's
  price and share count are already inputs the engine reads. Hold that multiple fixed, and apply
  it to the model's own **driven** book `CSE` in each forecast year to get a market-like equity
  proxy for that year: `E_proxy(t) = CSE(t) × (E_market,0 / CSE_0)`. Leverage for re-levering in
  year `t` is then `D(t) / E_proxy(t)`, using the debt path the two-of-three closure already
  produces. This responds to the forecast's own leverage decisions (a debt-funded buyback moves
  `D(t)` and `CSE(t)` together, and the proxy leverage moves with them), it needs no circular
  solve, and it doesn't blow up on a near-zero book equity company because the anchor multiple
  rescales it back to market terms before anything is divided. The cost is one added assumption —
  that the market-to-book multiple observed today holds across the forecast — which is a real
  simplification and should be disclosed as such, not hidden.

## 3. Net recommendation in one line

`r_e(t) = r_u + (r_u − r_d(t)) × [D(t) / (CSE(t) × E_market,0/CSE_0)]`, with `r_u` solved once at
the anchor from the current live rate and current leverage, no tax adjustment, and the anchor
market-to-book multiple held fixed and disclosed as an assumption.

## 4. What this does not yet resolve — flagging rather than deciding

- **`NOA = CSE + NFO` re-establishment.** `disclose.py`'s docstring names this as the second half
  of V2, alongside re-levering. The base/tied valuation already satisfies this identity by
  construction (`diagnose_T_tie.py` checks it directly). It breaks only on the **disclosed**
  (market-debt-adjusted) equity figure, because that adjustment currently adds the book-vs-market
  debt gap straight to equity without touching `NOA` — a bolt-on, not a re-partition. Re-levering
  the discount rate doesn't by itself fix that; it's a separate, smaller companion fix to
  `disclose.py`'s bridge, and I'd recommend doing it in the same landing since both are inside the
  V2 backlog note, but as a second, clearly-separated diff so either can be reviewed on its own.
- **The `AEG Buyback Study/00-METHODOLOGY-ADDENDUM-Generalization-2026-08-12.md` file you pointed
  me to does not exist in the folder as granted.** There is no `AEG Buyback Study` directory at
  all — I looked. I read the equivalent material directly from the code instead (`disclose.py`'s
  own docstring, `rate_feed.py`, `repoint_rates.py`), which is what your instructions call for
  regardless, so this proposal doesn't depend on that file. But if section 2 of that document
  contains evidence or a framing I haven't seen — the buyback angle in particular, since it
  bears directly on point C above — I'd want it before we land anything, not just before we start.
- **`AEG_SYSTEM_ARCHITECTURE_AND_BUILD.md`**, cited by `disclose.py` as carrying the "V2 backlog"
  entry this whole task is named after, is also not in the repository at head `3937d5e`. Worth
  tracking down or reconstructing so the backlog item has one home instead of a dangling
  reference.

## 5. What I'd need from you to proceed

One decision: approve the net recommendation in section 3 (rule, unlevered rate, leverage
measure), or tell me which of the three you want changed. If approved, next step is a small
standalone script (in the shape of `repoint_rates.py`'s existing hooks) that computes `r_u` and
the per-year re-levered `r_e(t)` and writes it the same way `install_idio_hook` writes
`finrate_idio` — additive onto the existing COE row, defaulting to a no-op so the tie is provably
unaffected until the hook is turned on — then a full fleet re-run and tie check before anything is
called done.
