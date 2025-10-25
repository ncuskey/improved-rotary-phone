#!/usr/bin/env python3
"""
Integration test for series-aware recommendations with database acceptance.

This test verifies that when you accept books into the database, they stop appearing
in the "go back for" recommendations.

Scenario:
1. Scan Book A (series) -> No recommendation
2. Scan Book B (same series) -> Recommends Book A
3. Accept Book B -> Book B added to database
4. Scan Book C (same series) -> Should only recommend Book A (not B, since it's accepted)
"""

from pathlib import Path
from tempfile import NamedTemporaryFile
from shared.models import BookMetadata, BookEvaluation


class MockDatabase:
    """Mock database to track accepted books."""
    def __init__(self):
        self.books = {}

    def fetch_book(self, isbn):
        """Return book if it exists in database, None otherwise."""
        return self.books.get(isbn)

    def add_book(self, isbn):
        """Simulate accepting a book."""
        self.books[isbn] = {"isbn": isbn, "accepted": True}


class MockBookService:
    """Mock BookService with database integration for testing."""
    def __init__(self):
        from isbn_lot_optimizer.recent_scans import RecentScansCache
        from shared.author_aliases import canonical_author as _canonical_author
        from shared.series_index import canonical_series as _canonical_series

        self.recent_scans = RecentScansCache(max_size=100)
        self.canonical_author = _canonical_author
        self.canonical_series = _canonical_series
        self.db = MockDatabase()

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

        # Filter out books that are already in the database (already accepted)
        matches_not_in_db = []
        for match in matches:
            if not self.db.fetch_book(match.isbn):
                matches_not_in_db.append(match)

        matches = matches_not_in_db

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
        """Track this scan in the recent scans cache."""
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

    def simulate_scan(self, isbn: str, title: str, author: str, series_name, series_position) -> BookEvaluation:
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

        # Apply series-aware enhancements
        self._enhance_evaluation_with_series_context(evaluation)
        self._track_recent_scan(evaluation)

        return evaluation

    def accept_book(self, isbn: str) -> None:
        """Simulate accepting a book (adding to database)."""
        self.db.add_book(isbn)


def test_acceptance_filtering():
    """Test that accepted books are not recommended."""
    print("\nTest: Accepted books filtered from recommendations")
    print("-" * 60)

    service = MockBookService()

    # Scan Book 1
    eval1 = service.simulate_scan(
        "9780439708180",
        "Harry Potter and the Sorcerer's Stone",
        "J.K. Rowling",
        "Harry Potter",
        1
    )
    print(f"Scan 1: {eval1.metadata.title} (Series #{eval1.metadata.series_index})")
    print(f"  In DB: No")
    print(f"  Recommendation: {eval1.justification}")
    assert len(eval1.justification) == 1, "First scan should have no series recommendation"
    print("  ✓ No recommendation (first book)")

    # Scan Book 2 (should recommend Book 1)
    eval2 = service.simulate_scan(
        "9780439064873",
        "Harry Potter and the Chamber of Secrets",
        "J.K. Rowling",
        "Harry Potter",
        2
    )
    print(f"\nScan 2: {eval2.metadata.title} (Series #{eval2.metadata.series_index})")
    print(f"  In DB: No")
    print(f"  Recommendation: {eval2.justification}")
    assert len(eval2.justification) == 2, "Should recommend Book 1"
    assert "#1" in eval2.justification[1], "Should mention Book #1"
    print("  ✓ Recommends Book 1")

    # Accept Book 2 into the database
    print(f"\n[ACTION] Accept Book 2 into database")
    service.accept_book("9780439064873")

    # Scan Book 3 (should only recommend Book 1, NOT Book 2)
    eval3 = service.simulate_scan(
        "9780439136365",
        "Harry Potter and the Prisoner of Azkaban",
        "J.K. Rowling",
        "Harry Potter",
        3
    )
    print(f"\nScan 3: {eval3.metadata.title} (Series #{eval3.metadata.series_index})")
    print(f"  Book 1 in DB: No")
    print(f"  Book 2 in DB: Yes")
    print(f"  Recommendation: {eval3.justification}")
    assert len(eval3.justification) == 2, "Should have recommendation"
    assert "another book" in eval3.justification[1], "Should mention 1 book (not 2)"
    assert "#1" in eval3.justification[1], "Should mention Book #1"
    assert "#2" not in eval3.justification[1], "Should NOT mention Book #2 (already accepted)"
    print("  ✓ Recommends only Book 1 (Book 2 filtered out)")

    # Accept Book 1
    print(f"\n[ACTION] Accept Book 1 into database")
    service.accept_book("9780439708180")

    # Scan Book 4 (should have NO recommendations - all previous books accepted)
    eval4 = service.simulate_scan(
        "9780439139595",
        "Harry Potter and the Goblet of Fire",
        "J.K. Rowling",
        "Harry Potter",
        4
    )
    print(f"\nScan 4: {eval4.metadata.title} (Series #{eval4.metadata.series_index})")
    print(f"  Book 1 in DB: Yes")
    print(f"  Book 2 in DB: Yes")
    print(f"  Book 3 in DB: No")
    print(f"  Recommendation: {eval4.justification}")
    assert len(eval4.justification) == 2, "Should recommend Book 3"
    assert "#3" in eval4.justification[1], "Should mention Book #3"
    print("  ✓ Recommends only Book 3 (Books 1 & 2 filtered out)")


def test_partial_acceptance():
    """Test mixed scenario with some books accepted, some not."""
    print("\nTest: Mixed acceptance scenario")
    print("-" * 60)

    service = MockBookService()

    # Scan books 1-4
    isbns = [
        ("9780439708180", "Book 1", 1),
        ("9780439064873", "Book 2", 2),
        ("9780439136365", "Book 3", 3),
        ("9780439139595", "Book 4", 4),
    ]

    for isbn, title, position in isbns:
        service.simulate_scan(isbn, title, "J.K. Rowling", "Harry Potter", position)
        print(f"  Scanned: {title}")

    # Accept books 2 and 4 (leave 1 and 3 unaccepted)
    service.accept_book("9780439064873")  # Book 2
    service.accept_book("9780439139595")  # Book 4
    print(f"\n  Accepted: Book 2, Book 4")
    print(f"  Not accepted: Book 1, Book 3")

    # Scan Book 5 (should only recommend Books 1 and 3)
    eval5 = service.simulate_scan(
        "9780439358071",
        "Harry Potter and the Order of the Phoenix",
        "J.K. Rowling",
        "Harry Potter",
        5
    )
    print(f"\nScan 5: {eval5.metadata.title}")
    print(f"  Recommendation: {eval5.justification}")
    assert len(eval5.justification) == 2, "Should have recommendation"
    assert "2 other books" in eval5.justification[1], "Should mention 2 books"
    assert "#1" in eval5.justification[1], "Should mention Book #1"
    assert "#3" in eval5.justification[1], "Should mention Book #3"
    assert "#2" not in eval5.justification[1], "Should NOT mention Book #2 (accepted)"
    assert "#4" not in eval5.justification[1], "Should NOT mention Book #4 (accepted)"
    print("  ✓ Recommends only Books 1 and 3 (Books 2 & 4 filtered out)")


if __name__ == "__main__":
    print("=" * 60)
    print("Series Recommendations with Acceptance Filtering")
    print("=" * 60)

    try:
        test_acceptance_filtering()
        test_partial_acceptance()

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        print("\nSummary:")
        print("  - Books already in database are filtered from recommendations")
        print("  - Only unaccepted books are suggested for 'go back for'")
        print("  - Mixed acceptance scenarios handled correctly")
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
