# Umsetzungsplan: Höhlenmenschen-KI-Simulation

Statuslegende: [ ] offen | [/] in Arbeit | [x] fertig

## 1. Technologieentscheidung (bestätigt)
- Python 3 + pygame (SDL2) für GUI; urllib/httpx-kompatibel für LLM;
  OpenAI-kompatible API (lokal: LM-Studio, extern beliebig).
- Deterministische Simulation (Regeln), LLM nur für Agenten-Entscheidungen.
  LLM-Fallback: Simulation läuft ohne Endpunkt weiter (Offline-Latch im Client).
- NixOS via `flake.nix` / `shell.nix`; Single-Script-Installation `install.sh`.

## 2. Zielstruktur
```
cavemen/            Python-Paket (Details siehe STRUCTURE.md)
├── __main__.py     Einstieg + CLI (--headless N --no-llm)
├── config.py       zentrale Konfiguration (config.yaml + Defaults)
├── simulation/     game_loop.py, rules.py
├── world/          generation.py, save_load.py  (max. 3 Slots)
├── agents/         agent.py, prompts.py        (Prompt <= 100 Zeichen)
├── animals/        tier/saurier prozedural + Wetter
├── llm/            client.py, fallback.py
└── gui/            menu.py, renderer.py, hud.py
flake.nix / shell.nix / install.sh / config.yaml / STRUCTURE.md
```

## 3. Phasen & Aufgaben (alle fertig – siehe Fortschrittsprotokoll)
### Phase 0 – Fundament
- [x] P0.1 Plan-Dokument anlegen (dieses File)
- [x] P0.2 flake.nix + shell.nix
- [x] P0.3 install.sh (prüfen -> einrichten -> starten, robust)
- [x] P0.4 Projektgerüst + config.yaml
- [x] P0.5 STRUCTURE.md
### Phase 1 – Konfiguration & LLM
- [x] P1.1 config.py (Schwellwerte; Defaults spiegeln config.yaml)
- [x] P1.2 llm/client.py (OpenAI-kompatibel, Timeout/Retry + Offline-Latch)
- [x] P1.3 llm/fallback.py (deterministisches Verhalten ohne LLM)
### Phase 2 – Welt & Speicher
- [x] P2.1 world/generation.py (prozedural, Seed, Höhle, Vegetation, Wasser)
- [x] P2.2 world/save_load.py (JSON, 3 Slots, Überschreib-Schutz via force-Flag)
### Phase 3 – Agenten
- [x] P3.1 agent.py (HP/Stamina/Hunger/Alter, Lebensgeschichte-Profil)
- [x] P3.2 prompts.py (Init-Prompt <=100 Zeichen, Laufzeit-Anpassung)
- [x] P3.3 pro-Tick LLM-Entscheidungen + Validierung/Fallback
### Phase 4 – Nicht-KI-Akteure & Umwelt
- [x] P4.1 animals/ (Mammut, Höhlenbär, Wolf, Triceratops; Regeln nur)
- [x] P4.2 weather.py (Wetterzyklus + Tageszeit, Effekte)
### Phase 5 – Reproduktion & Stammregeln
- [x] P5.1 rules.py (Nachwuchs wenn <10 im Altersfenster, Tod)
### Phase 6 – GUI
- [x] P6.1 renderer.py (Top-Down, Pixelart ~16px, Kamera-Follow auf den Stamm)
- [x] P6.2 menu.py (Neue Welt / Laden / explizites Überschreiben / Beenden; ENTER=Bestätigen)
- [x] P6.3 hud.py (Agent-Panel + Welt-Leiste)
### Phase 7 – Integration & Tests
- [x] P7.1 Unit-/Smoke-Tests headless (tests/test_core.py, unittest grün)
- [x] P7.2 End-to-end ohne LLM (Fallback) verifiziert: Headless 600 + 3000 Ticks stabil
- [x] P7.3 Save/Load-Roundtrip (inkl. GUI-Autosave im Smoke-Test, tick-600-State valid)
- [ ] P7.4 tmp/-Cleanup **nach** Nutzer-Bestätigung des Commits (steht noch aus)

