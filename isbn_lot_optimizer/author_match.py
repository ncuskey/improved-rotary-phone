from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Dict, Iterable, List, Sequence, Tuple


# Common suffixes to ignore for canonical keying
_SUFFIXES = {
    "jr",
    "sr",
    "ii",
    "iii",
    "iv",
    "v",
    "phd",
    "md",
    "esq",
}


_PUNCT_RE = re.compile(r"[^\w\s,]", re.UNICODE)  # keep comma for Last, First detection
_WS_RE = re.compile(r"\s+")
_AND_SPLIT_RE = re.compile(r"\s+(?:and|&)\s+", re.IGNORECASE)


def _strip_accents(text: str) -> str:
    """
    Remove diacritics from a string using NFKD normalization.
    """
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _normalize_spaces(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _tokens_without_initials(tokens: List[str]) -> List[str]:
    """
    Remove middle initials (single-letter tokens) and suffixes from a list of tokens.
    """
    result: List[str] = []
    for t in tokens:
        if not t:
            continue
        if len(t) == 1:  # drop single-letter initials
            continue
        if t in _SUFFIXES:
            continue
        result.append(t)
    return result


def _split_last_first(name: str) -> Tuple[List[str], bool]:
    """
    Split a name that may be in 'Last, First Middle' format.
    Returns (tokens, was_comma_format).
    """
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            last = parts[0]
            rest = parts[1]
            rest = _PUNCT_RE.sub(" ", rest)
            last = _PUNCT_RE.sub(" ", last)
            rest_tokens = [t for t in _normalize_spaces(rest.lower()).split(" ") if t]
            last_tokens = [t for t in _normalize_spaces(last.lower()).split(" ") if t]
            tokens = rest_tokens + last_tokens
            return tokens, True
    # No comma form
    name_clean = _PUNCT_RE.sub(" ", name)
    tokens = [t for t in _normalize_spaces(name_clean.lower()).split(" ") if t]
    return tokens, False


def author_key(name: str) -> str:
    """
    Compute a canonical key for an author suitable for equality/grouping.
    - case-insensitive
    - diacritic-insensitive
    - ignores punctuation
    - reorders 'Last, First Middle' to 'first middle last'
    - strips middle initials (single-letter tokens)
    - strips common suffixes (Jr, Sr, II, III, etc.)
    - collapses whitespace

    Examples:
    'Rowling, J. K.' -> 'jk rowling' -> after removing initials -> 'rowling' (but we keep 'jk' if not single letters)
    'J. K. Rowling'  -> 'jk rowling' -> removes single-letter tokens -> 'rowling'
    'Joanne K Rowling' -> 'joanne rowling'
    """
    if not name:
        return ""
    base = _strip_accents(name)
    tokens, _ = _split_last_first(base)
    # Replace hyphens/underscores that may remain after punctuation scrub
    tokens = [t.replace("_", " ").replace("-", " ") for t in tokens]
    # Split any multi-space tokens again
    split_tokens: List[str] = []
    for t in tokens:
        split_tokens.extend([p for p in t.split() if p])
    tokens = split_tokens
    # Drop initials and suffixes
    tokens = _tokens_without_initials(tokens)
    if not tokens:
        return ""
    # Collapse to unique spacing
    return _normalize_spaces(" ".join(tokens))


def author_key_pair(name: str) -> Tuple[str, str]:
    """
    Returns (key, display_base) where:
    - key is the canonical grouping key
    - display_base is a cleaned version with title-casing for human display
    """
    key = author_key(name)
    display = " ".join(w.capitalize() for w in key.split(" ")) if key else name.strip()
    return key, display


def similarity(a: str, b: str) -> float:
    """
    Compute similarity between two author names using canonical keys and difflib ratio.
    Returns a value in [0,1].

    Heuristic boost:
    - If last names match (common catalog case) and either side is short (e.g., only last name
      or first+last where the other has initials/full first), boost to at least ~0.85.
    """
    ka, kb = author_key(a), author_key(b)
    if not ka or not kb:
        return 0.0
    base = difflib.SequenceMatcher(None, ka, kb).ratio()
    ta, tb = ka.split(), kb.split()
    if ta and tb and ta[-1] == tb[-1]:
        # Last names match. If one side is short (<=2 tokens), they are likely the same author with
        # different initial/first-name representation. Boost conservatively.
        if len(ta) <= 2 or len(tb) <= 2:
            base = max(base, 0.85)
        else:
            base = max(base, 0.9)
    return min(base, 1.0)


def probable_author_matches(
    query: str,
    candidates: Sequence[str],
    threshold: float = 0.8,
    limit: int | None = None,
) -> List[Tuple[str, float]]:
    """
    Find probable matches for an author name against a set of candidates.

    - Canonicalizes names to compare robustly across punctuation/case/initials.
    - Uses difflib ratio as a simple heuristic.
    - Returns list sorted by score desc then candidate name asc.

    threshold: minimum similarity score to include
    limit: optionally cap number of returned matches
    """
    kq = author_key(query)
    if not kq:
        return []

    seen: Dict[str, float] = {}
    for cand in candidates:
        score = similarity(query, cand)
        if score >= threshold:
            # If multiple raw variants map to the same cand string, keep the max score
            if cand not in seen or score > seen[cand]:
                seen[cand] = score

    items = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
    if limit is not None and limit >= 0:
        items = items[:limit]
    return items


def cluster_authors(candidates: Iterable[str], threshold: float = 0.9) -> Dict[str, List[str]]:
    """
    Cluster candidate author names by their canonical keys (strong grouping),
    then post-merge clusters that clearly refer to the same author (e.g.,
    'rowling' vs 'joanne rowling').

    threshold: similarity threshold for merging near-duplicate keys.
    """
    # Initial grouping by canonical key
    groups: Dict[str, List[str]] = {}
    for cand in candidates:
        key = author_key(cand)
        if not key:
            continue
        groups.setdefault(key, []).append(cand)

    if not groups:
        return groups

    # Build index of keys by last token (last name)
    by_last: Dict[str, List[str]] = {}
    for key in list(groups.keys()):
        tokens = key.split()
        if not tokens:
            continue
        last = tokens[-1]
        by_last.setdefault(last, []).append(key)

    # Merge keys that share a last name and are similar
    for last, keys in by_last.items():
        if len(keys) < 2:
            continue
        # Prefer the shortest key as the canonical representative (often just the surname)
        keys_sorted = sorted(keys, key=lambda k: (len(k.split()), len(k)))
        canonical = keys_sorted[0]
        for other in keys_sorted[1:]:
            if other not in groups or canonical not in groups:
                continue
            # If canonical is contained in other, or similarity passes threshold, merge
            similar = similarity(canonical, other) >= threshold
            contains = canonical == last or canonical in other
            if similar or contains:
                # Merge members and drop the other key
                merged = groups.setdefault(canonical, [])
                for name in groups.get(other, []):
                    if name not in merged:
                        merged.append(name)
                groups.pop(other, None)

    return groups
