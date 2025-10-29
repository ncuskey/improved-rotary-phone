# Test Coverage Gaps - What We Should Be Testing

## Executive Summary

Our current test suite covers the **core decision logic** (TTS, Needs Review, Thresholds) but is missing tests for several critical supporting functions, edge cases, and integration points. This document identifies gaps and recommends additional tests to achieve comprehensive coverage.

**Current Coverage**: ~40% of functions
**Recommended Target**: 80%+ of critical path functions

---

## 1. Profit Calculation Functions (iOS)

### Currently NOT Tested ❌

**File**: `LotHelperApp/LotHelper/ScannerReviewView.swift`

#### `calculateEbayFees(salePrice:)` - Line 1574
**Function**: Calculates eBay fees (13.25% + $0.30)
**Why Critical**: Used in all eBay profit decisions
**Missing Tests**:
- [ ] Low price ($1-5) - fees might exceed proceeds
- [ ] Mid price ($10-30) - typical book range
- [ ] High price ($100+) - rare books
- [ ] Zero price edge case
- [ ] Negative price error handling

**Example Test**:
```python
def test_calculate_ebay_fees():
    # Test: $20 book
    sale_price = 20.0
    expected_fees = 20.0 * 0.1325 + 0.30  # $2.95
    expected_net = 20.0 - 2.95  # $17.05
    assert calculate_ebay_fees(sale_price) == (2.95, 17.05)

    # Test: $1 book (fees > 20% of price)
    sale_price = 1.0
    expected_fees = 1.0 * 0.1325 + 0.30  # $0.43 (43%!)
    assert calculate_ebay_fees(sale_price) == (0.43, 0.57)
```

#### `calculateAmazonFees(salePrice:)` - Line 1588
**Function**: Calculates Amazon fees (15% + $1.80)
**Why Critical**: Used for Amazon profit path decisions
**Missing Tests**:
- [ ] Verify 15% + $1.80 formula
- [ ] Compare to eBay fees (Amazon often higher for low-price books)
- [ ] High-value books where Amazon may be better

**Example Test**:
```python
def test_calculate_amazon_fees():
    # Test: $20 book
    sale_price = 20.0
    expected_fees = 20.0 * 0.15 + 1.80  # $4.80
    expected_net = 20.0 - 4.80  # $15.20

    # Compare to eBay for same book
    ebay_net = 17.05  # From above
    amazon_net = 15.20
    assert ebay_net > amazon_net  # eBay better for $20 book
```

#### `calculateProfit(_:)` - Line 1599
**Function**: Calculates net profit across all 3 exit strategies
**Why Critical**: Core decision input - determines buy/skip
**Missing Tests**:
- [ ] eBay only (no buyback/Amazon)
- [ ] Buyback only (best path)
- [ ] Amazon only
- [ ] All three paths available (choose best)
- [ ] Negative profit scenarios (loss after fees)
- [ ] Break-even scenarios
- [ ] Missing purchase price

**Example Test**:
```python
def test_calculate_profit_all_paths():
    # Book with all three exit strategies
    eval = create_eval(
        ebay_price=20.0,
        amazon_price=22.0,
        buyback_offer=15.0,
        purchase_price=2.0
    )

    profit = calculate_profit(eval)

    # eBay: $20 - $2.95 (fees) - $2 (cost) = $15.05
    assert profit.estimatedProfit == 15.05

    # Amazon: $22 - $4.80 (fees) - $2 (cost) = $15.20
    assert profit.amazonProfit == 15.20

    # Buyback: $15 - $2 (cost) = $13
    assert profit.buybackProfit == 13.0

    # Best path should be Amazon
    assert max(profit.estimatedProfit, profit.amazonProfit, profit.buybackProfit) == 15.20
```

---

## 2. Series Completion Logic (iOS)

### Currently NOT Tested ❌

#### `checkSeriesCompletion(_:)` - Line 1676
**Function**: Detects if book is part of ongoing series we're collecting
**Why Critical**: Strategic buying decision - may override profit thresholds
**Missing Tests**:
- [ ] Book in series with 0 previous books
- [ ] Book in series with 1-2 previous books
- [ ] Book in series with 3+ previous books (near-complete)
- [ ] Book NOT in a series
- [ ] Series name matching (exact vs fuzzy)
- [ ] Duplicate series detection (already have this book)

