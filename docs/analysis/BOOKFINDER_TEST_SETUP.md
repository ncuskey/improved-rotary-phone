# BookFinder.com Scraping Test

**Created:** November 1, 2025
**Status:** Ready to Test
**Purpose:** Validate scraping ability on BookFinder.com using Decodo Core

---

## Overview

This test validates our ability to scrape **BookFinder.com** (a meta-search aggregator that queries 20+ bookstores) using Decodo Core plan.

### Why BookFinder?

- **Efficiency:** One scrape = 15-30 vendor prices (vs 1 price per direct scraper)
- **Coverage:** 760 ISBNs × 15 vendors = **11,400 price points**
- **Cost:** Only 760 credits (~0.8% of 90K budget)
- **Value:** Floor price detection, cross-vendor validation, market consensus

---

## Test Script

### Location
```
scripts/test_bookfinder_scraper.py
```

### What It Does

1. **Scrapes 5 ISBNs** from BookFinder.com using Decodo Core
2. **Extracts offer data** from React/Next.js embedded JSON
3. **Validates data quality** (vendor, price, condition, binding)
4. **Saves results** to SQLite database (`/tmp/bookfinder_test.db`)
5. **Reports feasibility** for full-scale scraping

### Data Extraction Approach

BookFinder uses **React/Next.js** with data embedded as JSON in `<script>` tags:

```javascript
// Embedded in HTML
{
  "searchResults": {
    "allOffers": [
      {
        "affiliate": "ABEBOOKS",
        "price": 8.50,
        "condition": "Used - Good",
        "binding": "Hardcover",
        "seller": "Example Bookstore",
        // ... more fields
      }
    ]
  }
}
```

**Primary Method:** Extract JSON from script tags using regex
**Fallback Method:** Parse rendered HTML (less reliable)

---

## How to Run

### Prerequisites

1. **Decodo credentials** must be set in environment:
   ```bash
   export DECODO_AUTHENTICATION="U0000319432"
   export DECODO_PASSWORD="PW_1f6d59fd37e51ebfaf4f26739d59a7adc"
   ```

2. **Dependencies** (already installed):
   - beautifulsoup4
   - requests
   - sqlite3 (built-in)

### Run the Test

```bash
cd /Users/nickcuskey/ISBN
python3 scripts/test_bookfinder_scraper.py
```

### Expected Runtime

- **5 ISBNs** × 3 seconds = ~15 seconds
- Plus processing time (~5 seconds)
- **Total:** ~20 seconds

---

## Test ISBNs

The script tests with:

1. **3 ISBNs from your catalog** (if available)
2. **Classic titles** for validation:
   - 9780061120084 - To Kill a Mockingbird
   - 9780451524935 - 1984
   - 9780316769174 - The Catcher in the Rye
   - 9780062315007 - The Alchemist
   - 9780143127550 - Fahrenheit 451

---

## Expected Output

### Success Case

```
================================================================================
BOOKFINDER.COM SCRAPING TEST (Decodo Core)
================================================================================

🔧 Initializing Decodo client (Core plan)...
📚 Found 3 ISBNs from catalog
🎯 Testing with 5 ISBNs:
   - 9780134685991
   - 9780135957059
   - 9780137081073
   - 9780061120084
   - 9780451524935

================================================================================
Test 1/5
================================================================================

📖 Scraping ISBN: 9780134685991
   URL: https://www.bookfinder.com/search/?isbn=9780134685991
   ✅ Fetched HTML (234,567 bytes)
   ✅ Extracted 23 offers from JSON

   📊 Offer Summary:
   Vendor          Price    Condition            Binding
   ------------------------------------------------------------
   ABEBOOKS        $8.50    Used - Good          Hardcover
   EBAY            $12.99   Used - Very Good     Hardcover
   BIBLIO          $9.25    Used - Like New      Hardcover
   BOOKS_RUN       $7.00    Used - Acceptable    Paperback
   ... and 19 more offers

   💰 Price Range: $7.00 - $24.99
   💰 Average Price: $11.42

================================================================================
TEST RESULTS SUMMARY
================================================================================

📊 Overall Statistics:
   Total ISBNs tested: 5
   ✅ Successful: 5 (100.0%)
   ❌ Failed: 0 (0.0%)
   📦 Total offers extracted: 118
   📈 Average offers per ISBN: 23.6

================================================================================
FEASIBILITY ASSESSMENT
================================================================================

✅ FEASIBLE - BookFinder scraping works with Decodo Core!

   Next Steps:
   1. Review HTML debug files in /tmp/ if any extraction failed
   2. Adjust JSON extraction patterns if needed
   3. Build full scraper for 760 catalog ISBNs
   4. Integrate 3 ML features (lowest_price, source_count, new_vs_used_spread)

   💰 Cost Estimate:
   - Catalog ISBNs: 760
   - Credits per ISBN: ~1
   - Total credits: ~760 (0.8% of 90K budget)
   - Runtime: ~38 minutes (760 × 3 seconds)
```

