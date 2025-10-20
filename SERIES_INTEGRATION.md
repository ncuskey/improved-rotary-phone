# Book Series Integration

This document describes the integration of book series data from bookseries.org into the ISBN Lot Optimizer system.

## Overview

The system now includes comprehensive book series information for over 1,300 authors, 12,770 series, and 104,465 individual books. When you scan a book, the system automatically attempts to match it to known series data and displays series information in the book detail view.

## Features

### 1. Series Database
- **1,300 authors** with biographical information
- **12,770 book series** with complete book lists
- **104,465 books** cataloged with series order information
- Efficient fuzzy matching for author and title variations

### 2. Automatic Matching
When you scan a book:
1. The system compares the book's title and author(s) to the series database
2. Uses fuzzy matching to handle title variations and subtitles
3. Automatically saves high-confidence matches (90%+)
4. Displays series information in the book detail panel

### 3. Web Interface Display
Books matched to series show:
- Series name and author
- Total number of books in the series
- Match confidence score
- Complete series book list (scrollable)

## Components

### Database Tables

#### `authors`
- Stores author names, biographies, and source URLs
- Normalized names for efficient fuzzy matching

#### `series`
- Links authors to their series
- Tracks book counts and metadata

#### `series_books`
- Individual books within each series
- Preserves series order when available

#### `book_series_matches`
- Links ISBNs to matched series
- Stores confidence scores and match methods

### Python Modules

#### `isbn_lot_optimizer/series_database.py`
Core database management for series data:
- `SeriesDatabaseManager` - Database operations
- Fuzzy text matching and normalization
- Author/series/book CRUD operations

#### `isbn_lot_optimizer/series_matcher.py`
Intelligent matching engine:
- `SeriesMatcher` - Main matching logic
- Multiple matching strategies (title, author combinations)
- Confidence scoring (0.0 to 1.0)
- Bulk matching capabilities

#### `isbn_lot_optimizer/series_integration.py`
Integration helpers:
- `match_and_attach_series()` - Match a book and save result
- `get_series_info_for_isbn()` - Retrieve series for an ISBN
- `enrich_evaluation_with_series()` - Add series to evaluation objects

### Scripts

#### `scripts/scrape_bookseries_org.py`
Original scraper for bookseries.org:
```bash
# Scrape all authors and series
python3 scripts/scrape_bookseries_org.py --output bookseries_complete.json

# Test with limited authors
python3 scripts/scrape_bookseries_org.py --limit 10 --output test.json

# Get authors list only (fast)
python3 scripts/scrape_bookseries_org.py --authors-only
```

#### `scripts/import_series_data.py`
Import scraped data into database:
```bash
# Import series data
python3 scripts/import_series_data.py --json-file bookseries_complete.json --db books.db

# Clear existing data first
python3 scripts/import_series_data.py --clear --json-file bookseries_complete.json
```

#### `scripts/match_books_to_series.py`
Match existing scanned books to series:
```bash
# Match all books in database
python3 scripts/match_books_to_series.py --db books.db

# Test with limited books
python3 scripts/match_books_to_series.py --limit 100 --verbose
```

## Usage

### Automatic (Recommended)
Series matching happens automatically when you:
1. Scan a new book via the web interface or iOS app
2. The system fetches metadata and market data
3. Automatically matches to series if available
4. Series info appears in the book detail panel

### Manual Matching
To match existing books in your database:

```bash
# Match all your scanned books
python3 scripts/match_books_to_series.py --db books.db
```

### Updating Series Data
To update with fresh data from bookseries.org:

```bash
# 1. Re-scrape the website
python3 scripts/scrape_bookseries_org.py --output bookseries_complete.json

# 2. Clear and re-import
python3 scripts/import_series_data.py --clear --json-file bookseries_complete.json

# 3. Re-match your books
python3 scripts/match_books_to_series.py --db books.db
```

## Matching Algorithm

