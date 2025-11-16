-- Migration: Add first_edition column to books table
-- Date: 2025-11-15
-- Purpose: Support first edition detection for collectible book pricing

ALTER TABLE books ADD COLUMN first_edition INTEGER DEFAULT 0;

-- Verify the column was added
-- PRAGMA table_info(books);
