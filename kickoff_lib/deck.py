"""Kick-off deck = approved layout (reference/2026-11-11_1518_Kick-off-Deck.pdf) rebuilt with deckkit
(skill optimuse-slides), so it looks like the final presentation (cover, contact, fonts, PDF/PPTX export).

One deck, customer version only. Every slide has a condition:
    needs=()            always
    needs=("model",)    from 3D model
    needs=("baseline",) from baseline
    product="..."       only for that product
Slides the project stage does not allow are left out.

Outputs (kickoff/out/, one timestamp per build):
    <stamp>_Kick-off-Deck.html   interactive (3D model + HVAC schematic), self-contained, works offline
    <stamp>_Kick-off-Deck.pdf    } with --export: static pictures instead of the interactive parts
    <stamp>_Kick-off-Deck.pptx   }
3D model and HVAC schematic come from the installed model viewer (optimuse-viewer) when available
(see viewer.py), otherwise from the tool's own IDF reader (HVAC then as a written list).
"""
from __future__ import annotations

import html as H
import json
import os
import re
import subprocess
import sys

from . import visuals as V, viewer as VW
from .brief import STAGES
from .idf import Model, load_register
from .collect import find_idf
from .project import Project, stamp

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHIP = {"vorgeschlagen": ("amber", "vorgeschlagen"), "bestaetigt": ("green", "bestätigt"),
        "geaendert": ("blue", "geändert"), "offen": ("red", "offen")}
HAVE = {"none": set(), "model": {"model"}, "baseline": {"model", "baseline"}}

EXTRA_CSS = """
.slide table.k.ko td,.slide table.k.ko th{text-align:left;font-variant-numeric:normal}
.slide table.k.ko{font-size:13px}.slide table.k.ko.sm{font-size:12px}
.slide table.k.ko td.b{font-weight:700}
.slide table.k.ko.sm td,.slide table.k.ko.sm th{padding:4px 8px}
.slide .box.ko-q{margin-top:auto;max-width:62%;background:#EEF0FE !important;border-left:3px solid var(--signal);border-radius:8px}
.ko-ql{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#495DCC;font-weight:700;margin-bottom:2px}
.ko-note{font-size:12.5px;color:var(--grey-60)}
.ko-items .it{margin:0 0 8px}.ko-items .it b{display:block;font-size:14px}.ko-items .it span{font-size:12.5px;color:var(--grey-60)}
.ko-g3{display:grid;gap:14px;min-height:0;flex:1}
.ko-ph{flex:1;min-height:120px;border:2px dashed #C2C2C2;border-radius:10px;display:flex;align-items:center;
 justify-content:center;color:var(--grey-60);text-align:center;padding:12px}
.ko-img{width:100%;height:100%;object-fit:contain;border-radius:8px;display:block}
.ko-frame{width:100%;flex:1;min-height:0;border:0;border-radius:10px}.ko-frame.sm{height:100%}
.ko-svg{flex:1;display:flex;align-items:center}
.ko-g3.hv .card{font-size:11.5px;line-height:1.3;overflow:hidden}.ko-g3.hv .cardhead{margin-top:8px}
.ko-g3.hv .cardhead:first-child{margin-top:0}.ko-g3.hv p.hv-it{margin:0 0 5px}.hv-l{font-weight:600}
.hv-s,.hv-f{color:var(--grey-60)}.hv-f b{color:#0F0F0F;font-weight:600}
.card.fill{flex:1;display:flex;flex-direction:column;min-height:0}.card.fill>img.ko-img{flex:1;min-height:0;height:auto}
"""


def _dk(prj: Project):
    sys.path.insert(0, prj.skill_dir())
    import deckkit  # noqa: E402
    return deckkit


def e(x) -> str:
    return H.escape(str(x if x is not None else ""))


def md(x) -> str:
    """Minimal inline markup: **bold**, <br>."""
    s = e(x).replace("&lt;br&gt;", "<br>")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def chip(st: str) -> str:
    c, lab = CHIP.get(st or "offen", CHIP["offen"])
    return f'<span class="tag {c}">{lab}</span>'


