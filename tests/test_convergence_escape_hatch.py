#!/usr/bin/env python3
"""
tests/test_convergence_escape_hatch.py — does the documented escape hatch actually work?

WHAT THIS IS ABOUT, AND WHAT IT IS NOT ABOUT. It is not about PepsiCo. `convergence.reviewed:
true` is the documented, human-written remedy that a truncation refusal PRINTS IN ITS OWN ERROR
MESSAGE. If it does not clear the gate, then every future company whose scenario trips that gate
is unclearable and the error message is telling the reader to do something that does not work.
That is a live defect on the path of every valuation not yet made, which is why it was worth a
test rather than a fix to one company's yaml.

WHY IT LOOKED BROKEN. A fleet run at ae067d5 printed
`{'convergence_reviewed': False, 'funding_reviewed': False, 'terminal_reviewed': True}` and it
was read as PepsiCo's, because the refusal message names the SCENARIO but never the TICKER. It
is Coca-Cola's: `companies/KO.yaml` has a `terminal:` block and no `convergence:` block at all,
which is precisely that dict. `outputs/PEP_status.csv` and `outputs/KO_status.csv` were written
by the SAME run and record `convergence_reviewed,True` and `,False` respectively. The hatch was
never broken; two companies' output were confused for one, twice, across two sessions.

So this test does the thing neither session did: it runs the hatch A/B on demand.

`check_convergence_escape_hatch.py` alongside is the A/B itself — two real company yamls,
identical except for `convergence:\n  reviewed: true`, both loaded through the production
`config.load_config` and run through the production `run_scenarios` on the golden Apple engine
with the same scenario. Funding and terminal are cleared in both arms so truncation is the only
variable. It is kept as a standalone script because it is also a diagnostic somebody may want to
run by hand and read; this wrapper is what puts it under the regression harness, because a test
nobody runs is not a test.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, "tests", "check_convergence_escape_hatch.py")


def test_convergence_reviewed_clears_a_truncation_gate_it_is_documented_to_clear():
    """Arm 1: no `convergence:` block -> the gate refuses and NO scenarios CSV is written.
    Arm 2: the identical scenario with the flag -> it values, and the four-method tie still
    holds at machine precision, because the hatch clears a PUBLICATION gate and does not touch
    the arithmetic.

    If this fails, do not edit a company yaml. The remedy printed by every truncation refusal on
    this system has stopped working.
    """
    env = dict(os.environ)
    env.setdefault("AAPL_ENG_WORK", "/tmp/_hatch_yaml_work")
    p = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       cwd=ROOT, env=env, timeout=900)
    assert p.returncode == 0, (
        "the convergence escape hatch no longer clears a truncation gate:\n"
        + p.stdout[-6000:] + "\n" + p.stderr[-3000:])
    assert "14 passed, 0 failed" in p.stdout, p.stdout[-4000:]