## 4. Annahmen (bestätigt vom Nutzer, siehe Chat)
1. Default-LLM: LM-Studio `http://127.0.0.1:1234/v1`, Modell in config.yaml.
2. Simulation taktweise; LLM blockt die Sim nie (Offline-Latch im Client).
3. Saurier als prozedurale Kreaturen im Tierregelsystem.
4. Welten-Speicher: `~/cavemen_welten/` (konfigurierbar via config.yaml).
5. Python >= 3.10, pygame via Nix/pip (in tmp-Venv mit pygame-ce 2.5.8 getestet).

## 5. Fortschrittsprotokoll
- Phase 0–7 implementiert; alle Dateien existieren und sind lauffähig.
- Balancierung final: Tier-Cap 12→26 (config.yaml + Defaults), Tierspeeds runter
  (Mammut .3→.2, Bär .4→.25, Wolf .7→.45, Triceratops .5→.3), Jagd-Ertrag
  +25→+30 Sättigung pro Treffer, Beute-Suchradius im Fallback 15→48 Tiles,
  Ruhe-Bedingung Hunger≥60→Hunger≥80 (Jagd wird nicht unterbrochen),
  Startherde 4→8 Tiere. Ergebnis: Stamm stabil über 3000 Ticks (7–9 von ≤10
  überleben, kein Aussterben), Tierbestand konstant am Cap.
- Bugfixes GUI/LLM: Menü bekam ENTER/KP_ENTER/SPACE als Bestätigungstaste
  (vorher nur Maus) – ohne sie war das Starten per Tastatur unmöglich;
  LLMClient bekommt Offline-Latch (`_offline`): nach einem kompletten Timeout
  geben alle weiteren Calls sofort `None` zurück → Simulation blockt nie mehr,
  Fallback-Meldung erscheint genau einmal pro Prozess.
- Verifikation: unittest-Suite grün (T=0); headless `python -m cavemen --headless
  N --no-llm` stabil; GUI-E2E mit SDL_VIDEODRIVER=dummy: ENTER startet Simulation,
  Autosave schreibt gültiges world_1.json (tick 600), QUIT beendet sauber.
- Testumgebung: ./tmp/venv (Python 3.14 via Nix + pygame-ce); Smoke-/Debug-Skripte
  in ./tmp/gui_smoke.py, ./tmp/dbg.py, ./tmp/check_save.py – gehören zum tmp-Cleanup (P7.4).
- Phasen 8 & 9 implementiert und verifiziert (11.10.2026): Phase 8 = explizite Beerensäume
  (`worlds.gather.*` deterministisch in der Welt-Erzeugung, ~14 Büsche; Ernte +9 Sättigung,
  Regrowth ≈ 14 Tage; Renderer-Punkte, HUD "Beeren", Save/Load-Roundtrip und Unit-Tests);
  Phase 9 = manueller Stamms-Aufbau zwischen Menü und Simulation (`gui/setup.py`, WorldSetup):
  4 Spalten Name | Geschlecht | Alter | Prompt + Anzahl-/Start-Zeile, deterministisch
  vorausgefüllt; harte Grenzen erst bei Bestätigung (Name ≤ 8, Prompt via clip(), Alter geclampt
  auf [5..70]); `Simulation.new_world(..., roster=None)` + `_spawn_from_roster`, Legacy-Autopfad
  unverändert. Verifiziert: Unit-Suite grün, headless 600 Ticks stabil, GUI-Smoke geht sauber
  Menü → Setup → Simulation (SDL dummy driver) und beendet sich ohne Fehler.

## 6. Phase 8 – Beeren sammeln (implementiert & verifiziert; P8.5 optional offen)
- [x] P8.1 Ist-Analyse: `gather` existiert bereits als Aktion (+4 Sättigung/Tick auf
      Gras/Wald, Fallback zielt auf Wald-Tiles im Radius ~8); Grundfunktion erfüllt die
      Anforderung "Essen ohne jagen" aus INSTRUCTIONS.md.
