# Signed Book Data Collection Scripts

This directory contains scripts for capturing and syncing signed book data to improve ML model predictions.

**Latest Update (2025-11-19):** Added award winners import system and famous authors database expansion (11 → 36 authors)

## Quick Start

```bash
# 1. One-time setup: Authorize eBay access via token broker
# Visit: http://localhost:8787/oauth/authorize?scopes=sell.fulfillment,sell.inventory
# (Token broker must be running on port 8787)

# 2. Collect your eBay sales history (high-quality signed comp data)
python3 scripts/collect_my_ebay_sales.py --days 90

# 3. Run the complete enrichment + signed sync workflow
./scripts/enrich_and_sync_workflow.sh

# 4. Retrain models with new signed book data
python3 scripts/stacking/train_ebay_model.py
```

**Alternative:** If token broker isn't running, use standalone OAuth:
```bash
python3 scripts/setup_ebay_user_token.py
python3 scripts/collect_my_ebay_sales.py --use-env-token --days 90
```

## Scripts

### `setup_ebay_user_token.py` (OPTIONAL)
**Purpose:** Standalone OAuth setup if not using token broker

**When to use:** If you want to store the refresh token in `.env` instead of using the token broker's in-memory storage.

**Usage:**
```bash
python3 scripts/setup_ebay_user_token.py
```

**What it does:**
1. Opens eBay authorization page in your browser
2. You log in and authorize the app
3. Script exchanges authorization code for refresh token
4. Saves `EBAY_USER_REFRESH_TOKEN` to `.env` file

**Note:** Most users should use the token broker instead (see Quick Start above). This is only needed if you prefer persistent `.env` storage or if the token broker isn't running.

---

### `collect_my_ebay_sales.py` (NEW)
**Purpose:** Collect your eBay sales history as high-quality signed comp data

**Why This Matters:** Your actual signed book sales provide the most reliable training data. The model learns from real market transactions, not just scraped listings.

**Usage:**
```bash
# Using token broker (default - requires broker running on port 8787)
python3 scripts/collect_my_ebay_sales.py

# Using .env refresh token (if you ran setup_ebay_user_token.py)
python3 scripts/collect_my_ebay_sales.py --use-env-token

# Collect last 180 days
python3 scripts/collect_my_ebay_sales.py --days 180

# Dry run (see what would be collected)
python3 scripts/collect_my_ebay_sales.py --dry-run

# Custom broker URL
python3 scripts/collect_my_ebay_sales.py --broker-url http://localhost:8787
```

**What it does:**
1. Uses refresh token to get eBay API access
2. Fetches your completed orders via Sell Fulfillment API
3. Extracts ISBNs from titles and SKUs
4. Detects signed books using `shared/feature_detector.is_signed()`
5. Saves to `sold_listings` table with `source='user_sales'`
6. Reports statistics on signed books found

**Output Example:**
```
================================================================================
EBAY SALES COLLECTION
================================================================================

Fetching orders from the past 90 days...
Filter date: 2024-08-10T12:00:00.000Z

  Fetched 50 orders (total: 50)
  Fetched 45 orders (total: 95)

✓ Retrieved 95 total orders

Parsing orders into sales records...
✓ Parsed 87 sales with ISBNs
✓ Found 23 signed book sales (26.4%)

================================================================================
SAVING SALES TO DATABASE
================================================================================

Sales to save:
  Total:    87
  Signed:   23 (26.4%)
  Unsigned: 64

✓ Inserted 87 new sales

Next steps:
  1. Run: python3 scripts/sync_signed_status_to_training.py
  2. Retrain: python3 scripts/stacking/train_ebay_model.py
```

---

### `sync_signed_status_to_training.py`
**Purpose:** Aggregate signed book information from multiple sources and update training database

**Data Sources:**
- BookFinder offers (`is_signed = 1`)
- eBay sold listings (`signed = 1`)
- eBay active listings (parsed from titles)

**Usage:**
```bash
# Dry run (see what would be updated)
python3 scripts/sync_signed_status_to_training.py --dry-run

# Actually sync
python3 scripts/sync_signed_status_to_training.py

# Specify database path
python3 scripts/sync_signed_status_to_training.py --db data/custom.db
```

