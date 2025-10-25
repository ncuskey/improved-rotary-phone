#!/usr/bin/env python3
"""
Integration test for series-aware recommendations during scanning.

This simulates scanning multiple books from the same series and verifies that
the justification includes recommendations to go back for previously scanned books.
"""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Mock the necessary components
from shared.models import BookMetadata, BookEvaluation


class MockBookService:
    """Mock BookService for testing series-aware recommendations."""
    def __init__(self):
        from isbn_lot_optimizer.recent_scans import RecentScansCache
        from shared.author_aliases import canonical_author as _canonical_author
        from shared.series_index import canonical_series as _canonical_series

        self.recent_scans = RecentScansCache(max_size=100)
        self.canonical_author = _canonical_author
        self.canonical_series = _canonical_series

    def _enhance_evaluation_with_series_context(self, evaluation: BookEvaluation) -> None:
        """Add series-aware justification (same logic as in service.py)."""
        metadata = getattr(evaluation, "metadata", None)
        if not metadata:
            return

        series_name = getattr(metadata, "series_name", None) or getattr(metadata, "series", None)
        if not series_name:
            return

        # Build series ID for matching
        series_id = None
        authors = getattr(metadata, "authors", ()) or ()
        author_display = authors[0].strip() if authors else None
        if author_display:
            canonical_author_value = self.canonical_author(author_display)
            canonical_series_value = self.canonical_series(series_name)
            if canonical_author_value and canonical_series_value:
                series_id = f"{canonical_author_value}:{canonical_series_value}"

        # Check if we have other books from this series in recent scans
        matches = self.recent_scans.get_series_matches(series_name=series_name, series_id=series_id)

        # Exclude the current book from matches
        isbn = getattr(evaluation, "isbn", None)
        matches = [m for m in matches if m.isbn != isbn]

        if matches:
            # Build justification message
            if len(matches) == 1:
                match = matches[0]
                position = f" ({match.series_position})" if match.series_position else ""
                justification_msg = (
                    f"Series lot opportunity: You recently scanned another book from the '{series_name}' series"
                    f"{position}. Consider going back to get it for a series lot."
                )
            else:
                positions = [m.series_position for m in matches if m.series_position]
                if positions:
                    positions_str = ", ".join(positions)
                    justification_msg = (
                        f"Series lot opportunity: You recently scanned {len(matches)} other books "
                        f"from the '{series_name}' series ({positions_str}). Consider going back to get them for a series lot."
                    )
                else:
                    justification_msg = (
                        f"Series lot opportunity: You recently scanned {len(matches)} other books "
                        f"from the '{series_name}' series. Consider going back to get them for a series lot."
                    )

            # Add to justification list
            existing_justification = list(evaluation.justification) if evaluation.justification else []
            existing_justification.append(justification_msg)
            evaluation.justification = tuple(existing_justification)

    def _track_recent_scan(self, evaluation: BookEvaluation) -> None:
        """Track this scan in the recent scans cache (same logic as in service.py)."""
        isbn = getattr(evaluation, "isbn", None)
        if not isbn:
            return

        metadata = getattr(evaluation, "metadata", None)
        if not metadata:
            return

        series_name = getattr(metadata, "series_name", None) or getattr(metadata, "series", None)
        series_position = getattr(metadata, "series_index", None)
        title = getattr(metadata, "title", None)

        # Create a series ID from canonical author + series name for better matching
        series_id = None
        if series_name:
            authors = getattr(metadata, "authors", ()) or ()
            author_display = authors[0].strip() if authors else None
            if author_display:
                canonical_author_value = self.canonical_author(author_display)
                canonical_series_value = self.canonical_series(series_name)
                if canonical_author_value and canonical_series_value:
                    series_id = f"{canonical_author_value}:{canonical_series_value}"

        # Format series position as string if available
        position_str = None
        if series_position is not None:
            if isinstance(series_position, (int, float)):
                position_str = f"#{int(series_position)}"
            else:
                position_str = str(series_position)

        self.recent_scans.add_scan(
            isbn=isbn,
            series_name=series_name,
            series_id=series_id,
            series_position=position_str,
            title=title,
        )

    def simulate_scan(self, isbn: str, title: str, author: str, series_name: Optional[str], series_position: Optional[int]) -> BookEvaluation:
        """Simulate scanning a book."""
        metadata = BookMetadata(
            isbn=isbn,
            title=title,
            authors=(author,),
            series_name=series_name,
            series_index=series_position,
        )

        evaluation = BookEvaluation(
            isbn=isbn,
            original_isbn=isbn,
            metadata=metadata,
            market=None,
            estimated_price=10.0,
            condition="Good",
            edition=None,
            rarity=None,
            probability_score=50.0,
            probability_label="MAYBE",
            justification=("Base justification",),
        )

        # Apply series-aware enhancements (same as in scan_isbn)
        self._enhance_evaluation_with_series_context(evaluation)
        self._track_recent_scan(evaluation)

        return evaluation


