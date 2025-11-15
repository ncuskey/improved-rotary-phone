#!/bin/bash
# Monitor enrichment process and send iMessage updates

LOG_FILE="/tmp/enrichment_optimized_full.log"
STATE_FILE="/tmp/enrichment_monitor_state.txt"
PHONE_NUMBER="your_phone_number_here"  # Update this with your phone number or iMessage email

# Function to send iMessage
send_imessage() {
    local message="$1"
    osascript -e "tell application \"Messages\" to send \"$message\" to buddy \"$PHONE_NUMBER\""
}

# Check if log file exists
if [ ! -f "$LOG_FILE" ]; then
    send_imessage "Enrichment monitor: Log file not found. Process may not be running."
    exit 1
fi

# Extract key metrics from log
total_isbns=$(grep -oE "Found [0-9]+ ISBNs needing market data enrichment" "$LOG_FILE" | head -1 | grep -oE "[0-9]+")
enriched=$(grep -oE "Total enriched: [0-9]+" "$LOG_FILE" | tail -1 | grep -oE "[0-9]+")
last_rate=$(grep -oE "Rate: [0-9]+\.[0-9]+ ISBNs/sec" "$LOG_FILE" | tail -1 | grep -oE "[0-9]+\.[0-9]+")
last_progress=$(grep -oE "Progress: [0-9]+/[0-9]+ ISBNs \([0-9]+\.[0-9]+%\)" "$LOG_FILE" | tail -1)

# Check if process is still running
if pgrep -f "enrich_metadata_cache_market_data.py" > /dev/null; then
    status="Running"
else
    status="Stopped/Complete"
fi

# Calculate progress
if [ -n "$total_isbns" ] && [ -n "$enriched" ]; then
    percent_enriched=$(echo "scale=1; ($enriched / $total_isbns) * 100" | bc)

    # Estimate time remaining
    if [ -n "$last_rate" ] && [ "$last_rate" != "0.00" ]; then
        remaining=$((total_isbns - enriched))
        eta_seconds=$(echo "scale=0; $remaining / $last_rate" | bc)
        eta_hours=$(echo "scale=1; $eta_seconds / 3600" | bc)
    else
        eta_hours="Unknown"
    fi
else
    percent_enriched="0.0"
    eta_hours="Unknown"
fi

# Read last reported progress
last_reported=0
if [ -f "$STATE_FILE" ]; then
    last_reported=$(cat "$STATE_FILE")
fi

# Only send update if progress changed significantly (at least 5% or status changed)
current_progress=${enriched:-0}
progress_diff=$((current_progress - last_reported))

# Build status message
message="📊 ISBN Enrichment Status
━━━━━━━━━━━━━━━━━━
Status: $status
Progress: ${enriched:-0}/${total_isbns:-0} ISBNs (${percent_enriched}%)
Success Rate: ${percent_enriched}%
Current Rate: ${last_rate:-0.00} ISBNs/sec
ETA: ${eta_hours} hours

Last batch: $last_progress"

# Send update if:
# 1. Progress increased by at least 100 ISBNs
# 2. Process stopped/completed
# 3. First run (no state file)
if [ ! -f "$STATE_FILE" ] || [ $progress_diff -ge 100 ] || [ "$status" = "Stopped/Complete" ]; then
    send_imessage "$message"
    echo "$current_progress" > "$STATE_FILE"
fi

# If process completed, send final summary
if [ "$status" = "Stopped/Complete" ] && grep -q "ENRICHMENT COMPLETE" "$LOG_FILE"; then
    final_stats=$(grep -A 10 "ENRICHMENT COMPLETE" "$LOG_FILE" | head -15)
    send_imessage "✅ Enrichment Complete!

$final_stats"
fi