- [x] P8.2 (Empfohlen) Explizite Beerensäume: prozedural deterministisch auf
      Wald-/Gras-Tiles, Menge pro Tile + Nachwuchs nach N Ticks; Config-Bereich
      `worlds.gather.*` (max_menge=5, ertrag +9 Sättigung pro Sammeln, regrow_ticks
      ≈ 14 Tage); ohne Beeren kleiner flacher Bonus (+2 statt +4).
- [x] P8.3 Fallback bevorzugt Beerensäume; Renderer zeichnet Beeren-Punkte auf den
      Tile-Kacheln; HUD Welt-Leiste zeigt "Beeren: N"; Save/Load-Roundtrip + Unit-Tests
      (Ernte, Nachwuchs, Determinismus).
- [x] P8.4 Headless-Revalidierung 600 Ticks nach Balancierung (Sammel-Faktor ist
      Stabilitätsstütze gegen Verhungern); 3000-Tick-Stabilität bereits Phase 7 belegt.
- [ ] P8.5 (Optional) Fischen an der Wasserfläche als zweite Nahrungsquelle
      (INSTRUCTIONS.md-Namensbeispiel "Beeren oder Fische").

## 7. Phase 9 – Manuelle Stamms-Erstellung im Menü (vom Nutzer angefordert)
- [x] P9.1 Anforderungsaufnahme: Anzahl + je Agent Name/Geschlecht/**Alter**/Prompt händisch,
      mit vorausgefüllten Vorschlägen; betrifft beide Erstellungs-Pfade
      ("Neue Welt" und explizites "Ueberschreiben"), nicht Laden. Final bestätigt vom Nutzer
      (09.10.2026): Alter wird ebenfalls selbst eingegeben, Setup gilt für beide Erstellungs-
      Pfade, 100-Zeichen-Prompt-Hardcap bleibt in Kraft.
- [x] P9.2 Neues Modul `cavemen/gui/setup.py` (Klasse WorldSetup) + GUI-State
      "setup" in `gui/app.py` zwischen Menü und Sim.
- [x] P9.3 Vorschläge ("voreingetragen"): pro Index i Geschlecht alternierend M/F,
      Name/Eigenschaft via LLM (`make_character`) wenn Endpunkt online, sonst
      deterministisch per Slot-Saatgut (fallback `pick_character`); Alter wird mit 16–34
      vorgeschlagen und ist wie alle Felder frei editierbar; Prompt-Vorfüllung via
      `make_initial_prompt(name, alter, geschlecht, eigenschaft, cap)` – Name/Geschlecht/
      Alter/Prompt sind vier unabhängig handbearbeitbare Felder (keine Auto-Sync).
- [x] P9.4 Eingabe-UX: Zeilen mit Spalten Name | Geschlecht | Alter | Prompt (+ Anzahl-Zeile
      und Start-Zeile); Zeilennavigation (Pfeile/Tab/Mausklick aktiviert Feld), Texteingabe
      über KEYDOWN-Unicode + Backspace, M/F-Umschalten im Geschlechtsfeld, Zifferneingabe
      fürs Alter; +- für Anzahl (1..max_agents_per_world; editierte Felder bleiben beim
      Vergrößern erhalten, neue Zeilen bekommen frische Vorschläge); harte Grenzen bei
      Bestätigung: Name ≤ 8 Zeichen, Prompt ≤ init_max_chars via clip(), Alter geclampt auf
      [agents.age.child_until_years .. agents.age.death_age_limit] (5..70 aus config.yaml),
      Anzeige "n/max" je Feld in der Hinweisleiste; ENTER auf Start-Zeile = bestätigen,
      ESC = zurück zum Menü.