def table(head, rows, *, bold_first=False, small=False) -> str:
    th = "".join(f"<th>{e(h)}</th>" for h in head)
    tr = ""
    bold = ' class="b"'
    for r in rows:
        tr += "<tr>" + "".join(f"<td{bold if j == 0 and bold_first else ''}>{c}</td>"
                               for j, c in enumerate(r)) + "</tr>"
    return f'<table class="k ko{" sm" if small else ""}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


def question(text: str) -> str:
    return f'<div class="box ko-q"><span class="ko-ql">Frage an den Kunden</span>{md(text)}</div>'


def note(text: str) -> str:
    return f'<div class="box ko-note">{md(text)}</div>'


def placeholder(text: str) -> str:
    return f'<div class="ko-ph">{md(text)}</div>'


def target_text(g: dict) -> str:
    if g.get("target_text"):
        return g["target_text"]
    t = g.get("target") or {}
    if not t:
        return "qualitativ"
    unit = {"eui_kwh_m2a": "kWh/m²a", "payback_years": "Jahre", "co2_reduction_pct": "% CO2",
            "final_energy_reduction_pct": "% Endenergie", "hours_above_24C_occupied": "h > 24 °C",
            "npv_eur": "€ Kapitalwert", "stranding_year": "Stranding-Jahr"}.get(t.get("metric"), t.get("metric", ""))
    if t.get("metric") == "valeri_ok":
        return "Nachweis nach VALERI"
    v = t.get("value")
    v = "erfüllt" if v is True else str(v).replace(".", ",")
    return f"{v} {unit}" + (f" bis {t['by_year']}" if t.get("by_year") else "")