**Example Test**:
```python
def test_series_completion():
    # Test: 3rd book in Harry Potter series
    eval = create_eval_with_series(
        series_name="Harry Potter",
        series_index=3
    )

    # Mock: We already have books 1 and 2
    mock_database_has_books(["HP1", "HP2"])

    result = check_series_completion(eval)

    assert result.is_part_of_series == True
    assert result.books_in_series == 2
    assert result.series_name == "Harry Potter"

    # Strategic buying: Lower profit threshold from $5 to $3
    # (tested in buy decision logic)
```

**Strategic Impact**:
- Series completion may accept $3 profit instead of $5
- Near-complete series (3+ books) may accept $1 profit
- Very valuable series may accept -$2 (strategic loss)

---

## 3. Buy/Skip Decision Branches (iOS)

### Partially Tested ⚠️

We test **Needs Review** conditions but not the **actual buy/skip rules**.

#### Missing Buy Rule Tests:
**File**: `ScannerReviewView.swift` lines 1804-1896

- [ ] **RULE 1**: Buyback profit > 0 → Instant buy (guaranteed)
- [ ] **RULE 1.5**: Series completion with profit ≥ $3 → Strategic buy
- [ ] **RULE 2**: Strong profit (2x threshold) → Strong buy
- [ ] **RULE 3**: Meets minimum threshold + high confidence → Conditional buy
- [ ] **RULE 4**: Small profit ($1-5) + very high confidence → Buy
- [ ] **RULE 5**: No profit or loss → Skip
- [ ] **RULE 6**: No pricing + very high confidence → Buy with warning

**Example Tests Needed**:
```python
def test_buy_rule_guaranteed_buyback():
    # RULE 1: Buyback > 0 = instant buy
    eval = create_eval(
        buyback_offer=10.0,
        ebay_price=5.0,  # eBay might show loss
        purchase_price=2.0
    )

    decision = make_buy_decision(eval, thresholds=balanced)

    assert decision.decision_type == "buy"
    assert "Guaranteed" in decision.reason
    assert "$8.00 profit" in decision.reason  # $10 - $2


def test_buy_rule_series_strategic():
    # RULE 1.5: Series completion overrides profit threshold
    eval = create_eval_with_series(
        series_name="Harry Potter",
        profit=3.5,  # Below $5 threshold but above $3 series threshold
        confidence=55
    )

    mock_database_has_books(["HP1", "HP2"])

    decision = make_buy_decision(eval, thresholds=balanced)

    assert decision.decision_type == "buy"
    assert "Series: Harry Potter" in decision.reason
    assert "2 books" in decision.reason


def test_skip_rule_loss():
    # RULE 5: Loss after fees = skip
    eval = create_eval(
        ebay_price=5.0,  # Low price
        purchase_price=4.0,  # High cost
        confidence=80  # Even with high confidence
    )

    decision = make_buy_decision(eval, thresholds=balanced)

    # Net: $5 - $1.00 (fees) - $4 = $0 or negative
    assert decision.decision_type == "skip"
    assert "lose" in decision.reason.lower()
```

---

## 4. Backend Calculation Functions (Python)

### Currently NOT Tested ❌

**File**: `shared/probability.py`

#### `estimate_price(metadata, market, condition, edition, bookscouter)` - Line 192
**Function**: Estimates book price from various sources
**Why Critical**: Primary input to profit calculations
**Missing Tests**:
- [ ] Price from eBay sold median (most reliable)
- [ ] Price from eBay active average (fallback)
- [ ] Price from BookScouter Amazon (alternative)
- [ ] Price from list price (fallback)
- [ ] Condition adjustments (Like New vs Acceptable)
- [ ] Edition adjustments (1st edition premium)
- [ ] No data available (returns None)

