"""Live voice roleplay against a buyer built from the rep's own lost deals."""

from .engine import DojoEngine, persona_system_prompt
from .persona import build_persona

__all__ = ["DojoEngine", "build_persona", "persona_system_prompt"]
