import os
import sqlite3
import argparse
from typing import Optional

from isbn_lot_optimizer.services.hardcover import HardcoverClient
from isbn_lot_optimizer.services.series_resolver import (
    ensure_series_schema,
    get_series_for_isbn,
    update_book_row_with_series,
)

# Load .env (project root) so HARDCOVER_API_TOKEN is available when run via module
try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    # Discover .env from project root even when running inside a subdirectory/module
    load_dotenv(find_dotenv(), override=False)
except Exception:
    pass


def backfill(db_path: str, limit: int, only_missing: bool, stale_days: int) -> None:
    conn = sqlite3.connect(os.path.expanduser(db_path))
    try:
        ensure_series_schema(conn)
        try:
            token = (os.getenv("HARDCOVER_API_TOKEN") or "").strip()
            hc = HardcoverClient(token=token)
        except Exception as exc:
            raise SystemExit(f"HARDCOVER_API_TOKEN missing or invalid: {exc}")

        cur = conn.cursor()
        where_parts = []
        if only_missing:
            where_parts.append("(series_name IS NULL OR series_name = '')")
        if stale_days > 0:
            where_parts.append(
                f"(series_last_checked IS NULL OR julianday('now') - julianday(series_last_checked) > {int(stale_days)})"
            )
        where_sql = " AND ".join(where_parts) if where_parts else "1=1"

        # Our schema uses 'isbn' (TEXT PK). Restrict to 13-digit only.
        cur.execute(
            f"""
            SELECT isbn FROM books
            WHERE {where_sql}
              AND isbn IS NOT NULL
              AND length(isbn)=13
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = [r[0] for r in cur.fetchall()]

        processed = 0
        updated = 0
        for isbn13 in rows:
            processed += 1
            try:
                series = get_series_for_isbn(conn, isbn13, hc)
                if series.get("confidence", 0) >= 0.6 and series.get("series_name"):
                    update_book_row_with_series(conn, isbn13, series)
                    updated += 1
                else:
                    # Mark checked even if not found to avoid immediate reprocessing
                    cur.execute(
                        "UPDATE books SET series_last_checked = CURRENT_TIMESTAMP WHERE isbn = ?",
                        (isbn13,),
                    )
                    conn.commit()
            except Exception:
                # Soft-fail: mark checked, continue
                cur.execute(
                    "UPDATE books SET series_last_checked = CURRENT_TIMESTAMP WHERE isbn = ?",
                    (isbn13,),
                )
                conn.commit()

        print(f"Backfill complete. Processed={processed}, Updated={updated}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill series info from Hardcover")
    default_db = os.path.expanduser("~/.isbn_lot_optimizer/catalog.db")
    parser.add_argument("--db", required=False, default=default_db, help=f"Path to SQLite DB (default: {default_db})")
    parser.add_argument("--limit", type=int, default=500, help="Max number of rows to process (default: 500)")
    parser.add_argument("--only-missing", action="store_true", default=True, help="Only process rows missing series")
    parser.add_argument("--stale-days", type=int, default=30, help="Re-check rows older than N days (default: 30)")
    args = parser.parse_args()
    backfill(args.db, int(args.limit), bool(args.only_missing), int(args.stale_days))


if __name__ == "__main__":
    main()
