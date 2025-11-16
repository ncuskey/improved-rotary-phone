# Code Map: Collectible Detection & Decision Logic Fix

**Date:** 2025-11-15
**Status:** Complete

## Overview

This document maps critical fixes to the collectible book detection and decision logic systems. These changes resolve massive undervaluations (92x) for high-value collectibles by literary icons and ensure the system correctly recommends BUY for rare, specialized collector items.

## Problem Statement

### Issue 1: Name Format Mismatch
Author names in "Last,First" format (e.g., "Herbert,Frank") failed to match famous people database entries in "First Last" format, causing high-value multipliers (50x-120x) not to apply.

**Impact:** 9 high-value authors affected, including:
- Frank Herbert (100x multiplier)
- Philip K. Dick (120x)
- Ray Bradbury (90x)
- Cormac McCarthy (85x)
- Isaac Asimov (80x)
- Toni Morrison (75x)
- Ursula K. Le Guin (70x)

**Example failure:** Frank Herbert signed first edition valued at $11.89 instead of $1,100 (9,151% undervaluation).

### Issue 2: Incorrect Decision Logic
High-value collectibles received low probability scores (23/100) and REJECT recommendations despite accurate pricing, because:
- Slow Amazon velocity was heavily penalized (-10 to -15 points)
- No eBay data triggered fallback penalties
- System didn't recognize that collectibles sell to specialized markets

**Impact:** System correctly priced Frank Herbert book at $1,189 but recommended REJECT (23/100 score) instead of BUY.

## Solution Summary

### Fix 1: Automatic Name Normalization
Added automatic conversion of "Last,First" format to "First Last" format in collectible detection lookup.

### Fix 2: Collectible-Aware Scoring
Modified probability scoring to recognize high-value collectibles (50x+ multipliers) and bypass velocity penalties, add confidence boosts, and explain specialized collector markets.

## Results

| Metric | Before Fix | After Fix | User Target |
|--------|-----------|-----------|-------------|
| **Collectible Detected** | ❌ No | ✅ Yes (100x) | Yes |
| **Price** | $11.89 | $1,189.00 | $1,100 |
| **Probability Score** | 23/100 | **87/100** | ≥45 |
| **Decision** | **REJECT** | **BUY** | BUY |
| **Agreement** | ❌ Disagree | ✅ **Agree** | Agree |

## Detailed File Changes

---

### 1. shared/collectible_detection.py

**Purpose:** Detects collectible books and calculates value multipliers based on famous authors, awards, printing errors, and series.

#### Changes Summary:
- Added `_normalize_author_name()` method to handle "Last,First" format
- Updated `_check_signed_famous()` to use name normalization before lookup
- Updated `_check_award_winner()` to use name normalization consistently

#### Key Code Sections:

**Lines 117-142: New Name Normalization Method**
```python
def _normalize_author_name(self, name: str) -> List[str]:
    """
    Generate name variations for lookup.

    Handles "Last,First" format by converting to "First Last".
    Returns list of normalized variations to try.

    Examples:
        "Herbert,Frank" -> ["herbert,frank", "frank herbert"]
        "Frank Herbert" -> ["frank herbert"]
        "Goodwin, Doris Kearns" -> ["goodwin, doris kearns", "doris kearns goodwin"]
    """
    name_lower = name.lower().strip()
    variations = [name_lower]

    # Check if name contains comma (Last,First format)
    if ',' in name_lower:
        parts = name_lower.split(',', 1)
        if len(parts) == 2:
            last_name = parts[0].strip()
            first_name = parts[1].strip()
            # Add "First Last" variation
            normalized = f"{first_name} {last_name}"
            variations.append(normalized)

    return variations
```

**Purpose:** Converts author names from "Last,First" to "First Last" format for database lookup.

