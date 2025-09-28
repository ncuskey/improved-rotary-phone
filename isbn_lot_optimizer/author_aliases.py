"""Author alias helpers for normalising credited names."""

from __future__ import annotations

from typing import List

# Minimal, extensible alias map: credited_name -> canonical_name
ALIASES = {
    "Robert Galbraith": "J. K. Rowling",
    "Rowling, Robert Galbraith": "J. K. Rowling",
    # examples you can extend later:
    # "Mark Twain": "Samuel Clemens",
    # "Lemony Snicket": "Daniel Handler",
}


def canonical_author(credited: str) -> str:
    """Return canonical name for a credited author string."""
    c = (credited or "").strip()
    if not c:
        return ""
    c_norm = " ".join(c.replace(",", " ").split())
    return ALIASES.get(c, ALIASES.get(c_norm, c))


def display_label(crediteds: List[str]) -> str:
    """Preferred display: show credited name; append canonical if different."""
    if not crediteds:
        return ""
    credited = crediteds[0]
    canon = canonical_author(credited)
    others = crediteds[1:]
    if others and any(canonical_author(a) != canon for a in others):
        return f"{credited} (+aliases → {canon})"
    return credited if credited == canon else f"{credited} ({canon})"

__all__ = ["canonical_author", "display_label", "ALIASES"]
