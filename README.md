# Kick-off-Tool

Externes Werkzeug für den Client Kick-off. Es ist (vorerst) **nicht** Teil der Phasen 00–08 und wird
bei Bedarf für ein Projekt aufgerufen.

## Starten – zwei Wege

**A) Doppelklick:** `Kickoff_starten.bat` in diesem Ordner doppelklicken (oder einen Projektordner auf die
Datei ziehen). Das Fenster fragt nach dem Projektordner (Enter = Auswahlfenster) und danach:

| Auswahl | was passiert |
|---|---|
| 1 Vor dem Termin | Claude startet im Projektordner, liest die Unterlagen, füllt `kickoff_brief.json`, baut das Deck |
| 2 Nach dem Termin | Claude arbeitet das Transkript ein, baut das korrigierte Deck und das Protokoll |
| 3 Nur Deck bauen | ohne Claude: Deck aus dem vorhandenen `kickoff_brief.json` neu bauen, Ordner öffnet sich |

**B) Im Modell-Viewer (lokal):** im Claude-Terminal des Projekts einfach den Pfad eingeben:

> `C:\Users\Philipp\Documents\Projekte\tools\kickoff-deck`

Claude liest dann `CLAUDE.md` in diesem Ordner, erkennt am Projektstand, was zu tun ist (vor oder nach
dem Termin) und baut das Deck. Fragt höchstens nach dem Produkt. Du kannst auch dazuschreiben, was du
willst, z. B. „… Produkt Value Engineering“ oder „… Transkript ist da“.

**C) Im neuen Modell-Viewer (Cloud):** dort sieht Claude deine Festplatte nicht. Stattdessen die
Repository-Adresse eingeben:

> `https://github.com/philippracher-optimuse/kickoff-deck – bau das Kick-off-Deck`

Claude lädt das Tool von GitHub, holt Modell und Unterlagen über die Plattform und lädt das fertige
Deck auf Wunsch in die Dokumente des Gebäudes hoch.

## Teilen und aktualisieren (GitHub)

Repository: https://github.com/philippracher-optimuse/kickoff-deck. Kollegen holen es einmalig mit
`git clone https://github.com/philippracher-optimuse/kickoff-deck` und aktualisieren mit `git pull`.
Nach eigenen Änderungen (PowerShell im Tool-Ordner):

```powershell
git add -A
git commit -m "Kurz beschreiben, was sich geändert hat"
git push
```

Nicht im Repository (siehe `.gitignore`): Beispiel-PDF in `reference/`, Chat-Zusammenfassungen,
Transkripte – also keine Kundendaten.

## Was es macht

1. **Vor dem Termin:** sammelt alles Bekannte in `kickoff/kickoff_brief.json` im Projekt (aus
   `project_brief.json`, falls vorhanden, sonst aus Plattformdaten, Modell und Unterlagen) und baut daraus
   das Kick-off-Deck für den Kunden.
2. **Nach dem Termin:** Claude trägt die Antworten aus dem Transkript in `kickoff_brief.json` ein, das Tool
   baut das korrigierte Deck zum Versenden und das Protokoll.
3. **Übergabe (nur bei Bedarf):** gibt es noch kein `project_brief.json`, landet `kickoff_brief` in
   `02_transcripts/`. Die Baseline-Definition (Runbook 01) liest es dort mit ein.

## Ergebnis (`kickoff/out/` im Projekt)

| Datei | wofür |
|---|---|
| `JJJJ-MM-TT_HHMM_Kick-off-Deck.html` | **zum Präsentieren**: funktioniert ohne Internet, 3D-Modell und Anlagenschema interaktiv |
| `…_Kick-off-Deck.pdf` / `.pptx` | zum Versenden / Bearbeiten: „Raummodell“ zeigt die Grundrisse aller Geschosse nach Nutzung (gleiche Geschosse zusammengefasst), „Anlagen“ immer die Anlagenliste mit Kenngrößen – unabhängig davon, ob der Kunde einen Viewer hat |
| `…_Kick-off-Protokoll.md` / `.pdf` | nach dem Termin |

**3D-Modell und Anlagen** kommen aus dem installierten Modell-Viewer (`optimuse-viewer`): gleiches
Anlagenschema mit Zoom und Klick auf Komponenten, im 3D-Modell die gleichen Raumdaten (Sollwerte,
Lüftung, Lasten, U-Werte) plus Laubengang/Verschattung. Das gilt für die HTML-Fassung. Ist der Viewer
nicht installiert, zeigt auch die HTML auf „Anlagen“ die Liste.

## Ordner

| Ordner | Inhalt |
|---|---|
| `Kickoff_starten.bat`, `launcher/` | Start per Doppelklick |
| `CLAUDE.md` | Anleitung für Claude, wenn nur der Pfad genannt wird |
| `kickoff.py` | Befehle: init, status, stage, build, protocol, handover |
| `kickoff_lib/` | Programm (Datenmodell, Einlesen, Folien, Grafiken, Protokoll, Viewer-Anbindung) |
| `runbook/kickoff.md` | genauer Ablauf für Claude |
| `templates/` | Leistungsumfang je Produkt, 3D-Viewer |
| `reference/` | freigegebene Vorlage des Decks |
| `vendor/` | Plotly, three.js, Schrift Inter (damit das Deck ohne Internet läuft) |

Aussehen: kommt aus deckkit (Skill `optimuse-slides` im Projekt), also dieselben Bausteine wie die
Endpräsentation.
