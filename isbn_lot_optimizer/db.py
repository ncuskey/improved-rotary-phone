import json, sqlite3
from pathlib import Path


def connect(db_path: Path | str) -> sqlite3.Connection:
    p = Path(db_path).expanduser()
    if p.is_dir():
        p = p / "catalog.db"
    if not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn


def list_books(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM books ORDER BY updated_at DESC").fetchall()

def update_book_metadata(conn: sqlite3.Connection, isbn: str, meta: dict | None):
    """
    Write normalized fields into scalar columns (title/authors/publication_year)
    and store the full dict in metadata_json. Keep existing values if new ones are None.
    """
    if not meta:
        return
    title = meta.get("title")
    authors = meta.get("authors_str") or (", ".join(meta.get("authors") or []) or None)
    publication_year = meta.get("publication_year")
    metadata_json = json.dumps(meta, ensure_ascii=False)

    conn.execute("""
        UPDATE books SET
          title = COALESCE(:title, title),
          authors = COALESCE(:authors, authors),
          publication_year = COALESCE(:publication_year, publication_year),
          metadata_json = :metadata_json,
          updated_at = CURRENT_TIMESTAMP
        WHERE isbn = :isbn
    """, {
        "isbn": isbn,
        "title": title,
        "authors": authors,
        "publication_year": publication_year,
        "metadata_json": metadata_json,
    })
