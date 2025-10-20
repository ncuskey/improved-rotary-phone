# Series-Based Lot Building

## Overview

The system now automatically creates series-based lots using the bookseries.org data, showing you exactly which books you have and which ones are missing from each series.

## Features

### Automatic Series Lot Creation

When you have 2+ books from the same series, the system will:
1. **Group them together** as a series lot
2. **Calculate completion percentage** (e.g., "60% complete")
3. **Show which books you have** with positions (e.g., "Have: #1, #2, #5")
4. **Show which books are missing** (e.g., "Missing: #3, #4")
5. **Estimate total lot value**
6. **Apply series bonus** to probability score

### Visual Display

Series lots appear in your "Suggested Lots" table with:
- **Purple-highlighted section** for series details
- **Green checkmarks** for books you have
- **Orange circles** for missing books
- **Completion percentage** prominently displayed
- **Strategy badge** showing "series_enhanced"

## How It Works

### 1. Book Scanning
When you scan a book:
```
Book scanned → Metadata fetched → Series matched → Saved to database
```

### 2. Lot Generation
When lots are recalculated:
```
All books retrieved → Group by series → Check bookseries.org data →
Calculate completion → Build series lots → Display with have/missing info
```

### 3. Series Matching
The system uses the series matches created when books were scanned:
- Looks up which series each ISBN belongs to
- Groups books by series ID
- Gets complete series book list from database
- Compares your books against complete list
- Identifies gaps in your collection

## Example Output

### In the Suggested Lots Table

```
📚 The Hunger Games Series
Strategy: series_enhanced | High Probability

Series Details:
┌─────────────────────────────────────┐
│ The Hunger Games by Suzanne Collins │
│ Have 2 of 3 books (67% complete)    │
│ ✓ Have: #1, #2                      │
│ ○ Missing: #3                        │
│ Estimated value: $24.50              │
└─────────────────────────────────────┘

Books in this Lot:
• The Hunger Games (#1)
• Catching Fire (#2)
```

## Benefits

### For Sellers
1. **Targeted Acquisition** - Know exactly which books to source
2. **Completion Strategy** - See how close you are to complete sets
3. **Better Pricing** - Complete/near-complete sets command premiumprices
4. **Efficient Listing** - Group related books automatically

### For Buyers
1. **Clear Information** - See exactly what's included
2. **Gap Visibility** - Know what's missing upfront
3. **Value Assessment** - Understand set completion
4. **Better Experience** - Professional presentation

## Lot Priority

Series lots are prioritized by:
1. **Completion percentage** (higher = better)
2. **Total estimated value**
3. **Probability score**

Example ranking:
```
1. Harry Potter Series (100% complete, $180)
2. Jack Reacher Series (80% complete, $120)
3. Twilight Series (50% complete, $45)
```

## Configuration

### Minimum Requirements
Series lots are only created when:
- **2+ books** from the same series
- **$10+ estimated value** for the lot
- **Books successfully matched** to bookseries.org data

These thresholds can be adjusted in the code:
```python
# In isbn_lot_optimizer/series_lots.py
build_series_lots_enhanced(
    books=books,
    db_path=db_path,
    min_books=2,      # Minimum books needed
    min_value=10.0    # Minimum lot value
)
```

## Technical Details

### Database Integration
Series lots use data from:
- `book_series_matches` - Links your ISBNs to series
- `series` - Series metadata
- `series_books` - Complete book lists
- `books` - Your scanned book data

### Lot Strategy
The lot is marked with `strategy="series_enhanced"` to distinguish it from:
- `strategy="author"` - Author collections
- `strategy="series"` - Legacy series grouping (without bookseries.org data)
- `strategy="genre"` - Genre collections
- `strategy="value"` - Value bundles

### Justification Format
The justification array contains:
```python
[
    "The Hunger Games by Suzanne Collins",        # Series and author
    "Have 2 of 3 books (67% complete)",          # Completion status
    "Have: #1, #2",                               # Books you have
    "Missing: #3",                                # Books you're missing
    "Estimated value: $24.50"                     # Total value
]
```