# ================================================================ slide definitions
def build_slides(dk, P, b: dict, stage: str, interactive: bool, prj: Project, art: dict):
    """Returns (agenda, [(slide_meta, Slide)], backup). interactive=False -> static pictures (PDF/PPTX)."""
    S = []
    have = HAVE[stage]
    prod = b["meta"]["product"]

    def add(title, body, *, needs=(), product=None, js="", kind="content", kicker=None):
        sl = dk.slide(title, body, project=P, js=js, kind=kind,
                      kicker=f"{P.name} · {kicker}" if kicker else None)
        S.append((dict(needs=tuple(needs), product=product, title=title), sl))

    def frame(page, cls="ko-frame"):
        return f'<iframe class="{cls}" srcdoc="{H.escape(page, quote=True)}"></iframe>'

    def pic(b64, cls="ko-img photo"):
        return f'<img class="{cls}" src="data:image/png;base64,{b64}" alt="">'

    # -- agenda (dynamic) -------------------------------------------------
    ag = ["Begrüßung, Team & Ablauf", "Leistungsumfang", "Projekt & Gebäude"]
    ag += (["Raummodell, Anlagen & Baseline", "Unsere Annahmen"] if "baseline" in have
           else ["Raummodell"] if "model" in have else [])
    ag += ["Ziele & Randbedingungen", "Strategievorschlag", "Offene Punkte & nächste Schritte"]
    agenda = dk.agenda(P, [(t, "") for t in ag])
    agenda.html = agenda.html.replace(
        "</ul></div>", "</ul></div>" + note("**Hinweis:** Dieses Gespräch wird gegebenenfalls aufgezeichnet, "
                                             "außerdem machen wir Notizen."), 1)

    # -- team ---------------------------------------------------------------
    add("Projektteam & Rollen", dk.card(table(["Name", "Rolle", "Organisation", "Status"],
        [[e(t["name"]), e(t["role"]), e(t.get("org", "")), chip(t.get("status"))] for t in b["team"]])) +
        question("Wer entscheidet über die Strategien? Wer bekommt die Ergebnisse?"), kicker="Kick-off · Team")

    # -- timeline -------------------------------------------------------------
    add("Ablauf & Zeitplan", dk.card(f'<div class="ko-svg">{V.timeline_svg(stage)}</div>', cls="fill"),
        kicker="Kick-off · Ablauf")

    # -- scope ----------------------------------------------------------------
    def items(lst):
        return '<div class="ko-items">' + "".join(
            f'<div class="it"><b>{md(i["title"])}</b><span>{md(i["text"])}</span></div>' for i in lst) + "</div>"
    add("Leistungsumfang", dk.grid(dk.card(items(b["scope"]["included"]), head=f"Enthalten · {e(prod)}"),
                                   dk.card(items(b["scope"]["excluded"]), head="Nicht enthalten"), ratio="2") +
        question("Entspricht dieser Leistungsumfang Ihren Erwartungen, oder gibt es Punkte, "
                 "die Sie zusätzlich erwartet haben?"), kicker="Kick-off · Umfang")

    # -- project & building -----------------------------------------------------
    kp = []
    if b.get("construction_year"):
        kp.append((e(b["construction_year"]), "Baujahr"))
    if b.get("gross_floor_area_m2"):
        kp.append((f'{dk.num(b["gross_floor_area_m2"])} m²', "Bruttogrundfläche"))
    if b["project"].get("conditioned_area_m2"):
        kp.append((f'{dk.num(b["project"]["conditioned_area_m2"])} m²', "konditioniert"))
    if b["project"].get("zones"):
        kp.append((e(b["project"]["zones"]), "Zonen im Modell"))
    if "baseline" in have:
        kp += [(e(k["value"]), e(k["label"])) for k in b["baseline"]["kpis"][:2]]
    elif b["project"].get("storeys"):
        kp.append((e(b["project"]["storeys"]), "Geschosse"))
    if "model" in have and interactive and art.get("viewer_html") and not prj.asset("model3d.png"):
        img = frame(art["viewer_html"].replace("const DATA =", "window.__MODE='bare';const DATA =", 1),
                    "ko-frame sm")
    elif "model" in have and art.get("model_b64"):
        img = pic(art.get("model_card_b64") or art["model_b64"])
    else:
        img = placeholder("3D-Modell folgt, sobald die Pläne vorliegen")
    und = [[e(u["topic"]), md(u["value"] or "offen")] for u in b["understanding"]]
    env = [[e(x["element"]), e(x["u_value"] or "offen")] for x in b["envelope"]] or [["—", "offen"]]
    body = (dk.kpibar(kp[:5]) +
            '<div class="ko-g3" style="grid-template-columns:.95fr 1.3fr .85fr">' +
            dk.card(img, cls="fill") + dk.card(table(["Thema", "Stand"], und, bold_first=True, small=True)) +
            dk.card(table(["Bauteil", "U-Wert [W/(m²K)]"], env, bold_first=True, small=True)) + "</div>" +
            question("Gehören weitere Gebäude, Bauteile oder Flächen zum Umfang?"))
    add("Projekt & Gebäude", body, kicker="Kick-off · Projekt")

    # -- 3D model (HTML) / floor plans (PDF, PPTX) ----------------------------------
    if interactive and art.get("viewer_html"):
        view = frame(art["viewer_html"])
        foot = ""
    elif art.get("plans_svg"):
        view = (f'<img class="ko-img photo" src="data:image/svg+xml;base64,{V.svg_b64(art["plans_svg"])}" alt="">')
        foot = ""
    elif art.get("model_b64"):
        view, foot = pic(art["model_b64"]), "Raummodell des digitalen Zwillings, eingefärbt nach Nutzung."
    else:
        view, foot = placeholder("Raummodell nicht verfügbar"), ""
    add("Raummodell", dk.card(view + (f'<div class="meta" style="margin-top:6px">{foot}</div>' if foot else ""),
                              cls="fill") +
        ("" if not interactive and art.get("plans_svg") else      # PDF/PPTX: no question -> room for plans
         question("Erkennen Sie Ihr Gebäude wieder? Stimmen Nutzungen, Geschosse und Sollwerte?")),
        needs=("model",), kicker="Baseline · das Gebäude heute")

    # -- HVAC ("Anlagen"): schematic in the HTML, always the written list in PDF/PPTX ----
    if interactive and art.get("hvac_html"):
        body = dk.card(frame(art["hvac_html"]), cls="fill")
    elif art.get("hvac_cols"):
        body = ('<div class="ko-g3 hv" style="grid-template-columns:repeat(%d,1fr)">' % len(art["hvac_cols"]) +
                "".join(dk.card(c) for c in art["hvac_cols"]) + "</div>")
    else:
        body = dk.card(placeholder("Anlagen folgen mit der Baseline"), cls="fill")
    add("Anlagen", body + question("Fehlt eine Anlage? Stimmen die Leistungen?"), needs=("baseline",),
        kicker="Baseline · das Gebäude heute")

    # -- assumptions -------------------------------------------------------------------
    def atab(rows):
        return table(["Annahme", "Wert im Modell", "Basis", "Status"],
                     [[e(a["name"]), md(a.get("value") or "—"), e(a.get("basis") or "—"), chip(a.get("status"))]
                      for a in rows], small=True)
    add("Unsere Annahmen", dk.grid(dk.card(atab(b["assumptions"]["energy"]), head="Energie"),
                                   dk.card(atab(b["assumptions"]["general"]), head="Allgemein"), ratio="2") +
        note("Basis: **Bestand** = aus Ihren Unterlagen · **Standard** = Norm- oder Erfahrungswert · "
             "**Ziel** = Ihre Vorgabe. Typische Lücken: Leerstand und Sonderzonen, Contracting / BHKW, "
             "vorhandene PV-Studien, Mieterbereiche außerhalb des Umfangs."),
        needs=("baseline",), kicker="Baseline · Annahmen")

    # -- baseline KPIs --------------------------------------------------------------------
    bl = b["baseline"]
    js = ""
    if bl.get("enduse", {}).get("uses"):
        cols = {"Heizung": V.ALERT, "Kühlung": V.SB, "Warmwasser": V.AMBER, "Beleuchtung": V.SB60,
                "Geräte / Nutzer": V.GREY, "Ventilatoren": V.OK, "Pumpen": V.MUTED, "Prozessenergie": V.SB140}
        d = {"title": "Endenergie nach Anwendung [MWh/a]", "unit": "MWh/a", "short": bl["enduse"]["carriers"],
             "series": [{"name": k, "y": v, "color": cols.get(k)} for k, v in bl["enduse"]["uses"].items() if any(v)]}
        js = f"energyStack('ko_enduse', {json.dumps(d, ensure_ascii=False)});"
        chart = dk.plotcard("ko_enduse", cls="fill")
    else:
        chart = dk.card(placeholder("Endenergie nach Anwendung folgt mit der Baseline"), cls="fill")
    car = [[e(c["carrier"]), e(str(c.get("mwh", "")).replace(".", ",")), e(c.get("kwh_m2") or "—")]
           for c in bl.get("carriers", [])]
    if len(car) > 1:
        car.append(["<b>Gesamt</b>", f'<b>{str(round(sum(c.get("mwh") or 0 for c in bl["carriers"]), 1)).replace(".", ",")}</b>', ""])
    right = (dk.card(table(["Energieträger", "MWh/a", "kWh/m²a"], car or [["—", "offen", ""]]),
                     head="Endenergie nach Energieträger") +
             dk.card(placeholder("Platzhalter – Inhalt folgt"), head="Vergleich mit BBSR-Verbrauchskennwerten"))
    add("Baseline: Kennwerte", (dk.kpibar([(e(k["value"]), e(k["label"])) for k in bl.get("kpis", [])][:5])
                                if bl.get("kpis") else "") +
        f'<div class="body grid2">{chart}<div style="display:flex;flex-direction:column;gap:12px">{right}</div></div>',
        needs=("baseline",), js=js, kicker="Baseline · das Gebäude heute")

    # -- findings ----------------------------------------------------------------------------
    fr = [[f'<b>{md(f["title"])}</b><br>{md(f.get("text", ""))}', md(f.get("lever", ""))] for f in b["findings"]]
    add("Erste Befunde & Hebel", dk.card(table(["Befund", "Hebel"], fr or [["Befunde folgen nach Auswertung der Baseline", ""]])) +
        question("Deckt sich das mit Ihrer Erfahrung im Betrieb? Gibt es Beschwerden über zu warme oder zu kalte Räume?"),
        needs=("baseline",), kicker="Baseline · Befunde")

    # -- goals / constraints / strategies / open items ---------------------------------------
    gr = [[e(g.get("id", "")), md(g.get("short") or g.get("text", "")), e(target_text(g)), e(g.get("priority", "")),
           e(_src(g.get("source", "")))] for g in b["goals"]]
    add("Ziele & Bewertungskriterien", dk.card(table(["ID", "Ziel", "Zielwert", "Priorität", "Quelle"],
        gr or [["—", "Ziele im Termin festlegen", "", "", ""]])) +
        question("Gelten diese Ziele? Gibt es eine Zielpriorisierung?"), kicker="Ziele")
    cr = [[e(c.get("kind") or "—"), md(c["text"]), e(_src(c.get("source", ""))), chip(c.get("status"))]
          for c in b["constraints"]]
    add("Randbedingungen & Ausschlüsse", dk.card(table(["Art", "Beschreibung", "Quelle", "Status"],
        cr or [["—", "Randbedingungen im Termin klären", "", chip("offen")]])) +
        question("Gibt es weitere Randbedingungen?"), kicker="Ziele")
    sr = [[e(s.get("id", "")), e(s.get("name", "")), md(s.get("measures", "")), md(s.get("logic", "")),
           chip(s.get("status"))] for s in b["strategies"]]
    add("Strategievorschlag", dk.card(table(["", "Strategie", "Maßnahmen", "Logik", "Status"],
        sr or [["", "Strategien folgen", "", "", chip("offen")]])) +
        question("Welche Strategien rechnen wir? Was fehlt, was fällt raus? Decken die Strategien die Ziele der Studie ab?"),
        kicker="Strategien")
    orows = [[md(o["what"]), e(o.get("who", "")), e(o.get("due", "") or "—"), chip(o.get("status"))]
             for o in b["open_items"]]
    add("Offene Punkte", dk.card(table(["Was", "Wer", "bis", "Status"], orows or [["—", "", "", ""]])) +
        note("**Nächste Schritte:** Protokoll innerhalb von zwei Werktagen · Unterlagen bis zur vereinbarten Frist · "
             "Ergebnisunterlagen ca. zwei Wochen nach Erhalt aller Unterlagen."), kicker="Nächste Schritte")

    # -- product slides ----------------------------------------------------------------------
    ve = b["product_details"].get("ve") or [{"topic": t, "value": "", "status": "offen"} for t in
                                            ("Leistungsphase / LOD", "Vergleichsmaßstab", "Ausgeklammerte Bereiche",
                                             "Kunden-Fristen", "Kostenbasis")]
    add("Planungsstand & Vergleichsmaßstab", dk.card(table(["Thema", "Stand", "Status"],
        [[e(x["topic"]), md(x.get("value") or "offen"), chip(x.get("status"))] for x in ve])) +
        question("Wo sehen Sie selbst noch Spielraum in der Planung?"), product="Value Engineering",
        kicker="Value Engineering")
    epa = b["product_details"].get("epa") or []
    add("Datenpunkte & Zählerzuordnung", dk.card(table(["Datenpunkt", "ID im System", "Anlage / Bereich", "Auflösung", "Status"],
        [[e(x.get("point")), e(x.get("id")), e(x.get("area")), e(x.get("resolution")), chip(x.get("status"))] for x in epa]
        or [["—", "", "", "", chip("offen")]])) +
        note("Bis zu 30 Datenpunkte inklusive · mindestens ein Quartal Daten · Naming-Guideline und Zeitzone klären."),
        product="Energy Performance Analytics", kicker="Energy Performance Analytics")

    backup = [dk.appendix(P, "Methodik & Normen", dk.bullets([
        "Simulation: EnergyPlus, Stundenwerte, Normjahr", "Nutzungsprofile: SIA 2024",
        "Wirtschaftlichkeit: EN 15459 (VDI 2067), EN 17463", "Carbon Risk: CRREM Global Pathways, 1,5 °C-Pfad"])),
        dk.appendix(P, "Glossar", dk.card(table(["Begriff", "Bedeutung"], [
            ["Baseline", "Das Gebäude im heutigen bzw. geplanten Zustand – Referenz für alle Strategien"],
            ["Strategie", "Paket aus Maßnahmen, das gemeinsam gerechnet wird"],
            ["Kapitalwert", "Summe aller abgezinsten Zahlungen einer Strategie gegenüber der Baseline"],
            ["Stranding-Jahr", "Jahr, ab dem das Gebäude den CRREM-Pfad überschreitet"],
            ["Kalibrierung", "Abgleich des Modells mit gemessenen Verbräuchen"]], bold_first=True)))]
    return agenda, S, backup


