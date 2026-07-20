#!/usr/bin/env python3
"""
aeg_engine.py — one consolidated entry point for the AEG valuation pipeline.

    build_model(config, template_path, out_path) -> build_report   # openpyxl only
    <caller recalculates out_path with LibreOffice>
    read_results(out_path, price) -> results                        # after recalc

Wraps the hardened modules (loader_core, market_data, company_setup, validate_load)
so the Sheets/Colab front end calls ONE function with a config dict and never touches
the internals. Determinism + fail-loud: build_model raises on any critical gap; the
provenance/completeness gates run in read_results.

config = {
  "company","ticker",                      # names (labels + provenance)
  "price",                                  # current share price
  "files": {"is_csv","bs_csv","cf_csv","prices","dividends","splits"},  # paths
  "fy_end_month": 0,                        # 0 = auto-detect from statement dates
  "judgments": {"minority_include","finlease","oi_adj_override",
                "rd_capitalize","rd_life","dps_override"},
  "cost_of_debt": {"ytw_points": [(tenor,yield),...] | None,
                   "single_ytw": float|None,
                   "interest_expense": float|None, "total_debt": float|None},
}
"""
import shutil, openpyxl
import loader_core as LC
import market_data as MDX
import company_setup as CS
import validate_load as VL


def build_model(config, template_path, out_path):
    """Populate + repoint the model from config. openpyxl only (no recalc). Returns a
    build report. Raises ValueError (fail-loud) on missing critical line / bad alignment."""
    files = config["files"]
    j = dict(minority_include=False, finlease=0.0, oi_adj_override=None,
             rd_capitalize=False, rd_life=0.0, dps_override=None)
    j.update(config.get("judgments", {}))
    cod = config.get("cost_of_debt", {}) or {}

    shutil.copy(template_path, out_path)
    wb = openpyxl.load_workbook(out_path)

    # 1) statements -> reported tabs (fail-loud on missing critical line / misalignment)
    parsed = {k: LC.parse_statement(files[k]) for k in ("is_csv", "bs_csv", "cf_csv")}
    permitted, match_report, anchor_year = LC.populate_raw_tabs(wb, parsed)

    # 1b) boundary-independent operating-cost decomposition: rebuild a fabricated
    #     Cost-of-Revenue/Gross-Profit split (e.g. AT&T) from the stable Rev-OI-D&A spine
    #     so the row-61 opex wedge and the valuation don't ride the feed's COGS/OpEx line.
    #     Stable-margin filers (AAPL) are left exactly as filed.
    cost_boundary_report = LC.stabilize_cost_boundary(wb)

    # 2) derive Inputs scalars, fold in judgments, write
    derived = LC.derive_inputs(wb, anchor_year, parsed)
    LC.apply_judgments(derived, price=float(config["price"]),
                       minority_include=j["minority_include"], finlease=j["finlease"],
                       oi_adj_override=j["oi_adj_override"], rd_capitalize=j["rd_capitalize"],
                       rd_life=j["rd_life"], dps_override=j["dps_override"])
    LC.write_inputs(wb, derived)

    # 3) market data (year-end prices + near-term dividend)
    fyem = config.get("fy_end_month", 0) or 12
    MDX.apply_market_data(wb, derived,
                          prices_path=files.get("prices"), dividends_path=files.get("dividends"),
                          splits_path=files.get("splits"), anchor_year=anchor_year,
                          fy_end_month=fyem, manual_dps=j["dps_override"])

    # 4) cost of debt (per-company YTW curve; statement-implied fallback, flagged).
    #    When no explicit COD is given (e.g. cost_of_debt.source=bond_list, where the
    #    rate re-point will override COD downstream), auto-derive the statement-implied
    #    interest/debt seed from the just-written Inputs so the build never stalls.
    ie, td = cod.get("interest_expense"), cod.get("total_debt")
    if not cod.get("ytw_points") and cod.get("single_ytw") is None and ie is None and td is None:
        def _in(name):
            dn = wb.defined_names.get(name)
            if not dn:
                return None
            ref = str(dn.value).replace("$", "").replace("'", "")
            sh, cell = ref.split("!")
            return wb[sh][cell].value
        ie, td = _in("in_intexp0"), _in("in_debt")
    cod_report = CS.set_cost_of_debt(
        wb, ytw_points=cod.get("ytw_points"), single_ytw=cod.get("single_ytw"),
        interest_expense=ie, total_debt=td, ticker=config["ticker"])

    # 5) relabel every base-company cell (headers -> company, notes genericized)
    lbl_report = CS.set_company_labels(wb, config["company"], config["ticker"], anchor_year)

    wb.save(out_path)
    return {"anchor_year": anchor_year, "match_report": match_report,
            "cost_of_debt": cod_report, "labels": lbl_report,
            "cod_flagged": cod_report.get("flagged", False),
            "cost_boundary": {k: v for k, v in cost_boundary_report.items() if k != "permitted"}}


def read_results(out_path, price=None):
    """Read valuation + run the completeness/provenance gates. Call AFTER recalc.
    Returns a results dict; results['ok'] is False if any gate would halt the run."""
    ok, gate_report = VL.validate(out_path, price=price)
    wb = openpyxl.load_workbook(out_path, data_only=True)
    A = wb["Audit"]; V = wb["Valuation"]

    def nm(name):
        dn = wb.defined_names.get(name)
        if not dn:
            return None
        ref = str(dn.value).replace("$", "").replace("'", "")
        sh, cell = ref.split("!")
        try:
            return wb[sh][cell].value
        except Exception:
            return None

    ties = [A[t].value for t in ["B27", "B28", "B29", "B31", "B44", "B50", "B58", "B63"]
            if isinstance(A[t].value, (int, float))]
    results = {
        "ok": ok,
        "gates": gate_report,
        "audit_status": A["B6"].value,
        "max_identity_tie": max((abs(x) for x in ties), default=None),
        "equity_value": V["B52"].value,
        "enterprise_value": V["B53"].value,
        "active_value": V["B54"].value,
        "mode_tie": V["B55"].value,
        "price": price,
        "anchors": {a: nm(a) for a in ("anchor_eps0", "anchor_cse0", "anchor_shares0",
                                       "anchor_nfo0", "anchor_real_noa0", "anchor_real_cse0",
                                       "anchor_real_nfo0")},
    }
    return results
