#!/bin/bash
# Monitor enrichment process and send iMessage updates every 30 minutes

LOG_FILE="/tmp/enrichment_monitor_loop.log"

echo "==============================================================" >> "$LOG_FILE"
echo "Started enrichment monitoring at $(date)" >> "$LOG_FILE"
echo "Monitoring /tmp/enrichment_reprocess_all.log" >> "$LOG_FILE"
echo "Sending updates every 30 minutes" >> "$LOG_FILE"
echo "==============================================================" >> "$LOG_FILE"

while true; do
    cd /Users/nickcuskey/ISBN

    # Check if enrichment process is still running
    if ! pgrep -f "enrich_metadata_cache_market_data.py" > /dev/null; then
        echo "$(date): Enrichment process not running, sending final update..." >> "$LOG_FILE"
        python scripts/monitor_enrichment.py >> "$LOG_FILE" 2>&1
        echo "$(date): Monitoring stopped - process complete" >> "$LOG_FILE"
        break
    fi

    # Run the Python monitoring script
    echo "$(date): Checking enrichment progress..." >> "$LOG_FILE"
    python scripts/monitor_enrichment.py >> "$LOG_FILE" 2>&1

    # Wait 30 minutes before next check
    sleep 1800
done

echo "Enrichment monitoring stopped at $(date)" >> "$LOG_FILE"