## Code Structure

### Key Files

#### `isbn_lot_optimizer/series_lots.py`
Main series lot building logic:
- `build_series_lots_enhanced()` - Creates series lots
- `get_series_details_for_lot()` - Retrieves detailed series info
- Title normalization and matching

#### `isbn_lot_optimizer/lots.py`
Integrated into main lot generation:
- Calls `build_series_lots_enhanced()` when db_path is available
- Falls back to regular series grouping if needed
- Prioritizes series lots in output

#### `isbn_web/templates/components/lot_detail.html`
Enhanced display:
- Special purple section for series_enhanced lots
- Color-coded have (green) and missing (orange) indicators
- Completion percentage highlighting

## API Access

### Get Series Details for a Lot
```python
from pathlib import Path
from isbn_lot_optimizer.series_lots import get_series_details_for_lot

# Get detailed info
details = get_series_details_for_lot(lot, Path("books.db"))

if details:
    print(f"Series: {details['series_title']}")
    print(f"Author: {details['author_name']}")
    print(f"Total Books: {details['total_books']}")
    print(f"Completion: {details['completion_pct']:.0f}%")
    print(f"Have: {details['have_books']}")
    print(f"Missing: {details['missing_books']}")
```

### Build Series Lots Programmatically
```python
from pathlib import Path
from isbn_lot_optimizer.series_lots import build_series_lots_enhanced

# Get your book evaluations
books = service.list_books()

# Build series lots
series_lots = build_series_lots_enhanced(
    books=books,
    db_path=Path("books.db"),
    min_books=2,
    min_value=10.0
)

# Process lots
for lot in series_lots:
    print(f"{lot.name}: {lot.estimated_value}")
    print(f"  Strategy: {lot.strategy}")
    print(f"  Books: {len(lot.book_isbns)}")
    for justification_line in lot.justification:
        print(f"  - {justification_line}")
```

## Troubleshooting

### No Series Lots Appearing

**Possible causes:**
1. **Books not matched to series** - Run the series matching script:
   ```bash
   python3 scripts/match_books_to_series.py --db books.db
   ```

2. **Less than 2 books from same series** - Need at least 2 books

3. **Lot value below $10** - Increase book values or lower threshold

4. **Series data not imported** - Check series database:
   ```bash
   sqlite3 books.db "SELECT COUNT(*) FROM series"
   ```

### Wrong Books Grouped

**Possible causes:**
1. **Title matching issues** - Check normalization logic
2. **Multiple series with similar names** - Verify series_id
3. **Books matched to wrong series** - Review match confidence

**Solution:** Re-run matching with higher confidence threshold in code.

### Missing Books Incorrect

**Possible causes:**
1. **Title variation** - Your book title doesn't match bookseries.org
2. **Incomplete series data** - bookseries.org missing books
3. **Normalization mismatch** - Title normalization too aggressive

**Solution:** Check title normalization in `_normalize_title()` function.

## Performance

- **Lot generation time**: +0.5-1 second (negligible)
- **Database queries**: O(n) where n = number of books
- **Memory usage**: Minimal (efficient indexed queries)
- **Scalability**: Handles 1000+ books easily

## Future Enhancements

Potential improvements:
- [ ] Shopping list export (missing books to acquire)
- [ ] Price suggestions for partial vs complete sets
- [ ] Series completion goals/tracking
- [ ] Notify when new books complete a series
- [ ] eBay comps for complete vs partial series
- [ ] Multi-series bundle detection
- [ ] Author series collection lots (all series by one author)

## Related Documentation

- [SERIES_INTEGRATION.md](SERIES_INTEGRATION.md) - Main series integration guide
- [scripts/README_bookseries_scraper.md](scripts/README_bookseries_scraper.md) - Data scraping
- [isbn_lot_optimizer/lots.py](isbn_lot_optimizer/lots.py) - Lot building logic
