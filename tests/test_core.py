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
import json                                     # noqa: E402  (stub LLM payloads)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ["PYTHONPATH"] = REPO   # make 'cavemen' importable in any cwd
from cavemen.agents.agent import Agent          # noqa: E402
from cavemen.config import ConfigError, Config  # noqa: E402
from cavemen.llm.client import LLMClient        # noqa: E402
from cavemen.llm.fallback import fallback_action, fallback_character  # noqa: E402
from cavemen.simulation.game_loop import Simulation   # noqa: E402
from cavemen.simulation.rules import run_tick, _reproduce, _regrow_berries, _step_agent, _pick_weather   # noqa: E402
from cavemen.simulation.conversations import try_conversation, _nearest_food_source, _food_hint_line, _direction_from                  # noqa: E402
from cavemen.gui.prompt_editor import PromptEditor                            # noqa: E402
from cavemen.gui.hud import side_panel_width  # noqa: E402 (Phase 14 sidebar layout)
from cavemen.world.generation import World         # noqa: E402
from cavemen.animals.animals import spawn_animal            # noqa: E402
from cavemen.world.generation import WATER, FOREST           # noqa: E402
from cavemen.world import save_load                # noqa: E402
import pygame                                      # noqa: E402  (synthetic KEYDOWN events for the GUI screens)
from cavemen.config import update_config_values    # noqa: E402
from cavemen.gui.config_editor import ConfigEditor  # noqa: E402
import http.server                                   # noqa: E402  (stub LLM endpoint for client tests)


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

    def test_weather_state_machine_cycles_across_states(self):
        # Regression guard for _pick_weather: the weighted roll must stop at the
        # selected bucket. Without the break every roll lands on the LAST state in
        # config order and weather gets permanently stuck there (constant storm).
        world = World(self.cfg, seed=1)   # pure state machine, no sim side effects
        seen = set()
        for _ in range(480):              # ~24 transitions at min_ticks_per_state=20
            _pick_weather(world)
            seen.add(world.weather["state"])
        self.assertGreaterEqual(len(seen), 2)

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
            self.assertIn(act["action"], ("move", "hunt", "gather", "rest", "fish"))
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

    # ---- Phase 13: food-source info in conversations ---------------------------
    def test_food_hint_shares_bush_location(self):
        cfg = base_config()
        conv = cfg.data["agents"]["conversation"]
        conv.update({"enabled": True, "chance_per_tick": 1.0, "food_hint_chance": 1.0})

        def make_world():
            world = self._world_with_close_pair(cfg)
            a, b = world.agents              # Ane (uid 1), Bob (uid 2): the only possible pair
            a.hunger = b.hunger = 45.0       # hungry enough -> hint gate opens
            world.berry_tiles.clear()        # full control: exactly one bush at a known spot
            lx, ly = b.x, b.y
            world.berry_tiles[(lx + 5, ly - 3)] = 4   # 8 tiles northeast of the listener
            return world

        r1 = try_conversation(make_world())
        r2 = try_conversation(make_world())   # identical seed/state -> reproducible line
        self.assertIsNotNone(r1)                       # forced speech with a hungry pair
        self.assertEqual(r1, r2)                      # same seed -> identical line & speaker
        self.assertEqual(r1["speaker"], 1)           # fixed single pair: Ane speaks to Bob
        text = r1["text"]
        self.assertIn("northeast", text)              # direction relative to listener (Bob)
        self.assertIn("8", text)                     # Manhattan distance in tiles

    def test_food_hint_falls_back_without_bush(self):
        cfg = base_config()
        conv = cfg.data["agents"]["conversation"]
        conv.update({"enabled": True, "chance_per_tick": 1.0, "food_hint_chance": 1.0})

        def make_world():
            world = self._world_with_close_pair(cfg)
            a, b = world.agents
            a.hunger = b.hunger = 45.0       # hungry -> the hint gate would open...
            world.berry_tiles.clear()        # ...but no bush exists at all
            return world

        r1 = try_conversation(make_world())
        self.assertIsNotNone(r1)              # speech still happens via the existing pools
        text = r1["text"]
        # food-hint templates are the only lines containing "tiles"/"steps"; none here
        self.assertNotIn("tiles", text)
        self.assertNotIn("steps", text)

        conv["food_radius_tiles"] = 2       # bush exists but outside the tiny radius -> still fallback
        world = make_world()
        lx, ly = world.agents[1].x, world.agents[1].y
        world.berry_tiles[(lx + 5, ly - 3)] = 4
        r2 = try_conversation(world)
        self.assertIsNotNone(r2)
        text2 = r2["text"]
        self.assertNotIn("tiles", text2)
        self.assertNotIn("steps", text2)

    def test_food_hint_requires_hunger(self):
        cfg = base_config()
        conv = cfg.data["agents"]["conversation"]
        conv.update({"enabled": True, "chance_per_tick": 1.0, "food_hint_chance": 1.0})
        world = self._world_with_close_pair(cfg)
        a, b = world.agents
        a.hunger = b.hunger = 90.0          # well fed: no food hint wanted even with bush nearby
        lx, ly = b.x, b.y
        world.berry_tiles.clear()
        world.berry_tiles[(lx + 3, ly)] = 4
        r = try_conversation(world)
        self.assertIsNotNone(r)             # generic pool line instead of a bush hint
        text = r["text"]
        self.assertNotIn("tiles", text)
        self.assertNotIn("steps", text)

    def test_nearest_food_source_selection(self):
        bushes = {(10, 12): 3, (5, 5): 6, (30, 4): 0}   # depleted bush must be ignored
        self.assertEqual(_nearest_food_source(bushes, 9.0, 11.0, 24), ((10, 12), 2))
        self.assertIsNone(_nearest_food_source(bushes, 30.0, 4.0, 1))   # only a depleted bush in range
        tied = {(3, 5): 2, (5, 3): 2}                         # equal distance -> lexicographic tile order
        self.assertEqual(_nearest_food_source(tied, 4.0, 4.0, 10), ((3, 5), 2))

    def test_direction_words(self):
        self.assertEqual(_direction_from(5, -3), "northeast")
        self.assertEqual(_direction_from(-4, 2), "southwest")
        self.assertEqual(_direction_from(6, 0), "east")
        self.assertEqual(_direction_from(0, -7), "north")

    def test_food_hint_near_line_on_own_tile(self):
        rng = random.Random(1)               # seeded chat RNG: reproducible draw
        text = _food_hint_line(rng, "Bob", (7, 9), (7, 9))   # bush on the listener's tile
        self.assertIn("Bob", text)
        self.assertNotIn("tiles", text)      # near-lines carry no distance/direction markers

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




