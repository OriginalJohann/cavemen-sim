# Projektauftrag & Anforderungsspezifikation: Höhlenmenschen-KI-Simulation (Linux / NixOS)

* **Rolle:** Erfahrener Softwarearchitekt und Full-Stack-Entwickler.
* **Zielplattform:** Linux, optimiert für reibungslose Ausführbarkeit unter **NixOS** (inklusive `flake.nix` / `shell.nix` für Abhängigkeiten wie OpenGL/SDL/Python).
* **Bereitstellung:** Single-Script-Installationsskript (robustes Bash-Skript) zur automatischen Prüfung, Einrichtung und Ausführung. Sprache der Software soll Englisch sein.

---

## 1. Architektur & Kerntechnologien

* **Modularer Aufbau:** Sauber strukturierte Codebasis (z. B. Python mit Pygame oder Godot/Rust, je nach Performance- und Installationsanforderung).
* **Konfigurierbarkeit:** Zentrale Konfigurationsdatei oder UI-Parameter für alle Grenz- und Schwellwerte (Grenzwerte für Agenten, Alter, Fortpflanzung, LLM-Endpunkte).
* **LLM-Integration:** Konfigurierbarer Endpunkt (Unterstützung für lokale Anbieter wie LM-Studio via OpenAI-kompatibler API sowie externe Anbieter).

## 2. Simulationsregeln & Spielwelt

* **Start & Speicherstand:** Jeder Stamm startet in einer frisch generierten, begrenzten Welt direkt in einer Höhle. Welten müssen speicher- und ladbar sein (max. 3 Welten gleichzeitig).
* **Größenordnung:** Maximal 10 Höhlenmenschen (KI-Agenten) gleichzeitig pro Welt.
* **Nicht-KI-Akteure:** Tiere (eiszeitliche Tiere und Saurier) sowie das Wetter agieren nach festen, prozeduralen Regeln / Skripten ohne LLM-Steuerung.
* **Fortpflanzung:** Fällt der Stamm unter 10 Mitglieder, können ein Mann und eine Frau gemeinsam Nachwuchs zeugen (parametrierbare Alters- und Bedingungsschwellwerte).
* **Essen ohne jagen:** Es soll Möglichkeiten geben an Nahrung zu kommen, ohne zu jagen z.B. Sammeln von Beeren oder Fischen.
* **Tickraten:** Die Tickrate der Simulation soll konfigurierbar sein so, dass Nutzer mit leistungsstärkeren Systemen eine schnellere Simulation erhalten können.
* **Observierbarkeit:** Die Anwendung soll per Kommandozeilenargument in einem Modus gestartet werden können, der die Kommunikation mit dem LLM-Endpoint im Terminal darstellen kann.
* **Seeding:** Um leichter zu testen soll es möglich sein, beim Erstellen einer Welt einen Seed einzugeben, um die Generierung konsistent zu gestalten.

## 3. Agenten-Management & Attribute

* **Attribute:** Jeder Höhlenmensch verfügt über Lebenspunkte (HP), Ausdauer (Stamina), Hunger, ein alternsabhängiges System sowie ein persistentes Profil für Lebensgeschichten.
* **Initialisierung:** Generierung beim Weltenstart via individuellem Prompt (max. 100 Zeichen, inkl. Name, Alter, Geschlecht, Persönlichkeitsmerkmalen).
* **Laufzeit-Anpassung:** Dynamische Anpassung des individuellen Agenten-Prompts während der laufenden Simulation. Zusätzlich zur Aktualisierung der Prompts mit Weltinformationen durch die Simulation soll es auch dem Nutzer möglich sein, die Prompts zur Laufzeit anzupassen.
* **Konfigurierbarkeit:** Beim erstellen einer neuen Welt soll ein Dialog geöffnet werden, in dem man die Anzahl an Höhlenmenschen sowie deren Eigenschaften bestimmen kann. Name, Geschlecht, Alter und Prompt sollen vom Nutzer eingegeben werden können. Eine Vorbefüllung mit randomisierten Vorschlägen für einen Schnellstart ist gewünscht.
* **Konversationen:** Die Agenten sollen miteinander kommunizieren können. Diese Gespräche sind in Sprechblasen anzuzeigen. Sie sollen sich gegenseitig darüber informieren, wo es Nahrungsquellen gibt.
* **Welteigenschaften:** Welteigenschaften, wie Tickrate, LLM-Endpoint oder auch Höhlenmenschenanzahl und Geburtenparameter (Aufzählung nicht endgültig) sollen in einem seperaten Menü, welches vom Startbildschirm aus erreichbar ist, konfigurierbar sein.

## 4. Grafische Benutzeroberfläche (GUI)

* **Visualisierung:** Echtzeit-Beobachtung der Simulation in einer Top-Down-Ansicht.
* **Grafikstil:** Pixelgrafik (charmanter Retro-Look).
* **UI & Steuerung:** Hauptmenü beim Start, Anzeige von Agenten-Status (Hunger, HP, Ausdauer, Alter, Prompt, Profil) und Welt-Informationen (Wetter, Tageszeit, Tiere), Pausenmenü während Simulation pausiert das Spiel, gibt Möglichkeit zur Rückkehr ins Hauptmenü und erlaubt es die Prompts der Cavemen anzupassen.
