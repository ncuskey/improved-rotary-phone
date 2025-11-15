"""
Parallelized edition data collection using Serper + Decodo.
Maximizes throughput with async processing and proper rate limiting.
"""
import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import aiohttp
from shared.decodo import DecodoClient

# Config - OPTIMIZED FOR SPEED
DB_PATH = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"
SERPER_RATE = 45  # req/sec (conservative from 50 limit)
DECODO_RATE = 30  # req/sec (Core plan limit)
CONCURRENCY = 20  # Process 20 ISBNs in parallel
BATCH_SIZE = 100  # ISBNs per progress report

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class Offer:
    isbn: str
    marketplace: str
    price: float
    edition_type: str
    edition_confidence: float
    edition_text: str
    url: str
    source: str
    title: str = ""

class Classifier:
    FIRST = [(r'\b1st\s+edition\b', 0.9), (r'\bfirst\s+edition\b', 0.9),
             (r'\b1st\s+ed\.?\b', 0.8), (r'\bfirst\s+printing\b', 0.85)]
    LATER = [(r'\blater\s+printing\b', 0.9), (r'\breprint\b', 0.85),
             (r'\b\d+(?:nd|rd|th)\s+edition\b', 0.95)]

    @classmethod
    def classify(cls, text: str) -> Tuple[str, float, str]:
        lower = text.lower()
        for pat, conf in cls.FIRST:
            if m := re.search(pat, lower):
                return ('first', conf, m.group())
        for pat, conf in cls.LATER:
            if m := re.search(pat, lower):
                return ('later', conf, m.group())
        return ('unknown', 0.0, '')

