#!/usr/bin/env python3
"""run_company.py — the deterministic per-company valuation job. This is what a GitHub
Actions step invokes; it is also runnable locally in --cached mode for testing.

Pipeline (every stage deterministic, fail-loud):
  1. load + validate companies/<TICKER>.yaml            (config.py)
  2. stage raw statements: --cached DIR, or EODHD pull   (eodhd_puller.py)
  3. build the model from config                         (aeg_engine.build_model)
  4. recalc headless (LibreOffice)                       (recalc_lo)
  5. if a rate feed is available: re-point rates + install idio hook, recalc again
  6. run the completeness/provenance/tie GATES           (aeg_engine.read_results)
        -> ANY gate failure exits non-zero == a failed CI check == nothing ships
  7. if bonded + rate feed: Option-A disclosure bridge   (disclose.py)
  8. extract restated anchors / valuation / real series / manifest -> outputs/ CSVs

The engine + restatement stay in the sealed Excel; this job orchestrates and gates them.
"""
import os, sys, argparse, shutil
import openpyxl

# make the build_v2 modules importable when run from the pipeline/ dir
_HERE = os.path.dirname(os.path.abspath(__file__))
_BUILD_V2 = os.path.dirname(_HERE)
for p in (_HERE, _BUILD_V2):
    if p not in sys.path:
        sys.path.insert(0, p)

import config as CFG
import aeg_engine as AE
import extract as EX

RAW_FILES = {"is_csv": "REAL_IS.csv", "bs_csv": "REAL_BS.csv", "cf_csv": "REAL_CF.csv",
             "prices": "REAL_prices.csv", "dividends": "REAL_div.csv", "splits": "REAL_splits.csv"}


def _fail(msg, code=1):
    sys.stderr.write(f"\n[run_company] ABORT: {msg}\n")
    sys.exit(code)


def stage_raw(cfg, cached_dir, work_dir):
    """Return a files dict for build_model. Cached mode copies the six statement/market
    CSVs from cached_dir; EODHD mode pulls them (needs EODHD_API_KEY)."""
    files = {}
    if cached_dir:
        for key, fname in RAW_FILES.items():
            src = os.path.join(cached_dir, fname)
            if not os.path.exists(src):
                if key in ("is_csv", "bs_csv", "cf_csv"):
                    _fail(f"cached raw missing required {fname} in {cached_dir}")
                files[key] = None
                continue
            dst = os.path.join(work_dir, fname)
            shutil.copy(src, dst)
            files[key] = dst
        return files
    # --- EODHD live pull (production path)
    key = os.environ.get("EODHD_API_KEY")
    if not key:
        _fail("no --cached dir and EODHD_API_KEY not set; cannot stage raw statements")
    try:
        import eodhd_puller as EP
    except Exception as e:
        _fail(f"eodhd_puller import failed: {e}")
    # eodhd_puller writes the six CSVs into work_dir for this ticker (see its API)
    written = EP.pull_to_csvs(cfg["ticker"], key, work_dir)  # noqa: contract w/ puller
    for k in RAW_FILES:
        files[k] = written.get(k)
    if not all(files.get(k) for k in ("is_csv", "bs_csv", "cf_csv")):
        _fail("EODHD pull did not produce all three statement CSVs")
    return files


def resolve_price(cfg, files, cli_price):
    if cli_price is not None:
        return float(cli_price)
    if cfg["price_source"] == "override":
        return cfg["price_override"]
    # market: use the latest close in the staged prices file (production may pull live)
    pf = files.get("prices")
    if pf and os.path.exists(pf):
        import csv
        last = None
        with open(pf, newline="") as fh:
            for row in csv.DictReader(fh):
                c = row.get("Close") or row.get("close")
                if c not in (None, "", "null"):
                    last = c
        if last is not None:
            return float(last)
    _fail("could not resolve a price (no --price, no override, no prices file)")


