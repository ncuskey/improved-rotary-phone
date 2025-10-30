"""
Unified ISBN index across multiple databases.

Provides fast lookups to determine which database(s) contain data for a given ISBN.
Acts as a routing layer between training_data.db and metadata_cache.db.

Architecture:
- training_data.db: High-quality training data with eBay sold comps (expensive)
- metadata_cache.db: Lightweight metadata for fast lookups (cheap)
- unified_index.db: Index mapping ISBNs to which DBs have them (this file)
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ISBNLocation:
    """
    Location information for an ISBN across databases.

    Attributes:
        isbn: Primary ISBN
        in_training: True if ISBN exists in training_data.db
        in_cache: True if ISBN exists in metadata_cache.db
        training_updated: When training_data was last updated (None if not in training)
        cache_updated: When metadata_cache was last updated (None if not in cache)
        quality_score: Best quality score across databases (0-1)
    """
    isbn: str
    in_training: bool = False
    in_cache: bool = False
    training_updated: Optional[str] = None
    cache_updated: Optional[str] = None
    quality_score: float = 0.0


class UnifiedIndex:
    """
    Manage unified ISBN index across multiple databases.

    This index tracks which ISBNs exist in which databases, enabling
    fast routing for ISBN lookups without querying multiple databases.

    Database location: ~/.isbn_lot_optimizer/unified_index.db
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize unified index.

        Args:
            db_path: Path to index database (default: ~/.isbn_lot_optimizer/unified_index.db)
        """
        if db_path is None:
            db_path = Path.home() / '.isbn_lot_optimizer' / 'unified_index.db'

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()

    def _init_database(self):
        """Create index tables if they don't exist."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Main index table
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

        # Index on common queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_isbn_index_training
            ON isbn_index(in_training)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_isbn_index_cache
            ON isbn_index(in_cache)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_isbn_index_quality
            ON isbn_index(quality_score)
        ''')

        # Sync history table (track when we synced from source DBs)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT,
                source_db TEXT,
                isbns_synced INTEGER,
                started_at TEXT,
                completed_at TEXT,
                notes TEXT
            )
        ''')

        conn.commit()
        conn.close()

        logger.info(f"Unified index initialized at {self.db_path}")

    def update_location(self, isbn: str, in_training: bool = None,
                       in_cache: bool = None, training_updated: str = None,
                       cache_updated: str = None, quality_score: float = None):
        """
        Update index entry for an ISBN.

        Args:
            isbn: ISBN to update
            in_training: Set training DB presence (None = don't update)
            in_cache: Set cache DB presence (None = don't update)
            training_updated: Training DB last updated timestamp
            cache_updated: Cache DB last updated timestamp
            quality_score: Quality score (0-1)
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Check if entry exists
            cursor.execute('SELECT isbn FROM isbn_index WHERE isbn = ?', (isbn,))
            exists = cursor.fetchone() is not None

            if exists:
                # Update existing entry
                updates = []
                params = []

                if in_training is not None:
                    updates.append('in_training = ?')
                    params.append(1 if in_training else 0)
                if in_cache is not None:
                    updates.append('in_cache = ?')
                    params.append(1 if in_cache else 0)
                if training_updated is not None:
                    updates.append('training_updated = ?')
                    params.append(training_updated)
                if cache_updated is not None:
                    updates.append('cache_updated = ?')
                    params.append(cache_updated)
                if quality_score is not None:
                    updates.append('quality_score = ?')
                    params.append(quality_score)

                updates.append('last_checked = ?')
                params.append(datetime.now().isoformat())

                params.append(isbn)

                cursor.execute(f'''
                    UPDATE isbn_index
                    SET {', '.join(updates)}
                    WHERE isbn = ?
                ''', params)
            else:
                # Insert new entry
                cursor.execute('''
                    INSERT INTO isbn_index (
                        isbn, in_training, in_cache, training_updated,
                        cache_updated, quality_score, last_checked
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    isbn,
                    1 if in_training else 0,
                    1 if in_cache else 0,
                    training_updated,
                    cache_updated,
                    quality_score or 0.0,
                    datetime.now().isoformat()
                ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating index for {isbn}: {e}")

    def get_location(self, isbn: str) -> Optional[ISBNLocation]:
        """
        Get location information for an ISBN.

        Args:
            isbn: ISBN to lookup

        Returns:
            ISBNLocation if found, None otherwise
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM isbn_index WHERE isbn = ?
            ''', (isbn,))

            row = cursor.fetchone()
            conn.close()

            if row:
                return ISBNLocation(
                    isbn=row['isbn'],
                    in_training=bool(row['in_training']),
                    in_cache=bool(row['in_cache']),
                    training_updated=row['training_updated'],
                    cache_updated=row['cache_updated'],
                    quality_score=row['quality_score']
                )

            return None

        except Exception as e:
            logger.error(f"Error getting location for {isbn}: {e}")
            return None

    def get_stats(self) -> Dict:
        """
        Get statistics about the unified index.

        Returns:
            Dict with index statistics
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Total ISBNs
            cursor.execute('SELECT COUNT(*) FROM isbn_index')
            total = cursor.fetchone()[0]

            # In training DB
            cursor.execute('SELECT COUNT(*) FROM isbn_index WHERE in_training = 1')
            in_training = cursor.fetchone()[0]

            # In cache DB
            cursor.execute('SELECT COUNT(*) FROM isbn_index WHERE in_cache = 1')
            in_cache = cursor.fetchone()[0]

            # In both DBs
            cursor.execute('''
                SELECT COUNT(*) FROM isbn_index
                WHERE in_training = 1 AND in_cache = 1
            ''')
            in_both = cursor.fetchone()[0]

            # Quality distribution
            cursor.execute('''
                SELECT
                    CASE
                        WHEN quality_score >= 0.8 THEN 'high'
                        WHEN quality_score >= 0.5 THEN 'medium'
                        ELSE 'low'
                    END as quality_tier,
                    COUNT(*)
                FROM isbn_index
                GROUP BY quality_tier
            ''')
            by_quality = dict(cursor.fetchall())

            conn.close()

            return {
                'total_isbns': total,
                'in_training_db': in_training,
                'in_cache_db': in_cache,
                'in_both_dbs': in_both,
                'cache_only': in_cache - in_both,
                'training_only': in_training - in_both,
                'by_quality': by_quality
            }

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}

    def sync_from_training_db(self, training_db_path: Optional[Path] = None) -> int:
        """
        Sync index from training_data.db.

        Args:
            training_db_path: Path to training_data.db (default: standard location)

        Returns:
            Number of ISBNs synced
        """
        if training_db_path is None:
            training_db_path = Path.home() / '.isbn_lot_optimizer' / 'training_data.db'

        if not training_db_path.exists():
            logger.warning(f"Training DB not found: {training_db_path}")
            return 0

        try:
            start_time = datetime.now().isoformat()
            synced = 0

            # Read all ISBNs from training DB
            conn = sqlite3.connect(str(training_db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT isbn, updated_at
                FROM training_books
            ''')

            for row in cursor.fetchall():
                self.update_location(
                    isbn=row['isbn'],
                    in_training=True,
                    training_updated=row['updated_at'],
                    quality_score=1.0  # Training data is always high quality
                )
                synced += 1

            conn.close()

            # Record sync
            self._record_sync('full', 'training_data.db', synced, start_time,
                            datetime.now().isoformat())

            logger.info(f"Synced {synced} ISBNs from training_data.db")
            return synced

        except Exception as e:
            logger.error(f"Error syncing from training DB: {e}")
            return 0

    def sync_from_cache_db(self, cache_db_path: Optional[Path] = None) -> int:
        """
        Sync index from metadata_cache.db.

        Args:
            cache_db_path: Path to metadata_cache.db (default: standard location)

        Returns:
            Number of ISBNs synced
        """
        if cache_db_path is None:
            cache_db_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

        if not cache_db_path.exists():
            logger.warning(f"Cache DB not found: {cache_db_path}")
            return 0

        try:
            start_time = datetime.now().isoformat()
            synced = 0

            # Read all ISBNs from cache DB
            conn = sqlite3.connect(str(cache_db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT isbn, updated_at, quality_score
                FROM cached_books
            ''')

            for row in cursor.fetchall():
                self.update_location(
                    isbn=row['isbn'],
                    in_cache=True,
                    cache_updated=row['updated_at'],
                    quality_score=row['quality_score']
                )
                synced += 1

            conn.close()

            # Record sync
            self._record_sync('full', 'metadata_cache.db', synced, start_time,
                            datetime.now().isoformat())

            logger.info(f"Synced {synced} ISBNs from metadata_cache.db")
            return synced

        except Exception as e:
            logger.error(f"Error syncing from cache DB: {e}")
            return 0

    def sync_all(self) -> Dict[str, int]:
        """
        Sync index from both training and cache databases.

        Returns:
            Dict with counts: {'training': N, 'cache': M}
        """
        training_count = self.sync_from_training_db()
        cache_count = self.sync_from_cache_db()

        return {
            'training': training_count,
            'cache': cache_count
        }

    def find_gaps(self) -> Dict[str, List[str]]:
        """
        Find ISBNs that exist in one DB but not the other.

        Returns:
            Dict with two lists:
            - 'in_training_not_cache': ISBNs in training but not cache
            - 'in_cache_not_training': ISBNs in cache but not training
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # In training but not cache
            cursor.execute('''
                SELECT isbn FROM isbn_index
                WHERE in_training = 1 AND in_cache = 0
                ORDER BY isbn
            ''')
            training_not_cache = [row[0] for row in cursor.fetchall()]

            # In cache but not training
            cursor.execute('''
                SELECT isbn FROM isbn_index
                WHERE in_cache = 1 AND in_training = 0
                ORDER BY isbn
            ''')
            cache_not_training = [row[0] for row in cursor.fetchall()]

            conn.close()

            return {
                'in_training_not_cache': training_not_cache,
                'in_cache_not_training': cache_not_training
            }

        except Exception as e:
            logger.error(f"Error finding gaps: {e}")
            return {'in_training_not_cache': [], 'in_cache_not_training': []}

    def _record_sync(self, sync_type: str, source_db: str, isbns_synced: int,
                    started_at: str, completed_at: str, notes: str = ''):
        """Record a sync operation in history."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO sync_history (
                    sync_type, source_db, isbns_synced,
                    started_at, completed_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (sync_type, source_db, isbns_synced, started_at, completed_at, notes))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error recording sync: {e}")