def _src(s: str) -> str:
    """'[doc:PN kickoff 01.09. @06:10] [assume:…]' -> 'PN kickoff 01.09.' (short label for the table)."""
    m = re.findall(r"\[(?:doc|platform|assume|kickoff|idf|notes|user):([^\]@]*)", s or "")
    return (m[0].strip() if m else "") or (s or "—")


# ================================================================ assembly
def build(prj: Project, b: dict, *, stage: str | None = None, export: bool = False) -> list[str]:
    dk = _dk(prj)
    stage = stage or b["meta"]["stage"] or "none"
    assert stage in STAGES, stage
    art = artefacts(prj, b)
    for n in art.get("notes", []):
        print("  ·", n)
    short = b["project"].get("short") or b.get("object") or "Projekt"
    P = dk.Project(name=short, short=short,
                   date=_date(b), eyebrow=f"OPTIMUSE | {b['meta']['product']}",
                   platform_url=b["project"].get("platform_url", ""))
    for kv in (os.path.join(prj.root, "07_presentation", "assets", "keyvisual.svg"),
               os.path.join(prj.skill_dir(), "templates", "keyvisual.svg")):
        if os.path.isfile(kv):
            P.keyvisual = kv
            break
    st = stamp()
    base = os.path.join(prj.out_dir, f"{st}_Kick-off-Deck")

    def doc(interactive: bool) -> str:
        agenda, S, backup = build_slides(dk, P, b, stage, interactive, prj, art)
        keep = [sl for m, sl in S
                if set(m["needs"]) <= HAVE[stage] and (not m["product"] or m["product"] == b["meta"]["product"])]
        return _offline(dk.assemble(P, keep, backup=backup, agenda_slide=agenda,
                                    disclaimer_slide=False, extra_css=EXTRA_CSS))

    outs = [base + ".html"]
    open(outs[0], "w", encoding="utf-8").write(doc(True))
    if export:
        if not art.get("pictures"):
            _pictures(prj, art)
        pr = os.path.join(prj.out_dir, f".{st}_print.html")
        open(pr, "w", encoding="utf-8").write(doc(False))
        outs += _export(prj, pr, base, pptx=True)
        os.remove(pr)
    return outs


