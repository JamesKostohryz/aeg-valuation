#!/usr/bin/env python3
"""
pipeline/ci_drift.py — has the regression harness actually RUN on what is on main?

THE GAP NO TEST IN THIS REPOSITORY CAN SEE. Every check here answers "is the code right?". None
of them answers "did anything check?" -- and on 2026-08-19 that turned out to be three separate
ways to lose CI in a single afternoon:

  * A COMMIT MESSAGE THAT MERELY MENTIONS THE CI-SKIP MARKER SKIPS CI. It caught the commit that
    fixed the harness, whose message quoted the marker while explaining which commit had used
    it. GitHub reads the quotation as the instruction, anywhere in the message, not just the
    subject line. That is also how the original breakage went a day unseen: the bot commit that
    caused it carried the marker deliberately.
  * PATH FILTERS. regression.yml did not list idio/**, so a change to the module whose only job
    is to set a discount rate triggered no workflow and ran no test at all.
  * A PUSH BY A WORKFLOW TRIGGERS NOTHING. The onboard job commits with the default token, so
    the config it lands is never validated by the fleet run.

All three look identical from inside the repository: green, because nothing ran. This asks
GitHub instead.

WHAT IT CHECKS. For the current head of main: a regression-harness run exists, it succeeded, and
it is not older than MAX_AGE_DAYS. Anything else fails, with the reason and the remedy.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import datetime as dt
import urllib.request

OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "JamesKostohryz")
REPO = os.environ.get("GITHUB_REPOSITORY", "JamesKostohryz/aeg-valuation").split("/")[-1]
WORKFLOW = "regression.yml"
API = "https://api.github.com"
MAX_AGE_DAYS = 14


# The paths the regression harness is responsible for. Deliberately WIDER than regression.yml's
# own trigger filters: if the two disagree, that disagreement is a path-filter gap, and a gap is
# exactly what this file is looking for. idio/** was missing from those filters for a day.
_GUARDED_PREFIXES = ("pipeline/", "idio/", "tests/", "normalization/", ".github/workflows/",
                     "companies/")
_GUARDED_EXACT = ("MODEL_TEMPLATE.xlsx", "requirements.txt")


def _guarded(name: str) -> bool:
    if name in _GUARDED_EXACT:
        return True
    if name.startswith(_GUARDED_PREFIXES):
        return True
    return "/" not in name and name.endswith(".py")


def _api(path, token):
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "User-Agent": "aeg-ci-drift"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Has CI actually run on main's head?")
    ap.add_argument("--max-age-days", type=int, default=MAX_AGE_DAYS)
    a = ap.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN not set", file=sys.stderr)
        return 2

    # WHICH COMMIT SHOULD HAVE BEEN CHECKED. Not simply main's head: the pipeline bot pushes
    # `refresh valuation outputs` commits that touch outputs/ only, and those legitimately carry
    # the CI-skip marker because there is nothing in them for the harness to prove. Failing on
    # those every morning would be noise, and a check that cries wolf gets muted, which is the
    # failure mode this whole file exists to catch.
    #
    # So walk back to the newest commit that touched something the harness actually guards, and
    # ask whether THAT was proven.
    head = _api(f"/repos/{OWNER}/{REPO}/commits/main", token)
    recent = _api(f"/repos/{OWNER}/{REPO}/commits?sha=main&per_page=30", token)
    target = None
    for c in recent:
        files = _api(f"/repos/{OWNER}/{REPO}/commits/{c['sha']}", token).get("files") or []
        names = [f["filename"] for f in files]
        if any(_guarded(n) for n in names):
            target = c
            break
    if target is None:
        print(f"main head {head['sha'][:7]} — no behaviour-bearing commit in the last 30; "
              f"nothing for the harness to have proven")
        return 0
    sha = target["sha"]
    subject = (target["commit"]["message"].splitlines() or [""])[0]
    skipped = sha != head["sha"]
    print(f"newest behaviour-bearing commit on main: {sha[:7]}  {subject[:70]}"
          + (f"   (main head is {head['sha'][:7]}, outputs only)" if skipped else ""))
    head = target

    runs = _api(f"/repos/{OWNER}/{REPO}/actions/workflows/{WORKFLOW}/runs"
                f"?head_sha={sha}&per_page=10", token).get("workflow_runs", [])
    if not runs:
        # The skip marker, a path-filter gap, or a push made by a workflow. All three land here.
        msg = head["commit"]["message"]
        marker = "[" + "skip ci" + "]"      # not spelled out: this file's own commit must run CI
        hint = ("The head commit's message contains the CI-skip marker, which GitHub honours "
                "ANYWHERE in the message, including inside a quotation."
                if marker in msg else
                "Either the change touched no path in regression.yml's filters, or the commit "
                "was pushed by a workflow using the default token, which triggers nothing.")
        print(f"\nFAIL: the regression harness has never run on {sha[:7]}.\n  {hint}\n"
              f"  Nothing here is proven. Dispatch the harness on main, or push a commit that "
              f"does trigger it.", file=sys.stderr)
        return 1

    latest = runs[0]
    if latest.get("status") != "completed":
        print(f"\nPENDING: run {latest['id']} is {latest.get('status')}. Not a failure yet.")
        return 0
    if latest.get("conclusion") != "success":
        print(f"\nFAIL: the harness ran on {sha[:7]} and concluded "
              f"{latest.get('conclusion')}.\n  {latest.get('html_url')}", file=sys.stderr)
        return 1

    when = dt.datetime.strptime(latest["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc)
    age = (dt.datetime.now(dt.timezone.utc) - when).days
    if age > a.max_age_days:
        print(f"\nFAIL: the last successful harness run on main is {age} days old "
              f"({when.date()}), past {a.max_age_days}. main has not been proven recently even "
              f"though it looks green.", file=sys.stderr)
        return 1

    print(f"\nOK — regression harness succeeded on {sha[:7]} at {when.isoformat()} "
          f"({age} days ago)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
