#!/usr/bin/env python3
"""Self-contained headless-LibreOffice recalc for the AEG pipeline.

Forces a FULL recalculation of an .xlsx in place so the cached formula results
openpyxl reads afterward are the freshly computed ones.

    from recalc_lo import recalc
    recalc("AEG_Unified_Model.xlsx")   # raises RuntimeError on failure

Implementation: drives LibreOffice from the COMMAND LINE. A throwaway user
profile sets OOXML/ODF "recalculate on load = Always", then `soffice
--convert-to xlsx` reloads the file (recomputing every formula) and writes it
back in place. This needs only `soffice` on PATH -- no `uno` Python module and
no socket bridge -- so it works under any Python version and any CI runner
where LibreOffice is installed (the earlier `import uno` approach broke whenever
the job's Python differed from LibreOffice's, and when python3-uno wasn't
installed).
"""
import os, sys, glob, shutil, subprocess, tempfile

# Force LibreOffice Calc to recompute every formula when it loads a file.
# OOXMLRecalcMode / ODFRecalcMode: 0 = Always, 1 = Never, 2 = Prompt.
_RECALC_XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>
 <item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>
</oor:items>
"""


def _soffice_bin():
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    raise RuntimeError("recalc: LibreOffice (soffice) not found on PATH")


def _probe_value(path, sheet, cell):
    try:
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True)
        return wb[sheet][cell].value
    except Exception:
        return None


def recalc(path, probe=None, timeout=180):
    """Force a full recalc of `path` in place.

    Returns a dict {"ok": True, ...}. If `probe` is given as (sheet, cell), the
    pre- and post-recalc values of that cell are included so a caller can prove
    the recalc actually moved a downstream formula.
    """
    abspath = os.path.abspath(path)
    if not os.path.exists(abspath):
        raise RuntimeError(f"recalc: file not found: {abspath}")

    result = {"ok": True}
    if probe:
        result["probe_before"] = _probe_value(abspath, *probe)

    soffice = _soffice_bin()
    profile = tempfile.mkdtemp(prefix="lo_recalc_")
    outdir = tempfile.mkdtemp(prefix="lo_out_")
    try:
        userdir = os.path.join(profile, "user")
        os.makedirs(userdir, exist_ok=True)
        with open(os.path.join(userdir, "registrymodifications.xcu"),
                  "w", encoding="utf-8") as fh:
            fh.write(_RECALC_XCU)

        cmd = [soffice, "--headless", "--invisible", "--nologo", "--norestore",
               "--nofirststartwizard", "--nodefault",
               f"-env:UserInstallation=file://{profile}",
               "--convert-to", "xlsx:Calc MS Excel 2007 XML",
               "--outdir", outdir, abspath]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"recalc: LibreOffice timed out after {timeout}s")
        tail = proc.stdout.decode("utf-8", "replace")[-800:] if proc.stdout else ""
        if proc.returncode != 0:
            raise RuntimeError(f"recalc: soffice exited {proc.returncode}: {tail}")

        produced = os.path.join(outdir, os.path.basename(abspath))
        if not os.path.exists(produced):
            cands = glob.glob(os.path.join(outdir, "*.xlsx"))
            if not cands:
                raise RuntimeError(f"recalc: no output produced in {outdir}; log: {tail}")
            produced = cands[0]
        shutil.copyfile(produced, abspath)   # store the recalc'd values in place
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(outdir, ignore_errors=True)

    if probe:
        result["probe_after"] = _probe_value(abspath, *probe)
    return result


if __name__ == "__main__":
    import json
    pr = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else None
    print(json.dumps(recalc(sys.argv[1], probe=pr)))