### Failure Case

If extraction fails for an ISBN:

```
📖 Scraping ISBN: 9780451524935
   URL: https://www.bookfinder.com/search/?isbn=9780451524935
   ✅ Fetched HTML (198,432 bytes)
   ⚠️  JSON extraction failed, trying HTML fallback...
   ❌ No offers found
   💾 Saved HTML to /tmp/bookfinder_debug_9780451524935.html for debugging
```

**Action:** Inspect the HTML file to understand the page structure and adjust extraction patterns.

---

## Success Criteria

**Test is successful if:**
- ✅ At least 3 out of 5 ISBNs scraped successfully
- ✅ Each successful ISBN returns 10+ offers
- ✅ Offers contain expected fields (vendor, price, condition, binding)

**If successful:**
- Proceed to build full scraper for 760 catalog ISBNs
- Integrate 3 ML features into model

**If failed:**
- Investigate HTML debug files
- Adjust JSON extraction patterns
- Consider alternative aggregators (DealOz, BigWords)

---

## Test Database

### Location
```
/tmp/bookfinder_test.db
```

### Schema
```sql
CREATE TABLE bookfinder_test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    isbn TEXT NOT NULL,
    vendor TEXT,           -- ABEBOOKS, EBAY, BIBLIO, etc.
    seller TEXT,           -- Individual seller name
    price REAL,            -- USD price
    condition TEXT,        -- Used - Good, Used - Very Good, New, etc.
    binding TEXT,          -- Hardcover, Paperback, etc.
    shipping REAL,         -- Shipping cost
    url TEXT,              -- Clickout URL to vendor
    location TEXT,         -- Seller location
    scraped_at TIMESTAMP   -- When scraped
);
```

### Query Results
```bash
# View all results
sqlite3 /tmp/bookfinder_test.db 'SELECT * FROM bookfinder_test_results;'

# Count offers per ISBN
sqlite3 /tmp/bookfinder_test.db '
SELECT isbn, COUNT(*) as offer_count
FROM bookfinder_test_results
GROUP BY isbn
ORDER BY offer_count DESC;
'

# Price range per ISBN
sqlite3 /tmp/bookfinder_test.db '
SELECT isbn,
       MIN(price) as min_price,
       MAX(price) as max_price,
       AVG(price) as avg_price,
       COUNT(*) as vendors
FROM bookfinder_test_results
GROUP BY isbn;
'

# Vendor distribution
sqlite3 /tmp/bookfinder_test.db '
SELECT vendor, COUNT(*) as offers
FROM bookfinder_test_results
GROUP BY vendor
ORDER BY offers DESC;
'
```

---

## Technical Details

### BookFinder URL Format
```
https://www.bookfinder.com/search/?isbn={ISBN}&mode=basic&st=sr&ac=qr
```

**Required parameter:** `isbn` only

### Decodo Core Limitations

