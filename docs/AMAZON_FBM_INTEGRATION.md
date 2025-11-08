# Amazon FBM (Fulfilled by Merchant) Integration

## Overview

The Amazon FBM integration collects third-party seller pricing data from Amazon, filtering out Amazon direct sales and FBA (Fulfilled by Amazon) listings. This provides comparable marketplace data to eBay for ML model training.

## Why FBM Data?

FBM sellers are third-party merchants who handle their own fulfillment, similar to eBay sellers. This data is valuable because:

1. **Comparable to eBay**: FBM and eBay sellers operate in similar marketplaces
2. **Training Data**: Provides additional platform-specific pricing for ML models
3. **Market Insights**: Shows competitive pricing from non-Amazon sellers
4. **Specialist Models**: Enables Amazon FBM specialist model training

## Architecture

### Database Schema

**Table**: `cached_books` (in `metadata_cache.db`)

**New Fields**:
- `amazon_fbm_count` (INTEGER): Number of FBM sellers
- `amazon_fbm_min` (REAL): Lowest FBM price
- `amazon_fbm_median` (REAL): Median FBM price
- `amazon_fbm_max` (REAL): Highest FBM price
- `amazon_fbm_avg_rating` (REAL): Average seller rating (percentage)
- `amazon_fbm_collected_at` (TEXT): Collection timestamp

**Indexes**:
- `idx_amazon_fbm_median`: Fast queries on median FBM price
- `idx_amazon_fbm_count`: Fast queries on FBM seller count

### Components

1. **Database Migration** - `scripts/add_amazon_fbm_fields.py`
   - Adds FBM fields to cached_books table
   - Creates indexes for performance
   - Idempotent (safe to run multiple times)

2. **FBM Parser** - `shared/amazon_fbm_parser.py`
   - Filters FBM from FBA/Amazon direct
   - Parses Decodo amazon_pricing responses
   - Calculates aggregate statistics

3. **Collection Script** - `scripts/collect_amazon_fbm_prices.py`
   - Fetches Amazon pricing via Decodo API
   - Filters for FBM sellers only
   - Updates metadata_cache.db

## Usage

### 1. Run Database Migration

First, add the FBM fields to your database:

```bash
python scripts/add_amazon_fbm_fields.py
```

**Output:**
```
Adding column: amazon_fbm_count (INTEGER)
Adding column: amazon_fbm_min (REAL)
Adding column: amazon_fbm_median (REAL)
Adding column: amazon_fbm_max (REAL)
Adding column: amazon_fbm_avg_rating (REAL)
Adding column: amazon_fbm_collected_at (TEXT)
Created index: idx_amazon_fbm_median
Created index: idx_amazon_fbm_count

✓ Migration complete: Added 6 new columns
```

### 2. Set Decodo Credentials

The collection script requires Decodo API credentials:

```bash
export DECODO_AUTHENTICATION="your_username"
export DECODO_PASSWORD="your_password"
```

### 3. Collect FBM Pricing Data

**Test Mode** (10 ISBNs):
```bash
python scripts/collect_amazon_fbm_prices.py --test
```

**Production Mode**:
```bash
# Process all unenriched ISBNs (concurrency 10)
python scripts/collect_amazon_fbm_prices.py --concurrency 10

# Process first 1000 ISBNs (concurrency 50)
python scripts/collect_amazon_fbm_prices.py --concurrency 50 --limit 1000

# Process with offset for parallel execution
python scripts/collect_amazon_fbm_prices.py --concurrency 40 --offset 0 --limit 5000
```

**Arguments**:
- `--concurrency N`: Number of concurrent requests (default: 10)
- `--limit N`: Maximum ISBNs to process (default: all)
- `--offset N`: Skip first N ISBNs (enables parallel processing)
- `--test`: Test mode, process only 10 ISBNs

### Parallel Collection

For faster collection of large datasets, run multiple collection processes in parallel using `--offset` and `--limit`:

```bash
# Split 19,374 ISBNs across 3 processes
# Process 1: ISBNs 0-6457
python scripts/collect_amazon_fbm_prices.py --concurrency 40 --offset 0 --limit 6458 &

# Process 2: ISBNs 6458-12915
python scripts/collect_amazon_fbm_prices.py --concurrency 40 --offset 6458 --limit 6458 &

# Process 3: ISBNs 12916-19373
python scripts/collect_amazon_fbm_prices.py --concurrency 40 --offset 12916 --limit 6458 &
```

**Benefits:**
- 4x+ speedup (0.4 ISBN/s → 1.7 ISBN/s with 3 processes)
- SQLite handles concurrent writes automatically (WAL mode)
- Each process works on different ISBNs (no overlap)
- Can monitor each process independently

### 4. Query FBM Data

**Check FBM coverage**:
```sql
SELECT
  COUNT(*) as total_books,
  COUNT(amazon_fbm_collected_at) as with_fbm_data,
  COUNT(amazon_fbm_collected_at) * 100.0 / COUNT(*) as coverage_pct
FROM cached_books;
```

**Books with FBM sellers**:
```sql
SELECT
  isbn, title,
  amazon_fbm_count,
  amazon_fbm_median
FROM cached_books
WHERE amazon_fbm_count > 0
ORDER BY amazon_fbm_median DESC
LIMIT 10;
```

