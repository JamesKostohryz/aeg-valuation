"""Region 2's COMMON(t) term -- the 2026-08-19 change, under CI.

WHY THESE TESTS EXIST. Region 2 was ZERO for 490 of 499 names and no test in this repository
could see it, because zero is an arithmetically perfect value. The tests below assert three
things a future edit could quietly break: that the front-tenor identity survives, that the new
T4 identity holds at every tenor, and -- the one that matters most -- that COMMON(t) actually
MOVES a published number rather than sitting there being consistent.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "idio"))

import erp as IE  # noqa: E402

CAP = {"A": 3.0, "B": 1.0, "C": 2.0}
WIDEN = {"A": {h: 0.010 * (h - 1) for h in IE.GRID},
         "B": {h: 0.030 * (h - 1) for h in IE.GRID},
         "C": None}
COMMON = {h: 0.02 * (h - 1) for h in IE.GRID}
MKT = {h: 3.0 for h in IE.GRID}
INC = {"A": -0.5, "B": 1.5, "C": 0.0}


def test_selftest_passes():
    assert IE.selftest(verbose=False)


def test_common_is_zero_at_the_front_tenor():
    c = IE.common_widening({1: 0.49, 10: 0.98, 30: 1.02})
    assert c[IE.FRONT_TENOR] == 0.0


def test_region2_refuses_a_missing_common():
    import pytest
    with pytest.raises(ValueError):
        IE.region2(WIDEN, CAP, None)


def test_capweighted_mean_region2_equals_mc_times_common():
    r2, _ = IE.region2(WIDEN, CAP, COMMON)
    tot = sum(CAP.values())
    for h in IE.GRID:
        m = sum(CAP[t] * r2[t][h] for t in CAP) / tot
        assert abs(m - IE.M_COMMON * COMMON[h]) < 1e-12


def test_every_name_carries_common_including_those_with_no_bonds():
    """THE POINT OF THE WHOLE CHANGE. A name with no issuer curve used to get exactly zero."""
    r2, _ = IE.region2(WIDEN, CAP, COMMON)
    for h in IE.GRID:
        if h == IE.FRONT_TENOR:
            continue
        assert r2["C"][h] > 0, "a bondless name is back to zero Region 2 at tenor %d" % h


def test_common_does_not_reorder_companies():
    r2, _ = IE.region2(WIDEN, CAP, COMMON)
    r2z, _ = IE.region2(WIDEN, CAP, IE.zero_common())
    for h in IE.GRID:
        assert abs((r2["A"][h] - r2["B"][h]) - (r2z["A"][h] - r2z["B"][h])) < 1e-12


def test_t4_identity_holds_at_every_tenor():
    r2, _ = IE.region2(WIDEN, CAP, COMMON)
    r3 = {t: IE.region3(10 + 5 * i, grid=IE.GRID) for i, t in enumerate(sorted(CAP))}
    ok, worst, tenor = IE.t4_identity(INC, r2, r3, CAP, MKT, COMMON)
    assert ok, "T4 identity off by %.3e pp at tenor %r" % (worst, tenor)


def test_front_tenor_identity_is_unchanged_by_the_change():
    r2, _ = IE.region2(WIDEN, CAP, COMMON)
    tot = sum(CAP.values())
    m = sum(CAP[t] * (IE.decay(1) * INC[t] + r2[t][1]) for t in CAP) / tot
    assert abs(m) < 1e-12


def test_common_is_not_inert():
    """THE INFLUENCE GUARD. Perturb COMMON and demand that every company's number moves."""
    r3 = {t: IE.region3(40, grid=IE.GRID) for t in CAP}
    ok, detail = IE.influence_check(INC, WIDEN, CAP, MKT, r3)
    assert ok, "COMMON(t) is inert: %r" % (detail,)
    assert abs(detail["universe_move_pp"]) > 1e-3
    assert not detail["inert_names"]
