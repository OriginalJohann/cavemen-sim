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
application/
├── __init__.py            Paketmarker
├── __main__.py            Einstieg: CLI (GUI-Default, --headless N, --no-llm, --debug-llm)
├── config.py              Config-Klasse: config.yaml + eingebauten Defaults
│                          (Schwellwerte dupliziert, damit das Spiel auch ohne yaml startet)
│                          update_config_values(): In-Place-YAML-Save für Zwei-Level-Keys,
│                          behält Kommentare/Reihenfolge, Read-back-Check, ConfigError
simulation/
├── game_loop.py           Simulation: Welt-Erzeugung, Stamms-Init (LLM-Charaktere),
│                          tick()-Lauf, headless-Runner, Snapshots
└── rules.py               Deterministische Tick-Regeln: Hunger/Stamina/HP,
                           Bewegung, Jagd/Treffer, Wettereffekte, Alterung,
                           Tod/Nachwuchs (Stamm ≤ max_agents), Tier-Bestockung, Fisch-Action am Ufer
                           (agents.fishing.*); LLM-Pacing: max. llm.decisions_per_tick Netzwerk-Calls pro Tick
                           (aufgeschobene Agents behalten ihren Plan und versuchen es im nächsten Tick);
                           --debug-llm druckt [LLM-Debug]-Zeilen mit der rohen Antwort je Agent auf stdout
└── conversations.py       Agenten-Konversation (Sprechblasen): deterministische Dialog-Pools via
                           seeded world-rng, optional LLM-Zeilen, Distanz/Cooldown/Bubble-Dauer
                           via `agents.conversation.*` in config.yaml; Nahrungsquellen-Info-Austausch:
                           nächste Beerensaum im konfigurierbaren Radius als Richtung + Entfernung
                           (food_radius_tiles / food_hint_hunger_below / food_hint_chance), rein anzeigetechnisch
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
                            Triceratops, Fisch): Wanderung/Flucht/Gegnerangriffe; Fisch driftet im See und flieht vor Agenten
└── weather.py             Wetter- und Tageszyklus mit Effektfaktoren
llm/
├── client.py              OpenAI-kompatibler /chat/completions-Client (urllib), mit
│                          Auto-Fallback auf `/v1` im base_url (LM-Studio-Quirk); Timeout (30 s Default)/Retry,
│                          JSON-Validierung der Actions, Offline-Latch (_offline), _last_raw_text hält die
│                          rohe Modell-Antwort für das [LLM-Debug]-Output bereit
└── fallback.py            Deterministische Agenten-Entscheidung ohne LLM:
                           Ruhe bei Erschöpfung+Satt, Jagd auf Beute in Radius,
                            Fisch am Seeufer wenn hungrig ohne Beerenziel, sonst Weg zur Nahrungs-/Sicherheitsquelle
