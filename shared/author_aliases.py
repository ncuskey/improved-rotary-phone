"""Author alias helpers for normalising credited names."""

from __future__ import annotations

import re
from typing import List, Optional

from shared.constants import AUTHOR_SPLIT_RE

# Minimal, extensible alias map: credited_name -> canonical_name
ALIASES = {
    "Robert Galbraith": "J. K. Rowling",
    "Rowling, Robert Galbraith": "J. K. Rowling",
    # examples you can extend later:
    # "Mark Twain": "Samuel Clemens",
    # "Lemony Snicket": "Daniel Handler",
}


def canonical_author(credited: Optional[str], *, apply_aliases: bool = True) -> Optional[str]:
    """
    Return canonical name for a credited author string.

    This function combines two normalization strategies:
    1. Regex-based normalization (lowercase, split on delimiters, remove punctuation)
    2. Manual alias mapping (e.g., "Robert Galbraith" -> "J. K. Rowling")

    Args:
        credited: The author name to canonicalize
        apply_aliases: If True, apply manual ALIASES mapping after normalization

    Returns:
        Canonicalized author name, or None if input is empty
    """
    if not credited:
        return None

    # Step 1: Basic normalization (from series_index.py approach)
    lowered = credited.strip().lower()
    if not lowered:
        return None

    # Split on common delimiters and take first part
    parts = AUTHOR_SPLIT_RE.split(lowered)
    primary = parts[0] if parts else lowered

    # Remove non-alphanumeric characters (except spaces)
    primary = re.sub(r"[^a-z0-9\s]", " ", primary)
    primary = re.sub(r"\s+", " ", primary).strip()

    if not primary:
        return None

    # Step 2: Apply manual aliases if requested (from old author_aliases.py approach)
    if apply_aliases:
        # Check both original and normalized forms against ALIASES
        original_stripped = credited.strip()
        original_norm = " ".join(original_stripped.replace(",", " ").split())

        # If we find an exact match in ALIASES, use it
        if original_stripped in ALIASES:
            return ALIASES[original_stripped]
        if original_norm in ALIASES:
            return ALIASES[original_norm]

    return primary


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
