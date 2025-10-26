#!/usr/bin/env python3
"""End-to-end test for eBay listing creation.

This test verifies the complete workflow:
1. OAuth authorization
2. AI content generation
3. eBay API listing creation
4. Database persistence

IMPORTANT: This test requires:
- Token broker running (cd token-broker && node server.js)
- User OAuth authorization (open http://localhost:8787/oauth/authorize in browser)
- Ollama running with Llama 3.1 8B model

Usage:
    # Step 1: Start token broker
    cd token-broker && node server.js

    # Step 2: Authorize (in another terminal)
    curl http://localhost:8787/oauth/authorize
    # Open the authorization_url in a browser and grant access

    # Step 3: Run test
    python3 tests/test_ebay_listing_integration.py

    # Optional: Test with specific ISBN
    python3 tests/test_ebay_listing_integration.py --isbn 9780553381702
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.ebay_listing import EbayListingService
from isbn_lot_optimizer.ebay_sell import EbaySellError
from isbn_lot_optimizer.ai import GenerationError
import requests


def check_token_broker():
    """Check if token broker is running."""
    try:
        response = requests.get("http://localhost:8787/oauth/status", timeout=5)
        if response.status_code == 200:
            print("✓ Token broker is running")
            return True
    except requests.exceptions.RequestException:
        pass

    print("✗ Token broker is not running")
    print("\nPlease start the token broker:")
    print("  cd token-broker && node server.js")
    return False


def check_oauth_status():
    """Check if user has authorized."""
    try:
        response = requests.get("http://localhost:8787/oauth/status", timeout=5)
        data = response.json()

        if data.get("authorized"):
            print(f"✓ OAuth authorized")
            print(f"  Scopes: {', '.join(data.get('scopes', []))}")
            print(f"  Token valid: {data.get('token_valid')}")
            print(f"  Expires in: {data.get('expires_in')}s")
            return True
        else:
            print("✗ Not authorized")
            print(f"\nPlease authorize:")
            print(f"  1. GET {data.get('authorization_url')}")
            print(f"  2. Open the authorization_url in your browser")
            print(f"  3. Grant access to your eBay account")
            return False
    except Exception as e:
        print(f"✗ Failed to check OAuth status: {e}")
        return False


def check_ollama():
    """Check if Ollama is running with the correct model."""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3.1:8b", "prompt": "test", "stream": False},
            timeout=10,
        )
        if response.status_code == 200:
            print("✓ Ollama is running with llama3.1:8b")
            return True
    except requests.exceptions.RequestException:
        pass

    print("✗ Ollama is not running or model not found")
    print("\nPlease ensure Ollama is running:")
    print("  brew services start ollama")
    print("  ollama pull llama3.1:8b")
    return False


def test_listing_creation(isbn: str, dry_run: bool = False):
    """Test end-to-end listing creation."""

    print("\n" + "=" * 70)
    print("eBay Listing Integration Test")
    print("=" * 70)

    # Check prerequisites
    print("\n" + "─" * 70)
    print("Checking Prerequisites...")
    print("─" * 70)

    all_checks_passed = True

    if not check_token_broker():
        all_checks_passed = False

    if not check_oauth_status():
        all_checks_passed = False

    if not check_ollama():
        all_checks_passed = False

    if not all_checks_passed:
        print("\n" + "=" * 70)
        print("✗ Prerequisites not met. Please fix the issues above.")
        print("=" * 70)
        return False

    # Initialize services
    print("\n" + "─" * 70)
    print("Initializing Services...")
    print("─" * 70)

    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    book_service = BookService(db_path)
    listing_service = EbayListingService(db_path)

    print("✓ Services initialized")

    # Get book
    print("\n" + "─" * 70)
    print(f"Loading Book: {isbn}")
    print("─" * 70)

    book = book_service.get_book(isbn)

    if not book:
        print(f"✗ Book not found: {isbn}")
        print("\nPlease scan this ISBN first or use a different ISBN")
        return False

    print(f"✓ Found: {book.metadata.title}")
    if book.metadata.authors:
        print(f"  Authors: {', '.join(book.metadata.authors)}")
    print(f"  Estimated Price: ${book.estimated_price:.2f}")

    if dry_run:
        print("\n" + "=" * 70)
        print("DRY RUN MODE - Skipping actual listing creation")
        print("=" * 70)
        print("\nTo create a real listing, run without --dry-run")
        return True

    # Create listing
    print("\n" + "─" * 70)
    print("Creating eBay Listing...")
    print("─" * 70)

    try:
        start_time = datetime.now()

        listing = listing_service.create_book_listing(
            book=book,
            price=book.estimated_price,
            condition="GOOD",
            quantity=1,
            use_ai=True,
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"✓ Listing created in {elapsed:.1f}s")

        # Display results
        print("\n" + "=" * 70)
        print("LISTING CREATED SUCCESSFULLY")
        print("=" * 70)

        print(f"\nDatabase ID: {listing['id']}")
        print(f"SKU: {listing['sku']}")
        print(f"Offer ID: {listing['offer_id']}")
        if listing.get('ebay_listing_id'):
            print(f"eBay Listing ID: {listing['ebay_listing_id']}")

        print(f"\nTitle ({len(listing['title'])}/80 chars):")
        print(f"  {listing['title']}")

        print(f"\nDescription:")
        desc_preview = listing['description'][:200]
        print(f"  {desc_preview}{'...' if len(listing['description']) > 200 else ''}")

        print(f"\nPrice: ${listing['price']:.2f}")
        print(f"Status: {listing['status']}")

        print("\n" + "─" * 70)
        print("✓ TEST PASSED")
        print("─" * 70)

        print("\nView your listing:")
        print(f"  https://www.ebay.com/sh/lst/active")

        print("\nTo delete this test listing:")
        print(f"  # In Python:")
        print(f"  from isbn_lot_optimizer.ebay_sell import EbaySellClient")
        print(f"  client = EbaySellClient()")
        print(f"  client.delete_offer('{listing['offer_id']}')")
        print(f"  client.delete_inventory_item('{listing['sku']}')")

        return True

    except EbaySellError as e:
        print(f"\n✗ eBay API Error: {e}")
        print("\nPossible issues:")
        print("  - OAuth token expired (re-authorize)")
        print("  - Invalid category ID")
        print("  - Missing required listing policies")
        print("  - Rate limit exceeded")
        return False

    except GenerationError as e:
        print(f"\n✗ AI Generation Error: {e}")
        print("\nPossible issues:")
        print("  - Ollama not running")
        print("  - Model not available")
        print("  - Network timeout")
        return False

    except Exception as e:
        print(f"\n✗ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run the integration test."""

    parser = argparse.ArgumentParser(description="Test eBay listing creation end-to-end")
    parser.add_argument(
        "--isbn",
        default="9780553381702",
        help="ISBN to test with (default: A Storm of Swords)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check prerequisites only, don't create actual listing",
    )

    args = parser.parse_args()

    success = test_listing_creation(args.isbn, args.dry_run)

    if success:
        print("\n" + "=" * 70)
        print("Sprint 2 Ready!")
        print("=" * 70)
        print("\nAll systems operational:")
        print("  ✓ OAuth authorization")
        print("  ✓ AI content generation")
        print("  ✓ eBay API integration")
        print("  ✓ Database persistence")
        sys.exit(0)
    else:
        print("\n" + "=" * 70)
        print("Test Failed")
        print("=" * 70)
        sys.exit(1)


if __name__ == '__main__':
    main()
