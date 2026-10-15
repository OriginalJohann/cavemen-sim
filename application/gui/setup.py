"""Manual tribe creation screen ("setup") between menu and simulation.

Up to ten cavemen are entered in a four-column form (Name | Gender | Age |
Prompt) plus a count row, an editable Seed row and a start row. Every field is pre-filled with a
suggestion (member rows deterministic per slot; the seed is one fresh random value per open screen),
so ENTER starts the simulation immediately or any field can be edited beforehand. The Seed pins
world generation to reproducible test runs (INSTRUCTIONS "Seeding"); an empty or non-numeric
seed falls back to a new random seed at confirmation. Hard caps are enforced at confirmation
time only: name <= 8 chars, age clamped into [child_until_years, death_age_limit], prompt
clipped to init_max_chars - typing itself never truncates mid-word.

Keys: arrows move between fields, TAB steps through all fields in reading
order, +/- change the tribe size while the count field is active, plain typing
edits the active field, ENTER confirms and starts the sim, ESC returns to menu,
and the mouse wheel scrolls the row list vertically when it no longer fits into
the window height (Phase 15 overflow fix); arrow/TAB navigation auto-scrolls so
the active field always stays visible.
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
FIELDS = (("name", "Name"), ("gender", "Gender"), ("age", "Age"),
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
        # Phase 16 (Seeding): editable world seed, pre-filled with one fresh random value per
        # screen so the quick start works out of the box; an empty/invalid field falls back
        # to a new random seed inside World() at confirmation.
        self.seed_text = str(random.randrange(1 << 30))
        self.rows: list[dict] = [self._suggestion(i) for i in range(self.count)]
        # active field as (row, column); row layout: 0=count, 1=seed, 2..count+1=agents, count+2=start
        self.r, self.c = 1, 0
        # Phase 15 overflow handling: the row list scrolls vertically when it no
        # longer fits into the window height; fallback size until draw() reports
        # the real window size (keeps geometry pure and testable headlessly).
        self.scroll = 0                   # index of the first visible row (0..count+1)
        self.win_w, self.win_h = 1120, 640

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
        if not (0 <= self.r <= self.count + 2):                  # active field fell off-screen after shrinking the tribe
            self.r, self.c = min(self.count + 1, max(1, self.r - 3)), 0   # land on an existing row (seed/member region)
        self._clamp_scroll()                                    # count changes shrink what fits into the window

    # ---- field geometry ------------------------------------------------------
    def _row_fields(self, r: int) -> list[dict]:
        """Ordered fields of one row with their screen rects."""
        y = ROW_Y0 + r * (ROW_H + ROW_GAP)
        if r == 1:                             # Phase 16 seed row: pins reproducible world generation
            return [{"key": "seed", "label": "Seed",
                     "text": self.seed_text,
                     "rect": pygame.Rect(ROW_X, y, COLS[3][1], ROW_H)}]
        if r == 0 or r > self.count + 1:      # count row / start row: single field
            return [{"key": "count" if r == 0 else "start",
                     "label": "Count" if r == 0 else "Start",
                     "text": str(self.count) if r == 0 else "> Create tribe",
                     "rect": pygame.Rect(ROW_X, y, COLS[3][1], ROW_H)}]
        fields = []
        for c, (key, label) in enumerate(FIELDS):
            x_off, w = COLS[c]
            fields.append({"key": key, "label": label,
                          "text": self.rows[r - 2][key],   # member k sits on row index k+1 (seed occupies row 1)
                          "rect": pygame.Rect(ROW_X + x_off, y, w, ROW_H)})
        return fields

    def _all_rows(self) -> list[list[dict]]:
        return [self._row_fields(r) for r in range(self.count + 3)]   # count + seed + members + start

    # ---- Phase 15 overflow (vertical scroll of the row list) ------------------
    def _visible_row_count(self) -> int:
        """How many uniform rows fit into the current window height below ROW_Y0."""
        return max(1, (self.win_h - ROW_Y0) // (ROW_H + ROW_GAP))

    def _max_scroll(self) -> int:
        """Largest scroll index so every row (incl. count/start rows) stays reachable."""
        return max(0, self.count + 3 - self._visible_row_count())

    def _clamp_scroll(self) -> None:
        self.scroll = max(0, min(int(self.scroll), self._max_scroll()))

    def _ensure_cursor_visible(self) -> None:
        """Auto-scroll the row list so arrow/TAB navigation never loses the active field off-screen."""
        vis = self._visible_row_count()
        if self.r < self.scroll:                        # cursor moved above the viewport
            self.scroll = max(0, min(int(self.r), self._max_scroll()))
        elif self.r >= self.scroll + vis:               # cursor moved below the viewport
            self.scroll = max(0, min(int(self.r - vis + 1), self._max_scroll()))

    # ---- events --------------------------------------------------------------
    def handle_event(self, event):
        """Returns None (consumed/no action), a cancel dict or a confirm dict."""
        if event.type == pygame.MOUSEWHEEL:             # Phase 15: scroll the row list vertically when it overflows the window height
            self.scroll -= int(event.y)                 # pygame y>0 = wheel up, so wheel-down (y<0) advances to later rows
            self._clamp_scroll()
            return None
        if event.type != pygame.KEYDOWN:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                dy = -self.scroll * (ROW_H + ROW_GAP)   # shift the visible row rects by the current scroll offset
                first, last = self.scroll, min(self.count + 3, self.scroll + self._visible_row_count())
                for r in range(first, last):            # only rows inside the viewport are clickable
                    for c, field in enumerate(self._row_fields(r)):
                        if field["rect"].move(0, dy).collidepoint(event.pos):   # .move(): works in classic pygame AND pygame-ce (Rect + tuple only exists in pygame-ce)
                            self.r, self.c = r, c
                            return None
            return None
        key = event.key
        if key == pygame.K_ESCAPE:
            return {"kind": "cancel", "slot": self.slot}
        rows_n = self.count + 3                          # count row + seed row + member rows + start row (Phase 16)
        if key == pygame.K_UP:
            self.r = (self.r - 1) % rows_n
        elif key == pygame.K_DOWN:
            self.r = (self.r + 1) % rows_n
        else:
            n_cols = len(self._row_fields(self.r))
            if key == pygame.K_LEFT:
                self.c = (self.c - 1) % n_cols
                return None
            elif key == pygame.K_RIGHT:
                self.c = (self.c + 1) % n_cols
                return None
        # keep the column valid for single-field rows after vertical moves (count & seed rows are single-field too)
        if self.r in (0, 1) or self.r == rows_n - 1:
            self.c = 0
        elif self.c >= len(self._row_fields(self.r)):
            self.c = len(self._row_fields(self.r)) - 1
        self._ensure_cursor_visible()                   # Phase 15: keep the active field on screen during navigation
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
            try:
                idx = next(i for i, p in enumerate(order) if p == (self.r, self.c))
            except StopIteration:                       # defensive fallback: cursor position is stale
                idx = 0                                  # wrap around from the first field instead of crashing
            self.r, self.c = order[(idx + 1) % len(order)]   # wrap-around keeps TAB cycling safe
            return None
        # ---- plain text editing of the active field --------------------------
        ch = getattr(event, "unicode", None) or ""   # defensive: tolerate KEYDOWN events without .unicode (as in prompt_editor.py)
        if key == pygame.K_BACKSPACE:                # deletion needs no unicode payload; applies to seed and member rows
            if field["key"] == "seed" and self.seed_text:     # Phase 16: clear the last digit of the seed value
                self.seed_text = self.seed_text[:-1]
            elif 2 <= self.r <= self.count + 1 and field["text"]:   # member rows only (count/seed/start carry no row entry)
                row = self.rows[self.r - 2]                  # member k sits on row index k+1
                row[field["key"]] = field["text"][:-1]
            return None
        if field["key"] in ("count", "start"):      # single-field count/start rows: nothing to edit, never index self.rows
            return None
        # note: in Python "".isprintable() is True, so the explicit empty check keeps pure navigation keys (no unicode payload) out of this section
        if not ch or not ch.isprintable() or ch == " ":    # control chars / spaces ignored in fields
            return None
        cur = field["text"]
        if field["key"] == "seed":                # Phase 16: digits only, max. ten (the default random range is < 2**30)
            if ch.isdigit():
                self.seed_text = (cur + ch)[:10]   # keep the first ten digits; overflow shifts nothing, it truncates
            return None
        row = self.rows[self.r - 2]               # only member rows reach this point now
        if field["key"] == "name":                 # backspace already handled above; remaining branches append printable chars only
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
        # Phase 16 (Seeding): digits-only seed -> reproducible world generation; an empty or
        # non-numeric field yields None so World() rolls a fresh random seed as before.
        seed_text = str(self.seed_text).strip()
        seed = int(seed_text) if seed_text.isdigit() else None
        return {"kind": self.kind, "slot": self.slot, "seed": seed, "roster": roster}

    # ---- drawing -------------------------------------------------------------
    def draw(self, screen, font_title, font_item) -> None:
        screen.fill(BG_COLOR)
        self.win_w, self.win_h = screen.get_width(), screen.get_height()   # real size for the scroll geometry
        title = f"CAVMEN - Neue Welt in Slot {self.slot}"
        t = font_title.render(title, True, TEXT_COLOR)
        screen.blit(t, ((screen.get_width() - t.get_width()) // 2, TITLE_Y))
        hint = font_item.render(
            "Arrows= move | TAB= next field | +/-= count | Wheel=scroll | ENTER=start | ESC=back",
            True, DIM_COLOR)
        screen.blit(hint, (ROW_X, HINT_Y))
        dy = -self.scroll * (ROW_H + ROW_GAP)      # Phase 15: vertical shift of the row list
        for r, fields in enumerate(self._all_rows()):
            if not 0 <= (r - self.scroll) < self._visible_row_count():   # only draw rows inside the viewport
                continue
            for c, field in enumerate(fields):
                rect = field["rect"].move(0, dy)    # .move() (not Rect + tuple): stays compatible with classic pygame and pygame-ce alike
                pygame.draw.rect(screen, (30, 34, 40), rect)
                if r == self.r and c == self.c:
                    pygame.draw.rect(screen, CURSOR_COLOR, rect, width=2)   # active cursor
                label_s = font_item.render(field["label"] + ":", True, DIM_COLOR)
                screen.blit(label_s, (rect.x + 6, rect.y + (rect.h - label_s.get_height()) // 2))
                value_w = rect.w - 6 - label_s.get_width() - 8
                value_s = font_item.render(_fit_text(font_item, field["text"], value_w), True, TEXT_COLOR)
                screen.blit(value_s, (rect.x + 6 + label_s.get_width() + 2,
                                     rect.y + (rect.h - value_s.get_height()) // 2))

