from __future__ import annotations

import json
import re
import sqlite3
import os
import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


# ------------------------------------------------------------------------------
# Lightweight module-level logger for DB activity
# Writes to ~/.isbn_lot_optimizer/activity.log by default
LOG_DIR = Path.home() / ".isbn_lot_optimizer"
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
LOG_PATH = Path(os.getenv("APP_LOG_PATH", str(LOG_DIR / "activity.log")))
_logger = logging.getLogger("isbn_lot_optimizer.db")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    try:
        _handler = RotatingFileHandler(LOG_PATH, maxBytes=512 * 1024, backupCount=3)
    except Exception:
        _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _logger.addHandler(_handler)
    _logger.propagate = False


def _log(action: str, **fields: Any) -> None:
    try:
        _logger.info("%s %s", action, json.dumps(fields, ensure_ascii=False, sort_keys=True))
    except Exception:
        try:
            _logger.info("%s %s", action, str(fields))
        except Exception:
            pass
# ------------------------------------------------------------------------------

class DatabaseManager:
    """Lightweight SQLite wrapper for storing scanned books and lot suggestions."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()  # Thread-local storage for connections
        self._initialise()

    def _initialise(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS books (
                    isbn TEXT PRIMARY KEY,
                    title TEXT,
                    authors TEXT,
                    publication_year INTEGER,
                    edition TEXT,
                    condition TEXT,
                    estimated_price REAL,
                    price_reference REAL,
                    rarity REAL,
                    probability_label TEXT,
                    probability_score REAL,
                    probability_reasons TEXT,
                    sell_through REAL,
                    ebay_active_count INTEGER,
                    ebay_sold_count INTEGER,
                    ebay_currency TEXT,
                    metadata_json TEXT,
                    market_json TEXT,
                    booksrun_json TEXT,
                    bookscouter_json TEXT,
                    source_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS lots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    book_isbns TEXT NOT NULL,
                    estimated_value REAL,
                    probability_label TEXT,
                    probability_score REAL,
                    sell_through REAL,
                    justification TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name, strategy)
                );
                """
            )
            self._ensure_lot_justification(conn)
            self._ensure_booksrun_column(conn)
            self._ensure_bookscouter_column(conn)
            self._ensure_bookscouter_fetched_at(conn)
            self._ensure_api_fetch_timestamps(conn)

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get or create a thread-local database connection.

        SQLite connections must be used in the same thread they were created in.
        This uses thread-local storage to ensure each thread gets its own connection.
        """
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def close(self) -> None:
        """Close the database connection for the current thread."""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            finally:
                self._local.conn = None

    def _ensure_lot_justification(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(lots)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if "justification" not in existing_columns:
            conn.execute("ALTER TABLE lots ADD COLUMN justification TEXT")

    def _ensure_booksrun_column(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(books)")
        columns = {row[1] for row in cursor.fetchall()}
        if "booksrun_json" not in columns:
            conn.execute("ALTER TABLE books ADD COLUMN booksrun_json TEXT")

    def _ensure_bookscouter_column(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(books)")
        columns = {row[1] for row in cursor.fetchall()}
        if "bookscouter_json" not in columns:
            conn.execute("ALTER TABLE books ADD COLUMN bookscouter_json TEXT")

    def _ensure_bookscouter_fetched_at(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(books)")
        columns = {row[1] for row in cursor.fetchall()}
        if "bookscouter_fetched_at" not in columns:
            conn.execute("ALTER TABLE books ADD COLUMN bookscouter_fetched_at TEXT")
            # Create index for efficient staleness queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_books_bookscouter_fetched_at
                ON books(bookscouter_fetched_at)
            """)

    def _ensure_api_fetch_timestamps(self, conn: sqlite3.Connection) -> None:
        """Ensure timestamp columns exist for tracking API fetch freshness."""
        cursor = conn.execute("PRAGMA table_info(books)")
        columns = {row[1] for row in cursor.fetchall()}

        if "market_fetched_at" not in columns:
            conn.execute("ALTER TABLE books ADD COLUMN market_fetched_at TEXT")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_books_market_fetched_at
                ON books(market_fetched_at)
            """)

        if "metadata_fetched_at" not in columns:
            conn.execute("ALTER TABLE books ADD COLUMN metadata_fetched_at TEXT")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_books_metadata_fetched_at
                ON books(metadata_fetched_at)
            """)

    # ------------------------------------------------------------------
    # Book persistence helpers

    def upsert_book(self, payload: Dict[str, Any]) -> None:
        data = payload.copy()
        data["metadata_json"] = json.dumps(data.get("metadata_json", {}))
        data["market_json"] = json.dumps(data.get("market_json", {}))
        data["booksrun_json"] = json.dumps(data.get("booksrun_json", {}))
        data["bookscouter_json"] = json.dumps(data.get("bookscouter_json", {}))
        data["source_json"] = json.dumps(data.get("source_json", {}))
        data.setdefault("probability_reasons", "")
        data.setdefault("condition", "Good")
        data.setdefault("probability_label", "Unknown")
        data.setdefault("probability_score", 0.0)
        data.setdefault("estimated_price", 0.0)
        data.setdefault("price_reference", 0.0)

        _log("upsert_book", isbn=data.get("isbn"), title=data.get("title"))

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO books (
                    isbn, title, authors, publication_year, edition, condition,
                    estimated_price, price_reference, rarity,
                    probability_label, probability_score, probability_reasons,
                    sell_through, ebay_active_count, ebay_sold_count, ebay_currency,
                    metadata_json, market_json, booksrun_json, bookscouter_json, source_json,
                    sold_comps_count, sold_comps_min, sold_comps_median, sold_comps_max,
                    sold_comps_is_estimate, sold_comps_source,
                    created_at, updated_at
                ) VALUES (
                    :isbn, :title, :authors, :publication_year, :edition, :condition,
                    :estimated_price, :price_reference, :rarity,
                    :probability_label, :probability_score, :probability_reasons,
                    :sell_through, :ebay_active_count, :ebay_sold_count, :ebay_currency,
                    :metadata_json, :market_json, :booksrun_json, :bookscouter_json, :source_json,
                    :sold_comps_count, :sold_comps_min, :sold_comps_median, :sold_comps_max,
                    :sold_comps_is_estimate, :sold_comps_source,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT(isbn) DO UPDATE SET
                    title=excluded.title,
                    authors=excluded.authors,
                    publication_year=excluded.publication_year,
                    edition=excluded.edition,
                    condition=excluded.condition,
                    estimated_price=excluded.estimated_price,
                    price_reference=excluded.price_reference,
                    rarity=excluded.rarity,
                    probability_label=excluded.probability_label,
                    probability_score=excluded.probability_score,
                    probability_reasons=excluded.probability_reasons,
                    sell_through=excluded.sell_through,
                    ebay_active_count=excluded.ebay_active_count,
                    ebay_sold_count=excluded.ebay_sold_count,
                    ebay_currency=excluded.ebay_currency,
                    metadata_json=excluded.metadata_json,
                    market_json=excluded.market_json,
                    booksrun_json=excluded.booksrun_json,
                    bookscouter_json=excluded.bookscouter_json,
                    source_json=excluded.source_json,
                    sold_comps_count=excluded.sold_comps_count,
                    sold_comps_min=excluded.sold_comps_min,
                    sold_comps_median=excluded.sold_comps_median,
                    sold_comps_max=excluded.sold_comps_max,
                    sold_comps_is_estimate=excluded.sold_comps_is_estimate,
                    sold_comps_source=excluded.sold_comps_source,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                data,
            )

    def update_book_market_json(self, isbn: str, market_blob: Dict[str, Any]) -> None:
        """Update market data and set market_fetched_at timestamp."""
        payload = json.dumps(market_blob or {}, ensure_ascii=False)
        _log("update_market", isbn=isbn, bytes=len(payload))
        with self._get_connection() as conn:
            conn.execute(
                """UPDATE books
                   SET market_json = ?,
                       market_fetched_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE isbn = ?""",
                (payload, isbn),
            )

    def update_book_source_json(self, isbn: str, source_blob: Dict[str, Any]) -> None:
        payload = json.dumps(source_blob or {}, ensure_ascii=False)
        _log("update_source", isbn=isbn, bytes=len(payload))
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE books SET source_json = ?, updated_at = CURRENT_TIMESTAMP WHERE isbn = ?",
                (payload, isbn),
            )

    def update_book_bookscouter_json(self, isbn: str, bookscouter_blob: Dict[str, Any]) -> None:
        """Update BookScouter data and set fetched_at timestamp."""
        payload = json.dumps(bookscouter_blob or {}, ensure_ascii=False)
        _log("update_bookscouter", isbn=isbn, bytes=len(payload))
        with self._get_connection() as conn:
            conn.execute(
                """UPDATE books
                   SET bookscouter_json = ?,
                       bookscouter_fetched_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE isbn = ?""",
                (payload, isbn),
            )

    def update_book_record(
        self,
        isbn: str,
        *,
        columns: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        assignments: List[str] = []
        values: List[Any] = []
        columns = columns or {}
        metadata_dict = None

        if metadata is not None:
            metadata_dict = metadata
        elif columns:
            metadata_dict = None

        with self._get_connection() as conn:
            if metadata_dict is None and metadata is None:
                existing = conn.execute(
                    "SELECT metadata_json FROM books WHERE isbn = ?", (isbn,)
                ).fetchone()
                if not existing:
                    raise ValueError(f"Book {isbn} not found")
                try:
                    metadata_dict = json.loads(existing["metadata_json"] or "{}")
                except Exception:
                    metadata_dict = {}
            elif metadata_dict is None:
                existing = conn.execute(
                    "SELECT metadata_json FROM books WHERE isbn = ?", (isbn,)
                ).fetchone()
                if not existing:
                    raise ValueError(f"Book {isbn} not found")
                try:
                    metadata_dict = json.loads(existing["metadata_json"] or "{}")
                except Exception:
                    metadata_dict = {}

            for col, value in columns.items():
                assignments.append(f"{col} = ?")
                values.append(value)

            if metadata is not None:
                metadata_dict = metadata

            if metadata_dict is not None:
                assignments.append("metadata_json = ?")
                values.append(json.dumps(metadata_dict, ensure_ascii=False))

            assignments.append("updated_at = CURRENT_TIMESTAMP")
            sql = f"UPDATE books SET {', '.join(assignments)} WHERE isbn = ?"
            values.append(isbn)
            _log("update_record", isbn=isbn, columns=list(columns.keys()), metadata_changed=metadata_dict is not None)
            conn.execute(sql, values)

    def delete_book(self, isbn: str) -> None:
        with self._get_connection() as conn:
            _log("delete_book", isbn=isbn)
            conn.execute("DELETE FROM books WHERE isbn = ?", (isbn,))

    def delete_books(self, isbns: Iterable[str]) -> int:
        deleted = 0
        with self._get_connection() as conn:
            for isbn in isbns:
                before = conn.total_changes
                conn.execute("DELETE FROM books WHERE isbn = ?", (isbn,))
                after = conn.total_changes
                delta = max(0, after - before)
                deleted += delta
                _log("delete_book", isbn=isbn, deleted=delta)
        return deleted

    def fetch_book(self, isbn: str) -> Optional[sqlite3.Row]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM books WHERE isbn = ?", (isbn,))
            row = cursor.fetchone()
        return row

    def fetch_all_books(self) -> List[sqlite3.Row]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM books ORDER BY datetime(updated_at) DESC"
            )
            rows = cursor.fetchall()
        return list(rows)

    def search_books(self, query: str) -> List[sqlite3.Row]:
        """
        Full-text-like search across ISBN, title, and authors using simple LIKE.
        Returns rows ordered by probability_score then title.
        """
        q = f"%{(query or '').strip()}%"
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM books
                WHERE isbn LIKE ? OR title LIKE ? OR authors LIKE ?
                ORDER BY probability_score DESC, title COLLATE NOCASE
                """,
                (q, q, q),
            )
            rows = cursor.fetchall()
        return list(rows)

    def fetch_books_needing_bookscouter_refresh(
        self,
        max_age_days: int = 30
    ) -> List[sqlite3.Row]:
        """
        Fetch books that need BookScouter data refresh.

        Returns books where:
        - bookscouter_fetched_at is NULL (never fetched), OR
        - bookscouter_fetched_at is older than max_age_days

        Args:
            max_age_days: Maximum age in days before data is considered stale

        Returns:
            List of book rows that need refresh
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM books
                WHERE bookscouter_fetched_at IS NULL
                   OR bookscouter_fetched_at < datetime('now', '-' || ? || ' days')
                ORDER BY probability_score DESC, title COLLATE NOCASE
                """,
                (max_age_days,),
            )
            rows = cursor.fetchall()
        return list(rows)

    def fetch_books_needing_market_refresh(
        self,
        max_age_days: int = 30
    ) -> List[sqlite3.Row]:
        """
        Fetch books that need eBay market data refresh.

        Returns books where:
        - market_fetched_at is NULL (never fetched), OR
        - market_fetched_at is older than max_age_days

        Args:
            max_age_days: Maximum age in days before data is considered stale

        Returns:
            List of book rows that need refresh
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM books
                WHERE market_fetched_at IS NULL
                   OR market_fetched_at < datetime('now', '-' || ? || ' days')
                ORDER BY probability_score DESC, title COLLATE NOCASE
                """,
                (max_age_days,),
            )
            rows = cursor.fetchall()
        return list(rows)

    def fetch_books_needing_metadata_refresh(
        self,
        max_age_days: int = 90
    ) -> List[sqlite3.Row]:
        """
        Fetch books that need metadata refresh.

        Returns books where:
        - metadata_fetched_at is NULL (never fetched), OR
        - metadata_fetched_at is older than max_age_days

        Args:
            max_age_days: Maximum age in days before data is considered stale
                         (default: 90, metadata changes less frequently)

        Returns:
            List of book rows that need refresh
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM books
                WHERE metadata_fetched_at IS NULL
                   OR metadata_fetched_at < datetime('now', '-' || ? || ' days')
                ORDER BY probability_score DESC, title COLLATE NOCASE
                """,
                (max_age_days,),
            )
            rows = cursor.fetchall()
        return list(rows)

    def fetch_books_with_missing_covers(self) -> List[sqlite3.Row]:
        """
        Fetch books that have missing or broken cover images.

        Returns books where metadata_json is missing cover_url or thumbnail fields.
        This is useful for identifying books that need cover image updates.

        Returns:
            List of book rows with missing cover images
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM books
                WHERE metadata_json IS NULL
                   OR metadata_json NOT LIKE '%"cover_url"%'
                   OR metadata_json NOT LIKE '%"thumbnail"%'
                   OR metadata_json LIKE '%"cover_url": null%'
                   OR metadata_json LIKE '%"thumbnail": null%'
                ORDER BY probability_score DESC, title COLLATE NOCASE
                """
            )
            rows = cursor.fetchall()
        return list(rows)

    def count_books_with_covers(self) -> Dict[str, int]:
        """
        Count books with and without cover images.

        Returns:
            Dict with 'with_covers', 'without_covers', and 'total' counts
        """
        with self._get_connection() as conn:
            # Total books
            total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]

            # Books with covers (has cover_url or thumbnail in metadata_json)
            with_covers = conn.execute(
                """
                SELECT COUNT(*) FROM books
                WHERE metadata_json IS NOT NULL
                  AND (
                      (metadata_json LIKE '%"cover_url": "http%')
                      OR (metadata_json LIKE '%"thumbnail": "http%')
                  )
                """
            ).fetchone()[0]

            without_covers = total - with_covers

            return {
                "total": total,
                "with_covers": with_covers,
                "without_covers": without_covers,
                "coverage_percentage": (with_covers / total * 100) if total > 0 else 0,
            }

    # ------------------------------------------------------------------
    # Lot persistence helpers

    def replace_lots(self, lots: Iterable[Dict[str, Any]]) -> None:
        lot_payloads = list(lots)
        for payload in lot_payloads:
            payload["book_isbns"] = json.dumps(payload.get("book_isbns", []))
            payload.setdefault("justification", "")

        _log("replace_lots", count=len(lot_payloads))
        with self._get_connection() as conn:
            conn.execute("DELETE FROM lots")
            conn.executemany(
                """
                INSERT INTO lots (
                    name, strategy, book_isbns,
                    estimated_value, probability_label, probability_score,
                    sell_through, justification, updated_at
                ) VALUES (
                    :name, :strategy, :book_isbns,
                    :estimated_value, :probability_label, :probability_score,
                    :sell_through, :justification, CURRENT_TIMESTAMP
                )
                """,
                lot_payloads,
            )

    def fetch_lots(self) -> List[sqlite3.Row]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM lots ORDER BY probability_score DESC, estimated_value DESC"
            )
            rows = cursor.fetchall()
        return list(rows)

    def clear(self) -> None:
        with self._get_connection() as conn:
            _log("clear_all")
            conn.execute("DELETE FROM books")
            conn.execute("DELETE FROM lots")

    def list_distinct_author_names(self) -> List[str]:
        """
        Return a de-duplicated list of author names found in the books table.

        The 'authors' column is stored as a delimited string; this function splits on
        semicolons and commas, trims whitespace, and returns unique names sorted
        case-insensitively for stable display.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT authors FROM books WHERE authors IS NOT NULL AND authors <> ''"
            ).fetchall()

        names_set: set[str] = set()
        for row in rows:
            authors_str = row[0] if isinstance(row, tuple) else row["authors"]
            s = str(authors_str or "")
            parts = [p.strip() for p in re.split(r";|,", s) if p and p.strip()]
            for p in parts:
                if p:
                    names_set.add(p)

        return sorted(names_set, key=lambda x: x.lower())

    def update_book_metadata_fields(self, isbn: str, meta: Optional[Dict[str, Any]]) -> None:
        """
        Write normalized fields into scalar columns (title/authors/publication_year)
        and store the full dict in metadata_json. Keep existing values if new ones are None.

        This is the method used by CLI metadata refresh operations.
        """
        if not meta:
            return

        title = meta.get("title")
        authors = meta.get("authors_str") or (", ".join(meta.get("authors") or []) or None)
        publication_year = meta.get("publication_year")
        metadata_json = json.dumps(meta, ensure_ascii=False)

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE books SET
                  title = COALESCE(:title, title),
                  authors = COALESCE(:authors, authors),
                  publication_year = COALESCE(:publication_year, publication_year),
                  metadata_json = :metadata_json,
                  metadata_fetched_at = CURRENT_TIMESTAMP,
                  updated_at = CURRENT_TIMESTAMP
                WHERE isbn = :isbn
            """, {
                "isbn": isbn,
                "title": title,
                "authors": authors,
                "publication_year": publication_year,
                "metadata_json": metadata_json,
            })


def ensure_metadata_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(books)").fetchall()}
    add = []

    def need(c: str, typ: str) -> None:
        if c not in cols:
            add.append((c, typ))

    need("publisher", "TEXT")
    need("published_date", "TEXT")
    need("page_count", "INTEGER")
    need("categories", "TEXT")
    need("average_rating", "REAL")
    need("ratings_count", "INTEGER")
    need("language", "TEXT")
    need("cover_url", "TEXT")
    need("description", "TEXT")
    need("series_name", "TEXT")
    need("series_index", "INTEGER")

    for c, t in add:
        conn.execute(f"ALTER TABLE books ADD COLUMN {c} {t}")
    if add:
        conn.commit()


def update_book_metadata(conn: sqlite3.Connection, isbn: str, meta: dict) -> None:
    if not meta:
        return
    payload = {
        "publisher": meta.get("publisher"),
        "published_date": meta.get("published_date"),
        "page_count": meta.get("page_count"),
        "categories": meta.get("categories"),
        "average_rating": meta.get("average_rating"),
        "ratings_count": meta.get("ratings_count"),
        "language": meta.get("language"),
        "cover_url": meta.get("cover_url"),
        "description": meta.get("description"),
        "series_name": meta.get("series_name"),
        "series_index": meta.get("series_index"),
        "isbn": isbn,
    }
    conn.execute(
        """
        UPDATE books SET
          publisher=:publisher,
          published_date=:published_date,
          page_count=:page_count,
          categories=:categories,
          average_rating=:average_rating,
          ratings_count=:ratings_count,
          language=:language,
          cover_url=:cover_url,
          description=:description,
          series_name=:series_name,
          series_index=:series_index,
          updated_at=CURRENT_TIMESTAMP
        WHERE isbn=:isbn
        """,
        payload,
    )
