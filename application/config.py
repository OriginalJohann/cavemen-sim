"""Central configuration loader.

Loads config.yaml (if present) and deep-merges it over built-in defaults,
so every threshold can be parameterized without touching code. Access via
dotted keys, e.g. cfg.get("agents.vitals.hp_max").
"""
import copy
import json
import os
import re

try:
    import yaml
except ImportError:  # pragma: no cover - config only needed at runtime
    yaml = None

DEFAULTS = {
    "simulation": {
        "max_agents_per_world": 10,
        "tick_rate_hz": 5,
        "ticks_per_day": 24,      # one tick == one sim-hour
        "days_per_year": 36,      # compressed ice-age calendar
    },
    "worlds": {
        "save_dir": "~/cavemen_welten",
        "max_worlds": 3,
        "size": {"tiles_w": 48, "tiles_h": 36},
        # Berry bushes: a finite foraging resource that regrows over time.
        "gather": {
            "berry_count": 14,
            "max_amount": 6,
            "regrow_ticks": 48,
            "gather_yield_hunger": 8.0,
            "flat_gather_bonus": 2.0,
        },
    },
    "agents": {
        "age": {"child_until_years": 5, "elderly_from_year": 40, "death_age_limit": 70},
        "vitals": {"hp_max": 100, "stamina_max": 100, "hunger_max": 100, "starvation_below": 20},
        "reproduction": {"min_adult_years": 12, "max_adult_years": 38,
                          "cooldown_months_after_birth": 6},
        "prompts": {"init_max_chars": 100, "adapt_cooldown_ticks": 24},
        "conversation": {     # agent chatter shown as speech bubbles (transient)
            "enabled": True,
            "max_dist_tiles": 4,
            "chance_per_tick": 0.25,
            "speech_cooldown_ticks": 36,
            "bubble_ticks": 16,
            "use_llm": False,
            "max_chars": 60,
            "food_radius_tiles": 24,      # Manhattan radius around the pair midpoint for berry-bush hints; <=0 disables
            "food_hint_hunger_below": 55.0,  # hint only when speaker or listener hungrier than this
            "food_hint_chance": 0.35,     # probability a speech turns into a food-source hint
        },
        "fishing": {           # extra food source: fishing at lake shores
            "chance_per_try": 0.6,    # probability of a successful catch per try
            "hunger_restore": 8.0,    # satiety restored by one successful catch
            "cooldown_ticks": 12,     # min ticks between attempts (per agent)
        },
    },
    "llm": {
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "",
        "model": "local-model",
        "timeout_s": 30,
        "max_retries": 2,
        "decisions_per_tick": 1,
        "max_tokens": 300,
        "decision_cooldown_ticks": 6,
    },
    "weather": {
        "states": {
            "cold": {"weight": 3, "stamina_drain": 1.5, "hunger_gain": 1.2},
            "mild": {"weight": 4, "stamina_drain": 1.0, "hunger_gain": 1.0},
            "hot": {"weight": 2, "stamina_drain": 1.8, "hunger_gain": 1.6},
            "rain": {"weight": 3, "stamina_drain": 1.4, "hunger_gain": 1.0},
            "storm": {"weight": 1, "stamina_drain": 2.5, "hunger_gain": 1.8},
        },
        "min_ticks_per_state": 20,
    },
    "animals": {
        "max_alive": 26,
        "spawn_radius_min_from_cave_tiles": 4,
        "types": {
            "mammut": {"weight": 3, "speed": 0.2, "aggro_chance": 0.05, "hunt_damage": 8, "size": 2},
            "hoehlenbaer": {"weight": 3, "speed": 0.25, "aggro_chance": 0.15, "hunt_damage": 12, "size": 2},
            "wolf": {"weight": 4, "speed": 0.45, "aggro_chance": 0.30, "hunt_damage": 6, "size": 1},
            "triceratops": {"weight": 2, "speed": 0.3, "aggro_chance": 0.10, "hunt_damage": 18, "size": 3},
        },
    },
    "GUI": {"window_w": 960, "window_h": 540, "tile_px": 16, "side_panel_w": 300},
}


