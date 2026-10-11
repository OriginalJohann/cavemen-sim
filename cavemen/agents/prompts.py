"""Individual agent prompts: creation and runtime adaptation.

Every caveman gets a short individual prompt (max. 100 chars by config)
describing name, age, gender and personality. During the simulation the
prompt is periodically adapted with current situation facts, always capped
at the same length limit so LLM context stays small and stable.
"""
import random

MALE_NAMES = ["Tavo", "Muro", "Kilo", "Bramo", "Rudo", "Fango"]
female_names = ["Ursa", "Niva", "Tala", "Ora", "Veta", "Ilva"]
TRAITS = ["stur", "frisch", "mutig", "sorgsam", "flink", "ruhig", "neugierig", "stolz"]


def clip(text: str, max_chars: int) -> str:
    """Hard-limit a string to max_chars without breaking words when possible."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0] + "..."
    return cut[:max_chars]


def pick_character(rng: random.Random, gender: str):
    """Deterministic-per-seed name/trait choice used as LLM fallback."""
    names = MALE_NAMES if gender == "m" else female_names
    return rng.choice(names), rng.choice(TRAITS)


def make_initial_prompt(name: str, age_years: float, gender: str, trait: str,
                        max_chars: int) -> str:
    """Build the initial individual prompt (name, age, gender, personality)."""
    word = "Mann" if gender == "m" else "Frau"
    base = f"{name}, {int(age_years)} Jahre alter {word}, {trait}"
    return clip(base, max_chars)


def adapt_prompt(base: str, age_years: float, hunger_pct: int, weather_state: str,
                  max_chars: int, extra: str = "") -> str:
    """Runtime adaptation of the individual prompt with current context facts.

    `extra` is an optional appended context (e.g. berry bushes at the agent's
    tile) so situational details can ride inside the hard character cap.
    """
    situation = f"aktuell {int(age_years)} Jahre alt, Hunger {hunger_pct}%, Wetter {weather_state}"
    if extra:
        situation = f"{situation}, {extra}"
    return clip(f"{base} | {situation}", max_chars)
