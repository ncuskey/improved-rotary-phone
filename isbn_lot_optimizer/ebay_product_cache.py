"""eBay Product ID (ePID) caching for auto-populated Item Specifics.

This module manages the discovery and storage of eBay Product IDs (ePIDs) which
enable product-based listings with automatically populated Item Specifics.

When an ePID is available for a book's ISBN, eBay automatically fills in:
- Product title
- Author
- Publisher
- Publication year
- Number of pages
- Genre
- And many other catalog attributes

This provides perfect parity with eBay's web interface without needing the Buy API.

Usage:
    from isbn_lot_optimizer.ebay_product_cache import EbayProductCache

    cache = EbayProductCache(db_path)

    # Store an ePID discovered during keyword analysis
    cache.store_epid(
        isbn="9780553381689",
        epid="2266091",
        product_title="A Game of Thrones",
        product_url="https://www.ebay.com/p/2266091"
    )

    # Retrieve ePID for listing creation
    epid = cache.get_epid("9780553381689")
    if epid:
        # Use product-based listing (auto-populated)
    else:
        # Fallback to manual Item Specifics
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EbayProduct:
    """Cached eBay product information."""
    isbn: str
    epid: str
    product_title: Optional[str]
    product_url: Optional[str]
    category_id: Optional[str]
    discovered_at: str
    last_verified: Optional[str]
    times_used: int
    success_count: int
    failure_count: int
    notes: Optional[str]


class EbayProductCache:
    """Cache for eBay Product IDs (ePIDs) discovered during keyword analysis."""

    def __init__(self, db_path: Path):
        """
        Initialize the ePID cache.

        Args:
            db_path: Path to catalog database containing ebay_products table
        """
        self.db_path = Path(db_path)

        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_epid(self, isbn: str) -> Optional[str]:
        """
        Get cached ePID for an ISBN.

        Args:
            isbn: ISBN-13 to look up

        Returns:
            ePID string if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT epid FROM ebay_products WHERE isbn = ?",
                (isbn,)
            )
            row = cursor.fetchone()

        if row:
            logger.debug(f"Found cached ePID for {isbn}: {row['epid']}")
            return row['epid']

        logger.debug(f"No cached ePID found for {isbn}")
        return None

    def get_product(self, isbn: str) -> Optional[EbayProduct]:
        """
        Get full cached product information for an ISBN.

        Args:
            isbn: ISBN-13 to look up

        Returns:
            EbayProduct if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ebay_products WHERE isbn = ?",
                (isbn,)
            )
            row = cursor.fetchone()

        if not row:
            return None

        return EbayProduct(
            isbn=row['isbn'],
            epid=row['epid'],
            product_title=row['product_title'],
            product_url=row['product_url'],
            category_id=row['category_id'],
            discovered_at=row['discovered_at'],
            last_verified=row['last_verified'],
            times_used=row['times_used'] or 0,
            success_count=row['success_count'] or 0,
            failure_count=row['failure_count'] or 0,
            notes=row['notes'],
        )

    def store_epid(
        self,
        isbn: str,
        epid: str,
        product_title: Optional[str] = None,
        product_url: Optional[str] = None,
        category_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """
        Store an ePID discovered during keyword analysis.

        Args:
            isbn: ISBN-13
            epid: eBay Product ID
            product_title: Product title from eBay
            product_url: URL to product page (e.g., https://www.ebay.com/p/2266091)
            category_id: eBay category ID
            notes: Any notes about this ePID
        """
        with self._get_connection() as conn:
            # Use INSERT OR REPLACE to handle duplicates
            conn.execute(
                """
                INSERT OR REPLACE INTO ebay_products (
                    isbn, epid, product_title, product_url, category_id,
                    discovered_at, notes
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (isbn, epid, product_title, product_url, category_id, notes)
            )
            conn.commit()

        logger.info(f"Cached ePID for {isbn}: {epid}")

    def mark_used(self, isbn: str, success: bool = True) -> None:
        """
        Mark an ePID as used in a listing creation attempt.

        Args:
            isbn: ISBN-13
            success: Whether the listing creation succeeded
        """
        with self._get_connection() as conn:
            if success:
                conn.execute(
                    """
                    UPDATE ebay_products
                    SET times_used = times_used + 1,
                        success_count = success_count + 1,
                        last_verified = CURRENT_TIMESTAMP
                    WHERE isbn = ?
                    """,
                    (isbn,)
                )
            else:
                conn.execute(
                    """
                    UPDATE ebay_products
                    SET times_used = times_used + 1,
                        failure_count = failure_count + 1
                    WHERE isbn = ?
                    """,
                    (isbn,)
                )
            conn.commit()

    def invalidate(self, isbn: str) -> None:
        """
        Remove an ePID from cache (e.g., if it stopped working).

        Args:
            isbn: ISBN-13 to invalidate
        """
        with self._get_connection() as conn:
            conn.execute("DELETE FROM ebay_products WHERE isbn = ?", (isbn,))
            conn.commit()

        logger.info(f"Invalidated ePID cache for {isbn}")

    def clear_old_entries(self, days: int = 90) -> int:
        """
        Clear ePID entries older than specified days.

        ePIDs can change over time as eBay updates their catalog, so it's good
        to periodically re-discover them.

        Args:
            days: Remove entries older than this many days

        Returns:
            Number of entries removed
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM ebay_products
                WHERE discovered_at < ? AND last_verified IS NULL
                """,
                (cutoff_date,)
            )
            deleted_count = cursor.rowcount
            conn.commit()

        if deleted_count > 0:
            logger.info(f"Cleared {deleted_count} old ePID entries (>{days} days)")

        return deleted_count

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total_entries,
                    SUM(times_used) as total_uses,
                    SUM(success_count) as total_successes,
                    SUM(failure_count) as total_failures,
                    AVG(success_count * 1.0 / NULLIF(times_used, 0)) as success_rate
                FROM ebay_products
            """)
            row = cursor.fetchone()

        return {
            'total_entries': row['total_entries'] or 0,
            'total_uses': row['total_uses'] or 0,
            'total_successes': row['total_successes'] or 0,
            'total_failures': row['total_failures'] or 0,
            'success_rate': row['success_rate'] or 0.0,
        }

    def find_by_epid(self, epid: str) -> list[str]:
        """
        Find all ISBNs associated with an ePID.

        This can help identify different editions of the same book.

        Args:
            epid: eBay Product ID

        Returns:
            List of ISBNs sharing this ePID
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT isbn FROM ebay_products WHERE epid = ?",
                (epid,)
            )
            rows = cursor.fetchall()

        return [row['isbn'] for row in rows]
