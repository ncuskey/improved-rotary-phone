-- Migration: Add bookscouter_json column for multi-vendor buyback data
-- This stores the full BookScouter API response with all vendor offers

ALTER TABLE books ADD COLUMN bookscouter_json TEXT;
