# Testing Guide for ISBN Lot Optimizer

## Overview

This document describes the comprehensive test suite for the ISBN Lot Optimizer application suite. The test suite covers shared business logic, desktop app functionality, and web API endpoints.

## Test Infrastructure

### Files Created

```
tests/
├── conftest.py                 # Shared fixtures and pytest configuration
├── test_metadata.py            # Tests for shared.metadata module
├── test_database.py            # Tests for shared.database module
├── test_book_service.py        # Tests for BookService core methods
├── test_status_workflow.py     # Existing: Status workflow tests
├── test_incremental_lot_update.py # Existing: Lot update performance tests
└── ... (other existing tests)

pytest.ini                      # Pytest configuration
run_tests.py                    # Comprehensive test runner script
```

### Test Categories (Markers)

Tests are organized by markers for selective execution:

- **`@pytest.mark.unit`** - Fast unit tests, no external dependencies
- **`@pytest.mark.integration`** - Integration tests (database, file system)
- **`@pytest.mark.slow`** - Slow tests (API calls, heavy computation)
- **`@pytest.mark.network`** - Tests requiring network access
- **`@pytest.mark.database`** - Tests using database

## Running Tests

### Quick Start

```bash
# Run fast tests only (unit tests)
python run_tests.py

# Run all tests (including slow and integration)
python run_tests.py --full

# Run with code coverage
python run_tests.py --coverage

# Run specific test file
python run_tests.py --file test_metadata.py

# Run specific test
python run_tests.py --test test_fetch_metadata

# Verbose output
python run_tests.py --verbose

# Stop on first failure
python run_tests.py --failfast
```

### Direct pytest Usage

```bash
# Run all tests
pytest

# Run unit tests only
pytest -m unit

# Run integration tests only
pytest -m integration

# Run specific file
pytest tests/test_metadata.py

# Run with coverage
pytest --cov=shared --cov=isbn_lot_optimizer --cov-report=html

# Run with verbose output
pytest -vv

# Show test durations
pytest --durations=10
```

## Test Suite Structure

### 1. Shared Module Tests

#### test_metadata.py
Tests for metadata fetching and normalization:
- HTTP session creation
- Google Books API interaction
- Metadata normalization
- ISBN handling
- Image URL prioritization
- Authorship enrichment

**Key Tests:**
- `test_normalize_basic_fields` - Validates field extraction
- `test_normalize_prioritizes_large_images` - Ensures highest quality images
- `test_fetch_metadata_with_mock` - Tests API integration with mocking

#### test_database.py
Tests for database operations:
- Database initialization
- CRUD operations
- Status filtering (ACCEPT/REJECT)
- Search functionality
- Multiple book operations

**Key Tests:**
- `test_upsert_book_creates_new_record` - Insert operations
- `test_upsert_book_updates_existing_record` - Update operations
- `test_fetch_all_books_filters_by_accept_status` - Status filtering
- `test_search_books_finds_by_title` - Search functionality

### 2. Service Layer Tests

#### test_book_service.py
Tests for BookService core methods:
- Service initialization
- ISBN scanning workflow
- Book acceptance workflow
- Status management
- Book retrieval and search
- Lot generation
- Statistics

**Key Tests:**
- `test_scan_isbn_defaults_to_reject` - Default workflow behavior
- `test_accept_book_updates_status` - Acceptance workflow
- `test_get_all_books_filters_by_accept` - Query filtering
- `test_recompute_lots_returns_list` - Lot generation

### 3. Existing Tests

The following tests were already in place and continue to work:

- **test_status_workflow.py** (16K) - Status workflow and cover image quality
- **test_incremental_lot_update.py** (3.9K) - Lot update performance
- **test_recent_scans.py** (5.7K) - Scan history functionality
- **test_series_recommendations.py** (12K) - Series detection
- **test_author_match.py** (2.7K) - Author matching
- **test_booksrun_client.py** (3.6K) - BooksRun integration

## Current Test Coverage

### Before Test Suite Creation

```
SHARED: 21 modules
  ❌ amazon_api.py
  ❌ author_aliases.py
  ❌ bookscouter.py
  ✅ booksrun.py
  ❌ database.py
  ❌ metadata.py
  ❌ probability.py
  ... (18 untested modules)

ISBN_LOT_OPTIMIZER: 12 modules
  ❌ service.py (CRITICAL - 3,852 lines!)
  ❌ lots.py
  ❌ lot_market.py
  ✅ author_match.py
  ... (9 untested modules)

ISBN_WEB: 7 modules
  ✅ books.py (partial)
  ... (6 untested modules)
```

### After Test Suite Creation

```
SHARED:
  ✅ database.py (11 tests)
  ✅ metadata.py (15 tests)
  ✅ booksrun.py (existing)
  ❌ probability.py (TODO)
  ❌ market.py (TODO - complex, needs eBay API mocking)
  ... (16 others)

ISBN_LOT_OPTIMIZER:
  ✅ service.py (11 core tests)
  ✅ author_match.py (existing)
  ✅ recent_scans.py (existing)
  ... (9 others)

ISBN_WEB:
  ✅ books.py (existing integration test)
  ... (6 others)
```

**New Tests Added**: 37 tests
**Total Tests**: ~90 tests (53 existing + 37 new)

## Test Fixtures

