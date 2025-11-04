# Code Map: Sold Listings URL Enrichment

**Date:** November 4, 2025
**Achievement:** 96.2% price coverage (29,001 prices from 29,657 URLs)

## New Scripts

### `scripts/enrich_sold_listings_urls.py`
**Purpose:** Synchronous URL enrichment (prototype)
**Status:** Superseded by async version
**Performance:** 0.36 URLs/sec (would take 20+ hours)

Key components:
- Basic Decodo API integration
- Sequential processing
- Used for initial testing (5 URLs)

### `scripts/enrich_sold_listings_urls_async.py` ⭐
**Purpose:** Production async URL enrichment
**Status:** Production ready
**Performance:** 2.94 URLs/sec (2.8 hours actual)

**Architecture:**
```
AsyncSoldListingEnricher
├── AsyncDecodoClient (with TokenBucket rate limiting)
├── Batch processor (20 concurrent requests)
├── Platform parser routing
└── Real-time progress tracking
```

**Key Classes:**

1. **TokenBucket**
   - Rate limiting: 30 req/s
   - Smooth request distribution
   - No hard sleeps

2. **AsyncDecodoClient**
   - aiohttp session management
   - Async Decodo API calls
   - Error handling and retries

3. **AsyncSoldListingEnricher**
   - Main orchestrator
   - Batch processing with asyncio.gather()
   - Database updates
   - Progress logging

**Usage:**
```bash
python3.11 scripts/enrich_sold_listings_urls_async.py --concurrency 20
```

**Outputs:**
- Database: Updates `sold_listings` table with prices
- Log: `/tmp/enrich_full_run.log`
- Stats: Real-time progress every 20 URLs

## Monitoring Scripts

### `/tmp/send_update.py`
**Purpose:** Send iMessage progress updates

Features:
- Parses enrichment log
- Extracts progress statistics
- Sends via osascript to Messages.app
- Phone: +1 (208) 720-1241

**Statistics sent:**
- Progress: X/Y URLs (%)
- Rate: URLs/sec
- ETA: hours remaining
- Results: Parsed/Updated/Failed counts

### `/tmp/auto_monitor.sh`
**Purpose:** Automated progress updates every 30 minutes

Simple loop:
```bash
while true; do
    sleep 1800  # 30 minutes
    python3 /tmp/send_update.py
done
```

### `/tmp/imessage_listener.py`
**Purpose:** Two-way iMessage command interface
**Status:** Requires Full Disk Access permission

**Commands supported:**
- `***status` - Current progress
- `***process` - Check if running
- `***pause` - Pause enrichment
- `***resume` - Resume enrichment
- `***stop` - Stop enrichment
- `***help` - Command list

**Technical details:**
- Monitors `~/Library/Messages/chat.db`
- Polling interval: 10 seconds
- State tracking: `/tmp/imessage_last_id.txt`

## Updated Shared Code

### `shared/sold_parser_factory.py`
**Purpose:** Route URLs to platform-specific parsers

Functions:
- `detect_platform(url)` - Identify platform from URL
- `parse_sold_listing(url, html, snippet, platform)` - Main entry point

**Platform mapping:**
```python
{
    'ebay.com': 'ebay',
    'mercari.com': 'mercari',
    'amazon.com': 'amazon'
}
```

### `shared/ebay_sold_parser.py`
**Purpose:** Extract sold listing data from eBay HTML

**Key functions:**

1. **`parse_ebay_sold_listing(url, html, snippet)`**
   - Main parser entry point
   - Returns dict with price, condition, date, features

2. **`_extract_price(html)`**
   - Multiple extraction strategies
   - Handles "Sold for $X.XX" patterns
   - Price range detection

3. **`_extract_condition(html)`**
   - Condition mapping (New, Like New, Very Good, Good, Acceptable)
   - Handles various eBay formats

4. **`_extract_sold_date(html)`**
   - Date parsing with multiple formats
   - Returns ISO format YYYY-MM-DD

**Success rate:** ~92%

### `shared/mercari_sold_parser.py`
**Purpose:** Extract sold listing data from Mercari HTML

Similar structure to eBay parser
**Success rate:** ~94%

### `shared/amazon_sold_parser.py`
**Purpose:** Extract sold listing data from Amazon HTML

Similar structure to eBay parser
**Success rate:** ~91%

## ML Model Integration

### `isbn_lot_optimizer/ml/feature_extractor.py`
**Updated function:** `get_sold_listings_features(isbn, catalog_db_path)`

**New features extracted:**
- `serper_sold_min_price` - Lowest sold price
- `serper_sold_max_price` - Highest sold price
- `serper_sold_avg_price` - Average sold price
- `serper_sold_count` - Number of sold listings
- `serper_sold_ebay_pct` - Percentage from eBay
- `serper_sold_demand_signal` - Demand indicator
- `serper_sold_price_range` - Price variance

**Impact:** These features now represent 50%+ of model importance

### `scripts/train_price_model.py`
**No changes required** - Automatically uses enriched data

**Model improvements:**
- Training samples: 920 → 5,506 (6x increase)
- Sold feature importance: 50%+ (up from <10%)
- Real market data now drives predictions

