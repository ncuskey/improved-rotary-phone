#!/bin/bash
# Monitor BookFinder scrapes and send SMS at milestones

LOG_FILE="/tmp/bookfinder_sms_monitor.log"
YOUR_PHONE="+12087201241"

# Track milestones
LAST_100_MILESTONE=0
LAST_10K_OFFERS=0

echo "==============================================================" >> "$LOG_FILE"
echo "Started SMS monitoring at $(date)" >> "$LOG_FILE"
echo "==============================================================" >> "$LOG_FILE"

while true; do
    # Get current stats from database
    cd /Users/nickcuskey/ISBN
    COMPLETED=$(sqlite3 ~/.isbn_lot_optimizer/catalog.db "SELECT COUNT(*) FROM bookfinder_progress WHERE status='completed'")
    OFFERS=$(sqlite3 ~/.isbn_lot_optimizer/catalog.db "SELECT COUNT(*) FROM bookfinder_offers")

    # Check for 100 ISBN milestone
    CURRENT_100_MILESTONE=$((COMPLETED / 100))
    if [ $CURRENT_100_MILESTONE -gt $LAST_100_MILESTONE ]; then
        echo "$(date): Reached ${CURRENT_100_MILESTONE}00 ISBNs milestone" >> "$LOG_FILE"
        python scripts/send_sms_update.py --to "$YOUR_PHONE" >> "$LOG_FILE" 2>&1
        LAST_100_MILESTONE=$CURRENT_100_MILESTONE
    fi

    # Check for 10K offers milestone
    CURRENT_10K_OFFERS=$((OFFERS / 10000))
    if [ $CURRENT_10K_OFFERS -gt $LAST_10K_OFFERS ]; then
        echo "$(date): Reached ${CURRENT_10K_OFFERS}0K offers milestone" >> "$LOG_FILE"
        python scripts/send_sms_update.py --to "$YOUR_PHONE" >> "$LOG_FILE" 2>&1
        LAST_10K_OFFERS=$CURRENT_10K_OFFERS
    fi

    # Check if catalog scrape completed
    if [ $COMPLETED -ge 760 ]; then
        echo "$(date): Catalog scrape COMPLETED!" >> "$LOG_FILE"
        python scripts/send_sms_update.py --to "$YOUR_PHONE" >> "$LOG_FILE" 2>&1
        echo "🎉 Catalog scrape completed at $(date)" >> "$LOG_FILE"
        # Send one final notification and exit
        sleep 60
        break
    fi

    # Wait 15 minutes before next check
    sleep 900
done

echo "SMS monitoring stopped at $(date)" >> "$LOG_FILE"
