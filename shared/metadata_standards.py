"""
Metadata standardization and cleaning utilities.

This module provides functions to clean and standardize book metadata
according to established standards. All new metadata should be cleaned
using these functions before storage.

Standards:
- Titles: Title Case with proper exception handling
- Authors: Title Case for names, semicolon-separated for multiple
- Years: Plain integers (no commas or formatting)
- Whitespace: Normalized (single spaces, trimmed)
- Quotes: Removed from entire titles
"""

import re
from typing import Optional


# Title case exceptions (lowercase unless at start or after punctuation)
TITLE_CASE_EXCEPTIONS = {
    'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'in', 'into',
    'of', 'on', 'or', 'the', 'to', 'with', 'vs', 'via', 'per'
}


def clean_title(title: Optional[str]) -> Optional[str]:
    """
    Clean and standardize book title.

    Rules:
    - Remove quotes around entire title
    - Title Case with proper exception handling
    - Normalize whitespace
    - Capitalize after colons (subtitles)
    - Preserve intentional punctuation

    Args:
        title: Raw title string

    Returns:
        Cleaned title string

    Examples:
        >>> clean_title('"The rest of us"')
        'The Rest of Us'
        >>> clean_title('the information')
        'The Information'
        >>> clean_title('Real lace: america's irish rich')
        'Real Lace: America's Irish Rich'
    """
    if not title:
        return title

    # Remove quotes around entire title
    title = title.strip()
    if title.startswith('"') and title.endswith('"'):
        title = title[1:-1].strip()

    # Normalize whitespace (multiple spaces to single)
    title = re.sub(r'\s+', ' ', title)

    # Title case with exceptions
    words = title.split()
    result = []

    for i, word in enumerate(words):
        # Always capitalize first and last word
        if i == 0 or i == len(words) - 1:
            result.append(word.capitalize())
        # Capitalize after subtitle markers (: ! ?)
        elif i > 0 and result[i-1][-1] in ':!?':
            result.append(word.capitalize())
        # Check for exception words
        elif word.lower() in TITLE_CASE_EXCEPTIONS:
            result.append(word.lower())
        # Handle hyphenated words
        elif '-' in word:
            parts = word.split('-')
            result.append('-'.join(p.capitalize() for p in parts))
        # Handle words with apostrophes
        elif "'" in word:
            result.append(word.capitalize())
        # Default: capitalize
        else:
            result.append(word.capitalize())

    return ' '.join(result)


def clean_author(author: Optional[str]) -> Optional[str]:
    """
    Clean and standardize author name(s).

    Rules:
    - Title Case for names
    - Normalize whitespace
    - Preserve semicolons for multiple authors
    - Handle suffixes (Jr., Sr., III, etc.)
    - Proper formatting for initials

    Args:
        author: Raw author string (may contain multiple authors)

    Returns:
        Cleaned author string

    Examples:
        >>> clean_author('john smith')
        'John Smith'
        >>> clean_author('JOHN SMITH JR.')
        'John Smith JR.'
        >>> clean_author('jane doe; john smith')
        'Jane Doe; John Smith'
    """
    if not author:
        return author

    # Normalize whitespace
    author = re.sub(r'\s+', ' ', author.strip())

    # Split multiple authors by semicolon
    if ';' in author:
        authors = [_clean_single_author(a.strip()) for a in author.split(';')]
        return '; '.join(authors)

    return _clean_single_author(author)


def _clean_single_author(name: str) -> str:
    """Clean a single author name."""
    # Preserve all-caps suffixes (Jr., Sr., II, III, etc.)
    parts = name.split()
    result = []

    for part in parts:
        # Keep suffixes uppercase
        if part.upper() in ('JR.', 'SR.', 'II', 'III', 'IV', 'V', 'JR', 'SR'):
            result.append(part.upper())
        # Keep initials as-is but ensure proper format
        elif re.match(r'^[A-Z]\.?$', part.upper()):
            result.append(part.upper().rstrip('.') + '.')
        # Title case for regular name parts
        else:
            result.append(part.capitalize())

    return ' '.join(result)


def clean_year(year: Optional[str]) -> Optional[str]:
    """
    Clean and standardize publication year.

    Rules:
    - Remove commas (2,025 -> 2025)
    - Ensure it's a valid 4-digit year
    - Remove any non-digit characters

    Args:
        year: Raw year string

    Returns:
        Cleaned year string (4 digits) or None if invalid

    Examples:
        >>> clean_year('2,025')
        '2025'
        >>> clean_year('2020')
        '2020'
        >>> clean_year('20')
        None
    """
    if not year:
        return year

    # Remove all non-digit characters
    year_str = re.sub(r'[^\d]', '', str(year))

    # Must be 4 digits
    if len(year_str) == 4:
        return year_str

    # If not 4 digits, return None
    return None


def normalize_whitespace(text: Optional[str]) -> Optional[str]:
    """
    Normalize whitespace in any text field.

    Args:
        text: Raw text string

    Returns:
        Text with normalized whitespace

    Examples:
        >>> normalize_whitespace('  hello   world  ')
        'hello world'
    """
    if not text:
        return text

    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)

    # Strip leading/trailing whitespace
    return text.strip()


def clean_metadata(metadata: dict) -> dict:
    """
    Clean all metadata fields in a metadata dictionary.

    This is the main entry point for cleaning metadata. It applies
    all cleaning functions to appropriate fields.

    Args:
        metadata: Dictionary containing book metadata

    Returns:
        Dictionary with cleaned metadata

    Example:
        >>> meta = {'title': 'the information', 'authors': ['john smith'], 'published_year': '2,020'}
        >>> clean_metadata(meta)
        {'title': 'The Information', 'authors': ['John Smith'], 'published_year': '2020'}
    """
    cleaned = metadata.copy()

    # Clean title
    if 'title' in cleaned:
        cleaned['title'] = clean_title(cleaned['title'])

    # Clean subtitle
    if 'subtitle' in cleaned:
        cleaned['subtitle'] = clean_title(cleaned['subtitle'])

    # Clean authors (handle both string and list)
    if 'authors' in cleaned:
        if isinstance(cleaned['authors'], list):
            cleaned['authors'] = [clean_author(a) for a in cleaned['authors']]
        elif isinstance(cleaned['authors'], str):
            cleaned['authors'] = clean_author(cleaned['authors'])

    # Clean canonical_author
    if 'canonical_author' in cleaned:
        # Keep canonical author lowercase for consistency in matching
        pass

    # Clean credited_authors
    if 'credited_authors' in cleaned and isinstance(cleaned['credited_authors'], list):
        cleaned['credited_authors'] = [clean_author(a) for a in cleaned['credited_authors']]

    # Clean publication year
    if 'published_year' in cleaned:
        cleaned['published_year'] = clean_year(str(cleaned['published_year'])) if cleaned['published_year'] else None

    # Clean series name
    if 'series_name' in cleaned and cleaned['series_name']:
        cleaned['series_name'] = clean_title(cleaned['series_name'])

    return cleaned
