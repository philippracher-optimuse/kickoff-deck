"""Pictures for the deck: 3D room model (interactive HTML + static PNG), HVAC schema (SVG),
project timeline (SVG). Colours = OPTIMUSE brand palette (optimuse-slides/assets/brand.css)."""
from __future__ import annotations

import html
import json
import math
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INK, MUTED, LINE, SB, SB60, SB140, ALERT, AMBER, OK, GREY = (
    "#0F0F0F", "#5A5A5A", "#E6E6E8", "#5D55EA", "#A9B4F9", "#495DCC", "#D7642D", "#EFB347", "#29A883", "#999999")


def _vendor(name: str) -> str:
    return open(os.path.join(HERE, "vendor", name), encoding="utf-8").read()


# ---------------------------------------------------------------- 3D model
def _flat(v):
    return [round(c, 2) for p in v for c in p]


def _az(pts):
    from .idf import newell
    nx, ny, nz = newell(pts)
    if abs(nx) + abs(ny) < 1e-9:
        return None
    return round(math.degrees(math.atan2(nx, ny)) % 360)


def model_data(mdl, zones: list[dict], attrs: dict | None = None) -> dict:
    """Data for templates/viewer.html: zones (+ viewer attributes), every surface with construction
    and U-value, windows, shading (Laubengang, fins: 'a' = attached, 'c' = surroundings)."""
    from .idf import area, triangulate
    attrs = attrs or {}
    floors, fz = [], {}
    for z in sorted(zones, key=lambda z: z["zmin"]):
        if z["floor"] not in floors:
            floors.append(z["floor"])
            fz[z["floor"]] = z["zmin"]
    zi = {z["zone"]: i for i, z in enumerate(zones)}
    cons = mdl.constructions()
    rs = {"wall": 0.17, "roof": 0.14, "ceiling": 0.14, "floor": 0.17}

    def u_of(name, typ):
        c = cons.get((name or "").lower())
        if not c:
            return None, None
        if c["kind"] == "window":
            return c["u"], c["g"]
        return round(1 / (c["r"] + rs.get(typ, 0.17)), 3), None

    zl = []
    for z in zones:
        a = attrs.get(z["zone"])
        zl.append(dict(n=(a or {}).get("name") or z["name"], u=z["use"], fl=z["floor"], c=bool(z["cond"]),
                       a=z["area"], vol=round((a or {}).get("volume_m3") or z["vol"]), at=a))
    surf = []
    for s in mdl.surfaces:
        if len(s["pts"]) < 3:
            continue
        u, _ = u_of(s["cons"], s["type"])
        surf.append(dict(z=zi.get(s["zone"], -1), t=s["type"], bc=s["bc"], cn=s["cons"], U=u,
                         A=round(area(s["pts"]), 1), az=_az(s["pts"]),
                         v=_flat(s["pts"]), f=[i for t in triangulate(s["pts"]) for i in t]))
    win = []
    for w in mdl.windows:
        if len(w["pts"]) < 3:
            continue
        u, g = u_of(w["cons"], "window")
        win.append(dict(z=zi.get(w["host"]["zone"], -1) if w["host"] else -1, cn=w["cons"], U=u, g=g,
                        A=round(area(w["pts"]) * w["mult"], 1), az=_az(w["pts"]),
                        v=_flat(w["pts"]), f=[i for t in triangulate(w["pts"]) for i in t]))
    shade = [dict(k=s["kind"][0], zmin=round(min(p[2] for p in s["v"]), 2), v=_flat(s["v"]),
                  f=[i for t in s["f"] for i in t]) for s in mdl.shading()]
    return dict(floors=floors, floor_z=[fz[f] for f in floors], zones=zl, surf=surf, win=win, shade=shade)


def viewer_html(data: dict) -> str:
    t = open(os.path.join(HERE, "templates", "viewer.html"), encoding="utf-8").read()
    return (t.replace("/*THREE*/", _vendor("three-r147.min.js"))
             .replace("/*ORBIT*/", _vendor("OrbitControls.js"))
             .replace("/*DATA*/", json.dumps(data, separators=(",", ":"), ensure_ascii=False)))


