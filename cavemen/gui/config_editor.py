"""Modal global settings editor, opened from the main menu ("Edit settings").

Mirrors the prompt editor's modal design: overlay on a frozen screen while open.
Every row is one editable dotted config key (all must exist in config.yaml).
Navigation uses modulo arithmetic so scrolling past either list edge can never
index out of range; typing/backspace edits the active value with a soft cap.

ENTER validates all rows (types, inclusive ranges, URL scheme + age cross-check)
and returns {"kind": "save", ...} on success; validation failures set self.error
and keep the editor open for a fix. ESC cancels without saving. Persistence of
the save is done by the caller via config.update_config_values, which rewrites
only the edited lines in place so comments and unknown keys survive verbatim.

Keys: arrow keys select row | typing/backspace edit value | ENTER=save & close
| ESC=abort (unsaved). WASD is deliberately NOT a navigation key, so it can be typed
into any field without the cursor jumping away.
"""
import pygame

BG_COLOR = (16, 20, 24)
TEXT_COLOR = (235, 230, 215)
DIM_COLOR = (150, 145, 135)
ACTIVE_COLOR = (90, 160, 210)
ERROR_COLOR = (210, 90, 80)

# (dotted key, German label); every key must exist in config.yaml by default.
EDITABLE_KEYS: tuple[tuple[str, str], ...] = (
    ("simulation.max_agents_per_world", "Cavemen pro Welt (max.)"),
    ("simulation.tick_rate_hz", "Ticks pro Sekunde"),
    ("worlds.max_worlds", "Anzahl Welten-Slots"),
    ("agents.age.child_until_years", "Kind bis (Sim-Jahre)"),
    ("agents.age.death_age_limit", "Max. Alter (Sim-Jahre)"),
    ("agents.prompts.init_max_chars", "Prompt-Länge max. (Zeichen)"),
    ("llm.base_url", "LLM-Endpoint (URL)"),
    ("llm.api_key", "LLM API-Key ('' = ohne Auth)"),
    ("llm.model", "LLM Model-ID"),
    ("llm.timeout_s", "LLM Timeout (Sekunden)"),
    ("llm.max_retries", "LLM Retries"),
    ("llm.max_tokens", "LLM max. Tokens"),
    ("GUI.window_w", "Fensterbreite (Px, ab Neustart)"),
    ("GUI.window_h", "Fensterhöhe (Px, ab Neustart)"),
    ("llm.decisions_per_tick", "LLM-Entscheidungen pro Tick"),
)

# Per-key validation: python type plus inclusive [min, max] bounds.
_LIMITS = {
    "simulation.max_agents_per_world": (int, 1, 50),
    "simulation.tick_rate_hz": (float, 0.25, 60.0),
    "worlds.max_worlds": (int, 1, 99),
    "agents.age.child_until_years": (int, 1, 300),
    "agents.age.death_age_limit": (int, 1, 300),
    "agents.prompts.init_max_chars": (int, 1, 500),
    "llm.timeout_s": (float, 0.1, 600.0),
    "llm.max_retries": (int, 0, 10),
    "llm.max_tokens": (int, 1, 4096),
    "GUI.window_w": (int, 320, 7680),
    "GUI.window_h": (int, 240, 4320),
    "llm.decisions_per_tick": (int, 1, 32),
}

_VALUE_CAP = 64   # hard display/edit cap per field so lines stay single-row


