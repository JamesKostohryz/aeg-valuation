#!/usr/bin/env python3
"""convergence.py — E2 convergence period, computed on the engine's own recalc'd numbers.

Purpose (see AEG-Engine-Spec-Convergence-Period + AEG-Methodology-Continuing-Period-Value):
the engine hard-truncates AEG at cfg_N, which extrapolates whatever level actual EPS reached —
so stopping at a cyclical peak overvalues and a trough undervalues. This module inserts a
programmatic K-year glide from actual EPS at the forecast end onto the normalized (mid-cycle)
line, books the reversion AEG with the engine's EXACT formulas, and reports a convergence-
corrected equity value plus a reconciliation guard.

It reads the already-recalc'd, already-tied engine and computes an overlay — it does NOT modify
the sealed four-method tie (that stays green at ~1e-15). The equity (EPS-leg) intrinsic is the
headline number; extending the OI/NFE legs inside the template for four-method consistency of the
convergence increment itself is a separate spreadsheet increment (see the spec).

Engine AEG formulas reproduced here (validated to 1.7e-13 against the live AAPL engine):
  normal_t   = actual_{t-1} + rho_t * retained_{t-1}      (Valuation r22)
  AEG_t      = actual_t - normal_t                        (Valuation r23)
  contrib_t  = AEG_t * DF^E_{t-1} / rho_LR                (Valuation r24, t<=cfg_N)
  intrinsic  = normal_1/rho_LR + sum contrib_t            (Valuation r43+r44)

FAITHFULNESS (verified): when the normalized level equals actual EPS at cfg_N (on-trend name),
every convergence AEG is exactly 0 and the corrected value equals today's number to the penny.
So this is safe by construction — it only ever moves a value when actual is genuinely off-trend
AND a normalized level is supplied.
"""
import csv
import os

# reconciliation-guard thresholds (REVIEW above these; tune per spec)
GAP_FRAC_WARN = 0.15      # |actual[N] - norm[N]| / actual[N]  above this => analyst stopped far off-trend
VALUE_FRAC_WARN = 0.10    # |convergence value| / intrinsic     above this => the glide drives material value


def _nm(wb, name):
    dn = wb.defined_names.get(name)
    if not dn:
        return None
    ref = str(dn.value).replace("$", "").replace("'", "")
    sh, cell = ref.split("!")
    try:
        return wb[sh][cell].value
    except Exception:
        return None


def _series(ws, r):
    return [(ws.cell(r, c).value if isinstance(ws.cell(r, c).value, (int, float)) else None)
            for c in range(2, ws.max_column + 1)]   # index 0 = col B = t=0 anchor


def converge_valuation(engine_path, K=3, norm_eps_N=None, shape="geometric"):
    """Compute the convergence-corrected equity value from a recalc'd engine.

    K          : convergence length in years (cfg_converge_K; default 3, 0 = off).
    norm_eps_N : the normalized (mid-cycle) EPS level at the forecast end (year cfg_N).
                 None  -> assume on-trend (norm = actual[N]) => no change (faithfulness path).
                 This is where the normalization engine's line feeds in (E2.1).
    Returns a dict with the corrected value, the convergence schedule, and the guard verdict.
    """
    import openpyxl
    wb = openpyxl.load_workbook(engine_path, data_only=True)
    V = wb["Valuation"]
    rho = _series(V, 5)      # rho_E per year
    eps = _series(V, 7)      # actual EPS per year
    ret = _series(V, 9)      # retained per year
    dfE = _series(V, 16)     # DF^E cumulative
    N = int(_nm(wb, "cfg_N"))
    rho_LR = V["B20"].value
    eng_intrinsic = V["B44"].value

    if K <= 0 or norm_eps_N is None:
        # off => today's behavior, but still emit a PASS guard + the (empty) convergence block
        return {"N": N, "K": K, "retention": (ret[N] / eps[N] if eps[N] else None),
                "eng_intrinsic": eng_intrinsic, "corrected_intrinsic": eng_intrinsic,
                "converge_value_ps": 0.0, "converge_gap_ps": 0.0,
                "verdict": "PASS", "verdict_reason": "convergence off / on-trend (no glide)",
                "schedule": []}

    b = ret[N] / eps[N]
    actualN = eps[N]

    def rho_at(t):
        return rho[t] if (t < len(rho) and isinstance(rho[t], (int, float))) else rho_LR

    # normal (AEG=0) continuation off actual[N]
    npath = {N: actualN}
    for t in range(N + 1, N + K + 1):
        npath[t] = npath[t - 1] * (1 + rho_at(t) * b)

    # geometric glide of the actual->normalized ratio onto that normal path;
    # ratio = norm_eps_N / actual[N] (1.0 => on-trend => glide == npath => AEG 0)
    ratio = norm_eps_N / actualN
    glide = {N: actualN}
    for t in range(N + 1, N + K + 1):
        frac = (t - N) / K
        glide[t] = npath[t] * (ratio ** frac if shape == "geometric" else 1 + (ratio - 1) * frac)

    # book convergence AEG with the engine's exact formulas; extend DF^E
    dfEx = {N: dfE[N]}
    conv_value = 0.0
    sched = []
    for t in range(N + 1, N + K + 1):
        rt = rho_at(t)
        normal_t = glide[t - 1] * (1 + rt * b)
        aeg_t = glide[t] - normal_t
        dfEx[t] = dfEx[t - 1] / (1 + rt)
        contrib = aeg_t * dfEx[t - 1] / rho_LR
        conv_value += contrib
        sched.append({"t": t, "phase": "convergence", "eps": glide[t], "normal_eps": normal_t,
                      "aeg_eps": aeg_t, "contrib_eps": contrib, "coe": rt})

    corrected = eng_intrinsic + conv_value
    gap_ps = actualN - norm_eps_N

    # reconciliation guard (E2.3)
    gap_frac = abs(gap_ps) / actualN if actualN else 0.0
    val_frac = abs(conv_value) / abs(corrected) if corrected else 0.0
    if gap_frac > GAP_FRAC_WARN or val_frac > VALUE_FRAC_WARN:
        verdict, reason = "REVIEW", (
            f"off-trend gap {gap_frac:.0%} of EPS and convergence moves {val_frac:.0%} of value "
            f"— confirm the analyst's stop year and the normalized line")
    else:
        verdict, reason = "PASS", f"gap {gap_frac:.0%} of EPS, convergence value {val_frac:.0%} of intrinsic"

    return {"N": N, "K": K, "retention": b, "eng_intrinsic": eng_intrinsic,
            "corrected_intrinsic": corrected, "converge_value_ps": conv_value,
            "converge_gap_ps": gap_ps, "verdict": verdict, "verdict_reason": reason,
            "schedule": sched}


