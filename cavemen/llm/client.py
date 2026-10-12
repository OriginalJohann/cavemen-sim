"""OpenAI-compatible LLM client for agent decisions.

Works with local providers (e.g. LM-Studio) and external OpenAI-compatible
endpoints via configurable base_url/api_key/model. Failures degrade gently:
every method returns None instead of raising, so the simulation continues
with deterministic fallback behaviour (user-friendly, no stack traces).
"""
import json
import re
import urllib.request

ACTIONS = {"move", "hunt", "gather", "rest", "fish"}
SYSTEM_PROMPT = (
    'You steer one caveman in a top-down survival simulation. '
    'Reply with STRICT JSON only: {"action": "move|hunt|gather|rest|fish", '
    '"dx": -1/0/1, "dy": -1/0/1}. Fish at the lake shore when hungry; hunt and gather nearby. '
    "rest to recover stamina." )


def _valid_action(parsed) -> dict | None:
    """Validate an LLM answer against the fixed action grammar."""
    if not isinstance(parsed, dict):
        return None
    action = parsed.get("action")
    dx, dy = parsed.get("dx", 0), parsed.get("dy", 0)
    if action not in ACTIONS:
        return None
    try:
        dx, dy = int(dx), int(dy)
    except (TypeError, ValueError):
        dx, dy = 0, 0
    if not (-1 <= dx <= 1 and -1 <= dy <= 1):
        return None
    if action == "rest":
        dx = dy = 0
    return {"action": str(action), "dx": dx, "dy": dy}


class LLMClient:
    def __init__(self, cfg):
        self.cfg = cfg
        base = str(cfg.get("llm.base_url", "http://127.0.0.1:1234/v1")).rstrip("/")
        if not base.endswith("/chat/completions"):
            base += "/chat/completions"
        self.url = base
        self.api_key = str(cfg.get("llm.api_key", "") or "")
        self.model = str(cfg.get("llm.model", "local-model"))
        self.timeout = float(cfg.get("llm.timeout_s", 8))
        self.retries = max(0, int(cfg.get("llm.max_retries", 2)))
        # Offline latch: once the endpoint fully fails we never block the
        # simulation again - all further calls return immediately so the sim
        # keeps running at full speed in fallback mode.
        self._offline = False

    def _post(self, messages):
        if self._offline:
            # endpoint already known to be dead -> instant fallback, no waiting
            return None
        payload = {"model": self.model, "messages": messages,
                   "max_tokens": int(self.cfg.get("llm.max_tokens", 300)),
                   "temperature": 0.7}
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        last_error = "unknown"
        for _ in range(self.retries + 1):
            try:
                req = urllib.request.Request(self.url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                content = body["choices"][0]["message"]["content"]
                return self._extract_json(content)
            except Exception as exc:  # graceful degradation, never crash the sim
                last_error = str(exc)
        print(f"[cavemen] LLM endpoint not reachable ({last_error}); fallback mode active.")
        self._offline = True   # latched: subsequent calls skip the network entirely
        return None

    @staticmethod
    def _extract_json(text: str):
        """Pull a JSON object out of an LLM answer (code fences tolerated)."""
        if not isinstance(text, str):
            return None
        text = text.strip()
        match = re.search(r"\{.*?\}", text, flags=re.DOTALL)
        candidate = match.group(0) if match else text
        try:
            return json.loads(candidate)
        except ValueError:
            return None

    def decide_action(self, agent, world):
        """Ask the LLM for the agent's next action; returns dict or None."""
        cfg = self.cfg
        age_years = int(agent.age_years(cfg))
        state = (f"{agent.prompt} | HP {round(agent.hp)}, Stamina {round(agent.stamina)}, "
                 f"Hunger {round(agent.hunger)}%, day {world.day_number()}, "
                 f"weather {world.weather['state']}")
        user = (
            "Decide this caveman's action now.\n"
            f"State: {state}\n"
            'Nearby hints: use dx/dy to step toward food or away from danger.'
        )
        parsed = self._post([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ])
        return _valid_action(parsed)

    def make_character(self, gender: str):
        """Ask the LLM for a name + personality trait; returns dict or None."""
        word = "male" if gender == "m" else "female"
        user = (
            f'Create an individual caveman character ({word}). Reply with STRICT '
            'JSON only: {"name": string max 8 chars, "trait": one personality word}.'
        )
        parsed = self._post([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ])
        if not isinstance(parsed, dict):
            return None
        name = str(parsed.get("name", "")).strip()[:8]
        trait = str(parsed.get("trait", "")).strip()[:12]
        if not name or not trait:
            return None
        return {"name": name, "trait": trait}

    def conversation_line(self, speaker, listener):
        """Ask the LLM for one short caveman line; returns str or None.

        Used only when `agents.conversation.use_llm` is enabled; failures
        degrade to None so the deterministic dialogue pools take over.
        """
        user = (
            f"{speaker.name} says something to {listener.name}. "
            f"Hunger {int(speaker.hunger)}%, age {int(speaker.age_years(self.cfg))} years.\n"
            'Reply with STRICT JSON only: {"line": string, max 60 chars, in English, '
            "one short caveman-flavoured sentence."
        )
        parsed = self._post([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ])
        if not isinstance(parsed, dict):
            return None
        line = str(parsed.get("line", "")).strip()[:60]
        return line or None
