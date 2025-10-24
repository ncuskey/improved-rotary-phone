"""Recent scans tracking for series-aware recommendations."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, List, Optional


@dataclass
class RecentScan:
    """Represents a recently scanned book with series information."""
    isbn: str
    timestamp: datetime
    series_name: Optional[str] = None
    series_id: Optional[str] = None
    series_position: Optional[str] = None
    title: Optional[str] = None


class RecentScansCache:
    """
    Maintains a rolling cache of recently scanned ISBNs with series information.

    This cache enables series-aware recommendations by tracking what books have been
    scanned in the current session. When a new book is scanned that belongs to a series
    with previously scanned books, we can recommend going back to get those books for
    a series lot.
    """

    def __init__(self, max_size: int = 100):
        """
        Initialize the recent scans cache.

        Args:
            max_size: Maximum number of scans to track (default 100)
        """
        self.max_size = max_size
        self._scans: Deque[RecentScan] = deque(maxlen=max_size)
        self._isbn_index: dict[str, RecentScan] = {}

    def add_scan(
        self,
        isbn: str,
        series_name: Optional[str] = None,
        series_id: Optional[str] = None,
        series_position: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        """
        Add a scanned book to the cache.

        Args:
            isbn: The book's ISBN-13
            series_name: Name of the series (if applicable)
            series_id: Unique identifier for the series
            series_position: Position in series (e.g., "Book 1", "#2")
            title: Book title
        """
        # Remove existing entry if ISBN was scanned before
        if isbn in self._isbn_index:
            old_scan = self._isbn_index[isbn]
            try:
                self._scans.remove(old_scan)
            except ValueError:
                pass  # Already removed by deque max size

        # Create and add new scan
        scan = RecentScan(
            isbn=isbn,
            timestamp=datetime.now(),
            series_name=series_name,
            series_id=series_id,
            series_position=series_position,
            title=title,
        )
        self._scans.append(scan)
        self._isbn_index[isbn] = scan

        # Clean up index if it grows beyond max_size
        if len(self._isbn_index) > self.max_size:
            # Remove ISBNs that are no longer in the deque
            valid_isbns = {scan.isbn for scan in self._scans}
            self._isbn_index = {
                isbn: scan
                for isbn, scan in self._isbn_index.items()
                if isbn in valid_isbns
            }

    def get_series_matches(
        self,
        series_name: Optional[str] = None,
        series_id: Optional[str] = None,
    ) -> List[RecentScan]:
        """
        Find all recently scanned books in the same series.

        Args:
            series_name: Name of the series to search for
            series_id: Series ID to search for

        Returns:
            List of RecentScan objects matching the series, ordered by scan time (oldest first)
        """
        if not series_name and not series_id:
            return []

        matches = []
        for scan in self._scans:
            # Match by series_id first (more reliable), fall back to series_name
            if series_id and scan.series_id == series_id:
                matches.append(scan)
            elif series_name and scan.series_name and series_name.lower() == scan.series_name.lower():
                matches.append(scan)

        return matches

    def has_series_books(
        self,
        series_name: Optional[str] = None,
        series_id: Optional[str] = None,
    ) -> bool:
        """
        Check if any books in the specified series have been scanned recently.

        Args:
            series_name: Name of the series to check
            series_id: Series ID to check

        Returns:
            True if at least one book from the series was scanned recently
        """
        return len(self.get_series_matches(series_name, series_id)) > 0

    def get_all_scans(self) -> List[RecentScan]:
        """Get all recent scans, ordered by scan time (oldest first)."""
        return list(self._scans)

    def get_scan_by_isbn(self, isbn: str) -> Optional[RecentScan]:
        """Get a specific scan by ISBN."""
        return self._isbn_index.get(isbn)

    def clear(self) -> None:
        """Clear all scans from the cache."""
        self._scans.clear()
        self._isbn_index.clear()

    def size(self) -> int:
        """Get the current number of scans in the cache."""
        return len(self._scans)

    def __repr__(self) -> str:
        return f"RecentScansCache(size={self.size()}, max_size={self.max_size})"
