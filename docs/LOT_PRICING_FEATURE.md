# eBay Lot Comp Pricing Feature

## Overview

This feature searches eBay for book lot listings and analyzes per-book pricing across different lot sizes to help determine optimal lot configurations.

## How It Works

### 1. Search for Lot Listings
```python
from isbn_lot_optimizer.market import get_lot_pricing_for_series

result = get_lot_pricing_for_series('Alex Cross', 'James Patterson')
```

### 2. Parse Lot Sizes
The system intelligently extracts lot sizes from eBay listing titles using regex patterns:
- "Lot of 7" → 7 books
- "Lot 7" → 7 books
- "Lot 1st 12" → 12 books (handles ordinals)
- "Lot First 12" → 12 books
- "7 Book Lot" → 7 books
- "Set of 7 Books" → 7 books
- "Complete Set 7" → 7 books
- "#7" → 7 books (if reasonable)

**Enhanced Ordinal Support (v2):**
The parser now handles ordinal numbers before lot sizes, essential for series-based lot listings:
- Pattern: `(?:lot|set)\s+(?:1st|first|2nd|3rd|4th|...|Nth)\s+(\d+)`
- Example: "James Patterson Lot 1st 12 Alex Cross Novels" correctly extracts 12

### 3. Calculate Per-Book Pricing
For each listing:
- Total Price ÷ Lot Size = Per-Book Price
- Example: $28 for "Alex Cross Lot 7" = $4.00/book

### 4. Analyze by Lot Size
Groups listings by size and calculates averages:
```
3 books: $6.50/book (n=5 listings)
5 books: $5.20/book (n=12 listings)
7 books: $4.80/book (n=18 listings) ← OPTIMAL
```

### 5. Identify Optimal Size
The system recommends the lot size with the highest per-book price, indicating best market demand.

## API Functions

### `search_ebay_lot_comps(search_term, limit=50)`
Core function that searches eBay and parses results.

**Parameters:**
- `search_term`: Search query (e.g., "Alex Cross Lot")
- `limit`: Maximum results to fetch (default: 50)

**Returns:** `LotPricingResult` dict with:
- `search_term`: Query used
- `total_comps`: Number of lot listings found
- `lot_sizes`: Dict mapping size → list of per-book prices
- `comps`: List of individual `LotComp` objects
- `optimal_lot_size`: Best size (highest per-book price)
- `optimal_per_book_price`: Price at optimal size
- `avg_per_book_by_size`: Dict mapping size → average price

### `parse_lot_size_from_title(title)`
Extracts lot size from eBay listing title.

**Returns:** Integer lot size or None

### `get_lot_pricing_for_series(series_name, author_name=None)`
Convenience function for series pricing.

**Example:**
```python
result = get_lot_pricing_for_series('Wheel of Time', 'Robert Jordan')
```

## Data Models

### LotComp
Single lot listing:
```python
{
    "title": str,
    "price": float,
    "lot_size": int,
    "per_book_price": float,
    "currency": str,
    "item_id": str
}
```

### LotPricingResult
Aggregated analysis:
```python
{
    "search_term": str,
    "total_comps": int,
    "lot_sizes": Dict[int, List[float]],
    "comps": List[LotComp],
    "optimal_lot_size": Optional[int],
    "optimal_per_book_price": Optional[float],
    "avg_per_book_by_size": Dict[int, float]
}
```

## Integration with Lot Suggestions

### Implementation Status: ✅ COMPLETE

**Pricing Strategy:**
The system now **always prefers lot comp pricing** when available, treating it as a more direct comparable than individual book sales. This is because lot-to-lot comparisons better reflect actual market behavior.

**Backend Logic (`lots.py`):**
1. **Get series/author from lot**
2. **Call `get_lot_pricing_for_series()`** or search for author lots
3. **Use `optimal_lot_size` and `optimal_per_book_price`**
4. **Calculate lot value:**
   ```python
   lot_value = optimal_per_book_price * number_of_books
   ```
