"""Read an EnergyPlus IDF without dependencies: zones + surfaces (3D model), envelope U-values,
HVAC components. Pure standard library so it runs in any Python 3.11+."""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict

BOUNDARY = {"outdoors", "surface", "ground", "adiabatic", "zone", "foundation", "othersidecoefficients",
            "othersideconditionsmodel", "groundfcfactormethod", "groundslabpreprocessoraverage",
            "groundslabpreprocessorcore", "groundslabpreprocessorperimeter", "groundbasementpreprocessoraveragewall",
            "groundbasementpreprocessoraveragefloor", "groundbasementpreprocessorupperwall",
            "groundbasementpreprocessorlowerwall", "space"}


def parse(path: str) -> list[tuple[str, list[str]]]:
    txt = open(path, encoding="latin-1").read()
    txt = re.sub(r"!.*", "", txt)
    objs = []
    for chunk in txt.split(";"):
        f = [x.strip() for x in chunk.split(",")]
        if f and f[0]:
            objs.append((f[0].lower(), f[1:]))
    return objs


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- polygon helpers
def newell(p):
    nx = ny = nz = 0.0
    for i in range(len(p)):
        x1, y1, z1 = p[i]; x2, y2, z2 = p[(i + 1) % len(p)]
        nx += (y1 - y2) * (z1 + z2); ny += (z1 - z2) * (x1 + x2); nz += (x1 - x2) * (y1 + y2)
    return nx, ny, nz


def area(p) -> float:
    return math.sqrt(sum(c * c for c in newell(p))) / 2


def triangulate(p) -> list[tuple[int, int, int]]:
    """Ear clipping in the polygon's dominant plane (handles concave floor plates)."""
    n = len(p)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]
    nx, ny, nz = (abs(c) for c in newell(p))
    ax = (1, 2) if nx >= ny and nx >= nz else (0, 2) if ny >= nz else (0, 1)
    q = [(v[ax[0]], v[ax[1]]) for v in p]
    s = sum(q[i][0] * q[(i + 1) % n][1] - q[(i + 1) % n][0] * q[i][1] for i in range(n))
    idx = list(range(n)) if s > 0 else list(range(n))[::-1]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    tris, guard = [], 0
    while len(idx) > 3 and guard < 10 * n:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = q[i0], q[i1], q[i2]
            if cross(a, b, c) <= 1e-12:
                continue
            if any(cross(a, b, q[j]) > 0 and cross(b, c, q[j]) > 0 and cross(c, a, q[j]) > 0
                   for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2)); idx.pop(k); break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    elif len(idx) > 3:  # degenerate: fan fallback
        tris += [(idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1)]
    return tris


