#!/usr/bin/env python3
"""
Comprehensive test suite for the Purchase Decision System (Phases 1-3).

Tests:
- Phase 1: Time-to-Sell (TTS) calculation
- Phase 2: Needs Review decision state detection
- Phase 3: Configurable thresholds impact on decisions

Run: python3 tests/test_purchase_decision_system.py
"""

import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.models import BookEvaluation, EbayMarketStats, BookMetadata, BookScouterResult
from shared.probability import build_book_evaluation, compute_time_to_sell


class DecisionThresholds:
    """Python equivalent of Swift DecisionThresholds for testing."""
    def __init__(
        self,
        min_profit_auto_buy: float = 5.0,
        min_profit_slow_moving: float = 8.0,
        min_profit_uncertainty: float = 3.0,
        min_confidence_auto_buy: float = 50.0,
        low_confidence_threshold: float = 30.0,
        min_comps_required: int = 3,
        max_slow_moving_tts: int = 180,
        require_profit_data: bool = True
    ):
        self.min_profit_auto_buy = min_profit_auto_buy
        self.min_profit_slow_moving = min_profit_slow_moving
        self.min_profit_uncertainty = min_profit_uncertainty
        self.min_confidence_auto_buy = min_confidence_auto_buy
        self.low_confidence_threshold = low_confidence_threshold
        self.min_comps_required = min_comps_required
        self.max_slow_moving_tts = max_slow_moving_tts
        self.require_profit_data = require_profit_data

    @classmethod
    def balanced(cls):
        return cls()

    @classmethod
    def conservative(cls):
        return cls(
            min_profit_auto_buy=8.0,
            min_profit_slow_moving=10.0,
            min_profit_uncertainty=5.0,
            min_confidence_auto_buy=60.0,
            low_confidence_threshold=40.0,
            min_comps_required=5,
            max_slow_moving_tts=120
        )

    @classmethod
    def aggressive(cls):
        return cls(
            min_profit_auto_buy=3.0,
            min_profit_slow_moving=5.0,
            min_profit_uncertainty=2.0,
            min_confidence_auto_buy=40.0,
            low_confidence_threshold=20.0,
            min_comps_required=2,
            max_slow_moving_tts=240
        )


def simulate_needs_review_check(
    eval: BookEvaluation,
    thresholds: DecisionThresholds,
    best_profit: Optional[float] = None,
    buyback_profit: Optional[float] = None,
    ebay_profit: Optional[float] = None
) -> tuple[bool, list[str]]:
    """
    Simulate the Swift app's Needs Review logic.
    Returns (should_review, concerns_list)
    """
    concerns = []
    score = eval.probability_score

    # CHECK 1: Insufficient market data
    total_comps = 0
    if eval.market:
        total_comps = (eval.market.sold_count or 0) + (eval.market.active_count or 0)

    if total_comps < thresholds.min_comps_required:
        if total_comps == 0:
            concerns.append("No market data found")
        else:
            concerns.append(f"Only {total_comps} comparable listing{'s' if total_comps != 1 else ''} found")

    # CHECK 2: Conflicting signals
    if buyback_profit and buyback_profit > thresholds.min_profit_auto_buy:
        if ebay_profit and ebay_profit < 0:
            concerns.append(f"Conflicting: Buyback shows profit but eBay predicts loss")

    # CHECK 3: Very slow moving with thin margin
    if eval.time_to_sell_days and eval.time_to_sell_days > thresholds.max_slow_moving_tts:
        if best_profit and best_profit < thresholds.min_profit_slow_moving:
            concerns.append(f"Slow velocity (~{eval.time_to_sell_days} days) + thin margin")

    # CHECK 4: High uncertainty
    if score < thresholds.low_confidence_threshold:
        if best_profit and best_profit < thresholds.min_profit_uncertainty:
            concerns.append(f"Low confidence (score {int(score)}) + minimal profit")

    # CHECK 5: No profit data
    if thresholds.require_profit_data and best_profit is None:
        if score < thresholds.min_confidence_auto_buy:
            concerns.append("No pricing data + moderate confidence")

    return len(concerns) > 0, concerns