class FishingTests(unittest.TestCase):
    """New aquatic food source: fish spawning, drift/flee and the fishing action."""

    def setUp(self) -> None:
        self.cfg = base_config()

    def test_fish_spawn_only_inside_lake(self):
        world = World(self.cfg, seed=11)
        rng = random.Random(42)
        for _ in range(200):
            fish = spawn_animal(world, rng)
            if fish is not None and fish.kind == "fish":
                self.assertEqual(world.tile(fish.x, fish.y), WATER)   # aquatic: lake only
                return
        self.fail("no fish spawned within 200 tries (seeded!)")

    def test_fish_stay_in_lake_and_never_attack(self):
        world = World(self.cfg, seed=12)
        rng = random.Random(5)
        for _ in range(200):
            candidate = spawn_animal(world, rng)
            if candidate is not None and candidate.kind == "fish":
                break
        else:
            self.fail("no fish spawned within 200 tries (seeded!)")
        # One agent nearby so the flee logic gets exercised as well.
        watcher = Agent(90, "Watcher", "m", min(candidate.x + 2, world.w - 1),
                        min(candidate.y + 2, world.h - 1))
        world.agents.append(watcher)
        for i in range(60):
            candidate.step(world, random.Random(i))   # any seeded rng works per tick
            self.assertEqual(world.tile(candidate.x, candidate.y), WATER)   # fish never leave the lake

    def test_fallback_chooses_fishing_when_hungry_and_no_gather_targets(self):
        world = World(self.cfg, seed=3)   # probe-verified open shore without forest nearby: (37, 32)
        world.berry_tiles.clear()         # no berries -> the gather fallback also finds nothing
        agent = Agent(91, "Angler", "m", 37, 32)
        agent.hunger = 78.0   # in [75, 80): skips the hunting branch but is still hungry enough
        act = fallback_action(agent, world)
        self.assertEqual(act["action"], "fish")
        self.assertEqual((act["dx"], act["dy"]), (0, 0))

    def test_fishing_restores_hunger_and_has_cooldown(self):
        from cavemen.simulation.rules import HUNGER_DELTA, _step_agent
        world = World(self.cfg, seed=3)   # same probe-verified shore tile as above
        agent = Agent(92, "Tackle", "m", 37, 32)
        agent.hunger = 50.0
        agent.last_fish_tick = world.tick - 100      # cooldown already expired -> attempt allowed
        eff = {"stamina_drain": 1.0, "hunger_gain": 1.0}
        agent.planned_action = {"action": "fish", "dx": 0, "dy": 0}
        # Forced catch: the roll is seeded below the configured 60% success chance.
        world.rng.random = lambda: 0.5
        _step_agent(agent, world, eff)
        expected = (50.0 + HUNGER_DELTA["fish"]
                    + float(self.cfg.get("agents.fishing.hunger_restore", 8.0)))
        self.assertAlmostEqual(agent.hunger, expected, places=3)
        # Cooldown: an immediate second attempt cannot fish again in the same tick.
        before = agent.hunger
        _step_agent(agent, world, eff)
        self.assertAlmostEqual(agent.hunger, before + HUNGER_DELTA["fish"], places=3)

