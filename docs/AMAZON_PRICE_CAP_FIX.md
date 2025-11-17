# Amazon Price Cap Fix for Books Without eBay Data

## Problem

Books without eBay market data (0 sold, 0 active) were being overvalued by heuristic-based pricing, particularly the page count heuristic which adds up to $6 for books with 300+ pages.

### Example: The Quiet Game by Greg Iles
- **Pages**: 433
- **Amazon Lowest**: $6.71
- **Heuristic Calculation**: $4 base + $6 pages = **$10.00**
- **User Valuation**: $7.00
- **Problem**: System overvalued by $3 (43% error)

The page count heuristic (`$0.02/page, max $6`) was dominating when no eBay data existed, causing predictions to ignore available market signals from Amazon.

## Solution

Modified `/Users/nickcuskey/ISBN/shared/probability.py:254-269` to use Amazon price as a **ceiling** (not just a floor) when eBay data is unavailable.

### Logic Change

**Before**:
```python
if bookscouter and bookscouter.amazon_lowest_price:
    amazon_estimate = bookscouter.amazon_lowest_price * 0.7 * condition_weight
    base = max(base, amazon_estimate)  # Amazon as floor only
```

**After**:
```python
if bookscouter and bookscouter.amazon_lowest_price:
    amazon_estimate = bookscouter.amazon_lowest_price * 0.7 * condition_weight

    # When eBay data is unavailable, use Amazon as primary signal
    if not market or (market.sold_count == 0 and market.active_count == 0):
        # No eBay data - weight Amazon heavily and cap heuristics
        base = min(base, amazon_estimate * 1.5)
    else:
        # eBay data exists - use Amazon as floor only
        base = max(base, amazon_estimate)
```

### Key Points

1. **Amazon as Ceiling**: When no eBay data exists, cap heuristics at `1.5 × Amazon estimate`
2. **Preserves eBay Priority**: When eBay data exists, Amazon still acts as floor (no change)
3. **Conservative Markup**: 1.5× multiplier allows heuristics to add value but prevents wild overvaluation

## Results

### The Quiet Game Test Case
- **Before**: $10.00 (heuristic dominated)
- **After**: $6.69 (Amazon-capped)
- **User Valuation**: $7.00
- **Error**: $0.31 (4.4% - much improved from 43%)

### Impact

- ✅ Better alignment with market reality for low-information books
- ✅ Prevents page count heuristic from dominating
- ✅ Maintains heuristic value-add (up to 50% above Amazon)
- ✅ No impact on books with eBay data (most accurate predictions unchanged)

## When This Applies

This fix only affects books where:
- No eBay sold comps (`market.sold_count == 0`)
- No eBay active listings (`market.active_count == 0`)
- Amazon price data is available

For these books, the algorithm now respects Amazon as the primary market signal rather than relying solely on metadata heuristics.

## Commit

```
commit d492b53
Date: 2025-11-16

fix(pricing): Cap heuristics at 1.5x Amazon price for books without eBay data
```

## Related Files

- `/Users/nickcuskey/ISBN/shared/probability.py` - Main fix location
- `/Users/nickcuskey/ISBN/scripts/compare_valuation.py` - Tool used to identify issue
