"""
Complete Serper + Decodo edition data collector.
Ready for production with 790K Decodo credits.
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

# Config
DB_PATH = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"
SERPER_RATE = 3  # req/sec
DECODO_RATE = 25  # req/sec
BATCH_SIZE = 50

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

async def search_serper(isbn: str, key: str, session) -> List[Dict]:
    try:
        async with session.post(
            "https://google.serper.dev/search",
            json={"q": f'{isbn} "first edition" OR "1st edition" site:ebay.com OR site:abebooks.com OR site:amazon.com', "num": 20},
            headers={"X-API-KEY": key, "Content-Type": "application/json"}
        ) as r:
            if r.status == 200:
                data = await r.json()
                return data.get("organic", [])
    except Exception as e:
        logger.error(f"Serper error {isbn}: {e}")
    return []

def scrape_with_decodo(url: str, decodo: DecodoClient) -> Optional[str]:
    """Scrape page HTML with Decodo."""
    try:
        response = decodo.scrape_url(url)
        if response.status_code == 200:
            return response.body
    except Exception as e:
        logger.debug(f"Decodo error {url}: {e}")
    return None

def parse_scraped_page(html: str, url: str, isbn: str) -> Optional[Offer]:
    """Parse scraped HTML for price and edition info."""
    # Extract price from HTML
    price = extract_price(html)
    if not price:
        return None
    
    # Classify edition from full page content
    edition_type, confidence, text = Classifier.classify(html)
    marketplace = detect_marketplace(url)
    
    # Extract title (simple heuristic)
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
        title=title[:200]  # Limit length
    )

def store_offers(offers: List[Offer], conn):
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
    """Process one ISBN: Serper search + Decodo scraping."""
    offers = []
    
    # Phase 1: Serper search
    results = await search_serper(isbn, serper_key, session)
    await asyncio.sleep(1.0 / SERPER_RATE)
    
    if not results:
        return offers
    
    # Phase 2: Decodo scraping for results
    for result in results[:10]:  # Limit to top 10
        url = result.get('link', '')
        if not url:
            continue
        
        # Scrape page
        html = scrape_with_decodo(url, decodo)
        if html:
            offer = parse_scraped_page(html, url, isbn)
            if offer:
                offers.append(offer)
        
        # Rate limit
        time.sleep(1.0 / DECODO_RATE)
    
    return offers

def get_isbns_todo(conn, limit=None) -> List[str]:
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

async def main(limit=None):
    # Load keys
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
    
    logger.info(f"Processing {len(isbns)} ISBNs")
    
    if not isbns:
        logger.info("Nothing to do!")
        return
    
    total_offers = 0
    start = time.time()
    decodo_calls = 0
    
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(isbns), BATCH_SIZE):
            batch = isbns[i:i+BATCH_SIZE]
            logger.info(f"\nBatch {i//BATCH_SIZE + 1}/{(len(isbns)+BATCH_SIZE-1)//BATCH_SIZE}")
            
            for isbn in batch:
                offers = await process_isbn(isbn, serper_key, decodo, session)
                
                if offers:
                    store_offers(offers, conn)
                    total_offers += len(offers)
                    decodo_calls += len(offers)
                    logger.info(f"{isbn}: {len(offers)} offers (total: {total_offers})")
            
            # Progress
            done = i + len(batch)
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            remain = len(isbns) - done
            eta = remain / rate / 60 if rate > 0 else 0
            
            logger.info(f"Progress: {done}/{len(isbns)} ({100*done/len(isbns):.1f}%)")
            logger.info(f"Rate: {rate:.2f} ISBNs/sec, ETA: {eta:.1f} min")
            logger.info(f"Decodo calls: {decodo_calls}")
    
    conn.close()
    logger.info(f"\n{'='*60}")
    logger.info(f"DONE: {len(isbns)} ISBNs, {total_offers} offers")
    logger.info(f"Time: {(time.time()-start)/60:.1f} min")
    logger.info(f"Decodo credits used: ~{decodo_calls}")

if __name__ == "__main__":
    import sys
    limit = None
    if "--test" in sys.argv:
        limit = 5
        logger.info("TEST: 5 ISBNs only")
    elif any(a.startswith("--limit=") for a in sys.argv):
        limit = int([a for a in sys.argv if a.startswith("--limit=")][0].split("=")[1])
    
    asyncio.run(main(limit))
