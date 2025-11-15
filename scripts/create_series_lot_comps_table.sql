-- Series Lot Market Data Table
-- Stores eBay lot listing data for book series

CREATE TABLE IF NOT EXISTS series_lot_comps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id INTEGER NOT NULL,
    series_title TEXT NOT NULL,
    author_name TEXT,

    -- Listing details
    ebay_url TEXT NOT NULL UNIQUE,
    listing_title TEXT,
    lot_size INTEGER,  -- Number of books in lot
    is_complete_set BOOLEAN DEFAULT 0,  -- Whether advertised as complete set
    condition TEXT,  -- Overall condition or most common condition

    -- Pricing
    price REAL,
    is_sold BOOLEAN DEFAULT 0,  -- True if sold listing, False if active
    price_per_book REAL,  -- Calculated: price / lot_size

    -- Metadata
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    search_query TEXT,  -- Which query found this listing

    -- Indexes for fast lookups
    FOREIGN KEY (series_id) REFERENCES series(id)
);

CREATE INDEX IF NOT EXISTS idx_series_lot_comps_series_id ON series_lot_comps(series_id);
CREATE INDEX IF NOT EXISTS idx_series_lot_comps_lot_size ON series_lot_comps(lot_size);
CREATE INDEX IF NOT EXISTS idx_series_lot_comps_is_sold ON series_lot_comps(is_sold);
CREATE INDEX IF NOT EXISTS idx_series_lot_comps_scraped_at ON series_lot_comps(scraped_at);


-- Series Lot Statistics Table
-- Aggregated stats per series for quick lookups

CREATE TABLE IF NOT EXISTS series_lot_stats (
    series_id INTEGER PRIMARY KEY,
    series_title TEXT NOT NULL,
    author_name TEXT,

    -- Enrichment metadata
    total_lots_found INTEGER DEFAULT 0,
    sold_lots_count INTEGER DEFAULT 0,
    active_lots_count INTEGER DEFAULT 0,

    -- Lot size statistics
    min_lot_size INTEGER,
    max_lot_size INTEGER,
    median_lot_size INTEGER,
    most_common_lot_size INTEGER,

    -- Price statistics (sold listings only)
    min_sold_price REAL,
    median_sold_price REAL,
    max_sold_price REAL,
    median_price_per_book REAL,

    -- Active listing prices
    min_active_price REAL,
    median_active_price REAL,
    max_active_price REAL,

    -- Quality metrics
    has_complete_sets BOOLEAN DEFAULT 0,  -- Whether any complete sets found
    enrichment_quality_score REAL,  -- Based on number and variety of comps

    -- Timestamps
    enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (series_id) REFERENCES series(id)
);

CREATE INDEX IF NOT EXISTS idx_series_lot_stats_enrichment_quality ON series_lot_stats(enrichment_quality_score);
CREATE INDEX IF NOT EXISTS idx_series_lot_stats_total_lots ON series_lot_stats(total_lots_found);
