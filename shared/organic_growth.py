"""
Organic Growth System for Unified Training Database.

This module implements automatic synchronization of scanned books
from catalog.db to metadata_cache.db (unified training database).

Key Features:
- Auto-sync: Every scanned book is added to training database
- Deduplication: Check unified_index before enriching
- Quality Scoring: Calculate training_quality_score
- Training Eligibility: Set in_training flag based on quality gates
- Staleness Tracking: Track when data was last fetched

Data Flow:
    Scan ISBN → catalog.db → auto_sync → metadata_cache.db
             ↓
    Check unified_index (dedup) → Enrich if needed → Update quality score
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class UnifiedIndexEntry:
    """Entry in unified_index.db tracking ISBN locations."""
    isbn: str
    in_training: bool = False  # In metadata_cache.db
    in_cache: bool = False  # Legacy flag
    training_updated: Optional[str] = None
    cache_updated: Optional[str] = None
    quality_score: float = 0.0
    last_checked: Optional[str] = None


class OrganicGrowthManager:
    """
    Manage organic growth of unified training database.

    Responsibilities:
    1. Auto-sync scanned books to metadata_cache.db
    2. Deduplication via unified_index.db
    3. Calculate training quality scores
    4. Set in_training eligibility flag
    5. Track data freshness
    """

    # Quality gate thresholds
    MIN_COMPS_FOR_TRAINING = 8  # Minimum eBay sold comps
    MIN_PRICE_FOR_TRAINING = 5.0  # Minimum median price
    MIN_QUALITY_SCORE = 0.6  # Minimum composite quality score
    STALENESS_DAYS = 30  # Days before data is considered stale

    def __init__(
        self,
        metadata_cache_path: Optional[Path] = None,
        unified_index_path: Optional[Path] = None
    ):
        """
        Initialize organic growth manager.

        Args:
            metadata_cache_path: Path to metadata_cache.db
            unified_index_path: Path to unified_index.db
        """
        if metadata_cache_path is None:
            metadata_cache_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'
        if unified_index_path is None:
            unified_index_path = Path.home() / '.isbn_lot_optimizer' / 'unified_index.db'

        self.metadata_cache_path = Path(metadata_cache_path)
        self.unified_index_path = Path(unified_index_path)

        # Ensure unified_index exists
        self._init_unified_index()

    def _init_unified_index(self):
        """Initialize unified_index.db if it doesn't exist."""
        self.unified_index_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.unified_index_path))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS isbn_index (
                isbn TEXT PRIMARY KEY,
                in_training INTEGER DEFAULT 0,
                in_cache INTEGER DEFAULT 0,
                training_updated TEXT,
                cache_updated TEXT,
                quality_score REAL DEFAULT 0.0,
                last_checked TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_in_training
            ON isbn_index(in_training)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_quality_score
            ON isbn_index(quality_score DESC)
        ''')

        conn.commit()
        conn.close()

    def sync_book_to_training_db(self, book_data: Dict[str, Any]) -> bool:
        """
        Sync a book from catalog.db to metadata_cache.db (training database).

        This is called automatically when a book is scanned or updated.

        Args:
            book_data: Dict containing book fields from catalog.db

        Returns:
            True if synced successfully, False otherwise
        """
        isbn = book_data.get('isbn')
        if not isbn:
            logger.warning("Cannot sync book without ISBN")
            return False

        try:
            # Calculate training quality score
            quality_score = self.calculate_training_quality_score(book_data)

            # Determine if eligible for training
            in_training = self._is_eligible_for_training(book_data, quality_score)

            # Insert or update in metadata_cache.db
            conn = sqlite3.connect(str(self.metadata_cache_path))
            cursor = conn.cursor()

            # Prepare all fields
            insert_data = {
                'isbn': isbn,
                'title': book_data.get('title'),
                'authors': book_data.get('authors'),
                'publisher': book_data.get('publisher'),
                'publication_year': book_data.get('publication_year'),
                'binding': book_data.get('binding'),
                'page_count': book_data.get('page_count'),
                'language': book_data.get('language'),
                'isbn13': book_data.get('isbn13'),
                'isbn10': book_data.get('isbn10'),
                'thumbnail_url': book_data.get('thumbnail_url'),
                'description': book_data.get('description'),
                'source': book_data.get('source', 'catalog_sync'),

                # Market data
                'estimated_price': book_data.get('estimated_price'),
                'price_reference': book_data.get('price_reference'),
                'rarity': book_data.get('rarity'),
                'probability_label': book_data.get('probability_label'),
                'probability_score': book_data.get('probability_score'),

                # eBay market data
                'sell_through': book_data.get('sell_through'),
                'ebay_active_count': book_data.get('ebay_active_count'),
                'ebay_sold_count': book_data.get('ebay_sold_count'),
                'ebay_currency': book_data.get('ebay_currency', 'USD'),

                # Book attributes
                'cover_type': book_data.get('cover_type'),
                'signed': 1 if book_data.get('signed') else 0,
                'printing': book_data.get('printing'),

                # Sold comps
                'time_to_sell_days': book_data.get('time_to_sell_days'),
                'sold_comps_count': book_data.get('sold_comps_count'),
                'sold_comps_min': book_data.get('sold_comps_min'),
                'sold_comps_median': book_data.get('sold_comps_median'),
                'sold_comps_max': book_data.get('sold_comps_max'),
                'sold_comps_is_estimate': book_data.get('sold_comps_is_estimate', 0),
                'sold_comps_source': book_data.get('sold_comps_source'),

                # JSON blobs
                'market_json': json.dumps(book_data.get('market_json', {})) if isinstance(book_data.get('market_json'), dict) else book_data.get('market_json'),
                'booksrun_json': json.dumps(book_data.get('booksrun_json', {})) if isinstance(book_data.get('booksrun_json'), dict) else book_data.get('booksrun_json'),
                'bookscouter_json': json.dumps(book_data.get('bookscouter_json', {})) if isinstance(book_data.get('bookscouter_json'), dict) else book_data.get('bookscouter_json'),

                # Training quality tracking
                'training_quality_score': quality_score,
                'in_training': 1 if in_training else 0,
                'market_fetched_at': book_data.get('market_fetched_at'),
                'metadata_fetched_at': book_data.get('metadata_fetched_at'),
                'last_enrichment_at': datetime.now().isoformat(),
            }

            # Build INSERT OR REPLACE query
            columns = ', '.join(insert_data.keys())
            placeholders = ', '.join(['?' for _ in insert_data])
            values = list(insert_data.values())

            cursor.execute(f'''
                INSERT OR REPLACE INTO cached_books ({columns})
                VALUES ({placeholders})
            ''', values)

            conn.commit()
            conn.close()

            # Update unified_index
            self._update_unified_index(isbn, quality_score, in_training)

            logger.info(f"Synced {isbn} to training DB (quality={quality_score:.2f}, in_training={in_training})")
            return True

        except Exception as e:
            logger.error(f"Error syncing book {isbn} to training DB: {e}")
            return False

    def calculate_training_quality_score(self, book_data: Dict[str, Any]) -> float:
        """
        Calculate training quality score based on data completeness.

        Scoring:
        - eBay comps quality: 0-70 points (0.7)
          - 20+ comps: 70 points
          - 8-19 comps: 40 points
          - <8 comps: 0 points

        - Price quality: 0-30 points (0.3)
          - $15+ median: 30 points
          - $5-14 median: 15 points
          - <$5 median: 0 points

        Total: 0.0 to 1.0

        Args:
            book_data: Dict containing book fields

        Returns:
            Quality score from 0.0 to 1.0
        """
        score = 0.0

        # eBay comp quality (0-70 points)
        sold_comps_count = book_data.get('sold_comps_count', 0) or 0
        if sold_comps_count >= 20:
            score += 0.7
        elif sold_comps_count >= 8:
            score += 0.4

        # Price threshold (0-30 points)
        median_price = book_data.get('sold_comps_median', 0) or 0
        if median_price >= 15:
            score += 0.3
        elif median_price >= 5:
            score += 0.15

        return min(score, 1.0)

    def _is_eligible_for_training(self, book_data: Dict[str, Any], quality_score: float) -> bool:
        """
        Determine if book is eligible for ML training.

        Criteria:
        - sold_comps_count >= 8
        - sold_comps_median >= $5
        - training_quality_score >= 0.6

        Args:
            book_data: Dict containing book fields
            quality_score: Pre-calculated quality score

        Returns:
            True if eligible for training, False otherwise
        """
        sold_comps_count = book_data.get('sold_comps_count', 0) or 0
        median_price = book_data.get('sold_comps_median', 0) or 0

        return (
            sold_comps_count >= self.MIN_COMPS_FOR_TRAINING
            and median_price >= self.MIN_PRICE_FOR_TRAINING
            and quality_score >= self.MIN_QUALITY_SCORE
        )

    def should_enrich(self, isbn: str) -> bool:
        """
        Check if ISBN should be enriched (fetch market data).

        Reasons to enrich:
        1. Not in unified_index (new ISBN)
        2. Data is stale (>30 days old)
        3. Quality score is low (<0.5)

        Args:
            isbn: ISBN to check

        Returns:
            True if should enrich, False if skip
        """
        try:
            conn = sqlite3.connect(str(self.unified_index_path))
            cursor = conn.cursor()

            cursor.execute('''
                SELECT training_updated, quality_score
                FROM isbn_index
                WHERE isbn = ?
            ''', (isbn,))

            row = cursor.fetchone()
            conn.close()

            if not row:
                # New ISBN, always enrich
                return True

            training_updated, quality_score = row

            # Check staleness
            if training_updated:
                updated_dt = datetime.fromisoformat(training_updated)
                if datetime.now() - updated_dt > timedelta(days=self.STALENESS_DAYS):
                    return True  # Stale, re-enrich
            else:
                return True  # Never enriched

            # Check quality
            if quality_score and quality_score < 0.5:
                return True  # Low quality, needs more data

            return False  # Already have good data, skip

        except Exception as e:
            logger.error(f"Error checking should_enrich for {isbn}: {e}")
            return True  # On error, enrich to be safe

    def _update_unified_index(self, isbn: str, quality_score: float, in_training: bool):
        """Update unified_index.db with latest ISBN status."""
        try:
            conn = sqlite3.connect(str(self.unified_index_path))
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO isbn_index (
                    isbn, in_training, quality_score, training_updated, last_checked
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                isbn,
                1 if in_training else 0,
                quality_score,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating unified_index for {isbn}: {e}")

    def get_training_stats(self) -> Dict[str, Any]:
        """
        Get statistics about training database.

        Returns:
            Dict with training database stats
        """
        try:
            conn = sqlite3.connect(str(self.metadata_cache_path))
            cursor = conn.cursor()

            # Total books
            cursor.execute('SELECT COUNT(*) FROM cached_books')
            total = cursor.fetchone()[0]

            # Training eligible
            cursor.execute('SELECT COUNT(*) FROM cached_books WHERE in_training = 1')
            training_eligible = cursor.fetchone()[0]

            # Average quality
            cursor.execute('SELECT AVG(training_quality_score) FROM cached_books')
            avg_quality = cursor.fetchone()[0] or 0.0

            # Quality distribution
            cursor.execute('''
                SELECT
                    CASE
                        WHEN training_quality_score >= 0.8 THEN 'Excellent (0.8-1.0)'
                        WHEN training_quality_score >= 0.6 THEN 'Good (0.6-0.8)'
                        WHEN training_quality_score >= 0.4 THEN 'Fair (0.4-0.6)'
                        ELSE 'Poor (0.0-0.4)'
                    END as quality_tier,
                    COUNT(*) as count
                FROM cached_books
                GROUP BY quality_tier
                ORDER BY quality_tier DESC
            ''')
            quality_distribution = dict(cursor.fetchall())

            # Stale data (>30 days)
            cursor.execute('''
                SELECT COUNT(*) FROM cached_books
                WHERE in_training = 1
                  AND (market_fetched_at IS NULL
                       OR market_fetched_at < datetime('now', '-30 days'))
            ''')
            stale_count = cursor.fetchone()[0]

            conn.close()

            return {
                'total_books': total,
                'training_eligible': training_eligible,
                'training_percentage': (training_eligible / total * 100) if total > 0 else 0,
                'avg_quality_score': avg_quality,
                'quality_distribution': quality_distribution,
                'stale_training_data': stale_count
            }

        except Exception as e:
            logger.error(f"Error getting training stats: {e}")
            return {}

    def find_books_needing_enrichment(self, limit: int = 100) -> list[str]:
        """
        Find ISBNs that need enrichment.

        Returns books that:
        - Have never been enriched (market_fetched_at IS NULL)
        - Have stale data (>30 days old)
        - Have low quality scores (<0.5)

        Args:
            limit: Maximum number of ISBNs to return

        Returns:
            List of ISBNs needing enrichment
        """
        try:
            conn = sqlite3.connect(str(self.metadata_cache_path))
            cursor = conn.cursor()

            cursor.execute('''
                SELECT isbn FROM cached_books
                WHERE market_fetched_at IS NULL
                   OR market_fetched_at < datetime('now', '-30 days')
                   OR training_quality_score < 0.5
                ORDER BY training_quality_score DESC
                LIMIT ?
            ''', (limit,))

            isbns = [row[0] for row in cursor.fetchall()]
            conn.close()

            return isbns

        except Exception as e:
            logger.error(f"Error finding books needing enrichment: {e}")
            return []
