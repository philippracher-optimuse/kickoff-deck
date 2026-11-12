"""kickoff_brief.json - the one input file of the kick-off deck.

Shape follows project_brief.json (runbook 01 §2.5: client, object, usage, goals, criteria,
constraints, regulatory, decisions_due - same field names, same source tags) and adds what
the kick-off needs (team, scope, understanding, envelope, baseline, assumptions, findings,
strategies, open items) plus a `status` per entry:

    vorgeschlagen  from documents / assumption, not yet confirmed by the customer
    bestaetigt     confirmed in the kick-off
    geaendert      changed in the kick-off (old value kept in changelog)
    offen          still missing

Rules: the tool only fills EMPTY fields (never overwrites what the AI or a person wrote);
every value carries a source tag `[doc:...]`, `[platform:...]`, `[assume:...]`, `[kickoff:...]`.
"""
from __future__ import annotations

import copy
import json
import os
import re

from .project import Project, now_iso

SCHEMA = "kickoff_brief/1"
STATUSES = ("vorgeschlagen", "bestaetigt", "geaendert", "offen")
STAGES = ("none", "model", "baseline")   # ohne Pläne / 3D-Modell da / Baseline da
PRODUCTS = ("Energy Design", "Value Engineering", "Energy Performance Analytics")

UNDERSTANDING_TOPICS = ["Objekt", "Nutzung", "Bilanzgrenze", "Besonderheit", "Wärme", "Kälte",
                        "Lüftung", "Warmwasser", "Anlass", "Halten / Verkaufen"]

EMPTY = {
    "schema": SCHEMA,
    "meta": {"created": "", "updated": "", "launcher": "", "stage": "", "stage_set_by": "auto",
             "product": "Energy Design", "kickoff_date": "", "sources_read": []},
    # same keys as project_brief.json
    "client": "", "object": "", "usage": "", "construction_year": None, "gross_floor_area_m2": None,
    "reporting_year": None, "boundary": "",
    "goals": [], "criteria": [], "constraints": [], "regulatory": [], "decisions_due": [],
    # kick-off additions
    "project": {"short": "", "address": "", "platform_url": "", "conditioned_area_m2": None,
                "zones": None, "storeys": None},
    "team": [],            # {name, role, org, source, status}
    "scope": {"included": [], "excluded": []},   # {title, text}; empty -> product defaults
    "understanding": [],   # {topic, value, source, status}
    "envelope": [],        # {element, u_value, note, source, status}
    "baseline": {"kpis": [], "enduse": {}, "carriers": [], "source": ""},
    "assumptions": {"energy": [], "general": []},   # {name, value, basis, source, status}
    "findings": [],        # {title, text, lever, source}
    "strategies": [],      # {id, name, measures, logic, source, status}
    "open_items": [],      # {what, who, due, status}
    "product_details": {"ve": [], "epa": []},       # {topic, value, status} / {point, id, area, resolution, status}
    "kickoff": {"date": "", "transcript": "", "attendees": [], "decisions": [], "changelog": []},
}

DEFAULT_ASSUMPTIONS = {
    "energy": [
        {"name": "Energiepreise", "value": "Arbeits- und Grundpreis je Energieträger", "basis": "", "status": "offen"},
        {"name": "Preissteigerung", "value": "2,5 % p.a.", "basis": "Standard", "status": "vorgeschlagen"},
        {"name": "CO2-Faktoren", "value": "je Energieträger, Netzmix-Pfad", "basis": "Standard", "status": "vorgeschlagen"},
        {"name": "CO2-Preis", "value": "", "basis": "", "status": "offen"},
        {"name": "Einspeisung PV", "value": "Vergütung je kWh", "basis": "", "status": "offen"},
        {"name": "Wirtschaftlichkeit", "value": "Zins 3 %, 30 Jahre", "basis": "Standard", "status": "vorgeschlagen"},
    ],
    "general": [
        {"name": "Nutzungsprofile", "value": "SIA 2024; Angaben aus Unterlagen ersetzen die Profile",
         "basis": "Standard", "status": "vorgeschlagen"},
        {"name": "Betriebszeit", "value": "", "basis": "Standard", "status": "offen"},
        {"name": "Wetterdaten", "value": "Normjahr + Zukunftsszenario 2050", "basis": "Standard", "status": "vorgeschlagen"},
        {"name": "Belegung / Leerstand", "value": "voll genutzt", "basis": "Annahme", "status": "offen"},
    ],
}

