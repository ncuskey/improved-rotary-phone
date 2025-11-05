#!/usr/bin/env python3
"""
Production script to collect eBay sold listings data from WatchCount.com

WatchCount provides free access to historical eBay sold prices and sales data.
This script collects that data and stores it for market analysis.
"""

import asyncio
import sqlite3
import argparse
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from playwright.async_api import async_playwright
import random


# Database setup
DB_PATH = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'


def init_database(db_path: Path):
    """Initialize database schema for WatchCount sold listings."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchcount_sold (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT NOT NULL,

            -- Extracted fields
            price REAL,
            currency TEXT DEFAULT 'USD',
            sold_date TEXT,
            days_ago INTEGER,

            -- Listing details
            title TEXT,
            condition TEXT,
            watchers INTEGER,
            sold_quantity INTEGER,
            ebay_item_id TEXT,

            -- Sales velocity metrics
            avg_sales_per_month REAL,
            avg_sales_per_year REAL,

            -- Raw data
            raw_text TEXT,

            -- Metadata
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(isbn, ebay_item_id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_watchcount_isbn
        ON watchcount_sold(isbn)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_watchcount_sold_date
        ON watchcount_sold(sold_date)
    """)

    conn.commit()
    conn.close()
    logging.info("Database schema initialized")


def get_isbns_to_scrape(db_path: Path, limit: Optional[int] = None) -> List[str]:
    """Get ISBNs from catalog that need sold data collection."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get ISBNs from books table that don't have recent sold data
    query = """
        SELECT DISTINCT b.isbn
        FROM books b
        LEFT JOIN watchcount_sold ws ON b.isbn = ws.isbn
        WHERE ws.isbn IS NULL
           OR ws.scraped_at < datetime('now', '-30 days')
        ORDER BY RANDOM()
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    isbns = [row[0] for row in cursor.fetchall()]
    conn.close()

    logging.info(f"Found {len(isbns)} ISBNs to scrape")
    return isbns


def parse_sold_listing(raw_text: str) -> Dict:
    """
    Parse WatchCount raw text to extract structured data.

    Example raw text format:
    "Watchers: 2 * Sold: 1 * Average: 5.5 sold per year
    $5.47
    Buy It Now
    Free Shipping
    The Road (Oprah's Book Club)
    Acceptable
    aspenbookco (18,895) 99.6%
    Start: Wed, 20-Aug-25 02:34:03 UTC (2 months ago)"
    """
    data = {'raw_text': raw_text}

    # Extract watchers
    watcher_match = re.search(r'Watchers:\s*(\d+)', raw_text)
    if watcher_match:
        data['watchers'] = int(watcher_match.group(1))

    # Extract sold quantity
    sold_match = re.search(r'Sold:\s*(\d+)', raw_text)
    if sold_match:
        data['sold_quantity'] = int(sold_match.group(1))

    # Extract sales velocity
    monthly_match = re.search(r'Average:\s*([\d.]+)\s*sold per month', raw_text)
    yearly_match = re.search(r'Average:\s*([\d.]+)\s*sold per year', raw_text)
    if monthly_match:
        data['avg_sales_per_month'] = float(monthly_match.group(1))
    if yearly_match:
        data['avg_sales_per_year'] = float(yearly_match.group(1))

    # Extract price (look for $X.XX pattern)
    price_match = re.search(r'\$(\d+\.\d{2})', raw_text)
    if price_match:
        data['price'] = float(price_match.group(1))
        data['currency'] = 'USD'

    # Extract condition
    condition_keywords = ['New', 'Like New', 'Very Good', 'Good', 'Acceptable', 'Poor']
    for condition in condition_keywords:
        if condition in raw_text:
            data['condition'] = condition
            break

    # Extract date
    date_match = re.search(r'Start:\s*([^(]+)\s*\(([^)]+)\)', raw_text)
    if date_match:
        data['sold_date'] = date_match.group(1).strip()
        time_ago = date_match.group(2).strip()

        # Parse "X months ago" or "X days ago" into days_ago
        if 'month' in time_ago:
            months = re.search(r'(\d+)\s*month', time_ago)
            if months:
                data['days_ago'] = int(months.group(1)) * 30
        elif 'day' in time_ago:
            days = re.search(r'(\d+)\s*day', time_ago)
            if days:
                data['days_ago'] = int(days.group(1))
        elif 'year' in time_ago:
            years = re.search(r'(\d+)\s*year', time_ago)
            if years:
                data['days_ago'] = int(years.group(1)) * 365

    # Extract eBay item ID
    item_id_match = re.search(r'eBay-US\s*(\d+)', raw_text)
    if item_id_match:
        data['ebay_item_id'] = item_id_match.group(1)

    # Extract title (multi-line text between price section and condition)
    lines = raw_text.split('\n')
    for i, line in enumerate(lines):
        # Look for title after "See full listing" or "Shop Now"
        if 'listing' in line.lower() or 'shop now' in line.lower():
            if i + 1 < len(lines):
                # Next non-empty line is likely the title
                for j in range(i + 1, len(lines)):
                    if lines[j].strip() and lines[j].strip() not in ['Free Shipping', 'Buy It Now']:
                        data['title'] = lines[j].strip()
                        break
                break

    return data


