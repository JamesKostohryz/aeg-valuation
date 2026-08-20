"""
tests/test_idio_membership.py — hermetic tests for the index membership guards.

No network. The index payload comes from `tests/fixtures/idio_gspc_components.json`, a trimmed
copy of the EODHD GSPC.INDX response of 2026-08-19: all 503 `Components`, and fifteen
`HistoricalTickerComponents` (ten names that have left the index, five still active) so the
survivorship-free shape is exercised without carrying all 819.

WHAT THESE TESTS ARE FOR. The frozen membership list is the eighth instance of this project's
signature defect — a number silently wrong or silently inert while every gate reports success —
and the first one caught before it bit. An identity check cannot see influence, and a frozen
list cannot see itself. So these tests do not check that the guards exist; they check that each
guard DISCRIMINATES: that it fires on the failure it is for, and does not fire on the ordinary
case it must let through.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "idio"))

import membership as MB  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "idio_gspc_components.json")


@pytest.fixture(scope="module")
def payload():
    with open(FIXTURE) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def live(payload):
    return MB.current_from_payload(payload)


# ------------------------------------------------------------------ reading the source

def test_the_payload_yields_the_full_index(live):
    assert 480 <= len(live) <= 530, len(live)
    assert len(live) == len(set(live))
    assert all(t == t.strip().upper() for t in live)


def test_the_names_that_broke_it_last_time_are_present(live):
    """The pre-2026-08-19 list was a 228-name research sample missing 282 constituents,
    including these three, and the omission depressed the cap-weighted average semi-deviation —
    the denominator of every premium — by 9.25%."""
    for t in ("NVDA", "LLY", "TSLA"):
        assert t in live, f"{t} missing from the live index membership"


def test_former_members_carry_entry_and_exit_dates(payload):
    former = MB.former_from_payload(payload)
    assert former, "no historical components parsed"
    left = [v for v in former.values() if not v["active"]]
    assert left, "fixture carries no name that has left the index"
    assert all("start" in v and "end" in v for v in former.values())


def test_the_committed_file_matches_the_live_index_today(live):
    """VERIFIED 2026-08-19: 503 against 503, zero difference, because both were built from the
    same source on the same day. This test is what turns that into a standing fact rather than
    a note in a handoff — if it ever fails, either the refresh has not run or the file was
    hand-edited, and both are the drift this module exists to stop."""
    committed = MB.read_committed()
    assert committed, "idio/universe.txt is empty or missing"
    assert set(committed) == set(live), (
        "committed universe.txt and the index fixture disagree: "
        f"+{sorted(set(live) - set(committed))[:10]} "
        f"-{sorted(set(committed) - set(live))[:10]}")


# ------------------------------------------------------------------ G1: size

def test_a_truncated_payload_is_refused(live):
    """The failure that costs a number: a partial response shrinks the universe, the
    cap-weighted average semi-deviation falls, and EVERY premium inflates — including for the
    names that resolved perfectly."""
    with pytest.raises(MB.MembershipRefused, match="G1 SIZE"):
        MB.reconcile(live[:40], live)


def test_an_oversized_payload_is_refused(live):
    with pytest.raises(MB.MembershipRefused, match="G1 SIZE"):
        MB.reconcile(live + ["ZZ%03d" % i for i in range(60)], live)


def test_the_size_guard_lets_a_real_index_through(live):
    """It must not be so tight that an ordinary index of 500-505 lines trips it."""
    assert MB.reconcile(live, live)["drift"] == 0


# ------------------------------------------------------------------ G2: drift

def test_an_ordinary_reconstitution_passes(live):
    changed = sorted(set(live) - {live[0], live[1]} | {"AAAA", "BBBB"})
    r = MB.reconcile(changed, live)
    assert r["drift"] == 4 and r["accepted"]
    assert r["entrants"] == ["AAAA", "BBBB"]
    assert r["leavers"] == sorted([live[0], live[1]])


def test_a_large_drift_refuses_rather_than_reconciling_silently(live):
    changed = sorted(set(live) - set(live[:15]) | {"Z%03d" % i for i in range(15)})
    with pytest.raises(MB.MembershipRefused, match="G2 DRIFT"):
        MB.reconcile(changed, live)


def test_a_large_drift_can_be_ratified_deliberately(live):
    changed = sorted(set(live) - set(live[:15]) | {"Z%03d" % i for i in range(15)})
    r = MB.reconcile(changed, live, accept=True)
    assert r["drift"] == 30 and r["accepted"]


def test_the_refusal_names_the_entrants_and_leavers(live):
    """A refusal a person cannot act on becomes a flag somebody switches off."""
    changed = sorted(set(live) - set(live[:15]) | {"ZZTOP"})
    with pytest.raises(MB.MembershipRefused) as e:
        MB.reconcile(changed, live)
    assert "ZZTOP" in str(e.value) and live[0] in str(e.value)


# ------------------------------------------------------------------ G3: overlap

def test_a_different_index_of_the_same_size_is_refused(live):
    """G2 alone cannot catch this if the wrong index happens to be about 500 names, so the
    overlap floor is independent of the drift limit."""
    other = ["Q%03d" % i for i in range(len(live))]
    with pytest.raises(MB.MembershipRefused, match="G3 OVERLAP"):
        MB.reconcile(other, live, accept=True)


def test_overlap_is_checked_before_drift_is_ratified(live):
    """--accept-membership ratifies a reconstitution. It must not be able to ratify reading
    the wrong index."""
    other = ["Q%03d" % i for i in range(len(live))]
    with pytest.raises(MB.MembershipRefused, match="G3 OVERLAP"):
        MB.reconcile(other, live, accept=True)


# ------------------------------------------------------------------ bootstrap + round trip

def test_a_first_run_with_no_committed_file_bootstraps(live):
    r = MB.reconcile(live, [])
    assert r["bootstrap"] and r["leavers"] == [] and len(r["entrants"]) == len(live)


def test_write_then_read_round_trips(tmp_path, live):
    p = str(tmp_path / "universe.txt")
    MB.write_committed(live, path=p, asof="2026-08-19")
    assert MB.read_committed(p) == sorted(live)
    text = open(p).read()
    assert "GENERATED" in text and "Do not hand-edit" in text
    assert "as of 2026-08-19" in text


def test_resolve_uses_an_injected_payload_without_network(payload, tmp_path, live):
    p = str(tmp_path / "universe.txt")
    MB.write_committed(live, path=p)
    r = MB.resolve("no-key", path=p, payload=payload, log=lambda *_: None)
    assert r["drift"] == 0 and set(r["tickers"]) == set(live)