DEFAULT_TEAM = [{"name": "—", "role": "Entscheider / Ergebnisempfänger", "org": "—", "source": "", "status": "offen"}]


# ---------------------------------------------------------------- io
def load(prj: Project) -> dict:
    if not os.path.isfile(prj.brief_path):
        return copy.deepcopy(EMPTY)
    b = json.load(open(prj.brief_path, encoding="utf-8"))
    _fill_missing(b, EMPTY)
    return b


def save(prj: Project, b: dict) -> str:
    b["meta"]["updated"] = now_iso()
    if not b["meta"]["created"]:
        b["meta"]["created"] = b["meta"]["updated"]
    with open(prj.brief_path, "w", encoding="utf-8") as f:
        json.dump(b, f, ensure_ascii=False, indent=2)
    return prj.brief_path


def _fill_missing(d: dict, tmpl: dict) -> None:
    for k, v in tmpl.items():
        if k not in d:
            d[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(d[k], dict):
            _fill_missing(d[k], v)


def empty(v) -> bool:
    return v in (None, "", [], {})


def setdefault(d: dict, key: str, value) -> None:
    """Fill only if empty - never overwrite AI/user content."""
    if empty(d.get(key)) and not empty(value):
        d[key] = value


# ---------------------------------------------------------------- import project_brief.json
TAG = re.compile(r"\s*(\[(?:doc|assume|platform|kickoff|notes|user)[^\]]*\])")


def split_source(text: str) -> tuple[str, str]:
    tags = TAG.findall(text or "")
    return TAG.sub("", text or "").strip(), " ".join(tags)


def from_project_brief(b: dict, pb: dict, src: str) -> None:
    for k in ("client", "object", "usage", "construction_year", "gross_floor_area_m2",
              "reporting_year", "boundary"):
        setdefault(b, k, pb.get(k))
    if empty(b["goals"]):
        b["goals"] = [dict(g, priority=g.get("priority", ""), status=g.get("status", "vorgeschlagen"))
                      for g in pb.get("goals", [])]
    if empty(b["criteria"]):
        b["criteria"] = [dict(c, status=c.get("status", "vorgeschlagen")) for c in pb.get("criteria", [])]
    if empty(b["constraints"]):
        for c in pb.get("constraints", []):
            text, s = split_source(c) if isinstance(c, str) else (c.get("text", ""), c.get("source", ""))
            b["constraints"].append({"kind": "", "text": text, "source": s or src, "status": "vorgeschlagen"})
    if empty(b["regulatory"]):
        b["regulatory"] = [split_source(r)[0] if isinstance(r, str) else r for r in pb.get("regulatory", [])]
    if empty(b["decisions_due"]):
        b["decisions_due"] = pb.get("decisions_due", [])


def to_project_brief(b: dict) -> dict:
    """Subset in project_brief.json shape (runbook 01 §2.5) - used by the handover."""
    out = {k: b.get(k) for k in ("client", "object", "usage", "construction_year", "gross_floor_area_m2",
                                 "reporting_year", "boundary")}
    out["goals"] = [{k: g[k] for k in ("id", "text", "kind", "target", "source", "short") if k in g}
                    for g in b["goals"] if g.get("status") != "offen" or g.get("text")]
    out["criteria"] = [{k: c[k] for k in ("text", "kind", "target", "source", "short") if k in c}
                       for c in b["criteria"]]
    out["constraints"] = [f'{c["text"]} {c.get("source", "")}'.strip() for c in b["constraints"] if c.get("text")]
    out["regulatory"] = b["regulatory"]
    out["decisions_due"] = b["decisions_due"]
    return out


# ---------------------------------------------------------------- status helpers
def open_count(b: dict) -> dict:
    """How many entries per section are still open / only proposed (for `status`)."""
    sec = {"team": b["team"], "understanding": b["understanding"], "envelope": b["envelope"],
           "goals": b["goals"], "constraints": b["constraints"], "strategies": b["strategies"],
           "open_items": b["open_items"], "assumptions": b["assumptions"]["energy"] + b["assumptions"]["general"]}
    out = {}
    for k, rows in sec.items():
        st = [r.get("status", "offen") for r in rows]
        out[k] = {s: st.count(s) for s in STATUSES if st.count(s)} or {"leer": 1}
    return out


def log_change(b: dict, field: str, old, new, source: str) -> None:
    b["kickoff"]["changelog"].append({"when": now_iso(), "field": field, "old": old, "new": new, "source": source})