class ConfigEditorAndPersistenceTests(unittest.TestCase):
    """Menu-overlay settings editor plus the in-place YAML persistence function."""

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="cavemen_cfg_")
        self.path = os.path.join(self.dir, "config.yaml")
        shutil.copy(os.path.join(REPO, "config.yaml"), self.path)

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    @staticmethod
    def key_event(key, unicode=None):
        ev = pygame.event.Event(pygame.KEYDOWN, key=key)
        if unicode is not None:
            ev.unicode = unicode   # real pygame KEYDOWN events always carry .unicode
        return ev

    def _go_to_row(self, editor, dotted_key):
        idx = [k for k, _ in editor.rows].index(dotted_key)
        while editor.r != idx:          # K_DOWN steps through rows; navigation wraps safely
            editor.handle_event(self.key_event(pygame.K_DOWN))

    def test_update_preserves_comments_line_count_and_other_values(self):
        before = open(self.path, encoding="utf-8").read()
        update_config_values(self.path, {"llm.max_tokens": 512, "simulation.tick_rate_hz": 7})
        after = open(self.path, encoding="utf-8").read()
        self.assertIn("max_tokens: 512", after)
        # the edited line's own trailing comment must survive verbatim
        self.assertIn("tick_rate_hz: 7   # logical ticks per second", after)
        self.assertEqual(before.count("\n"), after.count("\n"))   # no lines added or dropped
        self.assertNotIn("max_tokens: 300", after)
        reloaded = Config(self.path)
        self.assertEqual(reloaded.get("llm.max_tokens"), 512)
        self.assertEqual(reloaded.get("simulation.tick_rate_hz"), 7)

    def test_update_missing_key_raises_and_leaves_file_untouched(self):
        with self.assertRaises(ConfigError):
            update_config_values(self.path, {"no.such.key": 1})
        self.assertIn("max_tokens: 300", open(self.path, encoding="utf-8").read())

    def test_editor_navigation_wraps_and_never_crashes(self):
        editor = ConfigEditor(Config(self.path))
        n_rows = len(editor.rows)
        for k in (pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d):   # WASD must never move navigation
            editor.handle_event(self.key_event(k))
        self.assertEqual(editor.r, 0)
        for i in range(2 * n_rows + 50):   # storm of arrows across both edges many times over
            editor.handle_event(self.key_event(pygame.K_DOWN if i % 2 == 0 else pygame.K_UP))
            self.assertTrue(0 <= editor.r < n_rows)

    def test_editor_valid_save_yields_typed_updates_and_persists(self):
        cfg = Config(self.path)
        editor = ConfigEditor(cfg)
        self._go_to_row(editor, "llm.max_tokens")
        for _ in range(len(editor.values[editor.r])):
            editor.handle_event(self.key_event(pygame.K_BACKSPACE))
        for ch in "512":    # F12 is not otherwise handled by the editor -> pure text input path
            editor.handle_event(self.key_event(pygame.K_F12, unicode=ch))
        action = editor.handle_event(self.key_event(pygame.K_RETURN))
        self.assertEqual(action["kind"], "save")
        self.assertEqual(action["updates"]["llm.max_tokens"], 512)      # typed int, not str
        update_config_values(cfg.path, action["updates"])
        reloaded = Config(cfg.path)
        self.assertEqual(reloaded.get("llm.max_tokens"), 512)

    def test_editor_rejects_out_of_range_value_and_stays_open(self):
        editor = ConfigEditor(Config(self.path))
        original = open(self.path, encoding="utf-8").read()
        self._go_to_row(editor, "worlds.max_worlds")
        for _ in range(len(editor.values[editor.r])):
            editor.handle_event(self.key_event(pygame.K_BACKSPACE))
        editor.handle_event(self.key_event(pygame.K_F12, unicode="0"))
        action = editor.handle_event(self.key_event(pygame.K_RETURN))   # ENTER must NOT close
        self.assertIsNone(action)
        self.assertTrue(editor.error)
        self.assertIn("Bereich", editor.error)
        self.assertEqual(open(self.path, encoding="utf-8").read(), original)

    def test_editor_requires_http_scheme_for_base_url(self):
        editor = ConfigEditor(Config(self.path))
        self._go_to_row(editor, "llm.base_url")
        for _ in range(len(editor.values[editor.r])):
            editor.handle_event(self.key_event(pygame.K_BACKSPACE))
        for ch in "localhost:8080/v1":
            editor.handle_event(self.key_event(pygame.K_F12, unicode=ch))
        self.assertIsNone(editor.handle_event(self.key_event(pygame.K_RETURN)))
        self.assertIn("http(s)://", editor.error)

    def test_editor_escal_cancel_returns_without_saving(self):
        editor = ConfigEditor(Config(self.path))
        original = open(self.path, encoding="utf-8").read()
        self.assertEqual(editor.handle_event(self.key_event(pygame.K_ESCAPE)), {"kind": "cancel"})
        self.assertEqual(open(self.path, encoding="utf-8").read(), original)