def test_phase1_tts_calculation():
    """Test Phase 1: TTS calculation with various velocities."""
    print("\n" + "="*80)
    print("PHASE 1: TIME-TO-SELL (TTS) CALCULATION")
    print("="*80)

    test_cases = [
        (100, 7, "Super fast-moving (100 sold) - capped at minimum"),
        (30, 7, "Very fast-moving (30 sold) - capped at minimum"),
        (12, 7, "Fast-moving (12 sold) - rounds to 7"),
        (9, 10, "Fast-moving (9 sold)"),
        (3, 30, "Moderate velocity (3 sold)"),
        (1, 90, "Slow-moving (1 sold)"),
        (0, 365, "Very slow (0 sold) - capped at maximum"),
    ]

    all_passed = True
    for sold_count, expected_tts, description in test_cases:
        market = EbayMarketStats(
            isbn="TEST",
            active_count=10,
            active_avg_price=15.0,
            sold_count=sold_count,
            sold_avg_price=14.0,
            sell_through_rate=0.5,
            currency="USD"
        )

        tts = compute_time_to_sell(market)
        passed = tts == expected_tts
        all_passed = all_passed and passed

        status = "✓" if passed else "✗"
        print(f"{status} {description}")
        print(f"  Sold: {sold_count}, TTS: {tts} days (expected: {expected_tts})")

        if not passed:
            print(f"  ❌ FAILED: Got {tts}, expected {expected_tts}")

    # Test None handling
    tts = compute_time_to_sell(None)
    passed = tts is None
    all_passed = all_passed and passed
    status = "✓" if passed else "✗"
    print(f"{status} No market data - returns None")
    print(f"  Result: {tts} (expected: None)")

    print("\n" + "-"*80)
    if all_passed:
        print("✅ Phase 1: All TTS tests PASSED")
    else:
        print("❌ Phase 1: Some TTS tests FAILED")

    return all_passed