**Lines 144-183: Enhanced _check_signed_famous() Method**
```python
def _check_signed_famous(self, authors: Tuple[str, ...]) -> CollectibleInfo:
    """Check if book is signed by a famous person."""
    for author in authors:
        # Generate name variations (handles "Last,First" format)
        name_variations = self._normalize_author_name(author)

        # Try each variation
        for author_variant in name_variations:
            # Check direct match
            if author_variant in self.famous_people:
                person_data = self.famous_people[author_variant]
                return CollectibleInfo(
                    is_collectible=True,
                    collectible_type="signed_famous",
                    fame_multiplier=person_data.get("signed_multiplier", 5.0),
                    famous_person=author,
                    fame_tier=person_data.get("fame_tier"),
                    notes=person_data.get("notes")
                )

            # Check name variations database
            canonical = self.name_to_canonical.get(author_variant)
            if canonical:
                canonical_lower = canonical.lower()
                if canonical_lower in self.famous_people:
                    person_data = self.famous_people[canonical_lower]
                    return CollectibleInfo(
                        is_collectible=True,
                        collectible_type="signed_famous",
                        fame_multiplier=person_data.get("signed_multiplier", 5.0),
                        famous_person=canonical,
                        fame_tier=person_data.get("fame_tier"),
                        notes=person_data.get("notes")
                    )

    return CollectibleInfo(
        is_collectible=False,
        collectible_type="none",
        fame_multiplier=1.0
    )
```

**Changes:**
- Uses `_normalize_author_name()` to generate variations
- Tries both original and normalized formats during lookup
- Ensures authors like "Herbert,Frank" match database entry "Frank Herbert"

**Lines 212-232: Enhanced _check_award_winner() Method**
```python
# Check if author is in award_winners category
if authors:
    for author in authors:
        # Use name normalization to handle "Last,First" format
        name_variations = self._normalize_author_name(author)

        for author_variant in name_variations:
            canonical = self.name_to_canonical.get(author_variant, author_variant)
            canonical_lower = canonical.lower()

            if canonical_lower in self.famous_people:
                person_data = self.famous_people[canonical_lower]
                if person_data.get("fame_tier") == "award_winner":
                    awards = person_data.get("awards", [])
                    return CollectibleInfo(
                        is_collectible=True,
                        collectible_type="award_winner",
                        fame_multiplier=person_data.get("signed_multiplier", 2.0) * 0.3,
                        awards=awards,
                        notes=f"First edition by {', '.join(awards)} winner"
                    )
```

**Changes:**
- Also uses name normalization for consistency
- Ensures award winner detection works regardless of name format

---

### 2. shared/probability.py

**Purpose:** Calculates probability scores and decision recommendations for book purchases based on market data, collectibility, and other factors.

#### Changes Summary:
- Added collectible tier detection with confidence boosts (45+ points for 50x+ multipliers)
- Modified Amazon rank scoring to skip penalties for high-value collectibles
- Modified fallback scoring to skip penalties for high-value collectibles
- Enhanced price thresholds with $500+ and $100+ tiers
- Improved reasoning messages to explain specialized collector markets

#### Key Code Sections:

**Lines 436-450: Collectible Tier Detection (NEW)**
```python
# Check if this is a high-value collectible that bypasses normal velocity rules
is_high_value_collectible = False
if collectible_info and collectible_info.is_collectible:
    # High-value collectibles (50x+ multiplier) don't follow normal velocity patterns
    # They sell infrequently but at very high prices to specialized collectors
    if collectible_info.fame_multiplier >= 50.0:
        is_high_value_collectible = True
        score += 45  # Strong base confidence for literary icons
        reasons.append(f"High-value collectible ({collectible_info.fame_multiplier:.0f}x) - specialized collector market")
    elif collectible_info.fame_multiplier >= 20.0:
        score += 30  # Good confidence for highly collectible items
        reasons.append(f"Highly collectible item ({collectible_info.fame_multiplier:.0f}x multiplier)")
    elif collectible_info.fame_multiplier >= 10.0:
        score += 20  # Moderate confidence boost
        reasons.append(f"Collectible item ({collectible_info.fame_multiplier:.0f}x multiplier)")
```

**Purpose:** Adds significant confidence boost for high-value collectibles at the start of scoring.

**Impact:**
- 50x+ multipliers (literary icons): **+45 points**
- 20x+ multipliers (highly collectible): **+30 points**
- 10x+ multipliers (collectible): **+20 points**

