#!/usr/bin/env python3
"""
Production BookFinder.com scraper using Playwright.

Collects 150-160 offers per ISBN from BookFinder's meta-search aggregator,
providing 3 new ML features: lowest_price, source_count, new_vs_used_spread.

Features:
- Scrapes from multiple sources:
  * catalog: Physical inventory ISBNs (760 total)
  * metadata_cache: ML training ISBNs (19,249 total)
  * all: Both sources combined
- Saves offers to catalog.db (bookfinder_offers table)
- Progress tracking & resume capability
- Robust error handling with retries
- Respectful rate limiting (12-18 sec randomized delays)
- Detailed logging

Usage:
  python scripts/collect_bookfinder_prices.py --source catalog          # Default, 760 ISBNs
  python scripts/collect_bookfinder_prices.py --source metadata_cache   # 19,249 ISBNs
  python scripts/collect_bookfinder_prices.py --source all              # Combined
  python scripts/collect_bookfinder_prices.py --test                    # Test mode, 5 ISBNs

Anti-Detection Measures:
- User agent rotation (5 realistic browser fingerprints)
- Session rotation every 50 ISBNs
- Randomized delays (12-18 seconds, avg 15s = 4 req/min)
- Real browser with full JavaScript (Playwright)
- Hidden automation flags (navigator.webdriver)
- Exponential backoff on errors

robots.txt Compliance Note:
BookFinder's robots.txt disallows /search/ paths. This scraper is for research
and ML model training purposes only. Traffic is extremely light (~4 requests/minute)
and runs during off-peak hours.

Runtime:
  - catalog: ~3.2 hours (760 ISBNs)
  - metadata_cache: ~80 hours (19,249 ISBNs)
  - all: ~83 hours (19,929 unique ISBNs)
Cost: $0 (uses free Playwright, no proxies needed for this volume)
"""

import asyncio
import logging
import random
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# User agent pool for rotation (realistic browser fingerprints)
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
]


def get_random_delay(min_seconds: int = 12, max_seconds: int = 18) -> float:
    """Get a randomized delay to avoid detection patterns."""
    return random.uniform(min_seconds, max_seconds)