## Updated Model Files

### `isbn_lot_optimizer/models/price_v1.pkl`
**Version:** v2_sold_listings
**Training date:** November 4, 2025
**Samples:** 5,506
**Performance:** MAE $2.95, R² 0.248

### `isbn_lot_optimizer/models/scaler_v1.pkl`
**Updated:** Reflects new feature distributions with enriched data

### `isbn_lot_optimizer/models/metadata.json`
**New fields:**
```json
{
  "version": "v2_sold_listings",
  "samples": 5506,
  "top_features": [
    "serper_sold_min_price",
    "serper_sold_avg_price",
    "serper_sold_ebay_pct",
    "rating",
    "serper_sold_demand_signal"
  ]
}
```

## Database Schema Changes

### `sold_listings` table - Enriched fields
**Before enrichment:** Most rows had URL but NULL price

**After enrichment:**
- `price` - Now populated for 96.2% of rows
- `condition` - Extracted from listings
- `sold_date` - When item sold
- `signed` - Signed book indicator
- `edition` - Edition information
- `features_json` - Additional features

## Data Flow

```
1. Serper Search
   ↓ (collected previously)
2. sold_listings table (URLs only)
   ↓
3. enrich_sold_listings_urls_async.py
   ├── Fetch HTML via Decodo
   ├── Parse with platform-specific parser
   ├── Extract price, condition, features
   └── Update database
   ↓
4. sold_listings table (96.2% with prices)
   ↓
5. train_price_model.py
   ├── get_sold_listings_features()
   ├── Extract aggregate statistics
   └── Train XGBoost model
   ↓
6. Updated ML model (sold features = 50%+ importance)
```

## Testing & Quality Control

### Test sequence executed:
1. **Small batch (5 URLs):** Initial validation
2. **Medium batch (50 URLs):** Caught bs4 dependency issue
3. **Full collection (29,657 URLs):** Production run

### Quality metrics tracked:
- Success rate: Real-time (target: >90%)
- Parse rate: Updated every 20 URLs
- ETA: Continuously calculated
- Database updates: Verified after each batch

### Lessons learned:
1. Always test on small batches first
2. Monitor success rate in real-time
3. Phone number format matters for iMessage
4. Use fallback logic for incomplete log entries

## Performance Optimizations

### Async benefits:
- **Before:** 0.36 URLs/sec (sequential)
- **After:** 2.94 URLs/sec (async, 8x faster)

### Key optimizations:
1. Token bucket vs. sleep-based rate limiting
2. Batch processing (20 URLs at a time)
3. aiohttp session reuse
4. asyncio.gather() for parallel execution

### Concurrency tuning:
- Started: 20 concurrent requests
- Optimal: 20 (respects 30 req/s limit)
- Formula: concurrency < (rate_limit / avg_latency)

## Dependencies Added

None - all dependencies were already present:
- aiohttp (async HTTP)
- asyncio (async runtime)
- beautifulsoup4 (HTML parsing)
- sqlite3 (database)

**Note:** bs4 was missing during testing but was supposed to be present

## Key Files Reference

**Core scripts:**
- `scripts/enrich_sold_listings_urls_async.py` - Main enrichment
- `scripts/train_price_model.py` - Model training (uses enriched data)

**Parsers:**
- `shared/sold_parser_factory.py` - Router
- `shared/ebay_sold_parser.py` - eBay extraction
- `shared/mercari_sold_parser.py` - Mercari extraction
- `shared/amazon_sold_parser.py` - Amazon extraction

**ML integration:**
- `isbn_lot_optimizer/ml/feature_extractor.py` - Feature extraction

**Models:**
- `isbn_lot_optimizer/models/price_v1.pkl` - Retrained model
- `isbn_lot_optimizer/models/scaler_v1.pkl` - Updated scaler
- `isbn_lot_optimizer/models/metadata.json` - Model metadata

**Monitoring:**
- `/tmp/send_update.py` - iMessage notifications
- `/tmp/auto_monitor.sh` - Automated updates
- `/tmp/imessage_listener.py` - Two-way commands

**Documentation:**
- `docs/analysis/SOLD_LISTINGS_ENRICHMENT_SUCCESS.md` - Full report
- `CODE_MAP_SOLD_LISTINGS_ENRICHMENT.md` - This file

## Next Steps

1. **Retry failed URLs (1,152)**
   - Create retry script
   - Use different strategies for persistent failures

2. **Real-time enrichment pipeline**
   - Enrich new sold listings as discovered
   - Maintain 95%+ coverage

3. **Platform parser improvements**
   - Handle more edge cases
   - Better date/condition extraction
   - Photo extraction

4. **ML model iteration**
   - Monitor prediction accuracy in production
   - A/B test with previous model
   - Fine-tune based on feedback

---

**Summary:** This enrichment work transformed the ML model from estimate-based to market-data-driven, with sold listings features now accounting for 50%+ of prediction importance. The async architecture completed in 2.8 hours vs. the 20-hour sequential estimate, demonstrating the value of proper async design for I/O-bound tasks.
