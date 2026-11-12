"""Use the installed model viewer (optimuse-viewer) for the HVAC schematic and zone attributes.

The viewer lives in its own `uv tool` environment, so we do not import it: we run
`viewer_bridge.py` with the viewer's Python and read what it writes to `kickoff/.viewer/`.
Cached on the IDF's modification time. No viewer installed -> empty result, the deck falls
back to its own extraction (3D model with fewer room details, HVAC as a written list).

Override the Python with the environment variable OPTIMUSE_VIEWER_PY if needed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def viewer_python() -> str | None:
    env = os.environ.get("OPTIMUSE_VIEWER_PY")
    if env and os.path.isfile(env):
        return env
    cands = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", os.path.expanduser("~/AppData/Roaming"))
        cands.append(os.path.join(appdata, "uv", "tools", "optimuse-viewer", "Scripts", "python.exe"))
    cands += [os.path.expanduser("~/.local/share/uv/tools/optimuse-viewer/bin/python")]
    uv = shutil.which("uv")
    if uv:
        try:
            d = subprocess.run([uv, "tool", "dir"], capture_output=True, text=True, timeout=20).stdout.strip()
            if d:
                cands += [os.path.join(d, "optimuse-viewer", "Scripts", "python.exe"),
                          os.path.join(d, "optimuse-viewer", "bin", "python")]
        except Exception:  # noqa: BLE001
            pass
    return next((c for c in cands if os.path.isfile(c)), None)


def export(prj, idf_path: str) -> dict:
    """-> {'hvac_html': str|None, 'zone_attrs': dict, 'info': dict}. Never raises."""
    res = {"hvac_html": None, "zone_attrs": {}, "info": {}}
    if not idf_path:
        return res
    out = os.path.join(prj.kdir, ".viewer")
    stamp_f = os.path.join(out, "source.json")
    src = {"idf": os.path.abspath(idf_path), "mtime": os.path.getmtime(idf_path),
           "bridge": os.path.getmtime(os.path.join(HERE, "viewer_bridge.py"))}
    fresh = os.path.isfile(stamp_f) and json.load(open(stamp_f, encoding="utf-8")) == src
    if not fresh:
        py = viewer_python()
        if not py:
            res["info"] = {"notes": ["Modell-Viewer (optimuse-viewer) nicht gefunden – eigene Darstellung."]}
            return res
        os.makedirs(out, exist_ok=True)
        p = subprocess.run([py, os.path.join(HERE, "viewer_bridge.py"), idf_path, out, prj.root],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
        if p.returncode != 0:
            res["info"] = {"notes": [f"Modell-Viewer-Export fehlgeschlagen: {(p.stderr or p.stdout).strip()[-300:]}"]}
            return res
        json.dump(src, open(stamp_f, "w", encoding="utf-8"))
    for name, key in (("zone_attrs.json", "zone_attrs"), ("bridge.json", "info")):
        f = os.path.join(out, name)
        if os.path.isfile(f):
            res[key] = json.load(open(f, encoding="utf-8"))
    info = res["info"] or {}
    f = os.path.join(out, "hvac.html")
    if info.get("hvac_loops") and os.path.isfile(f):   # files are overwritten, not deleted: trust bridge.json
        res["hvac_html"] = open(f, encoding="utf-8").read()
    if not info.get("zones"):
        res["zone_attrs"] = {}
    return res
