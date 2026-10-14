"""Modal live prompt editor, opened from the pause menu while the simulation runs.

INSTRUCTIONS §3 asks that users may adapt individual agent prompts while the
simulation runs. This overlay pauses the ticking; every keystroke writes
directly into `agent.prompt`, so changes are part of the world state and ride
along with autosaves. The hard cap (`agents.prompts.init_max_chars`) is applied
per keystroke via clip(); ESC or ENTER closes the editor (the simulation is resumed from the pause menu).

Keys: arrows move between agents, plain typing edits the active agent's
prompt, BACKSPACE deletes a character, ENTER/ESC close (changes are already
live by then).
"""
import pygame

from ..agents.prompts import clip

BG_COLOR = (16, 20, 24)
TEXT_COLOR = (235, 230, 215)
DIM_COLOR = (150, 145, 135)
ACTIVE_COLOR = (90, 160, 210)


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
    def __init__(self, world, cfg):
        self.world = world
        self.cfg = cfg
        self.cap = int(cfg.get("agents.prompts.init_max_chars", 100))
        # live references on purpose: edits write straight into the agents and
        # therefore persist with every autosave of the world
        self.rows = [a for a in world.agents if a.alive]
        self.r = 0                              # active row index

    def _active(self):
        return self.rows[self.r] if 0 <= self.r < len(self.rows) else None

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
        """Returns None (consumed), or {'kind': 'close'} when the editor ends."""
        if event.type != pygame.KEYDOWN:
            return None   # mouse input intentionally ignored on this screen
        key = event.key
        if key in (pygame.K_ESCAPE, pygame.K_RETURN):
            return {"kind": "close"}
        rows_n = max(1, len(self.rows))
        if key == pygame.K_UP:
            self.r = (self.r - 1) % rows_n
        elif key == pygame.K_DOWN:
            self.r = (self.r + 1) % rows_n
        elif key == pygame.K_BACKSPACE:
            self._backspace()
        else:
            char = getattr(event, "unicode", None) or ""   # defensive: tolerate events w/o .unicode
            if len(char) == 1 and char.isprintable():
                self._type_char(char)
        return None

    def draw(self, screen, font_title, font_item) -> None:
        w, h = screen.get_width(), screen.get_height()
        screen.fill(BG_COLOR)
        title = font_title.render("Edit prompts live (back via ESC / ENTER)", True, TEXT_COLOR)
        screen.blit(title, (20, 14))
        hint = font_item.render(
            "Arrows: pick agent | Type/Backspace: edit prompt | ENTER/ESC: back",
            True, DIM_COLOR)
        screen.blit(hint, (20, 60))
        y = 104
        for i, agent in enumerate(self.rows):
            active = i == self.r
            name_s = font_item.render(f"{agent.name}:", True, TEXT_COLOR if active else DIM_COLOR)
            screen.blit(name_s, (20, y + 2))
            prompt_x = 160
            max_w = max(40, w - prompt_x - 20)
            lines = _wrap(font_item, agent.prompt or "(empty)", max_w)
            line_h = font_item.get_linesize()
            block_h = len(lines) * line_h + 4
            if active:
                pygame.draw.rect(screen, ACTIVE_COLOR,
                                (16, y - 2, w - 32, block_h), width=1)
            for j, ln in enumerate(lines):
                s = font_item.render(ln, True, TEXT_COLOR if active else DIM_COLOR)
                screen.blit(s, (prompt_x, y + 2 + j * line_h))
            y += block_h + 14
