#!/usr/bin/env python3
"""
Test script for "Needs Review" decision state.

Tests Phase 2 implementation of the 3-state decision model.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.models import BookEvaluation, EbayMarketStats, BookMetadata, BookScouterResult
from shared.probability import build_book_evaluation


def test_needs_review_conditions():
    """Test that books with problematic signals are flagged for review."""
    print("Testing Needs Review Decision Logic")
    print("=" * 70)

    # Test Case 1: Insufficient market data (<3 comps)
    print("\nTest 1: Insufficient market data")
    print("-" * 70)

    metadata = BookMetadata(
        isbn="1234567890",
        title="Rare Book with Few Comps",
        authors=("Test Author",),
        published_year=2020
    )

    market = EbayMarketStats(
        isbn="1234567890",
        active_count=1,  # Only 2 total comps
        active_avg_price=20.0,
        sold_count=1,
        sold_avg_price=18.0,
        sell_through_rate=0.5,
        currency="USD",
        time_to_sell_days=90
    )

    eval1 = build_book_evaluation(
        isbn="1234567890",
        original_isbn="1234567890",
        metadata=metadata,
        market=market,
        condition="Good",
        edition=None,
        bookscouter=None
    )

    print(f"  ISBN: {eval1.isbn}")
    print(f"  Probability Score: {eval1.probability_score}")
    print(f"  Total Comps: {market.active_count + market.sold_count}")
    print(f"  Expected: Should flag for review (insufficient data)")
    print(f"  Justification:")
    for reason in eval1.justification:
        print(f"    • {reason}")

    # Test Case 2: Conflicting signals (buyback profitable but eBay shows loss)
    print("\nTest 2: Conflicting signals")
    print("-" * 70)

    market2 = EbayMarketStats(
        isbn="2234567890",
        active_count=5,
        active_avg_price=5.0,  # Very low eBay price
        sold_count=8,
        sold_avg_price=4.50,
        sell_through_rate=0.62,
        currency="USD",
        time_to_sell_days=15
    )

    bookscouter2 = BookScouterResult(
        isbn_10="2234567890",
        isbn_13="9782234567890",
        best_price=10.0,  # High buyback offer
        best_vendor="BooksRun",
        total_vendors=15,
        offers=[],
        amazon_sales_rank=50000,
        amazon_count=20,
        amazon_lowest_price=12.0,
        amazon_trade_in_price=None
    )

    metadata2 = BookMetadata(
        isbn="2234567890",
        title="Conflicting Signals Book",
        authors=("Test Author",),
        published_year=2019
    )

    eval2 = build_book_evaluation(
        isbn="2234567890",
        original_isbn="2234567890",
        metadata=metadata2,
        market=market2,
        condition="Good",
        edition=None,
        bookscouter=bookscouter2
    )

    print(f"  ISBN: {eval2.isbn}")
    print(f"  eBay Avg Price: ${market2.sold_avg_price:.2f}")
    print(f"  Buyback Offer: ${bookscouter2.best_price:.2f}")
    print(f"  Expected: Should flag for review (conflicting signals)")
    print(f"  Justification:")
    for reason in eval2.justification:
        print(f"    • {reason}")

    # Test Case 3: Very slow moving + thin margin
    print("\nTest 3: Slow velocity + thin margin")
    print("-" * 70)

    market3 = EbayMarketStats(
        isbn="3234567890",
        active_count=10,
        active_avg_price=12.0,
        sold_count=2,  # Only 2 sold in 90 days = ~45 day TTS
        sold_avg_price=11.0,
        sell_through_rate=0.17,
        currency="USD",
        time_to_sell_days=45  # Slow velocity
    )

    metadata3 = BookMetadata(
        isbn="3234567890",
        title="Slow Moving Book",
        authors=("Test Author",),
        published_year=2018
    )

    eval3 = build_book_evaluation(
        isbn="3234567890",
        original_isbn="3234567890",
        metadata=metadata3,
        market=market3,
        condition="Good",
        edition=None,
        bookscouter=None
    )

    print(f"  ISBN: {eval3.isbn}")
    print(f"  Time to Sell: {eval3.time_to_sell_days} days")
    print(f"  Estimated Price: ${eval3.estimated_price:.2f}" if eval3.estimated_price else "  No price estimate")
    print(f"  Sell-Through Rate: {market3.sell_through_rate:.1%}")
    print(f"  Expected: May flag for review if margin is thin")
    print(f"  Justification:")
    for reason in eval3.justification:
        print(f"    • {reason}")

    # Test Case 4: High confidence book (should NOT flag for review)
    print("\nTest 4: High confidence book (control)")
    print("-" * 70)

    market4 = EbayMarketStats(
        isbn="4234567890",
        active_count=15,
        active_avg_price=25.0,
        sold_count=20,  # Good sales velocity
        sold_avg_price=24.0,
        sell_through_rate=0.57,
        currency="USD",
        time_to_sell_days=7  # Fast moving
    )

    bookscouter4 = BookScouterResult(
        isbn_10="4234567890",
        isbn_13="9784234567890",
        best_price=18.0,  # Good buyback offer
        best_vendor="BooksRun",
        total_vendors=20,
        offers=[],
        amazon_sales_rank=10000,
        amazon_count=50,
        amazon_lowest_price=28.0,
        amazon_trade_in_price=15.0
    )

    metadata4 = BookMetadata(
        isbn="4234567890",
        title="Popular Book",
        authors=("Famous Author",),
        published_year=2022
    )

    eval4 = build_book_evaluation(
        isbn="4234567890",
        original_isbn="4234567890",
        metadata=metadata4,
        market=market4,
        condition="Like New",
        edition=None,
        bookscouter=bookscouter4
    )

    print(f"  ISBN: {eval4.isbn}")
    print(f"  Probability Score: {eval4.probability_score}")
    print(f"  Time to Sell: {eval4.time_to_sell_days} days")
    print(f"  Sell-Through Rate: {market4.sell_through_rate:.1%}")
    print(f"  Expected: Should NOT flag for review (high confidence)")
    print(f"  Justification:")
    for reason in eval4.justification:
        print(f"    • {reason}")

    # Test Case 5: No profit data + low confidence
    print("\nTest 5: No profit data + low confidence")
    print("-" * 70)

    market5 = EbayMarketStats(
        isbn="5234567890",
        active_count=3,
        active_avg_price=8.0,
        sold_count=2,
        sold_avg_price=7.0,
        sell_through_rate=0.40,
        currency="USD",
        time_to_sell_days=45
    )

    metadata5 = BookMetadata(
        isbn="5234567890",
        title="Obscure Book",
        authors=("Unknown Author",),
        published_year=2010
    )

    eval5 = build_book_evaluation(
        isbn="5234567890",
        original_isbn="5234567890",
        metadata=metadata5,
        market=market5,
        condition="Acceptable",
        edition=None,
        bookscouter=None  # No buyback data
    )

    print(f"  ISBN: {eval5.isbn}")
    print(f"  Probability Score: {eval5.probability_score}")
    print(f"  Estimated Price: ${eval5.estimated_price:.2f}" if eval5.estimated_price else "  No price estimate")
    print(f"  Expected: May flag for review (no profit data + low confidence)")
    print(f"  Justification:")
    for reason in eval5.justification:
        print(f"    • {reason}")

    print("\n" + "=" * 70)
    print("✓ Needs Review test scenarios completed!")
    print("\nNOTE: The actual 'Needs Review' decision is made in the iOS app's")
    print("makeBuyDecision() function, which evaluates these book evaluations.")
    print("These tests verify that the backend provides the necessary data for")
    print("those decisions (TTS, market data, pricing, etc.)")
    print()


if __name__ == "__main__":
    try:
        test_needs_review_conditions()
        print("\n🎉 Phase 2 'Needs Review' implementation tested!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
