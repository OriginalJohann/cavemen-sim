"""Agent-to-agent conversation, displayed as speech bubbles above the agents.

Chatter is cheap and offline-safe by design: once per tick one pair of living
agents within a configured distance may speak with a configured probability;
per-agent cooldowns keep nobody monologuing. Lines come from deterministic pools
drawn through the seeded world RNG (reproducible per seed). If
`agents.conversation.use_llm` is enabled and an LLM endpoint answers, the line
is model-generated instead (same strict-JSON contract as the other client
methods); failures fall back to the pools silently. Bubble state is transient UI
data on the agent and deliberately NOT persisted with world saves. Chatter draws from a dedicated seeded RNG (same pattern as the berry bushes in Phase 8) so conversation timing can never perturb the main sim stream - animals, weather and vitals keep their previously balanced behaviour. Since Phase 13 there is one more deterministic pool: when either party is hungry enough (`agents.conversation.food_hint_hunger_below`) and a berry bush lies within `food_radius_tiles` of the pair midpoint, the line announces that bush with its direction and distance relative to the listener, so the tribe shares real food-source information (INSTRUCTIONS.md §3).
"""
import random

from ..agents.prompts import clip

# short caveman-flavoured one-liners; {listener} gets the addressee's name
_GENERIC_LINES = [
    "Ugh, what are you doing there, {listener}?"
    "Hey, {listener}! The sun is high."
    "We will share the kill soon, {listener}."
    "Good hunting weather, don't you think so, {listener}?"
]
_HUNGRY_LINES = [
    "My belly rumbles... berries around here!"
    "Eat first, talk later, {listener}."
    "{listener}, hand me your berries. Just once."
    "Starving! And you look pale too, {listener}."
]
_WEATHER_LINES = {
    "cold":  ["Cold! The cave is warm, come in, {listener}."],
    "hot":   ["Hot like the sun. Water would be nice, {listener}."],
    "rain":  ["Rain... wet furs are no good, {listener}."],
    "storm": ["Storm! Better stay inside, {listener}."]
}


_FOOD_HINT_LINES = [     # concrete food-source info: direction + distance to a berry bush
    "Berries {dist} tiles {dir} of you, {listener}. Go pick them!",
    "{dist} tiles {dir}: berry bushes. I saw them myself, {listener}.",
    "I smell berries {dir}, about {dist} steps off, {listener}.",
]
_FOOD_HINT_NEAR_LINES = [  # bush on / right at the listener's own tile (no direction needed)
    "Berries right here! Pick them now, {listener}.",
    "Right under us: a berry bush. Take yours, {listener}.",
]


def _direction_from(dx: int, dy: int) -> str:
    """Compass-style direction word from (dx, dy); on the tile grid +y is south."""
    vert = "north" if dy < 0 else ("south" if dy > 0 else "")
    horiz = "east" if dx > 0 else ("west" if dx < 0 else "")
    return f"{vert}{horiz}" if (vert and horiz) else (vert or horiz)


def _nearest_food_source(berry_tiles, ax: float, ay: float, radius: int):
    """Nearest berry bush that still holds berries within Manhattan `radius` of the anchor.

    Returns ((x, y), distance). Ties are broken by lexicographic tile position (iteration
    runs over sorted positions) so the pick is fully deterministic per world state.
    Returns None when no non-depleted bush lies in range.
    """
    best_key = None          # (distance, pos); min wins, tuple compare keeps ties stable
    for pos in sorted(berry_tiles):
        if berry_tiles[pos] <= 0:
            continue         # depleted bush has nothing to point at
        dist = int(round(abs(pos[0] - ax) + abs(pos[1] - ay)))
        key = (dist, pos)
        if best_key is None or key < best_key:
            best_key = key
    if best_key is not None and best_key[0] <= radius:
        return (best_key[1], best_key[0])
    return None


def _food_hint_line(chat_rng, listener_name: str, bush_pos, listener_pos) -> str:
    """Draw one food-hint line through the per-tick seeded chat RNG (reproducible)."""
    dx = int(round(bush_pos[0] - listener_pos[0]))
    dy = int(round(bush_pos[1] - listener_pos[1]))
    dist = abs(dx) + abs(dy)
    if dist == 0:            # bush at the listener's tile -> short near-line, no compass word
        return chat_rng.choice(_FOOD_HINT_NEAR_LINES).format(listener=listener_name)
    dir_word = _direction_from(dx, dy)
    return chat_rng.choice(_FOOD_HINT_LINES).format(
        listener=listener_name, dist=dist, dir=dir_word)