def _date(b) -> str:
    d = b["meta"].get("kickoff_date") or b["kickoff"].get("date")
    if d and re.match(r"\d{4}-\d\d-\d\d", d):
        y, m_, dd = d[:10].split("-")
        return f"Kick-off · {dd}.{m_}.{y}"
    return "Kick-off"


def _b64(path: str) -> str:
    import base64
    return base64.b64encode(open(path, "rb").read()).decode()


def artefacts(prj: Project, b: dict) -> dict:
    """3D model + HVAC. Order of sources: kickoff/assets overrides > model viewer > own IDF reader."""
    art = {"notes": []}
    idf_path = find_idf(prj)
    mdl = Model(idf_path) if idf_path else None
    vw = VW.export(prj, idf_path) if idf_path else {}
    art["notes"] += (vw.get("info") or {}).get("notes", [])[:1] if not vw.get("hvac_html") else []
    if mdl:
        zones = mdl.zones(load_register(prj.p("zone_register")))
        art["viewer_html"] = V.viewer_html(V.model_data(mdl, zones, vw.get("zone_attrs")))
        art["zones"] = zones
        art["hvac_cols"] = V.hvac_list_cards(mdl.hvac_inventory())
        art["plans_svg"] = V.floorplans_svg(mdl, zones)
    if vw.get("hvac_html"):
        art["hvac_html"] = vw["hvac_html"]
    if prj.asset("model3d.html"):
        art["viewer_html"] = open(prj.asset("model3d.html"), encoding="utf-8").read()
    if prj.asset("hvac.html"):
        art["hvac_html"] = open(prj.asset("hvac.html"), encoding="utf-8").read()
    _pictures(prj, art)
    return art