def extract_price(text: str) -> Optional[float]:
    if m := re.search(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', text):
        try:
            return float(m.group(1).replace(',', ''))
        except:
            pass
    return None

def detect_marketplace(url: str) -> str:
    for d, m in [('ebay.com', 'ebay'), ('abebooks.com', 'abebooks'),
                 ('amazon.com', 'amazon')]:
        if d in url.lower():
            return m
    return 'other'

# Semaphores for rate limiting
serper_semaphore = None
decodo_semaphore = None

async def search_serper(isbn: str, key: str, session) -> List[Dict]:
    """Rate-limited Serper search."""
    async with serper_semaphore:
        try:
            async with session.post(
                "https://google.serper.dev/search",
                json={
                    "q": f'{isbn} "first edition" OR "1st edition" site:ebay.com OR site:abebooks.com OR site:amazon.com',
                    "num": 20
                },
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("organic", [])
        except Exception as e:
            logger.debug(f"Serper error {isbn}: {e}")
        return []

async def scrape_with_decodo_async(url: str, decodo: DecodoClient, session) -> Optional[str]:
    """Rate-limited async Decodo scraping."""
    async with decodo_semaphore:
        try:
            # Use synchronous DecodoClient in async context with run_in_executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, decodo.scrape_url, url)
            if response.status_code == 200:
                return response.body
        except Exception as e:
            logger.debug(f"Decodo error {url}: {e}")
        return None

def parse_scraped_page(html: str, url: str, isbn: str) -> Optional[Offer]:
    """Parse scraped HTML for price and edition info."""
    price = extract_price(html)
    if not price:
        return None

    edition_type, confidence, text = Classifier.classify(html)
    marketplace = detect_marketplace(url)

    title_match = re.search(r'<title>([^<]+)</title>', html, re.I)
    title = title_match.group(1) if title_match else ""

    return Offer(
        isbn=isbn,
        marketplace=marketplace,
        price=price,
        edition_type=edition_type,
        edition_confidence=confidence,
        edition_text=text,
        url=url,
        source='decodo_scrape',
        title=title[:200]
    )

def store_offers(offers: List[Offer], conn):
    """Store offers in database."""
    cursor = conn.cursor()
    for o in offers:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO edition_offers
                (isbn, marketplace, price, edition_type, edition_confidence,
                 edition_text, listing_url, source_type, title)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (o.isbn, o.marketplace, o.price, o.edition_type,
                  o.edition_confidence, o.edition_text, o.url, o.source, o.title))
        except:
            pass
    conn.commit()

async def process_isbn(isbn: str, serper_key: str, decodo: DecodoClient, session) -> List[Offer]:
    """Process one ISBN: Serper search + parallel Decodo scraping."""
    offers = []

    # Phase 1: Serper search
    results = await search_serper(isbn, serper_key, session)

    if not results:
        return offers

    # Phase 2: Parallel Decodo scraping for top 10 results
    scrape_tasks = []
    for result in results[:10]:
        url = result.get('link', '')
        if url:
            scrape_tasks.append(scrape_with_decodo_async(url, decodo, session))

    # Wait for all scrapes to complete in parallel
    htmls = await asyncio.gather(*scrape_tasks, return_exceptions=True)

    # Parse results
    for html, result in zip(htmls, results[:10]):
        if isinstance(html, str) and html:
            url = result.get('link', '')
            offer = parse_scraped_page(html, url, isbn)
            if offer:
                offers.append(offer)

    return offers

def get_isbns_todo(conn, limit=None) -> List[str]:
    """Get ISBNs that need edition data."""
    cursor = conn.cursor()
    query = """
    SELECT DISTINCT isbn FROM cached_books
    WHERE isbn NOT IN (
        SELECT isbn FROM edition_offers
        GROUP BY isbn
        HAVING SUM(CASE WHEN edition_type='first' THEN 1 ELSE 0 END) > 0
           AND SUM(CASE WHEN edition_type='later' THEN 1 ELSE 0 END) > 0
    )
    ORDER BY isbn
    """
    if limit:
        query += f" LIMIT {limit}"
    cursor.execute(query)
    return [r[0] for r in cursor.fetchall()]

async def process_batch(isbns: List[str], serper_key: str, decodo: DecodoClient) -> List[Offer]:
    """Process a batch of ISBNs concurrently."""
    async with aiohttp.ClientSession() as session:
        tasks = [process_isbn(isbn, serper_key, decodo, session) for isbn in isbns]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten results
        all_offers = []
        for result in results:
            if isinstance(result, list):
                all_offers.extend(result)

        return all_offers

async def main(limit=None):
    """Main collection function with parallel processing."""
    global serper_semaphore, decodo_semaphore

    # Initialize rate limit semaphores
    serper_semaphore = asyncio.Semaphore(SERPER_RATE)
    decodo_semaphore = asyncio.Semaphore(DECODO_RATE)

    # Load API keys
    serper_key = None
    env_path = Path.home() / "ISBN" / ".env"
    for line in open(env_path):
        if line.startswith("X-API-KEY="):
            serper_key = line.split("=", 1)[1].strip()

    if not serper_key:
        logger.error("No Serper key")
        return

    # Init Decodo
    decodo_user = os.getenv("DECODO_CORE_AUTHENTICATION", "U0000319430")
    decodo_pass = os.getenv("DECODO_CORE_PASSWORD", "PW_160bc1b00f0e3fe034ddca35df82923b2")
    decodo = DecodoClient(decodo_user, decodo_pass, rate_limit=DECODO_RATE)

    conn = sqlite3.connect(DB_PATH)
    isbns = get_isbns_todo(conn, limit)

    logger.info(f"Processing {len(isbns)} ISBNs with {CONCURRENCY}x parallelization")
    logger.info(f"Rates: Serper={SERPER_RATE}/s, Decodo={DECODO_RATE}/s")

    if not isbns:
        logger.info("Nothing to do!")
        return

    total_offers = 0
    start = time.time()

    # Process in concurrent batches
    for i in range(0, len(isbns), CONCURRENCY):
        batch = isbns[i:i+CONCURRENCY]
        batch_start = time.time()

        # Process batch concurrently
        offers = await process_batch(batch, serper_key, decodo)

        # Store results
        if offers:
            store_offers(offers, conn)
            total_offers += len(offers)

        batch_time = time.time() - batch_start

        # Progress reporting every BATCH_SIZE ISBNs
        done = i + len(batch)
        if done % BATCH_SIZE == 0 or done == len(isbns):
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            remain = len(isbns) - done
            eta = remain / rate / 60 if rate > 0 else 0

            logger.info(f"Progress: {done}/{len(isbns)} ({100*done/len(isbns):.1f}%)")
            logger.info(f"Rate: {rate:.2f} ISBNs/sec, Batch: {batch_time:.1f}s")
            logger.info(f"Offers: {total_offers}, ETA: {eta:.1f} min")

    conn.close()
    logger.info(f"\n{'='*60}")
    logger.info(f"DONE: {len(isbns)} ISBNs, {total_offers} offers")
    logger.info(f"Time: {(time.time()-start)/60:.1f} min")
    logger.info(f"Avg: {total_offers/len(isbns) if isbns else 0:.1f} offers/ISBN")

if __name__ == "__main__":
    import sys
    limit = None
    if "--test" in sys.argv:
        limit = 20
        logger.info("TEST: 20 ISBNs only")
    elif any(a.startswith("--limit=") for a in sys.argv):
        limit = int([a for a in sys.argv if a.startswith("--limit=")][0].split("=")[1])

    asyncio.run(main(limit))