def _deep_merge(base: dict, extra) -> dict:
    """Recursively merge `extra` on top of `base` (no mutation)."""
    if not isinstance(extra, dict):
        return copy.deepcopy(base)
    merged = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or parsed."""


class Config:
    """Wrapper around the effective (merged) configuration dictionary."""

    def __init__(self, path: str | None = None):
        self.path = os.path.abspath(path) if path else os.path.join(os.getcwd(), "config.yaml")
        data = {}
        if os.path.exists(self.path):
            if yaml is None:
                raise ConfigError("pyyaml is required to read config.yaml (install via flake.nix or pip).")
            try:
                with open(self.path, encoding="utf-8") as fh:
                    loaded = yaml.safe_load(fh)
            except Exception as exc:  # friendly error, no raw traceback for users
                raise ConfigError(f"Could not parse config.yaml: {exc}") from exc
            if loaded is None:
                data = {}
            elif not isinstance(loaded, dict):
                raise ConfigError("config.yaml must contain a mapping at the top level.")
            else:
                data = loaded
        self.data = _deep_merge(DEFAULTS, data)

    def get(self, dotted: str, default=None):
        """Fetch a value by dotted key, e.g. 'agents.vitals.hp_max'."""
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def _yaml_scalar(value) -> str:
    """Render one scalar value as a YAML-compatible token."""
    if isinstance(value, bool):                     # must precede the int check (bool subclasses int)
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)   # double-quoted strings are valid YAML


def update_config_values(path: str, updates: dict) -> None:
    """Persist scalar edits of dotted config keys ('llm.model', 'agents.age.child_until_years')
    inside an existing YAML file **in place**: only the value part of matching lines is
    rewritten, so every other line (comments, ordering, unknown keys) is preserved verbatim.

    Raises ConfigError when a key cannot be found or the result no longer parses.
    """
    if yaml is None:
        raise ConfigError("pyyaml is required to update config.yaml.")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc

    lines = text.splitlines(keepends=True)
    # Scan all "name:" lines with an indent stack so dotted keys of ANY depth
    # ('llm.model' as well as 'agents.age.child_until_years') are addressable.
    key_lines: dict[str, int] = {}
    stack: list[tuple[int, str]] = []          # (indent, name) ancestors of the current line
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^( *)([A-Za-z_]\w*):(.*)$", line)
        if not m:
            continue                       # continuation lines of flow-style maps etc.
        indent, name, _rest = len(m.group(1)), m.group(2), m.group(3)
        while stack and stack[-1][0] >= indent:   # drop ancestors at or below this indent level
            stack.pop()
        key_lines[".".join([n for _, n in stack] + [name])] = i
        stack.append((indent, name))

    new_lines = list(lines)
    for dotted, value in updates.items():
        idx = key_lines.get(dotted)
        if idx is None:
            raise ConfigError(f"Config key '{dotted}' not found in {path}; please edit it manually.")
        line = lines[idx]
        m_sub = re.match(r"^( *)([A-Za-z_]\w*):(.*)$", line)   # generic: works at any indent level
        rest = (m_sub.group(3) if m_sub else "").rstrip("\n")
        cm = re.search(r"\s+#", rest)                           # preserve a trailing comment, if any
        body = rest[cm.end():].strip() if cm else ""            # text after the '#' marker itself (no duplication)
        comment = f"   # {body}" if cm else ""
        indent = line[: len(line) - len(line.lstrip())]
        name = dotted.rsplit(".", 1)[-1]                      # leaf key name (works at any depth)
        new_lines[idx] = f"{indent}{name}: {_yaml_scalar(value)}{comment}\n"

    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(new_lines)
    except OSError as exc:
        raise ConfigError(f"Could not write {path}: {exc}") from exc

    # Read-back check so a failed update can never leave behind an unreadable config.
    try:
        with open(path, encoding="utf-8") as fh:
            reloaded = yaml.safe_load(fh)
    except Exception as exc:   # friendly failure instead of raw traceback
        raise ConfigError(f"Config file could not be parsed after the update: {exc}") from None
    if not isinstance(reloaded, dict):
        raise ConfigError("Config file no longer contains a top-level mapping.")
    for dotted in updates:
        node = reloaded
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                raise ConfigError(
                    f"Key '{dotted}' is missing after the update; please check config.yaml manually.")
            node = node[part]
