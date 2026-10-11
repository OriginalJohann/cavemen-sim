"""LLM subpackage: OpenAI-compatible client and deterministic fallback."""
from .client import LLMClient
from .fallback import fallback_action, fallback_character
