"""
Centralized feature detection for parsing book attributes from listing titles.

IMPORTANT: This module is designed for MARKETPLACE LISTING TITLES ONLY!

DO apply to:
- eBay listing titles (e.g., "Book - SIGNED First Edition Hardcover w/DJ")
- AbeBooks/Alibris listing titles
- Training data from eBay searches
- User-entered book descriptions

DO NOT apply to:
- Catalog book titles from ISBN APIs (e.g., "Book Title: A Novel")
- Google Books API results
- Open Library metadata
- Basic ISBNdb lookup results

See /docs/FEATURE_DETECTION_GUIDELINES.md for detailed usage guidelines.

Extracts:
- Signed/autographed status (expanded patterns)
- Edition/printing information (1st, 2nd, limited, special, etc.)
- Dust jacket status
- Cover type (Hardcover, Paperback, Mass Market)
- Special features (ex-library, book club, advance reader copy)

Used by:
- ebay_sold_comps.py: Parse eBay listing titles for features
- collect_training_data_poc.py: Extract features from eBay search results
- market.py: Filter and detect features in marketplace listings

WARNING: Applying this to ISBN metadata titles will return None for all features
since those titles don't contain feature information. This is correct behavior -
the issue is applying it to the wrong data source!
"""

import re
from typing import Optional, Dict, Set, Tuple


# ==================== SIGNED DETECTION ====================

SIGNED_PATTERNS = [
    # Basic signed patterns
    (r'\bsigned\b', "signed"),
    (r'\bautographed\b', "autographed"),
    (r'\bautograph\b', "autograph"),
    (r'\binscribed\b', "inscribed"),

    # Qualified signed patterns
    (r'\bhand\s*signed\b', "hand signed"),
    (r'\bhand[\s-]*autographed\b', "hand autographed"),
    (r'\bpersonally\s*signed\b', "personally signed"),
    (r'\bauthor[\s-]*signed\b', "author signed"),
    (r'\bsigned\s*by\s*author\b', "signed by author"),
    (r'\bsigned\s*copy\b', "signed copy"),
    (r'\bautographed\s*copy\b', "autographed copy"),
    (r'\bsigned\s*edition\b', "signed edition"),

    # Signature variants
    (r'\bsignature\b', "signature"),
    (r'\bw/?signature\b', "w/signature"),
    (r'\bwith\s+signature\b', "with signature"),

    # Bookplate/tipped-in signatures
    (r'\bbookplate\s*signed\b', "bookplate signed"),
    (r'\bsigned\s*bookplate\b', "signed bookplate"),
    (r'\bsignature\s*plate\b', "signature plate"),
    (r'\btipped[\s-]*in\s*signature\b', "tipped-in signature"),

    # Common abbreviations
    (r'\bs/\s*a\b', "s/a (signed/autographed)"),
    (r'\bsgnd\b', "sgnd (signed)"),
]

# Compile signed patterns
COMPILED_SIGNED_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in SIGNED_PATTERNS
]


def is_signed(title: str) -> bool:
    """
    Determine if a title indicates a signed/autographed book.

    Args:
        title: The listing title to check

    Returns:
        True if the title contains signed indicators, False otherwise

    Examples:
        >>> is_signed("The Martian by Andy Weir - Signed First Edition")
        True
        >>> is_signed("The Martian by Andy Weir")
        False
        >>> is_signed("Design Patterns Book")  # 'design' contains 'signed' but not a match
        False
    """
    if not title:
        return False

    # Check all signed patterns
    for pattern, _ in COMPILED_SIGNED_PATTERNS:
        if pattern.search(title):
            return True

    return False


def get_signed_detection_reason(title: str) -> Optional[str]:
    """
    Get the reason why a title was detected as signed (for debugging).

    Args:
        title: The listing title to check

    Returns:
        The detection reason string, or None if not signed
    """
    if not title:
        return None

    for pattern, reason in COMPILED_SIGNED_PATTERNS:
        if pattern.search(title):
            return reason

    return None


# ==================== EDITION/PRINTING DETECTION ====================