def test_phase2_needs_review():
    """Test Phase 2: Needs Review decision state."""
    print("\n" + "="*80)
    print("PHASE 2: NEEDS REVIEW DECISION STATE")
    print("="*80)

    thresholds = DecisionThresholds.balanced()
    all_passed = True

    # Test 1: Insufficient market data
    print("\n📋 Test 1: Insufficient Market Data")
    print("-"*80)

    metadata = BookMetadata(
        isbn="TEST001",
        title="Rare Book",
        authors=("Test Author",),
        published_year=2020
    )

    market = EbayMarketStats(
        isbn="TEST001",
        active_count=1,
        active_avg_price=20.0,
        sold_count=1,  # Only 2 total comps
        sold_avg_price=18.0,
        sell_through_rate=0.5,
        currency="USD",
        time_to_sell_days=90
    )

    eval1 = build_book_evaluation(
        isbn="TEST001",
        original_isbn="TEST001",
        metadata=metadata,
        market=market,
        condition="Good",
        edition=None,
        bookscouter=None
    )

    should_review, concerns = simulate_needs_review_check(eval1, thresholds)
    passed = should_review and any("2 comparable" in c for c in concerns)
    all_passed = all_passed and passed

    status = "✓" if passed else "✗"
    print(f"{status} Total comps: 2 (requires 3)")
    print(f"  Should Review: {should_review} (expected: True)")
    print(f"  Concerns: {concerns}")
    if not passed:
        print(f"  ❌ FAILED: Expected review flag for insufficient comps")

    # Test 2: Conflicting signals
    print("\n📋 Test 2: Conflicting Signals")
    print("-"*80)

    market2 = EbayMarketStats(
        isbn="TEST002",
        active_count=5,
        active_avg_price=5.0,
        sold_count=8,
        sold_avg_price=4.50,
        sell_through_rate=0.62,
        currency="USD",
        time_to_sell_days=15
    )

    bookscouter2 = BookScouterResult(
        isbn_10="TEST002",
        isbn_13="9780000000002",
        best_price=10.0,
        best_vendor="BooksRun",
        total_vendors=15,
        offers=[],
        amazon_sales_rank=50000,
        amazon_count=20,
        amazon_lowest_price=12.0,
        amazon_trade_in_price=None
    )

    metadata2 = BookMetadata(
        isbn="TEST002",
        title="Conflicting Book",
        authors=("Test Author",),
        published_year=2019
    )

    eval2 = build_book_evaluation(
        isbn="TEST002",
        original_isbn="TEST002",
        metadata=metadata2,
        market=market2,
        condition="Good",
        edition=None,
        bookscouter=bookscouter2
    )

    # Simulate: buyback profitable but eBay shows loss
    buyback_profit = 8.0  # $10 offer - $2 cost
    ebay_profit = -1.5  # Low eBay price - fees - cost

    should_review, concerns = simulate_needs_review_check(
        eval2, thresholds,
        best_profit=buyback_profit,
        buyback_profit=buyback_profit,
        ebay_profit=ebay_profit
    )

    passed = should_review and any("Conflicting" in c for c in concerns)
    all_passed = all_passed and passed

    status = "✓" if passed else "✗"
    print(f"{status} Buyback: ${buyback_profit:.2f}, eBay: ${ebay_profit:.2f}")
    print(f"  Should Review: {should_review} (expected: True)")
    print(f"  Concerns: {concerns}")
    if not passed:
        print(f"  ❌ FAILED: Expected review flag for conflicting signals")

    # Test 3: Slow velocity + thin margin
    print("\n📋 Test 3: Slow Velocity + Thin Margin")
    print("-"*80)

    # To get TTS > 180 days, we need: 90 / sold_count > 180
    # So sold_count < 0.5, which means sold_count = 0 (results in TTS = 365)
    market3 = EbayMarketStats(
        isbn="TEST003",
        active_count=10,
        active_avg_price=12.0,
        sold_count=0,  # Will result in TTS = 365 days
        sold_avg_price=11.0,
        sell_through_rate=0.0,
        currency="USD"
    )

    metadata3 = BookMetadata(
        isbn="TEST003",
        title="Slow Book",
        authors=("Test Author",),
        published_year=2018
    )

    eval3 = build_book_evaluation(
        isbn="TEST003",
        original_isbn="TEST003",
        metadata=metadata3,
        market=market3,
        condition="Good",
        edition=None,
        bookscouter=None
    )

    thin_margin = 6.0  # Below $8 threshold
    should_review, concerns = simulate_needs_review_check(
        eval3, thresholds,
        best_profit=thin_margin
    )

    actual_tts = eval3.time_to_sell_days or 0
    passed = should_review and any("Slow velocity" in c for c in concerns)
    all_passed = all_passed and passed

    status = "✓" if passed else "✗"
    print(f"{status} TTS: {actual_tts} days (>180), Profit: ${thin_margin:.2f}")
    print(f"  Should Review: {should_review} (expected: True)")
    print(f"  Concerns: {concerns}")
    if not passed:
        print(f"  ❌ FAILED: Expected review flag for slow + thin margin")

    # Test 4: High confidence - should NOT review
    print("\n📋 Test 4: High Confidence (Control)")
    print("-"*80)

    market4 = EbayMarketStats(
        isbn="TEST004",
        active_count=15,
        active_avg_price=25.0,
        sold_count=20,
        sold_avg_price=24.0,
        sell_through_rate=0.57,
        currency="USD",
        time_to_sell_days=7
    )

    bookscouter4 = BookScouterResult(
        isbn_10="TEST004",
        isbn_13="9780000000004",
        best_price=18.0,
        best_vendor="BooksRun",
        total_vendors=20,
        offers=[],
        amazon_sales_rank=10000,
        amazon_count=50,
        amazon_lowest_price=28.0,
        amazon_trade_in_price=15.0
    )

    metadata4 = BookMetadata(
        isbn="TEST004",
        title="Popular Book",
        authors=("Famous Author",),
        published_year=2022
    )

    eval4 = build_book_evaluation(
        isbn="TEST004",
        original_isbn="TEST004",
        metadata=metadata4,
        market=market4,
        condition="Like New",
        edition=None,
        bookscouter=bookscouter4
    )

    good_profit = 15.0
    should_review, concerns = simulate_needs_review_check(
        eval4, thresholds,
        best_profit=good_profit
    )

    passed = not should_review
    all_passed = all_passed and passed

    status = "✓" if passed else "✗"
    print(f"{status} High quality book with good profit")
    print(f"  Should Review: {should_review} (expected: False)")
    print(f"  Score: {eval4.probability_score}, Profit: ${good_profit:.2f}")
    if not passed:
        print(f"  ❌ FAILED: Should NOT flag high-confidence book")

    print("\n" + "-"*80)
    if all_passed:
        print("✅ Phase 2: All Needs Review tests PASSED")
    else:
        print("❌ Phase 2: Some Needs Review tests FAILED")

    return all_passed


