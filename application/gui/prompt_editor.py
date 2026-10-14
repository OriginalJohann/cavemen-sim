"""Modal live prompt editor, opened from the pause menu while the simulation runs.

INSTRUCTIONS §3 asks that users may adapt individual agent prompts while the
simulation runs. Phase 15 restructures this overlay into two stages so long
prompts never squeeze out of the window any more:

Stage "list": shows only the names of all alive cavemen (arrow keys select, a
mouse click or ENTER opens one). ESC closes the editor completely here.

Stage "edit": a large input area dedicated to exactly one agent with its full
prompt wrapped into the available width; if the content is taller than the
window it scrolls vertically (mouse wheel, PAGEUP/PAGEDOWN or up/down arrows).
Every keystroke writes directly into `agent.prompt`, so changes are part of
the world state and ride along with autosaves. The hard cap
(`agents.prompts.init_max_chars`) is applied per keystroke via clip(). ESC/ENTER
returns to the name list (the simulation stays paused via the pause menu).
"""
import pygame

from ..agents.prompts import clip

BG_COLOR = (16, 20, 24)
TEXT_COLOR = (235, 230, 215)
DIM_COLOR = (150, 145, 135)
ACTIVE_COLOR = (90, 160, 210)

LIST_START_Y = 130        # first name row of the list stage (below title + hint line)
EDIT_BOX_TOP = 112        # top edge of the large input area in the edit stage
EDIT_MARGIN_X = 24        # left/right inset of rows and edit box
EDIT_BOTTOM_PAD = 78      # space reserved below the edit box for the bottom hint line


def _wrap(font, text: str, width_px: int) -> list:
    """Wrap one string into pixel-width-bounded lines using font metrics."""
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.size(candidate)[0] > width_px and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