def _pictures(prj: Project, art: dict) -> None:
    """Static 3D picture for the project card in PDF/PPTX (screenshot of the viewer, cached by content).
    Fallback without playwright: matplotlib picture of the zones. Raummodell/Anlagen in PDF/PPTX use
    floor plans + the written list instead (no screenshots)."""
    import hashlib
    cache = os.path.join(prj.kdir, ".viewer")
    os.makedirs(cache, exist_ok=True)

    def shot(page, name, **kw):
        h = hashlib.sha1((page + repr(sorted(kw.items()))).encode("utf-8")).hexdigest()[:12]
        png = os.path.join(cache, f"{name}_{h}.png")
        if os.path.isfile(png):
            return png
        if os.path.isfile(png + ".failed"):      # tried before with the same content: do not wait again
            return None
        got = V.snapshot(page, png, **kw)
        import importlib.util
        if not got and importlib.util.find_spec("playwright"):   # real failure, not "playwright missing"
            open(png + ".failed", "w").close()
        return got

    own = prj.asset("model3d.png")
    if own:
        art["model_b64"] = art["model_card_b64"] = _b64(own)
    elif art.get("viewer_html"):     # small 3D picture for the "Projekt & Gebäude" card in PDF/PPTX
        card = shot(art["viewer_html"], "model_card", width=560, height=520, hash_="snap-bare")
        if not card and art.get("zones"):
            card = V.model_png(art["zones"], os.path.join(cache, "model_mpl_card.png"), legend=False)
        if card:
            art["model_b64"] = art["model_card_b64"] = _b64(card)
    art["pictures"] = True