**Example Test**:
```python
def test_estimate_price_hierarchy():
    # Test priority: eBay sold > eBay active > Amazon > List Price

    # Test 1: eBay sold median available (highest priority)
    market = EbayMarketStats(
        sold_avg_price=20.0,
        active_avg_price=25.0
    )
    price = estimate_price(metadata, market, "Good", None, None)
    assert price == 20.0  # Uses sold, not active

    # Test 2: Only eBay active available
    market = EbayMarketStats(
        sold_avg_price=None,
        active_avg_price=25.0
    )
    price = estimate_price(metadata, market, "Good", None, None)
    assert price == 25.0

    # Test 3: Only Amazon available
    bookscouter = BookScouterResult(amazon_lowest_price=22.0)
    price = estimate_price(metadata, None, "Good", None, bookscouter)
    assert price == 22.0


def test_estimate_price_condition_adjustments():
    market = EbayMarketStats(sold_avg_price=20.0)

    # Like New: +$3
    price_like_new = estimate_price(metadata, market, "Like New", None, None)
    assert price_like_new == 23.0

    # Good: -$1
    price_good = estimate_price(metadata, market, "Good", None, None)
    assert price_good == 19.0

    # Acceptable: -$4
    price_acceptable = estimate_price(metadata, market, "Acceptable", None, None)
    assert price_acceptable == 16.0
```

#### `compute_rarity(market)` - Line 267
**Function**: Calculates book rarity score (0-100)
**Why Critical**: Influences probability score
**Missing Tests**:
- [ ] Common book (high counts) → Low rarity
- [ ] Uncommon book (medium counts) → Medium rarity
- [ ] Rare book (low counts) → High rarity
- [ ] No market data → None

#### `score_probability(...)` - Line 397
**Function**: Calculates 0-100 probability score
**Why Critical**: Core confidence metric for decisions
**Missing Tests**:
- [ ] High sell-through (>60%) + low rarity → "Strong Buy"
- [ ] Medium everything → "Worth Buying"
- [ ] Low sell-through (<30%) → "Risky"
- [ ] Very low sell-through (<10%) → "Pass"
- [ ] Multiple signal combinations
- [ ] Edge cases (missing data)

---

## 5. Database Operations (Python)

### Currently NOT Tested ❌

**File**: `shared/database.py`, `isbn_lot_optimizer/service.py`

#### TTS Persistence
**Missing Tests**:
- [ ] Save book with TTS to database
- [ ] Load book with TTS from database
- [ ] Load legacy book (NULL TTS) → Returns None gracefully
- [ ] Update existing book with new TTS
- [ ] TTS column exists after migration

**Example Test**:
```python
def test_tts_database_persistence():
    from isbn_lot_optimizer.service import BookService

    service = BookService(test_db_path)

    # Create evaluation with TTS
    eval = BookEvaluation(
        isbn="TEST123",
        time_to_sell_days=45,
        # ... other fields
    )

    # Save to database
    service.save_book(eval)

    # Load from database
    loaded_book = service.get_book("TEST123")

    assert loaded_book.time_to_sell_days == 45


def test_tts_legacy_compatibility():
    # Test loading book without TTS (NULL in database)
    service = BookService(test_db_path)

    # Insert legacy record (no TTS column value)
    db.execute("INSERT INTO books (isbn, ...) VALUES (?, ...)", ("LEGACY123",))

    # Load should not crash
    book = service.get_book("LEGACY123")

    assert book.time_to_sell_days is None  # Graceful None
    assert book.isbn == "LEGACY123"  # Other fields work
```

---

## 6. Threshold Persistence (iOS)

### Currently Manually Tested ⚠️

**File**: `LotHelperApp/LotHelper/ScannerReviewView.swift`

#### DecisionThresholds Save/Load
**Missing Automated Tests**:
- [ ] Save custom thresholds to UserDefaults
- [ ] Load thresholds from UserDefaults
- [ ] Handle missing UserDefaults (first run)
- [ ] Handle corrupted UserDefaults (bad JSON)
- [ ] Preset application updates UserDefaults

