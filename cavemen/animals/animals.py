"""Procedural animals: ice-age megafauna and a dinosaur species.

All animal behaviour is fixed rule logic (wander, resource bias, aggro,
atk) - deliberately NO LLM steering per the project specification.
"""
import random
from ..world.generation import FOREST, GRASS


class Animal:
    def __init__(self, uid: int, kind: str, x: int, y: int):
        self.uid = int(uid)
        self.kind = str(kind)          # e.g. 'mammut', 'wolf', 'triceratops'
        self.x, self.y = int(x), int(y)
        spec_size = 1
        self.hp = float(20 + spec_size * 10)
        self.alive = True

    def spec(self, cfg) -> dict:
        """Configured behaviour parameters of this species."""
        return dict(cfg.get(f"animals.types.{self.kind}", {}))

    def size(self, cfg) -> int:
        return max(1, int(self.spec(cfg).get("size", 1)))

    # ---- procedural per-tick behaviour ---------------------------------------
    def step(self, world, rng: random.Random):
        """Advance one tick. Returns events: {'move': bool, 'attack': (agent_uid, dmg)}."""
        spec = self.spec(world.cfg)
        speed = float(spec.get("speed", 0.3))
        aggro = float(spec.get("aggro_chance", 0.1))
        size = self.size(world.cfg)
        event = {"move": False, "attack": None}

        # Find nearest living caveman within sight radius.
        target = None
        best = 11
        for agent in world.agents:
            if not agent.alive:
                continue
            dist = abs(agent.x - self.x) + abs(agent.y - self.y)
            if dist < best:
                best, target = dist, agent
        chasing = False
        if target is not None and rng.random() < aggro:
            chasing = True
            if best <= size:      # contact reached -> deal damage this tick
                event["attack"] = (target.uid, float(spec.get("hunt_damage", 5)))
                return event
        # Move towards target while chasing, else wander with resource bias.
        candidates = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = self.x + dx, self.y + dy
                if world.walkable(nx, ny) and (dx or dy):
                    candidates.append((nx, ny))
        if not candidates:
            return event
        if chasing:
            nx, ny = min(candidates, key=lambda p: abs(p[0] - target.x) + abs(p[1] - target.y))
        else:
            forests = [p for p in candidates if world.tile(*p) == FOREST]
            grasses = [p for p in candidates if world.tile(*p) == GRASS]
            pool = (forests or grasses or candidates)
            nx, ny = rng.choice(pool)
        if not chasing and rng.random() >= speed:
            return event            # slow species often skip a tick
        self.x, self.y = nx, ny
        event["move"] = True
        return event

    def to_dict(self) -> dict:
        return {"uid": self.uid, "kind": self.kind, "x": self.x, "y": self.y,
                "hp": round(self.hp, 2), "alive": self.alive}

    @classmethod
    def from_dict(cls, data: dict) -> "Animal":
        animal = cls(data["uid"], data["kind"], data["x"], data["y"])
        animal.hp = float(data.get("hp", 30.0))
        animal.alive = bool(data.get("alive", True))
        return animal


def spawn_animal(world, rng: random.Random):
    """Spawn one procedural animal at a wild tile away from the cave."""
    cfg = world.cfg
    types = dict(cfg.get("animals.types", {}))
    if not types or len([a for a in world.animals if a.alive]) >= int(cfg.get("animals.max_alive", 12)):
        return None
    weights = [(k, max(0.0, float(v.get("weight", 1)))) for k, v in types.items()]
    total = sum(w for _, w in weights)
    roll = rng.random() * total
    acc, kind = 0.0, next(iter(types))
    for name, w in weights:
        acc += w
        if roll <= acc:
            kind = name
            break
    occupied = {(a.x, a.y) for a in world.animals}
    cave_x, cave_y = world.cave_center
    min_dist = int(cfg.get("animals.spawn_radius_min_from_cave_tiles", 4))
    for _ in range(64):
        x = rng.randrange(world.w)
        y = rng.randrange(world.h)
        if not world.walkable(x, y) or (x, y) in occupied:
            continue
        if abs(x - cave_x) + abs(y - cave_y) < min_dist:
            continue
        uid = max([a.uid for a in world.animals], default=0) + 1
        return Animal(uid, kind, x, y)
    return None
