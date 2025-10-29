"""
Centralized lot detection for filtering multi-book listings from market data.

This module provides comprehensive detection of lot/bundle listings using:
- Expanded keyword matching (30+ patterns)
- Regex pattern detection for quantity indicators
- Lot size extraction

Used by:
- market.py: Filter active eBay listings
- ebay_sold_comps.py: Filter Marketplace Insights sold data
- watchcount_scraper.py: Filter WatchCount sold data
- train_price_model.py: Exclude lots from training data
"""

import re
from typing import Optional, Tuple


# Comprehensive keyword list for lot detection
LOT_KEYWORDS = [
    # Original patterns
    "lot of",
    "set of",
    "bundle",
    "collection",

    # Complete/full sets
    "complete set",
    "full set",
    "entire set",

    # Lot variations
    "book lot",
    "novel lot",
    "books lot",
    "paperback lot",
    "hardcover lot",
    "mixed lot",
    " lot ",  # Space-bounded to avoid matching "slot", "ballot", etc.
    "lot-",
    "-lot",
    "(lot)",
    "[lot]",

    # Quantity indicators
    "qty",
    "quantity",
    "bulk",
    "wholesale",
    "x books",
    "books x",

    # Series indicators (often multi-book)
    "complete series",
    "full series",
    "entire series",

    # Seller jargon
    "reseller",
    "resell lot",
    "library sale",
]

# Regex patterns for detecting quantity-based lots
LOT_PATTERNS = [
    # Pattern: "5 books", "7 book lot", "3 novels"
    (r'\d+\s*(?:book|novel|paperback|hardcover)s?\s*(?:lot)?', "number + book/novel"),

    # Pattern: "lot 5", "lot of 5", "lot-5"
    (r'lot\s*[-:]?\s*(?:of\s*)?\d+', "lot + number"),

    # Pattern: "set 5", "set of 5", "set-5"
    (r'set\s*[-:]?\s*(?:of\s*)?\d+', "set + number"),

    # Pattern: "qty: 5", "qty 5", "quantity: 5"
    (r'(?:qty|quantity)\s*:?\s*\d+', "qty indicator"),

    # Pattern: "5 pc", "5 pcs", "5 piece"
    (r'\d+\s*(?:pc|pcs|piece)s?', "piece count"),

    # Pattern: "#7 books", "#5"
    (r'#\d+\s*(?:book|novel)s?', "hash number"),

    # Pattern: "x5 books", "5x books"
    (r'(?:\d+\s*x|x\s*\d+)\s*(?:book|novel)s?', "multiplier"),
]

# Compile regex patterns for efficiency
COMPILED_PATTERNS = [(re.compile(pattern, re.IGNORECASE), reason)
                     for pattern, reason in LOT_PATTERNS]


def is_lot(title: str) -> bool:
    """
    Determine if a title appears to be a lot/bundle listing.

    Args:
        title: The listing title to check

    Returns:
        True if the title matches lot detection patterns, False otherwise

    Examples:
        >>> is_lot("Harry Potter Lot of 5 Books")
        True
        >>> is_lot("Harry Potter and the Sorcerer's Stone")
        False
        >>> is_lot("Complete Set of 7 Harry Potter Books")
        True
    """
    if not title:
        return False

    title_lower = title.lower()

    # Check keyword matches
    for keyword in LOT_KEYWORDS:
        if keyword in title_lower:
            return True

    # Check regex patterns
    for pattern, _ in COMPILED_PATTERNS:
        if pattern.search(title):
            return True

    return False