def _deterministic_line(rng, speaker, listener, weather_state: str) -> str:
    """Pick one pool line through the seeded world RNG (reproducible per seed)."""
    if speaker.hunger < 40.0:
        pool = _HUNGRY_LINES
    elif rng.random() < 0.5 and weather_state in _WEATHER_LINES:
        pool = _WEATHER_LINES[weather_state]
    else:
        pool = _GENERIC_LINES
    return rng.choice(pool).format(listener=listener.name)


def try_conversation(world, llm=None):
    """Maybe trigger one speech this tick; sets bubble state on the speaker.

    Returns {'speaker', 'listener', 'text'} when a line was created, else None.
    Never raises: LLM problems degrade silently to the deterministic pools.
    """
    cfg = world.cfg
    if not bool(cfg.get("agents.conversation.enabled", True)):
        return None
    max_dist = int(cfg.get("agents.conversation.max_dist_tiles", 4))
    chance = float(cfg.get("agents.conversation.chance_per_tick", 0.25))
    cooldown = max(1, int(cfg.get("agents.conversation.speech_cooldown_ticks", 36)))
    # Dedicated seeded RNG per tick, decoupled from the main sim stream (berry-bush
    # pattern): reproducible per world seed without shifting animal/weather draws.
    chat_rng = random.Random(f"{world.seed}-chat-{int(world.tick)}")
    if chat_rng.random() > chance:      # on most ticks nobody talks
        return None
    alive = [a for a in world.agents if a.alive]
    pairs = [(s, l)
             for i, s in enumerate(alive)
             for l in alive[i + 1:]
             if abs(s.x - l.x) + abs(s.y - l.y) <= max_dist
             and int(world.tick) - int(s.bubble_start_tick) >= cooldown
             and int(world.tick) - int(l.bubble_start_tick) >= cooldown]
    if not pairs:
        return None
    speaker, listener = chat_rng.choice(pairs)   # deterministic per seed
    max_chars = int(cfg.get("agents.conversation.max_chars", 60))
    # Phase 13: share real food-source information. When one of the two is hungry enough
    # and a berry bush lies within `food_radius_tiles` around the pair midpoint, the bubble
    # points the listener at the nearest bush (direction + distance relative to them). All
    # draws go through chat_rng -> reproducible per seed; nobody hungry or no bush in range
    # falls back silently to the generic/hungry/weather pools.
    food_hint = None
    radius = int(cfg.get("agents.conversation.food_radius_tiles", 24))
    if radius > 0:                                    # <= 0 disables hints entirely
        hunger_below = float(cfg.get("agents.conversation.food_hint_hunger_below", 55.0))
        hint_chance = float(cfg.get("agents.conversation.food_hint_chance", 0.35))
        hungry = speaker.hunger < hunger_below or listener.hunger < hunger_below
        if hungry and chat_rng.random() < hint_chance:
            midx, midy = (speaker.x + listener.x) / 2.0, (speaker.y + listener.y) / 2.0
            found = _nearest_food_source(world.berry_tiles, midx, midy, radius)
            if found is not None:
                bush_pos, _dist = found
                food_hint = _food_hint_line(
                    chat_rng, listener.name, bush_pos, (listener.x, listener.y))
    text = None
    if llm is not None and bool(cfg.get("agents.conversation.use_llm", False)):
        try:                              # chatter must never crash the sim
            # With use_llm on, hand the berry-bush context to the model so its line can
            # share real location info; failures fall back to `food_hint` below.
            text = llm.conversation_line(speaker, listener, food_hint=food_hint)
        except Exception:
            text = None
    if not text and food_hint is not None:
        text = food_hint                  # LLM offline/failed -> deterministic hint line still works
    if not text:
        text = _deterministic_line(chat_rng, speaker, listener,
                                   str(world.weather.get("state", "")))
    speaker.current_bubble = clip(text, max_chars)
    speaker.bubble_start_tick = int(world.tick)
    return {"speaker": speaker.uid, "listener": listener.uid,
            "text": speaker.current_bubble}
