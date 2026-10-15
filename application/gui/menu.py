"""Main menu: choose a world slot - new, load or explicit overwrite - plus exit.

Menu items are derived from the existing save files (max. three slots per
config). Overwriting an occupied slot is only possible via its dedicated menu
entry, which matches the "overwrite on explicit request" requirement.
"""
import pygame
from ..world import save_load

BG_COLOR = (16, 20, 24)
TEXT_COLOR = (235, 230, 215)
CURSOR_COLOR = (90, 160, 210)
TITLE_Y = 70      # vertical centre of the title line
ITEM_X = 50       # left edge of menu items
ITEM_W = 460      # width used for cursor highlight and click hit area
ITEM_START_Y = 130  # top of the first item row
LINE_H = 28       # vertical step per menu item


class MenuState:
    def __init__(self, cfg):
        self.cfg = cfg
        self.cursor = 0
        self._rebuild()

    def _rebuild(self) -> None:
        max_worlds = int(self.cfg.get("worlds.max_worlds", 3))
        try:
            slots = save_load.list_slots(self.cfg)
        except save_load.SaveError:   # unreadable saves are simply not offered
            slots = {}
        self.items: list[tuple[str, dict]] = []
        for slot in range(1, max_worlds + 1):
            if slot in slots:
                meta = slots[slot]
                # Phase 16 (Seeding): show the world generation seed so reproducible runs are verifiable at a glance
                label = f"Load World {slot} ({meta['name']}, Tick {meta['tick']}, Seed {meta.get('seed', '?')})"
                self.items.append((label, {"kind": "load", "slot": slot}))
                overwrite = f"Overwrite slot {slot} (explicit)"
                self.items.append((overwrite, {"kind": "overwrite", "slot": slot}))
            else:
                self.items.append((f"New world in slot {slot}",
                                   {"kind": "new", "slot": slot}))
        self.items.append(("Edit settings", {"kind": "config"}))   # global config editor overlay
        self.items.append(("Quit", {"kind": "quit", "slot": None}))

    def item_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(ITEM_X, ITEM_START_Y + index * LINE_H, ITEM_W, LINE_H - 4)

    def handle_event(self, event) -> dict | None:
        """Handle keys/mouse; returns the selected action or None."""
        if event.type == pygame.KEYDOWN:
            key = event.key
            if key == pygame.K_UP:
                self.cursor = (self.cursor - 1) % len(self.items)
            elif key == pygame.K_DOWN:
                self.cursor = (self.cursor + 1) % len(self.items)
            elif key == pygame.K_ESCAPE:
                return {"kind": "quit", "slot": None}
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                # confirm the highlighted menu entry (keyboard-only flow)
                return self.items[self.cursor][1]
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            index, y0 = divmod(event.pos[1] - ITEM_START_Y, LINE_H)   # clicked row
            if 0 <= index < len(self.items):
                self.cursor = index
                return self.items[index][1]
        return None

    def draw(self, screen, font_title, font_item) -> None:
        """Draw title + items with a cursor highlight (keyboard or mouse)."""
        screen.fill(BG_COLOR)
        title = font_title.render("CAVMEN", True, TEXT_COLOR)
        screen.blit(title, ((screen.get_width() - title.get_width()) // 2, TITLE_Y))
        hint = font_item.render("Choose a world (arrows, ENTER=start, ESC=back)", True, (150, 145, 135))
        screen.blit(hint, (ITEM_X, ITEM_START_Y - LINE_H))
        for i, (label, _action) in enumerate(self.items):
            rect = self.item_rect(i)
            if i == self.cursor:
                pygame.draw.rect(screen, CURSOR_COLOR, rect, width=2)
            surface = font_item.render(label, True, TEXT_COLOR)
            screen.blit(surface, (rect.x + 8, rect.y + 4))
