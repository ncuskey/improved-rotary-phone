-- Migration: Add timestamp tracking for all API fetches to enable smart refresh
-- This allows intelligent refresh logic that avoids redundant API calls

-- Track when market data (eBay) was last fetched
ALTER TABLE books ADD COLUMN IF NOT EXISTS market_fetched_at TEXT;

-- Track when metadata (Google Books API) was last fetched
ALTER TABLE books ADD COLUMN IF NOT EXISTS metadata_fetched_at TEXT;

-- Create indexes for efficient staleness queries
CREATE INDEX IF NOT EXISTS idx_books_market_fetched_at
ON books(market_fetched_at);

CREATE INDEX IF NOT EXISTS idx_books_metadata_fetched_at
ON books(metadata_fetched_at);