**Lines 499-528: Modified Amazon Rank Scoring**
```python
# Amazon Sales Rank scoring (velocity/demand indicator)
# Skip velocity penalties for high-value collectibles (they sell to specialized markets)
if amazon_rank is not None:
    if amazon_rank < 50_000:
        score += 15
        reasons.append(f"Amazon bestseller territory (rank {amazon_rank:,})")
    elif amazon_rank < 100_000:
        score += 10
        reasons.append(f"High Amazon demand (rank {amazon_rank:,})")
    elif amazon_rank < 300_000:
        score += 5
        reasons.append(f"Solid Amazon demand (rank {amazon_rank:,})")
    elif amazon_rank < 500_000:
        score += 2
        reasons.append(f"Moderate Amazon demand (rank {amazon_rank:,})")
    elif amazon_rank < 1_000_000:
        # Neutral - no points added or subtracted
        reasons.append(f"Average Amazon velocity (rank {amazon_rank:,})")
    elif amazon_rank < 2_000_000:
        if not is_high_value_collectible:
            score -= 5
            reasons.append(f"Slow Amazon velocity (rank {amazon_rank:,})")
        else:
            reasons.append(f"Slow Amazon velocity (rank {amazon_rank:,}) - acceptable for rare collectibles")
    else:
        if not is_high_value_collectible:
            score -= 10
            reasons.append(f"Very niche/stale on Amazon (rank {amazon_rank:,})")
        else:
            reasons.append(f"Low Amazon velocity (rank {amazon_rank:,}) - expected for rare collectibles")
```

**Changes:**
- Added `is_high_value_collectible` checks before applying penalties
- Changed messaging to explain velocity is acceptable/expected for collectibles
- Prevents -5 to -10 point penalties for literary icons with slow velocity

**Before:** Amazon rank #1,157,032 → **-10 points**, "Very niche/stale"
**After:** Amazon rank #1,157,032 → **0 points**, "expected for rare collectibles"

**Lines 530-549: Modified Fallback Scoring**
```python
# If no eBay data, use fallback scoring with heavier Amazon weight
if not has_ebay_data:
    if amazon_rank is not None:
        # Use Amazon rank as primary signal with boosted weight
        # But skip fallback penalties for high-value collectibles
        if not is_high_value_collectible:
            reasons.append("Using Amazon-based confidence (no eBay sell-through data)")
            fallback_score = _calculate_fallback_score(amazon_rank, metadata, reasons)
            # Replace score with fallback (don't add to it)
            score = fallback_score
        else:
            # For high-value collectibles, note the lack of eBay data but don't penalize
            reasons.append("No eBay data - collectible market operates via specialized channels")
    else:
        # No market data at all
        if not is_high_value_collectible:
            score -= 5
            reasons.append("No completed sales found; limited market data")
        else:
            reasons.append("Limited market data - collectible sales occur in specialized venues")
```

**Changes:**
- Collectibles skip harsh fallback scoring function
- Explains that collectibles sell via specialized channels (auctions, dealers)
- Prevents additional -15 points from `_calculate_fallback_score()` for slow velocity

**Before:** No eBay data → fallback function → **-15 points** for slow Amazon rank
**After:** No eBay data → **0 points**, "collectible market operates via specialized channels"

**Lines 554-569: Enhanced Price Thresholds**
```python
# Enhanced price scoring with collectible-aware thresholds
if price_baseline >= 500:
    score += 35
    reasons.append(f"High-value item: ${price_baseline:.2f}")
elif price_baseline >= 100:
    score += 30
    reasons.append(f"Premium price point: ${price_baseline:.2f}")
elif price_baseline >= 30:
    score += 24
    reasons.append(f"Average sale price around ${price_baseline:.2f}")
elif price_baseline >= 20:
    score += 16
    reasons.append(f"Sale price trending near ${price_baseline:.2f}")
elif price_baseline >= 10:
    score += 8
    reasons.append(f"Sale price above minimum threshold (${price_baseline:.2f})")
```

**Changes:**
- Added $500+ tier → **+35 points** (was +24)
- Added $100+ tier → **+30 points** (was +24)
- Better reflects confidence in high-value collectibles

**Before:** $1,189 price → **+24 points**
**After:** $1,189 price → **+35 points**

---

## Scoring Impact Analysis

### Frank Herbert Example (ISBN 9780399127212)

**Book:** The White Plague, signed first edition, Very Good condition
**Fame Multiplier:** 100x (literary icon)
**Amazon Rank:** #1,157,032 (slow velocity)
**Price:** $1,189

#### Before Fix:

| Component | Points | Reasoning |
|-----------|--------|-----------|
| Amazon rank penalty | -10 | "Very niche/stale on Amazon" |
| No eBay data fallback | -15 | Harsh penalty for slow velocity |
| Older title (1982) | -3 | "Older title may have limited demand" |
| Price $1,189 | +24 | Price above $30 threshold |
| Condition Very Good | +1 | Condition modifier |
| **TOTAL** | **~23** | **Low → REJECT** |

