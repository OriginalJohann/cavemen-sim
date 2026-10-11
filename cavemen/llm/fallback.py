"""Deterministic fallback behaviour for when no LLM endpoint answers.

Guarantees that the simulation keeps running (hunger, aging, reproduction)
even completely offline. The logic is deliberately simple rule prioritisation:
stamina recovery, hunting nearest prey, gathering near forest, going home.
"""
from ..agents.prompts import pick_character
from ..world.generation import FOREST


def _step_toward(x: int, y: int, tx: int, ty: int):
    """One cardinal step from (x,y) toward target (tx,ty); 0/0 when at target."""
    dx = 0 if x == tx else (1 if tx > x else -1)
    dy = 0 if y == ty else (1 if ty > y else -1)
    return dx, dy


def fallback_character(rng, gender: str) -> dict:
    """Seeded name/trait generation used instead of the LLM for new agents."""
    name, trait = pick_character(rng, gender)
    return {"name": name, "trait": trait}


def fallback_action(agent, world) -> dict:
    """Choose a valid action dict for one tick without any LLM call."""
    # 1) exhausted or very safe & well fed -> rest at the spot
    if agent.stamina < 20.0 and agent.hunger >= 80.0:
        return {"action": "rest", "dx": 0, "dy": 0}
    # 2) hungry -> hunt the nearest animal (hunt when adjacent, else walk to it)
    if agent.hunger < 75.0:
        prey = None
        best = 48
        for animal in world.animals:
            if not animal.alive:
                continue
            dist = abs(animal.x - agent.x) + abs(animal.y - agent.y)
            if dist < best:
                best, prey = dist, animal
        if prey is not None:
            if best <= 1:
                return {"action": "hunt", "dx": 0, "dy": 0}
            dx, dy = _step_toward(agent.x, agent.y, prey.x, prey.y)
            return {"action": "move", "dx": dx, "dy": dy}
    # 3) gather food: berry bushes first (finite resource with regrowth),
    #    plain forest tiles as fallback when no berries remain anywhere.
    if agent.hunger <= 90.0:
        target = None
        best = 10 ** 9
        for pos, amount in world.berry_tiles.items():
            if amount > 0:
                dist = abs(pos[0] - agent.x) + abs(pos[1] - agent.y)
                if dist < best:
                    best, target = dist, (int(pos[0]), int(pos[1]))
        if target is None:   # legacy behaviour: flat gather on forest tiles
            best = 9
            for y in range(max(0, agent.y - 8), min(world.h, agent.y + 9)):
                for x in range(max(0, agent.x - 8), min(world.w, agent.x + 9)):
                    if world.tile(x, y) == FOREST:
                        dist = abs(x - agent.x) + abs(y - agent.y)
                        if dist < best:
                            best, target = dist, (x, y)
        if target is not None:
            if best <= 1:
                return {"action": "gather", "dx": 0, "dy": 0}
            dx, dy = _step_toward(agent.x, agent.y, *target)
            return {"action": "move", "dx": dx, "dy": dy}
    # 4) head back to the cave and rest there
    cx, cy = world.cave_center
    if (agent.x, agent.y) != (cx, cy):
        dx, dy = _step_toward(agent.x, agent.y, cx, cy)
        return {"action": "move", "dx": dx, "dy": dy}
    return {"action": "rest", "dx": 0, "dy": 0}