def _verts(fields, start):
    nums = [_num(x) for x in fields[start:]]
    nums = [x for x in nums if x is not None]
    nums = nums[: len(nums) // 3 * 3]
    return [tuple(nums[i:i + 3]) for i in range(0, len(nums), 3)]


# ---------------------------------------------------------------- model
class Model:
    def __init__(self, path: str):
        self.path = path
        self.objs = parse(path)
        by = defaultdict(list)
        for t, f in self.objs:
            by[t].append(f)
        self.by = by
        rel = any(len(f) > 2 and f[2].lower() == "relative" for f in by.get("globalgeometryrules", []))
        self.origin = {}
        for f in by.get("zone", []):
            o = tuple(_num(x) or 0.0 for x in (f[2:5] + ["0", "0", "0"])[:3]) if rel else (0.0, 0.0, 0.0)
            self.origin[f[0]] = o
        self.surfaces = []
        for f in by.get("buildingsurface:detailed", []):
            b = next((i for i in range(3, min(len(f), 7)) if f[i].lower() in BOUNDARY), None)
            if b is None:
                continue
            zone = f[3]
            o = self.origin.get(zone, (0.0, 0.0, 0.0))
            pts = [(x + o[0], y + o[1], z + o[2]) for x, y, z in _verts(f, b + 6)]
            self.surfaces.append(dict(name=f[0], type=f[1].lower(), cons=f[2], zone=zone,
                                      bc=f[b].lower(), pts=pts))
        sz = {s["name"]: s for s in self.surfaces}
        self.windows = []
        for f in by.get("fenestrationsurface:detailed", []):
            host = sz.get(f[3])
            o = self.origin.get(host["zone"], (0, 0, 0)) if host else (0, 0, 0)
            pts = [(x + o[0], y + o[1], z + o[2]) for x, y, z in _verts(f, 9)]
            mult = _num(f[7]) or 1.0
            self.windows.append(dict(name=f[0], type=f[1].lower(), cons=f[2], host=host, pts=pts, mult=mult))

    # -- 3D model ------------------------------------------------------------
    def zones(self, register: dict | None = None) -> list[dict]:
        """One entry per zone: triangles, floor label, use, area. register: idf_zone_name -> info."""
        register = register or {}
        out = []
        by_zone = defaultdict(list)
        for s in self.surfaces:
            by_zone[s["zone"]].append(s)
        for zone, surfs in by_zone.items():
            verts, faces = [], []
            for s in surfs:
                base = len(verts)
                verts += s["pts"]
                faces += [(base + a, base + b, base + c) for a, b, c in triangulate(s["pts"])]
            zmin = min(v[2] for v in verts); zmax = max(v[2] for v in verts)
            fa = sum(area(s["pts"]) for s in surfs if s["type"] == "floor")
            info = register.get(zone, {})
            out.append(dict(zone=zone, name=info.get("model_zone_name") or zone,
                            use=(info.get("platform_space_type") or "").strip(),
                            cond=info.get("conditioned", True), zmin=zmin, zmax=zmax,
                            area=round(fa, 1), vol=round(fa * (zmax - zmin), 1), v=verts, f=faces))
        levels = sorted({round(z["zmin"] * 2) / 2 for z in out})
        lab = {}
        eg = next((l for l in levels if l > -0.5), levels[0] if levels else 0)
        ug = [l for l in levels if l < eg]
        for l in levels:
            if l < eg:
                lab[l] = "UG" if len(ug) == 1 else f"{ug.index(l) - len(ug)}. UG".replace("-", "")
            else:
                k = [x for x in levels if x >= eg].index(l)
                lab[l] = "EG" if k == 0 else f"{k}. OG"
        # merge levels closer than 1.5 m (split-level / stairs) into the lower storey
        merged, last = {}, None
        for l in levels:
            if last is not None and l - last < 1.5:
                merged[l] = merged[last]
            else:
                merged[l] = lab[l]; last = l
        for z in out:
            z["floor"] = merged[round(z["zmin"] * 2) / 2]
        return out

    def window_meshes(self) -> list[dict]:
        out = []
        for w in self.windows:
            if len(w["pts"]) >= 3:
                out.append(dict(v=w["pts"], f=triangulate(w["pts"])))
        return out

    def shading(self) -> list[dict]:
        """Shading:Building/Site:Detailed (e.g. Laubengang slabs, fins, neighbours).
        kind = 'attached' (within 5 m of the building) or 'context' (surroundings)."""
        pts = [p for s in self.surfaces for p in s["pts"]]
        if not pts:
            return []
        x0, x1 = min(p[0] for p in pts) - 5, max(p[0] for p in pts) + 5
        y0, y1 = min(p[1] for p in pts) - 5, max(p[1] for p in pts) + 5
        out = []
        for cls in ("shading:building:detailed", "shading:site:detailed"):
            for f in self.by.get(cls, []):
                v = _verts(f, 3)
                if len(v) < 3:
                    continue
                cx, cy = sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v)
                kind = "attached" if x0 <= cx <= x1 and y0 <= cy <= y1 else "context"
                out.append(dict(name=f[0], kind=kind, v=v, f=triangulate(v)))
        for f in self.by.get("shading:zone:detailed", []):
            host = next((s for s in self.surfaces if s["name"] == f[1]), None)
            o = self.origin.get(host["zone"], (0, 0, 0)) if host else (0, 0, 0)
            v = [(x + o[0], y + o[1], z + o[2]) for x, y, z in _verts(f, 4)]
            if len(v) >= 3:
                out.append(dict(name=f[0], kind="attached", v=v, f=triangulate(v)))
        return out

    def u_values(self) -> dict:
        """construction name (lower) -> (U [W/m²K], g or None). Opaque incl. Rsi/Rse 0.13/0.04."""
        out = {}
        for k, c in self.constructions().items():
            if c["kind"] == "window":
                out[k] = (c["u"], c["g"])
            elif c.get("r") is not None:
                out[k] = (round(1 / (c["r"] + 0.17), 3), None)
        return out

    # -- envelope ------------------------------------------------------------
    def _r_layers(self) -> dict:
        R = {}
        for f in self.by.get("material", []):
            t, k = _num(f[2]), _num(f[3])
            if t and k:
                R[f[0].lower()] = t / k
        for f in self.by.get("material:nomass", []):
            R[f[0].lower()] = _num(f[2]) or 0.0
        for f in self.by.get("material:airgap", []):
            R[f[0].lower()] = _num(f[1]) or 0.0
        return R

    def constructions(self) -> dict:
        R = self._r_layers()
        glaz = {f[0].lower(): (_num(f[1]), _num(f[2])) for f in self.by.get("windowmaterial:simpleglazingsystem", [])}
        out = {}
        for f in self.by.get("construction", []):
            layers = [x.lower() for x in f[1:] if x]
            if layers and layers[0] in glaz:
                out[f[0].lower()] = dict(kind="window", u=glaz[layers[0]][0], g=glaz[layers[0]][1])
            elif all(l in R for l in layers):
                out[f[0].lower()] = dict(kind="opaque", r=sum(R[l] for l in layers))
        return out

    def envelope(self) -> list[dict]:
        """Area-weighted U-values of the thermal envelope per element group (EN ISO 6946 Rsi/Rse)."""
        cons = self.constructions()
        groups = defaultdict(lambda: [0.0, 0.0])   # name -> [sum(U*A), sum(A)]
        rs = {"wall": 0.17, "roof": 0.14, "ceiling": 0.14, "floor": 0.17}
        for s in self.surfaces:
            c = cons.get(s["cons"].lower())
            if not c or c["kind"] != "opaque":
                continue
            ground = s["bc"].startswith("ground") or s["bc"] == "foundation"
            if s["bc"] != "outdoors" and not ground:
                continue
            name = {("wall", False): "Außenwand", ("wall", True): "Wand gegen Erdreich",
                    ("roof", False): "Dach", ("ceiling", False): "Dach", ("floor", True): "Bodenplatte",
                    ("floor", False): "Boden gegen Außenluft"}.get((s["type"], ground))
            if not name:
                continue
            u = 1 / (c["r"] + (0.17 if ground and s["type"] == "floor" else rs.get(s["type"], 0.17)))
            a = area(s["pts"])
            groups[name][0] += u * a; groups[name][1] += a
        rows = [dict(element=k, u_value=round(v[0] / v[1], 2), area_m2=round(v[1]))
                for k, v in groups.items() if v[1] > 0]
        wu = wa = wg = 0.0
        for w in self.windows:
            c = cons.get(w["cons"].lower())
            if c and c["kind"] == "window" and c["u"]:
                a = area(w["pts"]) * w["mult"]
                wu += c["u"] * a; wa += a; wg += (c["g"] or 0) * a
        if wa:
            rows.append(dict(element="Fenster", u_value=round(wu / wa, 2), g_value=round(wg / wa, 2),
                             area_m2=round(wa)))
        order = ["Außenwand", "Wand gegen Erdreich", "Dach", "Bodenplatte", "Boden gegen Außenluft", "Fenster"]
        return sorted(rows, key=lambda r: order.index(r["element"]) if r["element"] in order else 99)

    # -- HVAC ----------------------------------------------------------------
    HVAC_MAP = [  # (category, label, idf type prefix)
        ("Wärme", "Wärmepumpe", ("heatpump:plantloop:eir:heating", "heatpump:watertowater", "heatpump:airtowater")),
        ("Wärme", "Kessel", ("boiler:",)),
        ("Wärme", "Fernwärme", ("districtheating",)),
        ("Wärme", "Elektro-Heizregister", ("coil:heating:electric",)),
        ("Kälte", "Kältemaschine", ("chiller:",)),
        ("Kälte", "Wärmepumpe (Kühlen)", ("heatpump:plantloop:eir:cooling",)),
        ("Kälte", "Fernkälte", ("districtcooling",)),
        ("Kälte", "Rückkühler", ("coolingtower:", "fluidcooler:")),
        ("Kälte", "Split / DX", ("coil:cooling:dx",)),
        ("Übergabe", "Flächenheizung/-kühlung", ("zonehvac:lowtemperatureradiant:variableflow",
                                               "zonehvac:lowtemperatureradiant:constantflow")),
        ("Übergabe", "Heizkörper", ("zonehvac:baseboard",)),
        ("Übergabe", "Fan-Coils", ("zonehvac:fourpipefancoil",)),
        ("Lüftung", "Lüftungsanlage", ("airloophvac",)),
        ("Lüftung", "Wärmerückgewinnung", ("heatexchanger:airtoair",)),
        ("Lüftung", "Fensterlüftung", ("zoneventilation:windandstackopenarea",)),
        ("Lüftung", "Zu-/Abluft (Zone)", ("zoneventilation:designflowrate",)),
        ("Lüftung", "Lüftungsgerät dezentral", ("zonehvac:energyrecoveryventilator",)),
        ("Lüftung", "Ideal Loads", ("zonehvac:idealloadsairsystem",)),
        ("Warmwasser", "Warmwasserspeicher", ("waterheater:mixed", "waterheater:stratified")),
        ("Warmwasser", "Warmwasser-WP", ("waterheater:heatpump",)),
        ("Strom", "PV-Anlage", ("generator:photovoltaic", "generator:pvwatts")),
        ("Strom", "Batteriespeicher", ("electricloadcenter:storage",)),
    ]

    def hvac(self) -> dict:
        """category -> [(label, count, capacity_kW or None)] ; plus 'loops'."""
        cnt = Counter(t for t, _ in self.objs)
        out = defaultdict(list)
        for cat, label, prefixes in self.HVAC_MAP:
            types = [t for t in cnt if t.startswith(prefixes) and not t.endswith(":design")
                     and "surfacegroup" not in t]
            n = sum(cnt[t] for t in types)
            if n:
                cap = None
                for t in types:
                    for f in self.by[t]:
                        for x in f[1:8]:
                            v = _num(x)
                            if v and 1000 <= v <= 5e6 and label in ("Wärmepumpe", "Kessel", "Kältemaschine",
                                                                       "Wärmepumpe (Kühlen)"):
                                cap = (cap or 0) + v / 1000; break
                out[cat].append((label, n, round(cap) if cap else None))
        out["loops"] = [f[0] for f in self.by.get("plantloop", [])]
        return dict(out)

    # Written HVAC list (fallback when the model viewer is not installed).
    # (chapter, label, idf type, {field index: (key figure, unit, factor)})
    # Field indices = position after the class name, EnergyPlus 24.x/26.x IDD.
    INVENTORY = [
        ("Wärmeerzeugung", "Wärmepumpe", "heatpump:plantloop:eir:heating", "auto"),
        ("Wärmeerzeugung", "Wärmepumpe (Wasser/Wasser)", "heatpump:watertowater:equationfit:heating", "auto"),
        ("Wärmeerzeugung", "Kessel", "boiler:hotwater", {1: ("Brennstoff", "", None), 2: ("Nennleistung", "kW", 1e-3),
                                                           3: ("Wirkungsgrad", "", 1)}),
        ("Wärmeerzeugung", "Fernwärme", "districtheating:water", {3: ("Nennleistung", "kW", 1e-3)}),
        ("Kälteerzeugung", "Kältemaschine", "chiller:electric:eir", {1: ("Nennleistung", "kW", 1e-3),
                                                                   2: ("COP", "", 1)}),
        ("Kälteerzeugung", "Wärmepumpe (Kühlen)", "heatpump:plantloop:eir:cooling", "auto"),
        ("Kälteerzeugung", "Fernkälte", "districtcooling", {3: ("Nennleistung", "kW", 1e-3)}),
        ("Kälteerzeugung", "Rückkühler", "coolingtower:singlespeed", {}),
        ("Verteilung", "Pumpe (drehzahlgeregelt)", "pump:variablespeed", {3: ("Volumenstrom", "m³/h", 3600),
                                                                          4: ("Förderhöhe", "kPa", 1e-3),
                                                                          5: ("Leistung", "kW", 1e-3)}),
        ("Verteilung", "Pumpe (konstant)", "pump:constantspeed", {3: ("Volumenstrom", "m³/h", 3600),
                                                                  4: ("Förderhöhe", "kPa", 1e-3),
                                                                  5: ("Leistung", "kW", 1e-3)}),
        ("Übergabe", "Flächenheizung/-kühlung", "zonehvac:lowtemperatureradiant:variableflow", "zones"),
        ("Übergabe", "Flächenheizung (konstant)", "zonehvac:lowtemperatureradiant:constantflow", "zones"),
        ("Übergabe", "Heizkörper", "zonehvac:baseboard:radiantconvective:water", "zones"),
        ("Übergabe", "Heizkörper (elektrisch)", "zonehvac:baseboard:convective:electric", "zones"),
        ("Übergabe", "Fan-Coil", "zonehvac:fourpipefancoil", "zones"),
        ("Übergabe", "Ideale Anlage (Ideal Loads)", "zonehvac:idealloadsairsystem", "zones"),
        ("Lüftung", "Lüftungsanlage", "airloophvac", {}),
        ("Lüftung", "Wärmerückgewinnung", "heatexchanger:airtoair:sensibleandlatent",
         {2: ("Nennvolumenstrom", "m³/h", 3600), 3: ("Wirkungsgrad sensibel", "", 1)}),
        ("Lüftung", "Ventilator", "fan:systemmodel", {4: ("Volumenstrom", "m³/h", 3600)}),
        ("Lüftung", "Ventilator", "fan:variablevolume", {2: ("Wirkungsgrad", "", 1), 3: ("Druck", "Pa", 1),
                                                          4: ("Volumenstrom", "m³/h", 3600)}),
        ("Lüftung", "Ventilator", "fan:constantvolume", {2: ("Wirkungsgrad", "", 1), 3: ("Druck", "Pa", 1),
                                                          4: ("Volumenstrom", "m³/h", 3600)}),
        ("Lüftung", "Fensterlüftung", "zoneventilation:windandstackopenarea", "zones"),
        ("Lüftung", "Zu-/Abluft (Zone)", "zoneventilation:designflowrate", "zones"),
        ("Lüftung", "Lüftungsgerät dezentral", "zonehvac:energyrecoveryventilator", "zones"),
        ("Warmwasser", "Warmwasserspeicher", "waterheater:mixed", {1: ("Volumen", "l", 1000),
                                                                   6: ("Heizleistung", "kW", 1e-3),
                                                                   10: ("Energieträger", "", None)}),
        ("Warmwasser", "Schichtspeicher", "waterheater:stratified", {}),
        ("Warmwasser", "Warmwasser-Wärmepumpe", "waterheater:heatpump:pumpedcondenser", {}),
        ("Warmwasser", "Warmwasserverbrauch", "wateruse:equipment", "zones"),
        ("Strom", "PV-Anlage", "generator:pvwatts", {2: ("Leistung", "kWp", 1e-3), 7: ("Neigung", "°", 1),
                                                     8: ("Azimut", "°", 1)}),
        ("Strom", "PV-Anlage", "generator:photovoltaic", {}),
        ("Strom", "Batteriespeicher", "electricloadcenter:storage:simple", {}),
        ("Strom", "Batteriespeicher", "electricloadcenter:storage:liioncellmodel", {}),
    ]

    def hvac_inventory(self) -> list[dict]:
        """-> [{chapter, items: [{label, name, count, figures: [(key, value)]}]}] (order = INVENTORY)."""
        def fmt(v, unit, fac):
            x = _num(v)
            if fac is None or x is None:
                v = (v or "").strip()
                if v.lower() == "autosize":
                    return "automatisch"
                return {"electricity": "Strom", "naturalgas": "Erdgas", "districtheating": "Fernwärme",
                        "fueloilno1": "Heizöl", "propane": "Flüssiggas"}.get(v.lower(), v) or None
            y = x * fac
            s = f"{y:,.0f}" if abs(y) >= 100 else f"{y:,.1f}" if abs(y) >= 10 else f"{y:,.2f}"
            return s.replace(",", "X").replace(".", ",").replace("X", ".") + (f" {unit}" if unit else "")

        chapters: dict[str, list] = {}
        for chap, label, typ, spec in self.INVENTORY:
            rows = self.by.get(typ, [])
            if not rows:
                continue
            items = chapters.setdefault(chap, [])
            if spec == "zones":
                items.append(dict(label=label, name="", count=len(rows),
                                  figures=[("Anzahl", f"{len(rows)} Zone{'n' if len(rows) != 1 else ''}")]))
                continue
            for f in rows:
                figs = []
                if spec == "auto":   # heat pumps: first W-range number = capacity, then a COP-range number
                    nums = [(_num(x), x) for x in f[1:]]
                    cap = next((i for i, (v, _) in enumerate(nums) if v and 1000 <= v <= 5e6), None)
                    if cap is not None:
                        figs.append(("Nennleistung", fmt(nums[cap][1], "kW", 1e-3)))
                        cop = next((v for v, _ in nums[cap + 1:cap + 4] if v and 1.5 <= v <= 9), None)
                        if cop:
                            figs.append(("COP (Nenn)", fmt(str(cop), "", 1)))
                    elif any((x or "").lower() == "autosize" for x in f[1:12]):
                        figs.append(("Nennleistung", "automatisch dimensioniert"))
                else:
                    for i, (k, unit, fac) in spec.items():
                        if i < len(f) and f[i]:
                            v = fmt(f[i], unit, fac)
                            if v:
                                figs.append((k, v))
                items.append(dict(label=label, name=f[0], count=1, figures=figs))
        order = list(dict.fromkeys(c for c, *_ in self.INVENTORY))
        return [dict(chapter=c, items=chapters[c]) for c in order if c in chapters]

    def hvac_text(self) -> dict:
        """Short proposal per topic for the 'Projekt & Gebäude' table."""
        h = self.hvac()

        def txt(cats):
            parts = []
            for c in cats:
                for label, n, cap in h.get(c, []):
                    if label in ("Ideal Loads", "Zu-/Abluft (Zone)") and len(h.get(c, [])) > 1:
                        continue
                    s = label + (f" ({cap} kW)" if cap else "")
                    if c == "Übergabe":
                        s = label
                    parts.append(s)
            return ", ".join(dict.fromkeys(parts))
        return {"Wärme": txt(["Wärme"]) + (" · " + txt(["Übergabe"]) if txt(["Übergabe"]) else ""),
                "Kälte": txt(["Kälte"]), "Lüftung": txt(["Lüftung"]), "Warmwasser": txt(["Warmwasser"])}


def load_register(path: str | None) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    d = json.load(open(path, encoding="utf-8"))
    if not isinstance(d, list):
        return {}
    out = {}
    for r in d:  # index by original and by renamed zone name (zones may be renamed during phase 02)
        for k in ("idf_zone_name", "model_zone_name"):
            if r.get(k):
                out[r[k]] = r
    return out
