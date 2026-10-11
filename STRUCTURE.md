# Cavemen – Projektstruktur

Höhlenmenschen-KI-Simulation: taktweise deterministische Survival-Simulation
mit LLM-gesteuerten Agenten (OpenAI-kompatible API), prozeduraler Welt und
Pygame-GUI im Top-Down-Pixelart-Stil. Läuft ohne LLM komplett im Fallback.

## Architektur-Prinzip
Deterministische Simulationslogik ist strikt von der asynchronen LLM-Kommunikation
getrennt: `simulation/` kennt nur die Schnittstelle „LLM liefert eine validierte
Action oder None“. Jede Fehlersituation (Timeout, ungültige Antwort, Offline)
fällt auf `llm/fallback.py` zurück – die Simulation crashet nie und blockt nie
(LLMClient trägt einen Offline-Latch nach dem ersten kompletten Timeout).

## Verzeichnisübersicht
```
cavemen/
├── __init__.py            Paketmarker
├── __main__.py            Einstieg: CLI (GUI-Default, --headless N, --no-llm)
├── config.py              Config-Klasse: config.yaml + eingebauten Defaults
│                          (wichtige Schwellwerte sind hier dupliziert, damit das
│                          Spiel auch ohne yaml startet)
simulation/
├── game_loop.py           Simulation: Welt-Erzeugung, Stamms-Init (LLM-Charaktere),
│                          tick()-Lauf, headless-Runner, Snapshots
└── rules.py               Deterministische Tick-Regeln: Hunger/Stamina/HP,
                           Bewegung, Jagd/Treffer, Wettereffekte, Alterung,
                           Tod/Nachwuchs (Stamm ≤ max_agents), Tier-Bestockung
└── conversations.py       Agenten-Konversation (Sprechblasen): deterministische Dialog-Pools via
                           seeded world-rng, optional LLM-Zeilen, Distanz/Cooldown/Bubble-Dauer
                           via `agents.conversation.*` in config.yaml
world/
├── generation.py          Prozedurale Welt (Seed): Tiles, Höhle, Wald/Wasser/Hügel
│                          + World-Serialisierung (to_dict/from_dict)
└── save_load.py           JSON-Saves in ~/cavemen_welten/ (config: worlds.save_dir),
                           max. 3 Slots, Überschreiben nur mit force=True
agents/
├── agent.py               Agent-Datenobjekt: Vitals, Alter, Story-Log,
                           age_years(), prompt-Warteschlange
└── prompts.py             Init-Prompt (hart < 100 Zeichen) + laufzeit-adaptive
                           Prompts (ebenfalls längenbegrenzt)
animals/
├── animals.py             Prozedurale Tiere/Saurier (Mammut, Höhlenbär, Wolf,
│                          Triceratops): Wanderung/Flucht/Gegnerangriffe via Regeln
└── weather.py             Wetter- und Tageszyklus mit Effektfaktoren
llm/
├── client.py              OpenAI-kompatibler /chat/completions-Client (urllib),
│                          Timeout/Retry, JSON-Validierung der Actions,
│                          Offline-Latch (_offline)
└── fallback.py            Deterministische Agenten-Entscheidung ohne LLM:
                           Ruhe bei Erschöpfung+Satt, Jagd auf Beute in Radius,
                           sonst Bewegung zu Nahrung/Schutz
gui/
├── app.py                 App-Loop: Zustände Menü → Setup (nur bei neuer/überschriebener Welt)
│                          → Sim; Takt-Pacing, Autosave alle N Ticks + F5-Manuallsave
├── setup.py               Manuelle Stamms-Erstellung (WorldSetup): 4-Spalten-Formular
│                          Name/Geschlecht/Alter/Prompt + Anzahl-/Start-Zeile; deterministisch
│                          vorausgefüllt, harte Grenzen erst bei Bestätigung, Roster an Sim
├── prompt_editor.py       Modaler Laufzeit-Prompt-Editor (Taste E in der Sim): pausiert die
│                          Sim, live-Schreibzugriff auf agent.prompt mit clip()-Hardcap
├── menu.py                Menü Welt-Auswahl (neue/laden/überschreiben; ENTER=bestätigen)
├── renderer.py            Top-Down-Pixelart-Rendering: Tiles inkl. Beeren-Punkte, Tiere,
│                          Agenten, Sprechblasen über sprechenden Agenten, Kamera-Follow
└── hud.py                 HUD: Welt-Leiste (inkl. "Beeren") + Agent-Panel
```

