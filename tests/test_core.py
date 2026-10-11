"""Core-functionality smoke tests without the GUI.

Run: python -m unittest discover -s tests
Covers the main requirements end-to-end: deterministic generation, offline
fallback behaviour (no LLM), vitals/aging, reproduction cap of 10 agents,
prompt length limits, save round-trips and the graceful LLM failure path.
"""
import os
import random
import shutil
import tempfile
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ["PYTHONPATH"] = REPO   # make 'cavemen' importable in any cwd
from cavemen.agents.agent import Agent          # noqa: E402
from cavemen.config import ConfigError, Config  # noqa: E402
from cavemen.llm.client import LLMClient        # noqa: E402
from cavemen.llm.fallback import fallback_action, fallback_character  # noqa: E402
from cavemen.simulation.game_loop import Simulation   # noqa: E402
from cavemen.simulation.rules import _reproduce, _regrow_berries, _step_agent   # noqa: E402
from cavemen.simulation.conversations import try_conversation                  # noqa: E402
from cavemen.gui.prompt_editor import PromptEditor                            # noqa: E402
from cavemen.world.generation import World         # noqa: E402
from cavemen.world import save_load                # noqa: E402


def base_config() -> dict:
    return Config(os.path.join(REPO, "config.yaml"))


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = base_config()

    # ---- generation --------------------------------------------------------
    def test_generation_is_deterministic_for_same_seed(self):
        w1 = World(self.cfg, seed=42)
        w2 = World(self.cfg, seed=42)
        self.assertEqual(w1.tiles, w2.tiles)          # flat list of ints -> cmp
        self.assertEqual(w1.cave_center, w2.cave_center)

    def test_tiles_are_valid_and_walkable_boundaries_exist(self):
        world = World(self.cfg, seed=7)
        for y in range(world.h):
            for x in range(world.w):
                tile = world.tile(x, y)
                self.assertIn(tile, (0, 1, 2, 3, 4))
                if not world.walkable(x, y):          # only water/rock block
                    self.assertIn(tile, (3, 4))
        # cave centre is always walkable
        cx, cy = world.cave_center
        self.assertTrue(world.walkable(cx, cy))

    # ---- offline simulation -------------------------------------------------
    def test_offline_run_keeps_tribe_bounded_and_world_alive(self):
        sim = Simulation.new_world(self.cfg, slot=0, name="t1", llm_enabled=False)
        max_agents = int(self.cfg.get("simulation.max_agents_per_world", 10))
        for report in sim.run_headless(600):
            self.assertLessEqual(report["alive_agents"], max_agents)
        final = sim.world
        self.assertGreater(final.tick, 0)
        weather_states = set(self.cfg.get("weather.states", {}).keys())
        self.assertIn(final.weather["state"], weather_states)
        # procedural animals must spawn over time (deterministic seed!)
        alive_animals = len([a for a in final.animals if a.alive])
        self.assertGreater(alive_animals, 0)

    def test_prompts_stay_within_length_limit(self):
        sim = Simulation.new_world(self.cfg, slot=0, name="t2", llm_enabled=False)
        cap = int(self.cfg.get("agents.prompts.init_max_chars", 100))
        for _ in range(48):    # enough ticks to trigger prompt adaptation
            sim.tick()
        for agent in sim.world.agents:
            self.assertLessEqual(len(agent.prompt), cap)

    # ---- save round-trip -----------------------------------------------------
    def test_save_roundtrip_preserves_world(self):
        cfg = base_config()
        tmp_dir = tempfile.mkdtemp(prefix="cavemen_test_")
        try:
            # keep the test isolated from the real save directory
            cfg.data["worlds"]["save_dir"] = tmp_dir
            sim = Simulation.new_world(cfg, slot=1, name="saved_world",
                                       llm_enabled=False)
            for _ in range(50):
                sim.tick()
            save_load.save_world(sim.world, cfg, 1, force=True)
            reloaded = save_load.load_world(cfg, 1)
            self.assertEqual(reloaded.tiles, sim.world.tiles)
            self.assertEqual(len(reloaded.agents), len(sim.world.agents))
            self.assertEqual(save_load.list_slots(cfg).get(1, {}).get("tick"),
                             sim.world.tick)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ---- fallback behaviour ---------------------------------------------------
    def test_fallback_character_is_seed_deterministic(self):
        a = fallback_character(random.Random(7), "m")
        b = fallback_character(random.Random(7), "m")
        self.assertEqual(a["name"], b["name"])
        self.assertEqual(a["trait"], b["trait"])

    def test_fallback_action_always_valid(self):
        sim = Simulation.new_world(self.cfg, slot=0, name="t3", llm_enabled=False)
        for agent in list(sim.world.agents)[:3]:
            act = fallback_action(agent, sim.world)
            self.assertIn(act["action"], ("move", "hunt", "gather", "rest"))
            self.assertTrue(-1 <= act["dx"] <= 1 and -1 <= act["dy"] <= 1)

    # ---- reproduction rules ----------------------------------------------------
    def test_reproduction_creates_child_below_cap(self):
        world = World(self.cfg, seed=99)
        min_y = float(self.cfg.get("agents.reproduction.min_adult_years", 15))
        max_y = float(self.cfg.get("agents.reproduction.max_adult_years", 38))
        age_years = (min_y + max_y) / 2.0
        per_year = int(self.cfg.get("simulation.ticks_per_day", 24)) * int(self.cfg.get("simulation.days_per_year", 36))
        cap_prompt = int(self.cfg.get("agents.prompts.init_max_chars", 100))
        cx, cy = world.cave_center
        mom = Agent(1, "Mira", "f", cx, cy, age_ticks=age_years * per_year,
                    prompt="Test mother prompt." )
        dad = Agent(2, "Dug",  "m", cx + 1, cy, age_ticks=age_years * per_year,
                    prompt="Test father prompt.")
        mom.hunger = dad.hunger = 80.0   # fed and rested -> eligible
        mom.stamina = dad.stamina = 80.0
        world.agents.extend([mom, dad])
        born = _reproduce(world)   # llm=None -> seeded fallback character names
        self.assertTrue(born)
        self.assertEqual(len(world.agents), 3)
        child = world.agents[-1]
        self.assertLessEqual(len(child.prompt), cap_prompt)

    # ---- berry bushes ---------------------------------------------------------
    def test_berry_placement_is_deterministic_and_valid(self):
        w1 = World(self.cfg, seed=5)
        w2 = World(self.cfg, seed=5)
        self.assertEqual(w1.berry_tiles, w2.berry_tiles)     # same seed -> same bushes
        expected_count = int(self.cfg.get("worlds.gather.berry_count", 14))
        max_amount = int(self.cfg.get("worlds.gather.max_amount", 6))
        self.assertEqual(len(w1.berry_tiles), expected_count)
        for (x, y), amount in w1.berry_tiles.items():
            self.assertIn(w1.tile(x, y), (1, 2))           # grass/forest tiles only
            self.assertEqual(amount, max_amount)

    def test_gather_on_bush_depletes_and_yields(self):
        from cavemen.simulation.rules import HUNGER_DELTA
        world = World(self.cfg, seed=3)
        pos = sorted(world.berry_tiles)[0]
        yield_hunger = float(self.cfg.get("worlds.gather.gather_yield_hunger", 8.0))
        agent = Agent(9, "Tester", "m", pos[0], pos[1])
        agent.hunger = 70.0
        agent.planned_action = {"action": "gather", "dx": 0, "dy": 0}   # explicit gather intent
        world.agents.append(agent)
        before = world.berry_tiles[pos]
        eff = {"stamina_drain": 1.0, "hunger_gain": 1.0}   # neutral weather
        _step_agent(agent, world, eff)
        self.assertEqual(world.berry_tiles[pos], before - 1)     # one berry consumed
        expected_hunger = 70.0 + HUNGER_DELTA.get("gather", -0.5) + yield_hunger
        self.assertAlmostEqual(agent.hunger, expected_hunger, places=3)
        self.assertTrue(any("gathered berries" in t for _, t in agent.story))

    def test_berries_regrow_up_to_cap(self):
        world = World(self.cfg, seed=11)
        pos = sorted(world.berry_tiles)[0]
        max_amount = int(self.cfg.get("worlds.gather.max_amount", 6))
        period = int(self.cfg.get("worlds.gather.regrow_ticks", 48))
        world.berry_tiles[pos] = 1                       # depleted state
        world.tick = period - 1
        _regrow_berries(world)                           # too early -> nothing yet
        self.assertEqual(world.berry_tiles[pos], 1)
        world.tick = period                              # exactly on the regrowth point
        _regrow_berries(world)
        self.assertEqual(world.berry_tiles[pos], 2)
        world.berry_tiles[pos] = max_amount              # at cap -> stays capped
        _regrow_berries(world)
        self.assertEqual(world.berry_tiles[pos], max_amount)

    def test_save_roundtrip_preserves_depleted_berry_tiles(self):
        cfg = base_config()
        tmp_dir = tempfile.mkdtemp(prefix="cavemen_test_")
        try:
            cfg.data["worlds"]["save_dir"] = tmp_dir
            sim = Simulation.new_world(cfg, slot=2, name="berry_save", llm_enabled=False)
            world = sim.world
            pos = sorted(world.berry_tiles)[0]
            world.berry_tiles[pos] = 2                   # simulate some harvesting before saving
            for _ in range(10):
                sim.tick()
            save_load.save_world(world, cfg, 2, force=True)
            reloaded = save_load.load_world(cfg, 2)
            self.assertEqual(reloaded.berry_tiles, world.berry_tiles)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_fallback_prefers_berry_bush(self):
        world = World(self.cfg, seed=7)
        pos = sorted(world.berry_tiles)[0]
        agent = Agent(42, "Fallback", "m", pos[0], pos[1])
        agent.hunger = 85.0    # foraging threshold reached; no hunting trigger
        world.agents.append(agent)
        act = fallback_action(agent, world)
        self.assertEqual(act["action"], "gather")

    def test_fallback_moves_toward_nearest_bush(self):
        world = World(self.cfg, seed=7)
        pos = sorted(world.berry_tiles)[0]
        ax, ay = min(pos[0] + 1, world.w - 1), pos[1]
        if not world.walkable(ax, ay):
            ax, ay = max(pos[0] - 1, 0), pos[1]
        agent = Agent(43, "Walker", "m", ax, ay)
        agent.hunger = 85.0
        world.agents.append(agent)
        # mirror the fallback rule: nearest bush with berries > 0 (strict < keeps ties stable)
        best_target, best_dist = None, 10 ** 9
        for p2, amt in world.berry_tiles.items():
            if amt > 0:
                d = abs(p2[0] - ax) + abs(p2[1] - ay)
                if d < best_dist:
                    best_target, best_dist = (int(p2[0]), int(p2[1])), d
        act = fallback_action(agent, world)
        if best_dist <= 1:
            self.assertEqual(act["action"], "gather")
        else:
            ndx, ndy = ax + int(act["dx"]), ay + int(act["dy"])
            new_d = abs(best_target[0] - ndx) + abs(best_target[1] - ndy)
            self.assertLess(new_d, best_dist)

    # ---- manual tribe roster (Phase 9) ---------------------------------------
    def test_roster_spawn_respects_entries_and_clamps(self):
        cfg = base_config()
        cap = int(cfg.get("agents.prompts.init_max_chars", 100))
        max_age = float(cfg.get("agents.age.death_age_limit", 70))
        roster = [
            {"name": "Grog" + "x" * 20, "gender": "f", "age_years": 7.5,
             "prompt": "P" * (cap + 50)},
            {"name": "", "gender": "m", "age_years": 90, "prompt": ""},
        ]
        sim = Simulation.new_world(cfg, slot=3, name="roster_test",
                                   llm_enabled=False, roster=roster)
        agents = sim.world.agents
        self.assertEqual(len(agents), 2)                       # exactly the roster size
        a1, a2 = agents[0], agents[1]
        self.assertEqual(a1.name, "Grogxxxx")                 # name clipped to 8 chars
        self.assertEqual(a1.gender, "f")
        self.assertAlmostEqual(a1.age_years(cfg), 7.5, places=3)   # valid age kept as-is
        self.assertLessEqual(len(a1.prompt), cap)             # prompt hard-capped at 100
        self.assertEqual(a2.name, "Gast2")                   # empty name gets a default
        self.assertAlmostEqual(a2.age_years(cfg), max_age, places=3)   # age clamped to limit

    def test_legacy_new_world_without_roster_spawns_full_tribe(self):
        sim = Simulation.new_world(base_config(), slot=4, name="legacy", llm_enabled=False)
        expected = int(self.cfg.get("simulation.max_agents_per_world", 10))
        self.assertEqual(len(sim.world.agents), expected)     # backwards-compatible path

    # ---- graceful LLM degradation -----------------------------------------------
    def test_llm_client_returns_none_on_unreachable_endpoint(self):
        cfg = base_config()
        cfg.data["llm"]["base_url"] = "http://127.0.0.1:9/v1"   # closed port -> instant
        cfg.data["llm"]["timeout_s"] = 1
        cfg.data["llm"]["max_retries"] = 0
        client = LLMClient(cfg)
        sim = Simulation.new_world(base_config(), slot=0, name="t4",
                                   llm_enabled=False)
        agent = sim.world.agents[0]
        self.assertIsNone(client.decide_action(agent, sim.world))
        self.assertIsNone(client.make_character("f"))

    # ---- agent conversations (speech bubbles) -----------------------------------
    def _world_with_close_pair(self, cfg):
        """Bare world with two adjacent cavemen in neutral hunger state."""
        world = World(cfg, seed=31)
        cx, cy = world.cave_center
        a = Agent(1, "Ane", "f", cx, cy)
        b = Agent(2, "Bob", "m", min(cx + 1, world.w - 1), cy)
        a.hunger = b.hunger = 50.0       # neutral state: generic dialogue pool
        world.agents.extend([a, b])
        return world

    def test_conversation_is_deterministic_and_cooldown_respected(self):
        cfg = base_config()
        conv = cfg.data["agents"]["conversation"]
        conv.update({"enabled": True, "chance_per_tick": 1.0})   # force a speech
        r1 = try_conversation(self._world_with_close_pair(cfg))
        r2 = try_conversation(self._world_with_close_pair(cfg))
        self.assertIsNotNone(r1)                       # two close agents must talk
        self.assertEqual(r1, r2)                      # same seed -> identical line & speaker
        world = self._world_with_close_pair(cfg)
        first = try_conversation(world)
        second = try_conversation(world)              # both agents now on cooldown
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_prompt_editor_edits_live_and_enforces_hard_cap(self):
        cfg = base_config()
        sim = Simulation.new_world(cfg, slot=6, name="editor", llm_enabled=False)
        ed = PromptEditor(sim.world, cfg)
        cap = int(cfg.get("agents.prompts.init_max_chars", 100))
        agent = ed.rows[0]
        for char in "x" * (cap + 30):                # type far past the hard limit
            ed._type_char(char)
        self.assertLessEqual(len(agent.prompt), cap)   # live write-through, capped
        before = agent.prompt
        ed._backspace()
        self.assertEqual(agent.prompt, before[:-1])     # deletions apply immediately


if __name__ == "__main__":
    unittest.main()