class ConfigEditor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.rows = list(EDITABLE_KEYS)                    # stable order (tests rely on it)
        self.values = [str(cfg.get(key)) for key, _ in self.rows]  # effective values as text
        self.r = 0                                         # active row index
        self.error: str | None = None                        # shown until next clean action

    def handle_event(self, event) -> dict | None:
        """Returns None (consumed), {'kind': 'cancel'} or a save action on ENTER."""
        if event.type != pygame.KEYDOWN:
            return None   # mouse input intentionally ignored (consistent with prompt editor)
        key = event.key
        rows_n = max(1, len(self.rows))                     # never zero -> modulo always safe
        if key == pygame.K_ESCAPE:
            return {"kind": "cancel"}
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            updates = self._validated_updates()
            if updates is None:
                return None    # error already set -> stay open for a fix
            return {"kind": "save", "path": self.cfg.path, "updates": updates}
        if key == pygame.K_UP:    # arrow keys ONLY on purpose: W/S must stay typeable as plain text
            self.r = (self.r - 1) % rows_n                 # wrap-around: scrolling past edges is safe
        elif key == pygame.K_DOWN:
            self.r = (self.r + 1) % rows_n
        elif key == pygame.K_BACKSPACE:
            if self.values[self.r]:
                self.values[self.r] = self.values[self.r][:-1]
                self.error = None
        else:
            char = getattr(event, "unicode", None) or ""   # defensive: tolerate events w/o .unicode
            if len(char) == 1 and char.isprintable() and char != "\t":
                cur = self.values[self.r]
                if len(cur) < _VALUE_CAP:                  # field can never overflow its row width
                    self.values[self.r] = cur + char
                    self.error = None
        return None

    def _validated_updates(self) -> dict | None:
        """Parse & validate every row; returns {'key': typed_value} or sets self.error."""
        parsed: dict[str, object] = {}
        for (key, _label), text in zip(self.rows, self.values):
            t = str(text).strip()
            if key == "llm.base_url":
                # must be a URL so the client can never silently target nonsense endpoints
                if not (t.startswith("http://") or t.startswith("https://")):
                    self.error = f"LLM-Endpoint muss mit http(s):// beginnen ('{t}' ungültig)"
                    return None
                parsed[key] = t
                continue
            if key in ("llm.api_key", "llm.model"):        # free text (api key / model id)
                parsed[key] = t
                continue
            kind, lo, hi = _LIMITS[key]
            try:
                v = int(t) if kind is int else float(t)   # rejects non-numeric input cleanly
            except ValueError:
                self.error = f"{key}: '{t}' ist keine gültige Zahl"
                return None
            if not (lo <= v <= hi):
                self.error = f"{key}: Wert {v} außerhalb des erlaubten Bereichs [{lo}, {hi}]"
                return None
            parsed[key] = v
        # cross-check: the death age limit must stay above the child threshold
        if parsed["agents.age.death_age_limit"] < parsed["agents.age.child_until_years"]:
            self.error = "Max. Alter muss größer sein als 'Kind bis'"
            return None
        return parsed

    def draw(self, screen, font_title, font_item) -> None:
        """Render title + one row per editable key with a cursor highlight."""
        w = screen.get_width()
        screen.fill(BG_COLOR)                              # full overlay over the frozen menu frame
        title = font_title.render("Einstellungen bearbeiten", True, TEXT_COLOR)
        screen.blit(title, (20, 14))
        hint = font_item.render(
            "Pfeiltasten=Zeilen wählen | Tippen/Backspace=editieren | ENTER=speichern & schließen | ESC=abbrechen",
            True, DIM_COLOR)
        screen.blit(hint, (20, 56))
        if self.error:                                   # friendly one-liner instead of a crash
            err_s = font_item.render(self.error, True, ERROR_COLOR)
            screen.blit(err_s, (20, 84))
        y = 112
        label_x, value_x = 16, 300
        for i, ((key, label), value) in enumerate(zip(self.rows, self.values)):
            active = i == self.r
            row_h = font_item.get_linesize() + 8
            if active:
                pygame.draw.rect(screen, ACTIVE_COLOR, (12, y - 3, w - 24, row_h), width=1)
            label_s = font_item.render(label + ":", True, TEXT_COLOR if active else DIM_COLOR)
            screen.blit(label_s, (label_x, y))
            val_text = str(value).strip() or "(leer)"
            val_s = font_item.render(val_text, True, TEXT_COLOR if active else DIM_COLOR)
            screen.blit(val_s, (value_x, y))
            # dotted key shown dim on the right edge as reference to config.yaml
            key_s = font_item.render(key, True, (120, 116, 108))
            screen.blit(key_s, (w - key_s.get_width() - 16, y))
            y += row_h + 4