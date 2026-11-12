+++
id = "kickoff"
order = -1
title = "Client Kick-off (external tool)"
model = "sonnet"
entry = [ "<project>/files/customer/*", "<project>/02_transcripts/*" ]

[[exit]]
label = "kickoff brief"
glob = "kickoff/kickoff_brief.json"

[[exit]]
label = "deck (customer, after meeting)"
glob = "kickoff/out/*_Kick-off-Deck.pdf"

[[exit]]
label = "protocol"
glob = "kickoff/out/*_Kick-off-Protokoll.md"
+++

# Runbook K — Client Kick-off (external tool, not part of phases 00–08)

Entry points: `Kickoff_starten.bat` (double-click) or the user just pastes the tool path in a project
session → `$TOOL/CLAUDE.md` decides the step from the project state.

Tool: local folder `…\Projekte\tools\kickoff-deck` or a clone of
https://github.com/philippracher-optimuse/kickoff-deck (`$TOOL` below; cloud: see `$TOOL/CLAUDE.md` §0–1).
Project: the project root (`$PRJ`). Outputs always go to `$PRJ/kickoff/`.
Run Python with the **project's** venv (deckkit + playwright live there):

```powershell
$PY  = "$PRJ\.venv\Scripts\python.exe"      # cloud launcher without .venv: uv run --with playwright --with python-pptx --with matplotlib python
& $PY $TOOL\kickoff.py <cmd> $PRJ
```

Single input file = `$PRJ/kickoff/kickoff_brief.json` (shape: `$TOOL/kickoff_lib/brief.py` docstring;
keys = project_brief.json + kick-off additions). The deck is built **only** from this file.
Layout reference (approved 2026-11-11): `$TOOL/reference/2026-11-11_1518_Kick-off-Deck.pdf`.

## Rules (all steps)

- Never invent numbers. Missing → leave empty, `status: "offen"`.
- Every value carries a source tag: `[doc:<file> p.N]`, `[platform:<what>]`, `[idf:<file>]`,
  `[assume:<why>]`, `[kickoff:<YYYY-MM-DD> @mm:ss]`.
- Status per entry: `vorgeschlagen` (from documents/assumption) · `bestaetigt` · `geaendert` · `offen`.
- Never downgrade a `bestaetigt`/`geaendert` entry; never delete entries — set `offen` or log in
  `kickoff.changelog`.
- Customer-facing text in German, short, ToV of `optimuse-slides/tone-of-voice.md`. Headlines short.
- File names carry the `JJJJ-MM-TT_HHMM_` prefix (tool does it). Never rename to "final"/"aktuell".

---

## K1 — Before the meeting: fill `kickoff_brief.json`

**K1.1 Deterministic pre-fill**
```powershell
& $PY $TOOL\kickoff.py init $PRJ --product "Energy Design"   # | "Value Engineering" | "Energy Performance Analytics"
& $PY $TOOL\kickoff.py status $PRJ
```
Reads (only empty fields are filled): `07_presentation/data/project_brief.json` (if it already exists),
platform metadata, `memory/project_identity.md`, the baseline IDF (zones, U-values, HVAC), `enduse.json`.
Writes `kickoff/sources.md` = list of documents the tool cannot read itself.
Paths differ in a project → `kickoff/kickoff_config.json` `{"layout": {...}}` (keys: `kickoff_lib/project.py`).

**K1.2 Stage** (decides which slides the customer sees)
| stage | meaning | slides added |
|---|---|---|
| `none` | no plans yet | — |
| `model` | plans in, 3D model built (IDF geometry) | Raummodell |
| `baseline` | baseline simulated | Anlagen, Annahmen, Kennwerte, Befunde |

Auto-detected; override: `kickoff.py stage $PRJ baseline` (`auto` resets).

**K1.3 AI reads the sources and completes the brief** (edit the JSON directly)
- Classic launcher: every file in `kickoff/sources.md` (pdf MCP for PDFs; `02_transcripts/*`; `notes/`).
- Cloud launcher: platform tools — customer files (`customer_files_read` list/summary/read), team notes,
  Goals questionnaire (`goals_read`), building data. Record what was read in `meta.sources_read`.
