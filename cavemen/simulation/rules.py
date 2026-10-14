"""Deterministic per-tick rule engine.

All non-LLM mechanics live here: weather cycle, vitals (HP/stamina/hunger),
aging, animal behaviour and spawning, deaths, and reproduction of the tribe
(max. 10 members; a man + woman can have a child when the tribe is below).
The LLM only decides actions - everything else stays reproducible.
"""
from ..llm.fallback import fallback_action, fallback_character
from ..world.generation import WATER

# per-action vitals deltas before weather scaling (negative = drain)
STAMINA_DELTA = {"rest": 2.5, "move": -1.5, "gather": -0.8, "hunt": -1.2, "fish": -1.0}
HUNGER_DELTA = {"rest": -0.3, "move": -0.6, "gather": -0.5, "hunt": -0.7, "fish": -0.5}


def _pick_weather(world):
    """Advance the deterministic weather state machine by one tick."""
    cfg = world.cfg
    states = dict(cfg.get("weather.states", {}))
    w = world.weather
    w["left"] = int(w.get("left", 0)) - 1
    if w["left"] <= 0:
        weights = [(name, max(0.0, float(spec.get("weight", 1)))) for name, spec in states.items()]
        total = sum(x for _, x in weights)
        roll = world.rng.random() * total
        acc, chosen = 0.0, next(iter(weights))
        for name, wt in weights:
            acc += wt
            if roll <= acc:
                chosen = (name, wt)
                break                     # stop at the selected bucket; without it the last state always wins
        w["state"] = chosen[0]
        w["left"] = int(cfg.get("weather.min_ticks_per_state", 20))
    spec = states[w["state"]]
    return {"stamina_drain": float(spec.get("stamina_drain", 1.0)),
            "hunger_gain": float(spec.get("hunger_gain", 1.0))}


def _step_agent(agent, world, eff):
    """Apply vitals/aging/action for one agent; sets death when applicable."""
    cfg = world.cfg
    day = world.day_number()
    action = dict(agent.planned_action)
    verb = action.get("action", "rest")

    # --- movement (only onto walkable tiles) -------------------------------
    if verb == "move":
        nx, ny = agent.x + int(action.get("dx", 0)), agent.y + int(action.get("dy", 0))
        if world.walkable(nx, ny):
            agent.x, agent.y = nx, ny
    # --- gathering and hunting --------------------------------------------
    hunger_bonus = 0.0
    hunted_event = None
    if verb == "gather":
        position = (agent.x, agent.y)
        berries_here = world.berry_tiles.get(position, 0)
        if berries_here > 0:
            # berry bush: finite resource, one berry per action
            hunger_bonus += float(cfg.get("worlds.gather.gather_yield_hunger", 8.0))
            world.berry_tiles[position] = berries_here - 1     # deplete the bush by one
            # throttled life-story event so the log stays readable (~1 entry / 24 ticks)
            if world.tick - int(agent.last_berry_gather_tick) >= 24:
                agent.add_story(day, "gathered berries")
                agent.last_berry_gather_tick = world.tick
        elif world.tile(agent.x, agent.y) in (1, 2):   # grass/forest without berry bushes
            hunger_bonus += float(cfg.get("worlds.gather.flat_gather_bonus", 2.0))
    if verb == "hunt":
        for animal in world.animals:
            if animal.alive and abs(animal.x - agent.x) + abs(animal.y - agent.y) <= 1:
                animal.hp -= 30.0
                hunger_bonus += 30.0
                hunted_event = animal.kind
                if animal.hp <= 0:
                    animal.alive = False
                    agent.add_story(day, f"killed a {animal.kind}")
    if verb == "fish":
        # Fishing only works from a shore tile touching the lake; every attempt
        # is one seeded-RNG roll with a per-agent cooldown, restoring satiety.
        fish_cd = int(cfg.get("agents.fishing.cooldown_ticks", 12))
        if world.tick - int(agent.last_fish_tick) >= fish_cd:
            near_water = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    tx, ty = agent.x + dx, agent.y + dy
                    if world.in_bounds(tx, ty) and world.tile(tx, ty) == WATER:
                        near_water = True
            if near_water and world.rng.random() < float(cfg.get("agents.fishing.chance_per_try", 0.6)):
                hunger_bonus += float(cfg.get("agents.fishing.hunger_restore", 8.0))
                agent.last_fish_tick = world.tick
                # throttled life-story event so the log stays readable (about one per 24 ticks)
                if world.tick - int(agent.last_fish_story_tick) >= 24:
                    agent.add_story(day, "caught a fish")
                    agent.last_fish_story_tick = world.tick
    stam = STAMINA_DELTA.get(verb, -1.0)
    hungr = HUNGER_DELTA.get(verb, -0.5) + hunger_bonus
    if stam < 0:
        stam *= eff["stamina_drain"]          # bad weather exhausts more
    if hungr < 0:
        hungr *= eff["hunger_gain"]           # hot/cold weather empties faster
    agent.stamina = max(0.0, min(100.0, agent.stamina + stam))
    agent.hunger = max(0.0, min(100.0, agent.hunger + hungr))


