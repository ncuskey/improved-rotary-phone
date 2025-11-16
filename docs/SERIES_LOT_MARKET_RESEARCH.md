# Series Lot Market Research System

## Overview

The Series Lot Market Research system automatically collects and analyzes eBay marketplace data for book series to help determine the optimal selling strategy: sell books individually or bundle them into lots.

## Key Features

### 1. Automatic Data Collection During Scanning

When you scan a series book via the iOS app, the system:
- Detects that the book is part of a series
- Checks if we have eBay lot market data for that series
- If not, queues a background enrichment job
- Collects data without blocking the scan workflow

### 2. eBay Market Intelligence

For each series, the system collects:
- **Sold lot listings**: Historical prices and lot sizes
- **Active lot listings**: Current market prices
- **Median prices**: Per-book and total lot prices
- **Optimal lot size**: Most common lot size sold
- **Complete set premium**: Price boost for complete series

### 3. ROI Analysis & Recommendations

The analysis tool compares:
- Individual sale value (sum of ML predictions)
- Lot market value (eBay median × book count)
- Provides clear recommendation with profit difference

Example output:
```
LOT MARKET ANALYSIS:
• eBay Lot Data: $8.57/book (13 comps)
• Optimal Lot Size: 20 books (you have 2)
• Current Books as Lot: $17.14
• Individual Sale Value: $22.66
→ RECOMMEND: Sell individually (+$5.51, 32.2% gain)
```

## Architecture

### Database Schema

#### `series_lot_comps` (metadata_cache.db)
Stores individual eBay lot listings:
- `series_id`: Links to catalog.db series table
- `ebay_url`: Listing URL
- `lot_size`: Number of books in lot
- `price`: Sale/asking price
- `is_sold`: Whether listing sold
- `is_complete_set`: Whether it's a complete series
- `condition`: Book condition

#### `series_lot_stats` (metadata_cache.db)
Aggregated statistics per series:
- `median_sold_price`: Median price of sold lots
- `median_price_per_book`: Price per book in lots
- `most_common_lot_size`: Optimal bundling size
- `sold_lots_count`: Number of comps found
- `has_complete_sets`: Whether complete sets sell
- `enrichment_quality_score`: Data quality metric

### Code Components

#### 1. Data Collection (`scripts/enrich_series_lot_market_data.py`)

**SeriesLotEnricher class** collects eBay data:
- Uses Serper API for Google search
- Uses Decodo API for web scraping
- Searches: `site:ebay.com "Series Title book lot"`
- Extracts: price, lot size, condition, completeness
- Rate limits: Serper 50 req/sec, Decodo 30 req/sec

Usage:
```bash
# Enrich top 10 series by book count
python scripts/enrich_series_lot_market_data.py --limit 10 --results 20

# Force re-process existing data
python scripts/enrich_series_lot_market_data.py --limit 5 --force-reprocess
```

#### 2. Background Task (`isbn_lot_optimizer/series_lot_enrichment_task.py`)

**Functions:**
- `should_enrich_series_lot_data()`: Checks if enrichment needed
- `enrich_series_lot_data_async()`: Async enrichment task
- `enrich_series_lot_data_background()`: Fire-and-forget trigger

**Smart Caching:**
- Skips series with existing data (< 30 days old)
- Retries series with 0 lots found after 30 days
- Checks for API credentials before queuing

**Integration Point:**
`isbn_web/api/routes/books.py:439` - `/evaluate` endpoint

When a series book is evaluated:
```python
if book.metadata.series_id:
    enrich_series_lot_data_background(
        series_id=book.metadata.series_id,
        series_title=book.metadata.series_name,
        author_name=book.metadata.canonical_author
    )
```

#### 3. Analysis Tool (`scripts/analyze_recent_scans.py`)

**RecentScansAnalyzer class** shows lot opportunities:
- Groups scanned books by series
- Queries `series_lot_stats` for market data
- Calculates individual vs lot value
- Shows missing books and completion %
- Recommends optimal selling strategy

**Database Connection:**
```python
# Attaches metadata_cache.db for series_lot_stats access
self.conn.execute(f"ATTACH DATABASE '{metadata_cache_path}' AS metadata")
```

**Query:**
```python
query = """
SELECT median_sold_price, median_price_per_book, most_common_lot_size
FROM metadata.series_lot_stats
WHERE LOWER(series_title) LIKE ?
  AND median_price_per_book IS NOT NULL
"""
```

Usage:
```bash
# Analyze last 20 scans
python scripts/analyze_recent_scans.py --last 20

# Show only series books
python scripts/analyze_recent_scans.py --last 50 --series-only
```

## Workflow Example