- [x] P9.5 `Simulation.new_world(..., roster=None)` + `_spawn_from_roster(roster)`:
      exakt die eingegebenen Agenten (Name/Geschlecht/Prompt/Alter), Höhlen-Spots und
      Story-/Cooldown-Staggering wie bisher; Alter wird aus der Roster-Spec direkt in
      `age_ticks` (per_year-Umrechnung) überführt statt `rng.uniform(16, 34)` – das Clamping
      auf [5..70] erfolgt im Setup vor dem Spawn, die Sim-Regeln bleiben unangefochten;
      Legacy-Autopfad bleibt unverändert (Headless & Backward-Kompatibilität).
- [x] P9.6 Unit-Tests: Roster-Spawn respektiert Anzahl/Namen/Geschlechter/Age/Prompts,
      Clamping der Alter-Grenzen greift; bestehende Suite tangiert nicht.
- [x] P9.7 Doku: STRUCTURE.md (setup.py-Eintrag), Planstatus, Headless-Sanitylauf
      über neuen Roster-Pfad ohne Regression prüfen.

**Status Phase 9:** Implementiert & verifiziert (11.10.2026) – siehe Fortschrittsprotokoll.

## 8. Phase 10 – INSTRUCTIONS-Abgleich: Konversationen & Laufzeit-Prompt-Edit (11.10.2026)
Systematischer Abgleich von `INSTRUCTIONS.md` mit der Implementierung; alle übrigen Punkte
(NixOS/flake + install.sh, zentrale Config inkl. LLM-Endpunkt und konfigurierbarer Tickrate,
Höhlenstart, 3 Save-Slots, max. 10 Agenten, prozedurale Tiere/Wetter ohne KI, Fortpflanzung
Mann+Frau bei < 10 Mitgliedern mit parametrierbaren Schwellwerten, Essen ohne Jagen via Beeren,
Attribute + persistentes Profil, Init-Prompt ≤ 100 Zeichen inkl. manuell erstellbarem Roster mit
Vorschlägen (Phase 9), Sim-seitige Prompt-Anpassung, Menü/Agenten-Status/Welt-Infos/Top-Down)
sind bereits erfüllt. Zwei echte Lücken wurden geschlossen:
- [x] P10.1 Gap-Analyse INSTRUCTIONS.md vs. Code; fehlende Punkte identifiziert: inter-agentliche
      Konversationen mit Sprechblasen (§3 "Konversationen") und nutzerseitige Prompt-Anpassung zur
      Laufzeit (zweiter Halbsatz von §3 "Laufzeit-Anpassung"). Fischen bleibt bewusst optional
      (P8.5), da das Anforderungsbeispiel "z.B. Sammeln von Beeren oder Fischen" durch die Beeren
      bereits erfüllt ist.
- [x] P10.2 `simulation/conversations.py`: max. ein Agenten-Paar pro Tick innerhalb konfigurierbarer
      Manhattan-Distanz, Wahrscheinlichkeit/Cooldown/Bubble-Dauer via neuem Config-Bereich
      `agents.conversation.*` (config.yaml + Defaults); deterministische Dialog-Pools über den seeded
      world-rng (reprozierbar je Seed), optional LLM-generierte Zeilen (`use_llm`, neue Methode
      `LLMClient.conversation_line` mit Strict-JSON-Vertrag und graceful Fallback); Bubble-State ist
      transient am Agenten und wird bewusst nicht serialisiert.
- [x] P10.3 Renderer: Sprechblasen über sprechenden Agenten (Transparenz-Surface, Zeilenumbruch,
      Sichtfenster `bubble_ticks`), `draw_world(..., font=None)` rückwärts-kompatibel.
- [x] P10.4 GUI: `gui/prompt_editor.py` (Klasse PromptEditor) via Taste E im Sim-State; Simulation
      pausiert während der Bearbeitung; Live-Schreibzugriff auf `agent.prompt` mit clip()-Hardcap pro
      Tastenschlag (nie länger als init_max_chars); ESC/ENTER schließt, Änderungen sind sofort Teil des
      Weltzustands und reisen mit Autosaves.
