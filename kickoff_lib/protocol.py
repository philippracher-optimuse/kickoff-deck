"""Kick-off protocol (sent within two working days) + handover to the project process."""
from __future__ import annotations

import json
import os
import shutil

from . import brief as B
from .deck import _dk, e, md, target_text
from .project import Project, stamp

LAB = {"vorgeschlagen": "vorgeschlagen", "bestaetigt": "bestätigt", "geaendert": "geändert", "offen": "offen"}


def _rows(b: dict) -> dict:
    return {
        "Ziele": [(g.get("id", ""), g.get("short") or g.get("text", ""), target_text(g), g.get("priority", ""),
                   LAB.get(g.get("status"), "")) for g in b["goals"]],
        "Randbedingungen": [(c.get("kind") or "—", c["text"], LAB.get(c.get("status"), "")) for c in b["constraints"]],
        "Strategien": [(s.get("id", ""), s.get("name", ""), s.get("measures", ""), LAB.get(s.get("status"), ""))
                       for s in b["strategies"]],
        "Offene Punkte": [(o["what"], o.get("who", ""), o.get("due", "") or "—", LAB.get(o.get("status"), ""))
                          for o in b["open_items"]],
    }


def markdown(b: dict) -> str:
    k = b["kickoff"]
    L = [f"# Protokoll Kick-off · {b.get('object', '')}", "",
         f"**Datum:** {k.get('date') or b['meta'].get('kickoff_date') or '—'}  ",
         f"**Leistung:** {b['meta']['product']}  ",
         f"**Teilnehmende:** {', '.join(k.get('attendees') or [t['name'] for t in b['team'] if t.get('name') not in ('—', '')])}",
         ""]
    if k.get("decisions"):
        L += ["## Beschlüsse", ""] + [f"- {d}" for d in k["decisions"]] + [""]
    heads = {"Ziele": "| ID | Ziel | Zielwert | Priorität | Status |", "Randbedingungen": "| Art | Beschreibung | Status |",
             "Strategien": "| | Strategie | Maßnahmen | Status |", "Offene Punkte": "| Was | Wer | bis | Status |"}
    for sec, rows in _rows(b).items():
        if not rows:
            continue
        h = heads[sec]
        L += [f"## {sec}", "", h, "|" + "|".join("---" for _ in h.split("|")[1:-1]) + "|"]
        L += ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows] + [""]
    ch = k.get("changelog", [])
    if ch:
        L += ["## Änderungen gegenüber den Unterlagen", ""] + [
            f"- {c['field']}: {c.get('old') or '—'} → {c.get('new')}" for c in ch] + [""]
    L += ["## Nächste Schritte", "",
          "- Unterlagen bis zur vereinbarten Frist hochladen.",
          "- Bearbeitung startet nach Erhalt aller Unterlagen; Ergebnisunterlagen ca. zwei Wochen später.",
          "- Bitte prüfen Sie dieses Protokoll. Rückmeldungen nehmen wir in die Bearbeitung auf.", ""]
    return "\n".join(L)


