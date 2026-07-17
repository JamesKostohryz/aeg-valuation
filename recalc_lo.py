#!/usr/bin/env python3
"""Self-contained headless-LibreOffice recalc for the AEG loader notebook.

Opens the workbook in a headless LibreOffice instance, forces a FULL
recalculation (calculateAll), and stores the file in place so that the cached
formula results openpyxl reads are the freshly computed ones.

Usage:
    from recalc_lo import recalc
    recalc("AEG_Unified_Model.xlsx")   # raises RuntimeError on failure

Design notes:
  * Uses an explicit socket (host=127.0.0.1) rather than a named pipe -- the
    pipe-based officehelper.bootstrap is unreliable in sandboxed/Colab hosts.
  * Starts a private soffice instance with its own throwaway user profile so it
    never clashes with another LibreOffice on the machine.
  * calculateAll() (not soffice --convert-to) is what actually forces a recompute.
"""
import os, sys, time, subprocess, tempfile, shutil, socket

for _p in ("/usr/lib/libreoffice/program", "/usr/lib/python3/dist-packages"):
    if _p not in sys.path:
        sys.path.append(_p)
import uno  # noqa: E402
from com.sun.star.beans import PropertyValue  # noqa: E402


def _pv(name, value):
    p = PropertyValue(); p.Name = name; p.Value = value
    return p


def _free_port(start=2002):
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def recalc(path, probe=None, timeout=180):
    """Force a full recalc of `path` in place.

    Returns a dict. If `probe` is given as (sheet, cell), the pre- and
    post-recalc values of that cell are returned so the caller can prove the
    recalc actually moved a downstream formula.
    """
    abspath = os.path.abspath(path)
    if not os.path.exists(abspath):
        raise RuntimeError(f"recalc: file not found: {abspath}")
    profile = tempfile.mkdtemp(prefix="lo_recalc_")
    port = _free_port()
    accept = f"socket,host=127.0.0.1,port={port};urp;"
    proc = subprocess.Popen(
        ["soffice", "--headless", "--invisible", "--nologo", "--norestore",
         "--nofirststartwizard", "--nodefault",
         f"-env:UserInstallation=file://{profile}",
         f"--accept={accept}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ctx = None
    try:
        localContext = uno.getComponentContext()
        resolver = localContext.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", localContext)
        conn = (f"uno:socket,host=127.0.0.1,port={port};urp;"
                "StarOffice.ComponentContext")
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                ctx = resolver.resolve(conn)
                break
            except Exception as e:  # not up yet
                last = e
                time.sleep(0.5)
        if ctx is None:
            raise RuntimeError(f"recalc: could not connect to soffice ({last})")

        smgr = ctx.ServiceManager
        desktop = smgr.createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx)
        url = "file://" + abspath
        doc = desktop.loadComponentFromURL(url, "_blank", 0, (_pv("Hidden", True),))
        result = {"ok": True}
        try:
            if probe:
                sh, cell = probe
                result["probe_before"] = doc.Sheets.getByName(sh).getCellRangeByName(cell).getValue()
            doc.calculateAll()
            if probe:
                sh, cell = probe
                result["probe_after"] = doc.Sheets.getByName(sh).getCellRangeByName(cell).getValue()
            doc.store()
        finally:
            doc.close(False)
        return result
    finally:
        try:
            if ctx is not None:
                desktop = ctx.ServiceManager.createInstanceWithContext(
                    "com.sun.star.frame.Desktop", ctx)
                desktop.terminate()
        except Exception:
            pass
        try:
            proc.terminate(); proc.wait(timeout=20)
        except Exception:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    import json
    pr = None
    if len(sys.argv) > 3:
        pr = (sys.argv[2], sys.argv[3])
    print(json.dumps(recalc(sys.argv[1], probe=pr)))