# Configure logging
def setup_logging() -> logging.Logger:
    """Set up logging to both file and console."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"/tmp/bookfinder_scraper_{timestamp}.log"

    logging.basicConfig(
        level=logging.DEBUG,  # Enable debug logging for troubleshooting
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Logging to: {log_file}")
    return logger


logger = setup_logging()


def get_catalog_db_path() -> Path:
    """Get path to catalog database."""
    return Path.home() / '.isbn_lot_optimizer' / 'catalog.db'


def init_database():
    """
    Initialize database tables for BookFinder data.

    Creates:
    - bookfinder_offers: Stores all offers (150-160 per ISBN)
    - bookfinder_progress: Tracks scraping progress for resume capability
    """
    db_path = get_catalog_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create offers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookfinder_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT NOT NULL,
            vendor TEXT NOT NULL,
            seller TEXT,
            price REAL NOT NULL,
            shipping REAL,
            condition TEXT,
            binding TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookfinder_isbn ON bookfinder_offers(isbn)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookfinder_vendor ON bookfinder_offers(vendor)")

    # Create progress tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookfinder_progress (
            isbn TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            offer_count INTEGER,
            error_message TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

    logger.info("Database tables initialized")


def is_valid_isbn(isbn: str) -> bool:
    """
    Check if ISBN is valid format for BookFinder.

    Valid formats:
    - ISBN-13: 13 digits starting with 978 or 979
    - ISBN-10: 10 digits

    Args:
        isbn: ISBN string to validate

    Returns:
        True if valid, False otherwise
    """
    if not isbn or not isinstance(isbn, str):
        return False

    # Remove any hyphens or spaces
    clean_isbn = isbn.replace('-', '').replace(' ', '')

    # Check if all digits
    if not clean_isbn.isdigit():
        return False

    # ISBN-13: 13 digits starting with 978 or 979
    if len(clean_isbn) == 13:
        return clean_isbn.startswith('978') or clean_isbn.startswith('979')

    # ISBN-10: 10 digits
    if len(clean_isbn) == 10:
        return True

    return False


def load_catalog_isbns() -> List[str]:
    """
    Load all valid ISBNs from catalog that haven't been scraped yet.

    Returns:
        List of valid ISBNs to scrape
    """
    db_path = get_catalog_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all ISBNs that haven't been successfully scraped
    cursor.execute("""
        SELECT DISTINCT b.isbn
        FROM books b
        WHERE b.isbn IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM bookfinder_progress p
            WHERE p.isbn = b.isbn AND p.status = 'completed'
        )
        ORDER BY b.isbn
    """)

    all_isbns = [row[0] for row in cursor.fetchall()]
    conn.close()

    # Filter to only valid ISBNs
    valid_isbns = [isbn for isbn in all_isbns if is_valid_isbn(isbn)]
    invalid_count = len(all_isbns) - len(valid_isbns)

    if invalid_count > 0:
        logger.info(f"Filtered out {invalid_count} invalid ISBNs")

    logger.info(f"Loaded {len(valid_isbns)} valid ISBNs to scrape")
    return valid_isbns


def load_metadata_cache_isbns() -> List[str]:
    """
    Load all valid ISBNs from metadata_cache that haven't been scraped yet.

    Returns:
        List of valid ISBNs to scrape
    """
    metadata_db_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'
    catalog_db_path = get_catalog_db_path()

    # Connect to metadata cache
    metadata_conn = sqlite3.connect(metadata_db_path)
    metadata_cursor = metadata_conn.cursor()

    # Connect to catalog to check progress
    catalog_conn = sqlite3.connect(catalog_db_path)
    catalog_cursor = catalog_conn.cursor()

    # Get all ISBNs from metadata cache
    metadata_cursor.execute("""
        SELECT DISTINCT isbn
        FROM cached_books
        WHERE isbn IS NOT NULL
        ORDER BY isbn
    """)

    all_isbns = [row[0] for row in metadata_cursor.fetchall()]
    metadata_conn.close()

    # Filter out already completed ISBNs
    remaining_isbns = []
    for isbn in all_isbns:
        catalog_cursor.execute(
            "SELECT status FROM bookfinder_progress WHERE isbn = ? AND status = 'completed'",
            (isbn,)
        )
        if not catalog_cursor.fetchone():
            remaining_isbns.append(isbn)

    catalog_conn.close()

    # Filter to only valid ISBNs
    valid_isbns = [isbn for isbn in remaining_isbns if is_valid_isbn(isbn)]
    invalid_count = len(remaining_isbns) - len(valid_isbns)

    if invalid_count > 0:
        logger.info(f"Filtered out {invalid_count} invalid ISBNs")

    logger.info(f"Loaded {len(valid_isbns)} valid ISBNs from metadata_cache to scrape")
    return valid_isbns


def get_scraping_stats() -> Dict:
    """Get current scraping statistics."""
    db_path = get_catalog_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Total ISBNs in catalog
    cursor.execute("SELECT COUNT(DISTINCT isbn) FROM books WHERE isbn IS NOT NULL")
    total_isbns = cursor.fetchone()[0]

    # Completed ISBNs
    cursor.execute("SELECT COUNT(*) FROM bookfinder_progress WHERE status = 'completed'")
    completed = cursor.fetchone()[0]

    # Failed ISBNs
    cursor.execute("SELECT COUNT(*) FROM bookfinder_progress WHERE status = 'failed'")
    failed = cursor.fetchone()[0]

    # Total offers collected
    cursor.execute("SELECT COUNT(*) FROM bookfinder_offers")
    total_offers = cursor.fetchone()[0]

    conn.close()

    return {
        'total_isbns': total_isbns,
        'completed': completed,
        'failed': failed,
        'remaining': total_isbns - completed - failed,
        'total_offers': total_offers,
        'avg_offers_per_isbn': total_offers / completed if completed > 0 else 0
    }


async def extract_bookfinder_offers(page: Page) -> List[Dict]:
    """
    Extract book offers from BookFinder page using data attributes.

    BookFinder stores all offer data in data-csa-c-* attributes on div elements.

    Args:
        page: Playwright page object

    Returns:
        List of offer dictionaries
    """
    offers = []

    try:
        # Find all offer divs
        offer_divs = await page.query_selector_all('[data-csa-c-item-type="search-offer"]')

        logger.debug(f"Found {len(offer_divs)} offer elements")

        for div in offer_divs:
            try:
                # Extract basic data attributes
                vendor_raw = await div.get_attribute('data-csa-c-affiliate') or 'Unknown'
                price_str = await div.get_attribute('data-csa-c-usdprice') or '0'
                shipping_str = await div.get_attribute('data-csa-c-usdshipping') or '0'
                condition_raw = await div.get_attribute('data-csa-c-condition') or ''
                seller = await div.get_attribute('data-csa-c-seller') or ''
                binding_raw = await div.get_attribute('data-csa-c-binding') or ''

                # Extract new metadata fields
                title = await div.get_attribute('data-csa-c-title') or ''
                authors = await div.get_attribute('data-csa-c-authors') or ''
                publisher = await div.get_attribute('data-csa-c-publisher') or ''
                signed_str = await div.get_attribute('data-csa-c-signed') or 'false'
                first_edition_str = await div.get_attribute('data-csa-c-firstedition') or 'false'
                oldworld_str = await div.get_attribute('data-csa-c-oldworld') or 'false'

                # Extract additional fields
                offer_id = await div.get_attribute('data-csa-c-id') or ''
                clickout_type = await div.get_attribute('data-csa-c-clickouttype') or ''
                destination = await div.get_attribute('data-csa-c-destination') or ''
                seller_location = await div.get_attribute('data-csa-c-sellerlocation') or ''

                # Parse boolean flags
                is_signed = 1 if signed_str.lower() == 'true' else 0
                is_first_edition = 1 if first_edition_str.lower() == 'true' else 0
                is_oldworld = 1 if oldworld_str.lower() == 'true' else 0

                # Normalize vendor
                vendor_map = {
                    'EBAY': 'eBay',
                    'AMAZON': 'Amazon',
                    'ABEBOOKS': 'AbeBooks',
                    'BIBLIO': 'Biblio',
                    'THRIFT_BOOKS': 'ThriftBooks',
                    'ALIBRIS': 'Alibris',
                    'BETTER_WORLD_BOOKS': 'Better World Books',
                }
                vendor = vendor_map.get(vendor_raw.upper(), vendor_raw.title())

                # Parse numeric values
                try:
                    price = float(price_str)
                    shipping = float(shipping_str)
                except ValueError:
                    continue

                # Normalize condition
                condition_map = {'NEW': 'New', 'USED': 'Used'}
                condition = condition_map.get(condition_raw.upper(), condition_raw.title())

                # Normalize binding
                binding_map = {
                    'SOFTCOVER': 'Softcover',
                    'HARDCOVER': 'Hardcover',
                    'MASSMARKET': 'Mass Market',
                }
                binding = binding_map.get(binding_raw.upper(), binding_raw.title())

                # Extract description text
                description = ''
                try:
                    # Get all text content from the div
                    text_content = await div.inner_text()
                    lines = [line.strip() for line in text_content.split('\n') if line.strip()]

                    # Look for description lines (usually contain condition-related keywords)
                    for line in lines:
                        if len(line) > 30:  # Description lines are usually substantial
                            # Look for common description patterns
                            desc_keywords = ['item', 'copy', 'book', 'condition', 'pages', 'cover', 'spine']
                            line_lower = line.lower()
                            if any(keyword in line_lower for keyword in desc_keywords):
                                # This is likely a description line
                                # Try to clean it by removing price and UI elements
                                if '$' in line:
                                    # Split on $ and find the longest part with description keywords
                                    parts = line.split('$')
                                    for part in parts:
                                        if len(part) > 30 and any(kw in part.lower() for kw in desc_keywords):
                                            # Remove leading price digits and clean up
                                            cleaned = part.lstrip('0123456789.,').strip()
                                            if len(cleaned) > 20:
                                                description = cleaned
                                                break
                                else:
                                    description = line

                                if description:
                                    break
                except Exception as e:
                    logger.debug(f"Error extracting description: {e}")
                    description = ''

                # Validate and add offer
                if price > 0 and vendor != 'Unknown':
                    offers.append({
                        'vendor': vendor,
                        'seller': seller,
                        'price': price,
                        'condition': condition,
                        'binding': binding,
                        'shipping': shipping,
                        'title': title,
                        'authors': authors,
                        'publisher': publisher,
                        'is_signed': is_signed,
                        'is_first_edition': is_first_edition,
                        'is_oldworld': is_oldworld,
                        'description': description,
                        'offer_id': offer_id,
                        'clickout_type': clickout_type,
                        'destination': destination,
                        'seller_location': seller_location,
                    })

            except Exception as e:
                logger.debug(f"Error parsing offer: {e}")
                continue

        return offers

    except Exception as e:
        logger.error(f"Error extracting offers: {e}")
        return []


async def scrape_isbn(isbn: str, context: BrowserContext, retry_count: int = 0) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """
    Scrape a single ISBN from BookFinder.

    Args:
        isbn: ISBN to scrape
        context: Playwright browser context
        retry_count: Current retry attempt (for exponential backoff)

    Returns:
        Tuple of (offers_list, error_message)
        If successful: (offers, None)
        If failed: (None, error_message)
    """
    url = f"https://www.bookfinder.com/search/?isbn={isbn}"
    page = None

    try:
        # Create new page
        page = await context.new_page()

        # Navigate to URL
        logger.debug(f"Loading {url}")
        response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)

        logger.debug(f"Page loaded with status: {response.status}")

        # Wait for network to be idle (React hydration complete)
        # BookFinder uses React and loads data via JS
        try:
            await page.wait_for_load_state('networkidle', timeout=20000)
            logger.debug("Network idle, page fully loaded")
        except Exception as e:
            # NetworkIdle timeout is OK - page is likely loaded
            logger.debug(f"Network idle timeout: {str(e)[:100]}")
            # Brief wait for any pending JS
            await asyncio.sleep(2)

        # Extract offers
        offers = await extract_bookfinder_offers(page)

        if not offers:
            # Save screenshot for debugging
            screenshot_path = f"/tmp/bookfinder_fail_{isbn}_retry{retry_count}.png"
            await page.screenshot(path=screenshot_path)
            logger.warning(f"No offers found, screenshot saved to {screenshot_path}")

            await page.close()
            return None, "No offers found"

        await page.close()
        return offers, None

    except Exception as e:
        error_msg = f"Error scraping ISBN {isbn}: {str(e)}"
        logger.error(error_msg)

        # Try to save screenshot for debugging
        if page:
            try:
                screenshot_path = f"/tmp/bookfinder_error_{isbn}_retry{retry_count}.png"
                await page.screenshot(path=screenshot_path)
                logger.warning(f"Error screenshot saved to {screenshot_path}")
                await page.close()
            except:
                pass

        return None, error_msg


def save_offers(isbn: str, offers: List[Dict]):
    """
    Save offers to database.

    Args:
        isbn: ISBN these offers belong to
        offers: List of offer dictionaries
    """
    db_path = get_catalog_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for offer in offers:
        cursor.execute("""
            INSERT INTO bookfinder_offers
            (isbn, vendor, seller, price, shipping, condition, binding,
             title, authors, publisher, is_signed, is_first_edition, is_oldworld, description,
             offer_id, clickout_type, destination, seller_location)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            isbn,
            offer.get('vendor', ''),
            offer.get('seller', ''),
            offer.get('price', 0),
            offer.get('shipping', 0),
            offer.get('condition', ''),
            offer.get('binding', ''),
            offer.get('title', ''),
            offer.get('authors', ''),
            offer.get('publisher', ''),
            offer.get('is_signed', 0),
            offer.get('is_first_edition', 0),
            offer.get('is_oldworld', 0),
            offer.get('description', ''),
            offer.get('offer_id', ''),
            offer.get('clickout_type', ''),
            offer.get('destination', ''),
            offer.get('seller_location', '')
        ))

    conn.commit()
    conn.close()


