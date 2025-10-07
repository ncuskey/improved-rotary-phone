-- Add sold comps pricing columns to books table
-- Track A/B dual-track implementation for sold comparables

ALTER TABLE books ADD COLUMN sold_comps_count INTEGER;
ALTER TABLE books ADD COLUMN sold_comps_min REAL;
ALTER TABLE books ADD COLUMN sold_comps_median REAL;
ALTER TABLE books ADD COLUMN sold_comps_max REAL;
ALTER TABLE books ADD COLUMN sold_comps_is_estimate INTEGER DEFAULT 1;  -- 1=Track B estimate, 0=Track A real
ALTER TABLE books ADD COLUMN sold_comps_source TEXT;  -- "estimate" or "marketplace_insights"