## Laufzeit-Pfade
1. **GUI**: `python -m cavemen` → `gui/app.py run(cfg)`: Menü (Slot 1–3:
   neue Welt / laden / explizit überschreiben; ENTER=Start, ESC=Beenden); für
   neue/überschriebene Welten dazwischen den Setup-Bildschirm (`gui/setup.py`:
   Name/Geschlecht/Alter/Prompt je Agent vorausgefüllt, ENTER startet die Sim),
   dann Sim-Schleife mit Takt-Pacing, Autosave alle N Ticks + F5-Manuallsave; Taste E öffnet
   während der Simulation einen modalen Prompt-Editor (`gui/prompt_editor.py`, Sim pausiert);
   Renderer (Kamera folgt dem Stamm) inkl. Sprechblasen über sprechenden Agenten
   (`simulation/conversations.py`) + HUD (Welt-Leiste + Agent-Panel).
2. **Headless**: `python -m cavemen --headless TICKS [--no-llm]` → periodische
   Snapshot-Zeilen auf stdout (Tests/Demo, kein GUI-Bildschirm nötig).
3. **LLM-Schleife pro Tick**: für jede fällige Entscheidung ruft die Sim den
   Client ab; ungültige/fehlende Antwort → Fallbackregel. Charakter-Erzeugung
   beim Neustart nutzt denselben Pfad (Name/Trait ≤ 8/12 Zeichen).

## Konfiguration
`config.yaml` im Repo-Root (wird von `cavemen/config.py` gelesen, Pfade relativ
zum Prozess-CWD). Kernschalter: `simulation.max_agents` (Stammgröße ≤ 10),
`animals.types.*.speed/aggro_chance/hunt_damage`, `llm.base_url/model/timeout_s/
max_retries/max_tokens`, `worlds.gather.*` (Beerensäume: max_menge/ertrag/regrow_ticks),
`agents.conversation.*` (Sprechblasen: Distanz/Cooldown/Bubble-Dauer/use_llm),
`worlds.save_dir/max_worlds`, `gui.sim.llm`. Alle
Werte haben Defaults in `config.py`; die yaml kann jede Menge überschreiben.

## Tests & Entwicklung
- `tests/test_core.py` – unittest-Suite (Welt-Erzeugung, Save/Load-Roundtrip,
  Regeln/Stabilität headless, Beerensammeln (Ernte/Nachwuchs/Determinismus),
  Roster-Spawn (Phase 9), Konversationen/Sprechblasen + Laufzeit-Prompt-Editor (Phase 10),
  LLM-Client-Fallback). Aufruf:
  `python -m unittest discover -s tests`.
- NixOS: `flake.nix` + `shell.nix` liefern Python+SDL-Umgebung;
  `install.sh` prüft → richtet ein → startet (robust, nicht interaktiv).

## Bekannte Randbedingungen / Entscheidungen
- Pygame-Wheel für neuere Pythons kann fehlen; pygame-ce ist drop-in-kompatibel
  (in der tmp-Venv-Umgebung mit pygame-ce 2.5.8 verifiziert).
- Balancierung: gemessenes Verhalten (Headless, deterministischer Seed "headless"/Slot 0): der
  Stamm reduziert sich durch Tierattacken deutlich; ohne Fortpflanzungserholung (Geburts-Coldown
  von 6 Monaten ist zu langsam, wenn nur noch ein Geschlecht überlebt) kann um Tick ~1250 das
  Aussterben eintreten. Frühere "3000-Tick-Stabilität" gilt damit nicht mehr als allgemeine
  Garantie; Balancierung (z. B. Tier-Aggro/Cooldowns/Ertrag) ist ein offener, bewusst nicht in Phase
  10 erledigter Punkt – INSTRUCTIONS.md verlangt kein Überlebensziel für den Stamm.
