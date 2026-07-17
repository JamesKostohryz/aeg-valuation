/**
 * protect_workarea.gs — lock the AEG Work Area so only the blue input cells are editable.
 *
 * The whole point of the "walls" design: neither a human nor an AI can touch the valuation
 * machinery. In Google Sheets that means protecting every sheet and leaving ONLY the blue
 * driver/control cells as unprotected exceptions. The editable set below is computed
 * deterministically from the sealed Work Area by extract_blue_ranges.py (15 ranges, 276
 * cells) — regenerate and paste if the Work Area layout ever changes.
 *
 * HOW TO USE
 *   1. Extensions -> Apps Script, paste this file.
 *   2. Run protectAll() once. Authorize when prompted.
 *   3. Re-run after any layout change (it clears and re-applies cleanly).
 */

// ---- editable (blue-input) ranges on the "Forecast Work Area" tab ---------------
// Source: extract_blue_ranges.py -> blue_ranges.json
var WORK_AREA_SHEET = "Forecast Work Area";
var EDITABLE_RANGES = [
  "C2", "E2", "C3", "E3", "C4",   // mode / financing / payout / target-FLEV / anchor period
  "G7:AJ7",    // revenue_growth
  "G10:AJ10",  // gross_margin
  "G12:AJ12",  // sga_ratio
  "G14:AJ14",  // da_rate
  "G17:AJ17",  // tax_rate
  "G24:AJ24",  // buyback_rate (enterprise)
  "F30",       // real price anchor
  "G36:AJ36",  // capex_ratio
  "G45:AJ45",  // operating-liabilities ratio (enterprise)
  "G50:AJ50"   // noa_growth (enterprise)
];

// Tabs that are pipeline-fed or pure output: protect FULLY (no editable exceptions).
var FULLY_PROTECTED_SHEETS = ["_Actuals", "_Rates"];

function protectAll() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  protectWorkArea_(ss);
  FULLY_PROTECTED_SHEETS.forEach(function (name) { protectSheetFully_(ss, name); });
  SpreadsheetApp.getUi().alert("AEG protection applied: Work Area locked except blue inputs; "
    + "data tabs fully locked.");
}

function protectWorkArea_(ss) {
  var sh = ss.getSheetByName(WORK_AREA_SHEET);
  if (!sh) throw new Error("sheet not found: " + WORK_AREA_SHEET);
  clearProtections_(sh);
  var prot = sh.protect().setDescription("AEG Work Area — locked except blue inputs");
  lockToMe_(prot);
  prot.setUnprotectedRanges(EDITABLE_RANGES.map(function (a1) { return sh.getRange(a1); }));
}

function protectSheetFully_(ss, name) {
  var sh = ss.getSheetByName(name);
  if (!sh) return;  // optional tab
  clearProtections_(sh);
  var prot = sh.protect().setDescription("AEG " + name + " — pipeline-fed, fully locked");
  lockToMe_(prot);
}

// ---- helpers -------------------------------------------------------------------
function clearProtections_(sh) {
  [SpreadsheetApp.ProtectionType.SHEET, SpreadsheetApp.ProtectionType.RANGE]
    .forEach(function (t) { sh.getProtections(t).forEach(function (p) { p.remove(); }); });
}

function lockToMe_(prot) {
  var me = Session.getEffectiveUser();
  prot.addEditor(me);
  prot.getEditors().forEach(function (u) {
    if (u.getEmail() && u.getEmail() !== me.getEmail()) prot.removeEditor(u);
  });
  if (prot.canDomainEdit && prot.canDomainEdit()) prot.setDomainEdit(false);
}
