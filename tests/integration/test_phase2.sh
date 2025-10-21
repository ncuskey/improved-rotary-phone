#!/bin/bash
# Phase 2 Feature Tests

echo "========================================"
echo "  ISBN Web App - Phase 2 Tests"
echo "========================================"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

success_count=0
fail_count=0

test_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((success_count++))
}

test_fail() {
    echo -e "${RED}✗${NC} $1"
    ((fail_count++))
}

test_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Test 1: Lots API
echo "Test 1: List Lots"
response=$(curl -s "http://127.0.0.1:8000/api/lots")
if echo "$response" | grep -q "lots-container"; then
    test_pass "Lots endpoint returns container"

    # Count lots in response
    lot_count=$(echo "$response" | grep -o "hx-get=\"/api/lots/" | wc -l)
    test_info "Found $lot_count lots"
else
    test_fail "Lots endpoint failed"
fi
echo ""

# Test 2: Lot Regeneration
echo "Test 2: Regenerate Lots"
response=$(curl -s -X POST "http://127.0.0.1:8000/api/lots/regenerate")
if echo "$response" | grep -q "lots-container"; then
    test_pass "Lot regeneration works"
else
    test_fail "Lot regeneration failed"
fi
echo ""

# Test 3: SSE Events Endpoint
echo "Test 3: SSE Events Endpoint"
# Create a background curl that will timeout after 2 seconds
timeout 2s curl -s "http://127.0.0.1:8000/api/events/test-123" > /dev/null 2>&1 &
sleep 1
if ps -p $! > /dev/null 2>&1; then
    test_pass "SSE endpoint accepts connections"
    kill $! 2>/dev/null
else
    test_fail "SSE endpoint not responding"
fi
echo ""

# Test 4: Book Delete
echo "Test 4: Delete Book"
# First, get a book ISBN from the database
test_isbn=$(sqlite3 ~/.isbn_lot_optimizer/catalog.db "SELECT isbn FROM books LIMIT 1;")
if [ -n "$test_isbn" ]; then
    test_info "Testing delete with ISBN: $test_isbn"

    response=$(curl -s -X DELETE "http://127.0.0.1:8000/api/books/$test_isbn")
    if echo "$response" | grep -q "book-table"; then
        test_pass "Book delete endpoint works"

        # Verify book was deleted
        exists=$(sqlite3 ~/.isbn_lot_optimizer/catalog.db "SELECT COUNT(*) FROM books WHERE isbn = '$test_isbn';")
        if [ "$exists" = "0" ]; then
            test_pass "Book actually deleted from database"
        else
            test_fail "Book still in database after delete"
        fi
    else
        test_fail "Book delete endpoint failed"
    fi
else
    test_info "No books in database to test delete"
fi
echo ""

# Test 5: API Documentation includes new routes
echo "Test 5: API Documentation"
response=$(curl -s "http://127.0.0.1:8000/docs")
if echo "$response" | grep -q "lots"; then
    test_pass "API docs include lots routes"
else
    test_fail "API docs missing lots routes"
fi

if echo "$response" | grep -q "events"; then
    test_pass "API docs include events routes"
else
    test_fail "API docs missing events routes"
fi

if echo "$response" | grep -q "actions"; then
    test_pass "API docs include actions routes"
else
    test_fail "API docs missing actions routes"
fi
echo ""

# Summary
echo "========================================"
echo "  Test Summary"
echo "========================================"
echo -e "${GREEN}Passed: $success_count${NC}"
echo -e "${RED}Failed: $fail_count${NC}"
echo ""

if [[ $fail_count -eq 0 ]]; then
    echo -e "${GREEN}All Phase 2 tests passed! 🎉${NC}"
    echo ""
    echo "Phase 2 Features Working:"
    echo "  ✓ Lot generation and display"
    echo "  ✓ SSE infrastructure for real-time updates"
    echo "  ✓ Book deletion"
    echo "  ✓ All new API routes documented"
    echo ""
    echo "Ready to Test Manually:"
    echo "  1. CSV Import (via UI at http://127.0.0.1:8000)"
    echo "  2. Lot details modal"
    echo "  3. Progress bars during import"
    echo "  4. Metadata refresh"
else
    echo -e "${RED}Some tests failed. Check output above.${NC}"
fi

echo ""
echo "========================================"
