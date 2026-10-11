"""HUD: agent panel with vitals plus a top world bar.

Left overlay lists every living caveman (name, age, HP/stamina/hunger bars)
and shows the selected agent's current individual prompt and recent life-story
events. Top bar reports day, weather, tribe size and animal count.
"""
import pygame
from ..agents.agent import age_years_of_ticks

PANEL_W = 250


def _bar(screen, rect: pygame.Rect, value_pct: float, color) -> None:
    w = max(1, int(rect.w * max(0.0, min(1.0, value_pct))))
    screen.fill((35, 35, 40), rect)
    screen.fill(color, pygame.Rect(rect.x, rect.y, w, rect.h))


def draw_top_bar(screen, world, font) -> None:
    """One-line status: day, weather, tribe size (max from config), animals, berries."""
    max_agents = int(world.cfg.get("simulation.max_agents_per_world", 10))
    alive = sum(1 for a in world.agents if a.alive)
    animals = sum(1 for a in world.animals if a.alive)
    berries = sum(world.berry_tiles.values())   # total harvestable berries left
    text = (f"Tag {world.day_number()} | Wetter: {world.weather['state']} | "
            f"Stamm: {alive}/{max_agents} | Tiere: {animals} | Beeren: {berries}")
    surface = font.render(text, True, (235, 230, 215))
    screen.blit(surface, (8, 6))


def draw_panel(screen, world, selected_uid, font) -> None:
    """Left panel: vitals of all agents; bottom shows prompt + story of one."""
    rect = pygame.Rect(0, 24, PANEL_W, screen.get_height() - 24)
    overlay = pygame.Surface((PANEL_W, rect.h), flags=pygame.SRCALPHA)
    overlay.fill((15, 18, 22, 190))
    screen.blit(overlay, (rect.x, rect.y))
    y = rect.y + 6
    for agent in world.agents:
        if not agent.alive:
            continue
        age_years = int(agent.age_years(world.cfg))
        line = font.render(f"{agent.name} ({age_years} J.)", True, (235, 230, 215))
        screen.blit(line, (rect.x + 8, y))
        if agent.uid == selected_uid:
            hi = pygame.Rect(rect.x, y - 2, PANEL_W, line.get_height() + 4)
            pygame.draw.rect(screen, (90, 160, 210), hi, width=1)
        y += line.get_height() + 2
        for label, value, color in (
                ("HP", agent.hp / 100.0, (90, 200, 90)),
                ("STA", agent.stamina / 100.0, (235, 200, 90)),
                ("HUNGER", agent.hunger / 100.0, (210, 120, 80))):
            label_surface = font.render(label, True, (200, 195, 185))
            screen.blit(label_surface, (rect.x + 8, y))
            _bar(screen, pygame.Rect(rect.x + 46, y + 3, PANEL_W - 54, 7), value, color)
        y += 12
    # selected agent: current individual prompt + last life-story events
    selected = next((a for a in world.agents if a.uid == selected_uid), None)
    if selected is None:
        return   # panel shows the agent list only
    y += 4
    title = font.render("Prompt:", True, (235, 200, 120))
    screen.blit(title, (rect.x + 8, y))
    y += title.get_height() + 2
    for ln in _wrap(font, selected.prompt, PANEL_W - 16):
        s = font.render(ln, True, (235, 230, 215))
        screen.blit(s, (rect.x + 8, y))
        y += s.get_height() + 1
    y += 4
    title = font.render("Lebensgeschichte:", True, (160, 200, 235))
    screen.blit(title, (rect.x + 8, y))
    y += title.get_height() + 2
    for day, text in list(selected.story)[-3:]:   # only the latest events fit
        s = font.render(f"T{day}: {text}", True, (210, 205, 195))
        screen.blit(s, (rect.x + 8, y))
        y += s.get_height() + 1


def _wrap(font, text: str, width_px: int) -> list:
    """Wrap one string into pixel-width-bounded lines using the font metrics."""
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
