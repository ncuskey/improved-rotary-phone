"""
Training data database manager.

Separate database for strategically collected ML training data,
independent of the main inventory catalog.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class TrainingDataManager:
    """
    Manage training data collection database.

    Separate from catalog.db to keep training data collection
    independent from actual inventory management.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize training data manager.

        Args:
            db_path: Path to training_data.db. Defaults to ~/.isbn_lot_optimizer/training_data.db
        """
        if db_path is None:
            db_path = Path.home() / '.isbn_lot_optimizer' / 'training_data.db'

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Training books table (similar to catalog.db books table)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS training_books (
                isbn TEXT PRIMARY KEY,
                title TEXT,
                authors TEXT,
                publication_year INTEGER,
                cover_type TEXT,
                printing TEXT,
                signed INTEGER DEFAULT 0,
                page_count INTEGER,

                -- Price data (ground truth for training)
                sold_avg_price REAL,
                sold_median_price REAL,
                sold_count INTEGER,

                -- JSON data blobs
                metadata_json TEXT,
                market_json TEXT,
                bookscouter_json TEXT,

                -- Collection metadata
                collection_category TEXT,  -- 'signed_hardcover', 'first_edition_hardcover', etc.
                collection_priority INTEGER,
                comp_quality_score REAL,  -- 0-1 score based on sold_count

                -- Timestamps
                collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                -- Source tracking
                source TEXT DEFAULT 'ebay_search'
            )
        ''')

        # Collection targets (what we're trying to collect)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS collection_targets (
                category TEXT PRIMARY KEY,
                description TEXT,
                target_count INTEGER,
                current_count INTEGER DEFAULT 0,
                min_comps INTEGER DEFAULT 10,
                priority INTEGER DEFAULT 1,

                -- Search strategy
                search_query TEXT,
                ebay_filters TEXT,  -- JSON blob of eBay API filters

                -- Status
                status TEXT DEFAULT 'active',  -- 'active', 'completed', 'paused'
                completed_at TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Collection log (history of collection runs)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS collection_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,  -- UUID for this collection run
                isbn TEXT,
                category TEXT,
                success INTEGER DEFAULT 1,
                error_message TEXT,
                comp_count INTEGER,
                api_calls_used INTEGER,  -- Track API usage

                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (isbn) REFERENCES training_books(isbn)
            )
        ''')

        # API call tracking (rate limit management)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_call_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_name TEXT,  -- 'ebay_browse', 'ebay_sell', 'decodo', 'google_books'
                endpoint TEXT,
                success INTEGER DEFAULT 1,
                response_code INTEGER,

                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Deduplication table (books already in catalog.db or training_data.db)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS isbn_blacklist (
                isbn TEXT PRIMARY KEY,
                reason TEXT,  -- 'in_catalog', 'in_training', 'failed_collection', 'low_quality'
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_training_books_category ON training_books(collection_category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_training_books_priority ON training_books(collection_priority)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_collection_log_run_id ON collection_log(run_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_collection_log_category ON collection_log(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_call_log_timestamp ON api_call_log(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_call_log_api_name ON api_call_log(api_name)')

        conn.commit()
        conn.close()

    def add_training_book(
        self,
        isbn: str,
        category: str,
        sold_avg_price: float,
        sold_count: int,
        metadata_json: str,
        market_json: str,
        bookscouter_json: Optional[str] = None,
        **kwargs
    ) -> None:
        """Add a book to training dataset."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Parse metadata to extract key fields
        metadata = json.loads(metadata_json) if metadata_json else {}

        cursor.execute('''
            INSERT OR REPLACE INTO training_books (
                isbn, title, authors, publication_year, cover_type, printing, signed,
                page_count, sold_avg_price, sold_median_price, sold_count,
                metadata_json, market_json, bookscouter_json,
                collection_category, comp_quality_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            isbn,
            metadata.get('title', ''),
            json.dumps(metadata.get('authors', [])),
            metadata.get('published_year'),
            metadata.get('cover_type'),
            metadata.get('printing'),
            metadata.get('signed', 0),
            metadata.get('page_count'),
            sold_avg_price,
            kwargs.get('sold_median_price', sold_avg_price),
            sold_count,
            metadata_json,
            market_json,
            bookscouter_json,
            category,
            min(1.0, sold_count / 20.0)  # Quality score: 0-1 based on comp count
        ))

        conn.commit()
        conn.close()

    def log_api_call(self, api_name: str, endpoint: str, success: bool = True, response_code: Optional[int] = None) -> None:
        """Log an API call for rate limit tracking."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO api_call_log (api_name, endpoint, success, response_code, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (api_name, endpoint, 1 if success else 0, response_code, datetime.utcnow().isoformat()))

        conn.commit()
        conn.close()

    def get_api_call_count(self, api_name: str, hours: int = 24) -> int:
        """Get API call count in last N hours."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff = datetime.utcnow().timestamp() - (hours * 3600)
        cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()

        cursor.execute('''
            SELECT COUNT(*) FROM api_call_log
            WHERE api_name = ? AND timestamp > ?
        ''', (api_name, cutoff_iso))

        count = cursor.fetchone()[0]
        conn.close()

        return count

    def get_collection_progress(self) -> List[Dict]:
        """Get progress on all collection targets."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                t.category,
                t.description,
                t.target_count,
                t.current_count,
                t.priority,
                t.status,
                CAST(t.current_count AS FLOAT) / t.target_count AS progress_pct
            FROM collection_targets t
            ORDER BY t.priority, t.category
        ''')

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return results

    def update_target_count(self, category: str) -> None:
        """Update current_count for a category."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE collection_targets
            SET current_count = (
                SELECT COUNT(*) FROM training_books
                WHERE collection_category = ?
            ),
            updated_at = ?
            WHERE category = ?
        ''', (category, datetime.utcnow().isoformat(), category))

        # Mark as completed if target reached
        cursor.execute('''
            UPDATE collection_targets
            SET status = 'completed', completed_at = ?
            WHERE category = ? AND current_count >= target_count AND status != 'completed'
        ''', (datetime.utcnow().isoformat(), category))

        conn.commit()
        conn.close()

    def add_to_blacklist(self, isbn: str, reason: str) -> None:
        """Add ISBN to blacklist to avoid re-collecting."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR IGNORE INTO isbn_blacklist (isbn, reason)
            VALUES (?, ?)
        ''', (isbn, reason))

        conn.commit()
        conn.close()

    def is_blacklisted(self, isbn: str) -> bool:
        """Check if ISBN is blacklisted."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT 1 FROM isbn_blacklist WHERE isbn = ?', (isbn,))
        result = cursor.fetchone()

        conn.close()
        return result is not None

    def get_training_book_count(self) -> int:
        """Get total number of training books collected."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM training_books')
        count = cursor.fetchone()[0]

        conn.close()
        return count

    def get_stats(self) -> Dict:
        """Get overall training data statistics."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        stats = {}

        # Total books
        cursor.execute('SELECT COUNT(*) as total FROM training_books')
        stats['total_books'] = cursor.fetchone()['total']

        # By category
        cursor.execute('''
            SELECT collection_category, COUNT(*) as count
            FROM training_books
            GROUP BY collection_category
        ''')
        stats['by_category'] = {row['collection_category']: row['count'] for row in cursor.fetchall()}

        # Cover type distribution
        cursor.execute('''
            SELECT cover_type, COUNT(*) as count
            FROM training_books
            GROUP BY cover_type
        ''')
        stats['by_cover_type'] = {row['cover_type']: row['count'] for row in cursor.fetchall()}

        # Signed books
        cursor.execute('SELECT COUNT(*) as count FROM training_books WHERE signed = 1')
        stats['signed_books'] = cursor.fetchone()['count']

        # First editions
        cursor.execute('SELECT COUNT(*) as count FROM training_books WHERE printing = "1st"')
        stats['first_editions'] = cursor.fetchone()['count']

        # Quality distribution
        cursor.execute('''
            SELECT
                CASE
                    WHEN sold_count < 5 THEN '1-4 comps'
                    WHEN sold_count < 10 THEN '5-9 comps'
                    WHEN sold_count < 20 THEN '10-19 comps'
                    WHEN sold_count < 50 THEN '20-49 comps'
                    ELSE '50+ comps'
                END as quality_tier,
                COUNT(*) as count
            FROM training_books
            GROUP BY quality_tier
            ORDER BY MIN(sold_count)
        ''')
        stats['by_quality'] = {row['quality_tier']: row['count'] for row in cursor.fetchall()}

        # API usage (last 24h)
        cursor.execute('''
            SELECT api_name, COUNT(*) as count
            FROM api_call_log
            WHERE timestamp > datetime('now', '-1 day')
            GROUP BY api_name
        ''')
        stats['api_calls_24h'] = {row['api_name']: row['count'] for row in cursor.fetchall()}

        conn.close()
        return stats