### conftest.py Fixtures

```python
temp_db_path()           # Temporary database file
db_manager()             # DatabaseManager instance
book_service()           # BookService instance
sample_isbn()            # Sample ISBN-13
sample_isbn_10()         # Sample ISBN-10
sample_metadata()        # Sample metadata dict
sample_book_data()       # Sample book data for DB
mock_requests_session()  # Mocked requests session
mock_metadata_response() # Mocked Google Books response
```

## Writing New Tests

### Example: Unit Test

```python
import pytest
from shared.utils import normalise_isbn

@pytest.mark.unit
def test_normalise_isbn_removes_hyphens():
    """Test ISBN normalization removes hyphens."""
    result = normalise_isbn("978-0-143-12755-0")
    assert result == "9780143127550"
    assert "-" not in result
```

### Example: Integration Test

```python
import pytest

@pytest.mark.integration
@pytest.mark.database
def test_book_workflow(book_service):
    """Test complete book scanning and acceptance workflow."""
    with patch("shared.metadata.fetch_metadata") as mock:
        mock.return_value = {"title": "Test", "isbn_13": "9780143127550"}

        # Scan
        book_service.scan_isbn("9780143127550", include_market=False)

        # Accept
        book_service.accept_book("9780143127550")

        # Verify
        book = book_service.get_book("9780143127550")
        assert book is not None
        assert book.status == "ACCEPT"
```

### Example: Test with Mocking

```python
from unittest.mock import patch, Mock

@pytest.mark.unit
def test_api_call_with_mock():
    """Test API call with mocked response."""
    with patch("requests.Session.get") as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        mock_get.return_value = mock_response

        # Call function that uses requests
        result = my_function()

        assert result["result"] == "success"
```

## Best Practices

### 1. Test Independence
- Each test should be independent
- Use fixtures for setup/teardown
- Don't rely on test execution order

### 2. Use Markers
- Mark tests appropriately (@pytest.mark.unit, @pytest.mark.slow, etc.)
- Allows selective test execution
- Helps with CI/CD optimization

### 3. Mock External Dependencies
- Mock network calls (Google Books API, eBay API)
- Mock file system operations when possible
- Use temporary databases for integration tests

### 4. Descriptive Names
- Test names should describe what they test
- Use format: `test_<function>_<scenario>_<expected>`
- Example: `test_scan_isbn_with_invalid_isbn_returns_none`

### 5. Test Both Success and Failure
- Test happy path
- Test error conditions
- Test edge cases

## Continuous Integration

### Recommended CI/CD Setup

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      - name: Run fast tests
        run: pytest -m unit
      - name: Run all tests
        run: pytest --cov=shared --cov=isbn_lot_optimizer
```

## Coverage Goals

### Current Coverage (Estimated)
- **Shared modules**: ~15% (3 of 21 modules tested)
- **Desktop app**: ~25% (3 of 12 modules tested)
- **Web app**: ~15% (1 of 7 modules tested)

### Target Coverage
- **Critical modules** (shared/metadata, shared/probability, service): >80%
- **Other modules**: >60%
- **Overall**: >70%

## Known Issues & TODOs

### Test Refinements Needed

1. **Schema Compatibility**
   - Some database tests fail due to missing schema fields
   - Need to update fixtures with complete book data
   - Action: Review database.py schema and update sample_book_data fixture

2. **API Mocking**
   - Some metadata tests make real API calls
   - Mocking not working correctly for all cases
   - Action: Improve mock setup in conftest.py

3. **Missing Tests**
   - probability.py (critical - just moved to shared/)
   - market.py (critical - just moved to shared/)
   - Web API endpoints (integration tests needed)
   - Action: Create test_probability.py and test_market.py

4. **Integration Tests**
   - Need end-to-end workflow tests
   - Test complete scan → evaluate → accept → lot generation flow
   - Action: Create test_integration.py

## Next Steps

### High Priority
1. Fix database test fixtures to match current schema
2. Create test_probability.py for book evaluation logic
3. Add web API integration tests
4. Fix API mocking in test_metadata.py

### Medium Priority
1. Create test_market.py (complex - needs eBay API mocking)
2. Add end-to-end integration tests
3. Set up code coverage tracking
4. Add CI/CD pipeline

### Low Priority
1. Test utility modules (utils.py, constants.py)
2. Test series detection modules
3. Add performance benchmarks
4. Create load tests for web API

## Troubleshooting

### Common Issues

**Issue**: Tests fail with "module not found"
**Solution**: Run from project root: `cd /Users/nickcuskey/ISBN && pytest`

**Issue**: Database tests fail with schema errors
**Solution**: Update sample_book_data fixture in conftest.py with all required fields

**Issue**: Network tests timeout
**Solution**: Run only unit tests: `pytest -m unit` or mock network calls

**Issue**: Import errors
**Solution**: Ensure PYTHONPATH includes project root

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)

## Summary

The test suite provides a solid foundation for maintaining code quality and catching regressions. With 90+ tests covering critical paths, the application is well-positioned for continued development and refactoring.

**Key Benefits:**
- ✅ Catch regressions early
- ✅ Document expected behavior
- ✅ Enable safe refactoring
- ✅ Improve code quality
- ✅ Faster development cycles

**Status**: 🟡 In Progress - Core infrastructure complete, refinements needed