async def scrape_watchcount_sold(isbn: str, headless: bool = True) -> List[Dict]:
    """
    Scrape WatchCount for sold listings of a specific ISBN.

    Args:
        isbn: ISBN to search for
        headless: Run browser in headless mode

    Returns:
        List of parsed sold listings
    """
    url = f"https://www.watchcount.com/sold?q={isbn}&site=EBAY_US"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            logging.debug(f"Loading WatchCount for {isbn}")
            await page.goto(url, timeout=60000, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            # Check if we need to fill in search form
            search_input = await page.query_selector('input[name="q"], input[type="text"]')
            if search_input:
                input_value = await search_input.get_attribute('value')
                if not input_value or input_value != isbn:
                    await search_input.fill(isbn)
                    search_button = await page.query_selector('button[type="submit"], input[type="submit"]')
                    if search_button:
                        await search_button.click()
                        await page.wait_for_timeout(3000)

            # Try multiple selectors to find listings
            selectors_to_try = [
                'div.item',
                'div.result',
                'tr.result-row',
                '[class*="result"]',
            ]

            items = []
            for selector in selectors_to_try:
                items = await page.query_selector_all(selector)
                logging.debug(f"Selector '{selector}': Found {len(items)} elements")
                if len(items) > 5:
                    break

            if not items and logging.getLogger().isEnabledFor(logging.DEBUG):
                # Save screenshot for debugging when no items found
                await page.screenshot(path=f'/tmp/watchcount_debug_{isbn}.png')
                logging.debug(f"Screenshot saved to /tmp/watchcount_debug_{isbn}.png")

            results = []
            for item in items[:20]:  # Limit to 20 most recent
                try:
                    item_text = await item.inner_text()

                    # Must contain price to be valid
                    if '$' not in item_text:
                        continue

                    # Parse the raw text into structured data
                    parsed = parse_sold_listing(item_text)

                    # Only include if we got at least price or item ID
                    if parsed.get('price') or parsed.get('ebay_item_id'):
                        results.append(parsed)

                except Exception as e:
                    logging.debug(f"Error parsing item: {e}")
                    continue

            logging.info(f"Found {len(results)} sold listings for {isbn}")

        except Exception as e:
            logging.error(f"Error scraping {isbn}: {e}")
            results = []

        finally:
            await browser.close()

    return results


def save_sold_listings(db_path: Path, isbn: str, listings: List[Dict]):
    """Save sold listings to database."""
    if not listings:
        logging.debug(f"No listings to save for {isbn}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    saved_count = 0
    for listing in listings:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO watchcount_sold
                (isbn, price, currency, sold_date, days_ago, title, condition,
                 watchers, sold_quantity, ebay_item_id,
                 avg_sales_per_month, avg_sales_per_year, raw_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                isbn,
                listing.get('price'),
                listing.get('currency', 'USD'),
                listing.get('sold_date'),
                listing.get('days_ago'),
                listing.get('title'),
                listing.get('condition'),
                listing.get('watchers'),
                listing.get('sold_quantity'),
                listing.get('ebay_item_id'),
                listing.get('avg_sales_per_month'),
                listing.get('avg_sales_per_year'),
                listing.get('raw_text')
            ))
            saved_count += 1
        except sqlite3.IntegrityError:
            logging.debug(f"Duplicate listing for {isbn}, item {listing.get('ebay_item_id')}")
            continue

    conn.commit()
    conn.close()

    if saved_count > 0:
        logging.info(f"✓ Saved {saved_count} sold listings for {isbn}")


async def process_batch(isbns: List[str], db_path: Path, headless: bool = True):
    """Process a batch of ISBNs with rate limiting."""
    total = len(isbns)

    for i, isbn in enumerate(isbns, 1):
        logging.info(f"\n[{i}/{total}] Processing {isbn}")

        try:
            # Scrape sold listings
            listings = await scrape_watchcount_sold(isbn, headless=headless)

            # Save to database
            if listings:
                save_sold_listings(db_path, isbn, listings)
            else:
                logging.info(f"No sold listings found for {isbn}")

            # Rate limiting: 8-15 seconds between requests
            if i < total:
                delay = random.uniform(8, 15)
                logging.debug(f"Waiting {delay:.1f}s before next request")
                await asyncio.sleep(delay)

        except Exception as e:
            logging.error(f"Error processing {isbn}: {e}")
            continue


async def main():
    parser = argparse.ArgumentParser(
        description='Collect eBay sold listings data from WatchCount'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of ISBNs to process'
    )
    parser.add_argument(
        '--isbn',
        type=str,
        help='Test with a single ISBN'
    )
    parser.add_argument(
        '--visible',
        action='store_true',
        help='Show browser window (not headless)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Initialize database
    init_database(DB_PATH)

    # Get ISBNs to process
    if args.isbn:
        isbns = [args.isbn]
        logging.info(f"Testing with single ISBN: {args.isbn}")
    else:
        isbns = get_isbns_to_scrape(DB_PATH, limit=args.limit)

    if not isbns:
        logging.info("No ISBNs to process")
        return

    logging.info(f"\n{'='*80}")
    logging.info(f"Starting WatchCount sold listings collection")
    logging.info(f"ISBNs to process: {len(isbns)}")
    logging.info(f"{'='*80}\n")

    # Process ISBNs
    await process_batch(isbns, DB_PATH, headless=not args.visible)

    logging.info(f"\n{'='*80}")
    logging.info("Collection complete")
    logging.info(f"{'='*80}")


if __name__ == '__main__':
    asyncio.run(main())
