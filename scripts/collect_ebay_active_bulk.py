"""
Parallel eBay Browse API collection for active listings.
Optimized for maximum throughput with rate limiting.

eBay Browse API limits (Production):
- 5000 calls/day per app
- Burst: ~10 req/sec
"""
import asyncio
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

import aiohttp

# Config
DB_PATH = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"
EBAY_RATE = 8  # req/sec (conservative from 10 limit)
CONCURRENCY = 30  # Process 30 ISBNs in parallel
BATCH_SIZE = 100  # Progress reporting
MAX_DAILY_CALLS = 5000  # eBay daily limit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class EbayListing:
    """eBay active listing data"""
    isbn: str
    item_id: str
    title: str
    price: float
    condition: str
    binding: Optional[str]
    seller: Optional[str]
    listing_url: str
    image_url: Optional[str]
    shipping_cost: Optional[float]
    item_location: Optional[str]

# Rate limiting semaphore
ebay_semaphore = None
call_count = 0
call_count_lock = asyncio.Lock()

async def get_bearer_token(session: aiohttp.ClientSession) -> str:
    """Get eBay OAuth token"""
    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET required")

    import base64
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    async with session.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data="grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
        timeout=aiohttp.ClientTimeout(total=15)
    ) as response:
        data = await response.json()
        return data["access_token"]

async def search_ebay_isbn(isbn: str, token: str, session: aiohttp.ClientSession) -> List[EbayListing]:
    """Search eBay Browse API for active listings by ISBN"""
    global call_count

    async with ebay_semaphore:
        async with call_count_lock:
            call_count += 1
            if call_count > MAX_DAILY_CALLS:
                logger.warning(f"Approaching daily limit ({call_count}/{MAX_DAILY_CALLS})")

        try:
            url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
            params = {
                "q": isbn,
                "limit": 50,  # Max results per request
                "filter": "buyingOptions:{FIXED_PRICE}",
            }
            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            }

            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 429:
                    logger.warning(f"Rate limited on ISBN {isbn}")
                    await asyncio.sleep(5)
                    return []

                if response.status != 200:
                    logger.debug(f"eBay API error {response.status} for {isbn}")
                    return []

                data = await response.json()
                listings = []

                for item in data.get("itemSummaries", []):
                    try:
                        # Extract price
                        price_obj = item.get("price", {})
                        price = float(price_obj.get("value", 0))

                        # Extract binding from title
                        title = item.get("title", "")
                        binding = None
                        title_lower = title.lower()
                        if "hardcover" in title_lower or "hardback" in title_lower:
                            binding = "Hardcover"
                        elif "paperback" in title_lower or "softcover" in title_lower:
                            binding = "Paperback"

                        # Extract shipping
                        shipping_cost = None
                        shipping = item.get("shippingOptions", [])
                        if shipping:
                            shipping_cost_obj = shipping[0].get("shippingCost", {})
                            if shipping_cost_obj:
                                shipping_cost = float(shipping_cost_obj.get("value", 0))

                        listing = EbayListing(
                            isbn=isbn,
                            item_id=item.get("itemId", ""),
                            title=title[:200],
                            price=price,
                            condition=item.get("condition", ""),
                            binding=binding,
                            seller=item.get("seller", {}).get("username"),
                            listing_url=item.get("itemWebUrl", ""),
                            image_url=item.get("image", {}).get("imageUrl"),
                            shipping_cost=shipping_cost,
                            item_location=item.get("itemLocation", {}).get("city"),
                        )
                        listings.append(listing)

                    except (KeyError, ValueError, TypeError) as e:
                        logger.debug(f"Parse error for {isbn}: {e}")
                        continue

                return listings

        except asyncio.TimeoutError:
            logger.debug(f"Timeout for ISBN {isbn}")
            return []
        except Exception as e:
            logger.debug(f"Error for ISBN {isbn}: {e}")
            return []

