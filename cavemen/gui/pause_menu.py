"""ESC pause menu opened while the simulation runs.

While it is open, `gui/app.py` suspends the ticking. Three actions are offered:
resume, explicit save + back to the main menu, and the modal live prompt editor
(INSTRUCTIONS §3), now reached from this menu instead of a bare key. Cursor,
keyboard and mouse conventions match the main menu (`menu.py`).
"""
import pygame

from .menu import BG_COLOR, CURSOR_COLOR, ITEM_W, ITEM_X, LINE_H, TEXT_COLOR, TITLE_Y

# first item row: same geometry family as MenuState (below title + hint line)
PAUSE_START_Y = 130


class PauseMenu:
    """Pause overlay menu; handle_event returns the chosen action or None."""

    def __init__(self):
        self.cursor = 0
        # fixed order: resume, save & back to main menu, edit cavemen prompts
        self.items: list[tuple[str, dict]] = [
            ("Weiter (Simulation fortsetzen)", {"kind": "resume"}),
            ("Welt speichern und ins Hauptmenü", {"kind": "save_menu"}),
            ("Prompts der Cavemen bearbeiten", {"kind": "prompts"}),
        ]

    def item_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(ITEM_X, PAUSE_START_Y + index * LINE_H, ITEM_W, LINE_H - 4)

    def handle_event(self, event) -> dict | None:
        """Handle keys/mouse; returns the selected action or None.

        ESC is treated as resume so an accidental ESC can never lose the sim."""
        if event.type == pygame.KEYDOWN:
            key = event.key
            if key == pygame.K_ESCAPE:   # close the pause menu and resume
                return {"kind": "resume"}
            if key == pygame.K_UP:
                self.cursor = (self.cursor - 1) % len(self.items)
            elif key == pygame.K_DOWN:
                self.cursor = (self.cursor + 1) % len(self.items)
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self.items[self.cursor][1]   # confirm the highlighted entry
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            index, _ = divmod(event.pos[1] - PAUSE_START_Y, LINE_H)   # clicked row
            if 0 <= index < len(self.items):
                self.cursor = index
                return self.items[index][1]
        return None

    def draw(self, screen, font_title, font_item) -> None:
        """Full-screen pause overlay (covers the frozen simulation frame)."""
        screen.fill(BG_COLOR)
        title = font_title.render("PAUSE", True, TEXT_COLOR)
        screen.blit(title, ((screen.get_width() - title.get_width()) // 2, TITLE_Y))
        hint = font_item.render(
            "ESC/Weiter=resume | ENTER=auswählen | Pfeile/Maus=navigieren",
            True, (150, 145, 135))
        screen.blit(hint, (ITEM_X, PAUSE_START_Y - LINE_H))
        for i, (label, _action) in enumerate(self.items):
            rect = self.item_rect(i)
            if i == self.cursor:
                pygame.draw.rect(screen, CURSOR_COLOR, rect, width=2)
            surface = font_item.render(label, True, TEXT_COLOR)
            screen.blit(surface, (rect.x + 8, rect.y + 4))
