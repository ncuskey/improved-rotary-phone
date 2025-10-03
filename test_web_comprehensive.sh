#!/bin/bash
# Comprehensive test script for ISBN Lot Optimizer Web App

echo "========================================"
echo "  ISBN Web App - Comprehensive Tests"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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

# Test 1: Health Check
echo "Test 1: Health Check"
response=$(curl -s http://127.0.0.1:8000/health)
if [[ "$response" == *"healthy"* ]]; then
    test_pass "Server is healthy"
else
    test_fail "Server health check failed"
fi
echo ""

# Test 2: Dashboard loads
echo "Test 2: Dashboard Page"
response=$(curl -s -w "%{http_code}" http://127.0.0.1:8000 -o /tmp/dashboard.html)
if [[ "$response" == "200" ]]; then
    test_pass "Dashboard loads (HTTP 200)"
    if grep -q "ISBN Lot Optimizer" /tmp/dashboard.html; then
        test_pass "Dashboard contains expected title"
    else
        test_fail "Dashboard missing title"
    fi
else
    test_fail "Dashboard failed to load (HTTP $response)"
fi
echo ""

# Test 3: API Documentation
echo "Test 3: API Documentation"
response=$(curl -s -w "%{http_code}" http://127.0.0.1:8000/docs -o /dev/null)
if [[ "$response" == "200" ]]; then
    test_pass "API docs available at /docs"
else
    test_fail "API docs not accessible"
fi
echo ""

# Test 4: Scan ISBN (The Great Gatsby)
echo "Test 4: Scan ISBN - The Great Gatsby"
ISBN="9780743273565"
response=$(curl -s -X POST "http://127.0.0.1:8000/api/books/scan" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "isbn=$ISBN&condition=Good&edition=" \
    -w "\n%{http_code}")

http_code=$(echo "$response" | tail -1)
if [[ "$http_code" == "200" ]]; then
    test_pass "Scan request successful (HTTP 200)"
    if echo "$response" | grep -q "$ISBN"; then
        test_pass "Response contains ISBN $ISBN"
    else
        test_fail "Response missing ISBN"
    fi
else
    test_fail "Scan request failed (HTTP $http_code)"
fi
echo ""

# Test 5: Scan another ISBN (Harry Potter)
echo "Test 5: Scan ISBN - Harry Potter"
ISBN2="9780439708180"
response=$(curl -s -X POST "http://127.0.0.1:8000/api/books/scan" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "isbn=$ISBN2&condition=Very Good&edition=" \
    -w "\n%{http_code}")

http_code=$(echo "$response" | tail -1)
if [[ "$http_code" == "200" ]]; then
    test_pass "Second scan successful"
else
    test_fail "Second scan failed"
fi
echo ""

# Test 6: List all books
echo "Test 6: List All Books"
response=$(curl -s "http://127.0.0.1:8000/api/books")
if echo "$response" | grep -q "book-table"; then
    test_pass "Book list endpoint returns table"

    # Count books in response
    book_count=$(echo "$response" | grep -o "hx-get=\"/api/books/" | wc -l)
    test_info "Found $book_count books in catalog"
else
    test_fail "Book list endpoint failed"
fi
echo ""

# Test 7: Get book detail
echo "Test 7: Get Book Detail"
response=$(curl -s "http://127.0.0.1:8000/api/books/$ISBN")
if echo "$response" | grep -q "$ISBN"; then
    test_pass "Book detail endpoint returns ISBN"
    if echo "$response" | grep -q "Estimated Price"; then
        test_info "Book detail includes pricing information"
    fi
    if echo "$response" | grep -q "eBay Market Stats"; then
        test_info "Book detail includes market stats"
    fi
else
    test_fail "Book detail endpoint failed"
fi
echo ""

# Test 8: Search functionality
echo "Test 8: Search Books"
response=$(curl -s "http://127.0.0.1:8000/api/books?search=gatsby")
if echo "$response" | grep -q "book-table"; then
    test_pass "Search endpoint works"
    if echo "$response" | grep -q "$ISBN"; then
        test_pass "Search finds 'gatsby' (The Great Gatsby)"
    else
        test_info "Search didn't find Gatsby (might not have metadata yet)"
    fi
else
    test_fail "Search endpoint failed"
fi
echo ""

# Test 9: Invalid ISBN handling
echo "Test 9: Invalid ISBN Handling"
response=$(curl -s -X POST "http://127.0.0.1:8000/api/books/scan" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "isbn=invalid123&condition=Good&edition=" \
    -w "\n%{http_code}")

http_code=$(echo "$response" | tail -1)
if [[ "$http_code" == "200" ]]; then
    test_pass "Invalid ISBN handled gracefully (no crash)"
else
    test_fail "Invalid ISBN caused server error"
fi
echo ""

# Test 10: Static files
echo "Test 10: Static Files"
response=$(curl -s -w "%{http_code}" http://127.0.0.1:8000/static/css/custom.css -o /dev/null)
if [[ "$response" == "200" ]]; then
    test_pass "CSS file accessible"
else
    test_fail "CSS file not found"
fi

response=$(curl -s -w "%{http_code}" http://127.0.0.1:8000/static/js/app.js -o /dev/null)
if [[ "$response" == "200" ]]; then
    test_pass "JavaScript file accessible"
else
    test_fail "JavaScript file not found"
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
    echo -e "${GREEN}All tests passed! 🎉${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Open http://127.0.0.1:8000 in your browser"
    echo "  2. Try scanning more ISBNs"
    echo "  3. Click on books to see details"
    echo "  4. Use the search functionality"
else
    echo -e "${RED}Some tests failed. Check the output above.${NC}"
fi

echo ""
echo "Server logs: tail -f /tmp/isbn_web.log"
echo "========================================"
