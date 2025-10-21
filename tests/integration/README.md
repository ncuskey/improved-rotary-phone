# Integration Tests

Shell scripts for testing the web API endpoints and features.

## Prerequisites

- Web server running: `uvicorn isbn_web.main:app --host 0.0.0.0 --port 8000`
- Database with sample data (optional for some tests)

## Test Scripts

### test_web_scan.sh

Simple smoke test for the ISBN scanning endpoint.

**Tests:**
- POST /api/books/scan
- Book appears in database
- Book appears in listing

**Usage:**
```bash
./test_web_scan.sh
```

**Expected:** Scans ISBN 9780743273565 (The Great Gatsby) and verifies it's added.

---

### test_phase2.sh

Tests Phase 2 features added to the web app.

**Tests:**
- GET /api/lots - List lots
- POST /api/lots/regenerate - Regenerate lots
- GET /api/events/{id} - SSE endpoint
- DELETE /api/books/{isbn} - Delete book
- GET /docs - API documentation

**Usage:**
```bash
./test_phase2.sh
```

**Expected:** All tests pass with green checkmarks.

---

### test_web_comprehensive.sh

Comprehensive test suite covering core functionality.

**Tests:**
- GET /health - Health check
- GET / - Dashboard loads
- GET /docs - API documentation
- POST /api/books/scan - Scan ISBN
- Database integration
- Response validation

**Usage:**
```bash
./test_web_comprehensive.sh
```

**Expected:** Multiple tests with pass/fail indicators and summary.

---

## Running All Integration Tests

```bash
cd tests/integration
for script in test_*.sh; do
    echo "Running $script..."
    ./$script
    echo ""
done
```

## Notes

- These scripts test live endpoints (not mocked)
- Require web server to be running
- May modify database (add/delete books)
- Use `~/.isbn_lot_optimizer/catalog.db` by default
- Some tests assume specific ISBNs exist

## Alternative: pytest

For unit tests that don't require a running server, use pytest:

```bash
cd ../..
pytest tests/
```

See `tests/test_*.py` for Python unit tests.

---

## Maintenance

These integration tests complement the pytest unit tests by:
- Testing actual HTTP endpoints
- Verifying end-to-end workflows
- Catching integration issues
- Testing SSE/streaming features
- Validating database operations

Keep them updated as API endpoints change.
