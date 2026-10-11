"""Agent-to-agent conversation, displayed as speech bubbles above the agents.

Chatter is cheap and offline-safe by design: once per tick one pair of living
agents within a configured distance may speak with a configured probability;
per-agent cooldowns keep nobody monologuing. Lines come from deterministic pools
drawn through the seeded world RNG (reproducible per seed). If
`agents.conversation.use_llm` is enabled and an LLM endpoint answers, the line
is model-generated instead (same strict-JSON contract as the other client
methods); failures fall back to the pools silently. Bubble state is transient UI
data on the agent and deliberately NOT persisted with world saves. Chatter draws from a dedicated seeded RNG (same pattern as the berry bushes in Phase 8) so conversation timing can never perturb the main sim stream - animals, weather and vitals keep their previously balanced behaviour.
"""
import random

from ..agents.prompts import clip

# short caveman-flavoured one-liners; {listener} gets the addressee's name
_GENERIC_LINES = [
    "Ugh, was machst du da, {listener}?",
    "Höhr, {listener}! Die Sonne steht hoch.",
    "{listener}, wir teilen den Beutefund gleich.",
    "Gutes Wetter für die Jagd, meinst du auch, {listener}?",
]
_HUNGRY_LINES = [
    "Mein Magen knurrt... Beeren sind da!",
    "Zuerst essen, dann reden, {listener}.",
    "{listener}, gib mir deine Beeren. Einmalig.",
    "Hunger! Und du siehst auch blass aus, {listener}.",
]
_WEATHER_LINES = {
    "cold":  ["Kalt! Die Höhle ist warm, komm rein, {listener}."],
    "hot":   ["Heiß wie die Sonne. Wasser wäre gut, {listener}."],
    "rain":  ["Regen... nasse Felle sind schlecht, {listener}."],
    "storm": ["Sturm! Besser drinnen bleiben, {listener}."],
}


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
    speaker, listener = world.rng.choice(pairs)   # deterministic per seed
    max_chars = int(cfg.get("agents.conversation.max_chars", 60))
    text = None
    if llm is not None and bool(cfg.get("agents.conversation.use_llm", False)):
        try:                              # chatter must never crash the sim
            text = llm.conversation_line(speaker, listener)
        except Exception:
            text = None
    if not text:
        text = _deterministic_line(world.rng, speaker, listener,
                                   str(world.weather.get("state", "")))
    speaker.current_bubble = clip(text, max_chars)
    speaker.bubble_start_tick = int(world.tick)
    return {"speaker": speaker.uid, "listener": listener.uid,
            "text": speaker.current_bubble}