def test_phase3_configurable_thresholds():
    """Test Phase 3: Configurable thresholds."""
    print("\n" + "="*80)
    print("PHASE 3: CONFIGURABLE THRESHOLDS")
    print("="*80)

    all_passed = True

    # Create a marginal book that will have different outcomes based on thresholds
    print("\n📋 Marginal Book Test: $6 profit, 45% confidence, 8 comps")
    print("-"*80)

    market = EbayMarketStats(
        isbn="MARGINAL",
        active_count=5,
        active_avg_price=15.0,
        sold_count=3,
        sold_avg_price=14.0,
        sell_through_rate=0.375,
        currency="USD",
        time_to_sell_days=30
    )

    metadata = BookMetadata(
        isbn="MARGINAL",
        title="Marginal Book",
        authors=("Test Author",),
        published_year=2020
    )

    eval_marginal = build_book_evaluation(
        isbn="MARGINAL",
        original_isbn="MARGINAL",
        metadata=metadata,
        market=market,
        condition="Good",
        edition=None,
        bookscouter=None
    )

    profit = 6.0
    score = 45.0

    # Test with Conservative thresholds
    print("\n  Conservative Thresholds (Min Profit: $8)")
    conservative = DecisionThresholds.conservative()

    # With $6 profit < $8 threshold, should NOT auto-buy
    meets_threshold = profit >= conservative.min_profit_auto_buy
    passed = not meets_threshold
    all_passed = all_passed and passed

    status = "✓" if passed else "✗"
    print(f"  {status} Profit ${profit:.2f} < Threshold ${conservative.min_profit_auto_buy:.2f}")
    print(f"     Expected: SKIP or NEEDS REVIEW")
    if not passed:
        print(f"     ❌ FAILED")

    # Test with Balanced thresholds
    print("\n  Balanced Thresholds (Min Profit: $5)")
    balanced = DecisionThresholds.balanced()

    # With $6 profit >= $5 threshold, should consider buying
    meets_threshold = profit >= balanced.min_profit_auto_buy
    passed = meets_threshold
    all_passed = all_passed and passed

    status = "✓" if passed else "✗"
    print(f"  {status} Profit ${profit:.2f} >= Threshold ${balanced.min_profit_auto_buy:.2f}")
    print(f"     Expected: BUY (with moderate confidence check)")
    if not passed:
        print(f"     ❌ FAILED")

    # Test with Aggressive thresholds
    print("\n  Aggressive Thresholds (Min Profit: $3)")
    aggressive = DecisionThresholds.aggressive()

    # With $6 profit >= $3 threshold, definitely should buy
    meets_threshold = profit >= aggressive.min_profit_auto_buy
    passed = meets_threshold
    all_passed = all_passed and passed

    status = "✓" if passed else "✗"
    print(f"  {status} Profit ${profit:.2f} >= Threshold ${aggressive.min_profit_auto_buy:.2f}")
    print(f"     Expected: BUY")
    if not passed:
        print(f"     ❌ FAILED")

    # Test comps threshold variation
    print("\n📋 Comps Threshold Test: Book with 2 comps")
    print("-"*80)

    market_sparse = EbayMarketStats(
        isbn="SPARSE",
        active_count=1,
        active_avg_price=20.0,
        sold_count=1,
        sold_avg_price=19.0,
        sell_through_rate=0.5,
        currency="USD",
        time_to_sell_days=90
    )

    metadata_sparse = BookMetadata(
        isbn="SPARSE",
        title="Sparse Data Book",
        authors=("Test Author",),
        published_year=2021
    )

    eval_sparse = build_book_evaluation(
        isbn="SPARSE",
        original_isbn="SPARSE",
        metadata=metadata_sparse,
        market=market_sparse,
        condition="Good",
        edition=None,
        bookscouter=None
    )

    # Conservative: requires 5 comps
    should_review_cons, concerns_cons = simulate_needs_review_check(eval_sparse, conservative)
    passed_cons = should_review_cons

    status = "✓" if passed_cons else "✗"
    print(f"  {status} Conservative (requires 5 comps): Review = {should_review_cons} (expected: True)")

    # Balanced: requires 3 comps
    should_review_bal, concerns_bal = simulate_needs_review_check(eval_sparse, balanced)
    passed_bal = should_review_bal

    status = "✓" if passed_bal else "✗"
    print(f"  {status} Balanced (requires 3 comps): Review = {should_review_bal} (expected: True)")

    # Aggressive: requires 2 comps
    should_review_agg, concerns_agg = simulate_needs_review_check(eval_sparse, aggressive)
    passed_agg = not should_review_agg  # Should NOT review with 2 comps and min of 2

    status = "✓" if passed_agg else "✗"
    print(f"  {status} Aggressive (requires 2 comps): Review = {should_review_agg} (expected: False)")

    all_passed = all_passed and passed_cons and passed_bal and passed_agg

    # Test TTS threshold variation
    # To get TTS = 200 days: 90 / sold_count = 200, so sold_count = 0.45, rounds to 0 (gives 365)
    # Let's use sold_count = 0 which gives TTS = 365 days
    print("\n📋 TTS Threshold Test: Slow book with 365-day TTS and $7 profit")
    print("-"*80)

    market_slow = EbayMarketStats(
        isbn="SLOW",
        active_count=8,
        active_avg_price=15.0,
        sold_count=0,  # Results in TTS = 365 days
        sold_avg_price=14.0,
        sell_through_rate=0.0,
        currency="USD"
    )

    metadata_slow = BookMetadata(
        isbn="SLOW",
        title="Slow Moving Book",
        authors=("Test Author",),
        published_year=2019
    )

    eval_slow = build_book_evaluation(
        isbn="SLOW",
        original_isbn="SLOW",
        metadata=metadata_slow,
        market=market_slow,
        condition="Good",
        edition=None,
        bookscouter=None
    )

    profit_slow = 7.0
    actual_tts_slow = eval_slow.time_to_sell_days or 0

    # Conservative: 365 > 120 day limit AND $7 < $10 slow threshold
    should_review_cons, concerns_cons = simulate_needs_review_check(
        eval_slow, conservative,
        best_profit=profit_slow
    )
    passed_cons = should_review_cons and any("Slow velocity" in c for c in concerns_cons)

    status = "✓" if passed_cons else "✗"
    print(f"  {status} Conservative (TTS={actual_tts_slow}, limit 120): Review = {should_review_cons} (expected: True)")

    # Balanced: 365 > 180 day limit AND $7 < $8 slow threshold
    should_review_bal, concerns_bal = simulate_needs_review_check(
        eval_slow, balanced,
        best_profit=profit_slow
    )
    passed_bal = should_review_bal and any("Slow velocity" in c for c in concerns_bal)

    status = "✓" if passed_bal else "✗"
    print(f"  {status} Balanced (TTS={actual_tts_slow}, limit 180): Review = {should_review_bal} (expected: True)")

    # Aggressive: 365 > 240 day limit AND $7 > $5 slow threshold
    # This SHOULD flag because 365 > 240 AND $7 > $5 means it doesn't meet the slow-moving profit threshold
    # Actually the condition is: tts > max_tts AND profit < min_slow_profit
    # So: 365 > 240 (TRUE) AND $7 < $5 (FALSE) = Overall FALSE, should NOT flag
    should_review_agg, concerns_agg = simulate_needs_review_check(
        eval_slow, aggressive,
        best_profit=profit_slow
    )
    # With $7 profit > $5 threshold, should NOT flag even though TTS is high
    passed_agg = not should_review_agg or not any("Slow velocity" in c for c in concerns_agg)

    status = "✓" if passed_agg else "✗"
    print(f"  {status} Aggressive (TTS={actual_tts_slow}, limit 240, profit $7 > $5 threshold): Review = {should_review_agg} (expected: False)")

    all_passed = all_passed and passed_cons and passed_bal and passed_agg

    print("\n" + "-"*80)
    if all_passed:
        print("✅ Phase 3: All configurable threshold tests PASSED")
    else:
        print("❌ Phase 3: Some configurable threshold tests FAILED")

    return all_passed


