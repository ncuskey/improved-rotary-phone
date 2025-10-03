#!/bin/bash
# Test script to scan an ISBN via the web API

echo "Testing ISBN scan endpoint..."
echo ""

# Test with a valid ISBN (The Great Gatsby)
ISBN="9780743273565"
CONDITION="Good"

echo "Scanning ISBN: $ISBN"
echo "Condition: $CONDITION"
echo ""

# Make the request
curl -s -X POST "http://127.0.0.1:8000/api/books/scan" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "isbn=$ISBN&condition=$CONDITION&edition=" \
  -o /tmp/scan_result.html

if [ $? -eq 0 ]; then
    echo "✓ Scan request successful"
    echo ""
    echo "Response saved to /tmp/scan_result.html"
    echo ""

    # Check if the ISBN appears in the response
    if grep -q "$ISBN" /tmp/scan_result.html; then
        echo "✓ ISBN $ISBN found in response"
    else
        echo "✗ ISBN not found in response"
    fi

    # List books via API
    echo ""
    echo "Fetching book list..."
    curl -s "http://127.0.0.1:8000/api/books" | grep -o "$ISBN" | head -1

    if [ $? -eq 0 ]; then
        echo "✓ Book appears in listing"
    fi
else
    echo "✗ Scan request failed"
    exit 1
fi

echo ""
echo "Open http://127.0.0.1:8000 in your browser to see the full UI"