# ---------------------------------------------------------------- static pictures (PDF / PPTX)
def snapshot(page_html: str, png: str, *, width: int, height: int, hash_: str = "",
             ready_js: str = "window.__snapReady===true", css: str = "", before_js: str = "") -> str | None:
    """Render a self-contained HTML page in headless Chromium and save a PNG. Needs playwright
    (same requirement as the PDF export). Returns the path or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    tmp = png + ".src.html"
    open(tmp, "w", encoding="utf-8").write(page_html)
    try:
        import pathlib
        with sync_playwright() as p:
            br = p.chromium.launch(args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader",
                                         "--ignore-gpu-blocklist", "--enable-webgl"])
            pg = br.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
            pg.goto(pathlib.Path(tmp).resolve().as_uri() + (f"#{hash_}" if hash_ else ""))
            pg.wait_for_function(ready_js, timeout=30000)
            if css:
                pg.add_style_tag(content=css)
            if before_js:
                pg.evaluate(before_js)
            pg.wait_for_timeout(700)
            pg.screenshot(path=png)
            br.close()
        return png
    except Exception as e:  # noqa: BLE001
        print(f"! Bild konnte nicht erzeugt werden ({os.path.basename(png)}): {str(e)[:200]}")
        return None
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)


HVAC_SNAP_CSS = "#bar,#side,#notes,#banner,#ctlbar{display:none!important}"
HVAC_READY = "document.querySelectorAll('#sheet g').length>5"


def model_png(zones: list[dict], path: str, legend: bool = True) -> str | None:
    """Static axonometric view coloured by use (for the online HTML, PDF and PPTX)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except ImportError:
        return None
    pal = [ALERT, "#7488F6", AMBER, OK, SB60, GREY, SB140, "#C98FA8", "#B7B08C", "#7FB3D9", MUTED, "#86C0B0"]
    uses = list(dict.fromkeys(z["use"] or "ohne Zuordnung" for z in zones))
    col = {u: pal[i % len(pal)] for i, u in enumerate(uses)}
    fig = plt.figure(figsize=(8.5, 6.2) if legend else (6, 6))
    ax = fig.add_subplot(projection="3d")
    xs, ys, zs = [], [], []
    for z in zones:
        tris = [[z["v"][a], z["v"][b], z["v"][c]] for a, b, c in z["f"]]
        ax.add_collection3d(Poly3DCollection(tris, facecolor=col[z["use"] or "ohne Zuordnung"],
                                             edgecolor=(0, 0, 0, 0.08), linewidth=0.15))
        for p in z["v"]:
            xs.append(p[0]); ys.append(p[1]); zs.append(p[2])
    if not xs:
        plt.close(fig)
        return None
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    r = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
    ax.set_xlim(cx - r, cx + r); ax.set_ylim(cy - r, cy + r); ax.set_zlim(min(zs), min(zs) + 2 * r)
    ax.set_box_aspect((1, 1, 1)); ax.view_init(elev=26, azim=-58); ax.set_axis_off()
    area = {}
    for z in zones:
        area[z["use"] or "ohne Zuordnung"] = area.get(z["use"] or "ohne Zuordnung", 0) + z["area"]
    top = sorted(area, key=area.get, reverse=True)[:10]
    if legend:
        ax.legend(handles=[plt.Line2D([], [], marker="s", ls="", color=col[u], markersize=9, label=u) for u in top],
                  loc="center left", bbox_to_anchor=(0.95, 0.5), frameon=False, fontsize=9)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- floor plans (PDF / PPTX)
