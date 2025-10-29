#!/usr/bin/env python3
"""
Test suite for Time-to-Sell (TTS) database persistence.

Covers:
- TTS value storage in database
- TTS value retrieval from database
- Legacy record handling (NULL TTS)
- TTS updates when market data changes
- Database schema validation
"""

import sys
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.models import EbayMarketStats, BookMetadata, BookEvaluation
from shared.probability import compute_time_to_sell, build_book_evaluation


def create_test_database() -> Path:
    """Create a temporary test database with schema."""
    temp_db = tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False)
    db_path = Path(temp_db.name)
    temp_db.close()

    # Create schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create books table with time_to_sell_days column
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            isbn TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            metadata_json TEXT,
            time_to_sell_days INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create ebay_market table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ebay_market (
            isbn TEXT PRIMARY KEY,
            active_count INTEGER,
            active_avg_price REAL,
            sold_count INTEGER,
            sold_avg_price REAL,
            sold_median_price REAL,
            sell_through_rate REAL,
            currency TEXT,
            time_to_sell_days INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

    return db_path


def insert_book_with_tts(db_path: Path, isbn: str, title: str, tts: Optional[int]) -> None:
    """Insert a book record with TTS value."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO books (isbn, title, time_to_sell_days)
        VALUES (?, ?, ?)
    ''', (isbn, title, tts))

    conn.commit()
    conn.close()


def insert_market_with_tts(db_path: Path, market: EbayMarketStats, tts: Optional[int]) -> None:
    """Insert an eBay market record with TTS value."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO ebay_market (
            isbn, active_count, active_avg_price, sold_count, sold_avg_price,
            sold_median_price, sell_through_rate, currency, time_to_sell_days
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        market.isbn,
        market.active_count,
        market.active_avg_price,
        market.sold_count,
        market.sold_avg_price,
        market.sold_median_price,
        market.sell_through_rate,
        market.currency,
        tts
    ))

    conn.commit()
    conn.close()


