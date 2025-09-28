from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class DatabaseManager:
    """Lightweight SQLite wrapper for storing scanned books and lot suggestions."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
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

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_lot_justification(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(lots)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if "justification" not in existing_columns:
            conn.execute("ALTER TABLE lots ADD COLUMN justification TEXT")

    # ------------------------------------------------------------------
    # Book persistence helpers

    def upsert_book(self, payload: Dict[str, Any]) -> None:
        data = payload.copy()
        data["metadata_json"] = json.dumps(data.get("metadata_json", {}))
        data["market_json"] = json.dumps(data.get("market_json", {}))
        data["source_json"] = json.dumps(data.get("source_json", {}))
        data.setdefault("probability_reasons", "")
        data.setdefault("condition", "Good")
        data.setdefault("probability_label", "Unknown")
        data.setdefault("probability_score", 0.0)
        data.setdefault("estimated_price", 0.0)
        data.setdefault("price_reference", 0.0)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO books (
                    isbn, title, authors, publication_year, edition, condition,
                    estimated_price, price_reference, rarity,
                    probability_label, probability_score, probability_reasons,
                    sell_through, ebay_active_count, ebay_sold_count, ebay_currency,
                    metadata_json, market_json, source_json,
                    created_at, updated_at
                ) VALUES (
                    :isbn, :title, :authors, :publication_year, :edition, :condition,
                    :estimated_price, :price_reference, :rarity,
                    :probability_label, :probability_score, :probability_reasons,
                    :sell_through, :ebay_active_count, :ebay_sold_count, :ebay_currency,
                    :metadata_json, :market_json, :source_json,
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
                    source_json=excluded.source_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                data,
            )

    def update_book_market_json(self, isbn: str, market_blob: Dict[str, Any]) -> None:
        payload = json.dumps(market_blob or {}, ensure_ascii=False)
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE books SET market_json = ?, updated_at = CURRENT_TIMESTAMP WHERE isbn = ?",
                (payload, isbn),
            )

    def update_book_source_json(self, isbn: str, source_blob: Dict[str, Any]) -> None:
        payload = json.dumps(source_blob or {}, ensure_ascii=False)
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE books SET source_json = ?, updated_at = CURRENT_TIMESTAMP WHERE isbn = ?",
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
            conn.execute(sql, values)

    def delete_book(self, isbn: str) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM books WHERE isbn = ?", (isbn,))

    def delete_books(self, isbns: Iterable[str]) -> int:
        deleted = 0
        with self._get_connection() as conn:
            for isbn in isbns:
                before = conn.total_changes
                conn.execute("DELETE FROM books WHERE isbn = ?", (isbn,))
                after = conn.total_changes
                deleted += max(0, after - before)
        return deleted

    def fetch_book(self, isbn: str) -> Optional[sqlite3.Row]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM books WHERE isbn = ?", (isbn,))
            row = cursor.fetchone()
        return row

    def fetch_all_books(self) -> List[sqlite3.Row]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM books ORDER BY probability_score DESC, title COLLATE NOCASE"
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

    # ------------------------------------------------------------------
    # Lot persistence helpers

    def replace_lots(self, lots: Iterable[Dict[str, Any]]) -> None:
        lot_payloads = list(lots)
        for payload in lot_payloads:
            payload["book_isbns"] = json.dumps(payload.get("book_isbns", []))
            payload.setdefault("justification", "")

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
            conn.execute("DELETE FROM books")
            conn.execute("DELETE FROM lots")


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