LAYOUTS = {  # number of plans -> candidate arrangements (plans per row)
    1: [[1]],
    2: [[2], [1, 1]],
    3: [[3], [2, 1], [1, 1, 1]],
    4: [[4], [2, 2]],
    5: [[5], [3, 2], [2, 2, 1]],
    6: [[3, 3], [6], [2, 2, 2]],
    7: [[4, 3], [3, 2, 2], [7]],
    8: [[4, 4], [3, 3, 2], [8]],
}
PLAN_PAL = ["#D7642D", "#7488F6", "#EFB347", "#29A883", "#A9B4F9", "#999999", "#495DCC", "#C98FA8", "#B7B08C",
            "#7FB3D9", "#5A5A5A", "#86C0B0", "#E9A27C", "#5D55EA", "#3E8E7E", "#B5651D", "#8E6FC0", "#D4A017",
            "#6F9FB8", "#CF8F7A", "#9CB86F", "#E07A9B"]   # same order as templates/viewer.html


def floorplans_svg(mdl, zones: list[dict], W: int = 1160, H: int = 410, merge: bool = True) -> str:
    """All storeys as plans, coloured by use, with legend. Rotated so the main walls are straight
    (no north arrow). Identical consecutive storeys are merged ('1.–2. OG'). Same scale for all plans,
    grid chosen for the largest scale."""
    zinfo = {z["zone"]: z for z in zones}
    floors = []
    for z in sorted(zones, key=lambda z: z["zmin"]):
        if z["floor"] not in floors:
            floors.append(z["floor"])
    polys = {f: [] for f in floors}                     # floor -> [(use, [(x, y)])]
    for srf in mdl.surfaces:
        z = zinfo.get(srf["zone"])
        if not z or srf["type"] != "floor" or len(srf["pts"]) < 3:
            continue
        polys[z["floor"]].append((z["use"] or "ohne Zuordnung", [(p[0], p[1]) for p in srf["pts"]]))
    floors = [f for f in floors if polys[f]]
    if not floors:
        return ""
    # -- straighten: dominant edge direction (mod 90°), weighted by length
    acc = {}
    for f in floors:
        for _, pl in polys[f]:
            for (x1, y1), (x2, y2) in zip(pl, pl[1:] + pl[:1]):
                ln = math.hypot(x2 - x1, y2 - y1)
                if ln > 0.3:
                    a = round(math.degrees(math.atan2(y2 - y1, x2 - x1)) % 90)
                    acc[a % 90] = acc.get(a % 90, 0) + ln
    ang = math.radians(max(acc, key=acc.get) if acc else 0)
    ca, sa = math.cos(-ang), math.sin(-ang)

    def rot(p):
        return (p[0] * ca - p[1] * sa, p[0] * sa + p[1] * ca)
    for f in floors:
        polys[f] = [(u, [rot(p) for p in pl]) for u, pl in polys[f]]
    xs = [p[0] for f in floors for _, pl in polys[f] for p in pl]
    ys = [p[1] for f in floors for _, pl in polys[f] for p in pl]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = max(x1 - x0, 1), max(y1 - y0, 1)
    if bh > bw * 1.15:                                   # portrait building -> turn by 90° (wide plans fit better)
        for f in floors:
            polys[f] = [(u, [(p[1], -p[0]) for p in pl]) for u, pl in polys[f]]
        x0, x1, y0, y1 = y0, y1, -x1, -x0
        bw, bh = bh, bw

    # -- merge identical consecutive storeys (Regelgeschosse)
    def sig(f):
        return sorted((u, round(sum(abs(_area2(pl)) for uu, pl in polys[f] if uu == u) / 2)) for u in
                      {u for u, _ in polys[f]})
    groups = []
    for f in floors:
        if merge and groups and sig(groups[-1][-1]) == sig(f):
            groups[-1].append(f)
        else:
            groups.append([f])
    groups = groups[::-1]                                # top storey first
    label = {tuple(g): (g[0] if len(g) == 1 else f"{g[0]} – {g[-1]}".replace(". OG – ", ".–")) for g in groups}

    # -- uses, colours (by total area, same as the 3D viewer), legend
    area = {}
    for z in zones:
        u = z["use"] or "ohne Zuordnung"
        area[u] = area.get(u, 0) + z["area"]
    uses = sorted(area, key=area.get, reverse=True)
    col = {u: PLAN_PAL[i % len(PLAN_PAL)] for i, u in enumerate(uses)}
    shown = [u for u in uses if any(u == uu for g in groups for uu, _ in polys[g[0]])]
    lcols = 1 if len(shown) <= 26 else 2
    LW = 290 if lcols == 1 else 500
    row = min(19.0, (H - 8) / math.ceil(len(shown) / lcols))
    fs = min(13.0, row - 3.5)

    # -- layout: prepared arrangements for 1-8 plans (plans per row, top row first). Every plan gets
    #    the same cell size and the same scale; the cells fill the whole area left of the legend.
    #    The arrangement with the largest scale wins. More than 8 plans: rows of up to 5.
    gap, th = 22, 20
    aw, ah = W - LW - 16, H
    n = len(groups)
    pats = LAYOUTS.get(n) or [[5] * (n // 5) + ([n % 5] if n % 5 else [])]

    def fit(pat):
        c, r = max(pat), len(pat)
        cw, chh = (aw - (c - 1) * gap) / c, (ah - (r - 1) * gap) / r
        return min(cw / bw, (chh - th) / bh), pat, cw, chh

    sc, pat, cw, chh = max((fit(p) for p in pats), key=lambda x: x[0])
    pw, ph = bw * sc, bh * sc                           # drawn plan size (same for every storey)
    c = max(pat)
    out, i = [], 0
    for ri, k in enumerate(pat):
        cells = groups[i:i + k]; i += k
        rx = (c - k) * (cw + gap) / 2                   # shorter row: centred on the same cell grid
        for ci, g in enumerate(cells):
            cx = rx + ci * (cw + gap)
            cy = ri * (chh + gap)
            px = cx + (cw - pw) / 2                     # plan centred in its cell
            py = cy + th + (chh - th - ph) / 2
            out.append(f'<text x="{px:.1f}" y="{py - 6:.1f}" font-size="15" font-weight="700" fill="{INK}">'
                       f'{html.escape(label[tuple(g)])}</text>')
            for u, pl in polys[g[0]]:
                pts = " ".join(f"{px + (p[0] - x0) * sc:.1f},{py + (y1 - p[1]) * sc:.1f}" for p in pl)
                out.append(f'<polygon points="{pts}" fill="{col[u]}" stroke="#ffffff" stroke-width="0.9" '
                           f'stroke-linejoin="round"/>')
    # legend
    lx, ly = W - LW + 6, 4
    per = math.ceil(len(shown) / lcols)
    for k, u in enumerate(shown):
        x = lx + (k // per) * (LW / lcols)
        y = ly + (k % per) * row
        nm = u if len(u) <= 30 else u[:29] + "…"
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{fs:.0f}" height="{fs:.0f}" rx="2" fill="{col[u]}"/>'
                   f'<text x="{x + fs + 6:.1f}" y="{y + fs - 1.5:.1f}" font-size="{fs:.1f}" fill="{INK}">{html.escape(nm)}</text>'
                   f'<text x="{x + LW / lcols - 10:.1f}" y="{y + fs - 1.5:.1f}" font-size="{fs:.1f}" text-anchor="end" '
                   f'fill="{MUTED}">{round(area[u]):,} m²</text>'.replace(",", "."))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'font-family="Inter,Segoe UI,Arial,sans-serif"><rect width="{W}" height="{H}" fill="#fff"/>'
            f'{"".join(out)}</svg>')


def _area2(pl) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pl, pl[1:] + pl[:1]))