- Fill: `team` (name, role, org), `understanding` (Bilanzgrenze, Besonderheit, Anlass, Halten/Verkaufen,
  correct the HVAC lines), `goals` (id G1…, `text`, `short` ≤ 60 chars, `kind`, `target` if measurable,
  `priority` empty), `constraints` (`kind`: Budget/Technik/Denkmal/Betrieb/…), `strategies` (3–5 proposals,
  archetypes: Betriebsoptimierung · Hülle · Tausch Wärmeerzeuger · Elektrifizierung · Kombination; no measure
  numbers), `open_items` (missing documents per Kickoff-Leitfaden Teil A/B + who + due),
  `assumptions` values, `product_details.ve` / `.epa` for those products.
- Stage `baseline` only: `findings` (2–3, title ≤ 6 words + one sentence + lever) and, if `enduse.json` is
  missing, `baseline.kpis` / `baseline.enduse` / `baseline.carriers` from the simulation (eplus MCP or
  platform results) — numbers only from results, with source.
- 3D model + HVAC schematic: automatic. The tool runs the installed model viewer's own code
  (`optimuse-viewer`, found under `%APPDATA%\uv\tools\optimuse-viewer`; override with env
  `OPTIMUSE_VIEWER_PY`) → `kickoff/.viewer/` (cached per IDF). No viewer → own 3D model with fewer room
  details and a written HVAC list. Optional overrides in `kickoff/assets/`: `model3d.png`, `model3d.html`,
  `hvac.html` (e.g. View ▸ Export HVAC schematic in the viewer), `hvac.png`.

**K1.4 Check:** `kickoff.py status $PRJ` — everything still `offen` becomes a question in the meeting.

## K2 — Build the deck for the meeting

```powershell
& $PY $TOOL\kickoff.py build $PRJ --export
```
Writes to `kickoff/out/`, one timestamp per build (customer version only, slides per stage):
| file | for |
|---|---|
| `*_Kick-off-Deck.html` | **present this one**: self-contained, works offline, 3D model + HVAC schematic interactive |
| `*_Kick-off-Deck.pdf` / `.pptx` | send / edit. Always static content: "Raummodell" = floor plans of all storeys by use (identical storeys merged; prepared layouts for 1–8 plans in `visuals.LAYOUTS`; no customer question on this slide), "Anlagen" = written HVAC list with key figures |

`--export` needs playwright + chromium (`& $PY -m playwright install chromium`, once). Without it the
HTML is still written and the tool prints the error. playwright also renders the small 3D picture on
"Projekt & Gebäude" (cached in `kickoff/.viewer/`); without it that picture falls back to matplotlib.

QA before sending: open the PDF; "Raummodell" shows every storey, "Anlagen" the list; no "offen" row
the customer should not see.

## K3 — After the meeting: update, rebuild, protocol

**K3.1 Transcript** → `kickoff/` (Kickscale export .txt) or `02_transcripts/`.

**K3.2 AI updates `kickoff_brief.json` from the transcript** — walk every "Frage an den Kunden" slide:
- confirmed → `status: "bestaetigt"`, add `[kickoff:<date> @mm:ss]` to `source`.
- changed → new value, `status: "geaendert"`, append `{field, old, new, source}` to `kickoff.changelog`.
- new item named by the customer → add with `status: "bestaetigt"`.
- still unanswered → stays `offen` and becomes an `open_items` row (who + due).
- set `kickoff.date`, `kickoff.attendees`, `kickoff.decisions` (≤ 8 bullet sentences), `meta.kickoff_date`;
  goal `priority` (1, 2, 3 …) if the customer ranked them.
- re-check `meta.stage`.

**K3.3 Rebuild + protocol**
```powershell
& $PY $TOOL\kickoff.py build $PRJ --export      # corrected deck → send *_Kick-off-Deck.pdf (+ .html)
& $PY $TOOL\kickoff.py protocol $PRJ --export   # *_Kick-off-Protokoll.md / .html / .pdf (send within 2 working days)
```

## K4 — Handover to the project process (only when needed)

```powershell
& $PY $TOOL\kickoff.py handover $PRJ
```
- `project_brief.json` does **not** exist yet → copies `kickoff_brief.json` + a readable `kickoff_brief.md`
  (protocol + proposed project_brief.json) into `02_transcripts/`. Runbook 01 §2.5 ingests that folder as
  kick-off source — no change to the phase runbooks.
- `project_brief.json` exists → writes `kickoff/handover_diff.md` (differences only, nothing overwritten);
  the user decides what goes into the brief.
- Cloud launcher: uploading `kickoff_brief.md` to the platform is optional — only on request.

## Session end
Report to the user: stage, files written (paths), what is still `offen`.
