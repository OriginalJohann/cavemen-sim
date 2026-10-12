"""Procedural animals: ice-age megafauna and a dinosaur species.

All animal behaviour is fixed rule logic (wander, resource bias, aggro,
atk) - deliberately NO LLM steering per the project specification.
"""
import random
from ..world.generation import FOREST, GRASS, WATER


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
        # Fish are non-aggressive aquatic animals: dedicated drift/flee logic below;
        # they never chase or attack cavemen.
        if self.kind == "fish":
            return self._step_fish(world, rng)

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

    def _step_fish(self, world, rng):
        """Fish drift: stay on the lake bed and flee from nearby cavemen."""
        event = {"move": False, "attack": None}
        speed = float(self.spec(world.cfg).get("speed", 0.6))
        # Adjacent water tiles (orthogonal keeps fish inside the lake); staying still is allowed.
        options = [(self.x + dx, self.y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                   if world.in_bounds(self.x + dx, self.y + dy) and world.tile(self.x + dx, self.y + dy) == WATER]
        options.append((self.x, self.y))
        # Nearest caveman: within three tiles the fish flees to the farthest option.
        nearest = None
        best = 10 ** 9
        for agent in world.agents:
            if not agent.alive:
                continue
            d = abs(agent.x - self.x) + abs(agent.y - self.y)
            if d < best:
                best, nearest = d, agent
        if nearest is not None and best <= 3:
            nx, ny = max(options, key=lambda p: abs(nearest.x - p[0]) + abs(nearest.y - p[1]))
        else:
            nx, ny = rng.choice(options)
        if (nx, ny) == (self.x, self.y):
            return event              # staying still counts as no movement this tick
        if rng.random() >= speed:
            return event              # slow drift: fish often skip a tick
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
    if kind == "fish":   # aquatic species may only spawn inside the lake
        waters = [(x, y) for x in range(world.w) for y in range(world.h)
                  if world.tile(x, y) == WATER and (x, y) not in occupied]
        if not waters:
            return None
        x, y = rng.choice(waters)
        uid = max([a.uid for a in world.animals], default=0) + 1
        return Animal(uid, kind, x, y)
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