def build(prj: Project, b: dict, export: bool = False) -> list[str]:
    st = stamp()
    md_path = os.path.join(prj.out_dir, f"{st}_Kick-off-Protokoll.md")
    open(md_path, "w", encoding="utf-8").write(markdown(b))
    dk = _dk(prj)
    from deckkit import report as R
    P = dk.Project(name=b.get("object") or "Projekt", short=b["project"].get("short") or "Projekt", date="")
    sec = []
    for i, (title, rows) in enumerate(_rows(b).items(), 1):
        if not rows:
            continue
        heads = {"Ziele": ("ID", "Ziel", "Zielwert", "Priorität", "Status"), "Randbedingungen": ("Art", "Beschreibung", "Status"),
                 "Strategien": ("", "Strategie", "Maßnahmen", "Status"), "Offene Punkte": ("Was", "Wer", "bis", "Status")}[title]
        sec.append(R.sectionbar(i, title) + R.kvtable([[e(c) for c in r] for r in rows], head_labels=heads))
    dec = b["kickoff"].get("decisions") or []
    ch = b["kickoff"].get("changelog") or []
    body = ((R.sectionbar("", "Beschlüsse") + "".join(f"<p>• {md(d)}</p>" for d in dec)) if dec else "") + "".join(sec)
    if ch:
        body += R.sectionbar("", "Änderungen gegenüber den Unterlagen") + R.kvtable(
            [[e(c["field"]), e(c.get("old") or "—"), e(c.get("new"))] for c in ch], head_labels=("Thema", "bisher", "neu"))
    k = b["kickoff"]
    page = R.page("Protokoll Kick-off", body, project=P, subtitle=b["meta"]["product"],
                  meta=[("Datum", e(k.get("date") or b["meta"].get("kickoff_date") or "—")),
                        ("Teilnehmende", e(", ".join(k.get("attendees") or [])) or "—")],
                  footer=R.PFOOT, page_no=R.PNUM)
    html_path = os.path.join(prj.out_dir, f"{st}_Kick-off-Protokoll.html")
    css = "table.k td,table.k th{text-align:left !important} .page p{margin:3px 0}"
    open(html_path, "w", encoding="utf-8").write(R.document(P, "Protokoll Kick-off", [page], extra_css=css))
    out = [md_path, html_path]
    if export:
        r = os.path.join(prj.skill_dir(), "renderer")
        import subprocess, sys
        pdf = html_path[:-5] + ".pdf"
        p = subprocess.run([sys.executable, os.path.join(r, "export_pdf.py"), html_path, "-o", pdf],
                           capture_output=True, text=True)
        if p.returncode == 0:
            out.append(pdf)
        else:
            print("! PDF-Export fehlgeschlagen:", (p.stderr or p.stdout)[-300:])
    return out


def handover(prj: Project, b: dict) -> list[str]:
    """No project_brief.json yet -> hand kickoff_brief to the process as an input document
    (runbook 01 reads the transcripts folder). Otherwise only list the differences."""
    out = []
    if not prj.exists("project_brief"):
        dst = prj.p("transcripts")
        os.makedirs(dst, exist_ok=True)
        j = os.path.join(dst, "kickoff_brief.json")
        shutil.copyfile(prj.brief_path, j)
        mdp = os.path.join(dst, "kickoff_brief.md")
        pb = B.to_project_brief(b)
        txt = (markdown(b) + "\n\n## Für Phase 01: Vorschlag project_brief.json\n\n"
               "Abgeleitet aus dem Kick-off (Status bestätigt/geändert = Kundenaussage). "
               "Quellen-Tags übernehmen.\n\n```json\n" + json.dumps(pb, ensure_ascii=False, indent=2) + "\n```\n")
        open(mdp, "w", encoding="utf-8").write(txt)
        out += [j, mdp]
    else:
        pb = json.load(open(prj.p("project_brief"), encoding="utf-8"))
        have = {(g.get("short") or g.get("text", "")).strip() for g in pb.get("goals", [])}
        L = ["# Kick-off vs. project_brief.json", "",
             "project_brief.json existiert bereits. Unterschiede zur Prüfung (nichts wurde überschrieben):", ""]
        for g in b["goals"]:
            t = (g.get("short") or g.get("text", "")).strip()
            if t not in have or g.get("status") == "geaendert":
                L.append(f"- Ziel {g.get('id', '')}: {t} ({LAB.get(g.get('status'), '')})")
        cons = " ".join(pb.get("constraints", []))
        for c in b["constraints"]:
            if c["text"][:30] not in cons:
                L.append(f"- Randbedingung: {c['text']} ({LAB.get(c.get('status'), '')})")
        if len(L) == 4:
            L.append("- keine Unterschiede bei Zielen und Randbedingungen")
        p = os.path.join(prj.kdir, "handover_diff.md")
        open(p, "w", encoding="utf-8").write("\n".join(L) + "\n")
        out.append(p)
    return out
