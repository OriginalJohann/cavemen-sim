"""World save/load management.

At most three world slots can exist (config: worlds.max_worlds). Saves are
plain JSON files in the configured save directory; overwriting a used slot
requires an explicit force flag, so worlds are never lost accidentally.
"""
import json
import os

class SaveError(Exception):
    """User-friendly error for any save/load problem (no raw tracebacks)."""


def slots_dir(cfg) -> str:
    return os.path.expanduser(str(cfg.get("worlds.save_dir", "~/cavemen_welten")))


def slot_path(cfg, slot: int) -> str:
    return os.path.join(slots_dir(cfg), f"world_{slot}.json")


def list_slots(cfg):
    """Return {slot_number: meta_dict} for every existing saved world."""
    result = {}
    base = slots_dir(cfg)
    if not os.path.isdir(base):
        return result
    max_worlds = int(cfg.get("worlds.max_worlds", 3))
    for slot in range(1, max_worlds + 1):
        path = slot_path(cfg, slot)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            result[slot] = {
                "name": data.get("name", f"world_{slot}"),
                "tick": int(data.get("tick", 0)),
                "seed": data.get("seed"),   # world generation seed (Phase 16), shown in the main menu
                "agents_alive": sum(1 for a in data.get("agents", []) if a.get("alive")),
            }
        except Exception:
            raise SaveError(f"Save file for slot {slot} is corrupted.") from None
    return result


def save_world(world, cfg, slot: int, force: bool = False) -> str:
    """Persist `world` into the given slot. Returns the saved path."""
    max_worlds = int(cfg.get("worlds.max_worlds", 3))
    if not 1 <= slot <= max_worlds:
        raise SaveError(f"Slot {slot} invalid (allowed: 1..{max_worlds}).")
    path = slot_path(cfg, slot)
    existing = os.path.isfile(path)
    if existing and not force:
        raise SaveError(
            f"Slot {slot} already holds a world ('{os.path.basename(path)}'). "
            "Use an empty slot or explicitly overwrite."
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(world.to_dict(), fh, indent=1)
    except Exception as exc:  # disk/serialisation issues -> friendly message
        raise SaveError(f"Could not write world save: {exc}") from exc
    return path


def load_world(cfg, slot: int):
    """Load a saved world from the given slot. Raises SaveError on problems."""
    from .generation import World  # local import to avoid heavy top-level deps
    max_worlds = int(cfg.get("worlds.max_worlds", 3))
    if not 1 <= slot <= max_worlds:
        raise SaveError(f"Slot {slot} invalid (allowed: 1..{max_worlds}).")
    path = slot_path(cfg, slot)
    if not os.path.isfile(path):
        raise SaveError(f"No saved world in slot {slot}.")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        raise SaveError(f"Save file for slot {slot} is corrupted or unreadable.") from None
    if not isinstance(data, dict) or "tiles" not in data:
        raise SaveError(f"Slot {slot} does not look like a world save (missing 'tiles').")
    return World.from_dict(data, cfg)