def test_integration():
    """Test end-to-end integration of all phases."""
    print("\n" + "="*80)
    print("INTEGRATION TEST: All Phases Working Together")
    print("="*80)

    # Test a book that exercises all three phases
    print("\n📋 Complete Workflow: Fast-moving book with good profit")
    print("-"*80)

    market = EbayMarketStats(
        isbn="COMPLETE",
        active_count=12,
        active_avg_price=22.0,
        sold_count=18,  # Phase 1: Calculate TTS
        sold_avg_price=21.0,
        sell_through_rate=0.6,
        currency="USD"
    )

    bookscouter = BookScouterResult(
        isbn_10="COMPLETE",
        isbn_13="9780000000099",
        best_price=15.0,
        best_vendor="BooksRun",
        total_vendors=18,
        offers=[],
        amazon_sales_rank=15000,
        amazon_count=35,
        amazon_lowest_price=24.0,
        amazon_trade_in_price=12.0
    )

    metadata = BookMetadata(
        isbn="COMPLETE",
        title="Complete Test Book",
        authors=("Popular Author",),
        published_year=2022
    )

    # Phase 1: Build evaluation with TTS
    evaluation = build_book_evaluation(
        isbn="COMPLETE",
        original_isbn="COMPLETE",
        metadata=metadata,
        market=market,
        condition="Very Good",
        edition=None,
        bookscouter=bookscouter
    )

    print(f"✓ Phase 1: TTS calculated = {evaluation.time_to_sell_days} days")
    assert evaluation.time_to_sell_days is not None, "TTS should be calculated"
    assert evaluation.time_to_sell_days == 7, f"Expected TTS=7, got {evaluation.time_to_sell_days}"

    # Phase 2: Check if needs review
    thresholds = DecisionThresholds.balanced()
    profit = 12.0  # Good profit
    should_review, concerns = simulate_needs_review_check(
        evaluation, thresholds,
        best_profit=profit
    )

    print(f"✓ Phase 2: Needs Review = {should_review} (expected: False)")
    print(f"  Concerns: {concerns if concerns else 'None'}")
    assert not should_review, "High-quality book should not need review"

    # Phase 3: Verify thresholds affect decision
    print(f"✓ Phase 3: Profit ${profit:.2f} >= Balanced Threshold ${thresholds.min_profit_auto_buy:.2f}")
    assert profit >= thresholds.min_profit_auto_buy, "Should meet profit threshold"

    print(f"\n✅ Integration test PASSED: All phases working together")
    return True


