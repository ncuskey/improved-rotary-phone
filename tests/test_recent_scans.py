#!/usr/bin/env python3
"""Test script for recent scans cache functionality."""

from isbn_lot_optimizer.recent_scans import RecentScansCache


def test_basic_operations():
    """Test basic cache operations."""
    print("Testing basic cache operations...")
    cache = RecentScansCache(max_size=5)

    # Add some scans
    cache.add_scan("9780316769174", "Harry Potter", "jkrowling:harrypotter", "#1", "Harry Potter and the Philosopher's Stone")
    cache.add_scan("9780316769181", "Harry Potter", "jkrowling:harrypotter", "#2", "Harry Potter and the Chamber of Secrets")
    cache.add_scan("9780345339706", "The Hobbit", "jrrtolkien:middleearth", "#1", "The Hobbit")

    assert cache.size() == 3, f"Expected 3 scans, got {cache.size()}"
    print(f"  ✓ Added 3 scans, cache size: {cache.size()}")

    # Test series matching
    hp_matches = cache.get_series_matches(series_id="jkrowling:harrypotter")
    assert len(hp_matches) == 2, f"Expected 2 Harry Potter matches, got {len(hp_matches)}"
    print(f"  ✓ Found {len(hp_matches)} Harry Potter books")

    hobbit_matches = cache.get_series_matches(series_id="jrrtolkien:middleearth")
    assert len(hobbit_matches) == 1, f"Expected 1 Hobbit match, got {len(hobbit_matches)}"
    print(f"  ✓ Found {len(hobbit_matches)} Middle Earth book")

    # Test has_series_books
    assert cache.has_series_books(series_id="jkrowling:harrypotter"), "Should have Harry Potter books"
    assert not cache.has_series_books(series_id="nonexistent:series"), "Should not have nonexistent series"
    print("  ✓ has_series_books() works correctly")

    # Test get_scan_by_isbn
    scan = cache.get_scan_by_isbn("9780316769174")
    assert scan is not None, "Should find scan by ISBN"
    assert scan.series_name == "Harry Potter", f"Expected 'Harry Potter', got '{scan.series_name}'"
    assert scan.series_position == "#1", f"Expected '#1', got '{scan.series_position}'"
    print("  ✓ get_scan_by_isbn() works correctly")


def test_max_size():
    """Test that cache respects max size."""
    print("\nTesting max size enforcement...")
    cache = RecentScansCache(max_size=3)

    # Add 5 scans (should only keep last 3)
    cache.add_scan("1111111111111", "Series A", "author1:seriesa", "#1")
    cache.add_scan("2222222222222", "Series A", "author1:seriesa", "#2")
    cache.add_scan("3333333333333", "Series B", "author2:seriesb", "#1")
    cache.add_scan("4444444444444", "Series C", "author3:seriesc", "#1")
    cache.add_scan("5555555555555", "Series C", "author3:seriesc", "#2")

    assert cache.size() == 3, f"Expected 3 scans (max size), got {cache.size()}"
    print(f"  ✓ Cache respects max size: {cache.size()}")

    # First two should be evicted
    assert cache.get_scan_by_isbn("1111111111111") is None, "First scan should be evicted"
    assert cache.get_scan_by_isbn("2222222222222") is None, "Second scan should be evicted"
    assert cache.get_scan_by_isbn("5555555555555") is not None, "Last scan should be present"
    print("  ✓ Oldest scans evicted correctly")


def test_duplicate_isbn():
    """Test that re-scanning an ISBN updates the cache."""
    print("\nTesting duplicate ISBN handling...")
    cache = RecentScansCache(max_size=5)

    cache.add_scan("9780316769174", "Harry Potter", "jkrowling:harrypotter", "#1", "Book 1")
    cache.add_scan("9780316769181", "Harry Potter", "jkrowling:harrypotter", "#2", "Book 2")

    assert cache.size() == 2, f"Expected 2 scans, got {cache.size()}"

    # Re-scan the first book (should update, not duplicate)
    cache.add_scan("9780316769174", "Harry Potter", "jkrowling:harrypotter", "#1", "Book 1 Updated")

    assert cache.size() == 2, f"Expected 2 scans (no duplicate), got {cache.size()}"

    scan = cache.get_scan_by_isbn("9780316769174")
    assert scan.title == "Book 1 Updated", "Should have updated title"
    print("  ✓ Duplicate ISBN updates existing scan")


def test_series_name_matching():
    """Test matching by series name (case-insensitive)."""
    print("\nTesting series name matching...")
    cache = RecentScansCache(max_size=5)

    cache.add_scan("1111111111111", "Harry Potter", "jkrowling:harrypotter", "#1")
    cache.add_scan("2222222222222", "Harry Potter", "jkrowling:harrypotter", "#2")

    # Match by name (case-insensitive)
    matches = cache.get_series_matches(series_name="harry potter")
    assert len(matches) == 2, f"Expected 2 matches for 'harry potter', got {len(matches)}"

    matches = cache.get_series_matches(series_name="HARRY POTTER")
    assert len(matches) == 2, f"Expected 2 matches for 'HARRY POTTER', got {len(matches)}"
    print("  ✓ Case-insensitive series name matching works")


def test_clear():
    """Test clearing the cache."""
    print("\nTesting cache clear...")
    cache = RecentScansCache(max_size=5)

    cache.add_scan("1111111111111", "Series A", "author1:seriesa", "#1")
    cache.add_scan("2222222222222", "Series A", "author1:seriesa", "#2")

    assert cache.size() == 2, "Should have 2 scans"

    cache.clear()

    assert cache.size() == 0, "Should be empty after clear"
    assert cache.get_scan_by_isbn("1111111111111") is None, "Should not find any scans"
    print("  ✓ Cache clear works correctly")


if __name__ == "__main__":
    print("=" * 60)
    print("Recent Scans Cache Test Suite")
    print("=" * 60)

    try:
        test_basic_operations()
        test_max_size()
        test_duplicate_isbn()
        test_series_name_matching()
        test_clear()

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
