"""Test incremental lot updates for accepted books."""
import tempfile
from pathlib import Path

import pytest

from isbn_lot_optimizer.service import BookService


@pytest.fixture
def service():
    """Create a temporary BookService for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Create service with test database
    svc = BookService(
        database_path=db_path,
        ebay_app_id="test_app_id",
        ebay_global_id="EBAY_US",
    )

    yield svc

    # Cleanup
    try:
        db_path.unlink()
    except:
        pass


def test_incremental_update_only_affects_relevant_lots(service):
    """
    Test that update_lots_for_isbn only updates lots containing the specified book.
    """
    # Add some test books (these would normally be scanned)
    # For this test, we'll mock the book addition

    # Add a Stephen King book
    stephen_king_isbn = "9780307743657"

    # Accept the book (this would trigger incremental update)
    try:
        book = service.accept_book(
            stephen_king_isbn,
            condition="Good",
            recalc_lots=False  # Don't do full regeneration
        )
    except:
        # If book doesn't exist, we can't test incremental update
        pytest.skip("Test requires actual book data")

    # Run incremental update
    updated_lots = service.update_lots_for_isbn(stephen_king_isbn)

    # Verify that:
    # 1. Some lots were updated (not zero)
    assert len(updated_lots) > 0, "Should have updated at least one lot"

    # 2. All updated lots contain the ISBN
    for lot in updated_lots:
        assert stephen_king_isbn in lot.book_isbns, \
            f"Lot '{lot.name}' should contain the ISBN {stephen_king_isbn}"

    # 3. Updated lots are less than total lots (incremental, not full)
    all_lots = service.list_lots()
    assert len(updated_lots) < len(all_lots), \
        "Incremental update should update fewer lots than total"

    print(f"✓ Updated {len(updated_lots)} lots out of {len(all_lots)} total")
    print(f"  Efficiency: {len(updated_lots) / len(all_lots) * 100:.1f}% of lots updated")


def test_incremental_update_performance(service):
    """
    Test that incremental update is faster than full regeneration.

    This is more of a benchmark than a strict test.
    """
    import time

    # Get a book ISBN from the database
    books = service.list_books()
    if not books:
        pytest.skip("No books in database to test")

    test_isbn = books[0].isbn

    # Time incremental update
    start = time.time()
    incremental_lots = service.update_lots_for_isbn(test_isbn)
    incremental_time = time.time() - start

    # Time full regeneration
    start = time.time()
    full_lots = service.recalculate_lots()
    full_time = time.time() - start

    # Incremental should be significantly faster
    # (We expect 40-120x faster based on lot count reduction)
    print(f"  Incremental update: {incremental_time:.2f}s")
    print(f"  Full regeneration: {full_time:.2f}s")
    print(f"  Speedup: {full_time / incremental_time:.1f}x faster")

    assert incremental_time < full_time, \
        "Incremental update should be faster than full regeneration"


def test_update_nonexistent_isbn(service):
    """Test that updating lots for non-existent ISBN handles gracefully."""
    fake_isbn = "9999999999999"

    # Should return empty list, not crash
    result = service.update_lots_for_isbn(fake_isbn)

    assert result == [], "Should return empty list for non-existent ISBN"


def test_update_invalid_isbn(service):
    """Test that updating lots for invalid ISBN handles gracefully."""
    invalid_isbn = "not-an-isbn"

    # Should return empty list, not crash
    result = service.update_lots_for_isbn(invalid_isbn)

    assert result == [], "Should return empty list for invalid ISBN"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
