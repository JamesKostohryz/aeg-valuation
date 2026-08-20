#!/usr/bin/env python3
"""
pipeline/add_company.py — dispatch real-yields' company-data for one ticker and WAIT for it.

Step 1 of adding a company. It exists so that adding a company is one button instead of two
across two repositories, and so that step 2 (onboarding) cannot start before step 1 has actually
published. Onboarding refuses without the rate side, and that refusal reads like a defect when
it is really a race.

WAITING IS THE WHOLE POINT. A fire-and-forget dispatch would return success immediately and hand
onboarding a repository that has not been written to yet -- intermittently, depending on how busy
the runners are, which is the worst kind of failure to debug. So this polls until the run it
started finishes, and fails if it failed.

IDENTIFYING THE RUN IT STARTED. The dispatch API returns 204 and no run id, so the run has to be
found afterwards. Recording the newest run id BEFORE dispatching and then waiting for one newer
than that is what makes it unambiguous; matching on ticker or on "the most recent run" would
happily attach to somebody else's concurrent dispatch and report their result as ours.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

RY_OWNER = "JamesKostohryz"
RY_REPO = "real-yields"
RY_WORKFLOW = "company.yml"
API = "https://api.github.com"

POLL_S = 15
TIMEOUT_S = 45 * 60          # the rate side pulls bonds and rebuilds thirty tenors


class AddCompanyError(Exception):
    pass


def _api(path: str, token: str, method: str = "GET", body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=(json.dumps(body).encode() if body is not None else None),
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "aeg-add-company"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)


def _runs(token, per_page=10):
    _, d = _api(f"/repos/{RY_OWNER}/{RY_REPO}/actions/workflows/{RY_WORKFLOW}"
                f"/runs?per_page={per_page}", token)
    return (d or {}).get("workflow_runs", [])


def dispatch_and_wait(ticker: str, token: str, obs_category: str = "KEEP",
                      ory_override: str = "", wait: bool = True,
                      timeout_s: int = TIMEOUT_S, poll_s: int = POLL_S, log=print) -> dict:
    t = ticker.strip().upper()

    before = _runs(token)
    newest_before = before[0]["id"] if before else 0

    status, _ = _api(f"/repos/{RY_OWNER}/{RY_REPO}/actions/workflows/{RY_WORKFLOW}/dispatches",
                     token, "POST",
                     {"ref": "main",
                      "inputs": {"ticker": t, "obs_category": obs_category,
                                 "ory_override": ory_override}})
    if status != 204:
        raise AddCompanyError(f"real-yields company-data dispatch for {t} returned HTTP {status}")
    log(f"[add] dispatched real-yields company-data for {t} "
        f"(durability {obs_category})")
    if not wait:
        return {"ticker": t, "waited": False}

    deadline = time.time() + timeout_s
    run = None
    while time.time() < deadline:
        time.sleep(poll_s)
        for r in _runs(token):
            if r["id"] > newest_before:
                run = r
                break
        if run:
            break
    if run is None:
        raise AddCompanyError(
            f"no new company-data run appeared within {timeout_s // 60} minutes of dispatching "
            f"{t}. The dispatch was accepted, so either the runner queue is backed up or the "
            f"workflow was disabled. Refusing rather than onboarding against a rate side that "
            f"may not exist.")

    log(f"[add] watching run {run['id']} ({run['html_url']})")
    while time.time() < deadline:
        _, cur = _api(f"/repos/{RY_OWNER}/{RY_REPO}/actions/runs/{run['id']}", token)
        if cur and cur.get("status") == "completed":
            if cur.get("conclusion") != "success":
                raise AddCompanyError(
                    f"real-yields company-data for {t} finished {cur.get('conclusion')}. The "
                    f"rate side was NOT published, so onboarding would refuse anyway. See "
                    f"{cur.get('html_url')}")
            log(f"[add] rate side published for {t}")
            return {"ticker": t, "waited": True, "run_id": run["id"],
                    "url": cur.get("html_url")}
        time.sleep(poll_s)
    raise AddCompanyError(
        f"real-yields company-data for {t} did not finish within {timeout_s // 60} minutes "
        f"({run.get('html_url')}). Not onboarding against an unfinished rate side.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build one company's rate side and wait for it.")
    ap.add_argument("ticker")
    ap.add_argument("--obs-category", default="KEEP",
                    help="A durable / B moderate / C exposed, or KEEP to reuse what is recorded")
    ap.add_argument("--ory-override", default="")
    ap.add_argument("--wait", action="store_true", default=False)
    ap.add_argument("--timeout-min", type=int, default=TIMEOUT_S // 60)
    a = ap.parse_args(argv)

    token = os.environ.get("CROSS_REPO_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("CROSS_REPO_TOKEN not set — dispatching a workflow in real-yields needs a token "
              "with actions:write there. The default GITHUB_TOKEN cannot reach another "
              "repository.", file=sys.stderr)
        return 2
    try:
        dispatch_and_wait(a.ticker, token, obs_category=a.obs_category,
                          ory_override=a.ory_override, wait=a.wait,
                          timeout_s=a.timeout_min * 60)
    except (AddCompanyError, urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"\n[add] REFUSED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
