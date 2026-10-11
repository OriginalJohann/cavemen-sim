"""Manual tribe creation screen ("setup") between menu and simulation.

Up to ten cavemen are entered in a four-column form (Name | Gender | Age |
Prompt) plus a count row and a start row. Every field is pre-filled with a
deterministic suggestion derived from the world slot, so ENTER starts the
simulation immediately or any field can be edited beforehand. Hard caps are
enforced at confirmation time only: name <= 8 chars, age clamped into
[child_until_years, death_age_limit], prompt clipped to init_max_chars -
typing itself never truncates mid-word.

Keys: arrows/WASD move between fields, TAB steps through all fields in reading
order, +/- change the tribe size while the count field is active, plain typing
edits the active field, ENTER confirms and starts the sim, ESC returns to menu.
"""
import random

import pygame

from ..agents.prompts import clip, make_initial_prompt, pick_character

BG_COLOR = (16, 20, 24)
TEXT_COLOR = (235, 230, 215)
DIM_COLOR = (150, 145, 135)
CURSOR_COLOR = (90, 160, 210)

TITLE_Y = 30
HINT_Y = 74
ROW_X, ROW_H, ROW_GAP = 40, 26, 5
ROW_Y0 = 108
# four input columns as (x offset from ROW_X, width), in reading order
COLS = ((0, 230), (240, 90), (370, 70), (450, 490))
FIELDS = (("name", "Name"), ("gender", "Geschlecht"), ("age", "Alter"),
         ("prompt", "Prompt"))


def _fit_text(font, text: str, max_w: int) -> str:
    """Shrink a string until it fits the pixel width (display only)."""
    while len(text) > 0 and font.size(text)[0] > max(10, max_w):
        text = text[:-1]
    return text


