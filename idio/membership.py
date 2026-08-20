"""
idio/membership.py — where the S&P 500 membership list comes from, and when it may change.

WHAT WAS WRONG. `idio/universe.txt` held 503 tickers as a plain text file committed by hand on
2026-08-19. Nothing updated it. The monthly `idio-universe-refresh` workflow rebuilt the
semi-deviation and the cap weights FOR THE DECLARED NAMES, but never the names themselves. The
index reconstitutes quarterly plus ad hoc, so roughly twenty to twenty-five names a year would
have drifted out of that file with every gate reporting green.

THIS EXACT FAILURE HAS ALREADY COST A NUMBER. The list before 2026-08-19 was a 228-name research
sample missing 282 constituents including NVIDIA, Lilly and Tesla. The cap-weighted average
semi-deviation is the DENOMINATOR of every company premium, so the omission depressed it by
9.25% and inflated every premium in the system. Nothing could see it, because a frozen list is
arithmetically perfect.

THE SOURCE. EODHD publishes the index constituents at `fundamentals/GSPC.INDX`: `Components`
is the current membership, `HistoricalTickerComponents` every name that has been in the index
since 2000 with entry and exit dates. This is the same call `AEG-Project/tools/eodhd_store.py`
makes; it is re-implemented here rather than imported because that folder is not a repository
and GitHub Actions cannot reach it. One source, two readers, no second vintage.

THE DISCIPLINE, WHICH CUTS BOTH WAYS.
    A list that never changes is a fossil     -> so the refresh reads the index, not the file.
    A list that rewrites itself is invisible  -> so the file stays committed, the diff is the
                                                 record, and a large change REFUSES rather than
                                                 quietly reconciling.

Three guards, all fail-closed, because every one of them protects a denominator:

    G1  SIZE.   The payload must carry between MIN_MEMBERS and MAX_MEMBERS names. A truncated
                or partial API response that returned 40 constituents would otherwise shrink the
                universe to 40 and produce wrong premiums for every name, including the ones
                that resolved.
    G2  DRIFT.  Entrants plus leavers against the committed file must not exceed MAX_DRIFT.
                Ordinary reconstitution moves a handful of names a quarter; twenty at once means
                either the index changed in a way somebody should look at, or we are reading a
                different index. Ratify it deliberately with `--accept-membership`.
    G3  OVERLAP. The two lists must share at least MIN_OVERLAP of their names, independently of
                MAX_DRIFT, so that a payload for the wrong index cannot pass by being the same
                size as ours.

A drift inside the limits is APPLIED and RECORDED: `universe.txt` is rewritten, the entrants and
leavers go into `idio_universe_latest.json`, and the workflow commits both. The commit is the
thing a person can see. `universe.txt` is therefore an OUTPUT of the refresh and no longer an
input to it — kept in the repository so a valuation can be reproduced against the membership of
its own date.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(HERE, "universe.txt")

INDEX_CODE = "GSPC.INDX"
EODHD_BASE = "https://eodhd.com/api"

# G1. The S&P 500 has carried between 500 and 505 tradeable lines for decades (a handful of
# companies have two share classes). The window is deliberately wide enough that a real index
# change passes and narrow enough that a truncated payload cannot.
MIN_MEMBERS = 480
MAX_MEMBERS = 530

# G2. Quarterly reconstitution plus ad hoc changes move roughly twenty to twenty-five names a
# YEAR. Against a monthly refresh, more than five in one cycle is not routine.
MAX_DRIFT = 5

# G3. Independent of MAX_DRIFT: a payload that shares less than this with the committed list is
# not this index, whatever its size.
MIN_OVERLAP = 0.90


class MembershipRefused(Exception):
    """Nothing is written; the committed universe file stands and the refresh does not run."""


# ------------------------------------------------------------------ the source

def _get(url: str, timeout: int = 60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_index_payload(api_key: str, code: str = INDEX_CODE, timeout: int = 60) -> dict:
    q = urllib.parse.urlencode(dict(api_token=api_key, fmt="json"))
    d = _get(f"{EODHD_BASE}/fundamentals/{code}?{q}", timeout=timeout)
    if not isinstance(d, dict):
        raise MembershipRefused(f"{code} returned {type(d).__name__}, not an object")
    return d


def current_from_payload(payload: dict) -> list:
    """The tickers in `Components`, uppercased and sorted. Same field the canonical store reads."""
    comps = payload.get("Components") or {}
    out = set()
    for _, c in comps.items():
        code = (c or {}).get("Code")
        if code:
            out.add(str(code).strip().upper())
    return sorted(out)


def former_from_payload(payload: dict) -> dict:
    """{ticker: {start, end, active, delisted}} for every name that has been in the index.

    Not used to build the current universe. It is returned so that anything computing a
    historical aggregate has the survivorship-free membership available from the same call,
    rather than being tempted to reconstruct it from today's list.
    """
    hist = payload.get("HistoricalTickerComponents") or {}
    out = {}
    for _, c in hist.items():
        code = (c or {}).get("Code")
        if code:
            out[str(code).strip().upper()] = {
                "start": c.get("StartDate"), "end": c.get("EndDate"),
                "active": bool(c.get("IsActiveNow")), "delisted": bool(c.get("IsDelisted"))}
    return out


# ------------------------------------------------------------------ the committed record

def read_committed(path: str = UNIVERSE_FILE) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return sorted({ln.strip().upper() for ln in f
                       if ln.strip() and not ln.lstrip().startswith("#")})


def write_committed(tickers, path: str = UNIVERSE_FILE, asof: str | None = None) -> str:
    """Rewrite the committed record. This is an OUTPUT of the refresh: the file exists so a
    valuation can be reproduced against the membership of its own date, and so that a change of
    membership is a diff somebody can see rather than a silent move in every denominator."""
    body = "\n".join(sorted({t.strip().upper() for t in tickers if t.strip()}))
    header = (
        "# idio/universe.txt — the S&P 500 membership the company-premium universe was built on.\n"
        "#\n"
        "# GENERATED. Written by idio/membership.py from the EODHD GSPC.INDX constituents on\n"
        "# each run of the idio-universe-refresh workflow. Do not hand-edit: the next refresh\n"
        "# will overwrite it, and a hand-edit is exactly the drift this file was frozen by\n"
        "# before 2026-08-19. To change the universe deliberately, change the source or the\n"
        "# guards in membership.py.\n"
        "#\n"
        "# It is committed so that (a) a membership change is a visible diff and (b) a past\n"
        "# valuation can be reproduced against the membership of its own date.\n"
        "%s\n" % (("# as of %s\n" % asof) if asof else ""))
    with open(path, "w") as f:
        f.write(header + body + "\n")
    return path


# ------------------------------------------------------------------ the guards

def reconcile(live, committed, max_drift: int = MAX_DRIFT, accept: bool = False) -> dict:
    """Compare the live index membership with the committed record and decide whether the
    refresh may proceed. Raises MembershipRefused rather than reconciling silently."""
    live_s, comm_s = set(live), set(committed)

    if not (MIN_MEMBERS <= len(live_s) <= MAX_MEMBERS):
        raise MembershipRefused(
            f"G1 SIZE: the index payload carries {len(live_s)} constituents, outside "
            f"[{MIN_MEMBERS}, {MAX_MEMBERS}]. A partial or truncated payload would shrink the "
            f"cap-weighted average semi-deviation, which is the DENOMINATOR of every company's "
            f"premium — so it does not give slightly worse premiums, it gives wrong ones for "
            f"every name. Refusing; the committed list stands.")

    if not comm_s:                       # first ever run: nothing to reconcile against
        return dict(tickers=sorted(live_s), entrants=sorted(live_s), leavers=[],
                    drift=len(live_s), overlap=None, bootstrap=True, accepted=True)

    entrants = sorted(live_s - comm_s)
    leavers = sorted(comm_s - live_s)
    drift = len(entrants) + len(leavers)
    overlap = len(live_s & comm_s) / float(max(len(live_s), len(comm_s)))

    if overlap < MIN_OVERLAP:
        raise MembershipRefused(
            f"G3 OVERLAP: the live list shares only {overlap:.1%} of its names with the "
            f"committed one (floor {MIN_OVERLAP:.0%}). Sizes are {len(live_s)} live against "
            f"{len(comm_s)} committed, so this is not a reconstitution — it is probably a "
            f"different index. Refusing.")

    if drift > max_drift and not accept:
        raise MembershipRefused(
            f"G2 DRIFT: {drift} names differ from the committed list ({len(entrants)} in, "
            f"{len(leavers)} out; limit {max_drift}).\n"
            f"  entering: {', '.join(entrants[:20])}{' …' if len(entrants) > 20 else ''}\n"
            f"  leaving:  {', '.join(leavers[:20])}{' …' if len(leavers) > 20 else ''}\n"
            f"Ordinary reconstitution moves a handful of names a quarter. A change this size is "
            f"either something to look at or the wrong payload, and it moves the denominator of "
            f"every premium either way. Re-run with --accept-membership to ratify it "
            f"deliberately. Refusing; the committed list stands.")

    return dict(tickers=sorted(live_s), entrants=entrants, leavers=leavers, drift=drift,
                overlap=overlap, bootstrap=False, accepted=bool(drift <= max_drift or accept))


def resolve(api_key: str, path: str = UNIVERSE_FILE, accept: bool = False,
            payload: dict | None = None, log=print) -> dict:
    """The one call the feed makes. Returns the reconciliation dict; writes nothing."""
    p = payload if payload is not None else fetch_index_payload(api_key)
    live = current_from_payload(p)
    committed = read_committed(path)
    log(f"index membership: {len(live)} live constituents, {len(committed)} committed")
    r = reconcile(live, committed, accept=accept)
    if r["bootstrap"]:
        log(f"  no committed list — bootstrapping from {len(r['tickers'])} names")
    elif r["drift"] == 0:
        log("  membership unchanged (0 entrants, 0 leavers)")
    else:
        log(f"  membership CHANGED: +{len(r['entrants'])} {r['entrants']} "
            f"/ -{len(r['leavers'])} {r['leavers']}")
    return r