**FBM pricing statistics**:
```sql
SELECT
  COUNT(*) as books_with_fbm,
  AVG(amazon_fbm_count) as avg_sellers_per_book,
  AVG(amazon_fbm_median) as avg_median_price,
  MIN(amazon_fbm_median) as lowest_median,
  MAX(amazon_fbm_median) as highest_median
FROM cached_books
WHERE amazon_fbm_count > 0;
```

## FBM Detection Logic

### What is FBM?

**FBM (Fulfilled by Merchant)** means:
- ❌ NO "Fulfilled by Amazon" badge
- ❌ NO Prime logo
- ✅ Shows merchant name
- ✅ Shows "Ships from..." location
- ✅ Individual shipping costs (not Prime free shipping)

### Filtering Rules

The parser filters Amazon pricing data with these rules:

```python
# Skip if seller is Amazon
is_amazon_seller = 'amazon' in seller_name.lower()

# Skip if FBA fulfillment
is_fba = 'amazon' in fulfillment.lower() or 'fba' in fulfillment

# Include only if: NOT Amazon seller AND NOT FBA
if not is_amazon_seller and not is_fba:
    # This is an FBM seller
    fbm_offers.append(offer)
```

## ML Model Integration

### Current Models

The FBM data is designed for future Amazon FBM specialist model training:

**Proposed Model**: `scripts/stacking/train_amazon_fbm_model.py`

**Features**:
- `amazon_fbm_count`: Competitive density
- `amazon_fbm_median`: Market price point
- `amazon_fbm_min`: Price floor
- `amazon_fbm_max`: Price ceiling
- `amazon_fbm_avg_rating`: Seller quality indicator

**Training Requirements**:
- Minimum 500 books with FBM data
- Minimum 3 FBM sellers per book
- Comparable eBay sold comps for validation

### Feature Engineering

**Derived Features**:
```python
# Price spread (competitiveness indicator)
amazon_fbm_spread = amazon_fbm_max - amazon_fbm_min

# Price per seller (market depth)
amazon_fbm_price_per_seller = amazon_fbm_median / amazon_fbm_count

# FBM vs eBay comparison
fbm_ebay_ratio = amazon_fbm_median / ebay_sold_median
```

## Collection Performance

### Decodo Rate Limits

Decodo handles rate limiting automatically based on your plan:
- Standard: ~10-50 req/s
- Premium: ~100-200 req/s

The script respects Decodo's rate limiting via concurrency settings.

### Estimated Runtime

Assuming 10,000 ISBNs to process:

| Concurrency | Rate (ISBN/s) | Total Time |
|-------------|---------------|------------|
| 10          | ~8            | ~20 min    |
| 50          | ~40           | ~4 min     |
| 100         | ~80           | ~2 min     |

**Note**: Actual rate depends on Decodo plan and server load.

### Costs

- **Decodo API**: $0.001-0.01 per request (plan dependent)
- **10,000 ISBNs**: ~$10-100
- **Amazon pricing target**: Usually included in book pricing plans

## Data Quality

### Expected FBM Coverage

Based on typical Amazon marketplace data:

| Book Category | Expected FBM % |
|--------------|----------------|
| Textbooks    | 60-80%         |
| Popular Fiction | 40-60%      |
| Rare/Collectible | 20-40%    |
| New Releases | 10-30%        |

### Validation Checks

The parser includes quality checks:

1. **Price Validation**: `price > 0`
2. **Seller Validation**: `seller_name not empty`
3. **Condition Parsing**: Falls back to "Used" if missing
4. **Rating Extraction**: Parses percentage ratings (0-100)

## Troubleshooting

### No FBM Sellers Found

**Problem**: Many ISBNs return 0 FBM sellers

**Causes**:
1. Amazon dominates that book category
2. Only FBA sellers available
3. Book is out of print / no marketplace activity

**Solution**: This is expected behavior - not all books have FBM sellers.

### Decodo Authentication Error

**Problem**: `ValueError: DECODO_AUTHENTICATION and DECODO_PASSWORD must be set`

**Solution**: Set environment variables:
```bash
export DECODO_AUTHENTICATION="your_username"
export DECODO_PASSWORD="your_password"
```

### Rate Limiting Errors

**Problem**: Decodo returns rate limit errors

**Solution**: Reduce concurrency:
```bash
python scripts/collect_amazon_fbm_prices.py --concurrency 5
```

## Future Enhancements

1. **Amazon FBM Specialist Model**
   - Train on FBM pricing data
   - Compare to eBay specialist model
   - Integrate into meta-model stacking

2. **Condition-Specific Pricing**
   - Separate FBM prices by condition (Like New, Very Good, Good, Acceptable)
   - Track condition distribution

3. **Seller Rating Features**
   - Average seller rating per book
   - Rating variance (quality consistency)
   - High-rated seller premium

4. **Historical Tracking**
   - Track FBM price changes over time
   - Identify seasonal trends
   - Alert on price drops/spikes

## Related Documentation

- [Platform Specialist Models](./PLATFORM_SPECIALIST_MODELS.md)
- [Data Collection Plan](./EDITION_DATA_COLLECTION_PLAN.md)
- [Lot Specialist Model](./LOT_SPECIALIST_MODEL.md)