### Initial Scan
```
1. User scans "Killing Floor" (Jack Reacher #1)
   ↓
2. System detects: series_id=7732, title="Jack Reacher Series"
   ↓
3. Check: Do we have market data? → NO
   ↓
4. Queue background task: enrich_series_lot_data_async()
   ↓
5. Search eBay: site:ebay.com "Jack Reacher Series book lot"
   ↓
6. Find 13 sold lots: median $8.57/book, optimal size 20 books
   ↓
7. Store in series_lot_stats (series_id=7732)
```

### Subsequent Scans
```
1. User scans "Personal" (Jack Reacher #19)
   ↓
2. System detects: series_id=7732
   ↓
3. Check: Do we have market data? → YES (from earlier)
   ↓
4. Skip enrichment, use existing data
   ↓
5. Analysis shows: 2 books worth $22.66 individually
                   vs $17.14 as lot
   ↓
6. Recommend: Sell individually (+$5.51 profit, 32.2% gain)
```

### Future Scans (New Series)
```
1. User scans "Along Came a Spider" (Alex Cross #1)
   ↓
2. System detects: series_id=5628, title="Alex Cross Series"
   ↓
3. Check: Do we have market data? → NO
   ↓
4. Queue background enrichment for Alex Cross Series
   ↓
5. Build market intelligence automatically
```

## API Requirements

### Environment Variables

Required in `.env`:
```bash
# Serper (Google Search API)
SERPER_API_KEY=your_serper_key_here

# Decodo (Web Scraping)
DECODO_CORE_USERNAME=your_decodo_username
DECODO_CORE_PASSWORD=your_decodo_password
```

### Rate Limits
- **Serper**: 50 requests/second (Google search)
- **Decodo**: 30 requests/second (web scraping)

## Data Quality

### Enrichment Quality Score
Calculated based on:
- Number of comps found (more = better)
- Ratio of sold vs active listings (sold = reliable)
- Presence of complete set data
- Data freshness

### Validation
The system:
- Filters out invalid prices (< $1 or > $1000)
- Excludes listings with lot_size < 2
- Validates eBay URLs
- Handles missing/malformed data gracefully

## Maintenance

### Re-enrichment
Series with 0 lots found are automatically re-enriched after 30 days.

### Manual Re-processing
```bash
# Force re-process series with existing data
python scripts/enrich_series_lot_market_data.py --force-reprocess --limit 20
```

### Monitoring
Check enrichment status:
```bash
sqlite3 ~/.isbn_lot_optimizer/metadata_cache.db \
  "SELECT series_title, total_lots_found, enriched_at
   FROM series_lot_stats
   ORDER BY enriched_at DESC
   LIMIT 10"
```

## Future Enhancements

### Planned Features
1. **Complete Set Detection**: Identify when you have a full series
2. **Optimal Acquisition**: Suggest which books to buy to complete series
3. **Market Trend Analysis**: Track price changes over time
4. **Seasonal Patterns**: Detect best times to sell series lots
5. **Cross-Platform Data**: Integrate Amazon, AbeBooks lot pricing

### Integration Opportunities
- Show lot recommendations in iOS app UI
- Add "Build Lot" button when multiple series books detected
- Alert when series completion threshold reached (e.g., 80%)
- Integrate with eBay listing wizard for automatic lot creation

## Troubleshooting

### No Data Collected
**Problem**: Series enrichment returns 0 lots

**Causes**:
- Series too obscure (no eBay market)
- Search query too specific
- API rate limits exceeded
- Series title mismatch

**Solutions**:
- Check series title in catalog.db
- Run with `--results 20` for more coverage
- Verify API credentials
- Check Serper/Decodo logs

### Incorrect Lot Recommendations
**Problem**: System recommends lot when individual is better (or vice versa)

**Causes**:
- Stale eBay data
- Individual ML predictions inaccurate
- Lot size mismatch (comparing 2 books to 20-book lot data)

**Solutions**:
- Re-enrich series data
- Adjust lot_per_book multiplier in analysis
- Consider book condition differences

### Background Task Not Running
**Problem**: Enrichment doesn't trigger during scans

**Causes**:
- API credentials missing
- Event loop not available
- Series not detected properly

**Check**:
```bash
# Check API logs
tail -f /path/to/api/logs

# Verify series detection
sqlite3 ~/.isbn_lot_optimizer/catalog.db \
  "SELECT id, title FROM series WHERE title LIKE '%Reacher%'"
```

## References

- eBay Search API: [Serper Documentation](https://serper.dev/docs)
- Web Scraping: [Decodo API](https://www.decodo.io/)
- Series Detection: `shared/series_finder.py`
- Lot Building: `isbn_lot_optimizer/lots.py`
