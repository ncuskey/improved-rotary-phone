# Phase 4b Complete: Utils and Constants Moved to Shared

**Status:** ✅ COMPLETE
**Date:** 2025-10-20
**Commit:** 64bf0e5

## Summary

Successfully moved utility functions and constants to the `shared/` module as the second incremental step of Phase 4. This continues the consolidation of common code used by all three applications.

## What Was Done

### 1. Expanded Shared Module Structure
```
shared/
├── __init__.py          # Package initialization
├── database.py          # Database management (Phase 4a)
├── models.py            # Data models (Phase 4a)
├── utils.py             # ⭐ NEW: ISBN utilities and CSV helpers
└── constants.py         # ⭐ NEW: Shared constants
```

### 2. Moved Core Utilities

**shared/utils.py** (128 lines):
- `normalise_isbn()` - ISBN normalization and validation
- `read_isbn_csv()` - CSV file reading with ISBN detection
- `coerce_isbn13()` - ISBN-10 to ISBN-13 conversion
- `validate_isbn13()`, `validate_isbn10()` - Validation functions
- `compute_isbn13_check_digit()`, `compute_isbn10_check_digit()`

**shared/constants.py** (31 lines):
- `TITLE_NORMALIZER` - Regex for title normalization
- `AUTHOR_SPLIT_RE` - Author name splitting pattern
- `COVER_CHOICES` - Valid cover types list
- `BOOKSRUN_FALLBACK_KEY`, `BOOKSRUN_FALLBACK_AFFILIATE`
- `BOOKSCOUTER_FALLBACK_KEY`
- `DEFAULT_DB_NAME`, `DEFAULT_DB_DIR`

### 3. Updated Imports Across Codebase

**Desktop App (isbn_lot_optimizer/)** - 7 files:
- `app.py` - Uses `normalise_isbn` from shared.utils
- `service.py` - Uses both utils and constants
- `gui.py` - Uses constants
- `clipboard_import.py` - Uses `normalise_isbn`
- `author_aliases.py` - No longer needs relative import
- `series_catalog.py` - Uses `TITLE_NORMALIZER`

**Web App (isbn_web/)** - 2 files:
- `api/routes/books.py` - Changed from `isbn_lot_optimizer.utils` to `shared.utils`
- `api/routes/actions.py` - Changed from `isbn_lot_optimizer.utils` to `shared.utils`

### 4. Removed Duplicate Files
- Deleted `isbn_lot_optimizer/utils.py` (now in shared/)
- Deleted `isbn_lot_optimizer/constants.py` (now in shared/)

## Testing Results

All tests passed:

```bash
✅ python3 -c "from shared.utils import normalise_isbn"
✅ python3 -c "from shared.constants import TITLE_NORMALIZER"
✅ python3 -m isbn_lot_optimizer --no-gui --stats
   - Database: 702 books
   - All functionality working
✅ from isbn_lot_optimizer.service import BookService
✅ All imports work after file deletion
```

## Benefits

1. **Centralized ISBN Logic** - Single source of truth for ISBN validation
2. **Shared Utilities** - CSV reading and ISBN normalization available to all apps
3. **Constants in One Place** - API keys, defaults, patterns all centralized
4. **Web App Integration** - Web routes now use shared module directly
5. **Reduced Duplication** - No need to copy utility functions between apps

## Files Changed

- **Created:** 3 files (2 new shared modules + PHASE4A_COMPLETE.md)
- **Modified:** 9 files (import updates)
- **Deleted:** 2 files (moved to shared/)
- **Total Changes:** 105 insertions, 10 deletions

## Module Dependencies

After Phase 4b, the `shared/` module now contains:
- ✅ database.py (no external dependencies within project)
- ✅ models.py (no external dependencies within project)
- ✅ utils.py (no external dependencies within project)
- ✅ constants.py (no external dependencies within project)

All shared modules are now self-contained with no dependencies on `isbn_lot_optimizer` package!

## What's Left in isbn_lot_optimizer/

The remaining modules in `isbn_lot_optimizer/` fall into these categories:

**Core Services** (may move in later phases):
- `service.py` - Main BookService class
- `metadata.py` - Metadata fetching
- `bookscouter.py` - BookScouter API client
- `booksrun.py` - BooksRun API client
- `market.py` - eBay market data
- `ebay_sold_comps.py` - eBay sold comparisons
- `probability.py` - Lot probability calculations

**Desktop-Specific**:
- `app.py` - Main desktop application entry
- `gui.py` - Tkinter GUI (won't move - desktop only)
- `clipboard_import.py` - Clipboard functionality (desktop only)
- `bulk_helper.py` - Bulk operations UI (desktop only)

**Series Handling**:
- `series_*.py` (7 files) - Series matching and cataloging
  - Used by both web and desktop
  - Could move to shared/ in Phase 4c

**Lot Logic**:
- `lots.py` - Lot generation
- `lot_scoring.py` - Lot scoring
- `lot_market.py` - Lot market analysis
- `book_routing.py` - Book routing decisions

**Supporting**:
- `author_*.py` - Author aliases and matching
- `ebay_auth.py` - eBay OAuth

## Next Steps (Phase 4c)

Potential candidates for Phase 4c:
1. **Series modules** - Move series_*.py to shared/ (used by web and desktop)
2. **API clients** - Move bookscouter.py, booksrun.py to shared/
3. **Core services** - Consider moving service.py or refactoring it
4. **Directory restructure** - Reorganize into apps/{desktop,web,ios}/ structure

Each step will continue to be incremental and tested thoroughly.

## Notes

- Skipped moving `series_integration.py` in this phase because it depends on `series_matcher.py` which is still in isbn_lot_optimizer
- All series-related modules should be moved together in a future phase
- The shared module is now truly shared - no back-dependencies on isbn_lot_optimizer