def svg_b64(svg: str) -> str:
    import base64
    return base64.b64encode(svg.encode("utf-8")).decode()


# ---------------------------------------------------------------- HVAC list (no model viewer)
def hvac_list_cards(inv: list[dict], ncol: int = 4) -> list[str]:
    """Written HVAC summary for PDF/PPTX: chapters distributed over `ncol` columns; per column the inner
    HTML of one card (.cardhead per chapter, one <p> per component -> editable text in PowerPoint).
    Identical components (same type and figures) are merged: '2× Wärmepumpe'."""
    def esc(x):
        return html.escape(str(x))
    blocks = []
    for ch in inv:
        groups: dict = {}
        for it in ch["items"]:
            figs = tuple((k, v) for k, v in it["figures"] if k != "Anzahl" and v != "automatisch")
            cnt = next((v for k, v in it["figures"] if k == "Anzahl"), "")
            g = groups.setdefault((it["label"], figs, cnt), [])
            g.append(it["name"])
        rows = []
        for (label, figs, cnt), names in groups.items():
            n = len(names)
            head = (f"{n}× " if n > 1 else "") + esc(label)
            sub = cnt or (names[0] if n == 1 and names[0] and len(names[0]) <= 40 else "")
            f = " · ".join(f"{esc(k)} <b>{esc(v)}</b>" for k, v in figs)
            rows.append(f'<p class="hv-it"><b class="hv-l">{head}</b>{f" <span class=hv-s>{esc(sub)}</span>" if sub else ""}'
                        f'{f"<br><span class=hv-f>{f}</span>" if f else ""}</p>')
        blocks.append((len(rows) + 1.5, f'<div class="cardhead">{esc(ch["chapter"])}</div>{"".join(rows)}'))
    ncol = max(1, min(ncol, len(blocks)))
    # keep chapter order, cut into ncol columns of similar height
    total = sum(w for w, _ in blocks)
    cols, cur, acc = [], [], 0.0
    for w, h in blocks:
        if cur and acc + w / 2 > total / ncol * (len(cols) + 1) and len(cols) < ncol - 1:
            cols.append(cur); cur = []
        cur.append(h); acc += w
    cols.append(cur)
    return ["".join(c) for c in cols]


