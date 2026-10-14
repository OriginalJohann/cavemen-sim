# Cavemen – Ice-Age Tribe Simulation

Eine taktweise, deterministische Survival-Simulation eines Höhlenmenschen-Stamms im
Eiszeitalter. Die Welt wird prozedural erzeugt (See, Wald, Hügel, Höhle), die Agents
(mit Namen, Eigenschaften, Alter und individuellen Prompts) entscheiden jede Stunde
(Logik-Tick), was sie tun: Beeren sammeln, Tiere jagen, am Ufer fischen, wandern, sich
fortpflanzen oder ruhen.

## Was kann die App?

- **LLM-gesteuerte Agents (optional):** Entscheidungen laufen über einen beliebigen
  OpenAI-kompatiblen `/chat/completions`-Endpunkt (z. B. LM-Studio). Ist kein Endpoint
  erreichbar, fällt jede Entscheidung deterministisch auf `llm/fallback.py` zurück –
  die Simulation crasht oder blockt nie und läuft komplett offline.
- **Prozedurale Welt:** Seed-basierte Kachelwelt mit Höhle, Wäldern, Wasserseen, Beerenbüschen
  und Wild (Mammut, Höhlenbär, Wolf, Triceratops) sowie Fischen im See (Drift + Flucht).
- **Survival-Mechanik:** Hunger/Stamina/HP-Wertungen, Wetterzyklus (kalt/sanft/heiß/Regen/Sturm),
  Alterung, Fortpflanzung mit Geburts-Coldown und Tod.
- **Interaktion & Story:** Agents unterhalten sich per Sprechblasen (deterministisch oder via LLM);
  die Kamera folgt dem Stamm in einem Top-Down-Pixelart-Renderer (Pygame).
- **Dauerhaftes World-Slots-System:** bis zu drei Welten werden automatisch als JSON in
  `~/cavemen_welten/` gespeichert (Autosave + manueller Save per F5); die GUI beginnt mit
  einem Menü (Welt neu anlegen / laden / überschreiben) und optional einer Setup-Seite,
  auf der Agenten-Roster (Name/Geschlecht/Alter/Prompt) manuell vorgegeben werden.

## Voraussetzungen

- Python ≥ 3.10
- `pygame` **und** `pyyaml` (alternativ pygame-ce – drop-in-kompatibel)
- NixOS: `flake.nix` / `shell.nix` liefern die komplette Umgebung ohne manuelle Installation

## Starten

### Schnellstart (empfohlen, auch auf NixOS)

```bash
./install.sh            # prüft Python+Deps, legt ggf. .venv/ an und startet die GUI
```

Das Script übergibt zusätzliche Argumente direkt an die App weiter, z. B.:

```bash
./install.sh --headless 300     # ohne GUI: 300 Ticks, JSON-Snapshots auf stdout
```

### Manuell (ohne Nix)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pygame pyyaml
python -m cavemen            # aus dem Repo-Root ausführen; config.yaml wird von dort gelesen
```

### NixOS

```bash
nix shell .                     # interaktive Umgebungs-Shell
nix run .#cavemen               # direkt die Simulation starten (GUI-Default)
nix run .#cavemen -- --headless 300   # CLI-Args an die App weitergeben ("--"-Trenner nötig!)
```

Beide Kommandos aus dem **Repo-Root** ausführen – `config.yaml` und das Sim-Paket werden von dort geladen.

## Kommandozeilen-Optionen (`python -m cavemen`)

| Option | Bedeutung |
|---|---|
| `--config PATH` | Pfad zur Config (Default: `config.yaml` im Arbeitsverzeichnis) |
| `--headless TICKS` | Lauft N Ticks ohne GUI und beendet sich; druckt JSON-Reports pro Phase (ideal für Tests/Demos) |
| `--no-llm` | LLM-Endpoint komplett deaktivieren (nur Fallback-Logik) |
| `--debug-llm` | Druckt die rohe LLM-Antwort jedes Urzeitmenschen pro Entscheidung im Terminal aus (`[LLM-Debug] Name: Antwort -> Aktion`) – nützlich zum Debuggen von Prompts/Timeouts |

## Steuerung in der GUI

| Taste | Funktion |
|---|---|
| ENTER | Auswahl im Welt-Menü / Setup bestätigen, Simulation starten |
| ESC | Menü verlassen bzw. App beenden |
| ESC | Pause-Menü in der Simulation (pausiert): Weiter / Welt speichern & Hauptmenü / Prompts bearbeiten (modaler Prompt-Editor) |
| Hauptmenü → „Edit settings" (ENTER = speichern) | Globales Settings-Menü: zentrale `config.yaml`-Werte in der GUI bearbeiten; ESC bricht ab. Der In-Place-Save behält Kommentare und Zeilenreihenfolge bei. |
| F5 | Manueller World-Save in den aktuellen Slot |

## Konfiguration & weitere Doku

Alle Schwellwerte (Stammgröße, Beeren-/Fisch-Ertrag, Tier-Aggro, LLM-Endpoint, Wettergewichte …)
stehen zentral in **`config.yaml`** im Repo-Root; jede Menge hat einen Default in `cavemen/config.py`.
Vertiefte Architektur-Doku: [`STRUCTURE.md`](STRUCTURE.md) · Projektregeln: [`AGENTS.md`](AGENTS.md).

## Tests

```bash
python -m unittest discover -s tests   # 38 Tests: Welt, Save/Load, Regeln, Beeren, Fischfang, Konversationen/Prompt-Editor, LLM-Client (/v1-Fallback) inkl. Tick-Budget + --debug-llm, Config-Editor & -Persistence, Pause-Menü
```
