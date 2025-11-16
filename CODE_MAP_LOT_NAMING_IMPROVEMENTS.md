# Code Map: Lot Naming Improvements

**Date**: November 16, 2025
**Type**: UX Enhancement
**Status**: ✅ Complete

## Overview

Improved lot naming to make lot suggestions more readable, understandable, and professional. Removed confusing author aliases, redundant series prefixes, and eliminated hodgepodge value bundles that mix unrelated items.

## Problem Statement

Lot names were confusing and difficult to understand:

### Before
- **Author lots**: `"The Lincoln lawyer — Connelly. Michael (connelly michael)"` - showed book title, author with punctuation, and redundant canonical author in parentheses
- **Author lots (all caps)**: `"CHILD,LEE Collection"` - used all-caps formatting from raw metadata
- **Series lots**: `"Chronological Order of Jack Reacher Series (2/30 Books)"` - verbose prefix from bookseries.org
- **Value lots**: Mixed unrelated items (different authors, sheet music, etc.) into nonsensical bundles

### After
- **Author lots**: `"Lee Child Collection"` - clean, title-cased author name
- **Series lots**: `"Jack Reacher Series (2/30 Books)"` - clean series name with completion info
- **Value lots**: Disabled entirely - hodgepodge bundles don't make sense and would never sell

## Changes Made

### 1. Series Name Cleanup
**File**: `isbn_lot_optimizer/series_lots.py`
**Lines**: 160-169

Removes redundant prefixes from bookseries.org series data:

```python
# Clean up redundant prefixes from series names
clean_series_title = series_title
# Remove redundant prefixes like "Chronological Order of", "Publication Order of", etc.
for prefix in ["Chronological Order of ", "Publication Order of ", "Order of "]:
    if clean_series_title.startswith(prefix):
        clean_series_title = clean_series_title[len(prefix):]
        break

# Standardized naming convention: "Series Name (X/Y Books)"
lot_name = f"{clean_series_title} ({len(have_positions)}/{book_count} Books)"
```

**Impact**:
- Before: `"Chronological Order of Jack Reacher Series (2/30 Books)"`
- After: `"Jack Reacher Series (2/30 Books)"`

### 2. Author Lot Naming with Title Case
**File**: `isbn_lot_optimizer/service.py`
**Lines**: 1958-1980

Uses canonical author with title case for clean, readable names:

```python
candidate.display_author_label = display_author_label
candidate.canonical_author = canonical_author_value or candidate.canonical_author
# Don't overwrite names for enhanced series lots (they already have completion info)
if suggestion.strategy not in ['series_complete', 'series_incomplete']:
    # Only use series_name for actual series strategy lots
    if suggestion.strategy == 'series' and candidate.series_name:
        # For series lots, use series name without author suffix
        candidate.name = candidate.series_name
    elif display_author_label or canonical_author_value:
        # For author/value lots, use clean author name + descriptive suffix
        # Prefer canonical_author (nicely formatted) over credited name
        if canonical_author_value:
            # Title case the canonical author for better readability
            clean_author = canonical_author_value.title()
        else:
            # Fallback: extract from display_author_label
            clean_author = display_author_label.split('(')[0].split('+aliases')[0].strip().rstrip(' —,')

        # Use different suffix for value lots vs regular author lots
        if suggestion.strategy == 'value':
            candidate.name = f"{clean_author} Value Bundle"
        else:
            candidate.name = f"{clean_author} Collection"
```

**Key Improvements**:
- Uses `canonical_author` (normalized) with `.title()` for proper casing
- Removes redundant parenthetical canonical author info
- Strategy-specific suffixes: "Collection" for author lots, "Value Bundle" for value lots
- Only applies series_name for actual series strategy lots (not author lots)

**Impact**:
- Before: `"CHILD,LEE Collection"` or `"Connelly. Michael (connelly michael)"`
- After: `"Lee Child Collection"`, `"Connelly Michael Collection"`