class PromptEditor:
    """Two-stage modal prompt editor: name list first, then one big input area."""

    STAGE_LIST = "list"
    STAGE_EDIT = "edit"

    def __init__(self, world, cfg):
        self.world = world
        self.cfg = cfg
        self.cap = int(cfg.get("agents.prompts.init_max_chars", 100))
        # live references on purpose: edits write straight into the agents and
        # therefore persist with every autosave of the world
        self.rows = [a for a in world.agents if a.alive]
        # Phase 15 state: two-stage flow + independent scroll positions per stage
        self.stage = self.STAGE_LIST      # start on the plain name list (Phase 15 UX)
        self.scroll_rows = 0             # first visible row of the name list
        self.text_scroll = 0.0           # vertical offset in px inside the edit box
        self._max_text_scroll = 0.0      # content-dependent clamp, refreshed on every draw
        self.win_w, self.win_h = 1120, 640   # fallback size until draw() reports the real window
        self._row_h = 28                 # name-row height fallback (real font linesize reported in draw)
        self.r = 0                              # active row index

    def _active(self):
        return self.rows[self.r] if 0 <= self.r < len(self.rows) else None

    # ---- pure geometry helpers (also used headlessly by the unit tests) --------
    def list_row_rect(self, index: int, row_h: int) -> pygame.Rect:
        """Screen rect of one name row, already shifted by the scroll offset."""
        y = LIST_START_Y + (index - self.scroll_rows) * row_h
        return pygame.Rect(EDIT_MARGIN_X, y, max(80, self.win_w - 2 * EDIT_MARGIN_X), row_h)

    def edit_box_rect(self) -> pygame.Rect:
        """The large input area of the edit stage."""
        return pygame.Rect(EDIT_MARGIN_X, EDIT_BOX_TOP,
                           max(100, self.win_w - 2 * EDIT_MARGIN_X),
                           max(80, self.win_h - EDIT_BOX_TOP - EDIT_BOTTOM_PAD))

    def _visible_list_rows(self) -> int:
        row_h = max(1, int(self._row_h))
        area_h = max(row_h, self.win_h - LIST_START_Y - 20)   # reserve the bottom hint line
        return max(1, area_h // row_h)

    def _max_list_scroll(self) -> int:
        if not self.rows:
            return 0
        return max(0, len(self.rows) - self._visible_list_rows())

    def open_editor_for(self, index: int) -> None:
        """Stage switch: focus the big input area of agent `index`."""
        if 0 <= index < len(self.rows):
            self.r = index
            self.stage = self.STAGE_EDIT
            self.text_scroll = 0.0

    def _clamp_text_scroll(self) -> None:
        self.text_scroll = max(0.0, min(float(self._max_text_scroll), float(self.text_scroll)))

    # ---- live editing (unchanged semantics from Phase 10) ----------------------
    def _type_char(self, char: str) -> None:
        agent = self._active()
        if agent is not None and len(char) == 1:
            # hard cap per keystroke so the prompt can never exceed init_max_chars
            agent.prompt = clip(agent.prompt + char, self.cap)

    def _backspace(self) -> None:
        agent = self._active()
        if agent is not None and agent.prompt:
            agent.prompt = agent.prompt[:-1]

    def handle_event(self, event):
        """Returns None (consumed), or {'kind': 'close'} when the editor ends.

        Phase 15: in the list stage arrow keys / mouse wheel pick a name and
        ENTER/click opens the edit stage; ESC closes completely there only. In
        the edit stage arrows/PAGEUP-PAGEDOWN/mouse wheel scroll the prompt and
        plain typing edits it live; ESC/ENTER return to the name list.
        """
        if event.type == pygame.MOUSEWHEEL:                   # vertical scrolling of whichever stage is open
            if self.stage == self.STAGE_EDIT:
                self.text_scroll += 18.0 * float(-event.y)    # wheel down -> later lines (pygame y>0 = scroll up)
                self._clamp_text_scroll()
            else:
                self.scroll_rows = max(0, min(int(self.scroll_rows) + int(event.y), self._max_list_scroll()))
            return None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 \
                and self.stage == self.STAGE_LIST:             # list stage only: clicking a name opens its editor
            for i in range(len(self.rows)):
                if self.list_row_rect(i, int(self._row_h)).collidepoint(event.pos):
                    self.open_editor_for(i)
                    return None
        if event.type != pygame.KEYDOWN:
            return None   # any other mouse input is intentionally ignored on this screen
        key = event.key
        rows_n = max(1, len(self.rows))
        agent = self._active()
        if self.stage == self.STAGE_EDIT and key in (pygame.K_ESCAPE, pygame.K_RETURN):
            self.stage = self.STAGE_LIST      # ESC/ENTER only leave the big input area - back to the name list
            self.text_scroll = 0.0
            return None
        if self.stage == self.STAGE_LIST:                     # no typing on this screen - only navigation
            if key == pygame.K_ESCAPE:                        # from the list stage: close completely
                return {"kind": "close"}
            if key == pygame.K_RETURN:                       # ENTER opens the big input area of the selected name
                self.open_editor_for(self.r)
                return None
            if key == pygame.K_UP:
                self.r = (self.r - 1) % rows_n                 # wrap-around within the name list
            elif key == pygame.K_DOWN:
                self.r = (self.r + 1) % rows_n
        else:                                                 # edit stage: arrows scroll the text vertically
            if key == pygame.K_UP:
                self.text_scroll -= 18.0                      # one line up/down per step (matches wheel step)
            elif key == pygame.K_DOWN:
                self.text_scroll += 18.0
            elif key == pygame.K_PAGEUP:
                self.text_scroll -= 6 * float(self._row_h)    # roughly one screen of text up
            elif key == pygame.K_PAGEDOWN:
                self.text_scroll += 6 * float(self._row_h)
        if self.stage == self.STAGE_EDIT and agent is not None:
            if key == pygame.K_BACKSPACE:
                self._backspace()
            else:                                              # live typing, hard-capped per keystroke (Phase 10 rule unchanged)
                char = getattr(event, "unicode", None) or ""   # defensive: tolerate events w/o .unicode
                if len(char) == 1 and char.isprintable():
                    self._type_char(char)
        self._clamp_text_scroll()                              # no scroll beyond content in either stage
        return None

    def draw(self, screen, font_title, font_item) -> None:
        w, h = screen.get_width(), screen.get_height()
        self.win_w, self.win_h = w, h                   # scroll geometry follows the current window size
        screen.fill(BG_COLOR)
        title = font_title.render("Edit prompts live (back via ESC / ENTER)", True, TEXT_COLOR)
        screen.blit(title, (20, 14))
        if self.stage == self.STAGE_LIST:               # names only - no prompt text on this screen any more
            self._row_h = max(18, font_item.get_linesize() + 8)   # real row height for clicks and scrolling
            hint = font_item.render(
                "Arrows/mouse: pick a caveman | ENTER/click: edit prompt | ESC: back",
                True, DIM_COLOR)
            screen.blit(hint, (20, 60))
            vis = self._visible_list_rows()             # Phase 15: name list scrolls when taller than the window
            for i in range(len(self.rows)):
                if not 0 <= (i - self.scroll_rows) < vis:    # only rows inside the visible area are drawn
                    continue
                agent = self.rows[i]
                active = i == self.r
                name_s = font_item.render(f"{agent.name}:", True, TEXT_COLOR if active else DIM_COLOR)
                y0 = LIST_START_Y + (i - self.scroll_rows) * int(self._row_h)   # kept in sync with list_row_rect() for clicks
                screen.blit(name_s, (EDIT_MARGIN_X + 8, y0 + 2))
                if active:
                    pygame.draw.rect(screen, ACTIVE_COLOR,
                                     (EDIT_MARGIN_X - 4, y0 - 2, w - 2 * EDIT_MARGIN_X + 8, int(self._row_h)), width=1)
        else:                                           # edit stage: one big input area with the full prompt of agent `r`
            agent = self.rows[self.r]
            box = self.edit_box_rect()
            pygame.draw.rect(screen, ACTIVE_COLOR, box, width=1)
            lines = _wrap(font_item, agent.prompt or "(empty)", max(20, box.w - 24))   # full prompt wrapped into the box width
            line_h = font_item.get_linesize()
            content_h = len(lines) * line_h + 8          # total height of the text inside the box
            self._max_text_scroll = max(0.0, float(content_h - (box.h - 8)))   # scroll only when taller than window/box
            self.text_scroll = max(0.0, min(self.text_scroll, self._max_text_scroll))
            for j, ln in enumerate(lines):
                y_line = box.y + 10 + int(j * line_h - self.text_scroll)   # shifted by the scroll offset (truncated to px)
                if not (box.y <= y_line <= box.bottom):     # skip lines scrolled out of the box
                    continue
                s = font_item.render(ln, True, TEXT_COLOR)
                screen.blit(s, (box.x + 12, y_line))
            hint = font_item.render(
                f"{agent.name} | cap {self.cap} chars | Wheel/PAGEUP-DOWN: scroll | ESC/ENTER: back to list",
                True, DIM_COLOR)
            screen.blit(hint, (EDIT_MARGIN_X, h - 24))    # kept inside the window on any size