EDITION_PATTERNS = [
    # First edition patterns
    (r'\b1st\s+edition\b', "1st", "1st edition"),
    (r'\bfirst\s+edition\b', "1st", "first edition"),
    (r'\b1st\s+ed\.?\b', "1st", "1st ed."),
    (r'\bfirst\s+ed\.?\b', "1st", "first ed."),
    (r'\b1st/1st\b', "1st", "1st/1st"),
    (r'\bfirst\s+printing\b', "1st", "first printing"),
    (r'\b1st\s+printing\b', "1st", "1st printing"),
    (r'\bfirst\s+issue\b', "1st", "first issue"),
    (r'\bfirst\s+state\b', "1st", "first state"),
    (r'\btrue\s+first\b', "1st", "true first"),
    (r'\btrue\s+1st\b', "1st", "true 1st"),

    # Numbered editions (2nd through 10th)
    (r'\b2nd\s+edition\b', "2nd", "2nd edition"),
    (r'\bsecond\s+edition\b', "2nd", "second edition"),
    (r'\b3rd\s+edition\b', "3rd", "3rd edition"),
    (r'\bthird\s+edition\b', "3rd", "third edition"),
    (r'\b4th\s+edition\b', "4th", "4th edition"),
    (r'\bfourth\s+edition\b', "4th", "fourth edition"),
    (r'\b5th\s+edition\b', "5th", "5th edition"),
    (r'\bfifth\s+edition\b', "5th", "fifth edition"),
    (r'\b([6-9]|10)(?:th)?\s+edition\b', "later", "later edition"),

    # Special editions
    (r'\blimited\s+edition\b', "limited", "limited edition"),
    (r'\bspecial\s+edition\b', "special", "special edition"),
    (r'\bcollector\'?s?\s+edition\b', "collector's", "collector's edition"),
    (r'\banniversary\s+edition\b', "anniversary", "anniversary edition"),
    (r'\bdeluxe\s+edition\b', "deluxe", "deluxe edition"),
    (r'\billustrated\s+edition\b', "illustrated", "illustrated edition"),
    (r'\bexpanded\s+edition\b', "expanded", "expanded edition"),
    (r'\brevised\s+edition\b', "revised", "revised edition"),
    (r'\bextended\s+edition\b', "extended", "extended edition"),
    (r'\bunabridged\s+edition\b', "unabridged", "unabridged edition"),

    # Printings (when edition not specified)
    (r'\bearly\s+printing\b', "early", "early printing"),
    (r'\blater\s+printing\b', "later", "later printing"),
    (r'\b([2-9]|[1-9][0-9])(?:nd|rd|th)?\s+printing\b', "later", "later printing"),
]

# Compile edition patterns
COMPILED_EDITION_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), edition_type, reason)
    for pattern, edition_type, reason in EDITION_PATTERNS
]


def parse_edition(title: str) -> Optional[str]:
    """
    Parse edition information from a title.

    Args:
        title: The listing title to parse

    Returns:
        Edition type ("1st", "2nd", "limited", "special", etc.) or None

    Examples:
        >>> parse_edition("The Martian - First Edition Hardcover")
        '1st'
        >>> parse_edition("Special Edition with Bonus Content")
        'special'
        >>> parse_edition("Regular paperback")
        None
    """
    if not title:
        return None

    # Check all edition patterns
    for pattern, edition_type, _ in COMPILED_EDITION_PATTERNS:
        if pattern.search(title):
            return edition_type

    return None


def get_edition_detection_reason(title: str) -> Optional[str]:
    """
    Get the reason why an edition was detected (for debugging).

    Args:
        title: The listing title to check

    Returns:
        The detection reason string, or None if no edition detected
    """
    if not title:
        return None

    for pattern, _, reason in COMPILED_EDITION_PATTERNS:
        if pattern.search(title):
            return reason

    return None


# ==================== DUST JACKET DETECTION ====================

DUST_JACKET_PATTERNS = [
    (r'\bdust\s*jacket\b', "dust jacket"),
    (r'\bd/?j\b', "d/j"),
    (r'\bwith\s+jacket\b', "with jacket"),
    (r'\bw/?jacket\b', "w/jacket"),
    (r'\bw/?dj\b', "w/dj"),
    (r'\bdust[\s-]*wrapper\b', "dust wrapper"),
    (r'\bd/?w\b', "d/w"),
]

