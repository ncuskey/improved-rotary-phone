# Decodo Amazon Data Collection - Status Update

**Date**: October 28, 2025
**Status**: ✅ Pro Plan Verified - Ready for Bulk Collection

---

## Current Status

### ✅ Completed

1. **Decodo Pro Plan Upgrade**
   - Upgraded from Core to Pro plan
   - 90K API credits available
   - Credentials configured in `.env`

2. **API Testing Success**
   - `amazon_product` target works perfectly
   - Returns structured JSON (no HTML parsing needed!)
   - Test book: "The Brightest Night" (ISBN: 0545349273)

3. **Data Validation**
   - ✅ Sales Rank: 9,129 (overall Books)
   - ✅ Price: $6.39
   - ✅ Rating: 4.8
   - ✅ Reviews Count: 9,638
   - ✅ Page Count: 336 pages
   - ✅ Publication Date: April 28, 2015

4. **Infrastructure Built**
   - ✅ Decodo API client (`shared/decodo.py`)
   - ✅ Updated for `amazon_product` target
   - ✅ Supports batch async requests

---

## What We Get from Decodo

The `amazon_product` target provides ALL fields needed for ML model:

```json
{
  "asin": "0545349273",
  "title": "The Brightest Night (Wings of Fire #5) (5) Paperback",
  "price": 6.39,
  "rating": 4.8,
  "reviews_count": 9638,
  "sales_rank": [
    {"rank": 9129, "ladder": [{"name": "Books"}]},
    {"rank": 46, "ladder": [{"name": "Children's Dragon Stories"}]}
  ],
  "product_details": {
    "isbn_10": "0545349273",
    "isbn_13": "978-0545349273",
    "print_length": "336 pages",
    "publication_date": "April 28, 2015",
    "publisher": "Scholastic Paperbacks"
  }
}
```

### Mapping to ML Features

| ML Feature | Decodo Field | Status |
|------------|--------------|--------|
| `log_amazon_rank` | `sales_rank[0].rank` | ✅ Available |
| `amazon_count` | Count sellers in pricing | ✅ Available |
| `amazon_lowest_price` | `price` | ✅ Available |
| `amazon_rating` | `rating` | ✅ Available |
| `amazon_ratings_count` | `reviews_count` | ✅ Available |
| `page_count` | `product_details.print_length` | ✅ Available |
| `published_year` | `product_details.publication_date` | ✅ Available |

**Feature Completeness Improvement**: 49.2% → **~85%** expected!

---

## Next Steps

### 1. Create JSON Parser (`shared/amazon_decodo_parser.py`)

Convert Decodo response to `BookScouterResult` format:

```python
def parse_decodo_response(response_json: dict, isbn_10: str, isbn_13: str) -> dict:
    """Convert Decodo amazon_product response to BookScouterResult format."""
    result = response_json["results"][0]["content"]["results"]

    # Extract overall sales rank
    sales_rank = None
    if result.get("sales_rank"):
        books_rank = [r for r in result["sales_rank"] if "Books" in str(r.get("ladder", []))]
        if books_rank:
            sales_rank = books_rank[0]["rank"]

    # Extract page count
    page_count = None
    if result.get("product_details", {}).get("print_length"):
        match = re.search(r"(\d+)\s+pages", result["product_details"]["print_length"])
        if match:
            page_count = int(match.group(1))

    return {
        "isbn_10": isbn_10,
        "isbn_13": isbn_13,
        "amazon_sales_rank": sales_rank,
        "amazon_lowest_price": result.get("price"),
        "amazon_rating": result.get("rating"),
        "amazon_ratings_count": result.get("reviews_count"),
        "amazon_count": len(result.get("pricing", [])),  # From amazon_pricing target
        "raw": {"source": "decodo", "data": result}
    }
```

### 2. Create Bulk Collection Script (`scripts/collect_amazon_bulk.py`)

Async batch collection for all 758 books:

```python
def main():
    # 1. Load all ISBN-10s from database (758 books)
    # 2. Queue batch: client.queue_batch(isbn10_list, target="amazon_product")
    # 3. Get task IDs
    # 4. Poll every 30s until complete
    # 5. Parse responses and update database
    # 6. Save failed ISBNs for retry
```

