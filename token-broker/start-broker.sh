#!/bin/bash
# Token Broker Startup Script
# Starts the eBay token broker if not already running

set -e

BROKER_DIR="/Users/nickcuskey/ISBN/token-broker"
ENV_FILE="/Users/nickcuskey/ISBN/.env"
PORT=8787
LOG_FILE="$BROKER_DIR/broker.log"

# Check if broker is already running
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    # Already running, exit silently
    exit 0
fi

# Source environment variables
if [ -f "$ENV_FILE" ]; then
    # Extract just the eBay credentials
    export EBAY_APP_ID=$(grep '^EBAY_CLIENT_ID=' "$ENV_FILE" | cut -d'=' -f2)
    export EBAY_APP_SECRET=$(grep '^EBAY_CLIENT_SECRET=' "$ENV_FILE" | cut -d'=' -f2)
fi

# Start the broker in the background
cd "$BROKER_DIR"
PORT=$PORT node server.js > "$LOG_FILE" 2>&1 &

# Wait for it to start
for i in {1..5}; do
    sleep 0.5
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        exit 0
    fi
done

# If we get here, it didn't start
echo "⚠️  Token broker failed to start on port $PORT" >&2
echo "   Check logs: $LOG_FILE" >&2
exit 1