- **No structured parsing:** Must parse HTML yourself
- **JavaScript rendering:** Handled by Decodo (embedded in HTML response)
- **Rate limit:** 30 req/s (more than sufficient)

### Robots.txt Consideration

⚠️ **Important:** BookFinder's `/robots.txt` **DISALLOWS** crawling of `/search/` path.

```
Disallow: /search/
Disallow: /isbn/
Disallow: /book/
```

**Implications:**
- This scraping activity violates robots.txt policy
- Risk of IP blocking if detected
- Consider ethical/legal implications

**Mitigation:**
- Use conservative delays (2-3 seconds between requests)
- Limit to small batches (760 ISBNs = acceptable)
- Consider BookFinder's affiliate program (may have API access)

---

## Next Steps After Test

### If Test Succeeds (3+ ISBNs)

1. **Build full scraper** (`scripts/collect_bookfinder_prices.py`)
   - Scale from 5 → 760 ISBNs
   - Add database integration (catalog.db or new table)
   - Implement error handling & retry logic

2. **Integrate ML features** (Phase 3 of roadmap)
   - `bookfinder_lowest_price` - Absolute floor across all vendors
   - `bookfinder_source_count` - Number of vendors offering the book
   - `bookfinder_new_vs_used_spread` - Price gap between new and used

3. **Retrain model** with expanded features
   - Add 3 new features to feature_extractor.py
   - Retrain at Batch 150 milestone
   - Compare performance vs unified model

### If Test Fails (<3 ISBNs)

1. **Debug HTML files** in `/tmp/bookfinder_debug_*.html`
   - Inspect actual page structure
   - Identify where JSON is embedded
   - Adjust regex patterns

2. **Consider alternatives:**
   - **DealOz.com** - Similar aggregator, simpler HTML
   - **BigWords.com** - Textbook focus, static content
   - **Direct scrapers** - AbeBooks, Alibris (1:1 instead of 1:many)

---

## Cost-Benefit Analysis

### Costs
- **Decodo credits:** 760 (0.8% of 90K budget)
- **Development time:** 4-6 hours (test + full scraper + integration)
- **Runtime:** 38 minutes (one-time collection)
- **Ethical risk:** Robots.txt violation

### Benefits
- **15x data expansion:** 760 → 11,400 price points
- **Cross-vendor validation:** Detect AbeBooks outliers
- **Market floor:** Absolute lowest price across all sources
- **3 new ML features:** Floor price, vendor count, new/used spread
- **Expected MAE improvement:** 5-10% (estimated)

### ROI Score: ⭐⭐⭐ (3/5)

**Recommendation:** Proceed if test succeeds, but prioritize AbeBooks (higher ROI) first.

---

## Troubleshooting

### Issue: "DECODO_AUTHENTICATION not set"
**Solution:**
```bash
export DECODO_AUTHENTICATION="U0000319432"
export DECODO_PASSWORD="PW_1f6d59fd37e51ebfaf4f26739d59a7adc"
```

### Issue: "No offers found"
**Cause:** JSON extraction pattern doesn't match BookFinder's structure
**Solution:** Inspect `/tmp/bookfinder_debug_*.html` and adjust regex in `parse_bookfinder_json()`

### Issue: "Rate limit exceeded"
**Cause:** Too many requests too quickly
**Solution:** Decodo handles rate limiting automatically, but add manual delays if needed

### Issue: Empty HTML response
**Cause:** Decodo Core may not render JavaScript properly
**Solution:**
1. Check Decodo Core plan supports JS rendering
2. Consider upgrading to Advanced plan (unlikely needed)
3. Try alternative aggregators

---

## References

- **Data Expansion Roadmap:** `DATA_EXPANSION_ROADMAP.md` (Phase 3)
- **Decodo Client:** `shared/decodo.py`
- **BookFinder.com:** https://www.bookfinder.com
- **Robots.txt:** https://www.bookfinder.com/robots.txt

---

**Created by:** Claude Code
**Test Date:** November 1, 2025
**Status:** Ready to run
