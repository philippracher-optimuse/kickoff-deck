"""Project layout: where the kick-off tool finds inputs and writes outputs.

All paths are relative to the project root. The defaults match the classic project
template (old launcher). A project can override any entry with `kickoff/kickoff_config.json`
(e.g. for the cloud launcher if folder names differ) - no code change needed.
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
try:  # Windows needs the tzdata package for zoneinfo; fall back to local time
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Vienna")
except Exception:  # noqa: BLE001
    TZ = None

DEFAULT_LAYOUT = {
    "kickoff_dir": "kickoff",                                   # tool workspace inside the project
    "project_brief": "07_presentation/data/project_brief.json",  # written by runbook 01 (may not exist yet)
    "metadata_glob": ["files/metadata/*.json", "kickoff/input/*metadata*.json"],  # platform building metadata
    "idf_globs": ["03_original_model/baseline/baseline_final.idf",
                  "03_original_model/baseline/baseline_*.idf",
                  "kickoff/input/*.idf"],                       # first match wins (input/ = cloud download)
    "zone_register": "files/baseline_definition/zone_register.json",
    "enduse": "07_presentation/data/enduse.json",               # baseline end uses (pipeline output)
    "customer_docs": "files/customer",
    "transcripts": "02_transcripts",                            # handover target: runbook 01 ingests this folder
    "memory_building": "memory/building_data.md",
    "skill_dirs": [".claude/skills/optimuse-slides",            # deckkit: project copy first
                   "~/.claude/skills/optimuse-slides"],         # then the global copy
}


@dataclass
class Project:
    root: str
    layout: dict = field(default_factory=dict)

    @classmethod
    def open(cls, root: str) -> "Project":
        root = os.path.abspath(os.path.expanduser(root))
        if not os.path.isdir(root):
            raise SystemExit(f"Projektordner nicht gefunden: {root}")
        layout = dict(DEFAULT_LAYOUT)
        cfg = os.path.join(root, DEFAULT_LAYOUT["kickoff_dir"], "kickoff_config.json")
        if os.path.isfile(cfg):
            layout.update(json.load(open(cfg, encoding="utf-8")).get("layout", {}))
        return cls(root, layout)

    # -- paths -------------------------------------------------------------
    def p(self, key: str) -> str:
        return os.path.join(self.root, self.layout[key])

    @property
    def kdir(self) -> str:
        d = self.p("kickoff_dir")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def brief_path(self) -> str:
        return os.path.join(self.kdir, "kickoff_brief.json")

    @property
    def out_dir(self) -> str:
        d = os.path.join(self.kdir, "out")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def assets_dir(self) -> str:
        """Optional overrides: model3d.png/.html, hvac.png/.html (e.g. exports of the model viewer)."""
        return os.path.join(self.kdir, "assets")

    def asset(self, name: str) -> str | None:
        f = os.path.join(self.assets_dir, name)
        return f if os.path.isfile(f) else None

    def first(self, key: str) -> str | None:
        pats = self.layout[key]
        for pat in ([pats] if isinstance(pats, str) else pats):
            hits = sorted(glob.glob(os.path.join(self.root, pat)))
            hits = [h for h in hits if not h.endswith((".log", ".md"))]
            if hits:
                return hits[0]
        return None

    def exists(self, key: str) -> bool:
        return os.path.isfile(self.p(key))

    def launcher(self) -> str:
        """'classic' = old launcher (files on disk); 'cloud' = new launcher (data in the platform graph)."""
        f = os.path.join(self.root, ".optimuse-project.json")
        if os.path.isfile(f):
            track = json.load(open(f, encoding="utf-8")).get("track", "")
            if track and track != "classic":
                return "cloud"
        return "classic"

    def skill_dir(self) -> str:
        for d in self.layout["skill_dirs"] + [os.environ.get("OPTIMUSE_SLIDES", "")]:
            if not d:
                continue
            d = d if os.path.isabs(os.path.expanduser(d)) else os.path.join(self.root, d)
            d = os.path.expanduser(d)
            if os.path.isfile(os.path.join(d, "deckkit", "__init__.py")):
                return d
        raise SystemExit("deckkit (Skill optimuse-slides) nicht gefunden. Im Projekt "
                         "./update_skill.sh --global ausführen oder OPTIMUSE_SLIDES setzen.")


def stamp() -> str:
    """File prefix JJJJ-MM-TT_HHMM (Europe/Vienna) - newest file sorts last."""
    return datetime.now(TZ).strftime("%Y-%m-%d_%H%M")


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="minutes")
