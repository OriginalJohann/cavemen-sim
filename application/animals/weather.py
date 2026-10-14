"""Deterministic weather system (fixed procedural rules, no LLM).

Weather cycles through weighted states for a minimum number of ticks and
applies drain/gain factors to agents each tick (see simulation.rules).
"""
import random


class Weather:
    def __init__(self, cfg, rng: random.Random):
        self.cfg = cfg
        self.rng = rng
        states = dict(cfg.get("weather.states", {}))
        if not states:
            raise ValueError("config 'weather.states' must define at least one state")
        self._states = states
        self.state = "mild" if "mild" in states else next(iter(states))
        self.left_ticks = 0

    def step(self) -> str:
        """Advance weather by one tick; returns the current state name."""
        self.left_ticks -= 1
        if self.left_ticks <= 0:
            weights = [(name, max(0.0, float(spec.get("weight", 1)))) for name, spec in self._states.items()]
            total = sum(w for _, w in weights)
            roll = self.rng.random() * total
            acc = 0.0
            chosen = next(iter(weights))
            for name, w in weights:
                acc += w
                if roll <= acc:
                    chosen = (name, w)
                    break
            self.state = chosen[0]
            self.left_ticks = int(self.cfg.get("weather.min_ticks_per_state", 20))
        return self.state

    def effects(self) -> dict:
        """Per-tick modifiers applied to agents by the rule engine."""
        spec = self._states[self.state]
        return {"stamina_drain": float(spec.get("stamina_drain", 1.0)),
                "hunger_gain": float(spec.get("hunger_gain", 1.0))}
