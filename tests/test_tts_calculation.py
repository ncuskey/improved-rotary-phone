#!/usr/bin/env python3
"""
Test script for Time-to-Sell (TTS) calculation.

Tests Phase 1 implementation of TTS metric.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.models import EbayMarketStats
from shared.probability import compute_time_to_sell


def test_compute_time_to_sell():
    """Test TTS calculation with various market conditions."""
    print("Testing compute_time_to_sell() function...")
    print("=" * 70)

    # Test 1: Very fast-moving book (30 sold in 90 days) - capped at 7 day minimum
    market = EbayMarketStats(
        isbn="TEST1",
        active_count=10,
        active_avg_price=15.0,
        sold_count=30,
        sold_avg_price=14.5,
        sell_through_rate=0.75,
        currency="USD"
    )
    tts = compute_time_to_sell(market)
    print(f"Test 1 - Very fast (30 sold): TTS = {tts} days (expected: 7, raw would be 3)")
    assert tts == 7, f"Expected 7 days (min cap), got {tts}"

    # Test 2: Fast-moving book (12 sold in 90 days) - gives 7.5, rounds to 7
    market.sold_count = 12
    tts = compute_time_to_sell(market)
    print(f"Test 2 - Fast (12 sold): TTS = {tts} days (expected: 7, raw 7.5)")
    assert tts == 7, f"Expected 7 days, got {tts}"

    # Test 2b: Fast-moving (9 sold) - 10 days
    market.sold_count = 9
    tts = compute_time_to_sell(market)
    print(f"Test 2b - Fast (9 sold): TTS = {tts} days (expected: 10)")
    assert tts == 10, f"Expected 10 days, got {tts}"

    # Test 3: Moderate velocity (3 sold in 90 days)
    market.sold_count = 3
    tts = compute_time_to_sell(market)
    print(f"Test 3 - Moderate (3 sold): TTS = {tts} days (expected: 30)")
    assert tts == 30, f"Expected 30 days, got {tts}"

    # Test 4: Slow-moving (1 sold in 90 days)
    market.sold_count = 1
    tts = compute_time_to_sell(market)
    print(f"Test 4 - Slow (1 sold): TTS = {tts} days (expected: 90)")
    assert tts == 90, f"Expected 90 days, got {tts}"

    # Test 5: Very slow (0 sold in 90 days) - capped at 365
    market.sold_count = 0
    tts = compute_time_to_sell(market)
    print(f"Test 5 - Very slow (0 sold): TTS = {tts} days (expected: 365)")
    assert tts == 365, f"Expected 365 days (max cap), got {tts}"

    # Test 6: Super fast (100 sold) - capped at 7 days minimum
    market.sold_count = 100
    tts = compute_time_to_sell(market)
    print(f"Test 6 - Super fast (100 sold): TTS = {tts} days (expected: 7)")
    assert tts == 7, f"Expected 7 days (min cap), got {tts}"

    # Test 7: No market data
    tts = compute_time_to_sell(None)
    print(f"Test 7 - No market data: TTS = {tts} (expected: None)")
    assert tts is None, f"Expected None, got {tts}"

    print("=" * 70)
    print("✓ All TTS calculation tests passed!")
    print()


def test_end_to_end():
    """Test TTS in a real book scan."""
    print("Testing end-to-end TTS integration...")
    print("=" * 70)

    from isbn_lot_optimizer.service import BookService

    # Initialize service
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    service = BookService(db_path)

    # Get a book from the database to test loading
    books = service.list_books()
    if books:
        book = books[0]
        print(f"Loaded book: {book.metadata.title}")
        print(f"  ISBN: {book.isbn}")
        print(f"  Time to Sell: {book.time_to_sell_days} days" if book.time_to_sell_days else "  Time to Sell: Not calculated (no market data)")

        # Check if TTS is in justification
        tts_in_justification = any("sell in" in reason.lower() for reason in book.justification)
        if book.time_to_sell_days:
            print(f"  TTS in justification: {'✓' if tts_in_justification else '✗'}")

        print("\n  Full justification:")
        for reason in book.justification:
            print(f"    • {reason}")

        print("=" * 70)
        print("✓ End-to-end test completed!")
    else:
        print("No books in database to test. Scan a book first.")
        print("=" * 70)

    print()


if __name__ == "__main__":
    try:
        test_compute_time_to_sell()
        test_end_to_end()
        print("\n🎉 Phase 1 TTS implementation complete and tested!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
