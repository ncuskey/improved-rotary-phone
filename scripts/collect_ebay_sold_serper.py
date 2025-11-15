#!/usr/bin/env python3
"""
Collect eBay sold listings using Serper + Decodo approach.

This script:
1. Uses Serper to search for sold eBay listings for given ISBNs
2. Scrapes listing pages via Decodo when needed
3. Extracts condition, format (binding), first edition status, and sold price
4. Stores detailed per-listing data for multi-model training

Target: Collect 1000+ sold listings per condition tier with format/edition variance.
"""

import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
from bs4 import BeautifulSoup

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.decodo import DecodoClient


@dataclass
class EbaySoldListing:
    """Represents a single eBay sold listing."""
    isbn: str
    item_id: str
    title: str
    sold_price: float
    condition: str  # New, Like New, Very Good, Good, Acceptable, Poor
    binding: Optional[str]  # Hardcover, Paperback, Mass Market, etc.
    printing: Optional[str]  # "1st", "First Edition", etc.
    sold_date: str  # ISO format date
    seller: Optional[str]
    url: str


def normalize_condition(condition_text: str) -> str:
    """Normalize eBay condition text to standard categories."""
    condition_lower = condition_text.lower().strip()

    # Map eBay conditions to standard categories
    if "brand new" in condition_lower or condition_lower == "new":
        return "New"
    elif "like new" in condition_lower:
        return "Like New"
    elif "very good" in condition_lower:
        return "Very Good"
    elif "good" in condition_lower and "very" not in condition_lower:
        return "Good"
    elif "acceptable" in condition_lower:
        return "Acceptable"
    elif "poor" in condition_lower:
        return "Poor"
    else:
        return "Good"  # Default fallback


def extract_binding_from_text(text: str) -> Optional[str]:
    """Extract binding/format from text."""
    text_lower = text.lower()

    # Check for specific formats
    if "mass market" in text_lower:
        return "Mass Market"
    elif "hardcover" in text_lower or "hardback" in text_lower:
        return "Hardcover"
    elif "paperback" in text_lower or "softcover" in text_lower:
        return "Paperback"
    elif "trade paperback" in text_lower:
        return "Trade Paperback"

    return None


def extract_printing_from_text(text: str) -> Optional[str]:
    """Extract printing/edition info from text."""
    text_lower = text.lower()

    # First edition patterns
    first_edition_patterns = [
        r'\b1st\s+edition\b',
        r'\bfirst\s+edition\b',
        r'\b1st\s+ed\b',
        r'\bfirst\s+ed\b',
        r'\b1st\s+printing\b',
        r'\bfirst\s+printing\b',
        r'\b1/1\b',
    ]

    for pattern in first_edition_patterns:
        if re.search(pattern, text_lower):
            return "1st"

    # Later edition patterns
    later_patterns = [
        r'\b(\d+)(?:nd|rd|th)\s+edition\b',
        r'\b(\d+)(?:nd|rd|th)\s+printing\b',
        r'\blater\s+printing\b',
        r'\breprint\b',
    ]

    for pattern in later_patterns:
        match = re.search(pattern, text_lower)
        if match:
            if match.groups():
                return f"{match.group(1)}th"
            else:
                return "later"

    return None


def extract_price_from_text(text: str) -> Optional[float]:
    """Extract price from text."""
    # Match prices like $12.99, $12, US $25.00
    price_patterns = [
        r'(?:US\s*)?\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
        r'(\d+(?:,\d{3})*(?:\.\d{2}))\s*USD',
    ]

    for pattern in price_patterns:
        matches = re.findall(pattern, text)
        if matches:
            # Clean and convert first match
            price_str = matches[0].replace(',', '')
            try:
                price = float(price_str)
                # Sanity check: book prices typically $1-$1000
                if 1.0 <= price <= 1000.0:
                    return price
            except ValueError:
                continue

    return None


def extract_sold_date(text: str) -> Optional[str]:
    """Extract sold date from text."""
    # Try to find dates like "Sold Jan 15, 2024"
    date_pattern = r'Sold\s+([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})'
    match = re.search(date_pattern, text)

    if match:
        month_name, day, year = match.groups()
        # Convert to ISO format (approximation)
        month_map = {
            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
        }
        month = month_map.get(month_name, '01')
        return f"{year}-{month}-{day.zfill(2)}"

    # Fallback: use today's date
    return datetime.now().strftime("%Y-%m-%d")


