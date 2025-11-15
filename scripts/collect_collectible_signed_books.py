#!/usr/bin/env python3
"""
Collect high-value signed first edition books from collectible authors.

Uses Serper to search eBay sold listings and Decodo to scrape listing details.
Saves results to sold_listings table for ML training.

Usage:
    python3 scripts/collect_collectible_signed_books.py [--max-per-author 10] [--dry-run]
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.decodo import DecodoClient
from shared.ebay_sold_parser import parse_ebay_sold_listing
from shared.feature_detector import is_signed

# Load environment
load_dotenv()

SERPER_API_KEY = os.getenv("X-API-KEY")
DECODO_USERNAME = os.getenv("DECODO_CORE_AUTHENTICATION")
DECODO_PASSWORD = os.getenv("DECODO_CORE_PASSWORD")


def load_collectible_authors(authors_file: str) -> List[Dict]:
    """Load collectible authors list from JSON file."""
    with open(authors_file, 'r') as f:
        data = json.load(f)
    return data['authors']


def search_ebay_serper(query: str, num_results: int = 10) -> list:
    """Search eBay using Serper API."""
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "q": f"site:ebay.com {query} sold",
        "num": num_results,
        "gl": "us"
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    results = response.json()
    return results.get("organic", [])


def extract_ebay_urls(serper_results: list) -> list:
    """Extract eBay listing URLs from Serper results."""
    urls = []
    for result in serper_results:
        link = result.get("link", "")
        # Only include sold listing pages
        if "ebay.com" in link and ("/itm/" in link or "/p/" in link):
            urls.append(link)
    return urls


def scrape_ebay_listing(url: str, decodo_client: DecodoClient) -> Optional[Dict]:
    """Scrape and parse eBay listing."""
    try:
        response = decodo_client.scrape_url(url, render_js=True)

        if response.status_code != 200:
            print(f"    ✗ Decodo error {response.status_code}: {url[:60]}")
            return None

        # Parse using existing eBay parser
        parsed = parse_ebay_sold_listing(url, response.body)

        if not parsed:
            return None

        # Add signed/first_edition detection
        title = parsed.get("title", "") or ""

        # Detect signed
        signed = is_signed(title) if title else False

        # Detect first edition
        first_edition = False
        if title:
            title_lower = title.lower()
            first_edition = any(phrase in title_lower for phrase in [
                "first edition", "1st edition", "first printing",
                "1st printing", "first print", "1/1"
            ])

        # Extract ISBN from title
        isbn = None
        if title:
            isbn_match = re.search(r'ISBN[:\s-]*(\d{10}|\d{13})', title, re.IGNORECASE)
            if isbn_match:
                isbn = isbn_match.group(1)

        return {
            "url": url,
            "title": title,
            "price": parsed.get("price", 0.0) or 0.0,
            "condition": parsed.get("condition", "") or "",
            "sold_date": parsed.get("sold_date"),
            "isbn": isbn,
            "signed": 1 if signed else 0,
            "first_edition": 1 if first_edition else 0,
        }

    except Exception as e:
        print(f"    ✗ Error scraping {url[:60]}: {e}")
        return None


def save_to_database(listings: List[Dict], catalog_db: str, dry_run: bool = False) -> int:
    """Save listings to sold_listings table."""
    if not listings:
        return 0

    if dry_run:
        print(f"\nDRY RUN: Would save {len(listings)} listings")
        signed_count = sum(1 for l in listings if l['signed'] == 1)
        first_ed_count = sum(1 for l in listings if l['first_edition'] == 1)
        print(f"  Signed: {signed_count}")
        print(f"  First Edition: {first_ed_count}")
        return 0

    conn = sqlite3.connect(catalog_db)
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sold_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT,
            title TEXT,
            sold_price REAL,
            sold_date TEXT,
            vendor TEXT DEFAULT 'ebay',
            signed INTEGER DEFAULT 0,
            first_edition INTEGER DEFAULT 0,
            source TEXT DEFAULT 'collectible_scraper',
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sold_listings_isbn
        ON sold_listings(isbn)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sold_listings_signed
        ON sold_listings(signed)
    """)

    # Insert listings
    inserted = 0
    skipped = 0
    skipped_no_isbn = 0

    for listing in listings:
        # Check if URL already exists
        cursor.execute("SELECT id FROM sold_listings WHERE url = ?", (listing['url'],))
        if cursor.fetchone():
            skipped += 1
            continue

        # Track listings without ISBN for reporting
        if not listing.get('isbn'):
            skipped_no_isbn += 1

        cursor.execute("""
            INSERT INTO sold_listings (
                isbn, title, price, sold_date, platform,
                signed, url
            )
            VALUES (?, ?, ?, ?, 'ebay', ?, ?)
        """, (
            listing['isbn'],
            listing['title'],
            listing['price'],
            listing['sold_date'],
            listing['signed'],
            listing['url'],
        ))
        inserted += 1

    conn.commit()
    conn.close()

    print(f"\n✓ Saved {inserted} new listings to database")
    if skipped > 0:
        print(f"  Skipped {skipped} duplicates")
    if skipped_no_isbn > 0:
        print(f"  ({skipped_no_isbn} saved without ISBN)")

    return inserted


