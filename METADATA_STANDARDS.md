# Book Metadata Standards

This document defines the standards for book metadata in the LotHelper system.

## Overview

All book metadata must be cleaned and standardized before storage. This ensures:
- Consistent display across the app
- Reliable searching and sorting
- Professional appearance
- Easy maintenance

## Standards by Field

### Titles

**Standard**: Title Case with proper exception handling

**Rules**:
1. Capitalize first and last words always
2. Capitalize words after colons, exclamation marks, question marks (subtitles)
3. Lowercase articles, prepositions, and conjunctions in the middle:
   - `a`, `an`, `the`
   - `and`, `or`, `but`, `as`, `at`
   - `by`, `for`, `from`, `in`, `into`, `of`, `on`, `to`, `with`
   - `vs`, `via`, `per`
4. Capitalize all other words
5. Capitalize both parts of hyphenated words
6. Remove quotes around entire title (but preserve internal quotes)
7. Normalize whitespace (single spaces, no leading/trailing)

**Examples**:
- `the information` → `The Information`
- `"the rest of us"` → `The Rest of Us`
- `real lace: america's irish rich` → `Real Lace: America's Irish Rich`
- `once upon a time` → `Once Upon a Time`
- `the last voyage of Somebody the Sailor` → `The Last Voyage of Somebody the Sailor`

### Authors

**Standard**: Title Case for names

**Rules**:
1. Capitalize each part of the name
2. Keep suffixes uppercase: `JR.`, `SR.`, `II`, `III`, `IV`, `V`
3. Format initials with periods: `J.` not `J`
4. Multiple authors separated by semicolon and space: `; `
5. Normalize whitespace

**Examples**:
- `john smith` → `John Smith`
- `JOHN SMITH JR.` → `John Smith JR.`
- `jane doe; john smith` → `Jane Doe; John Smith`
- `clive cussler; jack du brul` → `Clive Cussler; Jack Du Brul`

### Publication Years

**Standard**: Plain 4-digit integer

**Rules**:
1. Remove all non-digit characters (including commas)
2. Must be exactly 4 digits
3. Store as string for consistency

**Examples**:
- `2,025` → `2025`
- `2020` → `2020`
- `20` → `null` (invalid)

### Series Names

**Standard**: Same as Titles (Title Case)

**Rules**: Follow the same rules as book titles

### Subtitles

**Standard**: Same as Titles (Title Case)

**Rules**: Follow the same rules as book titles

### Canonical Author

**Standard**: Lowercase for matching

**Rules**:
1. Keep lowercase for consistency in series matching
2. Used for deduplication and series detection
3. Not displayed to users

## Implementation

### For New Data

Use the `metadata_standards` module to clean all incoming data:

```python
from shared.metadata_standards import clean_metadata

# Clean metadata dictionary
cleaned = clean_metadata(raw_metadata)

# Or clean individual fields
from shared.metadata_standards import clean_title, clean_author, clean_year

title = clean_title(raw_title)
author = clean_author(raw_author)
year = clean_year(raw_year)
```

### For Existing Data

Run the cleaning script to update all existing records:

```bash
cd ~/ISBN
python3 scripts/clean_metadata.py --db ~/.isbn_lot_optimizer/catalog.db

# Dry run to preview changes
python3 scripts/clean_metadata.py --dry-run
```

## Maintenance

### When to Clean

1. **Always**: Before inserting new books into database
2. **Periodically**: Run cleanup script on existing data
3. **After imports**: After bulk imports from external sources
4. **When noticed**: If you spot formatting issues

### Syncing iOS App Cache

After cleaning the backend database, the iOS app's SwiftData cache will still have old, uncleaned data. To sync the cleaned metadata to the app:

1. Open the LotHelper app
2. Go to the **Books** tab
3. Tap the sort icon (⬆️⬇️) in the top right
4. Select **"Refresh All Books"**
5. Wait for the app to re-fetch all books from the backend

This will:
- Clear the local SwiftData cache
- Re-fetch all books from the backend (with cleaned metadata)
- Update all titles, authors, and years to the new standard

### Verification

Check data quality with SQL queries:

```sql
-- Find lowercase titles
SELECT isbn, title FROM books
WHERE title = LOWER(title) AND title != UPPER(title);

-- Find quoted titles
SELECT isbn, title FROM books
WHERE title LIKE '"%' OR title LIKE '%"';

-- Find years with commas
SELECT isbn, publication_year FROM books
WHERE publication_year LIKE '%,%';
```

## Edge Cases

### Possessives

Titles with possessives follow standard rules:
- `Robert Ludlum's the Treadstone Exile` (lowercase "the" per Chicago Manual of Style)
- If this looks odd, it's technically correct but can be manually adjusted

### All-Caps Titles

Avoid ALL CAPS titles except for:
- Acronyms that are part of the title: `CIA` in `The CIA Handbook`
- Brand names: `IBM` in `IBM and the Holocaust`

### Hyphenated Words

Both parts capitalized unless the first is a prefix:
- `Self-Help` (both capitalized)
- `Re-enter` (prefix lowercase)

### Numbers in Titles

Numbers at the start of titles:
- `1984` (keep as-is)
- `20,000 Leagues Under the Sea` (keep commas in numbers that aren't years)

## Statistics

As of last cleanup (October 2025):
- Total books: 714
- Books cleaned: 573 (80.3%)
- Common issues fixed:
  - Lowercase titles: 100%
  - Quoted titles: 100%
  - Author capitalization: 100%
  - Whitespace normalization: 100%

## Refreshing Market Data

After cleaning metadata, you may want to refresh all market data (vendor offers, eBay prices, Amazon data) to ensure books have current pricing information:

```bash
cd ~/ISBN

# Test with a few books first
python3 scripts/refresh_all_market_data.py --limit 10

# Run on all books (takes ~24 minutes for 713 books)
python3 scripts/refresh_all_market_data.py

# Adjust delay between API calls (default: 2 seconds)
python3 scripts/refresh_all_market_data.py --delay 1.5

# Skip recently updated books (default: skip books updated in last 7 days)
python3 scripts/refresh_all_market_data.py --skip-recent 14
```

**What gets refreshed:**
- eBay market stats (sold comps, active listings, sell-through rate)
- BookScouter vendor offers (buyback prices from multiple vendors)
- Amazon pricing and sales rank
- BooksRun offers

**Notes:**
- Uses a 2-second delay by default to respect API rate limits
- Estimated time: ~2 seconds per book (24 minutes for 713 books)
- Shows progress every 10 books
- Recalculates lots automatically after completion
- Safe to interrupt (Ctrl+C) and resume later

## Tools

- **Cleaning Script**: `scripts/clean_metadata.py`
- **Market Refresh Script**: `scripts/refresh_all_market_data.py`
- **Standards Module**: `shared/metadata_standards.py`
- **Test Data**: `tests/test_metadata_standards.py` (to be created)

## References

- Chicago Manual of Style (17th edition) for title case rules
- Library of Congress standards for author names
- ISBN standards for publication data