def write_convergence_csv(result, ticker, out_dir):
    """Emit <T>_convergence.csv: the convergence block (phase-labeled) + guard header."""
    os.makedirs(out_dir, exist_ok=True)
    fn = os.path.join(out_dir, f"{ticker}_convergence.csv")
    with open(fn, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["# convergence guard", f"verdict={result['verdict']}",
                    f"gap_ps={result['converge_gap_ps']:.4f}",
                    f"converge_value_ps={result['converge_value_ps']:.4f}",
                    f"eng_intrinsic={result['eng_intrinsic']:.4f}",
                    f"corrected_intrinsic={result['corrected_intrinsic']:.4f}"])
        w.writerow(["t", "phase", "eps", "normal_eps", "aeg_eps", "contrib_eps", "coe"])
        for row in result["schedule"]:
            w.writerow([row["t"], row["phase"], round(row["eps"], 6), round(row["normal_eps"], 6),
                        round(row["aeg_eps"], 8), round(row["contrib_eps"], 8), round(row["coe"], 6)])
    return fn


def normalized_eps_at_N(engine_path, X=4, g=None):
    """Model-default normalized EPS at the forecast end (year cfg_N): take EPS from each of the
    last X years, grow each forward to cfg_N at the NORMAL rate g = rho_LR * b, and take the
    median (mirrors normalization_engine.normalize_series forward mode, X=4). Growth is normal
    per James (2026-08-06): "walk eps of last 4 years forward and take median... normal growth
    from there." This is what feeds converge_valuation automatically."""
    import openpyxl
    import statistics
    wb = openpyxl.load_workbook(engine_path, data_only=True)
    V = wb["Valuation"]
    eps = _series(V, 7)
    ret = _series(V, 9)
    N = int(_nm(wb, "cfg_N"))
    rho_LR = V["B20"].value
    b = ret[N] / eps[N]
    if g is None:
        g = rho_LR * b
    anchors = [eps[N - a] * (1 + g) ** a for a in range(1, X + 1)
               if N - a >= 0 and isinstance(eps[N - a], (int, float))]
    return statistics.median(anchors) if anchors else eps[N]


def converge_auto(engine_path, K=3, X=4):
    """The automatic pipeline path: derive the normalized level from the engine (model default)
    and apply convergence. Returns the same dict as converge_valuation plus the normalized level."""
    nl = normalized_eps_at_N(engine_path, X=X)
    out = converge_valuation(engine_path, K=K, norm_eps_N=nl)
    out["norm_eps_N"] = nl
    return out


if __name__ == "__main__":
    import sys
    eng = sys.argv[1]
    K = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    nl = float(sys.argv[3]) if len(sys.argv) > 3 else None
    r = converge_auto(eng, K=K) if nl is None else converge_valuation(eng, K=K, norm_eps_N=nl)
    print(f"cfg_N={r['N']} K={r['K']}  engine={r['eng_intrinsic']:.4f}  "
          f"corrected={r['corrected_intrinsic']:.4f}  conv_value={r['converge_value_ps']:+.4f}  "
          f"verdict={r['verdict']} ({r['verdict_reason']})")