**Example Test** (Would require iOS testing framework):
```swift
func testThresholdsPersistence() {
    // Clear UserDefaults
    UserDefaults.standard.removeObject(forKey: "decisionThresholds")

    // First load: Should get balanced defaults
    let initial = DecisionThresholds.load()
    XCTAssertEqual(initial.minProfitAutoBuy, 5.0)

    // Modify and save
    var custom = initial
    custom.minProfitAutoBuy = 7.5
    custom.save()

    // Load again: Should get custom value
    let loaded = DecisionThresholds.load()
    XCTAssertEqual(loaded.minProfitAutoBuy, 7.5)
}


func testThresholdsCorruptedData() {
    // Inject bad JSON
    UserDefaults.standard.set("invalid json", forKey: "decisionThresholds")

    // Load should fall back to balanced
    let loaded = DecisionThresholds.load()
    XCTAssertEqual(loaded.minProfitAutoBuy, 5.0)
}
```

---

## 7. Edge Cases & Error Handling

### Currently NOT Tested ❌

#### Data Edge Cases
- [ ] Book with all fields NULL (no metadata, no market, no buyback)
- [ ] Book with conflicting data (Amazon says profitable, eBay says loss)
- [ ] Book at exact threshold boundary (profit = $5.00 with $5.00 threshold)
- [ ] Book with TTS at cap (7 days or 365 days)
- [ ] Book with negative eBay sold count (data error)

#### Error Scenarios
- [ ] Invalid ISBN format
- [ ] Database connection failure
- [ ] Network timeout during fetch
- [ ] JSON decode error
- [ ] Division by zero in calculations
- [ ] UserDefaults write failure

**Example Tests**:
```python
def test_edge_case_all_null_data():
    # Book with absolutely no data
    eval = BookEvaluation(
        isbn="EMPTY",
        metadata=None,
        market=None,
        bookscouter=None,
        time_to_sell_days=None,
        estimated_price=None
    )

    # Should not crash
    decision = make_buy_decision(eval, thresholds=balanced)

    # Should flag for review (no data)
    assert decision.decision_type == "needsReview"
    assert "No pricing data" in decision.concerns


def test_edge_case_boundary_threshold():
    # Book with profit EXACTLY at threshold
    eval = create_eval(profit=5.0)  # Exactly $5
    thresholds = DecisionThresholds(minProfitAutoBuy=5.0)

    decision = make_buy_decision(eval, thresholds)

    # Should use >= comparison (buy at threshold)
    assert decision.decision_type == "buy"
```

---

## 8. Integration & Workflow Tests

### Partially Tested ⚠️

We have 1 integration test, but missing:

#### Missing Integration Scenarios
- [ ] Scan → Evaluation → Decision → Accept → Database
- [ ] Scan → Decision changes when thresholds change
- [ ] Multiple scans with different books
- [ ] Scan same book twice (duplicate detection)
- [ ] Series detection across multiple scans
- [ ] Threshold changes affecting existing evaluations

**Example Test**:
```python
def test_integration_threshold_change_affects_decision():
    # Scan a book with balanced thresholds
    eval = create_eval(profit=6.0, confidence=55)

    balanced = DecisionThresholds.balanced()
    decision1 = make_buy_decision(eval, balanced)
    assert decision1.decision_type == "buy"  # $6 >= $5

    # Change to conservative
    conservative = DecisionThresholds.conservative()
    decision2 = make_buy_decision(eval, conservative)
    assert decision2.decision_type == "skip"  # $6 < $8

    # Same book, different decision based on thresholds
```

---

## 9. Real-World Validation

### Currently NOT Tested ❌

#### Missing Real-World Tests
- [ ] Test with actual ISBNs from database
- [ ] Test with real market data (not synthetic)
- [ ] Compare TTS prediction vs actual sale time
- [ ] Track decision accuracy (buy recommendations that actually profit)
- [ ] A/B test different thresholds on same books

**Recommended Approach**:
```python
def test_real_world_validation():
    # Load 100 random books from production database
    service = BookService(production_db)
    books = service.list_books(limit=100)

    # Test each with balanced thresholds
    for book in books:
        decision = make_buy_decision(book, DecisionThresholds.balanced())

        # Assertions:
        # - Should not crash
        # - Should return valid decision type
        # - Reason should be non-empty
        # - Concerns should be logical (not contradictory)

        assert decision.decision_type in ["buy", "skip", "needsReview"]
        assert len(decision.reason) > 0

        if decision.decision_type == "needsReview":
            assert len(decision.concerns) > 0
```

---

## 10. Performance Tests

### Currently NOT Tested ❌