- [x] P10.5 Verifikation: neue Unit-Tests (Konversation-Determinismus + Cooldown; Editor-Cap &
      Live-Edition) laufen grün; GUI-Smoke über kompletten Pfad inkl. Editor-Pause (Menü → Setup → Sim
      → E → ESC → QUIT). Headless-A/B-Lauf (Konversation an/aus): identisches Überlebensverhalten der
      Population → die Phase-10-Änderungen verändern die Survival-Balance nicht. Getrennt festgestellt:
      Beim deterministischen Seed "headless"/Slot 0 stirbt der Stamm durch Tierattacken bereits um
      Tick ~1250 aus (vorbestehende Balancierungseigenschaft, keine Phase-10-Wirkung) – als offener
      Punkt dokumentiert, da INSTRUCTIONS.md kein Überlebensziel verlangt. STRUCTURE.md + Plan aktualisiert.

## 9. Phase 11 – LLM-Pacing & Debug-Output (12.10.2026)
Ziel: Request-Pile-up beim LM-Studio-Endpunkt vermeiden und rohe LLM-Antworten im Terminal debuggen.
- [x] P11.1 `llm.decisions_per_tick` (Default 1, Config-Editor Bereich 1–32): pro Tick maximal N
      LLM-Netzwerk-Calls; aufgeschobene Agents behalten ihren letzten Plan und entscheiden im
      nächsten Tick (kein Stau von Requests am Endpunkt).
- [x] P11.2 Timeout Default 8 s → 30 s (`config.yaml` + Defaults); `LLMClient._last_raw_text` hält die
      rohe Modell-Antwort bereit (vor jedem Versuch neu initialisiert – kein Stale-Leak zwischen Agents).
- [x] P11.3 CLI-Flag `--debug-llm` (GUI und headless): druckt `[LLM-Debug] <Name>: <rohe Antwort> -> <Action>`
      je fälligem Agent auf stdout; Flag wird an Simulation/GUI durchgereicht (`gui/app.py run(cfg, llm_debug)`).
- [x] P11.4 Tests: neue `LLMPacingDebugTests` (Budget limitiert Calls/Tick, Config-Override greift live,
      Debug-Flag druckt die rohe Antwort je Agent via stdout-Capture); Suite 32 → 35 Tests, alle grün.
- [x] P11.5 LIVE-VERIFIKATION GELUNGEN (12.10.2026) via `nix run .#cavemen -- --headless 4 --debug-llm`
      (die Nix-Derivation läuft in einem eigenen Namespace, dort auflösbar; direkter Shell/Python-Zugriff
      auf den Workspace ist durch das FS-Overlay gestört: Name-Lookups auf älteren Inodes → ENOENT).
      Output bestätigt: [LLM-Debug]-Zeilen je fälligem Agent im Format "[LLM-Debug] <Name>: <raw> -> <action>",
      Tick-Budget greift live (Kaya tick 1, Grog verschoben auf späteren Tick), "(no reply from LLM)" bei
      nicht laufendem LM-Studio. Danach: Commit nach Nutzer-Bestätigung + tmp/-Cleanup.

## 10. Phase 12 – Pause-Menü (ESC) während der Simulation (12.10.2026)
Ziel: ESC öffnet in der laufenden Sim ein Pause-Menü; das Ticking wird pausiert. Vom Menü aus:
die Welt speichern und ins Hauptmenü zurückkehren, oder Prompts bearbeiten (alter Taste-E-Weg entfernt).
- [x] P12.1 Neues Modul `gui/pause_menu.py` (`PauseMenu`, Tastenkonventionen wie `menu.py`):
      Weiter / Welt speichern & Hauptmenü / Prompts der Cavemen bearbeiten; ESC=Weiter, ENTER/SPACE/Maus=Bestätigung.