async def search_ebay_sold_serper(
    isbn: str,
    api_key: str,
    max_results: int = 20
) -> List[Dict]:
    """
    Search for eBay sold listings via Serper.

    Returns list of search results with basic extracted data.
    """
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }

    # Search for sold listings
    # Note: Google may not index sold listings well, so results may be limited
    query = f'{isbn} site:ebay.com "sold"'

    payload = {
        "q": query,
        "num": max_results,
        "gl": "us",  # US results
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status != 200:
                print(f"⚠️  Serper error for {isbn}: {response.status}")
                return []

            data = await response.json()

            results = []
            for item in data.get("organic", []):
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                link = item.get("link", "")

                # Extract item ID from URL
                item_id_match = re.search(r'/itm/(\d+)', link)
                item_id = item_id_match.group(1) if item_id_match else None

                # Try to extract data from snippet (may be incomplete)
                full_text = f"{title} {snippet}"

                results.append({
                    "title": title,
                    "snippet": snippet,
                    "link": link,
                    "item_id": item_id,
                    "price": extract_price_from_text(full_text),
                    "condition": None,  # Usually need to scrape page for this
                    "binding": extract_binding_from_text(full_text),
                    "printing": extract_printing_from_text(full_text),
                    "sold_date": None,  # Need to scrape page
                })

            return results


def parse_ebay_sold_page(html: str, isbn: str, url: str) -> Optional[EbaySoldListing]:
    """
    Parse eBay sold listing page HTML to extract details.

    Args:
        html: HTML content from Decodo
        isbn: ISBN being searched
        url: Listing URL

    Returns:
        EbaySoldListing or None if parsing fails
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Extract item ID from URL
    item_id_match = re.search(r'/itm/(\d+)', url)
    item_id = item_id_match.group(1) if item_id_match else "unknown"

    # Extract title
    title_tag = soup.find('h1', class_=re.compile('x-item-title'))
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Extract sold price
    price = None
    price_tag = soup.find('div', class_=re.compile('x-price-primary'))
    if price_tag:
        price_text = price_tag.get_text()
        price = extract_price_from_text(price_text)

    if not price:
        return None  # No price = not useful

    # Extract condition
    condition = "Good"  # Default
    condition_tag = soup.find('div', class_=re.compile('x-item-condition'))
    if condition_tag:
        condition_text = condition_tag.get_text(strip=True)
        condition = normalize_condition(condition_text)

    # Extract binding from title and description
    full_text = title
    desc_tag = soup.find('div', class_=re.compile('x-item-description'))
    if desc_tag:
        full_text += " " + desc_tag.get_text()

    binding = extract_binding_from_text(full_text)
    printing = extract_printing_from_text(full_text)

    # Extract sold date
    sold_date = extract_sold_date(html)

    # Extract seller (optional)
    seller = None
    seller_tag = soup.find('a', class_=re.compile('x-sellercard-atf__seller-name'))
    if seller_tag:
        seller = seller_tag.get_text(strip=True)

    return EbaySoldListing(
        isbn=isbn,
        item_id=item_id,
        title=title,
        sold_price=price,
        condition=condition,
        binding=binding,
        printing=printing,
        sold_date=sold_date,
        seller=seller,
        url=url
    )


def init_database(db_path: Path) -> sqlite3.Connection:
    """Initialize database with ebay_sold_listings_detailed table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ebay_sold_listings_detailed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT NOT NULL,
            item_id TEXT NOT NULL,
            title TEXT,
            sold_price REAL NOT NULL,
            condition TEXT NOT NULL,
            binding TEXT,
            printing TEXT,
            sold_date TEXT,
            seller TEXT,
            url TEXT,
            collected_at TEXT NOT NULL,
            UNIQUE(isbn, item_id)
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ebay_sold_isbn
        ON ebay_sold_listings_detailed(isbn)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ebay_sold_condition
        ON ebay_sold_listings_detailed(condition)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ebay_sold_binding
        ON ebay_sold_listings_detailed(binding)
    """)

    conn.commit()
    return conn


def save_listing(conn: sqlite3.Connection, listing: EbaySoldListing) -> bool:
    """Save listing to database. Returns True if inserted, False if duplicate."""
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO ebay_sold_listings_detailed
            (isbn, item_id, title, sold_price, condition, binding, printing,
             sold_date, seller, url, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing.isbn,
            listing.item_id,
            listing.title,
            listing.sold_price,
            listing.condition,
            listing.binding,
            listing.printing,
            listing.sold_date,
            listing.seller,
            listing.url,
            datetime.now().isoformat()
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Duplicate
        return False


async def collect_isbn_sold_listings(
    isbn: str,
    serper_api_key: str,
    decodo_client: DecodoClient,
    conn: sqlite3.Connection,
    max_listings: int = 20
) -> Tuple[int, int]:
    """
    Collect sold listings for a single ISBN.

    Returns:
        Tuple of (new_listings, skipped_duplicates)
    """
    # Search via Serper
    search_results = await search_ebay_sold_serper(isbn, serper_api_key, max_listings)

    if not search_results:
        return 0, 0

    new_count = 0
    skip_count = 0

    # Process each result
    for result in search_results:
        link = result.get("link", "")
        if not link or "ebay.com" not in link:
            continue

        try:
            # Scrape page via Decodo
            decodo_resp = decodo_client.scrape_url(link, render_js=False)

            if decodo_resp.status_code != 200 or not decodo_resp.body:
                continue

            # Parse HTML
            listing = parse_ebay_sold_page(decodo_resp.body, isbn, link)

            if listing:
                # Save to database
                if save_listing(conn, listing):
                    new_count += 1
                else:
                    skip_count += 1

        except Exception as e:
            print(f"    ⚠️  Error scraping {link}: {e}")
            continue

    return new_count, skip_count


async def main():
    parser = argparse.ArgumentParser(
        description="Collect eBay sold listings using Serper + Decodo"
    )
    parser.add_argument(
        "--isbn-file",
        type=str,
        required=True,
        help="File containing ISBNs (one per line)"
    )
    parser.add_argument(
        "--max-per-isbn",
        type=int,
        default=20,
        help="Max sold listings to collect per ISBN (default: 20)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Database path (default: ~/.isbn_lot_optimizer/metadata_cache.db)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous run (skip ISBNs already collected)"
    )

    args = parser.parse_args()

    # Read ISBNs
    isbn_file = Path(args.isbn_file)
    if not isbn_file.exists():
        print(f"❌ ISBN file not found: {isbn_file}")
        return 1

    with open(isbn_file) as f:
        isbns = [line.strip() for line in f if line.strip()]

    print(f"📚 Loaded {len(isbns)} ISBNs from {isbn_file}")
    print()

    # Get API keys from environment
    serper_key = os.getenv("X-API-KEY")
    decodo_user = os.getenv("DECODO_USERNAME")
    decodo_pass = os.getenv("DECODO_PASSWORD")

    if not serper_key or not decodo_user or not decodo_pass:
        # Try reading from .env file
        env_path = Path.home() / "ISBN" / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.startswith("X-API-KEY="):
                        serper_key = line.split("=", 1)[1].strip()
                    elif line.startswith("DECODO_USERNAME="):
                        decodo_user = line.split("=", 1)[1].strip()
                    elif line.startswith("DECODO_PASSWORD="):
                        decodo_pass = line.split("=", 1)[1].strip()

    if not serper_key:
        print("❌ Missing Serper API key (X-API-KEY)")
        return 1
    if not decodo_user or not decodo_pass:
        print("❌ Missing Decodo credentials (DECODO_USERNAME, DECODO_PASSWORD)")
        return 1

    # Initialize Decodo client
    decodo = DecodoClient(
        username=decodo_user,
        password=decodo_pass,
        plan="core"
    )

    # Initialize database
    if args.db_path:
        db_path = Path(args.db_path)
    else:
        db_path = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = init_database(db_path)

    print(f"💾 Database: {db_path}")
    print()

    # Filter ISBNs if resuming
    if args.resume:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT isbn
            FROM ebay_sold_listings_detailed
        """)
        existing_isbns = {row[0] for row in cursor.fetchall()}

        original_count = len(isbns)
        isbns = [isbn for isbn in isbns if isbn not in existing_isbns]
        skipped = original_count - len(isbns)

        if skipped > 0:
            print(f"📝 Resuming: Skipping {skipped} ISBNs already collected")
            print(f"   Remaining: {len(isbns)} ISBNs")
            print()

    # Collect data
    print("=" * 70)
    print("Collecting eBay Sold Listings")
    print("=" * 70)
    print()

    total_new = 0
    total_skipped = 0

    for i, isbn in enumerate(isbns, 1):
        print(f"[{i}/{len(isbns)}] {isbn}")

        new_count, skip_count = await collect_isbn_sold_listings(
            isbn,
            serper_key,
            decodo,
            conn,
            args.max_per_isbn
        )

        total_new += new_count
        total_skipped += skip_count

        print(f"  ✓ Collected {new_count} new listings ({skip_count} duplicates)")

        # Throttle to respect rate limits
        await asyncio.sleep(0.5)

    # Final stats
    print()
    print("=" * 70)
    print("Collection Complete")
    print("=" * 70)
    print(f"Total new listings: {total_new}")
    print(f"Total duplicates skipped: {total_skipped}")
    print()

    # Show condition distribution
    cursor = conn.cursor()
    cursor.execute("""
        SELECT condition, COUNT(*) as cnt
        FROM ebay_sold_listings_detailed
        GROUP BY condition
        ORDER BY cnt DESC
    """)

    print("Condition Distribution:")
    for condition, count in cursor.fetchall():
        print(f"  {condition:20s} {count:6d}")

    print()

    # Show binding distribution
    cursor.execute("""
        SELECT binding, COUNT(*) as cnt
        FROM ebay_sold_listings_detailed
        WHERE binding IS NOT NULL
        GROUP BY binding
        ORDER BY cnt DESC
    """)

    print("Binding Distribution:")
    for binding, count in cursor.fetchall():
        print(f"  {binding:20s} {count:6d}")

    conn.close()
    decodo.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
