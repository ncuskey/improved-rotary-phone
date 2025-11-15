"""
Scalable edition data collection using Serper + Decodo.

Collects marketplace pricing for first editions vs later editions
for ML model training.

Features:
- Serper for initial discovery (cheap)
- Decodo for full page scraping (when needed)
- Smart caching and resume capability
- Rate limiting and progress tracking
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
from shared.decodo import DecodoClient


# Configuration
DB_PATH = Path.home() / ".isbn_lot_optimizer" / "catalog.db"
SERPER_RATE_LIMIT = 3  # Requests per second
DECODO_RATE_LIMIT = 25  # Requests per second (conservative)
BATCH_SIZE = 100  # Process ISBNs in batches
RESULTS_PER_ISBN = 20  # Max search results per ISBN

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class EditionOffer:
    """Represents a single marketplace offer for a book."""
    isbn: str
    marketplace: str
    seller: Optional[str]
    price: float
    condition: Optional[str]
    edition_type: str  # 'first', 'later', 'unknown'
    edition_confidence: float
    edition_text: str
    listing_url: str
    source_type: str  # 'serper_snippet' or 'decodo_scrape'
    title: Optional[str] = None
    description: Optional[str] = None


class EditionClassifier:
    """Classifies edition type from text."""

    FIRST_EDITION_PATTERNS = [
        (r'\b1st\s+edition\b', 0.9),
        (r'\bfirst\s+edition\b', 0.9),
        (r'\b1st\s+ed\.?\b', 0.8),
        (r'\bfirst\s+ed\.?\b', 0.8),
        (r'\b1/1\b', 0.7),  # Publisher notation
        (r'\bfirst\s+printing\b', 0.85),
        (r'\b1st\s+printing\b', 0.85),
    ]

    LATER_EDITION_PATTERNS = [
        (r'\blater\s+printing\b', 0.9),
        (r'\breprint\b', 0.85),
        (r'\b\d+(?:nd|rd|th)\s+edition\b', 0.95),
        (r'\b\d+(?:nd|rd|th)\s+printing\b', 0.9),
        (r'\bbook\s+club\s+edition\b', 0.8),
    ]

    @classmethod
    def classify(cls, text: str) -> Tuple[str, float, str]:
        """
        Classify edition type from text.

        Returns: (edition_type, confidence, matched_text)
        """
        text_lower = text.lower()

        # Check for first edition
        for pattern, confidence in cls.FIRST_EDITION_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                return ('first', confidence, match.group())

        # Check for later edition
        for pattern, confidence in cls.LATER_EDITION_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                return ('later', confidence, match.group())

        return ('unknown', 0.0, '')


class PriceExtractor:
    """Extracts prices from text."""

    PRICE_PATTERN = r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)'

    @classmethod
    def extract(cls, text: str) -> Optional[float]:
        """Extract first price from text."""
        matches = re.findall(cls.PRICE_PATTERN, text)
        if matches:
            try:
                price_str = matches[0].replace(',', '')
                return float(price_str)
            except ValueError:
                return None
        return None


class MarketplaceDetector:
    """Detects marketplace from URL."""

    MARKETPLACES = {
        'ebay.com': 'ebay',
        'abebooks.com': 'abebooks',
        'amazon.com': 'amazon',
        'alibris.com': 'alibris',
        'biblio.com': 'biblio',
    }

    @classmethod
    def detect(cls, url: str) -> str:
        """Detect marketplace from URL."""
        url_lower = url.lower()
        for domain, marketplace in cls.MARKETPLACES.items():
            if domain in url_lower:
                return marketplace
        return 'other'


async def search_serper(isbn: str, api_key: str, session: aiohttp.ClientSession) -> List[Dict]:
    """Search Google via Serper for marketplace listings."""
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }

    # Target edition-focused listings
    query = f'{isbn} "first edition" OR "1st edition" OR "later printing" site:ebay.com OR site:abebooks.com OR site:amazon.com'

    payload = {
        "q": query,
        "num": RESULTS_PER_ISBN,
    }

    try:
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status != 200:
                logger.error(f"Serper error for {isbn}: {response.status}")
                return []

            data = await response.json()
            return data.get("organic", [])

    except Exception as e:
        logger.error(f"Serper exception for {isbn}: {e}")
        return []


def parse_serper_result(isbn: str, result: Dict) -> Optional[EditionOffer]:
    """Parse a Serper search result into an EditionOffer."""
    title = result.get("title", "")
    snippet = result.get("snippet", "")
    link = result.get("link", "")

    if not link:
        return None

    # Extract price
    combined_text = f"{title} {snippet}"
    price = PriceExtractor.extract(combined_text)

    # Classify edition
    edition_type, confidence, edition_text = EditionClassifier.classify(combined_text)

    # Detect marketplace
    marketplace = MarketplaceDetector.detect(link)

    # We need at least a price to be useful
    if not price:
        return None

    return EditionOffer(
        isbn=isbn,
        marketplace=marketplace,
        seller=None,
        price=price,
        condition=None,
        edition_type=edition_type,
        edition_confidence=confidence,
        edition_text=edition_text,
        listing_url=link,
        source_type='serper_snippet',
        title=title,
        description=snippet
    )


def store_offers(offers: List[EditionOffer], conn: sqlite3.Connection):
    """Store offers in database."""
    cursor = conn.cursor()

    for offer in offers:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO edition_offers
                (isbn, marketplace, seller, price, condition, edition_type,
                 edition_confidence, edition_text, listing_url, source_type,
                 title, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                offer.isbn, offer.marketplace, offer.seller, offer.price,
                offer.condition, offer.edition_type, offer.edition_confidence,
                offer.edition_text, offer.listing_url, offer.source_type,
                offer.title, offer.description
            ))
        except sqlite3.IntegrityError:
            # Already exists
            pass

    conn.commit()


async def process_isbn_batch(
    isbns: List[str],
    api_key: str,
    session: aiohttp.ClientSession
) -> List[EditionOffer]:
    """Process a batch of ISBNs using Serper."""
    all_offers = []

    for isbn in isbns:
        # Search via Serper
        results = await search_serper(isbn, api_key, session)

        # Parse results
        for result in results:
            offer = parse_serper_result(isbn, result)
            if offer:
                all_offers.append(offer)

        # Rate limiting
        await asyncio.sleep(1.0 / SERPER_RATE_LIMIT)

        if len(results) > 0:
            logger.info(f"{isbn}: Found {len(results)} results")

    return all_offers


def get_isbns_to_process(conn: sqlite3.Connection, limit: Optional[int] = None) -> List[str]:
    """Get ISBNs that need edition data collection."""
    cursor = conn.cursor()

    # Get ISBNs that either:
    # 1. Have no edition_offers yet
    # 2. Have offers but don't have both first and later editions

    query = """
    SELECT DISTINCT isbn FROM books
    WHERE isbn NOT IN (
        SELECT isbn FROM edition_offers
        GROUP BY isbn
        HAVING
            SUM(CASE WHEN edition_type = 'first' THEN 1 ELSE 0 END) > 0
            AND SUM(CASE WHEN edition_type = 'later' THEN 1 ELSE 0 END) > 0
    )
    ORDER BY isbn
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    return [row[0] for row in cursor.fetchall()]


