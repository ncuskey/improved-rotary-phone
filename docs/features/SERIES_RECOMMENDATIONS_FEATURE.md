# Series-Aware Scanning Recommendations

## Overview

This feature tracks recently scanned books and provides intelligent recommendations when you scan multiple books from the same series. When you scan a book that belongs to a series with previously scanned books, the system will suggest going back to get those books for a series lot.

## How It Works

### Recent Scans Cache

- **Capacity**: Tracks the last 100 scanned ISBNs
- **Information Stored**: ISBN, series name, series ID, series position, title, timestamp
- **Eviction**: Oldest scans are automatically removed when the cache reaches 100 items
- **Session Scope**: The cache is in-memory and persists during the BookService session

### Series Matching

The system matches books to series using:
1. **Series ID** (preferred): Combination of canonical author + canonical series name
2. **Series Name** (fallback): Case-insensitive string matching

This dual approach ensures accurate matching even when metadata varies slightly between sources.

### Recommendation Logic

When you scan a book:
1. The system checks if the book belongs to a series
2. If yes, it searches the recent scans cache for other books in that series
3. **It filters out books already in the database** (books you've already accepted)
4. If matches are found (books NOT yet accepted), a justification message is added:
   - **1 match**: "You recently scanned another book from the 'Series Name' series (#1). Consider going back to get it for a series lot."
   - **Multiple matches**: "You recently scanned 2 other books from the 'Series Name' series (#1, #2). Consider going back to get them for a series lot."
5. The current book is then added to the cache for future recommendations

**Important**: Only books that were scanned but NOT accepted are recommended. This prevents recommending books that are already in your lot.

## Implementation Details

### Files

- **`isbn_lot_optimizer/recent_scans.py`**: Core cache implementation
  - `RecentScansCache` class with deque-based storage
  - Methods for adding scans, searching by series, and retrieving matches

- **`isbn_lot_optimizer/service.py`**: BookService integration
  - `_track_recent_scan()`: Adds scanned book to cache
  - `_enhance_evaluation_with_series_context()`: Checks for series matches and adds justification
  - Integration in `scan_isbn()` method

### Key Methods

#### `RecentScansCache.add_scan()`
Adds a scanned book to the cache. If the ISBN already exists, it updates the entry.

```python
cache.add_scan(
    isbn="9780439708180",
    series_name="Harry Potter",
    series_id="jkrowling:harrypotter",
    series_position="#1",
    title="Harry Potter and the Sorcerer's Stone"
)
```

#### `RecentScansCache.get_series_matches()`
Finds all recently scanned books in the same series.

```python
matches = cache.get_series_matches(
    series_name="Harry Potter",
    series_id="jkrowling:harrypotter"
)
```

#### `RecentScansCache.has_series_books()`
Quick check if any books from a series have been scanned.

```python
if cache.has_series_books(series_id="jkrowling:harrypotter"):
    print("You have Harry Potter books in recent scans!")
```

## Testing

Three test suites verify the implementation:

### Unit Tests (`tests/test_recent_scans.py`)
- Basic cache operations (add, retrieve, clear)
- Max size enforcement (100 items)
- Duplicate ISBN handling
- Case-insensitive series matching

### Integration Tests (`tests/test_series_recommendations.py`)
- Scanning multiple books from the same series
- Mixed series scanning (different series, same author)
- Cache overflow behavior
- Non-series books (graceful handling)

### Acceptance Filtering Tests (`tests/test_series_with_acceptance.py`)
- Verifies accepted books are filtered from recommendations
- Tests partial acceptance scenarios (some accepted, some not)
- Validates the "go back for" list only includes unaccepted books

Run tests:
```bash
PYTHONPATH=. python3 tests/test_recent_scans.py
PYTHONPATH=. python3 tests/test_series_recommendations.py
PYTHONPATH=. python3 tests/test_series_with_acceptance.py
```

## Usage Example

```python
from isbn_lot_optimizer.service import BookService
from pathlib import Path

# Initialize service
service = BookService(Path("books.db"))

# Scan first book in a series
eval1 = service.scan_isbn("9780439708180")  # Harry Potter #1
# No series recommendation (first book)

# Scan second book in same series
eval2 = service.scan_isbn("9780439064873")  # Harry Potter #2
# Justification includes: "Series lot opportunity: You recently scanned
# another book from the 'Harry Potter' series (#1)..."

# Accept book 2 (it gets added to the database)
# ... user accepts the book ...

# Scan third book
eval3 = service.scan_isbn("9780439136365")  # Harry Potter #3
# Justification includes: "Series lot opportunity: You recently scanned
# another book from the 'Harry Potter' series (#1)..."
# Note: Book #2 is NOT recommended because it's already in the database

# Accept book 1
# ... user goes back and gets book 1, accepts it ...

# Scan fourth book
eval4 = service.scan_isbn("9780439139595")  # Harry Potter #4
# Justification includes: "Series lot opportunity: You recently scanned
# another book from the 'Harry Potter' series (#3)..."
# Note: Only Book #3 is recommended (Books #1 and #2 are already accepted)
```

## Benefits

1. **Increases Lot Opportunities**: Helps you identify and build series lots in real-time
2. **Reduces Missed Opportunities**: Reminds you about books you may have left behind
3. **Smart Filtering**: Only recommends books you haven't accepted yet (avoids redundant suggestions)
4. **Session Awareness**: Tracks what you've scanned during your current sourcing trip
5. **Low Overhead**: Only 100 items (~20KB memory), no database persistence needed
6. **Series Quality Signal**: The recommendation doesn't affect buy/reject decision; it only suggests lot potential

## How Acceptance Filtering Works

The system automatically filters out books that are already in your database:

**Scenario**: Scanning Harry Potter books in order
1. Scan Book #1 → No recommendation (first in series)
2. Scan Book #2 → Recommends "go back for Book #1"
3. **Accept Book #2** → Added to database
4. Scan Book #3 → Recommends "go back for Book #1" (NOT Book #2, since it's accepted)
5. **Accept Book #1** → Added to database
6. Scan Book #4 → Recommends "go back for Book #3" (Books #1 and #2 already in lot)

This ensures:
- You don't see redundant recommendations for books already in your lot
- The "go back for" list is always accurate and actionable
- Series lot building is efficient (no duplicate trips)

## Future Enhancements

Potential improvements for future versions:

1. **Persistence**: Save recent scans to disk for cross-session tracking
2. **Configurable Cache Size**: Allow users to adjust the 100-item limit
3. **Location Context**: Track where books were scanned to help navigate back
4. **Time-Based Filtering**: Only show recommendations for books scanned in the last N hours
5. **Frontend Visualization**: Display recent series scans in a dedicated UI panel
6. **Export**: Allow exporting the "go back for" list to share with sourcing partners

## Design Decisions

### Why 100 items?
- Covers a typical sourcing session (most people scan 50-150 books per trip)
- Small memory footprint (~20KB)
- Fast lookups (O(1) for ISBN, O(n) for series matching where n ≤ 100)
- Not too much history (keeps recommendations relevant to current session)

### Why in-memory (not database)?
- Faster access (no disk I/O)
- Session-specific context (fresh start each session)
- Simplifies implementation (no schema changes)
- Series lot opportunities are time-sensitive (most relevant during active scanning)

### Why track after enhancement?
The order is critical:
1. Check for existing series matches (before adding current book)
2. Add justification if matches found
3. Track current book for future scans

This prevents self-referencing (a book recommending itself) and ensures the sequence is correct.

## Notes

- The series recommendation is **informational only** - it doesn't affect the buy/reject probability score
- Books without series information are handled gracefully (no errors, no tracking)
- The cache is cleared when the BookService is recreated (new session)
- Duplicate ISBNs are updated (not duplicated) in the cache
