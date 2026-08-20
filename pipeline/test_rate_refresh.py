#!/usr/bin/env python3
"""
pipeline/test_rate_refresh.py — offline tests for the rate-side refresh dispatcher.

No network and no token. Every cross-repository call is intercepted, so this proves the thing
that actually matters about a dispatcher: WHAT it would send, and to whom.

THE ONE THAT MUST NEVER REGRESS is the durability category. OBS_CATEGORY selects the
obsolescence elevator preset and lands in coe_v2_<T>_latest_annual.csv, the cost-of-equity
curve the AEG engine discounts with. A refresh that sent "B" instead of "KEEP" would silently
re-decide that judgment for every company on every run, moving every discount rate with no diff
to see and every gate green -- this project's signature failure, in the newest place it could
appear. So the payload is asserted field by field, not smoke-tested.
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import rate_refresh as RR  # noqa: E402

_pass = _fail = 0


def ok(cond, msg):
    global _pass, _fail
    print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
    if cond:
        _pass += 1
    else:
        _fail += 1


# ------------------------------------------------------------------ the company list

tmp = tempfile.mkdtemp()
cdir = os.path.join(tmp, "companies")
os.makedirs(cdir)
for t in ("KO", "aapl", "MSFT"):
    open(os.path.join(cdir, f"{t}.yaml"), "w").write("ticker: %s\n" % t.upper())
open(os.path.join(cdir, "KO.forecast.json"), "w").write("{}")   # must not be read as a company
open(os.path.join(cdir, "notes.txt"), "w").write("ignore me")

got = RR.onboarded_tickers(cdir)
ok(got == ["AAPL", "KO", "MSFT"],
   f"the refresh follows the committed configs, uppercased and sorted (got {got})")
ok("KO.FORECAST" not in "".join(got) and len(got) == 3,
   "a .forecast.json beside a config is not mistaken for another company")

ok(RR.onboarded_tickers(os.path.join(tmp, "nope")) == [],
   "a missing companies directory yields nothing rather than raising")


# ------------------------------------------------------------------ what gets dispatched

sent = []


def fake_api(path, token, method="GET", body=None):
    sent.append((path, method, body, token))
    return 204, None


RR._api = fake_api

RR.dispatch("KO", "tok")
path, method, body, token = sent[-1]
ok(path == "/repos/JamesKostohryz/real-yields/actions/workflows/company.yml/dispatches",
   "it dispatches real-yields' company-data workflow")
ok(method == "POST", "by POST")
ok(body["ref"] == "main", "against main")
ok(body["inputs"]["ticker"] == "KO", "for the ticker asked for")

# THE ONE THAT MATTERS.
ok(body["inputs"]["obs_category"] == "KEEP",
   "obs_category is KEEP — the refresh REUSES the recorded durability judgment")
ok(body["inputs"]["obs_category"] not in ("A", "B", "C"),
   "the refresh never sends a concrete category, which would re-decide it silently")
ok(body["inputs"]["ory_override"] == "",
   "no ORY override is imposed; the recorded one is reused upstream")


# ------------------------------------------------------------------ failure behaviour

def failing_api(path, token, method="GET", body=None):
    return 500, None


RR._api = failing_api
try:
    RR.dispatch("KO", "tok")
    ok(False, "a non-204 dispatch must raise")
except RR.RefreshError as e:
    ok("500" in str(e), "a non-204 dispatch raises and names the status")

# One company failing must not stop the rest, and the run must still fail overall.
calls = {"n": 0}


def flaky_api(path, token, method="GET", body=None):
    calls["n"] += 1
    if body and body["inputs"]["ticker"] == "AAPL":
        return 500, None
    return 204, None


RR._api = flaky_api
os.environ["CROSS_REPO_TOKEN"] = "tok"
rc = RR.main(["--companies-dir", cdir, "--pause", "0"])
ok(calls["n"] == 3, "every company is attempted even after one fails")
ok(rc == 1, "the run still exits non-zero — a refresh that half-ran must not report success")

# --dry-run must be inert.
calls["n"] = 0
rc = RR.main(["--companies-dir", cdir, "--dry-run", "--pause", "0"])
ok(rc == 0 and calls["n"] == 0, "--dry-run dispatches nothing and exits clean")

# No token is a loud failure, not a silent no-op.
del os.environ["CROSS_REPO_TOKEN"]
os.environ.pop("GH_TOKEN", None)
calls["n"] = 0
rc = RR.main(["--companies-dir", cdir, "--pause", "0"])
ok(rc == 2 and calls["n"] == 0,
   "a missing cross-repo token refuses loudly instead of appearing to refresh nothing")

print(f"\n{_pass} passed, {_fail} failed")
raise SystemExit(1 if _fail else 0)