def test_harry_potter_series():
    """Test scanning multiple Harry Potter books."""
    print("\nTest 1: Harry Potter series scanning")
    print("-" * 60)

    service = MockBookService()

    # Scan book 1
    eval1 = service.simulate_scan(
        "9780439708180",
        "Harry Potter and the Sorcerer's Stone",
        "J.K. Rowling",
        "Harry Potter",
        1
    )
    print(f"Scan 1: {eval1.metadata.title}")
    print(f"  Justification: {eval1.justification}")
    assert len(eval1.justification) == 1, "First scan should have no series recommendation"
    print("  ✓ No series recommendation (first book)")

    # Scan book 2
    eval2 = service.simulate_scan(
        "9780439064873",
        "Harry Potter and the Chamber of Secrets",
        "J.K. Rowling",
        "Harry Potter",
        2
    )
    print(f"\nScan 2: {eval2.metadata.title}")
    print(f"  Justification: {eval2.justification}")
    assert len(eval2.justification) == 2, "Second scan should have series recommendation"
    assert "Series lot opportunity" in eval2.justification[1], "Should mention series lot"
    assert "#1" in eval2.justification[1], "Should mention book #1"
    print("  ✓ Series recommendation detected (mentions book #1)")

    # Scan book 3
    eval3 = service.simulate_scan(
        "9780439136365",
        "Harry Potter and the Prisoner of Azkaban",
        "J.K. Rowling",
        "Harry Potter",
        3
    )
    print(f"\nScan 3: {eval3.metadata.title}")
    print(f"  Justification: {eval3.justification}")
    assert len(eval3.justification) == 2, "Third scan should have series recommendation"
    assert "Series lot opportunity" in eval3.justification[1], "Should mention series lot"
    assert "2 other books" in eval3.justification[1], "Should mention 2 books"
    assert "#1" in eval3.justification[1] and "#2" in eval3.justification[1], "Should mention positions"
    print("  ✓ Series recommendation detected (mentions 2 books: #1, #2)")


def test_mixed_series():
    """Test scanning books from different series."""
    print("\nTest 2: Mixed series scanning")
    print("-" * 60)

    service = MockBookService()

    # Scan Lord of the Rings book 1
    eval1 = service.simulate_scan(
        "9780544003415",
        "The Fellowship of the Ring",
        "J.R.R. Tolkien",
        "The Lord of the Rings",
        1
    )
    print(f"Scan 1: {eval1.metadata.title}")
    assert len(eval1.justification) == 1, "Should have no series recommendation"
    print("  ✓ No series recommendation")

    # Scan a different series
    eval2 = service.simulate_scan(
        "9780345339706",
        "The Hobbit",
        "J.R.R. Tolkien",
        "Middle Earth",
        1
    )
    print(f"\nScan 2: {eval2.metadata.title}")
    assert len(eval2.justification) == 1, "Different series - should have no recommendation"
    print("  ✓ No series recommendation (different series)")

    # Scan Lord of the Rings book 2
    eval3 = service.simulate_scan(
        "9780544003422",
        "The Two Towers",
        "J.R.R. Tolkien",
        "The Lord of the Rings",
        2
    )
    print(f"\nScan 3: {eval3.metadata.title}")
    assert len(eval3.justification) == 2, "Should detect LOTR book 1"
    assert "Series lot opportunity" in eval3.justification[1], "Should mention series lot"
    assert "The Lord of the Rings" in eval3.justification[1], "Should mention series name"
    print("  ✓ Series recommendation detected (LOTR book 1)")


def test_cache_overflow():
    """Test that cache respects the 100-item limit."""
    print("\nTest 3: Cache overflow handling")
    print("-" * 60)

    service = MockBookService()

    # Add 101 books from different series
    for i in range(101):
        service.simulate_scan(
            f"978{i:010d}",
            f"Book {i}",
            "Author X",
            f"Series {i}",
            1
        )

    assert service.recent_scans.size() == 100, f"Expected 100, got {service.recent_scans.size()}"
    print(f"  ✓ Cache size limited to 100 (scanned 101 books)")

    # First book should be evicted
    first_scan = service.recent_scans.get_scan_by_isbn("9780000000000")
    assert first_scan is None, "First scan should be evicted"
    print("  ✓ Oldest scan evicted")

    # Last book should still be there
    last_scan = service.recent_scans.get_scan_by_isbn("9780000000100")
    assert last_scan is not None, "Last scan should be present"
    print("  ✓ Most recent scan retained")


def test_no_series_info():
    """Test that books without series info don't cause errors."""
    print("\nTest 4: Books without series information")
    print("-" * 60)

    service = MockBookService()

    # Scan books without series info
    eval1 = service.simulate_scan(
        "9780141439518",
        "Pride and Prejudice",
        "Jane Austen",
        None,
        None
    )
    print(f"Scan 1: {eval1.metadata.title}")
    assert len(eval1.justification) == 1, "Should work fine without series"
    print("  ✓ No errors for non-series book")

    eval2 = service.simulate_scan(
        "9780142437247",
        "Moby Dick",
        "Herman Melville",
        None,
        None
    )
    print(f"\nScan 2: {eval2.metadata.title}")
    assert len(eval2.justification) == 1, "Should work fine without series"
    print("  ✓ No errors for another non-series book")


if __name__ == "__main__":
    print("=" * 60)
    print("Series-Aware Recommendations Integration Test")
    print("=" * 60)

    try:
        test_harry_potter_series()
        test_mixed_series()
        test_cache_overflow()
        test_no_series_info()

        print("\n" + "=" * 60)
        print("✓ All integration tests passed!")
        print("=" * 60)
        print("\nSummary:")
        print("  - Series recommendations work correctly")
        print("  - Multiple books from same series are detected")
        print("  - Different series are tracked independently")
        print("  - Cache respects 100-item limit")
        print("  - Non-series books handled gracefully")
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
