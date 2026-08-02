/**
 * add_cockpit_sections.gs — add the two missing cockpit displays in ONE run.
 *
 * WHY THIS EXISTS
 *   The engine now emits two feeds the Stage-18 cockpit does not yet show:
 *     • <TICKER>_status.csv            — anchor health + run verdicts (loss-anchor,
 *                                        representativeness, tie, inflation verdict, vintage)
 *     • <TICKER>_inflation_scorecard.csv — net beneficiary/loser of inflation, the
 *                                        capital-intensity penalty vs leverage subsidy,
 *                                        interest-tax-shield PVs (Miller-excluded, disclosure)
 *   This script wires both into the live Sheet WITHOUT touching any existing tab. It creates
 *   (or cleanly re-creates) two tabs — "Anchor Health" and "Inflation" — each with a small
 *   IMPORTDATA landing block and a labeled VLOOKUP readout, plus PASS/FAIL/SKIP colouring.
 *   Same mechanism as protect_workarea.gs: paste, run once, done. No connector, no browser.
 *
 * HOW TO USE
 *   1. Extensions -> Apps Script, paste this file (add it alongside protect_workarea.gs).
 *   2. VERIFY the three constants below match your Control tab (the cells where you type the
 *      ticker and the repo). Defaults follow the build_cockpit convention (ticker C2, repo C3).
 *   3. Run addCockpitSections() once. Authorize when prompted.
 *   4. Re-run any time — it clears and rebuilds its own two tabs; it never edits others.
 *   5. If you protect the sheet with protect_workarea.gs, these two tabs are pure output —
 *      let them stay protected (no editable exceptions needed).
 *
 * NOTE: IMPORTDATA only pulls PUBLIC raw.githubusercontent URLs. <TICKER>_status.csv lands in
 * the repo's outputs/ on the next pipeline run; until then the Anchor Health tab shows blanks.
 * The inflation scorecard CSV is already committed.
 */

// ---- CONFIG: confirm these match your Control tab -------------------------------
var CONTROL_SHEET = "Control";
var TICKER_CELL   = "C2";   // cell on Control where the ticker is typed
var REPO_CELL     = "C3";   // cell on Control holding "user/repo" (e.g. JamesKostohryz/aeg-valuation)

// "C2" -> "$C$2" (absolute reference)
function absCell_(a1) {
  var m = a1.match(/^([A-Za-z]+)(\d+)$/);
  return "$" + m[1].toUpperCase() + "$" + m[2];
}

// raw.githubusercontent base, built live from the two Control cells above.
function importData_(suffix) {
  var repo   = "'" + CONTROL_SHEET + "'!" + absCell_(REPO_CELL);
  var ticker = "'" + CONTROL_SHEET + "'!" + absCell_(TICKER_CELL);
  return '=IMPORTDATA("https://raw.githubusercontent.com/"&' + repo +
         '&"/main/outputs/"&' + ticker + '&"_' + suffix + '")';
}

// ---- styling helpers ------------------------------------------------------------
var HDR = {fontSize: 14, fontColor: "#1F4E78", bold: true};
var SECT = {background: "#1F4E78", fontColor: "#FFFFFF", bold: true};
var LBL = {bold: true};
var SUB = {italic: true, fontColor: "#595959"};

function styleCell_(cell, s) {
  if (s.fontSize) cell.setFontSize(s.fontSize);
  if (s.fontColor) cell.setFontColor(s.fontColor);
  if (s.background) cell.setBackground(s.background);
  if (s.bold) cell.setFontWeight("bold");
  if (s.italic) cell.setFontStyle("italic");
}

function freshSheet_(ss, name) {
  var ex = ss.getSheetByName(name);
  if (ex) ss.deleteSheet(ex);
  return ss.insertSheet(name);
}

// VLOOKUP a field out of a 2-col IMPORTDATA landing block on the same tab.
function vlk_(field, blockA1) {
  return '=IFERROR(VLOOKUP("' + field + '",' + blockA1 + ',2,FALSE),"—")';
}

// Colour a verdict cell green/amber/red on PASS/SKIP/FAIL text.
function verdictFormat_(sheet, a1) {
  var rng = sheet.getRange(a1);
  var rules = sheet.getConditionalFormatRules();
  function rule(text, colour) {
    return SpreadsheetApp.newConditionalFormatRule()
      .whenTextContains(text).setBackground(colour).setRanges([rng]).build();
  }
  rules.push(rule("PASS", "#C6F3DE"));
  rules.push(rule("BENEFICIARY", "#C6F3DE"));
  rules.push(rule("SKIP", "#FEF1D1"));
  rules.push(rule("FAIL", "#F6C5BE"));
  rules.push(rule("LOSER", "#F6C5BE"));
  sheet.setConditionalFormatRules(rules);
}