**Output Example:**
```
================================================================================
SYNCING SIGNED BOOK STATUS TO TRAINING DATA
================================================================================

Training database: 2736 total books in cached_books
Current signed books: 5 (0.18%)

Collecting signed ISBNs from data sources...
  ✓ BookFinder: 125 signed ISBNs
  ✓ Sold listings: 47 signed ISBNs
  ✓ Active listings: 23 signed ISBNs (parsed from titles)

Total unique signed ISBNs found: 142
ISBNs to update (currently signed=0): 137

Updating signed=1 for 137 ISBNs...
✓ Updated 137 records

New signed book count: 142 (5.19%)
Improvement: +137 signed books
```

---

### `import_award_winners.py` (NEW: 2025-11-19)
**Purpose:** Import literary award winners from CSV into famous_people.json with tier-based signed book multipliers

**Award Tiers:**
- **Tier 1 (Major Awards)**: National Book Award (12x), Booker Prize (15x), International Booker (12x), Women's Prize (10x), NBCC (10x)
- **Tier 2 (Genre Awards)**: Hugo Award (8x), Nebula Award (8x)
- **Tier 3 (Children's Awards)**: Newbery Medal (6x), Caldecott Medal (6x)

**CSV Format:**
```csv
Award,Author,Work,Year
National Book Award (Fiction),Percival Everett,James,2024
Booker Prize,Samantha Harvey,Orbital,2024
Hugo Award (Best Novel),Emily Tesh,Some Desperate Glory,2024
```

**Usage:**
```bash
# Import with preview and confirmation
python3 scripts/import_award_winners.py /path/to/award_winners.csv

# Auto-confirm mode (skip confirmation prompt)
python3 scripts/import_award_winners.py /path/to/award_winners.csv --yes
```

**Output Example:**
```
=== IMPORT SUMMARY ===
CSV authors: 28 total
New authors to add: 25
Skipped (already exists): 2

NEW AUTHORS TO ADD:

1. Percival Everett
   Multiplier: 12x
   Award: National Book Award (Fiction) (2024)
   Genres: literary fiction

2. Samantha Harvey
   Multiplier: 15x
   Award: Booker Prize (2024)
   Genres: literary fiction

... and 23 more

Add 25 new authors to famous_people.json? (yes/no): yes

✓ Successfully added 25 authors
✓ Total in database: 36
```

**Features:**
- Author name normalization ("Last, First" → "First Last")
- Automatic genre detection based on award type
- Skips translators and illustrators
- Deduplication against existing database entries
- Preview mode before making changes

**Impact:**
- Database expanded from 11 → 36 authors (227% increase)
- Signed books from award winners now receive appropriate premiums
- Covers major literary awards through 2024

---

### `check_vialibri.py` (NEW: 2025-11-19)
**Purpose:** Check viaLibri marketplace for pricing data on collectible/specialized books

**Use Case:** Manual validation of ML predictions for collectible books with limited eBay/Amazon data

**Requirements:**
- Decodo Advanced plan account (JavaScript rendering)
- `DECODO_AUTH_TOKEN` environment variable (base64-encoded credentials)

**Usage:**
```bash
# Check a single ISBN on viaLibri
python3 scripts/check_vialibri.py 9780805059199
```

**Output Example:**
```
=== VIALIBRI CHECK FOR ISBN 9780805059199 ===
Cost: 1 Decodo Advanced credit

Fetching...

✓ Found 12 listings (12 price points)

PRICE STATISTICS:
  Lowest:  $15.00
  Median:  $45.00
  Mean:    $52.30
  Highest: $125.00

Special editions: 3 signed, 5 first edition

SAMPLE LISTINGS:
1. Brian Herne - White Hunters: The Golden Age of African Safaris
   Seller: Rare Book Cellar (United States)
   First edition, signed by author. Fine condition in dust jacket.
   → AbeBooks: $125.00
   → ZVAB: $125.00

...
```

**Integration:**
- Used during manual comparison validations
- Provides third-party pricing when eBay/Amazon lack data
- Validates signed book premiums for famous authors
- Strategic usage (1 credit per ISBN check)

**Cost Management:**
- ~4,500 Decodo Advanced credits available
- Use for collectibles/signed books only
- Not for bulk collection

---

### `enrich_and_sync_workflow.sh`
**Purpose:** Complete enrichment workflow including signed book sync

**Usage:**
```bash
# Full workflow
./scripts/enrich_and_sync_workflow.sh

# Skip enrichment, only sync signed books
./scripts/enrich_and_sync_workflow.sh --skip-enrichment

# Skip signed sync, only enrichment
./scripts/enrich_and_sync_workflow.sh --skip-sync

# Help
./scripts/enrich_and_sync_workflow.sh --help
```

**Workflow Steps:**
1. Run market data enrichment (`enrich_metadata_cache_market_data.py`)
2. Sync signed book status (`sync_signed_status_to_training.py`)
3. Display next steps (model training, validation)

## Integration

### Complete Data Pipeline

```bash
# 1. One-time OAuth setup (if not done yet)
python3 scripts/setup_ebay_user_token.py

# 2. Collect data from various sources
python3 scripts/collect_bookfinder_prices.py
python3 scripts/collect_sold_listings.py
python3 scripts/collect_my_ebay_sales.py --days 90  # NEW: Your sales history

# 3. Enhanced enrichment with signed sync
./scripts/enrich_and_sync_workflow.sh

# 4. Train models with improved signed book data
python3 scripts/stacking/train_ebay_model.py
python3 scripts/stacking/train_amazon_model.py
```

### With Cron/Scheduled Jobs

```bash
# Run weekly: collect sales + enrichment + sync
0 2 * * 0 cd /path/to/ISBN && python3 scripts/collect_my_ebay_sales.py --days 7 && ./scripts/enrich_and_sync_workflow.sh >> /var/log/enrich.log 2>&1
```

### With Python

```python
from sync_signed_status_to_training import sync_signed_status

# Sync signed status
sync_signed_status('data/isbn_lot_optimizer.db', dry_run=False)

# Then retrain models...
```

## Expected Results

### Before Sync
- Signed training samples: **5 (0.18%)**
- Model signed premium: **$0**
- Example: Signed Tom Clancy 1st ed → **$3**

### After Sync + Retrain
- Signed training samples: **140+ (5%+)**
- Model signed premium: **$20-100+**
- Example: Signed Tom Clancy 1st ed → **$60-120**

## Validation

After running sync and retraining models, validate predictions:

```bash
# Test unsigned book
curl -X POST http://localhost:8111/api/books/9780399134401/estimate_price \
  -H 'Content-Type: application/json' \
  -d '{"condition": "very_good", "is_hardcover": true, "is_signed": false}'

# Test signed book (should show higher price)
curl -X POST http://localhost:8111/api/books/9780399134401/estimate_price \
  -H 'Content-Type: application/json' \
  -d '{"condition": "very_good", "is_hardcover": true, "is_signed": true}'
```

Check the `deltas` array in the response for `is_signed` attribute delta.

## Troubleshooting

### "cached_books table not found"
Run enrichment first:
```bash
python3 scripts/enrich_metadata_cache_market_data.py
```

### "No signed ISBNs found"
Collect data sources:
```bash
# First, set up eBay OAuth (one-time)
python3 scripts/setup_ebay_user_token.py

# Then collect from all sources
python3 scripts/collect_my_ebay_sales.py --days 90
python3 scripts/collect_bookfinder_prices.py
python3 scripts/collect_sold_listings.py
```

### Model still shows $0 delta
Retrain models after sync:
```bash
python3 scripts/stacking/train_ebay_model.py
```

## Documentation

- **Quick Start:** `docs/SIGNED_BOOK_QUICKSTART.md`
- **Complete Guide:** `docs/SIGNED_BOOK_DATA_COLLECTION.md`
- **Unified Model:** `docs/UNIFIED_CROSS_PLATFORM_MODEL.md`

## Feature Detection

Signed books are detected using patterns in `shared/feature_detector.py`:

- Basic: "signed", "autographed", "inscribed"
- Qualified: "hand signed", "author signed"
- Abbreviations: "s/a", "sgnd"
- Bookplates: "signed bookplate", "autographed bookplate"

## Status

✅ **Production Ready**
- Scripts tested and documented
- Error handling implemented
- Integration guides provided
- Ready to use when database is populated

---

**Last Updated:** November 9, 2025
**Maintainer:** ML Pipeline Team
