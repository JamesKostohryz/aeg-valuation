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
csv_path = os.path.join(_ROOT, "outputs", "PEP_scenarios.csv")
if os.path.exists(csv_path):
    rows = [r.split(",") for r in open(csv_path).read().strip().splitlines()[1:]]
    published = {r[3]: float(r[7]) for r in rows if r[7]}
    tol = float(doc["expected_values"].get("tolerance_ps", 0.01))
    for key in ("base", "bull", "bear", "expected_value"):
        exp = doc["expected_values"][key]
        got = published.get(key)
        check(got is not None and abs(got - exp) <= tol,
              f"published {key} {got} matches the forecast file's expected {exp} (tol {tol})")
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
