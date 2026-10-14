"""Top-down pixel-art renderer in retro Core-Keeper style.

Tiny flat colours per tile (16px default), tiny sprites for agents and
animals, camera follows the tribe with clamping to map bounds. No external
assets: everything is drawn procedurally from rects and dots, so the GUI
works fully offline.
"""
import pygame
from ..world.generation import CAVE, GRASS, FOREST, WATER, ROCK

TILE_COLORS = {CAVE: (107, 79, 58), GRASS: (95, 168, 88),
               FOREST: (43, 92, 60), WATER: (70, 130, 180), ROCK: (130, 128, 120)}
ANIMAL_COLORS = {"mammut": (150, 120, 90), "hoehlenbaer": (110, 75, 60),
                  "wolf": (130, 130, 140), "triceratops": (80, 140, 90)}
AGENT_COLORS = {"m": (185, 80, 60), "f": (70, 120, 175)}
BERRY_COLOR = (148, 42, 68)


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def camera_position(world, window_w: int, tile_px: int) -> tuple:
    """Camera top-left pixel offset (x component; y is computed the same way)."""
    map_w = world.w * tile_px
    view_w = min(window_w, map_w)
    agents = [a for a in world.agents if a.alive]
    cx = sum(a.x for a in agents) / len(agents) if agents else world.cave_center[0]
    return _clamp(int(cx * tile_px - view_w // 2), 0, map_w - view_w)


def draw_world(screen, world, window_h: int, tile_px: int, font=None, offset_x=0) -> None:
    """Draw the visible part of the map plus animals and agents - and bubbles.

    An optional `font` enables drawing transient conversation bubbles above
    speaking agents (INSTRUCTIONS §3); without it the function is unchanged.
    `offset_x` shifts all rendering right by that many pixels so a fixed left
    sidebar for the world info can sit outside the canvas (Phase 14).
    """
    tile = max(2, int(tile_px))
    win_w, win_h = screen.get_width(), window_h
    offset_x = max(0, int(offset_x))      # reserved area left of the canvas (sidebar)
    map_w, map_h = world.w * tile, world.h * tile
    view_w, view_h = min(max(1, win_w - offset_x), map_w), min(win_h, map_h)
    agents = [a for a in world.agents if a.alive]
    if agents:
        cx = sum(a.x for a in agents) / len(agents)
        cy = sum(a.y for a in agents) / len(agents)
    else:
        cx, cy = world.cave_center
    cam_x = _clamp(int(cx * tile - view_w // 2), 0, map_w - view_w)
    cam_y = _clamp(int(cy * tile - view_h // 2), 0, max(0, map_h - view_h))
    # ---- tiles (subtle checker shade for depth on grass) --------------------
    x0, y0 = cam_x // tile, cam_y // tile
    for ty in range(y0, min(world.h, y0 + win_h // tile + 1)):
        for tx in range(x0, min(world.w, x0 + win_w // tile + 1)):
            t = world.tile(tx, ty)
            color = TILE_COLORS[t]
            if t == GRASS and (tx + ty) % 2 == 1:   # checker variation
                color = tuple(max(0, c - 8) for c in color)
            screen.fill(color, pygame.Rect((tx - x0) * tile + offset_x, (ty - y0) * tile, tile, tile))
    # ---- berry bushes (dark-red dots scaled by remaining berries) ----------
    for pos, amount in world.berry_tiles.items():
        if amount <= 0:
            continue
        px = int(pos[0] * tile) - cam_x + offset_x
        py = int(pos[1] * tile) - cam_y
        if not (-tile <= px < view_w and -tile <= py < view_h):   # skip off-screen
            continue
        dots = max(1, (amount + 1) // 2)      # up to three dots for a full bush
        size = max(2, tile // 4)
        for offx, offy in ((2, 2), (tile - size - 2, 2), (size, tile - size - 2))[:dots]:
            screen.fill(BERRY_COLOR, pygame.Rect(px + offx, py + offy, size, size))
    # ---- animals (square body scaled by size + white eye dot) --------------
    for animal in world.animals:
        if not animal.alive:
            continue
        px = int(animal.x * tile) - cam_x + offset_x
        py = int(animal.y * tile) - cam_y
        side = max(3, min(tile, (tile * animal.size(world.cfg)) // 2 + 2))
        color = ANIMAL_COLORS.get(animal.kind, (150, 90, 60))
        body = pygame.Rect(px + (tile - side) // 2, py + (tile - side) // 2, side, side)
        screen.fill(color, body)
        screen.fill((240, 240, 235), pygame.Rect(body.x + 1, body.y + 1, 2, 2))
    # ---- agents (body by gender colour, head dot, HP bar on top) -----------
    for agent in world.agents:
        if not agent.alive:
            continue
        px = int(agent.x * tile) - cam_x + offset_x
        py = int(agent.y * tile) - cam_y
        body = pygame.Rect(px + (tile * 2 // 5), py + (tile * 2 // 5),
                           tile * 3 // 5, tile * 3 // 5)
        screen.fill(AGENT_COLORS.get(agent.gender, (170, 90, 60)), body)
        head = max(2, tile // 4)
        screen.fill((240, 240, 235),
                    pygame.Rect(body.x + body.w // 2 - head // 2, body.y - head, head, head))
        bar_w = int(tile * max(0.0, min(1.0, agent.hp / 100.0)))
        color = (90, 200, 90) if agent.hp > 50 else (210, 80, 70)
        screen.fill((30, 30, 30), pygame.Rect(px, py - 4, tile, 3))
        screen.fill(color, pygame.Rect(px, py - 4, bar_w, 3))
    # ---- speech bubbles above speaking agents (transient conversation) ------
    if font is not None:
        bubble_ticks = max(1, int(world.cfg.get("agents.conversation.bubble_ticks", 16)))
        for agent in world.agents:
            if not agent.alive or not agent.current_bubble:
                continue
            age = world.tick - int(agent.bubble_start_tick)
            if age > bubble_ticks:       # bubble expired -> no longer drawn
                continue
            lines, current = [], ""      # wrap the line into <= ~150px rows
            for word in str(agent.current_bubble).split():
                candidate = f"{current} {word}".strip()
                if font.size(candidate)[0] > 150 and current:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            if current:
                lines.append(current)
            line_h = max(8, font.get_linesize())
            pad_x, pad_y = 8, 6
            w = max([font.size(l)[0] for l in lines], default=10) + 2 * pad_x
            h = len(lines) * line_h + 2 * pad_y
            surf = pygame.Surface((w, h), flags=pygame.SRCALPHA)
            surf.fill((250, 246, 238, 235))
            for i, ln in enumerate(lines):
                t = font.render(ln, True, (40, 35, 30))
                offset_x = pad_x + max(0, (w - 2 * pad_x - t.get_width()) // 2)
                surf.blit(t, (offset_x, pad_y + i * line_h))
            pygame.draw.rect(surf, (60, 50, 40), pygame.Rect(0, 0, w, h), width=1)
            px = int(agent.x * tile) - cam_x
            py = int(agent.y * tile) - cam_y
            bx = _clamp(px + tile // 2 - w // 2, offset_x, offset_x + max(0, view_w - w))   # clamped to canvas
            by = _clamp(py - 6 - h, 0, max(0, view_h - h))                # above the HP bar
            screen.blit(surf, (bx, by))
