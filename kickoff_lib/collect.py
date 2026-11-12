"""Deterministic pre-fill of kickoff_brief.json from what lies in the project folder.

Only EMPTY fields are filled. Everything the tool cannot read itself (customer PDFs, mails,
transcripts, platform notes) is listed in kickoff/sources.md - the AI reads those and writes
the results into kickoff_brief.json (runbook step K1.3).
"""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import date

from . import brief as B
from . import idf as I
from .project import Project

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
END_USES = [("heating", "Heizung"), ("cooling", "Kühlung"), ("dhw", "Warmwasser"), ("lighting", "Beleuchtung"),
            ("equipment", "Geräte / Nutzer"), ("fans", "Ventilatoren"), ("pumps", "Pumpen"), ("other", "Prozessenergie")]


def _md_table(path: str, heading: str) -> list[list[str]]:
    """Rows of the first markdown table below `## heading`."""
    if not os.path.isfile(path):
        return []
    txt = open(path, encoding="utf-8").read()
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", txt, re.M | re.S)
    if not m:
        return []
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in m.group(1).splitlines()
            if l.strip().startswith("|")]
    return [r for r in rows[2:] if any(r)]   # skip header + separator


def find_idf(prj: Project) -> str | None:
    for pat in prj.layout["idf_globs"]:
        for f in sorted(glob.glob(os.path.join(prj.root, pat))):
            if f.endswith(".idf") and "smoketest" not in f:
                return f
    return None


def detect_stage(prj: Project, b: dict, idf_path: str | None) -> str:
    if b["meta"].get("stage_set_by") == "manual" and b["meta"].get("stage") in B.STAGES:
        return b["meta"]["stage"]
    if prj.exists("enduse") or b["baseline"].get("kpis"):
        return "baseline"
    if idf_path or prj.asset("model3d.png") or prj.asset("model3d.html"):
        return "model"
    return "none"