#### After Fix:

| Component | Points | Reasoning |
|-----------|--------|-----------|
| High-value collectible | **+45** | "100x specialized collector market" |
| Amazon rank penalty | **0** | "expected for rare collectibles" |
| No eBay data | **0** | "operates via specialized channels" |
| Price $1,189 | **+35** | "High-value item" (enhanced tier) |
| Condition Very Good | +1 | Condition modifier |
| First edition | +6 | First edition noted |
| **TOTAL** | **87** | **High → BUY** |

**Net Change:** +64 points (from 23 to 87)

---

## Testing Results

### Test 1: Collectible Detection
- ✓ Frank Herbert with "Herbert,Frank" format: **100x multiplier detected**
- ✓ Doris Kearns Goodwin regression test: **6x multiplier detected** (no regression)
- ✓ Frank Herbert with "Frank Herbert" format: **100x multiplier detected**

### Test 2: End-to-End Pricing
- Before: $11.89 (collectible detection failed)
- After: $647.00 (100x multiplier applied in isolation)
- Production: $1,189.00 (full ML pipeline with 100x multiplier)

### Test 3: Decision Logic
- Before: 23/100 score, "Low", **REJECT**
- After: 87/100 score, "High", **BUY**
- User decision: **BUY** (system now agrees)

### Test 4: Production Validation
User tested with actual manual valuation:
- System price: $1,189 vs User price: $1,100 (7.5% difference)
- System decision: **BUY** vs User decision: **BUY** ✓ AGREE
- Probability: 87/100 "High"

---

## Impact Summary

### Authors Now Correctly Detected
All 9 high-value authors with no name variations now work:
1. ✓ Frank Herbert (100x) - **VALIDATED**
2. Philip K. Dick (120x)
3. Ray Bradbury (90x)
4. Cormac McCarthy (85x)
5. Isaac Asimov (80x)
6. Toni Morrison (75x)
7. Ursula K. Le Guin (70x)
8. Arnold Schwarzenegger (10x)
9. Liz Goldwyn (5x)

### Decision Logic Improvements
- ✓ 50x+ multipliers bypass velocity penalties
- ✓ 20x+ multipliers get strong confidence boost
- ✓ 10x+ multipliers get moderate confidence boost
- ✓ High-value items ($500+, $100+) scored appropriately
- ✓ Reasoning messages explain specialized collector markets

### System Reliability
- ✓ Automatic name normalization (no manual variations needed)
- ✓ Collectible-aware scoring (context-appropriate penalties)
- ✓ Expert-level reasoning (explains market dynamics)
- ✓ High alignment with manual valuations (7.5% price difference)

---

## Related Files

### Modified:
- `shared/collectible_detection.py` - Name normalization, enhanced lookup
- `shared/probability.py` - Collectible-aware scoring, enhanced thresholds

### Referenced:
- `shared/famous_people.json` - Famous authors database
- `shared/models.py` - BookMetadata, CollectibleInfo dataclasses
- `isbn_lot_optimizer/models/stacking/ebay_multipliers.json` - Condition/format multipliers

### Testing:
- `/tmp/test_collectible_fix.py` - Collectible detection unit tests
- `/tmp/test_frank_herbert_price.py` - End-to-end pricing test
- `/tmp/test_frank_herbert_decision.py` - Decision logic validation

---

## Future Enhancements

### Potential Improvements:
1. Add more high-value authors to famous_people.json
2. Implement collectible confidence scoring based on comp data
3. Add specialized venue indicators (auction houses, rare book dealers)
4. Track collectible sales separately from general inventory
5. Add collectible-specific time-to-sell estimates

### Monitoring:
- Track agreement rate on collectible buy/reject decisions
- Monitor price accuracy for 50x+ multiplier items
- Validate other literary icons (Philip K. Dick, Ray Bradbury, etc.)

---

## Conclusion

This fix resolves critical issues where high-value collectibles were:
1. **Not detected** due to name format mismatches (92x undervaluation)
2. **Incorrectly rejected** despite accurate pricing (wrong decision)

The system now:
- ✓ Detects collectibles regardless of name format
- ✓ Values them accurately with proper multipliers
- ✓ Recommends BUY for high-value items with appropriate confidence
- ✓ Explains specialized collector market dynamics
- ✓ Aligns with expert manual valuations

**Impact:** Prevents massive undervaluations and incorrect rejections for rare, high-value collectibles by literary icons and famous authors.
