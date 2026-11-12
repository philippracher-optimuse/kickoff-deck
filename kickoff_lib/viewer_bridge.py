"""Runs INSIDE the model viewer's own Python (optimuse-viewer, installed with `uv tool`).

Uses the viewer's code so the deck shows exactly what the viewer shows:
  - hvac.html        = the viewer's HVAC schematic export (same renderer, zoom, panels), light theme
  - zone_attrs.json  = the viewer's per-zone attributes (setpoints, ventilation, loads ...),
                       keyed by the IDF zone name
  - bridge.json      = viewer version + notes

    <viewer-python> viewer_bridge.py <idf> <out_dir> <project_root>

Standalone on purpose: it must not import kickoff_lib (different Python, different packages).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Visible UI strings of the schematic page -> German (customer deck). Only exact, unique
# fragments of the page markup; the renderer's JS keeps working because ids are untouched.
DE = [
    ("<h1>HVAC schematic</h1>", "<h1>Anlagenschema</h1>"),
    ('placeholder="search components and node names"', 'placeholder="Komponente suchen"'),
    ('title="fit the sheet (F)">Fit<', 'title="Einpassen (F)">Einpassen<'),
    ('title="zoom in">+<', 'title="Vergrößern">+<'),
    ('title="zoom out">', 'title="Verkleinern">'),
    (">Stitch all</button>", ">Alle Verbindungen</button>"),
    ("\n          >Control</button>", "\n          >Regelung</button>"),
    ('<button id="legendBtn">Legend</button>', '<button id="legendBtn">Legende</button>'),
    ('<button id="printBtn">Print</button>', '<button id="printBtn" style="display:none">Drucken</button>'),
    ('<div class="t">Loops</div>', '<div class="t">Kreise</div>'),
    ('placeholder="filter loops"', 'placeholder="Kreise filtern"'),
    ('<div class="lgsec">Components</div>', '<div class="lgsec">Komponenten</div>'),
    ("<span>Heat pump / chiller / boiler</span>", "<span>Wärmepumpe / Kältemaschine / Kessel</span>"),
    ("<span>Pump</span>", "<span>Pumpe</span>"),
    ("<span>Fan</span>", "<span>Ventilator</span>"),
    ("<span>Heating coil</span>", "<span>Heizregister</span>"),
    ("<span>Cooling coil</span>", "<span>Kühlregister</span>"),
    ("<span>Tank / DHW</span>", "<span>Speicher / Warmwasser</span>"),
    ("<span>Outdoor-air system</span>", "<span>Außenluftsystem</span>"),
    ("<span>Splitter</span>", "<span>Verteiler</span>"),
    ("<span>Mixer</span>", "<span>Sammler</span>"),
    ("<span>Valve</span>", "<span>Ventil</span>"),
    ("<span>Zone terminals (group)</span>", "<span>Raumübergabe (Gruppe)</span>"),
    ("<span>Water use (group)</span>", "<span>Wasserverbrauch (Gruppe)</span>"),
    ("<span>Pipe (drawn as link)</span>", "<span>Rohr (als Linie)</span>"),
    ('<div class="lgsec">Connectors</div>', '<div class="lgsec">Verbindungen</div>'),
    ("<span>Flow (supply direction)</span>", "<span>Vorlauf</span>"),
    ("<span>Return (dashed)</span>", "<span>Rücklauf (gestrichelt)</span>"),
]
# strings built by the page's JS (replaced everywhere)
DE_ALL = [
    ('<div class="ln">All loops</div>', '<div class="ln">Alle Kreise</div>'),
    ("' loops on one sheet</span>'", "' Kreise auf einem Blatt</span>'"),
    ("' nodes</span>'", "' Knoten</span>'"),
    ("shown + ' of ' + LOOPS.length + ' loop' + (LOOPS.length === 1 ? '' : 's')",
     "shown + ' von ' + LOOPS.length + ' Kreis' + (LOOPS.length === 1 ? '' : 'en')"),
    ("' aggregated'", "' zusammengefasst'"),
]
# compact layout for a slide (the page is shown in a ~1150 x 450 px frame)
SLIDE_CSS = ("<style>#side{width:210px}.attrib,#exp{display:none}#bar{gap:6px;padding:5px 10px}"
             "#bar button{padding:3px 8px}#bar input[type=search]{width:170px}</style></head>")


def main() -> int:
    idf, out, root = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    from model_viewer import project_paths
    project_paths.set_project_root(root)
    from model_viewer.extract_scene import parse_idf, build_zone_attrs, _zone_key
    from model_viewer import extract_hvac, hvac_export
    notes, info = [], {}
    try:
        from importlib.metadata import version
        info["viewer_version"] = version("optimuse-viewer")
    except Exception:  # noqa: BLE001
        info["viewer_version"] = "?"
    objs = parse_idf(idf)

    # -- zone attributes (same numbers as the viewer's inspector) --------------
    try:
        from model_viewer.schedules import SchedLib
        attrs = build_zone_attrs(objs, None, SchedLib(objs))
        by_name = {}
        for row in objs.get("zone", []):
            if not row:
                continue
            name = row[0].strip()
            a = attrs.get(_zone_key(name)) or attrs.get(name)
            if a:
                by_name[name] = {k: v for k, v in a.items() if k != "schedules"}
        (out / "zone_attrs.json").write_text(json.dumps(by_name, ensure_ascii=False), encoding="utf-8")
        info["zones"] = len(by_name)
    except Exception as e:  # noqa: BLE001
        notes.append(f"zone attributes: {type(e).__name__}: {e}")

    # -- HVAC schematic export ---------------------------------------------------
    try:
        payload = extract_hvac.build_hvac(objs, extract_hvac.load_field_labels())
        if payload.get("nodes"):
            try:
                from model_viewer.hvac_details_idf import IdfDetails
                details = IdfDetails(idf)
            except Exception as e:  # noqa: BLE001
                details, _ = None, notes.append(f"hvac details: {e}")
            html, xn = hvac_export.build_export(payload, details, False, idf.stem, hvac_export.DEFAULT_BUDGET)
            for a, b in DE:
                html = html.replace(a, b, 1)
            for a, b in DE_ALL:
                html = html.replace(a, b)
            html = html.replace("</head>", SLIDE_CSS, 1)
            (out / "hvac.html").write_text(html, encoding="utf-8")
            notes += xn
            info["hvac_loops"] = len(payload.get("loops", []))
        else:
            notes.append("no HVAC topology in this IDF")
    except Exception as e:  # noqa: BLE001
        notes.append(f"hvac export: {type(e).__name__}: {e}")

    info["notes"] = notes
    (out / "bridge.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ok: {info.get('zones', 0)} zones, {info.get('hvac_loops', 0)} HVAC loops")
    return 0


if __name__ == "__main__":
    sys.exit(main())
