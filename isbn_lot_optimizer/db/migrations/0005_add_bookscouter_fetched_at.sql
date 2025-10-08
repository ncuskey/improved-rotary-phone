-- Migration: Add bookscouter_fetched_at timestamp for tracking API call freshness
-- This enables intelligent refresh logic to only update stale data

ALTER TABLE books ADD COLUMN IF NOT EXISTS bookscouter_fetched_at TEXT;

-- Create index for efficient queries on stale data
CREATE INDEX IF NOT EXISTS idx_books_bookscouter_fetched_at
ON books(bookscouter_fetched_at);