def collect_for_author(
    author: Dict,
    decodo_client: DecodoClient,
    max_per_search: int = 10
) -> List[Dict]:
    """Collect signed first editions for one author."""
    print(f"\n{'='*80}")
    print(f"COLLECTING: {author['name']}")
    print(f"{'='*80}")

    all_listings = []

    for search_term in author['search_terms']:
        print(f"\n  Search: {search_term}")

        # Search with Serper
        try:
            serper_results = search_ebay_serper(search_term, num_results=max_per_search)
            print(f"    Found {len(serper_results)} search results")
        except Exception as e:
            print(f"    ✗ Serper error: {e}")
            continue

        if not serper_results:
            continue

        # Extract URLs
        urls = extract_ebay_urls(serper_results)
        print(f"    Extracted {len(urls)} eBay URLs")

        if not urls:
            continue

        # Scrape each listing
        print(f"    Scraping {len(urls)} listings...")
        for i, url in enumerate(urls, 1):
            listing = scrape_ebay_listing(url, decodo_client)
            if listing:
                all_listings.append(listing)
                status = "✓ SIGNED" if listing['signed'] else "  unsigned"
                print(f"      [{i}/{len(urls)}] {status} - ${listing['price']:.2f}")
            else:
                print(f"      [{i}/{len(urls)}] ✗ Failed")

            # Rate limiting - be nice to APIs
            time.sleep(1)

    # Summary for this author
    signed_count = sum(1 for l in all_listings if l['signed'] == 1)
    first_ed_count = sum(1 for l in all_listings if l['first_edition'] == 1)
    both_count = sum(1 for l in all_listings if l['signed'] == 1 and l['first_edition'] == 1)

    print(f"\n  Summary for {author['name']}:")
    print(f"    Total listings: {len(all_listings)}")
    print(f"    Signed: {signed_count}")
    print(f"    First Edition: {first_ed_count}")
    print(f"    Signed + First Ed: {both_count}")

    return all_listings


def main():
    parser = argparse.ArgumentParser(
        description="Collect high-value signed first editions from collectible authors"
    )
    parser.add_argument(
        '--authors-file',
        default='scripts/collectible_authors_list.json',
        help='Path to authors JSON file'
    )
    parser.add_argument(
        '--catalog-db',
        default=str(Path.home() / '.isbn_lot_optimizer' / 'catalog.db'),
        help='Path to catalog.db'
    )
    parser.add_argument(
        '--max-per-author',
        type=int,
        default=10,
        help='Max results per search term (default: 10)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be collected without saving'
    )
    parser.add_argument(
        '--author',
        help='Only collect for specific author (e.g., "Tom Clancy")'
    )

    args = parser.parse_args()

    print("="*80)
    print("COLLECTIBLE SIGNED BOOKS SCRAPER")
    print("="*80)

    # Check environment
    if not SERPER_API_KEY:
        print("✗ Error: X-API-KEY not found in .env")
        return 1

    if not DECODO_USERNAME or not DECODO_PASSWORD:
        print("✗ Error: DECODO_CORE_AUTHENTICATION/PASSWORD not found in .env")
        return 1

    print("✓ API keys found")

    # Check catalog.db
    catalog_path = Path(args.catalog_db)
    if not catalog_path.parent.exists():
        print(f"✗ Error: Directory not found: {catalog_path.parent}")
        return 1

    # Initialize Decodo client
    decodo = DecodoClient(
        username=DECODO_USERNAME,
        password=DECODO_PASSWORD,
        plan="core"
    )

    # Load authors
    try:
        authors = load_collectible_authors(args.authors_file)
        print(f"✓ Loaded {len(authors)} collectible authors")
    except Exception as e:
        print(f"✗ Error loading authors file: {e}")
        return 1

    # Filter to specific author if requested
    if args.author:
        authors = [a for a in authors if a['name'].lower() == args.author.lower()]
        if not authors:
            print(f"✗ Author not found: {args.author}")
            return 1
        print(f"  Filtering to: {authors[0]['name']}")

    # Collect from all authors
    all_listings = []

    for author in authors:
        listings = collect_for_author(author, decodo, args.max_per_author)
        all_listings.extend(listings)

    # Save to database
    if all_listings:
        print(f"\n{'='*80}")
        print("SAVING TO DATABASE")
        print(f"{'='*80}")

        inserted = save_to_database(all_listings, args.catalog_db, args.dry_run)

        # Final summary
        signed_count = sum(1 for l in all_listings if l['signed'] == 1)
        first_ed_count = sum(1 for l in all_listings if l['first_edition'] == 1)
        both_count = sum(1 for l in all_listings if l['signed'] == 1 and l['first_edition'] == 1)

        print(f"\n{'='*80}")
        print("COLLECTION COMPLETE")
        print(f"{'='*80}")
        print(f"Total listings collected: {len(all_listings)}")
        print(f"  Signed: {signed_count} ({signed_count/len(all_listings)*100:.1f}%)")
        print(f"  First Edition: {first_ed_count} ({first_ed_count/len(all_listings)*100:.1f}%)")
        print(f"  Signed + First Ed: {both_count} ({both_count/len(all_listings)*100:.1f}%)")
        if not args.dry_run:
            print(f"  Saved to database: {inserted}")

        print(f"\nNext steps:")
        print(f"  1. Run: python3 scripts/sync_signed_status_to_training.py")
        print(f"  2. Retrain: python3 scripts/stacking/train_ebay_model.py")
        print(f"  3. Test predictions for high-value signed first editions")
    else:
        print("\n⚠ No listings collected")

    return 0


if __name__ == "__main__":
    sys.exit(main())
