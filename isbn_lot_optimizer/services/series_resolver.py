import json
import sqlite3
import time
from typing import Any, Dict, Optional, List

from .hardcover import HardcoverClient

CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def ensure_series_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    # books: add columns if missing
    cur.execute("PRAGMA table_info(books)")
    cols = {row[1] for row in cur.fetchall()}

    def addcol(name: str, type_sql: str) -> None:
        if name not in cols:
            cur.execute(f"ALTER TABLE books ADD COLUMN {name} {type_sql}")

    addcol("series_name", "TEXT")
    addcol("series_slug", "TEXT")
    addcol("series_id_hardcover", "INTEGER")
    addcol("series_position", "REAL")
    addcol("series_confidence", "REAL DEFAULT 0")
    addcol("series_last_checked", "TEXT")

    # series_peers table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS series_peers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id_hardcover INTEGER,
            series_slug TEXT,
            series_name TEXT,
            peer_title TEXT NOT NULL,
            peer_authors TEXT,
            peer_isbn13s TEXT,
            peer_position REAL,
            peer_slug TEXT,
            source TEXT DEFAULT 'Hardcover',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(series_id_hardcover, peer_title, peer_position)
        )
        """
    )
    # hc_cache table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hc_cache (
            key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()


def cache_get(conn: sqlite3.Connection, key: str) -> Optional[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute("SELECT payload, updated_at FROM hc_cache WHERE key = ?", (key,))
    row = cur.fetchone()
    if not row:
        return None
    payload, updated_at = row
    try:
        if (int(time.time()) - int(updated_at)) > CACHE_TTL_SECONDS:
            return None
    except Exception:
        return None
    try:
        return json.loads(payload)
    except Exception:
        return None


def cache_put(conn: sqlite3.Connection, key: str, payload: Dict[str, Any]) -> None:
    cur = conn.cursor()
    now = int(time.time())
    s = json.dumps(payload)
    cur.execute(
        """
        INSERT INTO hc_cache (key, payload, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
        """,
        (key, s, now, now),
    )
    conn.commit()


def upsert_series_peers(
    conn: sqlite3.Connection,
    series_id_hc: Optional[int],
    series_slug: Optional[str],
    series_name: Optional[str],
    peers: List[Dict[str, Any]],
) -> None:
    if not peers:
        return
    cur = conn.cursor()
    for p in peers:
        cur.execute(
            """
            INSERT OR IGNORE INTO series_peers
            (series_id_hardcover, series_slug, series_name, peer_title, peer_authors, peer_isbn13s, peer_position, peer_slug, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Hardcover')
            """,
            (
                series_id_hc,
                series_slug,
                series_name,
                p.get("title"),
                json.dumps(p.get("authors") or []),
                json.dumps(p.get("isbn13s") or []),
                p.get("position"),
                p.get("slug"),
            ),
        )
    conn.commit()


def get_series_for_isbn(conn: sqlite3.Connection, isbn13: str, hc: HardcoverClient) -> Dict[str, Any]:
    """
    Resolve series info for an ISBN-13 using Hardcover search.
    Returns a dict with series fields and peers, plus a 'confidence' score in [0,1].
    """
    ensure_series_schema(conn)
    # Cache key and lookup
    ck = f"book:isbn:{isbn13}"
    data = cache_get(conn, ck)
    if not data:
        data = hc.find_book_by_isbn(isbn13)
        cache_put(conn, ck, data)

    parsed = HardcoverClient.parse_book_hit(data)
    if not parsed or not parsed.get("series_name"):
        return {"confidence": 0}

    series_name = parsed.get("series_name")
    series_slug = parsed.get("series_slug")
    series_id_hc = parsed.get("series_id_hc")
    series_position = parsed.get("series_position")

    confidence = 0.6
    if series_position is not None:
        confidence += 0.2

    # Fetch peers, using series slug if available; otherwise name
    key_series = f"series:{('slug:'+series_slug) if series_slug else ('name:'+str(series_name))}"
    series_cache = cache_get(conn, key_series)
    peers: Optional[List[Dict[str, Any]]] = None
    if series_cache:
        peers = series_cache.get("_peers")  # optional direct cached peers
    if peers is None:
        # Try pulling via Book search filtered by series name (works consistently)
        books_data = hc.search_books_by_series_name(series_name, per_page=50, page=1)  # type: ignore[arg-type]
        peers = HardcoverClient.parse_book_hits_for_series_peers(books_data, str(series_name))
        cache_put(conn, key_series, {"_peers": peers})

    upsert_series_peers(conn, series_id_hc, series_slug, series_name, peers or [])

    return {
        "series_name": series_name,
        "series_slug": series_slug,
        "series_id_hardcover": series_id_hc,
        "series_position": series_position,
        "peers": peers or [],
        "confidence": confidence,
    }


def update_book_row_with_series(conn: sqlite3.Connection, isbn: str, series: Dict[str, Any]) -> None:
    """
    Persist resolved series fields into the books table for the given ISBN (primary key).
    """
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE books
        SET
            series_name = ?,
            series_slug = ?,
            series_id_hardcover = ?,
            series_position = ?,
            series_confidence = ?,
            series_last_checked = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE isbn = ?
        """,
        (
            series.get("series_name"),
            series.get("series_slug"),
            series.get("series_id_hardcover"),
            series.get("series_position"),
            float(series.get("confidence", 0) or 0.0),
            isbn,
        ),
    )
    conn.commit()