COMPILED_DUST_JACKET_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in DUST_JACKET_PATTERNS
]


def has_dust_jacket(title: str) -> bool:
    """
    Determine if a title mentions a dust jacket.

    Args:
        title: The listing title to check

    Returns:
        True if dust jacket is mentioned, False otherwise
    """
    if not title:
        return False

    for pattern, _ in COMPILED_DUST_JACKET_PATTERNS:
        if pattern.search(title):
            return True

    return False


# ==================== COVER TYPE DETECTION ====================

HARDCOVER_PATTERNS = [
    (r'\bhardcover\b', "hardcover"),
    (r'\bhardback\b', "hardback"),
    (r'\bhc\b', "hc"),
    (r'\bbound\b', "bound"),
    (r'\bcloth\b', "cloth"),
    (r'\bclothbound\b', "clothbound"),
]

PAPERBACK_PATTERNS = [
    (r'\bpaperback\b', "paperback"),
    (r'\bsoftcover\b', "softcover"),
    (r'\bsoft\s+cover\b', "soft cover"),
    (r'\bpb\b', "pb"),
    (r'\btrade\s+paperback\b', "trade paperback"),
    (r'\btpb\b', "tpb"),
]

MASS_MARKET_PATTERNS = [
    (r'\bmass\s+market\b', "mass market"),
    (r'\bmmpb\b', "mmpb"),
    (r'\bmm\s+paperback\b', "mm paperback"),
    (r'\bpocket\s+book\b', "pocket book"),
]

COMPILED_HARDCOVER_PATTERNS = [(re.compile(p, re.IGNORECASE), r) for p, r in HARDCOVER_PATTERNS]
COMPILED_PAPERBACK_PATTERNS = [(re.compile(p, re.IGNORECASE), r) for p, r in PAPERBACK_PATTERNS]
COMPILED_MASS_MARKET_PATTERNS = [(re.compile(p, re.IGNORECASE), r) for p, r in MASS_MARKET_PATTERNS]


def parse_cover_type(title: str) -> Optional[str]:
    """
    Parse cover type from a title.

    Args:
        title: The listing title to parse

    Returns:
        "Hardcover", "Paperback", "Mass Market", or None

    Note:
        Checks mass market first (most specific), then hardcover, then paperback
    """
    if not title:
        return None

    # Check mass market first (most specific)
    for pattern, _ in COMPILED_MASS_MARKET_PATTERNS:
        if pattern.search(title):
            return "Mass Market"

    # Check hardcover
    for pattern, _ in COMPILED_HARDCOVER_PATTERNS:
        if pattern.search(title):
            return "Hardcover"

    # Check paperback
    for pattern, _ in COMPILED_PAPERBACK_PATTERNS:
        if pattern.search(title):
            return "Paperback"

    return None


# ==================== SPECIAL FEATURES DETECTION ====================

SPECIAL_FEATURE_PATTERNS = [
    # Ex-library
    (r'\bex[\s-]*library\b', "ex-library"),
    (r'\blibrary\s+copy\b', "library copy"),
    (r'\bex[\s-]*lib\b', "ex-lib"),

    # Book club
    (r'\bbook\s+club\b', "book club"),
    (r'\bbce\b', "bce (book club edition)"),
    (r'\bb\.?c\.?e\.?\b', "b.c.e."),

    # Advance reader copy
    (r'\barc\b', "arc"),
    (r'\badvance\s+reader\b', "advance reader"),
    (r'\badvance\s+reading\s+copy\b', "advance reading copy"),
    (r'\badvance\s+copy\b', "advance copy"),
    (r'\bproof\s+copy\b', "proof copy"),
    (r'\buncorrected\s+proof\b', "uncorrected proof"),
    (r'\bgalley\b', "galley"),

    # First thus
    (r'\bfirst\s+thus\b', "first thus"),

    # Limited/numbered
    (r'\bnumbered\s+copy\b', "numbered copy"),
    (r'\blimited\s+to\s+\d+\b', "limited numbered"),
    (r'\b#?\d+\s*\/\s*\d+\b', "numbered (e.g., #42/500)"),
]