- [x] P12.2 `gui/app.py`: Escape-Routing ersetzt "ESC beendet die App"; Prompt-Editor nur noch vom
      Pause-Menü erreichbar (Taste E entfernt); Ticking bei Editor UND Pause-Menü pausiert; speichern &
      Hauptmenü speichert explizit (SaveError-freundlich) und kehrt zurück inkl. Slotliste-Auffrischung.
- [x] P12.3 `gui/prompt_editor.py`: Docstring/Titel an den neuen Einstieg angepasst ("key E" entfernt).
- [x] P12.4 Tests: neue PauseMenuTests (Navigation/Wrap, ENTER/SPACE/Maus, ESC=resume); Suite 35→38.
      README-Tastentabelle/-Zähler und STRUCTURE.md (Baum + Ablauf) aktualisiert.
- [x] P12.5 Verifikation: Unit-Suite grün (38 Tests, 0.85 s, Exit 0). WICHTIGER BEFUND:
      `tests/test_core.py` Zeile 585 enthielt den Tippfehler `from cavmen.gui.pause_menu`
      (ein 'e' fehlte – Rest des abgebrochenen letzten Jobs); dadurch war die Suite bei jedem
      Start auf import-level rot. Fix: korrekt nach `cavemen.gui...`. Da die Shell-Namespace-
      Name-Lookups auf alten Inodes weiterhin ENOENT liefern, lief der Lauf über eine frische
      Byte-identische Kopie in `./tmp/run` mit neu angelegtem `./tmp/venv` (Nix-Python 3.14.7 +
      pygame-ce 2.5.8 via Store-pip). Committet als `ad2c766` (12.10.2026); tmp/-Cleanup steht mit P7.4 noch aus.

## 11. Phase 13 – Konversationen: Info-Austausch über Nahrungsquellen (angefordert am 12.10.2026, abgeschlossen)
Quelle: Nutzer-Ergänzung in INSTRUCTIONS.md §3 ("Konversationen"): "Sie sollen sich gegenseitig
darüber informieren, wo es Nahrungsquellen gibt." (Tippfehler 'ifnromieren' wurde beim P12-Commit
korrigiert.) Ziel: Sprechblasen enthalten echte Orts-Infos zu den vorhandenen Beerenbüschen statt nur
allgemeiner Floskeln; deterministisch und offline-sicher wie der Rest der Konversations-Logik.
Ist-Analyse (Stand 12.10.2026): `simulation/conversations.py` kennt drei Pools (_GENERIC_, _HUNGRY_ mit
vager "berries around here!", _WEATHER_), Zeilen werden über einen pro-Tick seeded RNG (`{seed}-chat-{tick}`)
gezogen; LLM-Option via `LLMClient.conversation_line(speaker, listener)` (Strict-JSON). Welt hält die
Büsche in `world.berry_tiles: {(x, y): menge > 0}` (~14 Büsche aus `worlds.gather.berry_count`); Fischen/P8.5
ist eine zweite potenzielle Nahrungsquelle für künftige Zeilen.
- [x] P13.1 Design festgelegt: Richtungsangabe (Himmelsricht-Wort) + Entfernung in Tiles; nächster Busch =
      max Menge, bei Gleichstand geringste Manhattan-Distanz zu beiden Agenten, dann lexikographische
      Tile-Reihenfolge (`_nearest_food_source`, deterministisch je Seed); Trigger: Speaker oder Listener mit
      Hunger > `food_hint_hunger_below` (Default 55) und Chance `food_hint_chance` (0.35); kein Busch im Radius
      → Fallback auf bestehende Pools; Radius `food_radius_tiles` = 24 (<=0 deaktiviert).
- [x] P13.2 Implementierung in `conversations.py`: `_nearest_food_source()` + `_direction_from()` (Himmelsricht-Wort) +
      `_food_hint_line()`, als bevorzugte Auswahl vor den bestehenden Zeilenpools; Config-Keys in `config.yaml`
      und Default in `cavemen/config.py`; deterministische Zeile, LLM-unabhängig.
