# Data Directory

This directory contains large data files used by the ISBN Lot Optimizer.

## Series Data

The application uses book series data from bookseries.org. This data is imported once into the SQLite database and then referenced from there.

### Files

- `bookseries_complete.json` (11MB) - Complete scraped series data
  - **Status:** Can be regenerated with `scripts/scrape_bookseries_org.py`
  - **Already imported into:** `~/.isbn_lot_optimizer/catalog.db`
  - Current database contains: 12,770 series, 1,300 authors

### Regenerating Series Data

If you need to regenerate `bookseries_complete.json`:

```bash
# Scrape fresh data from bookseries.org
python scripts/scrape_bookseries_org.py --output data/bookseries_complete.json

# Import into database
python scripts/import_series_data.py \
  --json-file data/bookseries_complete.json \
  --db ~/.isbn_lot_optimizer/catalog.db
```

**Note:** Be respectful to bookseries.org when scraping (default 1s delay between requests).

## Database Files

Development/test databases should NOT be committed to git:
- Use `~/.isbn_lot_optimizer/catalog.db` for the production database
- Test databases should be created in this directory and added to `.gitignore`

## .gitignore

This directory's `.gitignore` excludes:
- `*.db` - Database files
- `*.json` - Large data files (can be regenerated)
- Keep: Sample/fixture data in `samples/` subdirectory
