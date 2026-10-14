"""Procedural world generation and the World state container.

A world is a small tile grid. The tribe always starts inside a cave
in the map center; forest patches, one water lake and sparse rock are
placed deterministically from the world seed (reproducible worlds).
"""
import random

CAVE = 0
GRASS = 1
FOREST = 2
WATER = 3
ROCK = 4
TILE_NAMES = ["cave", "grass", "forest", "water", "rock"]
WALKABLE_TILES = {CAVE, GRASS, FOREST}


def generate_tiles(width: int, height: int, rng: random.Random):
    """Create the tile grid plus cave center. Fully deterministic for a seed."""
    tiles = [[GRASS] * width for _ in range(height)]
    cx, cy = width // 2, height // 2
    cave_radius = max(2, min(4, width // 12))
    # Central cave: the tribe's starting home.
    for y in range(height):
        for x in range(width):
            if (x - cx) ** 2 + (y - cy) ** 2 <= cave_radius ** 2:
                tiles[y][x] = CAVE
    # Forest patches: gathering resources, spread across the map.
    for _ in range(6):
        fx, fy = rng.randint(3, width - 4), rng.randint(3, height - 4)
        fr = rng.randint(1, 2)
        if (fx - cx) ** 2 + (fy - cy) ** 2 <= cave_radius ** 2:
            continue  # keep the cave clear
        for x in range(max(0, fx - fr), min(width, fx + fr + 1)):
            for y in range(max(0, fy - fr), min(height, fy + fr + 1)):
                if tiles[y][x] != CAVE:
                    tiles[y][x] = FOREST
    # One water lake, kept away from the cave (a few retries).
    for _ in range(24):
        lx, ly = rng.randint(4, width - 5), rng.randint(4, height - 5)
        if (lx - cx) ** 2 + (ly - cy) ** 2 > (cave_radius + 3) ** 2:
            break
    for x in range(max(0, lx - 2), min(width, lx + 3)):
        for y in range(max(0, ly - 2), min(height, ly + 3)):
            if (x - lx) ** 2 + (y - ly) ** 2 <= 4 and tiles[y][x] != CAVE:
                tiles[y][x] = WATER
    # Sparse rocks: obstacles, purely decorative gameplay texture.
    for y in range(height):
        for x in range(width):
            if tiles[y][x] == GRASS and rng.random() < 0.04:
                tiles[y][x] = ROCK
    return tiles, (cx, cy)


def place_berry_bushes(tiles, width: int, height: int, seed: int,
                       count: int, max_amount: int) -> dict:
    """Deterministic berry-bush layout for a world.

    Berries grow on forest tiles (grass is the fallback when fewer than `count`
    forest tiles exist). A dedicated seeded RNG - independent of the main sim
    stream - keeps the layout reproducible per world seed, so legacy saves
    without an explicit "berries" payload can be rebuilt identically.
    """
    rng = random.Random(f"{int(seed)}-berries")
    forest = [(x, y) for y in range(height) for x in range(width) if tiles[y][x] == FOREST]
    fallback = [(x, y) for y in range(height) for x in range(width) if tiles[y][x] == GRASS]
    candidates = forest + fallback      # deterministic order before shuffling
    rng.shuffle(candidates)
    return {pos: max_amount for pos in candidates[:max(0, count)]}


class World:
    """Runtime state of one simulated world (map, time, actors)."""

    def __init__(self, cfg, seed=None, name="world"):
        from ..agents.agent import Agent  # lazy import to avoid cycles
        self.cfg = cfg
        self.name = str(name)
        self.seed = int(seed) if seed is not None else random.randrange(1 << 30)
        self.w = int(cfg.get("worlds.size.tiles_w"))
        self.h = int(cfg.get("worlds.size.tiles_h"))
        self.rng = random.Random(self.seed)
        self.tick = 0
        self.weather = {"state": "mild", "left": 0}  # driven by rules each tick
        self.tiles, self.cave_center = generate_tiles(self.w, self.h, self.rng)
        # Berry bushes (foraging without hunting): deterministic per seed; only the
        # *amounts* are mutable state and get serialized together with the world.
        self.berry_tiles = place_berry_bushes(
            self.tiles, self.w, self.h, self.seed,
            int(self.cfg.get("worlds.gather.berry_count", 14)),
            max(0, int(self.cfg.get("worlds.gather.max_amount", 6))))
        self.agents: list[Agent] = []
        self.animals = []  # filled by spawn logic and from_dict

    def in_bounds(self, x, y) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def tile(self, x, y):
        return self.tiles[y][x]

    def walkable(self, x, y) -> bool:
        return self.in_bounds(x, y) and self.tile(x, y) in WALKABLE_TILES

    def day_number(self) -> int:
        """1-based sim-day derived from the tick counter."""
        tpd = max(1, int(self.cfg.get("simulation.ticks_per_day", 24)))
        return self.tick // tpd + 1

    def age_years_of_ticks(self, ticks: float) -> float:
        """Convert sim-ticks to compressed calendar years."""
        per_year = max(1, int(self.cfg.get("simulation.ticks_per_day", 24))
                        * int(self.cfg.get("simulation.days_per_year", 36)))
        return ticks / per_year

    def to_dict(self) -> dict:
        """Full serializable snapshot for the world save files (slot max. 3)."""
        return {
            "version": 1,
            "name": self.name,
            "seed": self.seed,
            "w": self.w,
            "h": self.h,
            "tick": self.tick,
            "weather": dict(self.weather),
            "cave_center": list(self.cave_center),
            "tiles": [list(row) for row in self.tiles],
            "berries": [[int(x), int(y), int(amount)]
                        for (x, y), amount in sorted(self.berry_tiles.items()) if amount > 0],
            "agents": [a.to_dict() for a in self.agents],
            "animals": [an.to_dict() for an in self.animals],
        }

    @classmethod
    def from_dict(cls, data: dict, cfg) -> "World":
        """Rebuild a world from a saved snapshot (inverse of to_dict)."""
        world = cls.__new__(cls)
        world.cfg = cfg
        world.name = data["name"]
        world.seed = int(data["seed"])
        world.w, world.h = int(data["w"]), int(data["h"])
        world.rng = random.Random(world.seed)  # continue reproducible RNG stream
        world.tick = int(data.get("tick", 0))
        world.weather = dict(data.get("weather", {"state": "mild", "left": 0}))
        world.cave_center = tuple(data["cave_center"])
        world.tiles = [list(row) for row in data["tiles"]]
        # Berry bushes; legacy saves predate the berry system -> rebuild full bushes
        # deterministically from the world seed (nothing was ever harvested there).
        saved_berries = data.get("berries")
        if saved_berries is None:
            world.berry_tiles = place_berry_bushes(
                world.tiles, world.w, world.h, int(data["seed"]),
                int(world.cfg.get("worlds.gather.berry_count", 14)),
                max(0, int(world.cfg.get("worlds.gather.max_amount", 6))))
        else:
            world.berry_tiles = {(int(x), int(y)): int(a) for x, y, a in saved_berries
                                 if int(a) > 0}
        from ..agents.agent import Agent
        from ..animals.animals import Animal
        world.agents = [Agent.from_dict(a, cfg) for a in data.get("agents", [])]
        world.animals = [Animal.from_dict(an) for an in data.get("animals", [])]
        return world
