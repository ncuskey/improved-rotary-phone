#!/bin/bash
#
# Stale Data Alert Script
# Checks for stale market data in training database and sends alerts
#
# Schedule with cron (daily at 6am):
#   0 6 * * * /path/to/stale_data_alert.sh
#

set -e

METADATA_CACHE_DB="${HOME}/.isbn_lot_optimizer/metadata_cache.db"
THRESHOLD_PERCENT=20  # Alert if >20% of training data is stale
MARKET_DATA_DAYS=30   # Consider market data stale after 30 days
METADATA_DAYS=90      # Consider metadata stale after 90 days

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "STALE DATA ALERT CHECK"
echo "========================================================================"
echo "Date: $(date)"
echo ""

if [ ! -f "$METADATA_CACHE_DB" ]; then
    echo -e "${RED}✗ metadata_cache.db not found at: $METADATA_CACHE_DB${NC}"
    exit 1
fi

# Count total training books
TOTAL_TRAINING=$(sqlite3 "$METADATA_CACHE_DB" "SELECT COUNT(*) FROM cached_books WHERE in_training=1")
echo "Total training books: $TOTAL_TRAINING"

# Count stale market data
STALE_MARKET=$(sqlite3 "$METADATA_CACHE_DB" "SELECT COUNT(*) FROM cached_books WHERE in_training=1 AND (market_fetched_at IS NULL OR market_fetched_at < datetime('now', '-$MARKET_DATA_DAYS days'))")
STALE_MARKET_PCT=$(echo "scale=1; $STALE_MARKET * 100 / $TOTAL_TRAINING" | bc)

echo "Stale market data (>$MARKET_DATA_DAYS days): $STALE_MARKET ($STALE_MARKET_PCT%)"

# Count stale metadata
STALE_METADATA=$(sqlite3 "$METADATA_CACHE_DB" "SELECT COUNT(*) FROM cached_books WHERE in_training=1 AND (metadata_fetched_at IS NULL OR metadata_fetched_at < datetime('now', '-$METADATA_DAYS days'))")
STALE_METADATA_PCT=$(echo "scale=1; $STALE_METADATA * 100 / $TOTAL_TRAINING" | bc)

echo "Stale metadata (>$METADATA_DAYS days): $STALE_METADATA ($STALE_METADATA_PCT%)"
echo ""

# Check thresholds and alert
ALERT_TRIGGERED=false

if [ $(echo "$STALE_MARKET_PCT > $THRESHOLD_PERCENT" | bc) -eq 1 ]; then
    echo -e "${RED}========================================================================${NC}"
    echo -e "${RED}⚠️  ALERT: STALE MARKET DATA THRESHOLD EXCEEDED${NC}"
    echo -e "${RED}========================================================================${NC}"
    echo ""
    echo -e "${YELLOW}$STALE_MARKET_PCT% of training books have market data older than $MARKET_DATA_DAYS days${NC}"
    echo -e "${YELLOW}Threshold: $THRESHOLD_PERCENT%${NC}"
    echo ""
    echo "This may impact ML model accuracy. Consider refreshing market data."
    echo ""

    # List top 10 stale books
    echo "Top 10 books with oldest market data:"
    sqlite3 "$METADATA_CACHE_DB" <<EOF
.mode column
.headers on
SELECT
    isbn,
    title,
    market_fetched_at,
    ROUND(JULIANDAY('now') - JULIANDAY(market_fetched_at)) as days_old
FROM cached_books
WHERE in_training=1 AND market_fetched_at IS NOT NULL
ORDER BY market_fetched_at ASC
LIMIT 10;
EOF
    echo ""

    ALERT_TRIGGERED=true
fi

if [ $(echo "$STALE_METADATA_PCT > $THRESHOLD_PERCENT" | bc) -eq 1 ]; then
    echo -e "${YELLOW}========================================================================${NC}"
    echo -e "${YELLOW}⚠️  WARNING: STALE METADATA THRESHOLD EXCEEDED${NC}"
    echo -e "${YELLOW}========================================================================${NC}"
    echo ""
    echo "$STALE_METADATA_PCT% of training books have metadata older than $METADATA_DAYS days"
    echo "Threshold: $THRESHOLD_PERCENT%"
    echo ""
    echo "Consider refreshing metadata for improved training data quality."
    echo ""

    ALERT_TRIGGERED=true
fi

if [ "$ALERT_TRIGGERED" = false ]; then
    echo -e "${GREEN}✓ All checks passed - data freshness within acceptable limits${NC}"
    echo ""
fi

# Remediation suggestions
if [ "$ALERT_TRIGGERED" = true ]; then
    echo "========================================================================"
    echo "REMEDIATION SUGGESTIONS"
    echo "========================================================================"
    echo ""
    echo "1. Run bulk market data refresh:"
    echo "   python3 scripts/refresh_stale_market_data.py --days $MARKET_DATA_DAYS --limit 100"
    echo ""
    echo "2. Prioritize high-value books for refresh:"
    echo "   sqlite3 $METADATA_CACHE_DB \"SELECT isbn, title, sold_comps_median FROM cached_books WHERE in_training=1 AND market_fetched_at < datetime('now', '-$MARKET_DATA_DAYS days') ORDER BY sold_comps_median DESC LIMIT 50;\""
    echo ""
    echo "3. Check organic growth system is running:"
    echo "   tail -f logs/organic_growth.log"
    echo ""
fi

echo "========================================================================"
echo "STALE DATA CHECK COMPLETE"
echo "========================================================================"
echo ""
echo -e "${GREEN}To schedule this check daily, add to crontab:${NC}"
echo "  0 6 * * * $(realpath $0)"
