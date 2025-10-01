-- Add series columns to books (SQLite)
-- Note: ALTER TABLE ... ADD COLUMN IF NOT EXISTS requires SQLite 3.35+.
-- If your SQLite is older, the code path ensure_series_schema() will add columns dynamically.
ALTER TABLE books ADD COLUMN IF NOT EXISTS series_name TEXT;
ALTER TABLE books ADD COLUMN IF NOT EXISTS series_slug TEXT;
ALTER TABLE books ADD COLUMN IF NOT EXISTS series_id_hardcover INTEGER;
ALTER TABLE books ADD COLUMN IF NOT EXISTS series_position REAL;
ALTER TABLE books ADD COLUMN IF NOT EXISTS series_confidence REAL DEFAULT 0;
ALTER TABLE books ADD COLUMN IF NOT EXISTS series_last_checked TIMESTAMP;

-- series_peers table
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
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(series_id_hardcover, peer_title, peer_position)
);

-- hc_cache table for API responses
CREATE TABLE IF NOT EXISTS hc_cache (
  key TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