class LLMClientTests(unittest.TestCase):
    """Offline-safe behaviour of the OpenAI-compatible client (incl. the LM-Studio /v1 quirk)."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path == "/v1/chat/completions":
                payload = json.dumps(
                    {"choices": [{"message": {"content": '{"action": "rest"}'}}]}).encode()
            else:   # mirrors the LM-Studio log line: unexpected endpoint, still answers with 200
                payload = json.dumps({"error": "Unexpected endpoint"}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):       # keep unittest output clean
            pass

    @staticmethod
    def _cfg(base_url: str):
        vals = {"llm.base_url": base_url, "llm.api_key": "", "llm.model": "fake-model",
                "llm.timeout_s": 5.0, "llm.max_retries": 1, "llm.max_tokens": 32}

        class Cfg:                       # minimal duck-type of cavemen.config.Config.get
            def get(self, key, default=None):
                return vals.get(key, default)
        return Cfg()

    def test_client_recovers_lm_studio_v1_prefix_automatically(self):
        import threading
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._Handler)
        port = server.server_address[1]
        # serve_forever must run itself - binding the socket alone accepts but never answers
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            client = LLMClient(self._cfg(f"http://127.0.0.1:{port}"))   # root without /v1, like the user yaml
            result = client._post([{"role": "user", "content": "ping"}])
            self.assertEqual(result, {"action": "rest"})        # only the /v1 variant answers validly
            self.assertFalse(client._offline)
        finally:
            server.shutdown()

    def test_client_latches_offline_and_falls_back(self):
        import socket
        probe = socket.socket()              # find a port that is guaranteed to be free
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]
        probe.close()
        client = LLMClient(self._cfg(f"http://127.0.0.1:{dead_port}"))
        self.assertIsNone(client._post([{"role": "user", "content": "ping"}]))
        self.assertTrue(client._offline)    # later calls must not touch the network at all


class LLMPacingDebugTests(unittest.TestCase):
    """Per-tick LLM budget (llm.decisions_per_tick) and the --debug-llm terminal output."""

    class _StubLLM:
        def __init__(self, debug=False, reply="RAW-MODEL-REPLY"):
            self.calls = 0
            self.debug = debug
            self._last_raw_text = reply

        def decide_action(self, agent, world):   # duck-typed LLM client (no network access)
            self.calls += 1
            return {"action": "hunt", "dx": 1, "dy": 0}

    def _due_sim(self):
        sim = Simulation.new_world(base_config(), slot=9, name="t5", llm_enabled=False)
        for agent in sim.world.agents:   # everyone due at the very first tick -> worst case
            agent.next_decision_tick = 0
            agent.planned_action = {"action": "rest", "dx": 0, "dy": 0}
        return sim

    def test_budget_limits_llm_calls_per_tick(self):
        stub = self._StubLLM()
        sim = self._due_sim()
        run_tick(sim.world, stub)   # all agents due at once, budget is 1 in config.yaml
        cooldown = int(sim.cfg.get("llm.decision_cooldown_ticks", 6))
        decided_first = sum(1 for a in sim.world.agents if a.next_decision_tick == cooldown)
        self.assertEqual(decided_first, 1)     # exactly one LLM decision happened this tick
        rest_plans = sum(1 for a in sim.world.agents if a.planned_action["action"] == "rest")
        self.assertGreaterEqual(rest_plans, len(sim.world.agents) - 1)   # others kept their plan
        calls = stub.calls
        for _ in range(3):               # still due agents rotate: +1 call per tick
            run_tick(sim.world, stub)
            self.assertEqual(stub.calls, calls + 1)
            calls += 1

    def test_budget_from_config_is_honored(self):
        sim = self._due_sim()
        sim.cfg.data["llm"]["decisions_per_tick"] = 2   # raise the budget live, like in settings menu
        stub = self._StubLLM()
        run_tick(sim.world, stub)
        self.assertEqual(stub.calls, 2)

    def test_debug_flag_prints_raw_llm_output_per_caveman(self):
        import contextlib
        import io
        sim = self._due_sim()
        stub = self._StubLLM(debug=True, reply="RAW-DEBUG-TOKEN")
        buf = io.StringIO()   # capture stdout while the tick runs (debug lines)
        with contextlib.redirect_stdout(buf):   # capture the per-caveman debug lines on stdout
            run_tick(sim.world, stub)
        out = buf.getvalue()
        cooldown = int(sim.cfg.get("llm.decision_cooldown_ticks", 6))
        decided_names = [a.name for a in sim.world.agents if a.next_decision_tick == cooldown]
        self.assertEqual(len(decided_names), 1)
        self.assertIn("[LLM-Debug]", out)                      # debug line went to stdout
        self.assertIn("RAW-DEBUG-TOKEN", out)                 # raw model reply is included
        self.assertIn(f"[LLM-Debug] {decided_names[0]}:", out)   # per caveman, with its name


from cavemen.gui.pause_menu import PauseMenu   # noqa: E402  (ESC pause overlay actions)


class PauseMenuTests(unittest.TestCase):
    """Pause menu on ESC: navigation wrap-around, action confirmation and resume."""

    @staticmethod
    def key_event(key):
        return pygame.event.Event(pygame.KEYDOWN, key=key)

    def test_items_complete_and_navigation_wraps(self):
        menu = PauseMenu()
        kinds = [action["kind"] for _label, action in menu.items]
        self.assertEqual(kinds, ["resume", "save_menu", "prompts"])
        n = len(menu.items)
        menu.handle_event(self.key_event(pygame.K_UP))          # wrap from first row to last
        self.assertEqual(menu.cursor, n - 1)
        for _ in range(n + 4):                                   # storm across both loop edges
            direction = pygame.K_DOWN if menu.cursor % 2 == 0 else pygame.K_UP
            menu.handle_event(self.key_event(direction))
            self.assertTrue(0 <= menu.cursor < n)

    def test_confirm_and_esc_behaviour(self):
        menu = PauseMenu()
        self.assertEqual(menu.handle_event(self.key_event(pygame.K_RETURN)), {"kind": "resume"})
        menu.handle_event(self.key_event(pygame.K_DOWN))         # move to the save & main-menu row
        self.assertEqual(menu.handle_event(self.key_event(pygame.K_SPACE)), {"kind": "save_menu"})
        for _ in range(2):                                       # wrap around to last row (prompts)
            menu.handle_event(self.key_event(pygame.K_UP))
        self.assertEqual(menu.handle_event(self.key_event(pygame.K_RETURN)), {"kind": "prompts"})
        self.assertEqual(menu.handle_event(self.key_event(pygame.K_ESCAPE)), {"kind": "resume"})

    def test_mouse_click_selects_row(self):
        menu = PauseMenu()
        rect = menu.item_rect(2)
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(rect.x + 5, rect.y + 5))
        self.assertEqual(menu.handle_event(event)["kind"], "prompts")
class SidePanelLayoutTests(unittest.TestCase):
    """Phase 14: fixed left sidebar next to the canvas - pure layout facts."""

    def test_side_panel_width_clamps_to_window(self):
        self.assertEqual(side_panel_width(2000, 300), 300)      # request fits verbatim
        self.assertEqual(side_panel_width(960, 5000), 880)      # huge request clamped to win-80
        self.assertGreaterEqual(side_panel_width(300, 10), 120)

    def test_panel_and_canvas_fill_window_without_overlap(self):
        for win in (300, 400, 960, 2000):
            p = side_panel_width(win, 5000)     # worst-case request
            canvas_w = win - p                  # canvas region [p, win)
            self.assertGreaterEqual(p, 120)     # panel stays usable (MIN_PANEL_W)
            self.assertGreater(canvas_w, 0)     # canvas never disappears
            self.assertEqual(p + canvas_w, win) # exact cover -> zero overlap

    def test_canvas_never_below_minimum_width(self):
        # Phase 14: canvas region must keep >= 80 px even in small windows.
        from cavemen.gui.hud import side_panel_width as sw
        for w in range(500, 1600, 37):
            p2 = sw(w, 5000)
            self.assertGreaterEqual(w - p2, 80)

if __name__ == "__main__":
    unittest.main()
