#!/usr/bin/env python3
"""Kick-off tool - command line.

    python kickoff.py init     <projekt>            # create/refresh kickoff/kickoff_brief.json + sources.md
    python kickoff.py status   <projekt>            # stage + what is still open
    python kickoff.py stage    <projekt> <none|model|baseline|auto>   # set project stage by hand
    python kickoff.py build    <projekt> [--export] # customer deck: interactive .html (+ PDF/PPTX with --export)
    python kickoff.py protocol <projekt> [--export] # protocol .md + A4 .html (+ PDF)
    python kickoff.py handover <projekt>            # hand kickoff_brief to the process (see runbook K4)

<projekt> = project root folder. Run with the PROJECT's Python so deckkit + playwright are found:
    <projekt>\\.venv\\Scripts\\python.exe kickoff.py build <projekt> --export
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kickoff_lib import brief as B, collect, deck, protocol  # noqa: E402
from kickoff_lib.project import Project  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="OPTIMUSE Kick-off-Tool")
    ap.add_argument("cmd", choices=["init", "status", "stage", "build", "protocol", "handover"])
    ap.add_argument("project")
    ap.add_argument("value", nargs="?")
    ap.add_argument("--export", action="store_true", help="zusätzlich PDF/PPTX (braucht playwright + chromium)")
    ap.add_argument("--product", choices=B.PRODUCTS, help="gebuchtes Produkt setzen")
    a = ap.parse_args()
    prj = Project.open(a.project)
    b = B.load(prj)
    if a.product:
        b["meta"]["product"] = a.product

    if a.cmd == "init":
        log = collect.run(prj, b)
        print("\n".join(f"  · {x}" for x in log) or "  · keine Projektdaten gefunden")
        print(f"→ {B.save(prj, b)}\n→ {os.path.join(prj.kdir, 'sources.md')}  (für die AI)")
    elif a.cmd == "status":
        print(f"Launcher: {prj.launcher()} · Stand: {b['meta']['stage'] or '—'} ({b['meta']['stage_set_by']}) · "
              f"Produkt: {b['meta']['product']} · project_brief.json: {'ja' if prj.exists('project_brief') else 'nein'}")
        for k, v in B.open_count(b).items():
            print(f"  {k:<14} {json.dumps(v, ensure_ascii=False)}")
    elif a.cmd == "stage":
        if a.value == "auto":
            b["meta"]["stage_set_by"] = "auto"
            collect.run(prj, b)
        elif a.value in B.STAGES:
            b["meta"].update(stage=a.value, stage_set_by="manual")
        else:
            ap.error("stage: none | model | baseline | auto")
        B.save(prj, b)
        print(f"Stand = {b['meta']['stage']}")
    elif a.cmd == "build":
        B.save(prj, b)
        for p in deck.build(prj, b, export=a.export):
            print("→", p)
    elif a.cmd == "protocol":
        for p in protocol.build(prj, b, export=a.export):
            print("→", p)
    elif a.cmd == "handover":
        for p in protocol.handover(prj, b):
            print("→", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