def store_listings(listings: List[EbayListing], conn):
    """Store eBay listings in database"""
    cursor = conn.cursor()

    # Create table if needed
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ebay_active_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT NOT NULL,
            item_id TEXT NOT NULL,
            title TEXT,
            price REAL,
            condition TEXT,
            binding TEXT,
            seller TEXT,
            listing_url TEXT,
            image_url TEXT,
            shipping_cost REAL,
            item_location TEXT,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(isbn, item_id)
        )
    """)

    for listing in listings:
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO ebay_active_listings
                (isbn, item_id, title, price, condition, binding, seller,
                 listing_url, image_url, shipping_cost, item_location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                listing.isbn, listing.item_id, listing.title, listing.price,
                listing.condition, listing.binding, listing.seller,
                listing.listing_url, listing.image_url, listing.shipping_cost,
                listing.item_location
            ))
        except sqlite3.IntegrityError:
            pass

    conn.commit()

def get_isbns_to_collect(conn, limit=None) -> List[str]:
    """Get ISBNs that need eBay data"""
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='ebay_active_listings'
    """)
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        # First run - get all ISBNs
        query = "SELECT DISTINCT isbn FROM cached_books ORDER BY isbn"
    else:
        # Get ISBNs not yet collected or stale (>7 days old)
        query = """
        SELECT DISTINCT isbn FROM cached_books
        WHERE isbn NOT IN (
            SELECT DISTINCT isbn FROM ebay_active_listings
            WHERE collected_at > datetime('now', '-7 days')
        )
        ORDER BY isbn
        """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    return [r[0] for r in cursor.fetchall()]

async def process_batch(isbns: List[str], token: str) -> List[EbayListing]:
    """Process a batch of ISBNs concurrently"""
    async with aiohttp.ClientSession() as session:
        tasks = [search_ebay_isbn(isbn, token, session) for isbn in isbns]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten results
        all_listings = []
        for result in results:
            if isinstance(result, list):
                all_listings.extend(result)

        return all_listings

async def main(limit=None, max_calls=None):
    """Main collection function"""
    global ebay_semaphore, call_count

    if max_calls:
        global MAX_DAILY_CALLS
        MAX_DAILY_CALLS = max_calls

    # Initialize rate limit semaphore
    ebay_semaphore = asyncio.Semaphore(EBAY_RATE)

    # Get OAuth token
    async with aiohttp.ClientSession() as session:
        token = await get_bearer_token(session)

    logger.info(f"Got eBay OAuth token")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    isbns = get_isbns_to_collect(conn, limit)

    logger.info(f"Processing {len(isbns)} ISBNs with {CONCURRENCY}x parallelization")
    logger.info(f"Rate: {EBAY_RATE} req/sec, Daily limit: {MAX_DAILY_CALLS}")

    if not isbns:
        logger.info("Nothing to collect!")
        return

    total_listings = 0
    start = time.time()

    # Process in concurrent batches
    for i in range(0, len(isbns), CONCURRENCY):
        batch = isbns[i:i+CONCURRENCY]
        batch_start = time.time()

        # Check if we're approaching daily limit
        if call_count >= MAX_DAILY_CALLS * 0.95:
            logger.warning(f"Approaching daily limit ({call_count}/{MAX_DAILY_CALLS}), stopping")
            break

        # Process batch
        listings = await process_batch(batch, token)

        # Store results
        if listings:
            store_listings(listings, conn)
            total_listings += len(listings)

        batch_time = time.time() - batch_start

        # Progress reporting
        done = min(i + len(batch), len(isbns))
        if done % BATCH_SIZE == 0 or done == len(isbns):
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            remain = len(isbns) - done
            eta = remain / rate / 60 if rate > 0 else 0

            logger.info(f"Progress: {done}/{len(isbns)} ({100*done/len(isbns):.1f}%)")
            logger.info(f"Rate: {rate:.2f} ISBNs/sec, Batch: {batch_time:.1f}s")
            logger.info(f"Listings: {total_listings}, API calls: {call_count}, ETA: {eta:.1f} min")

    conn.close()

    logger.info(f"\n{'='*60}")
    logger.info(f"DONE: {done}/{len(isbns)} ISBNs, {total_listings} listings")
    logger.info(f"Time: {(time.time()-start)/60:.1f} min")
    logger.info(f"API calls used: {call_count}/{MAX_DAILY_CALLS}")
    logger.info(f"Avg: {total_listings/done if done else 0:.1f} listings/ISBN")

if __name__ == "__main__":
    import sys
    limit = None
    max_calls = None

    if "--test" in sys.argv:
        limit = 50
        max_calls = 100
        logger.info("TEST: 50 ISBNs, 100 API calls max")
    elif any(a.startswith("--limit=") for a in sys.argv):
        limit = int([a for a in sys.argv if a.startswith("--limit=")][0].split("=")[1])

    if any(a.startswith("--max-calls=") for a in sys.argv):
        max_calls = int([a for a in sys.argv if a.startswith("--max-calls=")][0].split("=")[1])

    asyncio.run(main(limit, max_calls))