def _adapt_prompt_if_due(agent, world):
    """Runtime adaptation of the individual prompt (capped by config)."""
    from ..agents.prompts import adapt_prompt
    cfg = world.cfg
    every = max(1, int(cfg.get("agents.prompts.adapt_cooldown_ticks", 24)))
    if world.tick % every != 0:
        return
    cap = int(cfg.get("agents.prompts.init_max_chars", 100))
    age_years = agent.age_years(cfg)
    hunger_pct = max(0, min(99, round(agent.hunger)))
    # personal context line: mention the berry bushes where the agent stands when relevant
    berries_here = world.berry_tiles.get((agent.x, agent.y), 0)
    extra = f"Berries here: {berries_here}" if berries_here > 0 else ""
    agent.prompt = adapt_prompt(agent.prompt, age_years, hunger_pct,
                               world.weather["state"], cap, extra=extra)


def _age_and_hp(agent, world):
    """Aging and HP logic: starvation drain, regeneration, old-age death."""
    cfg = world.cfg
    day = world.day_number()
    agent.age_ticks += 1.0   # one tick == one sim-hour; aging is continuous
    age_years = agent.age_years(cfg)
    starve_below = float(cfg.get("agents.vitals.starvation_below", 20))
    death_limit = float(cfg.get("agents.age.death_age_limit", 70))
    if agent.hunger <= starve_below:
        # starving: HP drops until the caveman dies
        agent.hp -= 1.2
        if agent.hp <= 0.0:
            agent.alive = False
            agent.death_cause = "starvation"
            agent.add_story(day, f"died of starvation at age {int(age_years)}")
    else:
        # mild regeneration while fed (scaled by satiety)
        agent.hp += 0.3 * (agent.hunger / 100.0)
    if not agent.alive:
        return
    if age_years >= death_limit:
        # natural end of life, probabilistic once the limit is reached
        if world.rng.random() < 0.02:
            agent.alive = False
            agent.death_cause = "old_age"
            agent.add_story(day, f"died of old age at {int(age_years)} years")
    elif agent.is_elderly(cfg):
        # elderly agents degrade visibly (threshold from config)
        agent.hp -= 0.15
        if agent.hp <= 0.0:
            agent.alive = False
            agent.death_cause = "frailty"
            agent.add_story(day, f"died of frailty at age {int(age_years)}")
    agent.hp = max(0.0, min(100.0, agent.hp))


def _run_animals(world):
    """Advance all procedural animals: behaviour, attacks, cleanup, spawn."""
    from ..animals.animals import spawn_animal
    for animal in list(world.animals):
        if not animal.alive:
            continue
        event = animal.step(world, world.rng)
        attack = event.get("attack")
        if attack:
            uid, dmg = attack
            target = next((a for a in world.agents if a.uid == uid), None)
            if target is not None and target.alive:
                target.hp -= float(dmg)
                target.add_story(world.day_number(), f"was attacked by an {animal.kind}")
    # remove dead animals (keep saves lean, no corpse system in this scope)
    world.animals[:] = [a for a in world.animals if a.alive]
    max_alive = int(world.cfg.get("animals.max_alive", 12))
    if len([a for a in world.animals if a.alive]) < max_alive and world.rng.random() < 0.3:
        newborn = spawn_animal(world, world.rng)
        if newborn is not None:
            world.animals.append(newborn)


