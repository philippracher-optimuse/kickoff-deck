# Kick-off tool - start script (called by Kickoff_starten.bat).
# Asks for the project folder, then either starts Claude in that project with the kick-off
# instructions (recommended) or only rebuilds the deck from kickoff_brief.json.
param([string]$Project = "")

$ErrorActionPreference = "Stop"
$TOOL = Split-Path -Parent $PSScriptRoot
Write-Host ""
Write-Host "  OPTIMUSE Kick-off-Tool" -ForegroundColor Cyan
Write-Host "  ----------------------"

# -- 1. project folder -----------------------------------------------------------
if (-not $Project) {
    Write-Host ""
    Write-Host "  Projektordner eingeben (z.B. $HOME\Documents\Projekte\mein-projekt)"
    $Project = Read-Host "  oder einfach Enter druecken fuer ein Auswahlfenster"
}
$Project = $Project.Trim().Trim('"')
if (-not $Project) {
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = "Projektordner fuer den Kick-off waehlen"
    $dlg.SelectedPath = (Join-Path $HOME "Documents\Projekte")
    if ($dlg.ShowDialog() -ne "OK") { Write-Host "  Abgebrochen."; exit 1 }
    $Project = $dlg.SelectedPath
}
if (-not (Test-Path -LiteralPath $Project -PathType Container)) {
    Write-Host "  Ordner nicht gefunden: $Project" -ForegroundColor Red; exit 1
}
$Project = (Resolve-Path -LiteralPath $Project).Path
Write-Host "  Projekt: $Project" -ForegroundColor Green

# -- 2. what to do ---------------------------------------------------------------
$brief = Join-Path $Project "kickoff\kickoff_brief.json"
Write-Host ""
Write-Host "  Was moechtest du tun?"
Write-Host "   [1] Vor dem Termin: mit Claude vorbereiten (Unterlagen lesen, Deck bauen)  <- empfohlen"
Write-Host "   [2] Nach dem Termin: mit Claude Transkript einarbeiten (Deck + Protokoll)"
Write-Host "   [3] Nur das Deck neu bauen (ohne Claude, aus kickoff_brief.json)"
$choice = Read-Host "  Auswahl (1/2/3)"

$product = ""
if ($choice -eq "1" -and -not (Test-Path -LiteralPath $brief)) {
    Write-Host ""
    Write-Host "  Gebuchtes Produkt:  [1] Energy Design   [2] Value Engineering   [3] Energy Performance Analytics"
    $p = Read-Host "  Auswahl (1/2/3, Enter = Energy Design)"
    if ($p -eq "2") { $product = "Value Engineering" }
    elseif ($p -eq "3") { $product = "Energy Performance Analytics" }
    else { $product = "Energy Design" }
}

# -- 3a. with Claude -------------------------------------------------------------
if ($choice -eq "1" -or $choice -eq "2") {
    $claude = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $claude) {
        Write-Host "  Claude (Befehl 'claude') nicht gefunden. Ich baue nur das Deck (wie Option 3)." -ForegroundColor Yellow
        $choice = "3"
    } else {
        if ($choice -eq "1") {
            $task = "vor dem Termin (Schritt K1 und K2)"
            if ($product) { $task += ", Produkt: $product" }
        } else {
            $task = "nach dem Termin (Schritt K3): das Transkript liegt in kickoff\ oder 02_transcripts\"
        }
        $prompt = "Kick-off-Tool: $TOOL - lies $TOOL\CLAUDE.md und fuehre den Kick-off fuer dieses Projekt aus, $task."
        Write-Host ""
        Write-Host "  Starte Claude im Projektordner ..." -ForegroundColor Cyan
        Set-Location -LiteralPath $Project
        & claude $prompt
        exit $LASTEXITCODE
    }
}

# -- 3b. deck only (no Claude) -----------------------------------------------------
if ($choice -ne "3") { Write-Host "  Unbekannte Auswahl." -ForegroundColor Red; exit 1 }
$venvPy = Join-Path $Project ".venv\Scripts\python.exe"
$kick = Join-Path $TOOL "kickoff.py"
function Run-Kickoff([string[]]$a) {
    if (Test-Path -LiteralPath $venvPy) { & $venvPy $kick @a }
    elseif (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv run --directory $Project --with playwright --with python-pptx --with matplotlib python $kick @a
    } else { Write-Host "  Kein Python gefunden (.venv im Projekt oder uv)." -ForegroundColor Red; exit 1 }
    if ($LASTEXITCODE -ne 0) { Write-Host "  Fehler (Code $LASTEXITCODE)." -ForegroundColor Red; exit $LASTEXITCODE }
}
if (-not (Test-Path -LiteralPath $brief)) {
    Write-Host "  Noch kein kickoff_brief.json - lege es aus den Projektdaten an (ohne AI-Ergaenzungen)."
    $initArgs = @("init", $Project)
    if ($product) { $initArgs += @("--product", $product) }
    Run-Kickoff $initArgs
}
Write-Host "  Baue das Deck (HTML + PDF + PPTX) ..." -ForegroundColor Cyan
Run-Kickoff @("build", $Project, "--export")
$out = Join-Path $Project "kickoff\out"
Write-Host ""
Write-Host "  Fertig. Ordner: $out" -ForegroundColor Green
Start-Process explorer.exe $out
