#!/bin/bash
# Monitor log file for 429 rate limit errors in real-time

LOG_FILE="${1:-/tmp/sold_metadata_cache_full.log}"
CHECK_INTERVAL=5  # seconds

echo "Monitoring: $LOG_FILE"
echo "Checking for 429 rate limit errors every ${CHECK_INTERVAL}s"
echo "Press Ctrl+C to stop"
echo ""

last_line=0

while true; do
    # Count total 429 errors (excluding timestamps)
    error_count=$(grep -i "serper api error: 429\|status.*429" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')

    # Get latest progress lines
    latest_progress=$(grep -E "Progress:|Rate:|Total saved:" "$LOG_FILE" 2>/dev/null | tail -3)

    # Get current line count
    current_line=$(wc -l < "$LOG_FILE" 2>/dev/null)

    clear
    echo "=================================="
    echo "  RATE LIMIT MONITOR"
    echo "=================================="
    echo "File: $LOG_FILE"
    echo "Updated: $(date '+%H:%M:%S')"
    echo ""

    if [ "$error_count" -gt 0 ]; then
        echo "⚠️  WARNING: $error_count rate limit errors detected!"
        echo ""
        echo "Recent errors:"
        grep -i "serper api error: 429\|status.*429" "$LOG_FILE" 2>/dev/null | tail -5
    else
        echo "✓ No rate limit errors detected"
    fi

    echo ""
    echo "Latest Progress:"
    if [ -n "$latest_progress" ]; then
        echo "$latest_progress"
    else
        echo "  (waiting for first batch to complete...)"
    fi

    echo ""
    echo "Log activity: $current_line lines (+$((current_line - last_line)) since last check)"

    last_line=$current_line
    sleep $CHECK_INTERVAL
done