async def main(limit: Optional[int] = None):
    """Main collection function."""

    # Load API key
    api_key = os.getenv("X-API-KEY")
    if not api_key:
        env_path = Path.home() / "ISBN" / ".env"
        with open(env_path) as f:
            for line in f:
                if line.startswith("X-API-KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        logger.error("No Serper API key found")
        return

    # Connect to database
    conn = sqlite3.connect(DB_PATH)

    # Get ISBNs to process
    isbns = get_isbns_to_process(conn, limit)
    logger.info(f"Found {len(isbns)} ISBNs to process")

    if not isbns:
        logger.info("No ISBNs need processing!")
        return

    # Process in batches
    total_offers = 0
    start_time = time.time()

    async with aiohttp.ClientSession() as session:
        for i in range(0, len(isbns), BATCH_SIZE):
            batch = isbns[i:i+BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(isbns) + BATCH_SIZE - 1) // BATCH_SIZE

            logger.info(f"\nProcessing batch {batch_num}/{total_batches} ({len(batch)} ISBNs)")

            # Process batch
            offers = await process_isbn_batch(batch, api_key, session)

            # Store results
            if offers:
                store_offers(offers, conn)
                total_offers += len(offers)
                logger.info(f"Stored {len(offers)} offers (total: {total_offers})")

            # Progress stats
            elapsed = time.time() - start_time
            processed = i + len(batch)
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = len(isbns) - processed
            eta_seconds = remaining / rate if rate > 0 else 0
            eta_minutes = eta_seconds / 60

            logger.info(f"Progress: {processed}/{len(isbns)} ISBNs ({processed/len(isbns)*100:.1f}%)")
            logger.info(f"Rate: {rate:.1f} ISBNs/sec, ETA: {eta_minutes:.1f} minutes")

    conn.close()

    # Final summary
    logger.info("\n" + "="*60)
    logger.info("COLLECTION COMPLETE")
    logger.info("="*60)
    logger.info(f"Total ISBNs processed: {len(isbns)}")
    logger.info(f"Total offers collected: {total_offers}")
    logger.info(f"Avg offers per ISBN: {total_offers/len(isbns) if isbns else 0:.1f}")
    logger.info(f"Total time: {(time.time() - start_time) / 60:.1f} minutes")


if __name__ == "__main__":
    import sys

    limit = None
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        limit = 10
        logger.info("TEST MODE: Processing only 10 ISBNs")
    elif len(sys.argv) > 1 and sys.argv[1].startswith("--limit="):
        limit = int(sys.argv[1].split("=")[1])
        logger.info(f"Processing {limit} ISBNs")

    asyncio.run(main(limit))