### Confidence Scoring
- **≥ 0.90** (90%+) - Auto-saved, high confidence match
- **0.80-0.89** - Good match, shown but not auto-saved
- **< 0.80** - Not shown to user

### Matching Strategies
1. **Author + Title Match**
   - Finds all series by the book's author(s)
   - Compares normalized book title to each book in each series
   - Uses fuzzy string matching (SequenceMatcher)

2. **Normalization**
   - Removes subtitles (text after `:`, `(`, `[`)
   - Removes articles ("the", "a", "an")
   - Converts to lowercase
   - Removes punctuation
   - Normalizes whitespace

### Example Matches
```
Book: "The Atlantis Gene: A Thriller"
Normalized: "atlantis gene thriller"
Matches: "The Atlantis Gene" in "The Origin Mystery Series" by A.G. Riddle
Confidence: 0.92 ✓ Auto-saved
```

## Database Schema

```sql
-- Authors table
CREATE TABLE authors (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    name_normalized TEXT,
    bio TEXT,
    source_url TEXT
);

-- Series table
CREATE TABLE series (
    id INTEGER PRIMARY KEY,
    author_id INTEGER,
    title TEXT,
    title_normalized TEXT,
    book_count INTEGER,
    FOREIGN KEY (author_id) REFERENCES authors(id)
);

-- Series books table
CREATE TABLE series_books (
    id INTEGER PRIMARY KEY,
    series_id INTEGER,
    book_title TEXT,
    book_title_normalized TEXT,
    series_position INTEGER,
    FOREIGN KEY (series_id) REFERENCES series(id)
);

-- Book-series matches
CREATE TABLE book_series_matches (
    isbn TEXT,
    series_id INTEGER,
    confidence REAL,
    match_method TEXT,
    PRIMARY KEY (isbn, series_id)
);
```

## API Integration

The series data is automatically integrated into book evaluations:

```python
from isbn_lot_optimizer.series_integration import get_series_info_for_isbn

# Get series info for an ISBN
series_info = get_series_info_for_isbn("9780062472182", Path("books.db"))

if series_info:
    print(f"Series: {series_info['series_title']}")
    print(f"Author: {series_info['author_name']}")
    print(f"Books: {series_info['book_count']}")
    print(f"Confidence: {series_info['confidence']:.0%}")
```

## Performance

- **Database size**: ~15-20 MB for complete series data
- **Import time**: ~30 seconds for 104K books
- **Matching time**: ~0.1-0.5 seconds per book
- **Memory usage**: Minimal (indexed queries)

## Data Source

All series data is scraped from [bookseries.org](https://www.bookseries.org), a comprehensive catalog of book series organized by author. The data includes:
- Author biographies
- Complete series listings
- Books in series order
- Standalone novels and non-fiction works

## Future Enhancements

Potential improvements:
- [ ] Series-aware lot building (suggest series lots)
- [ ] Missing book detection (identify gaps in series)
- [ ] Series completion scoring
- [ ] Alternative series sources (Goodreads, LibraryThing)
- [ ] User-contributed series corrections
- [ ] ISBN-to-series precomputed index

## Troubleshooting

### Books not matching
- Check if the author name matches exactly
- Verify book title isn't heavily edited
- Check confidence threshold (adjust in code if needed)
- Author might not be in bookseries.org database

### Incorrect matches
- False positives are rare due to author + title matching
- Adjust confidence threshold if needed
- Report patterns to improve normalization

### Performance issues
- Ensure database has proper indexes (automatically created)
- Consider batch matching for large imports
- Use `--limit` flag for testing

## Statistics

Current database stats (as of import):
```
Authors:  1,300
Series:   12,770
Books:    104,465
Matches:  (varies based on your scanned books)
```

## Support

For issues or questions:
1. Check this documentation
2. Review script help: `python3 scripts/[script_name].py --help`
3. Check logs in `~/.isbn_lot_optimizer/activity.log`