// ---- main -----------------------------------------------------------------------
function addCockpitSections() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss.getSheetByName(CONTROL_SHEET)) {
    SpreadsheetApp.getUi().alert('Control tab "' + CONTROL_SHEET +
      '" not found — set CONTROL_SHEET/TICKER_CELL/REPO_CELL at the top of the script.');
    return;
  }
  buildAnchorHealth_(ss);
  buildInflation_(ss);
  SpreadsheetApp.getUi().alert(
    'Added "Anchor Health" and "Inflation" tabs. If a tab shows blanks, that CSV has not been ' +
    'committed to outputs/ yet (status.csv lands on the next pipeline run).');
}

function buildAnchorHealth_(ss) {
  var s = freshSheet_(ss, "Anchor Health");
  // IMPORTDATA landing block off to the right (H:I), out of the way of the readout.
  s.getRange("H1").setFormula(importData_("status.csv"));
  var BLK = "$H:$I";

  styleCell_(s.getRange("B1").setValue("Anchor Health & Run Status"), HDR);
  styleCell_(s.getRange("B2").setValue("Did the engine accept this anchor? (loss / representativeness guards)"), SUB);

  var rows = [
    ["Run status",                 "run_status"],
    ["Reconciliation (tie) check",  "tie_check"],
    ["Loss-anchor guard",           "anchor_earnings_check"],
    ["Anchor representative?",      "anchor_representativeness"],
    ["FY0 operating margin",        "anchor_margin"],
    ["  vs company normal (median)","anchor_normal_margin"],
    ["  ratio (FY0 / normal)",      "anchor_margin_vs_normal"],
    ["Inflation verdict",           "inflation_verdict"],
    ["Anchor fiscal year",          "anchor_year"],
    ["Run vintage",                 "vintage"],
    ["Config hash",                 "config_hash"]
  ];
  var r = 4;
  styleCell_(s.getRange(r, 2).setValue("ANCHOR HEALTH"), SECT);
  styleCell_(s.getRange(r, 3).setValue(""), SECT);
  r++;
  rows.forEach(function (row) {
    styleCell_(s.getRange(r, 2).setValue(row[0]), LBL);
    s.getRange(r, 3).setFormula(vlk_(row[1], BLK)).setHorizontalAlignment("right");
    r++;
  });
  // percent formats + colouring
  s.getRange("C9:C10").setNumberFormat("0.0%");   // margins
  s.getRange("C11").setNumberFormat("0.00");      // ratio
  verdictFormat_(s, "C6"); verdictFormat_(s, "C7"); verdictFormat_(s, "C8");
  styleCell_(s.getRange(r + 1, 2).setValue(
    "Green = PASS. A rejected run aborts and commits nothing, so a stale 'vintage' here vs the " +
    "Valuation tab means the current name/config was refused — investigate before trusting the number."), SUB);
  s.setColumnWidth(2, 230); s.setColumnWidth(3, 150); s.hideColumns(8, 2);
}

function buildInflation_(ss) {
  var s = freshSheet_(ss, "Inflation");
  s.getRange("H1").setFormula(importData_("inflation_scorecard.csv"));
  var BLK = "$H:$I";

  styleCell_(s.getRange("B1").setValue("Inflation Scorecard"), HDR);
  styleCell_(s.getRange("B2").setValue("Is this firm a net winner or loser from inflation? (Increment 2, disclosure)"), SUB);

  var verdict = [
    ["Verdict",                         "verdict"],
    ["Net inflation position / yr",     "net_inflation_position_annual"],
    ["  Capital-intensity penalty / yr","depreciation_penalty_annual"],
    ["  Leverage subsidy / yr",         "interest_benefit_annual"]
  ];
  var ctx = [
    ["Expected inflation",              "expected_inflation"],
    ["Net debt",                        "net_debt"],
    ["Avg asset age (yrs)",             "avg_asset_age_yrs"],
    ["Breakeven leverage (CPI rule)",   "breakeven_leverage"]
  ];
  var shield = [
    ["Interest-tax-shield PV (fixed-nominal)", "interest_tax_shield_pv_fixed_nominal"],
    ["Interest-tax-shield PV (constant-real)", "interest_tax_shield_pv_constant_real"]
  ];
  var r = 4;
  function block(title, arr) {
    styleCell_(s.getRange(r, 2).setValue(title), SECT);
    styleCell_(s.getRange(r, 3).setValue(""), SECT); r++;
    arr.forEach(function (row) {
      styleCell_(s.getRange(r, 2).setValue(row[0]), LBL);
      s.getRange(r, 3).setFormula(vlk_(row[1], BLK)).setHorizontalAlignment("right"); r++;
    });
    r++;
  }
  block("VERDICT", verdict);
  block("CONTEXT", ctx);
  block("INTEREST TAX SHIELD  (disclosure only — Miller 1977, excluded from headline)", shield);
  verdictFormat_(s, "C5");
  s.getRange("C10").setNumberFormat("0.00%");  // expected inflation
  styleCell_(s.getRange(r, 2).setValue(
    "Net position uses the engine's BEA capital-goods deflator (authoritative). 'Breakeven leverage' " +
    "is a general-CPI rule of thumb — context only, not the verdict driver. Money figures are in the " +
    "engine's units (same scaling as the Valuation tab)."), SUB);
  s.setColumnWidth(2, 300); s.setColumnWidth(3, 160); s.hideColumns(8, 2);
}