def build_cost_of_debt(cfg):
    """Map config cost_of_debt into build_model's cod dict. For bond_list we let the
    build use the flagged statement-implied fallback, then the rate re-point overrides
    COD entirely with real_cod — so the initial value is a placeholder that never ships."""
    cod = cfg["cost_of_debt"]
    src = cod["source"]
    if src == "ytw_points":
        return {"ytw_points": cod["ytw_points"]}
    if src == "single_ytw":
        return {"single_ytw": cod["single_ytw"]}
    if src == "bond_list":
        # throwaway seed for the initial build; the rate re-point overrides COD entirely
        return {"single_ytw": cod.get("seed_ytw", 0.05)}
    return {}  # interest_implied -> statement-implied fallback (flagged), may fail if interest≈0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config", help="path to companies/<TICKER>.yaml")
    ap.add_argument("--template", default=os.path.join(_BUILD_V2, "MODEL_TEMPLATE.xlsx"))
    ap.add_argument("--cached", help="dir with cached raw CSVs (else EODHD pull)")
    ap.add_argument("--out-dir", default=os.path.join(_HERE, "outputs"))
    ap.add_argument("--work-dir", default=os.path.join(_HERE, "_work"))
    ap.add_argument("--rate-feed-dir", help="local dir with rate CSVs (testing)")
    ap.add_argument("--rate-feed-live", action="store_true",
                    help="fetch rate CSVs from the live rate-infra repo (production)")
    ap.add_argument("--price", type=float, help="explicit price (repro/test)")
    ap.add_argument("--vintage", default="unset", help="data vintage tag for the manifest")
    ap.add_argument("--payload", help="RUN-button forecast payload: JSON string or path to .json")
    args = ap.parse_args()

    cfg = CFG.load_config(args.config)
    tk = cfg["ticker"]
    os.makedirs(args.work_dir, exist_ok=True)
    print(f"[run_company] {tk}  config_hash={cfg['config_hash']}  bonded={cfg['bonded']}")

    # --- unsupported-knob guard: fail fast rather than emit a number that ignores a stated
    #     judgment. oi_adj_override sets in_oiadj0, which feeds ONLY an Audit identity requiring
    #     it to equal reported OI (Econ Statements anchors on reported OI directly) — so a real
    #     override silently breaks the tie instead of normalizing the anchor. Refuse with the
    #     reason rather than dying mid-tie. (rd_capitalize=true is inert too, but committed
    #     configs set it; that one is a tracked engine backlog item, not a hard refusal here.)
    if cfg["judgments"].get("oi_adj_override") is not None:
        _fail(
            "oi_adj_override is set, but it is NOT a working normalization knob yet: the economic "
            "restatement anchors on REPORTED operating income (Econ Statements S20 <- rep_oi), and "
            "in_oiadj0 feeds only an Audit identity that requires it to equal reported OI — so any "
            "real override breaks the four-method tie rather than repricing the anchor. To value on "
            "a representative base, repoint FY0 to a representative fiscal year instead. Leave "
            "oi_adj_override null until the normalized-anchor increment lands.")
    if cfg["judgments"].get("finlease"):
        _fail(
            f"finlease={cfg['judgments']['finlease']} is set, but the finance-lease add-back is NOT "
            "wired: in_finlease (Inputs B8) feeds no engine formula, and NFO is built as "
            "in_debt - in_cash - in_sti — so a non-zero finlease would silently NOT change NFO or "
            "equity. EODHD 'Total Debt' already includes capitalized finance leases for most names "
            "(so 0.0 is correct there); an extra add-back is an engine-backlog item. Refusing rather "
            "than emitting a valuation that ignores the lease obligation you entered.")

    files = stage_raw(cfg, args.cached, args.work_dir)
    price = resolve_price(cfg, files, args.price)

    build_config = {
        "company": cfg["company"], "ticker": tk, "price": price, "files": files,
        "fy_end_month": cfg["fy_end_month"], "judgments": cfg["judgments"],
        "cost_of_debt": build_cost_of_debt(cfg),
    }
    out_xlsx = os.path.join(args.work_dir, f"{tk}_engine.xlsx")
    try:
        rep = AE.build_model(build_config, args.template, out_xlsx)
    except Exception as e:
        _fail(f"build_model failed (statement adjustment): {e}")
    print(f"[build] anchor {rep['anchor_year']}  COD {rep['cost_of_debt']['source']}"
          f"{'  [FLAGGED fallback]' if rep.get('cod_flagged') else ''}")

    # Keep the real-terms deflator tables (CPI-U + BEA PP&E) covering the anchor fiscal
    # year using monthly FRED CPI-U, and IFERROR-guard the cap-engine capex window. Must
    # run BEFORE recalc so the real-terms lookups resolve. Fail-closed on a missing CPI.
    import deflator_extend as DE
    try:
        _defl = DE.ensure_deflator_covers_anchor(
            out_xlsx, anchor_year=rep["anchor_year"], fy_end_month=cfg["fy_end_month"])
    except DE.DeflatorError as e:
        _fail(f"deflator extension failed (real-terms base cannot cover the anchor): {e}")
    if _defl.get("extended"):
        print(f"[deflator] extended to {_defl['anchor_year']} via monthly CPI "
              f"(cap-capex-guarded {_defl['cap_capex_wrapped']}): {_defl['added']}")
    else:
        print(f"[deflator] anchor {_defl['anchor_year']} already covered "
              f"(cap-capex-guarded {_defl['cap_capex_wrapped']})")

    # Point the reported-FY0 reconciliation anchors (Audit CHECK-4b) at the ACTUAL
    # anchor-year column. The template hardcodes them to the last column (AP), which is
    # only correct when the newest fiscal year fills AP (long histories: AAPL/HD/T). A
    # shorter-history issuer (e.g. POOL, newest year in AK) leaves AP blank, reddening the
    # audit on an otherwise-tying model. No-op for AP-anchored names. Runs before recalc.
    import repoint_fy0 as F0
    try:
        _f0 = F0.repoint_anchor_columns(out_xlsx, anchor_year=rep["anchor_year"])
    except F0.Fy0Error as e:
        _fail(f"FY0 anchor repoint failed (reconciliation cannot target the anchor year): {e}")
    if _f0["moved"]:
        print(f"[fy0] repointed reconciliation anchors to the {_f0['anchor_year']} "
              f"column: {_f0['moved']}")
    else:
        print(f"[fy0] reconciliation anchors already at the {_f0['anchor_year']} column")

    from recalc_lo import recalc
    recalc(out_xlsx)

    # --- optional payload overrides parsed early: 'bonded' (gates the rate re-point) and
    #     'erp_override' (cockpit ERP-method selector: COE = model real_rf + erp_override).
    #     Neither edits the committed company config; absent -> committed behaviour (bit-identical).
    _erp_override = None
    _scenarios = None
    if args.payload:
        try:
            import apply_payload as _APB
            _peek = _APB.load_payload(args.payload)
            if isinstance(_peek, dict) and _peek.get("bonded") is not None:
                cfg["bonded"] = bool(_peek["bonded"])
                print(f"[payload] bonded override -> {cfg['bonded']}")
            if isinstance(_peek, dict) and _peek.get("erp_override") is not None:
                _erp_override = float(_peek["erp_override"])
            if isinstance(_peek, dict) and _peek.get("scenarios") is not None:
                _scenarios = _peek["scenarios"]
        except Exception:
            pass

    # --- optional rate re-point (only if a feed is provided/available)
    disclosure = None
    feed = None
    if args.rate_feed_dir or args.rate_feed_live:
        import rate_feed as RF, repoint_rates as RP, openpyxl
        wb = openpyxl.load_workbook(out_xlsx, data_only=False)
        cash = wb["Inputs"]["B6"].value or 0.0
        sti = wb["Inputs"]["B7"].value or 0.0
        try:
            feed = RF.load_all(tk, cash=cash, sti=sti, local_dir=args.rate_feed_dir,
                               bonded=cfg["bonded"])  # local_dir=None -> live repo fetch
            # Cost-of-debt provenance + generalized (unbonded) fallback (ERP ladder ratified
            # 2026-07-25): issuer_bonds -> published -> synthetic coverage rating. Unbonded keeps
            # the build-time BOOK NFO; only real_cod is supplied from the rating curve.
            if "real_cod" in feed:                       # issuer bonds present (GREEN)
                feed["cod_provenance"] = {"cod_source": "issuer_bonds", "rating": feed.get("cod_rating"),
                                          "coverage": None, "audit": "GREEN", "as_of": args.vintage,
                                          "flags": []}
            else:                                        # unbonded -> rating-curve fallback (synthetic)
                import cod_fallback as CF
                vwb = openpyxl.load_workbook(out_xlsx, data_only=True)

                def _dn(name):
                    # scalar value of a defined name; if it points at a range, take the last
                    # numeric (latest period); tolerate a missing name (-> None).
                    try:
                        sheet, coord = list(vwb.defined_names[name].destinations)[0]
                        cells = vwb[sheet][coord]
                        if isinstance(cells, tuple):
                            nums = [c.value for r in cells for c in (r if isinstance(r, tuple) else (r,))
                                    if isinstance(c.value, (int, float))]
                            return nums[-1] if nums else None
                        return cells.value
                    except Exception:
                        return None
                fundamentals = dict(ebit=_dn("in_oiadj0"), interest_expense=_dn("in_intexp0"),
                                    total_debt=_dn("in_debt"), assets=_dn("rep_total_assets"))
                curve = CF.load_credit_curve(local_dir=args.rate_feed_dir)
                real_cod, prov = CF.resolve_cod(fundamentals=fundamentals, curve=curve,
                                                real_rf=feed["real_rf_fwd1y"])
                if not prov.get("spread_nonneg", True):
                    _fail(f"cod validation gate: negative spread vs real_rf on the rating curve ({prov['flags']})")
                prov["as_of"] = args.vintage
                feed["real_cod"] = real_cod
                feed["cod_rating"] = prov["rating"]
                feed["cod_provenance"] = prov
                print(f"[cod] unbonded fallback: {prov['cod_source']} rating={prov['rating']} "
                      f"coverage={prov['coverage']} audit={prov['audit']} flags={prov['flags']}")
            RP.repoint(wb, feed)
            if _erp_override is not None:
                RP.apply_erp_override(wb, _erp_override)
                feed["erp_override"] = _erp_override
                print(f"[erp-override] COE = model real_rf + {_erp_override} (company ERP flat; idio zeroed)")
            wb.save(out_xlsx)
            recalc(out_xlsx)
            print(f"[rates] re-pointed from feed (nfo_basis={feed['nfo_basis']})")
        except RF.RateFeedError as e:
            print(f"[rates] feed unavailable/invalid ({e}); keeping build-time rates")
            feed = None

    # --- Phase-2.1 MULTI-SCENARIO path (gated behind payload.scenarios). Values + ties
    #     base+bull+bear INDEPENDENTLY off the rate-repointed workbook and writes
    #     outputs/<TICKER>_scenarios.csv (one row per scenario + an expected-value row).
    #     Absent -> the single-scenario path below runs unchanged (bit-identical by
    #     construction). Fail-closed PER scenario: any non-tie aborts the whole dispatch.
    if _scenarios is not None:
        import run_scenarios as RS
        try:
            srep = RS.run_scenarios(out_xlsx, _scenarios, ticker=tk, price=price,
                                    out_dir=args.out_dir, recalc=recalc,
                                    commit_sha=os.environ.get("GITHUB_SHA", ""))
        except RS.ScenariosError as e:
            _fail(f"SCENARIOS FAILED: {e}")
        print(f"[done] {tk}  scenarios={srep['scenarios']} -> {tk}_scenarios.csv")
        return

    # --- optional RUN-button forecast payload (cockpit dispatch contract 20260722-0800).
    # Applied AFTER the rate re-point so nominal growth drivers are deflated with the very
    # inflation series the engine discounts against. Drivers absent from the payload are NOT
    # written, so they keep their existing formula (anchor hold / legacy scenario overlay) and
    # a payload-free run stays bit-identical. The gates below remain authoritative.
    payload_report = None
    if args.payload:
        import apply_payload as AP
        try:
            payload = AP.load_payload(args.payload)
            vals = openpyxl.load_workbook(out_xlsx, data_only=True)
            infl = AP.engine_inflation(vals, int(payload.get("N") or 0) or 1)
            wbp = openpyxl.load_workbook(out_xlsx, data_only=False)
            payload_report = AP.apply_payload(wbp, payload, infl)
            wbp.save(out_xlsx)
            recalc(out_xlsx)
        except AP.PayloadError as e:
            _fail(f"PAYLOAD REJECTED: {e}")
        if payload_report["ticker"] != tk:
            _fail(f"payload ticker {payload_report['ticker']!r} != config ticker {tk!r}")
        print(f"[payload] mode={payload_report['mode']} N={payload_report['N']} "
              f"wrote={sorted(payload_report['written'])} "
              f"held_at_anchor={payload_report['held_at_anchor']}")

    # --- GATES (required check): completeness/provenance, THEN the standing tie check
    results = AE.read_results(out_xlsx, price=price)
    results["anchor_year"] = rep.get("anchor_year")
    tie = results.get("max_identity_tie")
    print(f"[gates] ok={results['ok']}  audit={results['audit_status']!r}  tie={tie:.2e}"
          if isinstance(tie, float) else f"[gates] ok={results['ok']}")
    if not results["ok"]:
        _fail(f"GATES FAILED (completeness/provenance): {results.get('gates')}")

    import checks as CK
    tie_ok, tie_detail = CK.tie_check(results)
    results["tie_check"] = tie_detail
    print(f"[tie-check] {tie_detail['tie_check']}  "
          f"(audit_ok={tie_detail['audit_ok']} tie_ok={tie_detail['tie_ok']} mode_ok={tie_detail['mode_ok']})")
    if not tie_ok:
        _fail("TIE CHECK FAILED: " + "; ".join(tie_detail["reasons"]))

    # --- earnings-base guard: the tie is an identity on the shared forecast, so it holds for
    #     ANY anchor including a loss. This catches the one bright-line invalid anchor the tie
    #     cannot: a non-positive FY0 OPERATING income (a cyclical trough). Placed AFTER the tie
    #     so a refusal here means the anchor itself is invalid, not a data artifact. Remedy is
    #     human (pick a representative anchor year / supply a normalized OI) — D1.
    anchor_ok, anchor_detail = CK.anchor_earnings_check(out_xlsx)
    results["anchor_earnings_check"] = anchor_detail
    print(f"[anchor-earnings] {anchor_detail['anchor_earnings_check']}  "
          f"anchor_oi_at0={anchor_detail['anchor_oi_at0']} (FY{anchor_detail['anchor_year']})")
    if not anchor_ok:
        _fail("ANCHOR EARNINGS CHECK FAILED: " + anchor_detail["reason"])

    # --- R&D / opex-wedge diagnostic (Forecast row 61). Visible, non-fatal — EXCEPT a
    #     firm that declares no wedge (expect_zero_rd_wedge) must actually have ~0.
    wedge = CK.rd_wedge_report(out_xlsx)
    results["rd_wedge"] = wedge
    wpct = wedge.get("wedge_pct_ebit")
    print(f"[rd-wedge] opex wedge {wedge['opex_wedge']}  "
          f"({'%.1f%% of EBIT' % (100*wpct) if wpct is not None else 'n/a'}); "
          f"rev-scaled-consistent={wedge['rev_scaled_consistent']}; "
          f"rd_capitalization_wired={wedge['rd_capitalization_wired']}")
    if wedge["rd_reserve_nonzero_but_inert"]:
        print("[rd-wedge] NOTE: R&D reserve is nonzero but INERT (capitalization not yet "
              "wired into NOA/OI) — see docs; R&D-heavy names not yet capitalized.")
    if not wedge["rev_scaled_consistent"]:
        _fail("row-61 wedge is no longer revenue-proportional (engine structure changed unexpectedly)")
    if cfg.get("expect_zero_rd_wedge") and wpct is not None and wpct > 0.005:
        _fail(f"expect_zero_rd_wedge set but Forecast row 61 wedge is {100*wpct:.2f}% of EBIT "
              f"(expected ~0 for a no-R&D / no-opex-wedge name)")

    # --- Option-A disclosure (needs the live feed + bonded issuer)
    if feed is not None and cfg["bonded"] and "company" in feed:
        try:
            import disclose as D
            disclosure = D.disclose(out_xlsx, feed, price=price, recalc=recalc,
                                    sens_path=os.path.join(args.work_dir, f"{tk}_idiosens.xlsx"))
            print(D.format_bridge(disclosure))
        except Exception as e:
            print(f"[disclose] skipped ({e})")

    # --- disclosed inflation scorecard (Increment 2; tie-safe — never enters the four-method
    #     tie). Interest-tax-shield PVs under both debt policies (Miller-excluded) + the
    #     capital-intensity-vs-leverage verdict. Computed in engine units from the recalced
    #     workbook + the rate feed; additive, no engine edit.
    if feed is not None:
        try:
            import scorecard as SCD
            _sc = SCD.compute_scorecard(out_xlsx, feed)
            SCD.write_scorecard_csv(os.path.join(args.out_dir, f"{tk}_inflation_scorecard.csv"), _sc)
            _np = _sc.get("net_inflation_position_annual")
            print(f"[scorecard] {tk}: {_sc.get('verdict')}"
                  + (f"  (net {_np:.4g}/yr = benefit {_sc['interest_benefit_annual']:.4g}"
                     f" - penalty {_sc['depreciation_penalty_annual']:.4g})" if isinstance(_np, (int, float)) else ""))
        except Exception as e:
            print(f"[scorecard] skipped ({e})")

    # --- extract committed outputs + manifest
    manifest = EX.extract_outputs(out_xlsx, tk, args.out_dir, results=results,
                                  config_hash=cfg["config_hash"], vintage=args.vintage,
                                  disclosure=disclosure)
    print(f"[extract] wrote {', '.join(manifest['outputs'])} + {tk}_manifest.json to {args.out_dir}")
    # cost-of-debt provenance -> manifest (audit tab: cod_source / rating / coverage / audit / as_of)
    if feed is not None and feed.get("cod_provenance"):
        import json as _json
        _mp = os.path.join(args.out_dir, f"{tk}_manifest.json")
        try:
            with open(_mp) as _fh:
                _mj = _json.load(_fh)
            _mj["cost_of_debt"] = feed["cod_provenance"]
            if feed.get("erp_override") is not None:
                _mj["erp_override"] = {"value": feed["erp_override"], "method": "override",
                                       "note": "COE = model real_rf + erp_override (idio zeroed)"}
            with open(_mp, "w") as _fh:
                _json.dump(_mj, _fh, indent=2)
            print(f"[cod] provenance -> manifest: {feed['cod_provenance']['cod_source']} "
                  f"{feed['cod_provenance']['audit']} rating={feed['cod_provenance']['rating']}")
        except Exception as _e:
            print(f"[cod] manifest provenance skip ({_e})")
    print(f"[done] {tk}  equity={results.get('equity_value')}  tie={tie}")


if __name__ == "__main__":
    main()
