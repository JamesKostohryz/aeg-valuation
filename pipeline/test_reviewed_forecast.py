#!/usr/bin/env python3
"""test_reviewed_forecast.py — the reviewed forecast is a repository artifact, and a company
that has one cannot be valued payload-free.

Why this file exists. Before 2026-08-13 a reviewed forecast lived only inside a one-time
Cockpit dispatch. Nothing in the repository remembered it. So any push touching companies/**,
pipeline/** or *.py re-ran the whole fleet through run_company.py with no payload, the default
constant-growth overlay could not satisfy Gate A, the run REFUSED, and it quarantined that
company's published valuation/summary/fact_sheet/manifest to .STALE. PepsiCo — the first
company on this system to clear every gate — lost its published outputs exactly that way at
commit 33a6b5a. These tests hold the fix in place.

Offline and deterministic: no LibreOffice, no recalculation, no network.
"""
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for p in (_ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import apply_payload as AP
import run_company as RC
import run_scenarios as RS

_pass = _fail = 0


def check(cond, msg):
    global _pass, _fail
    if cond:
        _pass += 1
    else:
        _fail += 1
        print(f"  FAIL  {msg}")


def _write(tmp, obj):
    path = os.path.join(tmp, "PEP.forecast.json")
    with open(path, "w") as fh:
        json.dump(obj, fh)
    return path


def _raises(path, ticker):
    try:
        RC.load_reviewed_forecast(path, ticker)
    except RC.ReviewedForecastError as e:
        return str(e)
    return None


# ---------------------------------------------------------------- the real PEP file
FC = os.path.join(_ROOT, "companies", "PEP.forecast.json")
check(os.path.exists(FC), "companies/PEP.forecast.json exists — the forecast is in the repo")
doc = json.load(open(FC))

check(doc.get("reviewed") is True, "PEP forecast is marked reviewed")
check(doc.get("ticker") == "PEP", "PEP forecast carries its own ticker")
names = [s["name"] for s in doc["scenarios"]]
check(names == ["base", "bull", "bear"], f"three scenarios, base/bull/bear (got {names})")
check((doc.get("primary") or "base") in names, "the primary scenario exists in the array")

probs = sum(float(s["probability"]) for s in doc["scenarios"])
check(abs(probs - 1.0) < 1e-9, f"probabilities sum to 1.0 (got {probs})")

# The structural validator the workflow and run_scenarios both use.
try:
    RS._validate_scenarios(doc["scenarios"])
    check(True, "scenarios array passes run_scenarios._validate_scenarios")
except Exception as e:                                    # pragma: no cover - a real failure
    check(False, f"scenarios array rejected by _validate_scenarios: {e}")

# Every scenario must survive the same payload validator a Cockpit dispatch goes through,
# reshaped to the single-scenario form exactly as run_scenarios._as_single_payload does.
for sc in doc["scenarios"]:
    single = {"ticker": doc["ticker"], "mode": sc.get("mode"), "N": sc.get("N"),
              "drivers": sc.get("drivers") or {}, "singles": sc.get("singles") or {}}
    try:
        tk, mode, N = AP.validate_payload(single)
        check((tk, mode, N) == ("PEP", sc["mode"], sc["N"]),
              f"{sc['name']}: validate_payload round-trips ({tk}, {mode}, {N})")
    except AP.PayloadError as e:
        check(False, f"{sc['name']}: validate_payload rejected the stored drivers: {e}")
    for key, arr in (sc.get("drivers") or {}).items():
        check(len(arr) == sc["N"],
              f"{sc['name']}: driver {key} has {len(arr)} years, N={sc['N']}")

# The stored forecast must be the one that produced the published CSV. If someone edits a
# driver without re-proving it, this is the check that says so.
#
# WHY THIS IS A BAND AND NOT AN EQUALITY, RULED BY JAMES 2026-08-19. It was written as a
# penny-exact comparison and it turned the regression harness red for five days, from
# 2026-08-13 to 2026-08-19, across four sessions and the entire Region 2 build, while three
# handoff documents described the state of this repository without mentioning it.
#
# Nothing was wrong with the valuation. Commit ecf6a58, an automated `pipeline: refresh
# valuation outputs [skip ci]` run, re-priced PepsiCo sixteen hours after the reviewed run
# against a market that had moved -- real cost of equity 5.4877% to 5.5279%, price 144.38 to
# 146.38 -- and the published figures moved about 0.4%. They were supposed to. The scheduled
# refresh re-prices against live rates BY DESIGN; the reviewed number is a fixed record of a
# human judgment BY DESIGN. Requiring them to be equal to a penny is requiring the market to
# stand still, so the check could only ever be red, and a check that is always red stops being
# read. That is the same failure as a gate reporting success over a wrong number, reached from
# the other side.
#
# WHAT THE CHECK IS ACTUALLY FOR, and what the band preserves. It exists to catch a driver
# edited without being re-proven -- somebody changing the forecast and not re-running it. That
# is a change in the FORECAST, and a forecast change that matters moves value by far more than
# rates drift between two runs of the same week. The band is therefore wide enough to absorb
# repricing and nowhere near wide enough to absorb a forecast edit: PepsiCo's own bull and bear
# cases sit 12% above and 32% below its base, so a driver change worth noticing clears 2% by an
# order of magnitude.
#
# The tolerance is RELATIVE, because an absolute per-share band means something different for a
# $30 stock and a $600 one. A company may TIGHTEN it in its own forecast file; the default is
# the ceiling, not a suggestion.
TOLERANCE_PCT_DEFAULT = 0.02


def _within_band(got, exp, tol_pct):
    """True if a published figure is close enough to its reviewed one to be the same forecast
    priced on a different day."""
    return got is not None and exp and abs(got - exp) <= abs(exp) * tol_pct


# THE BAND HAS TO DISCRIMINATE, NOT MERELY EXIST. A tolerance loose enough to pass everything
# is not a check. These pin both edges against the real reviewed base value, so the band cannot
# be widened later without one of them failing.
_b = doc["expected_values"]["base"]
check(_within_band(_b * 1.004, _b, TOLERANCE_PCT_DEFAULT),
      "the band ABSORBS a 0.4% repricing — the drift that turned the harness red")
check(_within_band(_b * 0.985, _b, TOLERANCE_PCT_DEFAULT),
      "the band absorbs a 1.5% repricing, a hard week in rates")
check(not _within_band(_b * 1.03, _b, TOLERANCE_PCT_DEFAULT),
      "the band REFUSES a 3% move — beyond anything two runs of the same week can drift")
check(not _within_band(doc["expected_values"]["bull"], _b, TOLERANCE_PCT_DEFAULT),
      "the band refuses the BULL case as the base — a real forecast change clears it easily")
check(not _within_band(doc["expected_values"]["bear"], _b, TOLERANCE_PCT_DEFAULT),
      "the band refuses the BEAR case as the base")
check(not _within_band(None, _b, TOLERANCE_PCT_DEFAULT),
      "a missing published figure is a failure, not a pass")

csv_path = os.path.join(_ROOT, "outputs", "PEP_scenarios.csv")
if os.path.exists(csv_path):
    rows = [r.split(",") for r in open(csv_path).read().strip().splitlines()[1:]]
    published = {r[3]: float(r[7]) for r in rows if r[7]}
    # The retired key must be GONE, not merely ignored. A dead knob that still reads like a
    # live one is how somebody sets a tolerance in good faith and nothing happens.
    check("tolerance_ps" not in doc["expected_values"],
          "the retired absolute tolerance_ps is not left lying in the forecast file")
    tol_pct = float(doc["expected_values"].get("tolerance_pct", TOLERANCE_PCT_DEFAULT))
    check(tol_pct <= TOLERANCE_PCT_DEFAULT,
          f"the forecast file's tolerance_pct {tol_pct:.4f} tightens rather than loosens the "
          f"{TOLERANCE_PCT_DEFAULT:.0%} default")
    for key in ("base", "bull", "bear", "expected_value"):
        exp = doc["expected_values"][key]
        got = published.get(key)
        drift = (abs(got - exp) / abs(exp)) if (got is not None and exp) else None
        check(_within_band(got, exp, tol_pct),
              f"published {key} {got} is within {tol_pct:.0%} of the reviewed {exp} "
              f"(drift {drift:.2%})" if drift is not None else
              f"published {key} is missing")
else:                                                     # pragma: no cover
    check(False, "outputs/PEP_scenarios.csv is missing — nothing to reconcile against")

# ---------------------------------------------------------------- the refusal guards
with tempfile.TemporaryDirectory() as tmp:
    good = {"ticker": "PEP", "reviewed": True, "primary": "base",
            "scenarios": [{"name": "base", "probability": 1.0, "mode": "Enterprise", "N": 4,
                           "drivers": {}, "singles": {}}]}

    p = _write(tmp, good)
    out = RC.load_reviewed_forecast(p, "PEP")
    check(out["ticker"] == "PEP" and out["primary"] == "base" and len(out["scenarios"]) == 1,
          "a well-formed reviewed forecast loads into a dispatchable payload")

    bad = dict(good); bad["reviewed"] = False
    check("not marked reviewed" in (_raises(_write(tmp, bad), "PEP") or ""),
          "a forecast without reviewed:true is refused, not published as a draft")

    bad = dict(good); bad["ticker"] = "KO"
    check("not 'PEP'" in (_raises(_write(tmp, bad), "PEP") or ""),
          "a forecast file for the wrong ticker is refused")

    bad = dict(good); bad["primary"] = "midcase"
    check("is not one of" in (_raises(_write(tmp, bad), "PEP") or ""),
          "a primary scenario that does not exist is refused")

    bad = dict(good); bad.pop("scenarios")
    check("no scenarios array" in (_raises(_write(tmp, bad), "PEP") or ""),
          "a forecast with no scenarios array is refused")

    with open(os.path.join(tmp, "PEP.forecast.json"), "w") as fh:
        fh.write("{ this is not json")
    check("UNREADABLE" in (_raises(os.path.join(tmp, "PEP.forecast.json"), "PEP") or ""),
          "an unreadable forecast file refuses the run instead of silently falling back")

    check(RC.reviewed_forecast_path(os.path.join(tmp, "PEP.yaml"), "PEP")
          == os.path.join(tmp, "PEP.forecast.json"),
          "the forecast file is looked for beside the company config")

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
