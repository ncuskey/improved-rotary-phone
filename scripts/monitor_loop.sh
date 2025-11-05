#!/bin/bash
# Monitor BookFinder scrapes every 5 minutes

LOG_FILE="/tmp/bookfinder_monitor.log"

echo "==============================================================" >> "$LOG_FILE"
echo "Started monitoring at $(date)" >> "$LOG_FILE"
echo "==============================================================" >> "$LOG_FILE"

while true; do
    echo "" >> "$LOG_FILE"
    echo "--- Check at $(date) ---" >> "$LOG_FILE"

    # Check if processes are still running
    if ps aux | grep -q "[c]ollect_bookfinder_prices.py --source catalog"; then
        echo "✅ Catalog scrape is running" >> "$LOG_FILE"
    else
        echo "❌ Catalog scrape has stopped" >> "$LOG_FILE"
    fi

    if ps aux | grep -q "[c]ollect_bookfinder_prices.py --source metadata_cache"; then
        echo "✅ Metadata scrape is running" >> "$LOG_FILE"
    else
        echo "❌ Metadata scrape has stopped" >> "$LOG_FILE"
    fi

    # Run progress report
    cd /Users/nickcuskey/ISBN
    ./.venv/bin/python3 scripts/monitor_bookfinder_scrapes.py >> "$LOG_FILE"

    # Wait 5 minutes
    sleep 300
done
