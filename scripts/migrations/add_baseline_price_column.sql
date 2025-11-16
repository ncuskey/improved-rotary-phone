-- Migration: Add baseline_price column to books table
-- Date: 2025-11-15
-- Purpose: Store immutable ML baseline price to prevent compounding multipliers

-- Add the column
ALTER TABLE books ADD COLUMN baseline_price REAL DEFAULT NULL;

-- Populate baseline_price from current estimated_price for existing records
UPDATE books SET baseline_price = estimated_price WHERE baseline_price IS NULL;

-- Going forward:
-- - baseline_price: Original ML prediction (never changes after initial calculation)
-- - estimated_price: Current price after applying attribute multipliers (updates when attributes change)