class WorldSetup:
    def __init__(self, cfg, slot: int, kind: str = "new"):
        self.cfg = cfg
        self.slot = int(slot)
        self.kind = kind                        # kept for confirmation (new/overwrite)
        self.cap_count = min(10, max(1, int(cfg.get("simulation.max_agents_per_world", 10))))
        self.count = self.cap_count             # pre-filled: a full tribe of 10
        self.name_cap = 8                       # hard cap for names (UI spec)
        self.prompt_cap = int(cfg.get("agents.prompts.init_max_chars", 100))
        self.age_min = float(cfg.get("agents.age.child_until_years", 5))
        self.age_max = float(cfg.get("agents.age.death_age_limit", 70))
        self.rows: list[dict] = [self._suggestion(i) for i in range(self.count)]
        # active field as (row, column); row layout: 0=count, 1..count=agents, count+1=start
        self.r, self.c = 1, 0

    def _suggestion(self, index: int) -> dict:
        """Deterministic pre-fill per (slot, row): name, trait, age and prompt."""
        rng = random.Random(f"{self.slot}-setup-{index}")   # stable across count changes
        gender = "m" if index % 2 == 0 else "f"              # balanced like the auto-tribe
        name, trait = pick_character(rng, gender)
        age_years = int(rng.uniform(16.0, 34.0))
        return {
            "name": name[:self.name_cap],
            "gender": gender,
            "age": str(age_years),
            "prompt": make_initial_prompt(name[:self.name_cap], age_years, gender, trait,
                                          self.prompt_cap),
        }

    def _set_count(self, n: int) -> None:
        """Clamp the tribe size and keep the row list in sync."""
        n = max(1, min(self.cap_count, int(n)))
        while len(self.rows) < n:
            self.rows.append(self._suggestion(len(self.rows)))   # fresh deterministic pre-fill
        del self.rows[n:]
        self.count = n
        if not (0 <= self.r <= self.count + 1):                  # active field fell off-screen
            self.r, self.c = min(max(0, self.r - 2), max(0, self.count)), 0

    # ---- field geometry ------------------------------------------------------
    def _row_fields(self, r: int) -> list[dict]:
        """Ordered fields of one row with their screen rects."""
        y = ROW_Y0 + r * (ROW_H + ROW_GAP)
        if r == 0 or r > self.count:         # count row / start row: single field
            return [{"key": "count" if r == 0 else "start",
                     "label": "Anzahl" if r == 0 else "Starten",
                     "text": str(self.count) if r == 0 else "> Stamm gruenden",
                     "rect": pygame.Rect(ROW_X, y, COLS[3][1], ROW_H)}]
        fields = []
        for c, (key, label) in enumerate(FIELDS):
            x_off, w = COLS[c]
            fields.append({"key": key, "label": label,
                          "text": self.rows[r - 1][key],
                          "rect": pygame.Rect(ROW_X + x_off, y, w, ROW_H)})
        return fields

    def _all_rows(self) -> list[list[dict]]:
        return [self._row_fields(r) for r in range(self.count + 2)]

    # ---- events --------------------------------------------------------------
    def handle_event(self, event):
        """Returns None (consumed/no action), a cancel dict or a confirm dict."""
        if event.type != pygame.KEYDOWN:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for r, fields in enumerate(self._all_rows()):
                    for c, field in enumerate(fields):
                        if field["rect"].collidepoint(event.pos):
                            self.r, self.c = r, c
                            return None
            return None
        key = event.key
        if key == pygame.K_ESCAPE:
            return {"kind": "cancel", "slot": self.slot}
        rows_n = self.count + 2
        if key in (pygame.K_UP, pygame.K_w):
            self.r = (self.r - 1) % rows_n
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.r = (self.r + 1) % rows_n
        else:
            n_cols = len(self._row_fields(self.r))
            if key in (pygame.K_LEFT, pygame.K_a):
                self.c = (self.c - 1) % n_cols
                return None
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.c = (self.c + 1) % n_cols
                return None
        # keep the column valid for single-field rows after vertical moves
        if self.r == 0 or self.r == rows_n - 1:
            self.c = 0
        elif self.c >= len(self._row_fields(self.r)):
            self.c = len(self._row_fields(self.r)) - 1
        field = self._row_fields(self.r)[self.c]
        if key in (pygame.K_PLUS, pygame.K_EQUALS) and field["key"] == "count":
            self._set_count(self.count + 1)      # cap enforced inside _set_count
            return None
        if key == pygame.K_MINUS and field["key"] == "count":
            self._set_count(self.count - 1)
            return None
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            return self._confirm()               # fields pre-filled -> start immediately
        if key == pygame.K_TAB:
            order = [(r_, c_) for r_ in range(rows_n)
                     for c_ in range(len(self._row_fields(r_)))]
            idx = next(i for i, p in enumerate(order) if p == (self.r, self.c))
            self.r, self.c = order[(idx + 1) % len(order)]
            return None
        # ---- plain text editing of the active field --------------------------
        ch = event.unicode or ""
        if not ch.isprintable() or ch == " ":    # control chars / spaces ignored in fields
            return None
        cur = field["text"]
        row = self.rows[self.r - 1]
        if key == pygame.K_BACKSPACE:
            row[field["key"]] = cur[:-1]
        elif field["key"] == "name":
            row["name"] = cur + ch               # hard cap applied only at confirmation
        elif field["key"] == "gender":           # single letter m/f, replaces content
            low = ch.lower()
            if low in ("m", "f"):
                row["gender"] = low
            return None
        elif field["key"] == "age":
            if ch.isdigit():                     # keep the last two digits (range 5..70)
                row["age"] = (cur + ch)[-2:] if len(cur) >= 2 else cur + ch
            return None
        elif field["key"] == "prompt":
            row["prompt"] = cur + ch             # hard char cap applied only at confirmation
        return None

    def _confirm(self) -> dict:
        """Build the validated roster; caps are enforced here, not during typing."""
        roster = []
        for i in range(self.count):
            row = self.rows[i]
            name = str(row["name"]).strip()[:self.name_cap] or "Gast"
            gender = "f" if str(row["gender"]).strip().lower() in ("f", "female") else "m"
            try:
                age_years = float(str(row["age"]).strip())
            except ValueError:
                age_years = 20.0
            age_years = min(self.age_max, max(self.age_min, age_years))   # clamp into range
            roster.append({"name": name, "gender": gender, "age_years": age_years,
                          "prompt": clip(str(row["prompt"]), self.prompt_cap)})
        return {"kind": self.kind, "slot": self.slot, "roster": roster}

    # ---- drawing -------------------------------------------------------------
    def draw(self, screen, font_title, font_item) -> None:
        screen.fill(BG_COLOR)
        title = f"CAVMEN - Neue Welt in Slot {self.slot}"
        t = font_title.render(title, True, TEXT_COLOR)
        screen.blit(t, ((screen.get_width() - t.get_width()) // 2, TITLE_Y))
        hint = font_item.render(
            "Pfeile/WASD= bewegen | TAB= naechstes Feld | +/-= Anzahl | "
            "ENTER=Starten | ESC=zurueck", True, DIM_COLOR)
        screen.blit(hint, (ROW_X, HINT_Y))
        for r, fields in enumerate(self._all_rows()):
            for c, field in enumerate(fields):
                rect = field["rect"]
                pygame.draw.rect(screen, (30, 34, 40), rect)
                if r == self.r and c == self.c:
                    pygame.draw.rect(screen, CURSOR_COLOR, rect, width=2)   # active cursor
                label_s = font_item.render(field["label"] + ":", True, DIM_COLOR)
                screen.blit(label_s, (rect.x + 6, rect.y + (rect.h - label_s.get_height()) // 2))
                value_w = rect.w - 6 - label_s.get_width() - 8
                value_s = font_item.render(_fit_text(font_item, field["text"], value_w), True, TEXT_COLOR)
                screen.blit(value_s, (rect.x + 6 + label_s.get_width() + 2,
                                     rect.y + (rect.h - value_s.get_height()) // 2))

