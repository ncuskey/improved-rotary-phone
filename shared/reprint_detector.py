"""
Reprint/Reissue Detection

Identifies books that are likely modern reprints or reissues of classic works,
which should NOT be considered for first edition premiums.

Strategy:
1. Title-based keyword detection (anniversary editions, reissues, etc.)
2. Age-based heuristics (pre-1960 books with ISBN-13 are reprints)
3. Exception handling for collectible anniversary editions
"""

import re
from typing import Optional
from shared.models import BookMetadata


# Keywords indicating a reprint/reissue
REPRINT_KEYWORDS = [
    r'\banniversary\s+edition\b',
    r'\breissue\b',
    r'\breprint\b',
    r'\bre-print\b',
    r'\brepublished\b',
    r'\brevised\s+edition\b',
    r'\bnew\s+edition\b',
    r'\bupdated\s+edition\b',
    r'\bspecial\s+edition\b',
    r"\bcollector[''']?s?\s+edition\b",
    r'\bdeluxe\s+edition\b',
    r'\billustrated\s+edition\b',
    r'\bfacsimile\b',
    r'\bclassic\s+reprint\b',
    r'\blegacy\s+edition\b',
    r'\bmodern\s+library\b',
    r'\bpenguin\s+classics\b',
    r'\bvintage\s+classics\b',
    r"\beveryman[''']?s?\s+library\b",
]

# Series/authors where anniversary editions ARE collectible and valuable
COLLECTIBLE_ANNIVERSARY_EXCEPTIONS = [
    r'harry\s+potter',
    r'lord\s+of\s+the\s+rings',
    r'the\s+hobbit',
    r'game\s+of\s+thrones',
    r'song\s+of\s+ice\s+and\s+fire',
    r'star\s+wars',
    r'stephen\s+king',  # King anniversary editions can be valuable
    r'tolkien',
]

# Famous authors and their death years (for continuation novel detection)
FAMOUS_AUTHOR_DEATH_YEARS = {
    'agatha christie': 1976,
    'arthur conan doyle': 1930,
    'ian fleming': 1964,
    'robert ludlum': 2001,
    'tom clancy': 2013,
    'v.c. andrews': 1986,
    'robert b. parker': 2010,
    'stieg larsson': 2004,
}

# Patterns indicating continuation novels
CONTINUATION_PATTERNS = [
    r'\bnew\s+.*\s+novel\b',
    r'\bcontinuation\b',
    r'\bauthorized\b.*\bnovel\b',
    r'\bin\s+the\s+tradition\s+of\b',
    r'\bcontinues\s+the\s+legacy\b',
]


def is_likely_reprint(metadata: Optional[BookMetadata]) -> bool:
    """
    Determine if a book is likely a modern reprint/reissue.

    Returns True if the book should NOT receive first edition uplift.

    Args:
        metadata: Book metadata to analyze

    Returns:
        True if likely a reprint (skip first edition uplift)
        False if genuine first edition is possible (calculate uplift)
    """
    if not metadata:
        return False

    # Signal 1: Title-based keyword detection
    title = (metadata.title or '').lower()

    # Check for collectible exceptions first
    for exception_pattern in COLLECTIBLE_ANNIVERSARY_EXCEPTIONS:
        if re.search(exception_pattern, title, re.IGNORECASE):
            # This is a collectible series - even anniversary editions can be valuable
            # Only skip if it's explicitly labeled as a reprint/reissue (not anniversary)
            if re.search(r'\breissue\b|\breprint\b|\bre-print\b', title, re.IGNORECASE):
                return True
            # Anniversary editions of collectible series are valuable
            return False

    # Check for general reprint keywords
    for pattern in REPRINT_KEYWORDS:
        if re.search(pattern, title, re.IGNORECASE):
            return True

    # Signal 2: Age-based heuristic (pre-1960 books with ISBN-13 are reprints)
    isbn = metadata.isbn or ''
    pub_year = metadata.published_year

    # ISBN-13 started in 2007, but books may have been converted earlier
    # Books originally published before 1960 with ISBN-13 (978-prefix) are reprints
    if pub_year and pub_year < 1960 and isbn.startswith('978'):
        return True

    # Signal 3: Very old books (pre-1970) with ANY ISBN should be scrutinized
    # ISBNs weren't widely adopted until the 1970s
    if pub_year and pub_year < 1970 and len(isbn) >= 10:
        # This is likely a reprint, unless it's a collectible series
        # We already checked collectible exceptions above
        return True

    # Signal 4: Continuation novels (posthumous books using famous author names)
    # Check if any author in the list is a famous deceased author
    authors = metadata.authors or tuple()
    for author in authors:
        author_lower = author.lower().replace(',', ' ').strip()
        # Normalize whitespace for matching
        author_normalized = ' '.join(author_lower.split())

        for famous_author, death_year in FAMOUS_AUTHOR_DEATH_YEARS.items():
            famous_normalized = ' '.join(famous_author.split())
            # Check both "firstname lastname" and "lastname firstname" orders
            author_parts = set(author_normalized.split())
            famous_parts = set(famous_normalized.split())

            # Match if all parts of the famous name appear in the author string
            if famous_parts.issubset(author_parts):
                # Check if book was published after author's death
                if pub_year and pub_year > death_year:
                    # This is a posthumous publication using the author's name
                    return True

                # Check if there are multiple authors (continuation by another writer)
                if len(authors) > 1:
                    # Check if title has continuation patterns
                    for pattern in CONTINUATION_PATTERNS:
                        if re.search(pattern, title, re.IGNORECASE):
                            return True

    return False


def get_reprint_explanation(metadata: Optional[BookMetadata]) -> Optional[str]:
    """
    Get human-readable explanation of why a book was identified as a reprint.

    Args:
        metadata: Book metadata

    Returns:
        Explanation string, or None if not a reprint
    """
    if not metadata or not is_likely_reprint(metadata):
        return None

    title = (metadata.title or '').lower()
    isbn = metadata.isbn or ''
    pub_year = metadata.published_year

    # Check what triggered the detection
    for pattern in REPRINT_KEYWORDS:
        if re.search(pattern, title, re.IGNORECASE):
            matched = re.search(pattern, title, re.IGNORECASE)
            if matched:
                return f"Title contains reprint indicator: '{matched.group()}'"

    if pub_year and pub_year < 1960 and isbn.startswith('978'):
        return f"Book from {pub_year} with ISBN-13 (introduced 2007) indicates reprint"

    if pub_year and pub_year < 1970 and len(isbn) >= 10:
        return f"Book from {pub_year} with ISBN (introduced 1970s) indicates reprint"

    # Check for continuation novels
    authors = metadata.authors or tuple()
    for author in authors:
        author_lower = author.lower().replace(',', ' ').strip()
        author_normalized = ' '.join(author_lower.split())

        for famous_author, death_year in FAMOUS_AUTHOR_DEATH_YEARS.items():
            famous_normalized = ' '.join(famous_author.split())
            author_parts = set(author_normalized.split())
            famous_parts = set(famous_normalized.split())

            if famous_parts.issubset(author_parts):
                if pub_year and pub_year > death_year:
                    return f"Posthumous publication: {famous_author.title()} died in {death_year}, book published {pub_year}"
                if len(authors) > 1:
                    return f"Continuation novel: Multiple authors including {famous_author.title()}"

    return "Identified as likely reprint based on metadata"