def extract_lot_size(title: str) -> Optional[int]:
    """
    Extract the lot size from a title if it's a lot listing.

    Args:
        title: The listing title to parse

    Returns:
        The lot size (2-50) if detected, None otherwise

    Examples:
        >>> extract_lot_size("Lot of 7 Harry Potter Books")
        7
        >>> extract_lot_size("Harry Potter Bundle - 3 Books")
        3
        >>> extract_lot_size("Harry Potter and the Sorcerer's Stone")
        None
    """
    if not title:
        return None

    # Try each regex pattern to extract quantity
    patterns_for_extraction = [
        r'lot\s*[-:]?\s*(?:of\s*)?(\d+)',         # "lot 7", "lot of 7"
        r'set\s*[-:]?\s*(?:of\s*)?(\d+)',         # "set 7", "set of 7"
        r'(\d+)\s*(?:book|novel)s?\s*(?:lot)?',   # "7 books", "7 book lot"
        r'(?:qty|quantity)\s*:?\s*(\d+)',         # "qty: 7"
        r'(\d+)\s*(?:pc|pcs|piece)s?',            # "7 pcs"
        r'#(\d+)',                                 # "#7"
        r'(?:(\d+)\s*x|x\s*(\d+))',               # "7x" or "x7"
    ]

    for pattern in patterns_for_extraction:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            # Handle patterns with multiple capture groups
            quantity_str = next((g for g in match.groups() if g), None)
            if quantity_str:
                try:
                    quantity = int(quantity_str)
                    # Validate range (2-50) to avoid false positives
                    if 2 <= quantity <= 50:
                        return quantity
                except ValueError:
                    continue

    return None


def get_lot_detection_reason(title: str) -> Optional[str]:
    """
    Get the reason why a title was detected as a lot (for debugging).

    Args:
        title: The listing title to check

    Returns:
        The detection reason string, or None if not a lot

    Examples:
        >>> get_lot_detection_reason("Lot of 5 Books")
        'keyword: lot of'
        >>> get_lot_detection_reason("7 Books Bundle")
        'pattern: number + book/novel'
    """
    if not title:
        return None

    title_lower = title.lower()

    # Check keywords
    for keyword in LOT_KEYWORDS:
        if keyword in title_lower:
            return f"keyword: {keyword}"

    # Check regex patterns
    for pattern, reason in COMPILED_PATTERNS:
        if pattern.search(title):
            return f"pattern: {reason}"

    return None


def get_lot_stats(titles: list[str]) -> dict:
    """
    Get statistics on lot detection for a list of titles.

    Args:
        titles: List of titles to analyze

    Returns:
        Dict with stats: total, lot_count, individual_count, lot_percentage

    Example:
        >>> titles = ["Book 1", "Lot of 5 Books", "Book 2", "Set of 3"]
        >>> get_lot_stats(titles)
        {'total': 4, 'lot_count': 2, 'individual_count': 2, 'lot_percentage': 50.0}
    """
    total = len(titles)
    lot_count = sum(1 for title in titles if is_lot(title))
    individual_count = total - lot_count
    lot_percentage = (lot_count / total * 100) if total > 0 else 0.0

    return {
        "total": total,
        "lot_count": lot_count,
        "individual_count": individual_count,
        "lot_percentage": round(lot_percentage, 2)
    }


# For backward compatibility with existing code
def parse_lot_size_from_title(title: str) -> Optional[int]:
    """
    Backward compatibility wrapper for extract_lot_size().

    This matches the signature of the function in market.py.
    """
    return extract_lot_size(title)


if __name__ == "__main__":
    # Test cases
    test_titles = [
        ("Harry Potter and the Sorcerer's Stone", False, None),
        ("Lot of 5 Harry Potter Books", True, 5),
        ("Complete Set of 7 Books", True, 7),
        ("Bundle: 3 Novels", True, 3),
        ("Book Collection", True, None),
        ("10 Book Lot", True, 10),
        ("Qty: 5 Books", True, 5),
        ("The Slot Machine Book", False, None),  # Should NOT match
        ("Ballot Book", False, None),  # Should NOT match
        ("First Edition", False, None),
        ("Series Complete Set", True, None),
    ]

    print("Lot Detector Test Results:")
    print("-" * 80)

    for title, expected_lot, expected_size in test_titles:
        is_lot_result = is_lot(title)
        size = extract_lot_size(title)
        reason = get_lot_detection_reason(title)

        lot_match = "✓" if is_lot_result == expected_lot else "✗"
        size_match = "✓" if size == expected_size else "✗"

        print(f"{lot_match} {size_match} | {title}")
        print(f"        Lot: {is_lot_result} | Size: {size} | Reason: {reason}")
        print()