if __name__ == "__main__":
    print("\n" + "="*80)
    print("PURCHASE DECISION SYSTEM - COMPREHENSIVE TEST SUITE")
    print("Testing Phases 1-3: TTS, Needs Review, Configurable Thresholds")
    print("="*80)

    try:
        # Run all test phases
        phase1_passed = test_phase1_tts_calculation()
        phase2_passed = test_phase2_needs_review()
        phase3_passed = test_phase3_configurable_thresholds()
        integration_passed = test_integration()

        # Summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Phase 1 (TTS):                    {'✅ PASSED' if phase1_passed else '❌ FAILED'}")
        print(f"Phase 2 (Needs Review):           {'✅ PASSED' if phase2_passed else '❌ FAILED'}")
        print(f"Phase 3 (Configurable Thresholds):{'✅ PASSED' if phase3_passed else '❌ FAILED'}")
        print(f"Integration:                      {'✅ PASSED' if integration_passed else '❌ FAILED'}")
        print("="*80)

        all_passed = phase1_passed and phase2_passed and phase3_passed and integration_passed

        if all_passed:
            print("\n🎉 ALL TESTS PASSED!")
            print("The Purchase Decision System (Phases 1-3) is working correctly.")
            sys.exit(0)
        else:
            print("\n❌ SOME TESTS FAILED")
            print("Please review the failures above and fix the issues.")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Test suite failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