def _reproduce(world, llm=None):
    """Reproduction: only when the tribe has fewer than max members.

    One eligible man + one eligible woman (age window, fed, rested,
    cooldown after last birth) produce a child whose individual initial
    prompt is generated via LLM or seeded fallback. Returns True on birth.
    """
    from ..agents.agent import Agent
    from ..agents.prompts import make_initial_prompt
    cfg = world.cfg
    alive = [a for a in world.agents if a.alive]
    max_agents = int(cfg.get("simulation.max_agents_per_world", 10))
    if len(alive) >= max_agents:
        return False
    min_y = float(cfg.get("agents.reproduction.min_adult_years", 12))
    max_y = float(cfg.get("agents.reproduction.max_adult_years", 38))
    months_cd = float(cfg.get("agents.reproduction.cooldown_months_after_birth", 6))
    per_year = int(cfg.get("simulation.ticks_per_day", 24)) * int(cfg.get("simulation.days_per_year", 36))
    cooldown_ticks = max(1, int(per_year * months_cd / 12.0))

    def eligible(a: Agent) -> bool:
        age_years = a.age_years(cfg)
        if not (min_y <= age_years <= max_y):
            return False
        if a.hunger < 30 or a.stamina < 25:
            return False   # only well-fed, rested partners reproduce
        if world.tick - int(a.last_birth_tick) < cooldown_ticks:
            return False   # birth cooldown (config months)
        return True

    mothers = [a for a in alive if a.gender == "f" and eligible(a)]
    fathers = [a for a in alive if a.gender == "m" and eligible(a)]
    if not mothers or not fathers:
        return False
    mom = min(mothers, key=lambda a: a.last_birth_tick)
    dad = min(fathers, key=lambda a: a.last_birth_tick)

    gender = world.rng.choice("mf")
    char = None
    if llm is not None:
        char = llm.make_character(gender)      # individual prompt via LLM when available
    if char is None:
        char = fallback_character(world.rng, gender)
    cap = int(cfg.get("agents.prompts.init_max_chars", 100))
    uid = max((a.uid for a in world.agents), default=0) + 1
    child = Agent(uid, char["name"], gender, *world.cave_center,
                   prompt=make_initial_prompt(char["name"], 0, gender, char["trait"], cap))
    child.add_story(world.day_number(), "was born in the cave")
    mom.last_birth_tick = world.tick
    dad.last_birth_tick = world.tick
    mom.add_story(world.day_number(), f"gave birth to {child.name} with {dad.name}")
    dad.add_story(world.day_number(), f"fathered {child.name} with {mom.name}")
    child.next_decision_tick = world.tick + int(cfg.get("llm.decision_cooldown_ticks", 6))
    world.agents.append(child)
    return True


def _regrow_berries(world):
    """Berry regrowth: every N ticks each bush grows by one berry up to its cap."""
    cfg = world.cfg
    max_amount = int(cfg.get("worlds.gather.max_amount", 6))
    period = max(1, int(cfg.get("worlds.gather.regrow_ticks", 48)))
    if world.tick % period != 0:
        return
    for pos in list(world.berry_tiles):
        amount = world.berry_tiles[pos]
        if amount < max_amount:
            world.berry_tiles[pos] = amount + 1


def run_tick(world, llm=None):
    """Advance the whole simulation by one tick; returns {'births','deaths'}."""
    before_alive = sum(1 for a in world.agents if a.alive)
    eff = _pick_weather(world)
    _regrow_berries(world)
    cooldown = max(1, int(world.cfg.get("llm.decision_cooldown_ticks", 6)))
    # Per-tick LLM budget: at most this many network calls per tick. A slow local model would
    # otherwise stack up pending requests in the provider and block the GUI main loop; agents
    # whose decision is due but whose budget slot is gone keep their previous plan and ask on
    # the next tick instead of falling back to the deterministic rules.
    llm_budget = max(1, int(world.cfg.get("llm.decisions_per_tick", 1)))
    llm_calls_this_tick = 0
    born = died = 0
    for agent in list(world.agents):
        if not agent.alive:
            continue
        # LLM decision (with graceful fallback) only every N ticks per agent.
        due = world.tick >= int(agent.next_decision_tick)
        pacing_deferred = due and llm is not None and llm_calls_this_tick >= llm_budget
        if due and not pacing_deferred:
            action = None
            if llm is not None:
                action = llm.decide_action(agent, world)
                llm_calls_this_tick += 1
                if getattr(llm, "debug", False):   # --debug-llm flag: per-caveman raw LLM output in the terminal
                    raw = getattr(llm, "_last_raw_text") or "(no reply from LLM)"
                    verdict = action if action is not None else "fallback (deterministic rules)"
                    print(f"[LLM-Debug] {agent.name}: {raw} -> {verdict}")
            if action is None:
                action = fallback_action(agent, world)   # deterministic offline mode
            agent.planned_action = {"action": action.get("action", "rest"),
                                     "dx": int(action.get("dx", 0)),
                                     "dy": int(action.get("dy", 0))}
            agent.next_decision_tick = world.tick + cooldown
        _adapt_prompt_if_due(agent, world)
        was_alive = agent.alive
        _step_agent(agent, world, eff)
        _age_and_hp(agent, world)
        if was_alive and not agent.alive:
            died += 1
    _run_animals(world)
    born = 1 if _reproduce(world, llm) else 0
    from .conversations import try_conversation   # lazy import: no circular deps
    try_conversation(world, llm)                   # agent chatter (speech bubbles)
    world.tick += 1
    return {"births": born, "deaths": died}