gui/
├── app.py                 App-Loop: Zustände Menü → Setup (nur bei neuer/überschriebener Welt)
│                          → Sim; Takt-Pacing, Autosave alle N Ticks + F5-Manuallsave
├── setup.py               Manuelle Stamms-Erstellung (WorldSetup): 4-Spalten-Formular
│                          Name/Geschlecht/Alter/Prompt + Anzahl-/Start-Zeile; deterministisch
│                          vorausgefüllt, harte Grenzen erst bei Bestätigung;
│                          Phase 15: vertikales Scrollen der Zeilenliste (Mausrad) mit Clamping, Auto-Scroll des
│                          aktiven Felds bei Pfeil-/TAB-Navigation und Maus-Hit-Test inkl. Scroll-Versatz
├── prompt_editor.py       Modaler Laufzeit-Prompt-Editor (über das Pause-Menü): pausiert die Sim;
│                          Phase 15 zweistufig – Stufe 1 scrollbare Namensliste (Pfeile/Maus), ENTER/Klick öffnet Stufe 2:
│                          großes Eingabefeld für genau einen Agenten mit umgebrochenem Prompt und vertikalem Scrollen
│                          (Mausrad/PAGEUP-PAGEDOWN/Pfeile, geclampt); live-Schreibzugriff auf agent.prompt
│                          mit clip()-Hardcap; ESC-Hierarchie: Editor -> Namensliste, Liste -> vollständig schließen
├── pause_menu.py          ESC-Pause-Menü während der Simulation (Taste ESC; Sim pausiert)
│                          Weiter / Welt speichern & Hauptmenü / modaler Prompt-Editor öffnen
├── config_editor.py       Modales globales Settings-Menü (Hauptmenü → „Edit settings"):
│                          15 editierbare Werte (inkl. llm.decisions_per_tick) mit Typ-/Bereichs-/URL-Validierung,
│                          ENTER=In-Place-Save via update_config_values(), ESC=abbrechen
├── menu.py                Menü Welt-Auswahl (neue/laden/überschreiben; ENTER=bestätigen)
├── renderer.py            Top-Down-Pixelart-Rendering: Tiles inkl. Beeren-Punkte, Tiere,
│                          Agenten, Sprechblasen über sprechenden Agenten, Kamera-Follow; Welt-Viewport-Versatz via offset_x (linke Sidebar)
└── hud.py                 Fixed linke Sidebar (Weltinfos zeilenweise + Agentenliste); draw_side_panel, Breite via side_panel_width(); Phase 15: eigene Zeile pro HP/STA/HUNGER-Balken (vitals_bar_geometry(); Balken hinter dem breitestem Label), Rendering geclampt am unteren Sidebar-Rand; Prompt-Anzeige entfernt (läuft über Pause-Menü -> Prompt-Editor)
```

## Laufzeit-Pfade
1. **GUI**: `python -m application` → `gui/app.py run(cfg)`: Menü (Slot 1–3:
   neue Welt / laden / explizit überschreiben; ENTER=Start, ESC=Beenden); für
   neue/überschriebene Welten dazwischen den Setup-Bildschirm (`gui/setup.py`:
   Name/Geschlecht/Alter/Prompt je Agent vorausgefüllt, ENTER startet die Sim; Phase 15: Zeilenliste scrollt per Mausrad, Auto-Scroll des aktiven Felds bei Navigation),
   dann Sim-Schleife mit Takt-Pacing, Autosave alle N Ticks + F5-Manuallsave; ESC öffnet in der Simulation ein Pause-Menü
   (`gui/pause_menu.py`; Sim pausiert): Weiter / Welt speichern & Hauptmenü / modaler Prompt-Editor (`gui/prompt_editor.py`) für Live-Prompt-Edition;
   Hauptmenü → „Edit settings" öffnet das globale Settings-Menü (`gui/config_editor.py`),
   ENTER speichert In-Place in config.yaml (Kommentare bleiben erhalten), ESC bricht ab;
   Renderer (Kamera folgt dem Stamm) inkl. Sprechblasen über sprechenden Agenten
   (`simulation/conversations.py`) + fixed linke Sidebar für Weltinfos & Agenten (gui.side_panel_w, Default 300 px); Canvas wird rechts versetzt gezeichnet.
2. **Headless**: `python -m application --headless TICKS [--no-llm] [--debug-llm]` → periodische
   Snapshot-Zeilen auf stdout (Tests/Demo, kein GUI-Bildschirm nötig).
3. **LLM-Schleife pro Tick**: für jede fällige Entscheidung ruft die Sim den
   Client ab; ungültige/fehlende Antwort → Fallbackregel. Charakter-Erzeugung
   beim Neustart nutzt denselben Pfad (Name/Trait ≤ 8/12 Zeichen).

## Konfiguration
`config.yaml` im Repo-Root (wird von `application/config.py` gelesen, Pfade relativ
zum Prozess-CWD). Kernschalter: `simulation.max_agents` (Stammgröße ≤ 10),
`animals.types.*.speed/aggro_chance/hunt_damage`, `llm.base_url/model/timeout_s (30 s)/
max_retries/max_tokens/decisions_per_tick (LLM-Netzwerk-Calls pro Tick)`, `worlds.gather.*` (Beerensäume: max_menge/ertrag/regrow_ticks),
`agents.conversation.*` (Sprechblasen: Distanz/Cooldown/Bubble-Dauer/use_llm, Food-Hints: food_radius_tiles/food_hint_hunger_below/food_hint_chance), agents.fishing.* (Fischfang am Seeufer: Chance/Ertrag/Cooldown),
`worlds.save_dir/max_worlds`, `gui.sim.llm`. Alle
Werte haben Defaults in `config.py`; die yaml kann jede Menge überschreiben.

## Tests & Entwicklung
- `tests/test_core.py` – unittest-Suite (Welt-Erzeugung, Save/Load-Roundtrip,
  Regeln/Stabilität headless, Beerensammeln (Ernte/Nachwuchs/Determinismus),
  Roster-Spawn (Phase 9), Konversationen/Sprechblasen + Laufzeit-Prompt-Editor (Phase 10), Pause-Menü (ESC, Phase 12),
  LLM-Client-Fallback, Fishing-Suite (Spawn/Drift/Fallback-Entscheidung/Hunger-Wiederherstellung/Cooldown), Phase-15-GUI-Fixes (Vitals-Balken-Geometrie ohne Overlap + Sidebar-Rand-Clamping,
   Setup-Scroll: Wheel-Clamp/Auto-Scroll/Maus-Hit-Test mit Scroll-Versatz, zweistufiger Prompt-Editor inkl. Tipp nur im
   Editor-Stadium und Wheel/PAGEUP-PAGEDOWN-Clamp)). Aufruf:
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