def run(prj: Project, b: dict) -> list[str]:
    """Fill b in place; returns a log of what was read."""
    log = []
    b["meta"]["launcher"] = prj.launcher()
    today = date.today()

    # 1 project_brief.json (exists after runbook 01)
    if prj.exists("project_brief"):
        B.from_project_brief(b, json.load(open(prj.p("project_brief"), encoding="utf-8")), "[doc:project_brief]")
        log.append("project_brief.json übernommen")

    # 2 platform metadata
    meta_f = prj.first("metadata_glob")
    if meta_f:
        m = json.load(open(meta_f, encoding="utf-8"))
        s = m.get("summary", {})
        a = s.get("address") or {}
        B.setdefault(b, "object", s.get("name"))
        B.setdefault(b["project"], "short", s.get("name"))
        B.setdefault(b["project"], "address", " ".join(x for x in [a.get("road", ""), a.get("house_number", "")] if x)
                     + (f', {a.get("postcode", "")} {a.get("city", "")}' if a.get("city") else ""))
        B.setdefault(b, "construction_year", s.get("construction_year"))
        B.setdefault(b, "gross_floor_area_m2", round(s["total_area_m2"], 1) if s.get("total_area_m2") else None)
        B.setdefault(b["project"], "conditioned_area_m2",
                     round(s["total_conditioned_area_m2"], 1) if s.get("total_conditioned_area_m2") else None)
        B.setdefault(b["project"], "storeys", s.get("storey_count"))
        by = {}
        for sp in m.get("spaces", []):
            k = sp.get("space_type_name_de") or sp.get("space_type_name_en") or "?"
            by[k] = by.get(k, 0) + (sp.get("area_m2") or 0)
        tot = sum(by.values()) or 1
        top = sorted(by, key=by.get, reverse=True)[:3]
        cy = s.get("construction_year")
        kind = "Neubau (Planung)" if cy and cy >= today.year else "Bestand"
        _understand(b, "Objekt", f"{kind}, Baujahr {cy}" if cy else kind, "[platform:metadata]")
        _understand(b, "Nutzung", ", ".join(f"{k} {by[k] / tot * 100:.0f} %" for k in top), "[platform:metadata]")
        log.append(f"Plattform-Metadaten: {os.path.relpath(meta_f, prj.root)}")

    # 3 project identity (old launcher memory): platform url, client, contacts
    ident = os.path.join(prj.root, "memory", "project_identity.md")
    for r in _md_table(ident, "Core"):
        if len(r) >= 2 and r[0].lower() == "platform url":
            B.setdefault(b["project"], "platform_url", r[1])
        if len(r) >= 2 and r[0].lower() == "client":
            B.setdefault(b, "client", r[1])
    if not [t for t in b["team"] if t.get("name") not in ("—", "")]:
        for r in _md_table(ident, "Contacts"):
            if len(r) >= 2 and r[1] not in ("", "—"):
                name, _, org = r[1].partition(",")
                b["team"].append({"name": name.strip(), "role": r[0], "org": org.strip(),
                                  "source": "[doc:memory/project_identity]", "status": "vorgeschlagen"})
        if os.path.isfile(ident):
            log.append("memory/project_identity.md gelesen")

    # 4 IDF: zones, envelope, HVAC
    idf_path = find_idf(prj)
    if idf_path:
        mdl = I.Model(idf_path)
        tag = f"[idf:{os.path.basename(idf_path)}]"
        B.setdefault(b["project"], "zones", len({s['zone'] for s in mdl.surfaces}))
        if not b["envelope"]:
            for e in mdl.envelope():
                val = f'{e["u_value"]:.2f}'.replace(".", ",")
                if "g_value" in e:
                    val += f' · g {e["g_value"]:.2f}'.replace(".", ",")
                b["envelope"].append({"element": f'{e["element"]} ({e["area_m2"]} m²)', "u_value": val,
                                      "source": tag, "status": "vorgeschlagen"})
        for k, v in mdl.hvac_text().items():
            _understand(b, k, v or "keine Anlage im Modell", tag)
        log.append(f"IDF gelesen: {os.path.relpath(idf_path, prj.root)}")

    # 5 baseline end uses (pipeline output, exists once the baseline is simulated)
    if prj.exists("enduse") and not b["baseline"].get("enduse"):
        e = json.load(open(prj.p("enduse"), encoding="utf-8"))
        st = e.get("strategies", {})
        base = st.get("Bestand") or st.get("Baseline") or next(iter(st.values()), {})
        eu = base.get("enduse_mwh", {})
        ngf = e.get("meta", {}).get("ngf_m2") or b.get("gross_floor_area_m2")
        uses = {lab: [round(eu.get(k, 0.0), 2)] for k, lab in END_USES}
        tot = base.get("total_mwh") or sum(v[0] for v in uses.values())
        b["baseline"]["enduse"] = {"carriers": ["Strom"], "uses": uses}
        b["baseline"]["carriers"] = [{"carrier": "Strom", "mwh": round(tot, 1),
                                      "kwh_m2": round(tot * 1000 / ngf) if ngf else None}]
        b["baseline"]["kpis"] = [{"value": f"{tot:.1f} MWh/a".replace(".", ","), "label": "Endenergie"}]
        if ngf:
            b["baseline"]["kpis"].insert(0, {"value": f"{tot * 1000 / ngf:.0f} kWh/m²a", "label": "Endenergie spezifisch"})
        b["baseline"]["source"] = "[doc:07_presentation/data/enduse.json]"
        log.append("enduse.json übernommen (Energieträger: nur Strom ausgewiesen)")

    # 6 defaults the deck always needs
    if not b["scope"]["included"]:
        cat = json.load(open(os.path.join(TOOL, "templates", "products.json"), encoding="utf-8"))
        b["scope"] = cat.get(b["meta"]["product"], cat["Energy Design"])
    for k in ("energy", "general"):
        if not b["assumptions"][k]:
            b["assumptions"][k] = [dict(a, source="[assume:Standard]") for a in B.DEFAULT_ASSUMPTIONS[k]]
    if not any(t.get("role", "").startswith("Entscheider") for t in b["team"]):
        b["team"] += B.DEFAULT_TEAM
    for t in B.UNDERSTANDING_TOPICS:
        _understand(b, t, "", "")

    st = detect_stage(prj, b, idf_path)
    if b["meta"]["stage"] != st:
        b["meta"]["stage"] = st
    b["meta"]["sources_read"] = log
    write_sources(prj)
    return log


def _understand(b: dict, topic: str, value: str, source: str) -> None:
    row = next((r for r in b["understanding"] if r["topic"] == topic), None)
    if row is None:
        b["understanding"].append({"topic": topic, "value": value, "source": source,
                                   "status": "vorgeschlagen" if value else "offen"})
    elif not row.get("value") and value:
        row.update(value=value, source=source, status="vorgeschlagen")


def write_sources(prj: Project) -> str:
    """List of documents the AI must read (the tool cannot read PDFs/mails itself)."""
    lines = ["# Quellen für kickoff_brief.json", "",
             "Vom Tool nicht automatisch gelesen. Die AI liest diese Dateien und trägt die Inhalte",
             "mit Quellen-Tag in kickoff/kickoff_brief.json ein (Runbook Schritt K1.3).", ""]
    groups = [("Kundendokumente", prj.layout["customer_docs"]), ("Transkripte / Notizen", prj.layout["transcripts"]),
              ("Projektnotizen", "notes"), ("Projekt-Gedächtnis", "memory")]
    for title, rel in groups:
        d = os.path.join(prj.root, rel)
        files = sorted(f for f in glob.glob(os.path.join(d, "**", "*"), recursive=True)
                       if os.path.isfile(f) and not f.endswith((".dwg", ".3dm", ".zip")))
        if files:
            lines += [f"## {title}", ""] + [f"- `{os.path.relpath(f, prj.root)}`" for f in files] + [""]
    lines += ["## Cloud-Launcher", "",
              "Liegen die Daten nur auf der Plattform: über die Plattform-Tools lesen",
              "(Kundendateien, Team-Notizen, Gebäudedaten) und ebenfalls hier eintragen.", ""]
    p = os.path.join(prj.kdir, "sources.md")
    open(p, "w", encoding="utf-8").write("\n".join(lines))
    return p
