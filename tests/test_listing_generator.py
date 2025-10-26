#!/usr/bin/env python3
"""Test the AI listing generator with real book data.

This script tests the EbayListingGenerator by generating listings for
actual books in the database. It demonstrates the quality of AI-generated
titles and descriptions.

Usage:
    python3 tests/test_listing_generator.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.ai import EbayListingGenerator, GenerationError


def test_book_listing():
    """Test generating a listing for a popular book."""

    print("=" * 70)
    print("Testing eBay Listing Generator - Individual Book")
    print("=" * 70)

    # Initialize services
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    service = BookService(db_path)
    generator = EbayListingGenerator()

    # Get a book with good metadata
    # Try A Storm of Swords first
    test_isbns = [
        "9780553381702",  # A Storm of Swords (popular fantasy)
        "9780553573404",  # A Game of Thrones
        "9780439136365",  # Harry Potter and the Prisoner of Azkaban
    ]

    book = None
    for isbn in test_isbns:
        book = service.get_book(isbn)
        if book:
            print(f"\n✓ Found test book: {book.metadata.title}")
            break

    if not book:
        print("\n✗ No suitable test books found in database")
        print("  Please scan one of these ISBNs first:")
        for isbn in test_isbns:
            print(f"    - {isbn}")
        return False

    # Display book info
    print("\n" + "─" * 70)
    print("Book Information")
    print("─" * 70)
    print(f"Title: {book.metadata.title}")
    if book.metadata.subtitle:
        print(f"Subtitle: {book.metadata.subtitle}")
    if book.metadata.authors:
        print(f"Authors: {', '.join(book.metadata.authors)}")
    print(f"ISBN: {book.metadata.isbn}")
    if book.metadata.published_year:
        print(f"Published: {book.metadata.published_year}")
    if book.metadata.series_name:
        print(f"Series: {book.metadata.series_name} #{book.metadata.series_index or '?'}")
    print(f"Estimated Price: ${book.estimated_price:.2f}")
    if book.market:
        print(f"Market: {book.market.active_count} active, {book.market.sold_count} sold")

    # Generate listing
    print("\n" + "─" * 70)
    print("Generating AI Listing Content...")
    print("─" * 70)

    try:
        start_time = datetime.now()

        listing = generator.generate_book_listing(
            book=book,
            condition="Good",
            price=book.estimated_price,
        )

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        print(f"✓ Generated in {elapsed_ms:.0f}ms")

        # Display generated content
        print("\n" + "=" * 70)
        print("GENERATED EBAY LISTING")
        print("=" * 70)

        print("\n📋 TITLE (" + str(len(listing.title)) + "/80 characters)")
        print("─" * 70)
        print(listing.title)

        print("\n📝 DESCRIPTION")
        print("─" * 70)
        print(listing.description)

        print("\n⭐ KEY HIGHLIGHTS")
        print("─" * 70)
        for highlight in listing.highlights:
            print(f"  • {highlight}")

        print("\n" + "─" * 70)
        print(f"Model: {listing.model_used}")
        print(f"Generation Time: {elapsed_ms:.0f}ms")

        print("\n" + "=" * 70)
        print("✓ TEST PASSED: Successfully generated book listing")
        print("=" * 70)

        return True

    except GenerationError as e:
        print(f"\n✗ Generation failed: {e}")
        print("\nMake sure Ollama is running:")
        print("  brew services start ollama")
        print("\nOr check that the model is available:")
        print("  ollama list")
        return False


def test_lot_listing():
    """Test generating a listing for a book lot."""

    print("\n\n" + "=" * 70)
    print("Testing eBay Listing Generator - Book Lot")
    print("=" * 70)

    # Initialize services
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    service = BookService(db_path)
    generator = EbayListingGenerator()

    # Get lots
    lots = service.list_lots()

    if not lots:
        print("\n✗ No lots found in database")
        print("  Run lot regeneration first:")
        print("    python3 -m isbn_lot_optimizer.service")
        return False

    # Find a good lot with multiple books
    test_lot = None
    for lot_data in lots:
        if len(lot_data.book_isbns) >= 3:  # At least 3 books
            test_lot = lot_data
            break

    if not test_lot:
        test_lot = lots[0]  # Use first lot if none have 3+ books

    # Get book evaluations for the lot
    books = []
    for isbn in test_lot.book_isbns:
        book = service.get_book(isbn)
        if book:
            books.append(book)

    if not books:
        print(f"\n✗ No books found for lot: {test_lot.name}")
        return False

    # Display lot info
    print("\n" + "─" * 70)
    print("Lot Information")
    print("─" * 70)
    print(f"Name: {test_lot.name}")
    print(f"Strategy: {test_lot.strategy}")
    print(f"Number of Books: {len(books)}")
    print(f"Estimated Value: ${test_lot.estimated_value:.2f}")

    print("\nBooks in Lot:")
    for i, book in enumerate(books, 1):
        print(f"  {i}. {book.metadata.title}")

    # Generate listing
    print("\n" + "─" * 70)
    print("Generating AI Lot Listing...")
    print("─" * 70)

    try:
        start_time = datetime.now()

        listing = generator.generate_lot_listing(
            lot=test_lot,
            books=books,
            condition="Good",
            price=test_lot.estimated_value,
        )

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        print(f"✓ Generated in {elapsed_ms:.0f}ms")

        # Display generated content
        print("\n" + "=" * 70)
        print("GENERATED EBAY LOT LISTING")
        print("=" * 70)

        print("\n📋 TITLE (" + str(len(listing.title)) + "/80 characters)")
        print("─" * 70)
        print(listing.title)

        print("\n📝 DESCRIPTION")
        print("─" * 70)
        print(listing.description)

        print("\n⭐ KEY HIGHLIGHTS")
        print("─" * 70)
        for highlight in listing.highlights:
            print(f"  • {highlight}")

        print("\n" + "─" * 70)
        print(f"Model: {listing.model_used}")
        print(f"Generation Time: {elapsed_ms:.0f}ms")

        print("\n" + "=" * 70)
        print("✓ TEST PASSED: Successfully generated lot listing")
        print("=" * 70)

        return True

    except GenerationError as e:
        print(f"\n✗ Generation failed: {e}")
        return False


def main():
    """Run all listing generator tests."""

    print("\n🤖 eBay Listing Generator - AI Test Suite")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {
        "book_listing": test_book_listing(),
        "lot_listing": test_lot_listing(),
    }

    # Summary
    print("\n\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")

    print("\n" + "─" * 70)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("✓ ALL TESTS PASSED")
        print("\n" + "=" * 70)
        print("Sprint 1 Complete!")
        print("=" * 70)
        print("\nNext Steps:")
        print("  • Sprint 2: Implement OAuth and eBay Sell APIs")
        print("  • Sprint 3: Build iOS listing creation UI")
        print("  • Sprint 4: Add sales tracking")
        print("  • Sprint 5: Build analytics dashboard")
    else:
        print("✗ SOME TESTS FAILED")

    print("=" * 70)

    return passed == total


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
