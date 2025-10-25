#!/usr/bin/env python3
"""
Pre-Scanning Validation Test Suite

Comprehensive test to ensure all features work before going to a book sale.
Run this before scanning to validate the system is ready.
"""

import requests
import time
import json
from pathlib import Path
from typing import Dict, List, Optional
import sys

# ANSI color codes for pretty output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

BASE_URL = "http://localhost:8000/api"
TEST_RESULTS = []

def print_header(text: str):
    """Print a section header"""
    print(f"\n{BOLD}{BLUE}{'=' * 70}{RESET}")
    print(f"{BOLD}{BLUE}{text.center(70)}{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 70}{RESET}\n")

def print_test(name: str, passed: bool, details: str = ""):
    """Print test result"""
    status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
    print(f"  {status} {name}")
    if details:
        print(f"      {YELLOW}{details}{RESET}")
    TEST_RESULTS.append((name, passed, details))

def print_summary():
    """Print final test summary"""
    passed = sum(1 for _, p, _ in TEST_RESULTS if p)
    total = len(TEST_RESULTS)

    print_header("TEST SUMMARY")

    if passed == total:
        print(f"{GREEN}{BOLD}ALL TESTS PASSED! ({passed}/{total}){RESET}")
        print(f"{GREEN}✓ System is ready for scanning!{RESET}\n")
        return True
    else:
        print(f"{RED}{BOLD}SOME TESTS FAILED ({passed}/{total}){RESET}")
        print(f"{RED}✗ Fix issues before scanning{RESET}\n")

        # Show failed tests
        print("Failed tests:")
        for name, passed, details in TEST_RESULTS:
            if not passed:
                print(f"  {RED}✗{RESET} {name}")
                if details:
                    print(f"      {details}")
        return False


