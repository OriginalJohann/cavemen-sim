"""HUD: fixed left sidebar next to the world canvas (Phase 14).

The sidebar shows the world info as separate readable lines (day, weather,
tribe size, animals, fish, berries) and below that the agent panel with
vitals plus the selected agent's current individual prompt and recent
life-story events. The world canvas is rendered to its right via
renderer.draw_world(..., offset_x=panel_w), so neither overlaps the map.
"""
import pygame
from ..agents.agent import age_years_of_ticks

MIN_PANEL_W = 120   # narrowest usable sidebar; keeps the text block readable


def side_panel_width(window_w: int, requested: int) -> int:
    """Clamp the sidebar width so panel + canvas always fit into the window.

    Pure geometry (no pygame), unit-testable headlessly: MIN_PANEL_W <= result
    and result < window; the world canvas starts at x = result with zero
    overlap onto the sidebar.
    """
    req = max(MIN_PANEL_W, int(requested))
    return min(req, max(MIN_PANEL_W, int(window_w) - 80))


def _bar(screen, rect: pygame.Rect, value_pct: float, color) -> None:
    w = max(1, int(rect.w * max(0.0, min(1.0, value_pct))))
    screen.fill((35, 35, 40), rect)
    screen.fill(color, pygame.Rect(rect.x, rect.y, w, rect.h))


def draw_world_info_block(screen, world, x: int, y: int, font) -> int:
    """World info as separate lines (better legibility than the old one-liner).

    Returns the next free y coordinate after the last line.
    """
    max_agents = int(world.cfg.get("simulation.max_agents_per_world", 10))
    alive = sum(1 for a in world.agents if a.alive)
    animals = sum(1 for a in world.animals if a.alive)
    fish = sum(1 for a in world.animals if a.alive and a.kind == "fish")
    berries = sum(world.berry_tiles.values())   # total harvestable berries left
    rows = (
        f"Day {world.day_number()}",
        f"Weather: {world.weather['state']}",
        f"Tribe: {alive}/{max_agents}",
        f"Animals: {animals}",
        f"Fish: {fish}",
        f"Berries: {berries}",
    )
    y += 8
    for row in rows:
        s = font.render(row, True, (235, 230, 215))
        screen.blit(s, (x + 10, y))
        y += max(16, s.get_height()) + 2
    return y


def _draw_agent_entries(screen, world, selected_uid, font, rect: pygame.Rect, y: int) -> None:
    """Agent vitals list plus prompt/story of the selected agent (was draw_panel)."""
    for agent in world.agents:
        if not agent.alive:
            continue
        age_years = int(agent.age_years(world.cfg))
        line = font.render(f"{agent.name} (age {age_years})", True, (235, 230, 215))
        screen.blit(line, (rect.x + 8, y))
        if agent.uid == selected_uid:
            hi = pygame.Rect(rect.x, y - 2, rect.w, line.get_height() + 4)
            pygame.draw.rect(screen, (90, 160, 210), hi, width=1)
        y += line.get_height() + 2
        for label, value, color in (
                ("HP", agent.hp / 100.0, (90, 200, 90)),
                ("STA", agent.stamina / 100.0, (235, 200, 90)),
                ("HUNGER", agent.hunger / 100.0, (210, 120, 80))):
            label_surface = font.render(label, True, (200, 195, 185))
            screen.blit(label_surface, (rect.x + 8, y))
            _bar(screen, pygame.Rect(rect.x + 46, y + 3, rect.w - 54, 7), value, color)
        y += 12
    # selected agent: current individual prompt + last life-story events
    selected = next((a for a in world.agents if a.uid == selected_uid), None)
    if selected is None:
        return   # panel shows the agent list only
    y += 4
    title = font.render("Prompt:", True, (235, 200, 120))
    screen.blit(title, (rect.x + 8, y))
    y += title.get_height() + 2
    for ln in _wrap(font, selected.prompt, rect.w - 16):
        s = font.render(ln, True, (235, 230, 215))
        screen.blit(s, (rect.x + 8, y))
        y += s.get_height() + 1
    y += 4
    title = font.render("Life story:", True, (160, 200, 235))
    screen.blit(title, (rect.x + 8, y))
    y += title.get_height() + 2
    for day, text in list(selected.story)[-3:]:   # only the latest events fit
        s = font.render(f"T{day}: {text}", True, (210, 205, 195))
        screen.blit(s, (rect.x + 8, y))
        y += s.get_height() + 1


def draw_side_panel(screen, world, selected_uid, font, panel_w: int) -> None:
    """Full-height left sidebar next to the canvas (Phase 14): world info lines
    on top, agent vitals / prompt / life story below."""
    win_h = screen.get_height()
    rect = pygame.Rect(0, 0, max(1, int(panel_w)), win_h)
    overlay = pygame.Surface((rect.w, win_h), flags=pygame.SRCALPHA)
    overlay.fill((15, 18, 22, 220))
    screen.blit(overlay, (rect.x, rect.y))
    y_next = draw_world_info_block(screen, world, rect.x, rect.y, font)
    pygame.draw.line(screen, (90, 160, 210),
                     (rect.x + 4, y_next), (rect.x + rect.w - 4, y_next))
    _draw_agent_entries(screen, world, selected_uid, font, rect, y_next + 8)


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
