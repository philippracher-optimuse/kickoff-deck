# Kick-off tool — instructions for Claude

You are reading this because the user pointed you at this tool inside a **project** session —
by its local path (`…\Projekte\tools\kickoff-deck`), by its repository
(`https://github.com/philippracher-optimuse/kickoff-deck`), or via the start script
`Kickoff_starten.bat`. That means: **run the client kick-off for the current project.** Do not ask
what the path is for.

## 0. Get the tool (`$TOOL`)

- Local Windows session (classic launcher, model viewer on the PC): `$TOOL` = the given path.
- The path is not reachable (e.g. **cloud model viewer / Linux container**): fetch the repository
  ```bash
  git clone --depth 1 https://github.com/philippracher-optimuse/kickoff-deck ~/kickoff-deck \
    || git -C ~/kickoff-deck pull --ff-only
  ```
  `$TOOL=~/kickoff-deck`. If git or the network is not available, tell the user exactly that and stop.

## 1. Find the project and the situation (no questions yet)

- Project root `$PRJ` = the current working directory (the folder with `CLAUDE.md` / `.claude/`
  / `runbooks/`), or the folder named in the prompt. In a container: the writable project working
  directory you were started in.
- Python: `$PRJ\.venv\Scripts\python.exe` (Windows) if it exists; else
  `uv run --directory $PRJ --with playwright --with python-pptx --with matplotlib python`;
  else plain `python3` (matplotlib/playwright optional — without them: no PDF/PPTX, HTML still works).
- Cloud / container only — the project data lives on the platform, not on disk. Before `init`,
  put what the tool needs into `$PRJ/kickoff/input/` with the platform tools:
  - newest baseline IDF: generated files (`generated_files_read` list → download) →
    `kickoff/input/model.idf` (download link with `curl -L -o`). No IDF yet → stage `none`, fine.
  - building data: `ask_hans` / building metadata → `kickoff/input/building_metadata.json`
    (name, address, year, use, areas) if obtainable.
  - customer documents, team notes, goals questionnaire: read them in K1.3 directly with the
    platform tools (`customer_files_read`, `team_notes_read`, `goals_read`) — no download needed.
  - Record what you read in `kickoff_brief.json` `meta.sources_read`.
- Deck layout needs deckkit (skill `optimuse-slides`): searched in `$PRJ/.claude/skills/`,
  `~/.claude/skills/` or env `OPTIMUSE_SLIDES`. Not found → tell the user and stop (do not
  improvise a deck).
- Decide the step from the files, in this order:

| situation | step |
|---|---|
| `kickoff/kickoff_brief.json` missing | **K1 + K2** (before the meeting) |
| a transcript in `kickoff/` (`*.txt`, `*.vtt`, `*.docx`) or a new kick-off transcript in `02_transcripts/` newer than `kickoff_brief.json`, and `kickoff.date` still empty | **K3** (after the meeting) |
| `kickoff.date` set, `project_brief.json` missing, user asks for handover | **K4** |
| otherwise | ask the user in ONE question: rebuild deck · after the meeting (transcript) · handover |

- Product: from the prompt, else `kickoff_brief.json` `meta.product`, else ask once
  (Energy Design · Value Engineering · Energy Performance Analytics).

## 2. Run it

Follow `$TOOL/runbook/kickoff.md` for that step exactly (rules, source tags, status values).
Short form:

```
$PY $TOOL/kickoff.py init     $PRJ --product "Energy Design"   # K1.1, only if the brief is missing
$PY $TOOL/kickoff.py status   $PRJ
#   K1.3: read the sources (kickoff/sources.md + platform tools), complete kickoff/kickoff_brief.json
$PY $TOOL/kickoff.py build    $PRJ --export                    # K2 / K3.3
$PY $TOOL/kickoff.py protocol $PRJ --export                    # K3.3 only
```

3D model and HVAC schematic in the HTML come from the installed model viewer when it is on the same
machine (`kickoff_lib/viewer.py`); otherwise the tool uses its own 3D model and the HVAC list.
PDF/PPTX always show floor plans + HVAC list.

## 3. Finish

- Cloud / container: the user cannot open files in the container. Ask once whether to upload the
  deck (`kickoff/out/*_Kick-off-Deck.html` and `.pdf`) to the building's documents
  (`customer_files_upload`); do it on yes.
- Tell the user in German, short: which step ran, the files written, what is still `offen`
  (these become questions in the meeting), and what they have to do next.