COMPILED_SPECIAL_FEATURE_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in SPECIAL_FEATURE_PATTERNS
]


def detect_special_features(title: str) -> Set[str]:
    """
    Detect special features mentioned in a title.

    Args:
        title: The listing title to check

    Returns:
        Set of detected feature strings

    Examples:
        >>> detect_special_features("First Edition ARC - Advance Reader Copy")
        {'arc', 'advance reader'}
        >>> detect_special_features("Ex-Library Book Club Edition")
        {'ex-library', 'book club'}
    """
    if not title:
        return set()

    features = set()
    for pattern, feature in COMPILED_SPECIAL_FEATURE_PATTERNS:
        if pattern.search(title):
            features.add(feature)

    return features


# ==================== COMPREHENSIVE PARSING ====================

class BookFeatures:
    """Container for all detected book features."""

    def __init__(
        self,
        signed: bool = False,
        edition: Optional[str] = None,
        dust_jacket: bool = False,
        cover_type: Optional[str] = None,
        special_features: Optional[Set[str]] = None,
        signed_reason: Optional[str] = None,
        edition_reason: Optional[str] = None,
    ):
        self.signed = signed
        self.edition = edition
        self.dust_jacket = dust_jacket
        self.cover_type = cover_type
        self.special_features = special_features or set()
        self.signed_reason = signed_reason
        self.edition_reason = edition_reason

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "signed": self.signed,
            "edition": self.edition,
            "dust_jacket": self.dust_jacket,
            "cover_type": self.cover_type,
            "special_features": list(self.special_features),
            "signed_reason": self.signed_reason,
            "edition_reason": self.edition_reason,
        }

    def __repr__(self) -> str:
        parts = []
        if self.signed:
            parts.append(f"signed={self.signed_reason or 'true'}")
        if self.edition:
            parts.append(f"edition={self.edition}")
        if self.dust_jacket:
            parts.append("dust_jacket")
        if self.cover_type:
            parts.append(f"cover={self.cover_type}")
        if self.special_features:
            parts.append(f"features={','.join(self.special_features)}")
        return f"BookFeatures({', '.join(parts)})"


def parse_all_features(title: str, include_reasons: bool = False) -> BookFeatures:
    """
    Parse all book features from a title.

    Args:
        title: The listing title to parse
        include_reasons: If True, include detection reasons for debugging

    Returns:
        BookFeatures object with all detected features

    Examples:
        >>> features = parse_all_features("The Martian - Signed First Edition Hardcover w/DJ")
        >>> features.signed
        True
        >>> features.edition
        '1st'
        >>> features.dust_jacket
        True
        >>> features.cover_type
        'Hardcover'
    """
    signed = is_signed(title)
    edition = parse_edition(title)
    dust_jacket = has_dust_jacket(title)
    cover_type = parse_cover_type(title)
    special_features = detect_special_features(title)

    signed_reason = None
    edition_reason = None

    if include_reasons:
        signed_reason = get_signed_detection_reason(title) if signed else None
        edition_reason = get_edition_detection_reason(title) if edition else None

    return BookFeatures(
        signed=signed,
        edition=edition,
        dust_jacket=dust_jacket,
        cover_type=cover_type,
        special_features=special_features,
        signed_reason=signed_reason,
        edition_reason=edition_reason,
    )


# ==================== TESTING ====================

if __name__ == "__main__":
    # Test cases
    test_titles = [
        "The Martian by Andy Weir - First Edition Hardcover",
        "Harry Potter - Signed by JK Rowling - 1st/1st",
        "Design Patterns Book (should not match 'signed')",
        "Special Edition with Dust Jacket",
        "Mass Market Paperback - Ex-Library",
        "Limited Edition #42/500 - Hand Signed",
        "ARC Advance Reader Copy - Uncorrected Proof",
        "2nd Edition Trade Paperback",
        "Book Club Edition BCE",
        "First Thus - Signed Bookplate",
    ]

    print("=" * 80)
    print("FEATURE DETECTION TEST")
    print("=" * 80)
    print()

    for title in test_titles:
        features = parse_all_features(title, include_reasons=True)
        print(f"Title: {title}")
        print(f"  {features}")
        print()