def _offline(doc: str) -> str:
    plotly = open(os.path.join(TOOL, "vendor", "plotly-cartesian-2.35.2.min.js"), encoding="utf-8").read()
    plotly = plotly.replace("</script", "<\\/script")
    fonts = open(os.path.join(TOOL, "vendor", "inter_fonts.css"), encoding="utf-8").read()
    doc = re.sub(r'<script src="https://cdn\.plot\.ly/[^"]+"[^>]*></script>',
                 lambda _: f"<script>{plotly}</script>", doc, count=1)
    doc = re.sub(r"@import url\('https://fonts\.googleapis\.com[^']*'\);", lambda _: fonts, doc, count=1)
    return doc


def _export(prj: Project, html_path: str, base: str, pptx: bool) -> list[str]:
    """PDF (+PPTX) with the deckkit renderer. Needs playwright + chromium in the running Python."""
    r = os.path.join(prj.skill_dir(), "renderer")
    out = []
    jobs = [("export_pdf.py", base + ".pdf")] + ([("export_pptx_native.py", base + ".pptx")] if pptx else [])
    for script, target in jobs:
        cmd = [sys.executable, os.path.join(r, script), html_path, "-o", target]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
        if p.returncode == 0 and os.path.isfile(target):
            out.append(target)
        else:
            print(f"! Export fehlgeschlagen ({script}): {(p.stderr or p.stdout).strip()[-400:]}")
            print("  Einmalig nötig: python -m playwright install chromium")
    return out
