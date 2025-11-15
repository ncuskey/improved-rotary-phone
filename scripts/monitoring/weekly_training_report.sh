#!/bin/bash
#
# Weekly Training Data Quality Report
# Monitors training data quality, completeness, and freshness
#
# Schedule with cron:
#   0 9 * * MON /path/to/weekly_training_report.sh
#

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="/tmp/training_report_${TIMESTAMP}.txt"
METADATA_CACHE_DB="${HOME}/.isbn_lot_optimizer/metadata_cache.db"
CATALOG_DB="${HOME}/.isbn_lot_optimizer/catalog.db"

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "WEEKLY TRAINING DATA QUALITY REPORT"
echo "========================================================================"
echo "Date: $(date)" | tee "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

if [ ! -f "$METADATA_CACHE_DB" ]; then
    echo -e "${RED}✗ metadata_cache.db not found at: $METADATA_CACHE_DB${NC}" | tee -a "$REPORT_FILE"
    exit 1
fi

if [ ! -f "$CATALOG_DB" ]; then
    echo -e "${RED}✗ catalog.db not found at: $CATALOG_DB${NC}" | tee -a "$REPORT_FILE"
    exit 1
fi

# 1. OVERALL STATISTICS
echo "=== OVERALL STATISTICS ===" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

sqlite3 "$METADATA_CACHE_DB" <<EOF | tee -a "$REPORT_FILE"
.mode column
.headers on
SELECT
    'Total ISBNs' as metric,
    COUNT(*) as value
FROM cached_books
UNION ALL
SELECT
    'Training Eligible',
    SUM(CASE WHEN in_training=1 THEN 1 ELSE 0 END)
FROM cached_books
UNION ALL
SELECT
    'Avg Training Quality',
    ROUND(AVG(training_quality_score), 3)
FROM cached_books WHERE in_training=1
UNION ALL
SELECT
    'Avg Metadata Quality',
    ROUND(AVG(quality_score), 3)
FROM cached_books WHERE in_training=1;
EOF

echo "" | tee -a "$REPORT_FILE"

# 2. FEATURE COMPLETENESS
echo "=== FEATURE COMPLETENESS (Training Books Only) ===" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

sqlite3 "$METADATA_CACHE_DB" <<EOF | tee -a "$REPORT_FILE"
.mode column
.headers on
SELECT
    'Market Data (market_json)' as feature,
    SUM(CASE WHEN market_json IS NOT NULL AND market_json != '{}' THEN 1 ELSE 0 END) as count,
    ROUND(AVG(CASE WHEN market_json IS NOT NULL AND market_json != '{}' THEN 100.0 ELSE 0.0 END), 1) || '%' as percentage
FROM cached_books WHERE in_training=1
UNION ALL
SELECT
    'BookScouter Data',
    SUM(CASE WHEN bookscouter_json IS NOT NULL AND bookscouter_json != '{}' THEN 1 ELSE 0 END),
    ROUND(AVG(CASE WHEN bookscouter_json IS NOT NULL AND bookscouter_json != '{}' THEN 100.0 ELSE 0.0 END), 1) || '%'
FROM cached_books WHERE in_training=1
UNION ALL
SELECT
    'Cover Type',
    SUM(CASE WHEN cover_type IS NOT NULL THEN 1 ELSE 0 END),
    ROUND(AVG(CASE WHEN cover_type IS NOT NULL THEN 100.0 ELSE 0.0 END), 1) || '%'
FROM cached_books WHERE in_training=1
UNION ALL
SELECT
    'Signed Flag',
    SUM(CASE WHEN signed IS NOT NULL THEN 1 ELSE 0 END),
    ROUND(AVG(CASE WHEN signed IS NOT NULL THEN 100.0 ELSE 0.0 END), 1) || '%'
FROM cached_books WHERE in_training=1
UNION ALL
SELECT
    'Printing Info',
    SUM(CASE WHEN printing IS NOT NULL THEN 1 ELSE 0 END),
    ROUND(AVG(CASE WHEN printing IS NOT NULL THEN 100.0 ELSE 0.0 END), 1) || '%'
FROM cached_books WHERE in_training=1
UNION ALL
SELECT
    'Sold Comps (>=8)',
    SUM(CASE WHEN sold_comps_count >= 8 THEN 1 ELSE 0 END),
    ROUND(AVG(CASE WHEN sold_comps_count >= 8 THEN 100.0 ELSE 0.0 END), 1) || '%'
FROM cached_books WHERE in_training=1;
EOF

echo "" | tee -a "$REPORT_FILE"

# 3. QUALITY SCORE DISTRIBUTION
echo "=== QUALITY SCORE DISTRIBUTION ===" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

sqlite3 "$METADATA_CACHE_DB" <<EOF | tee -a "$REPORT_FILE"
.mode column
.headers on
SELECT
    CASE
        WHEN training_quality_score >= 0.8 THEN 'Excellent (0.8-1.0)'
        WHEN training_quality_score >= 0.6 THEN 'Good (0.6-0.8)'
        WHEN training_quality_score >= 0.4 THEN 'Fair (0.4-0.6)'
        ELSE 'Poor (0.0-0.4)'
    END as tier,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM cached_books WHERE in_training=1), 1) || '%' as percentage
