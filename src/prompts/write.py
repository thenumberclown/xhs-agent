"""Prompt templates for the Write Agent.

Sub-modules: strategy selection, headline generation, body expansion.
All prompts output JSON.
"""

from .analyze import (
    STRATEGY_SYSTEM,
    STRATEGY_USER,
    HEADLINE_SYSTEM,
    HEADLINE_USER,
    BODY_SYSTEM,
    BODY_USER,
)

__all__ = [
    "STRATEGY_SYSTEM",
    "STRATEGY_USER",
    "HEADLINE_SYSTEM",
    "HEADLINE_USER",
    "BODY_SYSTEM",
    "BODY_USER",
]