# ---------------------------------------------------------------- timeline
WHO = {"Kunde": GREY, "OPTIMUSE": SB, "gemeinsam": INK}


def timeline_svg(stage: str) -> str:
    """Standard process in working days (5 per week). 2 weeks from receipt of all documents.
    Bars already done for the current stage are drawn solid, later ones solid too (brand colour),
    the customer task is dashed and interrupted (open-ended)."""
    rows = [  # label, start, length, who, note, kind
        ("Auftrag erhalten", 0, 0, "Kunde", "", "ms"),
        ("Pläne hochgeladen", 1, 0, "Kunde", "", "ms"),
        ("Erstellung 3D-Modell", 1.5, 3, "OPTIMUSE", "", "bar"),
        ("Kick-off", 5, 0, "gemeinsam", "", "ms"),
        ("Restliche Unterlagen hochladen", 5.3, 3.7, "Kunde", "Kundenaufgabe", "client"),
        ("Erstellung Baseline & Simulation", 9, 2.86, "OPTIMUSE", "Start nach Erhalt aller Unterlagen", "bar"),
        ("Strategien & Varianten", 11.86, 5.71, "OPTIMUSE", "", "bar"),
        ("Abgabe Ergebnisunterlagen", 17.57, 1.43, "OPTIMUSE", "", "bar"),
        ("Endpräsentation (optional)", 20.5, 0, "gemeinsam", "Termin nach Vereinbarung", "opt"),
    ]
    if stage == "baseline":   # kick-off after the baseline: documents and baseline done before
        rows[3] = ("Kick-off", 12, 0, "gemeinsam", "", "ms")
    L, T, DW, RH = 300, 40, 33.0, 34          # left margin, top, px per day, row height
    W = L + 25 * DW + 160
    H = T + len(rows) * RH + 80
    s = []
    for k in range(5):
        x = L + k * 5 * DW
        s.append(f'<line x1="{x}" y1="{T - 10}" x2="{x}" y2="{T + len(rows) * RH}" stroke="{LINE}"/>')
        s.append(f'<text x="{x + 2.5 * DW}" y="{T - 16}" text-anchor="middle" font-size="14" font-weight="600" '
                 f'fill="{MUTED}">Woche {k + 1}</text>')
    for i, (lab, a, ln, who, note, kind) in enumerate(rows):
        y = T + i * RH
        if i % 2:
            s.append(f'<rect x="{L - 5}" y="{y}" width="{25 * DW + 10}" height="{RH}" fill="#FAFAFB"/>')
        c = WHO[who]
        weight = "700" if lab == "Kick-off" else "400"
        s.append(f'<text x="{L - 14}" y="{y + RH / 2 + 5}" text-anchor="end" font-size="15" font-weight="{weight}" '
                 f'fill="{MUTED if kind == "opt" else INK}">{lab}</text>')
        x = L + a * DW
        if kind == "bar":
            s.append(f'<rect x="{x}" y="{y + 9}" width="{ln * DW}" height="{RH - 18}" rx="6" fill="{c}"/>')
            xe = x + ln * DW + 8
        elif kind == "client":
            w1 = 1.2 * DW
            s.append(f'<rect x="{x}" y="{y + 9}" width="{w1}" height="{RH - 18}" rx="6" fill="#fff" stroke="{c}" '
                     f'stroke-width="2" stroke-dasharray="6 4"/>')
            s.append(f'<text x="{x + w1 + 0.3 * DW}" y="{y + RH / 2 + 6}" text-anchor="middle" font-size="17" '
                     f'font-weight="700" fill="{c}">//</text>')
            s.append(f'<rect x="{x + w1 + 0.6 * DW}" y="{y + 9}" width="{(ln - 1.8) * DW}" height="{RH - 18}" rx="6" '
                     f'fill="#fff" stroke="{c}" stroke-width="2" stroke-dasharray="6 4"/>')
            xe = x + ln * DW + 8
        else:
            fill = "#fff" if kind == "opt" else c
            cx, cy, r = x, y + RH / 2, 9
            s.append(f'<path d="M{cx} {cy - r}L{cx + r} {cy}L{cx} {cy + r}L{cx - r} {cy}Z" fill="{fill}" '
                     f'stroke="{c}" stroke-width="2"/>')
            xe = x + 16
        if note:
            s.append(f'<text x="{xe}" y="{y + RH / 2 + 5}" font-size="13" fill="{MUTED}">{note}</text>')
    yb = T + len(rows) * RH + 14
    x1, x2 = L + 9 * DW, L + 19 * DW
    s.append(f'<line x1="{x1 + 6}" y1="{yb}" x2="{x2 - 6}" y2="{yb}" stroke="{SB140}" stroke-width="2"/>'
             f'<path d="M{x1} {yb}l9 -5v10z M{x2} {yb}l-9 -5v10z" fill="{SB140}"/>'
             f'<text x="{(x1 + x2) / 2}" y="{yb - 6}" text-anchor="middle" font-size="13.5" font-weight="700" '
             f'fill="{SB140}">ca. 2 Wochen ab Erhalt aller Unterlagen</text>')
    lx, ly = L, yb + 36
    for name, c in WHO.items():
        s.append(f'<rect x="{lx}" y="{ly - 11}" width="13" height="13" rx="2" fill="{c}"/>'
                 f'<text x="{lx + 20}" y="{ly}" font-size="13" fill="{INK}">{name}</text>')
        lx += 130
    s.append(f'<path d="M{lx + 6} {ly - 11}l7 7l-7 7l-7 -7z" fill="#fff" stroke="{INK}" stroke-width="1.6"/>'
             f'<text x="{lx + 20}" y="{ly}" font-size="13" fill="{INK}">Termin</text>')
    lx += 110
    s.append(f'<rect x="{lx}" y="{ly - 11}" width="13" height="13" rx="2" fill="#fff" stroke="{GREY}" '
             f'stroke-dasharray="3 2" stroke-width="1.6"/><text x="{lx + 20}" y="{ly}" font-size="13" fill="{INK}">'
             f'Kundenaufgabe (offene Dauer)</text>')
    return (f'<svg viewBox="0 0 {W:.0f} {H:.0f}" width="100%" style="font-family:Inter,Arial,sans-serif" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(s)}</svg>')