- [x] P13.3 Optionaler LLM-Pfad: `LLMClient.conversation_line(..., bush_context)` – bei `use_llm=true` wird der
      Buschkontext (Relativposition) als zusätzliche Prompt-Zeile übergeben; Strict-JSON-Vertrag und
      Fallback auf die deterministische Hint-Zeile bleiben unverändert.
- [x] P13.4 Tests: Unit-Tests für `_direction_from`, `_nearest_food_source` (Determinismus je Seed, Radius-
      Einhaltungen, Gleichstandstiebreak), Hint-Zeilen (Format/Hunger-Schwelle) + A/B-Verifizierung: Conversation ON
      vs OFF über 600 Ticks → identische Weltzustände auf allen Sample-Punkten (Seeds 0–8, inkl. Seeds mit
      überlebendem Stamm; Sprechblasen sind reine Anzeige).
- [x] P13.5 Doku (STRUCTURE.md + Plan); Commit nach Nutzer-Bestätigung (offen).

**Status Phase 13:** Abgeschlossen am 12.10.2026, Unit-Tests grün, A/B-Lauf bestätigt Nicht-Einfluss auf
Regeln/Weltzustand. **Zusatzbefund während der Verifikation (außerhalb des P13-Spektrums):** `_pick_weather` in
`rules.py` fehlte seit Commit `96dca5b` die `break`-Anweisung nach dem gewichteten Roll – dadurch landete jeder
Wetter-Roll auf dem letzten Konfig-State ("storm") und das Wetter stand permanent, was zu frühem Verhungern des
Stamms in Headless-Läufen führte. Behoben durch Wiederherstellung der `break` (Original-Verhalten von Commit
`0526b8a`, identisch zur Referenzimplementierung `Weather.step`) + neuer Regressionstest
`test_weather_state_machine_cycles_across_states` in `tests/test_core.py`.

## 12. Phase 14 – Weltinfos-Panel links neben dem Canvas (angefordert am 12.10.2026, noch nicht implementiert)
Anforderung: "Die Anzeige der Weltinformationen soll links neben dem Canvas platziert werden, in dem die
Welt angezeigt wird, um Lesbarkeit zu steigern." Ist-Analyse: aktuell zeichnen `gui/hud.py::draw_top_bar`
(eine einzelne Zeile oben über/durch das Canvas: Tag/Wetter/Stamm/Tiere/Fische/Beeren) und `draw_panel`
(das Agenten-Panel) in die Bildfläche; Fenster-Geometrie kommt aus `gui/app.py`.
- [ ] P14.1 Layout-Design: feste linke Spalte (z. B. 260–300 px) außerhalb des Welt-Renders für die
      Weltinfos, zeilenweise statt als einzelne kompakte Zeile (bessere Lesbarkeit); Canvas-Offset in
      `renderer.py`/`app.py` entsprechend verschieben und Fensterbreite anpassen; Agenten-Panel bleibt
      rechts unten im Viewport, es sei denn, du möchtest es ebenfalls links – Entscheidung bei P14.1.
- [ ] P14.2 Implementierung: `gui/hud.py` (neue/separierte `draw_side_panel` + Umzug der Top-Bar-Inhalte),
      Geometrie in `gui/app.py`, Renderer-Koordinatenversatz; Kamera-Follow und Bubble-Sprites bleiben
      unverändert relativ zum Welt-Viewport.
- [ ] P14.3 Verifikation: Unit-/Smoke-Test für die Layout-Fakten (Spalten-Breiten, keine Überlappung mit
      dem Canvas), GUI-Smoke über den Dummy-Video-Treiber (Menü → Setup → Sim → ESC-Pause → QUIT); Suite
      grün; Doku (README-Tasten/Ansicht + STRUCTURE.md) aktualisieren.
- [ ] P14.4 Commit nach Nutzer-Bestätigung.

**Status Phase 14:** Angefordert, noch offen – keine Implementierung begonnen.