#### Missing Performance Tests
- [ ] Decision time for 1 book (should be < 10ms)
- [ ] Decision time for 1000 books (batch processing)
- [ ] TTS calculation time (should be O(1))
- [ ] Database query time
- [ ] UserDefaults save/load time

**Example Test**:
```python
def test_performance_single_decision():
    import time

    eval = create_typical_book_eval()

    start = time.time()
    decision = make_buy_decision(eval, DecisionThresholds.balanced())
    end = time.time()

    elapsed_ms = (end - start) * 1000
    assert elapsed_ms < 10, f"Decision took {elapsed_ms}ms (> 10ms limit)"


def test_performance_batch_decisions():
    evals = [create_typical_book_eval() for _ in range(1000)]

    start = time.time()
    for eval in evals:
        make_buy_decision(eval, DecisionThresholds.balanced())
    end = time.time()

    total_sec = end - start
    per_book_ms = (total_sec / 1000) * 1000

    assert per_book_ms < 5, f"Average {per_book_ms}ms per book (> 5ms limit)"
```

---

## Priority Recommendations

### High Priority (Should Add Soon) 🔴
1. **Profit Calculation Tests** - Core to all buy decisions
2. **Buy/Skip Rule Tests** - Most of decision logic untested
3. **Database TTS Persistence** - Critical for data integrity
4. **Edge Case: All NULL Data** - Common real-world scenario

### Medium Priority (Add in Next Iteration) 🟡
5. **Series Completion Logic** - Strategic value but complex
6. **Estimate Price Tests** - Price accuracy affects everything
7. **Threshold Boundary Tests** - Ensure >= not > comparison
8. **Real-World Validation** - Confidence in production

### Low Priority (Nice to Have) 🟢
9. **Performance Tests** - System seems fast enough
10. **Error Handling** - Rare scenarios, good defensive coding

---

## Test Implementation Plan

### Step 1: Add Python Backend Tests
**File**: `tests/test_profit_and_pricing.py`
```bash
# Test profit calculations, price estimation, rarity
python3 tests/test_profit_and_pricing.py
```

### Step 2: Add Buy/Skip Decision Tests
**File**: `tests/test_buy_skip_rules.py`
```python
# Test all 6 buy/skip rules
# Test series completion logic
# Test threshold boundary conditions
```

### Step 3: Add Database Tests
**File**: `tests/test_database_persistence.py`
```python
# Test TTS save/load
# Test legacy compatibility
# Test migration
```

### Step 4: Add iOS Unit Tests (XCTest)
**File**: `LotHelperApp/LotHelperTests/DecisionTests.swift`
```swift
// Test profit calculations
// Test threshold persistence
// Test UI state management
```

### Step 5: Real-World Validation Script
**File**: `tests/validate_production_decisions.py`
```python
# Load real books
# Test decision quality
# Generate accuracy report
```

---

## Current vs Target Coverage

| Component | Current | Target | Gap |
|-----------|---------|--------|-----|
| TTS Calculation | ✅ 100% | 100% | 0% |
| Needs Review Detection | ✅ 80% | 100% | 20% |
| Threshold Configuration | ✅ 70% | 90% | 20% |
| Profit Calculation | ❌ 0% | 100% | **100%** |
| Buy/Skip Rules | ❌ 20% | 100% | **80%** |
| Series Completion | ❌ 0% | 80% | **80%** |
| Price Estimation | ❌ 0% | 80% | **80%** |
| Database Operations | ⚠️ 30% | 90% | **60%** |
| Error Handling | ❌ 0% | 60% | **60%** |
| Integration Tests | ⚠️ 20% | 80% | **60%** |

**Overall Coverage**: ~35% → **Target**: 85%

---

## Conclusion

We have **solid coverage of the decision logic foundations** (TTS, Needs Review, Thresholds) but are missing tests for:

1. **Critical calculations** (profit, fees, price estimation)
2. **Decision branches** (actual buy/skip rules)
3. **Strategic logic** (series completion)
4. **Data persistence** (database, UserDefaults)
5. **Edge cases** (NULL data, boundaries, errors)

**Recommended Action**: Prioritize profit calculation and buy/skip rule tests to reach 60% coverage, then add database and edge case tests to reach 80%+.