def get_tts_from_db(db_path: Path, isbn: str, table: str = "books") -> Optional[int]:
    """Retrieve TTS value from database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(f'''
        SELECT time_to_sell_days FROM {table} WHERE isbn = ?
    ''', (isbn,))

    result = cursor.fetchone()
    conn.close()

    return result[0] if result else None


# ============================================================================
# TEST SECTION: Database Schema Validation
# ============================================================================

def test_schema_has_tts_column():
    """Test that database schema includes time_to_sell_days column."""
    db_path = create_test_database()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check books table
        cursor.execute("PRAGMA table_info(books)")
        books_columns = {row[1] for row in cursor.fetchall()}

        # Check ebay_market table
        cursor.execute("PRAGMA table_info(ebay_market)")
        market_columns = {row[1] for row in cursor.fetchall()}

        conn.close()

        print(f"✓ Books table columns: {sorted(books_columns)}")
        print(f"✓ Market table columns: {sorted(market_columns)}")

        assert "time_to_sell_days" in books_columns, "books table missing time_to_sell_days column"
        assert "time_to_sell_days" in market_columns, "ebay_market table missing time_to_sell_days column"

        return True

    finally:
        db_path.unlink()


# ============================================================================
# TEST SECTION: TTS Storage
# ============================================================================

def test_store_tts_in_books_table():
    """Test storing TTS value in books table."""
    db_path = create_test_database()

    try:
        # Insert book with TTS = 30 days
        insert_book_with_tts(db_path, "ISBN001", "Test Book", 30)

        # Retrieve and verify
        tts = get_tts_from_db(db_path, "ISBN001", "books")

        print(f"✓ Stored TTS: 30 days")
        print(f"✓ Retrieved TTS: {tts} days")

        assert tts == 30, f"Expected TTS=30, got {tts}"

        return True

    finally:
        db_path.unlink()


def test_store_tts_in_market_table():
    """Test storing TTS value in ebay_market table."""
    db_path = create_test_database()

    try:
        # Create market with TTS
        market = EbayMarketStats(
            isbn="ISBN002",
            active_count=10,
            active_avg_price=20.00,
            sold_count=5,
            sold_avg_price=18.00,
            sold_median_price=17.50,
            sell_through_rate=0.33,
            currency="USD"
        )

        tts = compute_time_to_sell(market)  # Should be 90/5 = 18 days
        insert_market_with_tts(db_path, market, tts)

        # Retrieve and verify
        stored_tts = get_tts_from_db(db_path, "ISBN002", "ebay_market")

        print(f"✓ Calculated TTS: {tts} days")
        print(f"✓ Retrieved TTS: {stored_tts} days")

        assert stored_tts == tts, f"Expected TTS={tts}, got {stored_tts}"
        assert stored_tts == 18, f"Expected TTS=18, got {stored_tts}"

        return True

    finally:
        db_path.unlink()


def test_store_null_tts():
    """Test storing NULL TTS value (no market data)."""
    db_path = create_test_database()

    try:
        # Insert book with NULL TTS
        insert_book_with_tts(db_path, "ISBN003", "Book with No Market Data", None)

        # Retrieve and verify
        tts = get_tts_from_db(db_path, "ISBN003", "books")

        print(f"✓ Stored TTS: None (NULL)")
        print(f"✓ Retrieved TTS: {tts}")

        assert tts is None, f"Expected None, got {tts}"

        return True

    finally:
        db_path.unlink()


# ============================================================================
# TEST SECTION: TTS Retrieval
# ============================================================================

def test_retrieve_multiple_tts_values():
    """Test retrieving TTS values for multiple books."""
    db_path = create_test_database()

    try:
        # Insert multiple books with different TTS values
        books = [
            ("ISBN_FAST", "Fast-Moving Book", 7),
            ("ISBN_MED", "Medium Velocity Book", 45),
            ("ISBN_SLOW", "Slow-Moving Book", 180),
            ("ISBN_VERY_SLOW", "Very Slow Book", 365),
        ]

        for isbn, title, tts in books:
            insert_book_with_tts(db_path, isbn, title, tts)

        # Retrieve and verify all
        all_correct = True
        for isbn, title, expected_tts in books:
            retrieved_tts = get_tts_from_db(db_path, isbn, "books")
            match = "✓" if retrieved_tts == expected_tts else "✗"
            print(f"{match} {isbn}: expected {expected_tts} days, got {retrieved_tts} days")

            if retrieved_tts != expected_tts:
                all_correct = False

        assert all_correct, "Some TTS values did not match"

        return True

    finally:
        db_path.unlink()


# ============================================================================
# TEST SECTION: Legacy Record Handling
# ============================================================================

def test_legacy_record_null_tts():
    """Test handling legacy records without TTS value."""
    db_path = create_test_database()

    try:
        # Insert legacy record (TTS = NULL)
        insert_book_with_tts(db_path, "LEGACY001", "Legacy Book", None)

        # Retrieve and verify graceful handling
        tts = get_tts_from_db(db_path, "LEGACY001", "books")

        print(f"✓ Legacy record TTS: {tts} (NULL as expected)")

        # Should be None, not raise an error
        assert tts is None

        # Now update with calculated TTS
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE books SET time_to_sell_days = ? WHERE isbn = ?
        ''', (45, "LEGACY001"))
        conn.commit()
        conn.close()

        # Verify update
        updated_tts = get_tts_from_db(db_path, "LEGACY001", "books")
        print(f"✓ Updated TTS: {updated_tts} days")

        assert updated_tts == 45

        return True

    finally:
        db_path.unlink()


def test_backward_compatibility():
    """Test that queries work with both NULL and populated TTS."""
    db_path = create_test_database()

    try:
        # Insert mix of old and new records
        insert_book_with_tts(db_path, "OLD001", "Old Book", None)
        insert_book_with_tts(db_path, "NEW001", "New Book", 30)
        insert_book_with_tts(db_path, "OLD002", "Another Old Book", None)
        insert_book_with_tts(db_path, "NEW002", "Another New Book", 90)

        # Query all books
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT isbn, title, time_to_sell_days FROM books ORDER BY isbn
        ''')
        results = cursor.fetchall()
        conn.close()

        print(f"✓ Retrieved {len(results)} records")
        for isbn, title, tts in results:
            tts_str = f"{tts} days" if tts is not None else "NULL"
            print(f"  {isbn}: {tts_str}")

        # Verify all records retrieved successfully
        # ORDER BY isbn: NEW001, NEW002, OLD001, OLD002
        assert len(results) == 4
        assert results[0][2] == 30  # NEW001
        assert results[1][2] == 90  # NEW002
        assert results[2][2] is None  # OLD001
        assert results[3][2] is None  # OLD002

        return True

    finally:
        db_path.unlink()


# ============================================================================
# TEST SECTION: TTS Updates
# ============================================================================

def test_update_tts_when_market_changes():
    """Test updating TTS when market data changes."""
    db_path = create_test_database()

    try:
        # Initial market: 5 sold in 90 days → TTS = 18 days
        market1 = EbayMarketStats(
            isbn="ISBN_UPDATE",
            active_count=10,
            active_avg_price=20.00,
            sold_count=5,
            sold_avg_price=18.00,
            sold_median_price=17.50,
            sell_through_rate=0.33,
            currency="USD"
        )

        tts1 = compute_time_to_sell(market1)
        insert_market_with_tts(db_path, market1, tts1)

        print(f"✓ Initial TTS: {tts1} days (5 sold)")

        # Updated market: 10 sold in 90 days → TTS = 9 days
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        tts2 = 9  # 90 / 10 = 9
        cursor.execute('''
            UPDATE ebay_market
            SET sold_count = 10, time_to_sell_days = ?
            WHERE isbn = ?
        ''', (tts2, "ISBN_UPDATE"))

        conn.commit()
        conn.close()

        # Verify update
        updated_tts = get_tts_from_db(db_path, "ISBN_UPDATE", "ebay_market")
        print(f"✓ Updated TTS: {updated_tts} days (10 sold)")

        assert updated_tts == tts2
        assert updated_tts != tts1, "TTS should have changed"

        return True

    finally:
        db_path.unlink()


def test_bulk_tts_recalculation():
    """Test recalculating TTS for multiple books at once."""
    db_path = create_test_database()

    try:
        # Insert multiple market records with old TTS values
        markets = [
            EbayMarketStats(
                isbn=f"ISBN_{i}",
                active_count=10,
                active_avg_price=20.00,
                sold_count=i,  # Varies from 1 to 5
                sold_avg_price=18.00,
                sold_median_price=17.50,
                sell_through_rate=0.5,
                currency="USD"
            )
            for i in range(1, 6)
        ]

        # Insert with old TTS (all set to 999 - incorrect)
        for market in markets:
            insert_market_with_tts(db_path, market, 999)

        # Recalculate TTS for all records
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for market in markets:
            correct_tts = compute_time_to_sell(market)
            cursor.execute('''
                UPDATE ebay_market
                SET time_to_sell_days = ?
                WHERE isbn = ?
            ''', (correct_tts, market.isbn))

        conn.commit()

        # Verify all updates
        cursor.execute('''
            SELECT isbn, sold_count, time_to_sell_days
            FROM ebay_market
            ORDER BY sold_count
        ''')
        results = cursor.fetchall()
        conn.close()

        print(f"✓ Recalculated TTS for {len(results)} records:")
        all_correct = True
        for isbn, sold_count, tts in results:
            expected_tts = max(7, min(90 // sold_count, 365))
            match = "✓" if tts == expected_tts else "✗"
            print(f"  {match} {isbn}: {sold_count} sold → {tts} days (expected {expected_tts})")

            if tts != expected_tts:
                all_correct = False

        assert all_correct, "Some TTS recalculations were incorrect"

        return True

    finally:
        db_path.unlink()


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def main():
    """Run all database TTS persistence tests."""
    print("\n" + "="*70)
    print("DATABASE TTS PERSISTENCE TEST SUITE")
    print("="*70)

    tests = [
        # Schema tests
        ("Schema - TTS Column Exists", test_schema_has_tts_column),

        # Storage tests
        ("Storage - Books Table", test_store_tts_in_books_table),
        ("Storage - Market Table", test_store_tts_in_market_table),
        ("Storage - NULL TTS", test_store_null_tts),

        # Retrieval tests
        ("Retrieval - Multiple Values", test_retrieve_multiple_tts_values),

        # Legacy record tests
        ("Legacy - NULL TTS Handling", test_legacy_record_null_tts),
        ("Legacy - Backward Compatibility", test_backward_compatibility),

        # Update tests
        ("Update - Market Data Changes", test_update_tts_when_market_changes),
        ("Update - Bulk Recalculation", test_bulk_tts_recalculation),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        print(f"\n{'─'*70}")
        print(f"Test: {test_name}")
        print(f"{'─'*70}")

        try:
            result = test_func()
            if result:
                passed += 1
                print(f"✅ PASSED")
            else:
                failed += 1
                print(f"❌ FAILED")
        except Exception as e:
            failed += 1
            print(f"❌ FAILED: {e}")

    # Summary
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}")
    print(f"Total tests: {passed + failed}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success rate: {(passed/(passed+failed)*100):.1f}%")
    print(f"{'='*70}\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