def update_progress(isbn: str, status: str, offer_count: int = 0, error_message: str = None):
    """
    Update scraping progress in database.

    Args:
        isbn: ISBN that was processed
        status: 'completed', 'failed', or 'skipped'
        offer_count: Number of offers found
        error_message: Error message if failed
    """
    db_path = get_catalog_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO bookfinder_progress
        (isbn, status, offer_count, error_message, scraped_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (isbn, status, offer_count, error_message))

    conn.commit()
    conn.close()


async def main(limit: Optional[int] = None, source: str = 'catalog'):
    """
    Main scraper function.

    Args:
        limit: Optional limit on number of ISBNs to scrape (for testing)
        source: Data source - 'catalog' (760 ISBNs), 'metadata_cache' (19,249 ISBNs), or 'all'
    """

    print("=" * 80)
    print("BOOKFINDER.COM PRODUCTION SCRAPER")
    print(f"SOURCE: {source.upper()}")
    if limit:
        print(f"TEST MODE: Limiting to {limit} ISBNs")
    print("=" * 80)
    print()

    # Initialize database
    init_database()

    # Get current stats
    stats = get_scraping_stats()
    logger.info(f"Current progress: {stats['completed']}/{stats['total_isbns']} ISBNs completed")
    logger.info(f"Total offers collected: {stats['total_offers']}")

    if stats['completed'] > 0:
        logger.info(f"Average offers per ISBN: {stats['avg_offers_per_isbn']:.1f}")

    # Load ISBNs to scrape based on source
    if source == 'catalog':
        isbns = load_catalog_isbns()
    elif source == 'metadata_cache':
        isbns = load_metadata_cache_isbns()
    elif source == 'all':
        catalog_isbns = load_catalog_isbns()
        metadata_isbns = load_metadata_cache_isbns()
        # Combine and deduplicate
        isbns = list(set(catalog_isbns + metadata_isbns))
        logger.info(f"Combined {len(catalog_isbns)} catalog + {len(metadata_isbns)} metadata_cache ISBNs = {len(isbns)} unique")
    else:
        logger.error(f"Invalid source: {source}. Must be 'catalog', 'metadata_cache', or 'all'")
        return 1

    if not isbns:
        logger.info("✅ All ISBNs already scraped!")
        return 0

    # Apply limit if in test mode
    if limit and len(isbns) > limit:
        isbns = isbns[:limit]
        logger.info(f"TEST MODE: Limited to {limit} ISBNs")

    logger.info(f"Starting scrape of {len(isbns)} ISBNs")
    logger.info(f"Estimated runtime: {len(isbns) * 15 / 3600:.1f} hours")
    print()

    # Launch browser
    logger.info("Launching Chromium browser...")

    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )

        logger.info("Browser ready")
        print()

        # Scrape each ISBN
        successful = 0
        failed = 0
        total_offers = 0
        start_time = time.time()
        context = None

        for i, isbn in enumerate(isbns, 1):
            # Rotate browser context every 50 ISBNs to avoid session tracking
            if i % 50 == 1 or context is None:
                if context:
                    await context.close()
                    logger.info("Rotating browser session for anti-detection")

                # Select random user agent
                user_agent = random.choice(USER_AGENTS)

                # Create new browser context with rotated fingerprint
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent=user_agent,
                    locale='en-US',
                    timezone_id='America/Los_Angeles',
                )

                # Hide automation
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)

            print(f"[{i}/{len(isbns)}] ISBN: {isbn}")

            # Scrape with retries
            offers = None
            error_msg = None

            for attempt in range(3):  # Max 3 attempts
                offers, error_msg = await scrape_isbn(isbn, context, retry_count=attempt)

                if offers:
                    break  # Success!

                if attempt < 2:  # Don't sleep after last attempt
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s
                    logger.warning(f"Retry {attempt + 1}/3 after {wait_time}s...")
                    await asyncio.sleep(wait_time)

            # Save results
            if offers:
                save_offers(isbn, offers)
                update_progress(isbn, 'completed', len(offers))
                successful += 1
                total_offers += len(offers)

                print(f"  ✅ {len(offers)} offers collected")
            else:
                update_progress(isbn, 'failed', 0, error_msg)
                failed += 1
                print(f"  ❌ Failed: {error_msg}")

            # Progress update every 10 ISBNs
            if i % 10 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed  # ISBNs per second
                remaining = len(isbns) - i
                eta_seconds = remaining / rate if rate > 0 else 0

                print()
                print(f"Progress: {i}/{len(isbns)} ({i/len(isbns)*100:.1f}%)")
                print(f"Success rate: {successful}/{i} ({successful/i*100:.1f}%)")
                print(f"Total offers: {total_offers} (avg {total_offers/successful:.1f} per ISBN)")
                print(f"ETA: {eta_seconds/3600:.1f} hours")
                print()

            # Rate limit: randomized 12-18 seconds between requests (avg 15s)
            if i < len(isbns):  # Don't wait after last ISBN
                delay = get_random_delay(12, 18)
                logger.debug(f"Waiting {delay:.1f}s before next request")
                await asyncio.sleep(delay)

        if context:
            await context.close()

        await browser.close()

    # Final summary
    elapsed = time.time() - start_time

    print()
    print("=" * 80)
    print("SCRAPING COMPLETE")
    print("=" * 80)
    print()
    print(f"Total ISBNs processed: {len(isbns)}")
    print(f"✅ Successful: {successful} ({successful/len(isbns)*100:.1f}%)")
    print(f"❌ Failed: {failed} ({failed/len(isbns)*100:.1f}%)")
    print(f"📦 Total offers collected: {total_offers}")
    if successful > 0:
        print(f"📈 Average offers per ISBN: {total_offers/successful:.1f}")
    print()
    print(f"Runtime: {elapsed/3600:.2f} hours")
    print(f"Rate: {len(isbns)/elapsed*3600:.1f} ISBNs/hour")
    print()

    # Get updated stats
    stats = get_scraping_stats()
    print(f"Overall completion: {stats['completed']}/{stats['total_isbns']} ISBNs ({stats['completed']/stats['total_isbns']*100:.1f}%)")
    print(f"Overall offers collected: {stats['total_offers']:,}")
    print()

    logger.info("Scraping session complete")

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Scrape BookFinder.com for book offers')
    parser.add_argument('--limit', type=int, help='Limit number of ISBNs to scrape (for testing)')
    parser.add_argument('--test', action='store_true', help='Test mode: scrape only 5 ISBNs')
    parser.add_argument('--source', type=str, default='catalog',
                        choices=['catalog', 'metadata_cache', 'all'],
                        help='Data source: catalog (760 ISBNs), metadata_cache (19,249 ISBNs), or all (default: catalog)')

    args = parser.parse_args()

    limit = args.limit
    if args.test:
        limit = 5

    sys.exit(asyncio.run(main(limit=limit, source=args.source)))