FROM cached_books
WHERE in_training=1
GROUP BY tier
ORDER BY tier DESC;
EOF

echo "" | tee -a "$REPORT_FILE"

# 4. PRICE DISTRIBUTION
echo "=== PRICE DISTRIBUTION (Training Books) ===" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

sqlite3 "$METADATA_CACHE_DB" <<EOF | tee -a "$REPORT_FILE"
.mode column
.headers on
SELECT
    CASE
        WHEN sold_comps_median >= 50 THEN '$50+ (Premium)'
        WHEN sold_comps_median >= 15 THEN '$15-49 (High)'
        WHEN sold_comps_median >= 5 THEN '$5-14 (Medium)'
        ELSE '$0-4 (Low)'
    END as price_tier,
    COUNT(*) as count,
    ROUND(AVG(sold_comps_median), 2) as avg_price,
    ROUND(MIN(sold_comps_median), 2) as min_price,
    ROUND(MAX(sold_comps_median), 2) as max_price
FROM cached_books
WHERE in_training=1 AND sold_comps_median IS NOT NULL
GROUP BY price_tier
ORDER BY avg_price DESC;
EOF

echo "" | tee -a "$REPORT_FILE"

# 5. DATA STALENESS
echo "=== DATA FRESHNESS ===" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Count stale data
STALE_MARKET=$(sqlite3 "$METADATA_CACHE_DB" "SELECT COUNT(*) FROM cached_books WHERE in_training=1 AND (market_fetched_at IS NULL OR market_fetched_at < datetime('now', '-30 days'))")
STALE_METADATA=$(sqlite3 "$METADATA_CACHE_DB" "SELECT COUNT(*) FROM cached_books WHERE in_training=1 AND (metadata_fetched_at IS NULL OR metadata_fetched_at < datetime('now', '-90 days'))")
TOTAL_TRAINING=$(sqlite3 "$METADATA_CACHE_DB" "SELECT COUNT(*) FROM cached_books WHERE in_training=1")

echo "Market data >30 days old: $STALE_MARKET / $TOTAL_TRAINING" | tee -a "$REPORT_FILE"
echo "Metadata >90 days old: $STALE_METADATA / $TOTAL_TRAINING" | tee -a "$REPORT_FILE"

STALE_MARKET_PCT=$(echo "scale=1; $STALE_MARKET * 100 / $TOTAL_TRAINING" | bc)

if [ $(echo "$STALE_MARKET_PCT > 20" | bc) -eq 1 ]; then
    echo -e "${YELLOW}⚠ WARNING: ${STALE_MARKET_PCT}% of training data has stale market data${NC}" | tee -a "$REPORT_FILE"
fi

echo "" | tee -a "$REPORT_FILE"

# 6. CATALOG STATUS
echo "=== CATALOG.DB STATUS ===" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

sqlite3 "$CATALOG_DB" <<EOF | tee -a "$REPORT_FILE"
.mode column
.headers on
SELECT
    'Total Books' as metric,
    COUNT(*) as value
FROM books
UNION ALL
SELECT
    'Status=ACCEPT',
    SUM(CASE WHEN status='ACCEPT' THEN 1 ELSE 0 END)
FROM books
UNION ALL
SELECT
    'With Sold Comps',
    SUM(CASE WHEN sold_comps_count >= 5 THEN 1 ELSE 0 END)
FROM books;
EOF

echo "" | tee -a "$REPORT_FILE"

# 7. RECOMMENDATIONS
echo "=== RECOMMENDATIONS ===" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Generate recommendations based on findings
if [ "$STALE_MARKET" -gt 0 ]; then
    echo "• Refresh market data for $STALE_MARKET training books" | tee -a "$REPORT_FILE"
fi

MISSING_COVER=$(sqlite3 "$METADATA_CACHE_DB" "SELECT COUNT(*) FROM cached_books WHERE in_training=1 AND cover_type IS NULL")
if [ "$MISSING_COVER" -gt 0 ]; then
    echo "• Enrich $MISSING_COVER training books with cover_type attribute" | tee -a "$REPORT_FILE"
fi

MISSING_PRINTING=$(sqlite3 "$METADATA_CACHE_DB" "SELECT COUNT(*) FROM cached_books WHERE in_training=1 AND printing IS NULL")
if [ "$MISSING_PRINTING" -gt 0 ]; then
    echo "• Enrich $MISSING_PRINTING training books with printing information" | tee -a "$REPORT_FILE"
fi

LOW_COMPS=$(sqlite3 "$METADATA_CACHE_DB" "SELECT COUNT(*) FROM cached_books WHERE in_training=1 AND sold_comps_count < 8")
if [ "$LOW_COMPS" -gt 0 ]; then
    echo "• Consider collecting more sold comps for $LOW_COMPS training books" | tee -a "$REPORT_FILE"
fi

echo "" | tee -a "$REPORT_FILE"

echo "========================================================================"
echo "REPORT COMPLETE"
echo "========================================================================"
echo ""
echo "Full report saved to: $REPORT_FILE"
echo ""
echo -e "${GREEN}To schedule this report weekly, add to crontab:${NC}"
echo "  0 9 * * MON $(realpath $0)"