5. **Always prefer lot comp pricing** when available (set `use_lot_pricing = True`)
6. **Store individual pricing** as `individual_value` for comparison
7. **Update justification** to show both pricing methods

### Actual Implementation (lots.py:240-322)

```python
# In _suggest_lot() function
individual_value = _sum_price(books)  # Sum individual book prices

# Initialize lot pricing fields
lot_market_value = None
individual_value_for_comparison = individual_value
use_lot_pricing = False

# Fetch lot market pricing for series and author lots
if strategy in ("series", "author") and len(books) >= 2:
    lot_pricing = get_lot_pricing_for_series(search_series, search_author)

    if lot_pricing and lot_pricing.get("total_comps", 0) > 0:
        lot_per_book_price = lot_pricing.get("optimal_per_book_price")

        if lot_per_book_price:
            # Calculate market value for our lot size
            lot_market_value = round(lot_per_book_price * len(books), 2)

            # Always prefer lot comp pricing as more direct comparable
            use_lot_pricing = True
            final_value = lot_market_value

            # Show comparison to individual pricing
            if lot_market_value > individual_value:
                justification.insert(1, f"+${diff:.2f} vs individual pricing")
            else:
                justification.insert(1, f"Individual pricing higher: ${individual_value:.2f}")

# Return LotSuggestion with lot pricing data
return LotSuggestion(
    estimated_value=final_value,  # Uses lot_market_value when available
    individual_value=individual_value,  # Stored for comparison
    lot_market_value=lot_market_value,
    use_lot_pricing=use_lot_pricing
)
```

## CLI Testing

```bash
python -m isbn_lot_optimizer.market "Alex Cross" "James Patterson"
```

## Implementation Status

### ✅ Completed Features

1. **Backend Integration (`lots.py`):**
   - ✅ Lot pricing fetching for series and author lots
   - ✅ Always prefers lot comp pricing when available
   - ✅ Stores both lot and individual pricing for comparison
   - ✅ Enhanced justification text with pricing comparison
   - ✅ Improved regex parser for lot size detection (handles "1st 12", ordinals, etc.)

2. **Data Models (`models.py`):**
   - ✅ Added `individual_value` field to `LotSuggestion`
   - ✅ Updated `use_lot_pricing` flag logic
   - ✅ Full lot pricing metadata included

3. **iOS App Integration:**
   - ✅ Added lot pricing fields to `LotSuggestionDTO`
   - ✅ Updated `CachedLot` model for persistence
   - ✅ Cache manager properly saves/loads lot pricing data
   - ✅ Lot detail view displays lot comp pricing section
   - ✅ Visual indicators show pricing comparison
   - ✅ "Recalculate" button for triggering lot recalculation
   - ✅ Long-running session (5min timeout) for expensive operations

4. **API Endpoints:**
   - ✅ `/api/lots/regenerate.json` - POST endpoint to trigger recalculation

### iOS UI Features

**Lot Detail View (`LotRecommendationsView.swift`):**
- Shows "Lot Comp Pricing" section when `use_lot_pricing == true`
- Displays:
  - Lot market value (primary price)
  - Number of eBay comps used
  - Per-book price
  - Individual pricing comparison (when available)
  - Visual indicators (green/orange) showing price difference
  - Note: "Using lot comps as more direct comparable"

**Example Display:**
```
📈 Lot comp pricing                    41 eBay comps
─────────────────────────────────────────────────────
Lot market value                           $285.74

Per-book price                              $23.81

─────────────────────────────────────────────────────
Individual pricing                         $568.62

⬇ $282.88 (49.8%) vs individual sales

Using lot comps as more direct comparable
```

## Benefits

- **Market-driven pricing** based on actual eBay lot sales
- **Optimal lot size detection** maximizes per-book value
- **Better lot decisions** compared to individual book pricing
- **Data-backed recommendations** for lot configurations

## File Location

`/Users/nickcuskey/ISBN/isbn_lot_optimizer/market.py` (lines 505-761)
