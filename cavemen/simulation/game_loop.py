"""Simulation orchestrator: world creation, initial tribe and the tick loop.

The GUI and headless tests both drive this class. The LLM client is created
here (optional); every agent decision degrades to fallback rules when no
endpoint answers, so an offline run behaves exactly like an online one.
"""
from ..agents.agent import Agent
from ..agents.prompts import clip, make_initial_prompt, pick_character
from ..animals.animals import spawn_animal
from ..llm.client import LLMClient
from .rules import run_tick


class Simulation:
    def __init__(self, cfg, world=None, llm_enabled: bool = True):
        if world is None:
            raise ValueError("Simulation needs a World instance (use new_world()).")
        self.cfg = cfg
        self.world = world
        self.llm = LLMClient(cfg) if llm_enabled else None

    @classmethod
    def new_world(cls, cfg, slot: int = 0, seed=None, name="world",
                  llm_enabled: bool = True, roster=None) -> "Simulation":
        from ..world.generation import World
        sim = cls(cfg, world=World(cfg, seed=seed, name=name), llm_enabled=llm_enabled)
        # Manual roster (GUI setup screen) takes precedence over the legacy auto-tribe;
        # all fields are user-specified there, so no LLM character queries happen here.
        if roster:
            sim._spawn_from_roster(roster)
        else:
            sim._spawn_initial_tribe()
        # Initial prey herd: without it the tribe would starve before any
        # animal spawned on its own (hard-coded small count by design).
        rng = sim.world.rng
        for _ in range(8):
            animal = spawn_animal(sim.world, rng)
            if animal is not None:
                sim.world.animals.append(animal)
        return sim

    # ---- initial tribe ------------------------------------------------------
    def _cave_spots(self) -> list[tuple[int, int]]:
        """Walkable cave tiles around the centre for spreading out the tribe."""
        world = self.world
        cx, cy = world.cave_center
        spots = []
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                nx, ny = cx + dx, cy + dy
                if world.walkable(nx, ny) and (dx or dy):
                    spots.append((nx, ny))
        spots.append((cx, cy))
        return spots

    def _spawn_initial_tribe(self) -> None:
        """Start the tribe with up to max. members: 5 men + 5 women (config cap)."""
        world = self.world
        cfg = self.cfg
        rng = world.rng
        max_agents = int(cfg.get("simulation.max_agents_per_world", 10))
        cap = int(cfg.get("agents.prompts.init_max_chars", 100))
        cooldown = max(1, int(cfg.get("llm.decision_cooldown_ticks", 6)))
        per_year = int(cfg.get("simulation.ticks_per_day", 24)) * int(cfg.get("simulation.days_per_year", 36))
        spots = self._cave_spots()
        uid = 0
        for i in range(max_agents):
            gender = "m" if i % 2 == 0 else "f"   # balanced start: 5 men + 5 women
            char = None
            if self.llm is not None:
                char = self.llm.make_character(gender)   # individual prompt via LLM
            if char is None:
                name, trait = pick_character(rng, gender); char = {"name": name, "trait": trait}
            age_years = rng.uniform(16.0, 34.0)
            uid += 1
            spot = spots[i % len(spots)]
            agent = Agent(uid, char["name"], gender, spot[0], spot[1],
                          age_ticks=age_years * per_year,
                          prompt=make_initial_prompt(char["name"], int(age_years), gender,
                                                    char["trait"], cap))
            agent.add_story(1, "arrived with the tribe in the cave")
            agent.next_decision_tick = rng.randrange(cooldown)  # stagger LLM queries
            world.agents.append(agent)

    def _spawn_from_roster(self, roster: list) -> None:
        """Spawn exactly the manually entered tribe members onto cave spots.

        Roster entries are dicts {name, gender, age_years, prompt} coming from
        the GUI setup screen; values are defensively clipped/clamped so a
        malformed entry can never break world generation or the sim loop.
        """
        world = self.world
        cfg = self.cfg
        rng = world.rng
        max_agents = int(cfg.get("simulation.max_agents_per_world", 10))
        cap = int(cfg.get("agents.prompts.init_max_chars", 100))
        cooldown = max(1, int(cfg.get("llm.decision_cooldown_ticks", 6)))
        per_year = int(cfg.get("simulation.ticks_per_day", 24)) * int(cfg.get("simulation.days_per_year", 36))
        min_age = float(cfg.get("agents.age.child_until_years", 5))
        max_age = float(cfg.get("agents.age.death_age_limit", 70))
        spots = self._cave_spots()
        entries = [e for e in roster if isinstance(e, dict)][:max_agents]
        uid = 0
        for i, entry in enumerate(entries):
            uid += 1
            gender = "f" if str(entry.get("gender", "")).strip().lower() in ("f", "female") else "m"
            name = str(entry.get("name", "")).strip()[:8] or f"Gast{uid}"   # hard cap: 8 chars
            try:
                age_years = float(entry.get("age_years", 20.0))
            except (TypeError, ValueError):
                age_years = 20.0
            age_years = min(max_age, max(min_age, age_years))   # clamp into valid range
            prompt = clip(str(entry.get("prompt", "")), cap)     # hard character cap
            spot = spots[i % len(spots)]
            agent = Agent(uid, name, gender, spot[0], spot[1],
                          age_ticks=age_years * per_year, prompt=prompt)
            agent.add_story(1, "arrived with the tribe in the cave")
            agent.next_decision_tick = rng.randrange(cooldown)   # stagger first decisions
            world.agents.append(agent)
    def tick(self) -> dict:
        """Advance one simulation tick; returns event counters."""
        return run_tick(self.world, self.llm)

    def snapshot(self) -> dict:
        """Compact summary used by GUI HUD and headless tests."""
        world = self.world
        alive = [a for a in world.agents if a.alive]
        return {
            "day": world.day_number(),
            "tick": world.tick,
            "weather": world.weather["state"],
            "alive_agents": len(alive),
            "animals": sum(1 for a in world.animals if a.alive),
        }

    def run_headless(self, n_ticks: int) -> list:
        """Run N ticks without any GUI and return periodic snapshots (debug/test)."""
        reports = []
        for i in range(max(0, int(n_ticks))):
            self.tick()
            if i % 50 == 49 or i == n_ticks - 1:
                reports.append(self.snapshot())
        return reports