### 3. Disabled Value Bundles
**File**: `isbn_lot_optimizer/lots.py`
**Lines**: 205-222

Commented out hodgepodge value bundle creation:

```python
# Disabled: Value bundles create hodgepodge mixes of unrelated items that don't make sense
# and would never sell. Low-value books should be handled individually or through
# author/series-specific lots.
# low_value = [book for book in books if book.suppress_single]
# if len(low_value) >= 2:
#     suggestion = _compose_lot(
#         name="Value Bundle",
#         strategy="value",
#         books=low_value,
#         justification=[
#             "Combines sub-$10 books to exceed listing threshold",
#             f"Aggregate estimated value ${_sum_price(low_value):.2f}",
#             _probability_summary(low_value),
#         ],
#         fetch_pricing=fetch_pricing,
#     )
#     if suggestion:
#         suggestions.append(suggestion)
```

**Rationale**: Value bundles mixed completely unrelated items (different authors, genres, sheet music) into lots that buyers would never purchase. Low-value books should be:
- Handled individually if they have market value
- Grouped into author-specific or series-specific lots if cohesive
- Not forced into nonsensical bundles just to meet listing thresholds

## Files Modified

1. **isbn_lot_optimizer/series_lots.py** (lines 160-169)
   - Strip redundant prefixes from bookseries.org series names

2. **isbn_lot_optimizer/service.py** (lines 1958-1980)
   - Use canonical author with title case for lot names
   - Strategy-specific naming logic (series vs author vs value)

3. **isbn_lot_optimizer/lots.py** (lines 205-222)
   - Disabled value bundle creation

4. **isbn_web/api/routes/lots.py** (lines 175-185)
   - Fixed sqlite3.Row AttributeError (prerequisite fix)

## Testing

### Before (8 lots generated)
```
1. "Bosch Universe Series (3/44 Books)" - series_incomplete
2. "The Lincoln lawyer" - author (using series name!)
3. "CHILD,LEE Collection" - author (all caps)
4. "BALDACCI,DAVID Collection" - author (all caps)
5. "Connelly Michael Value Bundle" - value (9 unrelated books!)
6. "Jack Reacher Series (2/30 Books)" - series_incomplete
7. "Cotton Malone Series (2/25 Books)" - series_incomplete
8. "Berry, Steve Collection" - author
```

### After (7 lots generated)
```
1. "Bosch Universe Series (3/44 Books)" - series_incomplete ✅
2. "Connelly Michael Collection" - author ✅
3. "Lee Child Collection" - author ✅
4. "David Baldacci Collection" - author ✅
5. "Jack Reacher Series (2/30 Books)" - series_incomplete ✅
6. "Cotton Malone Series (2/25 Books)" - series_incomplete ✅
7. "Steve Berry Collection" - author ✅
```

**Improvements**:
- All names are clean, readable, and professional
- Author names properly formatted in title case
- Series names stripped of redundant prefixes
- No more hodgepodge value bundles

## User Feedback

User requested lot names be "more readable and understandable" after seeing confusing names like:
- `"The Lincoln lawyer — Connelly. Michael (connelly michael)"`
- `"CHILD,LEE Collection"`
- Value bundles mixing Baldacci, Connelly, and La La Land sheet music

All feedback addressed with this implementation.

## Related Documentation

- **Series Lot System**: `isbn_lot_optimizer/series_lots.py`
- **Lot Building**: `isbn_lot_optimizer/lots.py`
- **Service Layer**: `isbn_lot_optimizer/service.py`
- **Author Aliases**: `shared/author_aliases.py` - provides `canonical_author()` and `display_label()`

## Future Enhancements

Potential improvements:
1. **Smart Author Formatting**: Handle edge cases like "Jr.", "III", multi-part last names
2. **Genre-Based Lots**: Create cohesive lots by genre instead of random value bundles
3. **Condition-Based Lots**: Group similar condition books for specific markets
4. **Custom Naming Rules**: Allow user-defined naming templates