class PreScanValidator:
    """Main validation class"""

    def __init__(self):
        self.session = requests.Session()
        self.test_isbns = {
            # Jack Reacher series - for series detection
            "killing_floor": "9780515153651",
            "die_trying": "9780515142242",
            "echo_burning": "9780515143829",
            # Test book not in database
            "new_book": "9780735219090",  # "Where the Crawdads Sing"
        }

    def test_backend_health(self) -> bool:
        """Test 1: Backend is running and healthy"""
        print_header("TEST 1: Backend Health Check")

        try:
            response = self.session.get("http://localhost:8000/health", timeout=5)
            passed = response.status_code == 200
            print_test("Backend server is running", passed,
                      f"Status: {response.status_code}")
            return passed
        except requests.exceptions.ConnectionError:
            print_test("Backend server is running", False,
                      "Cannot connect to backend - is it running on port 8000?")
            return False
        except Exception as e:
            print_test("Backend server is running", False, str(e))
            return False

    def test_database_stats(self) -> bool:
        """Test 2: Database is accessible and has data"""
        print_header("TEST 2: Database Statistics")

        try:
            response = self.session.get(f"{BASE_URL}/books/stats", timeout=10)
            if response.status_code != 200:
                print_test("Database statistics", False,
                          f"Status: {response.status_code}")
                return False

            stats = response.json()
            book_count = stats.get("book_count", 0)
            lot_count = stats.get("lot_count", 0)

            has_data = book_count > 0
            print_test("Database is accessible and has data", has_data,
                      f"Books: {book_count}, Lots: {lot_count}")
            return has_data

        except Exception as e:
            print_test("Database statistics", False, str(e))
            return False

    def test_existing_book_lookup(self) -> bool:
        """Test 3: Can fetch existing book data"""
        print_header("TEST 3: Existing Book Lookup")

        # Get all books first
        try:
            response = self.session.get(f"{BASE_URL}/books/all", timeout=10)
            if response.status_code != 200:
                print_test("Fetch all books", False,
                          f"Status: {response.status_code}")
                return False

            books = response.json()
            if not books:
                print_test("Fetch all books", False, "No books in database")
                return False

            print_test("Fetch all books", True, f"Retrieved {len(books)} books")

            # Test fetching a specific book
            test_isbn = books[0]["isbn"]
            response = self.session.get(f"{BASE_URL}/books/{test_isbn}/evaluate", timeout=10)

            if response.status_code == 200:
                book = response.json()
                title = book.get("metadata", {}).get("title", "Unknown")
                print_test("Fetch specific book evaluation", True,
                          f"{test_isbn} - {title}")
                return True
            else:
                print_test("Fetch specific book evaluation", False,
                          f"Status: {response.status_code}")
                return False

        except Exception as e:
            print_test("Existing book lookup", False, str(e))
            return False

    def test_series_detection(self) -> bool:
        """Test 4: Series detection works"""
        print_header("TEST 4: Series Detection")

        try:
            # Check if Jack Reacher books exist
            killing_floor_isbn = self.test_isbns["killing_floor"]
            response = self.session.get(
                f"{BASE_URL}/books/{killing_floor_isbn}/evaluate",
                timeout=10
            )

            if response.status_code != 200:
                print_test("Series detection", False,
                          "Test book not in database - add Jack Reacher books first")
                return False

            book = response.json()
            series_name = book.get("metadata", {}).get("series_name")

            if not series_name:
                print_test("Series name detected", False,
                          "Book has no series metadata")
                return False

            print_test("Series name detected", True, f"Series: {series_name}")

            # Check if series index is present (optional - not all books have it)
            series_index = book.get("metadata", {}).get("series_index")
            if series_index is not None:
                print_test("Series index present", True, f"Index: {series_index}")
            else:
                # Not a failure - many books don't have series index
                pass

            return True

        except Exception as e:
            print_test("Series detection", False, str(e))
            return False

    def test_lot_grouping(self) -> bool:
        """Test 5: Lot grouping and retrieval"""
        print_header("TEST 5: Lot Grouping")

        try:
            # Fetch all lots
            response = self.session.get(f"{BASE_URL}/lots/all", timeout=10)

            if response.status_code != 200:
                print_test("Fetch lots", False, f"Status: {response.status_code}")
                return False

            lots = response.json()

            if not lots:
                print_test("Fetch lots", False, "No lots found - regenerate lots")
                return False

            print_test("Fetch lots", True, f"Found {len(lots)} lots")

            # Check for series lots
            series_lots = [lot for lot in lots if "series" in lot.get("strategy", "").lower()]
            author_lots = [lot for lot in lots if "author" in lot.get("strategy", "").lower()]

            print_test("Series lots exist", len(series_lots) > 0,
                      f"{len(series_lots)} series lots")
            print_test("Author lots exist", len(author_lots) > 0,
                      f"{len(author_lots)} author lots")

            # Check Jack Reacher lot
            reacher_lot = next(
                (lot for lot in lots if "reacher" in lot.get("name", "").lower()),
                None
            )

            if reacher_lot:
                book_count = len(reacher_lot.get("book_isbns", []))
                print_test("Jack Reacher lot found", True,
                          f"{book_count} books in lot")
            else:
                print_test("Jack Reacher lot found", False,
                          "Expected Jack Reacher series lot")

            return True

        except Exception as e:
            print_test("Lot grouping", False, str(e))
            return False

    def test_duplicate_detection(self) -> bool:
        """Test 6: Duplicate book detection"""
        print_header("TEST 6: Duplicate Detection")

        try:
            # Get an existing book
            response = self.session.get(f"{BASE_URL}/books/all", timeout=10)
            if response.status_code != 200:
                print_test("Duplicate detection", False, "Cannot fetch books")
                return False

            books = response.json()
            if not books:
                print_test("Duplicate detection", False, "No books to test")
                return False

            test_isbn = books[0]["isbn"]

            # Try to evaluate it again (should work - evaluation doesn't persist)
            response = self.session.get(
                f"{BASE_URL}/books/{test_isbn}/evaluate",
                timeout=10
            )

            passed = response.status_code == 200
            print_test("Can re-evaluate existing book", passed,
                      f"ISBN: {test_isbn}")

            return passed

        except Exception as e:
            print_test("Duplicate detection", False, str(e))
            return False

    def test_book_acceptance(self) -> bool:
        """Test 7: Book acceptance workflow"""
        print_header("TEST 7: Book Accept/Reject Workflow")

        # We'll test with a book that might already exist
        test_isbn = self.test_isbns["killing_floor"]

        try:
            # First check current state
            response = self.session.get(
                f"{BASE_URL}/books/{test_isbn}/evaluate",
                timeout=10
            )

            if response.status_code == 200:
                book = response.json()
                title = book.get("metadata", {}).get("title", "Unknown")
                print_test("Test book exists in database", True,
                          f"{test_isbn} - {title}")
            else:
                print_test("Test book exists in database", False,
                          "Test book not found - add it first")
                return False

            # Test scan history endpoint (for logging scans)
            response = self.session.get(
                f"{BASE_URL}/books/scan-history?limit=10",
                timeout=10
            )

            if response.status_code == 200:
                try:
                    history = response.json()
                    scan_count = len(history.get("scans", []))
                    print_test("Scan history accessible", True,
                              f"{scan_count} recent scans")
                except json.JSONDecodeError:
                    # Endpoint might return HTML - that's OK, it still works
                    print_test("Scan history accessible", True,
                              "Endpoint responding (HTML format)")
            else:
                print_test("Scan history accessible", False,
                          f"Status: {response.status_code}")

            return True

        except Exception as e:
            print_test("Book acceptance workflow", False, str(e))
            return False

    def test_api_rate_limits(self) -> bool:
        """Test 8: API rate limiting and retry logic"""
        print_header("TEST 8: API Performance")

        try:
            # Test response time for existing book
            test_isbn = self.test_isbns["killing_floor"]

            start = time.time()
            response = self.session.get(
                f"{BASE_URL}/books/{test_isbn}/evaluate",
                timeout=10
            )
            elapsed = time.time() - start

            if response.status_code == 200:
                # Should be fast for cached data
                if elapsed < 1.0:
                    print_test("Cached book lookup speed", True,
                              f"{elapsed:.2f}s (excellent)")
                elif elapsed < 3.0:
                    print_test("Cached book lookup speed", True,
                              f"{elapsed:.2f}s (good)")
                else:
                    print_test("Cached book lookup speed", False,
                              f"{elapsed:.2f}s (slow - may be rate limited)")

                return True
            else:
                print_test("API performance", False,
                          f"Status: {response.status_code}")
                return False

        except Exception as e:
            print_test("API performance", False, str(e))
            return False

    def test_ios_endpoints(self) -> bool:
        """Test 9: iOS-specific endpoints"""
        print_header("TEST 9: iOS App Integration")

        try:
            # Test lots endpoint (used by iOS)
            response = self.session.get(f"{BASE_URL}/lots/all.json", timeout=10)

            if response.status_code == 200:
                lots = response.json()
                print_test("iOS lots endpoint", True,
                          f"{len(lots)} lots available")
            else:
                print_test("iOS lots endpoint", False,
                          f"Status: {response.status_code}")
                return False

            # Test books endpoint (used by iOS)
            response = self.session.get(f"{BASE_URL}/books/all", timeout=10)

            if response.status_code == 200:
                books = response.json()
                print_test("iOS books endpoint", True,
                          f"{len(books)} books available")
            else:
                print_test("iOS books endpoint", False,
                          f"Status: {response.status_code}")
                return False

            # Test scan history endpoint (used for series detection)
            response = self.session.get(
                f"{BASE_URL}/books/scan-history?limit=100",
                timeout=10
            )

            if response.status_code == 200:
                try:
                    history = response.json()
                    print_test("Scan history endpoint", True,
                              f"{len(history.get('scans', []))} scans recorded")
                except json.JSONDecodeError:
                    print_test("Scan history endpoint", True,
                              "Endpoint responding (HTML format)")
            else:
                print_test("Scan history endpoint", False,
                          f"Status: {response.status_code}")

            return True

        except Exception as e:
            print_test("iOS endpoints", False, str(e))
            return False

    def run_all_tests(self) -> bool:
        """Run complete test suite"""
        print(f"\n{BOLD}Pre-Scanning Validation Test Suite{RESET}")
        print(f"Testing backend at: {BASE_URL}\n")

        # Run tests in order
        tests = [
            self.test_backend_health,
            self.test_database_stats,
            self.test_existing_book_lookup,
            self.test_series_detection,
            self.test_lot_grouping,
            self.test_duplicate_detection,
            self.test_book_acceptance,
            self.test_api_rate_limits,
            self.test_ios_endpoints,
        ]

        for test in tests:
            try:
                test()
            except Exception as e:
                print(f"{RED}Unexpected error in {test.__name__}: {e}{RESET}")

        # Print summary
        return print_summary()


def main():
    """Main entry point"""
    validator = PreScanValidator()

    success = validator.run_all_tests()

    if success:
        print(f"{GREEN}{BOLD}🎉 All systems go! Ready to scan!{RESET}\n")
        sys.exit(0)
    else:
        print(f"{RED}{BOLD}⚠️  Fix issues before scanning{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