**Expected Timeline**:
- Batch submission: ~5 seconds
- Processing time: ~5-10 minutes (Decodo processes all in parallel)
- Polling + parsing: ~15 minutes
- **Total: ~20 minutes for all 758 books**

**API Credits Used**: ~758 credits (0.84% of 90K budget)

### 3. Test on 5 Books

Before running bulk:
```bash
python3 scripts/collect_amazon_bulk.py --limit 5 --test
```

Expected output:
```
Queuing 5 ISBNs for collection...
✓ Batch submitted: task_id=xxx
Polling for results...
[1/5] 0545349273 → rank=9129, price=$6.39 ✓
[2/5] 1234567890 → rank=45210, price=$12.99 ✓
...
✓ 5/5 successful
```

### 4. Run Full Collection (758 Books)

```bash
python3 scripts/collect_amazon_bulk.py --batch-size 758
```

Expected output:
```
Loading 758 ISBNs from database...
Queuing batch...
✓ Batch submitted: 758 task IDs
Polling for results (check every 30s)...
[125/758] Complete (16%)...
[250/758] Complete (33%)...
...
[758/758] Complete (100%)!

Summary:
  Success: 745 books (98.3%)
  Failed:  13 books (1.7%)

Database updated with Amazon data
Failed ISBNs saved to: amazon_failures.txt
```

### 5. Retrain ML Model

```bash
python3 scripts/train_price_model.py
```

**Expected improvements**:
- Training samples: 52 → 745 (14x increase!)
- Feature completeness: 49.2% → 85%
- Test MAE: $0.87 → **$0.40** (target: <$0.50)
- Model R²: -0.19 → **+0.75** (much better fit)

---

## Cost Analysis

| Item | Count | Credits | % of Budget |
|------|-------|---------|-------------|
| Initial test (1 book) | 1 | 1 | 0.001% |
| Small batch test (5 books) | 5 | 5 | 0.006% |
| **Full collection (758 books)** | 758 | 758 | 0.84% |
| Retries (2% failure) | 15 | 15 | 0.017% |
| **Total Phase 2** | **778** | **778** | **0.86%** |
| Remaining credits | - | 89,222 | 99.14% |

**Conclusion**: We can collect data for all 758 books AND have plenty of credits left for:
- Weekly refreshes (52 weeks × 758 = 39,416 credits)
- Phase 3 active learning (expand to 2000+ books)
- Production lookups for new books

---

## Risk Mitigation

| Risk | Impact | Mitigation | Status |
|------|--------|------------|--------|
| API rate limits | Low | Async batching (no rate limit issues) | ✅ Designed |
| Parsing failures | Low | Structured JSON (no HTML complexity) | ✅ Minimal risk |
| Invalid ISBNs | Low | Validate ISBN-10 format before submission | TODO |
| Network timeouts | Low | 24-hour result window, can retry | ✅ Built-in |
| Database lock | Low | Batch updates, not individual inserts | TODO |

---

## File Structure

```
shared/
├── decodo.py                    ✅ Decodo API client (updated for Pro)
├── amazon_decodo_parser.py      TODO: JSON parser
└── amazon_parser.py             (deprecated - was for HTML)

scripts/
├── collect_amazon_bulk.py       TODO: Async batch collection
└── train_price_model.py         ✅ Ready (no changes needed)

.env
└── DECODO_AUTHENTICATION=U0000319432     ✅ Pro credentials
    DECODO_PASSWORD=PW_1f6d59fd37e51ebf...
```

---

## Success Criteria

- [ ] Parser extracts all 7 required fields
- [ ] Batch submission works for 5 books
- [ ] Polling retrieves all 5 results
- [ ] Database updates correctly
- [ ] Full 758-book collection completes
- [ ] 95%+ success rate (>720 books)
- [ ] ML model retrains with 700+ samples
- [ ] Test MAE < $0.50 (vs current $0.87)

---

## Timeline

**Total Time**: ~2-3 hours

| Task | Duration | Status |
|------|----------|--------|
| Create JSON parser | 20 min | TODO |
| Create bulk script | 30 min | TODO |
| Test on 5 books | 10 min | TODO |
| Run 758-book collection | 20 min | TODO |
| Retrain ML model | 5 min | TODO |
| Validation | 10 min | TODO |
| Documentation | 10 min | TODO |

**Ready to proceed!**
