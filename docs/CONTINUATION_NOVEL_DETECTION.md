# Continuation Novel Detection

## Overview

The system automatically detects and filters out continuation novels (books published after an author's death using their name) to prevent false positive value uplifts for first edition and signed book checks.

## Problem Statement

Continuation novels are books published posthumously using a famous deceased author's name, often written by other authors. For example:
- "The Monogram Murders" (2014) by Sophie Hannah, using Agatha Christie's name (died 1976)
- "The House of Silk" (2011) by Anthony Horowitz, a new Sherlock Holmes novel (Arthur Conan Doyle died 1930)
- Tom Clancy novels published after his death in 2013

These books should not receive first edition or signed book value uplifts based on the deceased author's fame, as they are not genuine works by the famous author.

## Implementation

### Detection Logic (`shared/reprint_detector.py`)

The `is_likely_reprint()` function uses four signals to detect reprints and continuation novels:

1. **Title Keywords**: Anniversary editions, reissues, etc.
2. **ISBN Format vs. Publication Date**: Pre-1960 books with ISBN-13, etc.
3. **Collectible Exceptions**: Harry Potter, Lord of the Rings, etc. are allowed
4. **Posthumous Publication**: Books published after a famous author's death

#### Signal 4: Posthumous Publication Detection

```python
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
```

The detector:
1. Normalizes author names to handle various formats (e.g., "CHRISTIE,AGATHA" → "christie agatha")
2. Uses set-based matching to detect famous authors regardless of word order
3. Compares publication year with death year
4. Flags as reprint if `published_year > death_year`

### Author Name Normalization

The system handles multiple author name formats:
- "LASTNAME, FIRSTNAME" (database format)
- "Firstname Lastname" (standard format)
- "lastname, firstname" (lowercase with comma)

Normalization steps:
```python
author_lower = author.lower().replace(',', ' ').strip()
author_normalized = ' '.join(author_lower.split())  # Remove extra whitespace
author_parts = set(author_normalized.split())  # Convert to set for matching
```

This allows matching "CHRISTIE,AGATHA" against "agatha christie" in the death years database.

### Integration with Value Uplift System

The reprint detector is integrated at two points in `/isbn_web/api/routes/books.py`:

#### 1. First Edition Check (line ~129)
```python
if is_first_edition is not True:
    if is_likely_reprint(metadata):
        logger.debug(f"Skipping first edition uplift - detected as reprint")
    elif _edition_estimator.is_ready():
        # Calculate first edition premium
```

#### 2. Signed Check (line ~232)
```python
if is_signed is not True:
    if is_likely_reprint(metadata):
        logger.debug(f"Skipping signed uplift - detected as reprint/continuation")
    else:
        # Check for collectible author and calculate signed premium
```

## Test Cases

All test cases pass in `/tmp/test_continuation.py`:

1. ✓ **Monogram Murders** (2014, Agatha Christie died 1976) - Filtered
2. ✓ **House of Silk** (2011, Conan Doyle died 1930) - Filtered
3. ✓ **Tom Clancy Firing Point** (2020, Clancy died 2013) - Filtered
4. ✓ **Genuine Agatha Christie from 1970** - Allowed (published before death)

## Results

### Before Fix
The Monogram Murders showed:
- Total potential: **$1,507.38**
- Signed: $1,000.00
- First Edition: $500.00
- Condition/Format: $7.38

### After Fix
- Total potential: **$7.38**
- Condition/Format: $7.38 only
- Signed and First Edition checks correctly filtered out

## Maintenance

To add more famous authors to the detection system:

1. Add to `FAMOUS_AUTHOR_DEATH_YEARS` in `shared/reprint_detector.py`
2. Use lowercase "firstname lastname" format
3. Include the year of death as the value

Example:
```python
'isaac asimov': 1992,
'michael crichton': 2008,
```

## See Also

- `shared/reprint_detector.py` - Core detection logic
- `isbn_web/api/routes/books.py` - Integration with value uplift system
- `shared/collectible_detection.py` - Fame multiplier system
