#!/bin/bash
# Monitor BookFinder scrapes and send iMessage at milestones

LOG_FILE="/tmp/bookfinder_imessage_monitor.log"

# Track milestones for both scrapers
CATALOG_LAST_50=0
CATALOG_LAST_5K_OFFERS=0
METADATA_LAST_100=0
METADATA_LAST_10K_OFFERS=0

echo "==============================================================" >> "$LOG_FILE"
echo "Started iMessage monitoring at $(date)" >> "$LOG_FILE"
echo "Monitoring BOTH catalog and metadata_cache scrapers" >> "$LOG_FILE"
echo "==============================================================" >> "$LOG_FILE"

while true; do
    cd /Users/nickcuskey/ISBN

    # === CATALOG SCRAPER ===
    CATALOG_COMPLETED=$(sqlite3 ~/.isbn_lot_optimizer/catalog.db "SELECT COUNT(*) FROM bookfinder_progress WHERE status='completed'" 2>/dev/null || echo "0")
    CATALOG_OFFERS=$(sqlite3 ~/.isbn_lot_optimizer/catalog.db "SELECT COUNT(*) FROM bookfinder_offers" 2>/dev/null || echo "0")

    # Check catalog 50 ISBN milestone
    CURRENT_50=$((CATALOG_COMPLETED / 50))
    if [ $CURRENT_50 -gt $CATALOG_LAST_50 ]; then
        MILESTONE_COUNT=$((CURRENT_50 * 50))
        echo "$(date): CATALOG reached ${MILESTONE_COUNT} ISBNs" >> "$LOG_FILE"
        python scripts/send_imessage_update.py >> "$LOG_FILE" 2>&1
        CATALOG_LAST_50=$CURRENT_50
    fi

    # Check catalog 5K offers milestone
    CURRENT_5K=$((CATALOG_OFFERS / 5000))
    if [ $CURRENT_5K -gt $CATALOG_LAST_5K_OFFERS ]; then
        MILESTONE_COUNT=$((CURRENT_5K * 5000))
        echo "$(date): CATALOG reached ${MILESTONE_COUNT} offers" >> "$LOG_FILE"
        python scripts/send_imessage_update.py >> "$LOG_FILE" 2>&1
        CATALOG_LAST_5K_OFFERS=$CURRENT_5K
    fi

    # === METADATA_CACHE SCRAPER ===
    if [ -f ~/.isbn_lot_optimizer/metadata_cache.db ]; then
        METADATA_COMPLETED=$(sqlite3 ~/.isbn_lot_optimizer/metadata_cache.db "SELECT COUNT(*) FROM bookfinder_progress WHERE status='completed'" 2>/dev/null || echo "0")
        METADATA_OFFERS=$(sqlite3 ~/.isbn_lot_optimizer/metadata_cache.db "SELECT COUNT(*) FROM bookfinder_offers" 2>/dev/null || echo "0")

        # Check metadata_cache 100 ISBN milestone (larger intervals for 18K ISBNs)
        CURRENT_100=$((METADATA_COMPLETED / 100))
        if [ $CURRENT_100 -gt $METADATA_LAST_100 ]; then
            MILESTONE_COUNT=$((CURRENT_100 * 100))
            echo "$(date): METADATA_CACHE reached ${MILESTONE_COUNT} ISBNs" >> "$LOG_FILE"
            python scripts/send_imessage_update.py >> "$LOG_FILE" 2>&1
            METADATA_LAST_100=$CURRENT_100
        fi

        # Check metadata_cache 10K offers milestone
        CURRENT_10K=$((METADATA_OFFERS / 10000))
        if [ $CURRENT_10K -gt $METADATA_LAST_10K_OFFERS ]; then
            MILESTONE_COUNT=$((CURRENT_10K * 10000))
            echo "$(date): METADATA_CACHE reached ${MILESTONE_COUNT} offers" >> "$LOG_FILE"
            python scripts/send_imessage_update.py >> "$LOG_FILE" 2>&1
            METADATA_LAST_10K_OFFERS=$CURRENT_10K
        fi
    fi

    # Check if both scrapers completed
    CATALOG_DONE=false
    METADATA_DONE=false

    if [ $CATALOG_COMPLETED -ge 760 ]; then
        CATALOG_DONE=true
    fi

    if [ -f ~/.isbn_lot_optimizer/metadata_cache.db ] && [ $METADATA_COMPLETED -ge 18727 ]; then
        METADATA_DONE=true
    fi

    # Send final message when both complete
    if [ "$CATALOG_DONE" = true ] && [ "$METADATA_DONE" = true ]; then
        echo "$(date): BOTH SCRAPERS COMPLETED!" >> "$LOG_FILE"
        python scripts/send_imessage_update.py >> "$LOG_FILE" 2>&1
        echo "🎉 All scraping completed at $(date)" >> "$LOG_FILE"
        sleep 60
        break
    fi

    # Wait 15 minutes before next check
    sleep 900
done

echo "iMessage monitoring stopped at $(date)" >> "$LOG_FILE"
