"""
Async Serper.dev Google Search API client with concurrent request support.

Provides high-throughput search with proper rate limiting (50 queries/second).
"""

import os
import hashlib
import json
import time
import asyncio
import logging
from typing import List, Dict, Optional
from pathlib import Path
import sqlite3

import aiohttp


logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket rate limiter for controlling request rate."""

    def __init__(self, rate: float, capacity: float):
        """
        Initialize token bucket.

        Args:
            rate: Tokens per second
            capacity: Maximum tokens in bucket
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1):
        """Acquire tokens, waiting if necessary."""
        async with self._lock:
            while True:
                now = time.time()
                elapsed = now - self.last_update

                # Add new tokens based on elapsed time
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # Calculate how long to wait for enough tokens
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.rate
                await asyncio.sleep(wait_time)


class AsyncSerperSearchAPI:
    """Async Serper.dev Google Search API client with high-throughput support."""

    API_URL = "https://google.serper.dev/search"
    RATE_LIMIT = 50  # queries per second
    MAX_CONCURRENT = 50  # maximum concurrent requests
    CACHE_TTL = 7 * 24 * 60 * 60  # 7 days in seconds

    # Platform-specific search patterns
    PLATFORM_QUERIES = {
        'ebay': 'site:ebay.com "{isbn}" (sold OR completed)',
        'abebooks': 'site:abebooks.com "{isbn}" sold',
        'mercari': 'site:mercari.com "{isbn}" sold',
        'amazon': 'site:amazon.com "{isbn}" ("currently unavailable" OR "out of stock")',
    }

    def __init__(self, api_key: Optional[str] = None, cache_db_path: Optional[Path] = None):
        """
        Initialize async Serper API client.

        Args:
            api_key: Serper API key (reads from X-API-KEY env var if not provided)
            cache_db_path: Path to SQLite cache database
        """
        self.api_key = api_key or os.getenv('X-API-KEY')
        if not self.api_key:
            raise ValueError("Serper API key required (X-API-KEY environment variable)")

        self.cache_db_path = cache_db_path or Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

        # Rate limiting with token bucket (50 tokens/sec, capacity 50)
        self.rate_limiter = TokenBucket(rate=self.RATE_LIMIT, capacity=self.RATE_LIMIT)

        # Semaphore to limit concurrent requests
        self.semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)

        # Session will be created when needed
        self.session: Optional[aiohttp.ClientSession] = None

        # Usage tracking
        self._searches_this_session = 0

    def _init_cache_db(self):
        """Initialize search cache table in database (sync operation)."""
        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash TEXT UNIQUE NOT NULL,
                query TEXT NOT NULL,
                platform TEXT NOT NULL,
                isbn TEXT NOT NULL,
                response_json TEXT NOT NULL,
                result_count INTEGER,
                timestamp INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_cache_hash
            ON search_cache(query_hash)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_cache_isbn
            ON search_cache(isbn, platform)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS serper_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                searches_used INTEGER NOT NULL,
                platform TEXT,
                timestamp INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_serper_usage_date
            ON serper_usage(date)
        """)

        conn.commit()
        conn.close()

    async def __aenter__(self):
        """Async context manager entry."""
        self._init_cache_db()
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    def _get_query_hash(self, query: str) -> str:
        """Generate hash for cache key."""
        return hashlib.md5(query.encode()).hexdigest()

    def _get_cached_results(self, query_hash: str) -> Optional[List[Dict]]:
        """Check cache for existing results (sync operation)."""
        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        current_time = int(time.time())

        cursor.execute("""
            SELECT response_json FROM search_cache
            WHERE query_hash = ? AND expires_at > ?
        """, (query_hash, current_time))

        row = cursor.fetchone()
        conn.close()

        if row:
            response_json = row[0]
            logger.debug(f"Cache HIT for query hash {query_hash[:8]}...")
            return json.loads(response_json)

        logger.debug(f"Cache MISS for query hash {query_hash[:8]}...")
        return None

    def _cache_results(self, query_hash: str, query: str, platform: str, isbn: str, results: List[Dict]):
        """Cache search results (sync operation)."""
        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        current_time = int(time.time())
        expires_at = current_time + self.CACHE_TTL

        cursor.execute("""
            INSERT OR REPLACE INTO search_cache
            (query_hash, query, platform, isbn, response_json, result_count, timestamp, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            query_hash,
            query,
            platform,
            isbn,
            json.dumps(results),
            len(results),
            current_time,
            expires_at
        ))

        conn.commit()
        conn.close()
        logger.debug(f"Cached {len(results)} results for query hash {query_hash[:8]}...")

    def _track_usage(self, platform: str):
        """Track API usage for budget monitoring (sync operation)."""
        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        date_str = time.strftime('%Y-%m-%d')
        timestamp = int(time.time())

        cursor.execute("""
            INSERT INTO serper_usage (date, searches_used, platform, timestamp)
            VALUES (?, 1, ?, ?)
        """, (date_str, platform, timestamp))

        conn.commit()
        conn.close()

        self._searches_this_session += 1

    async def search(
        self,
        isbn: str,
        platform: str,
        num_results: int = 10,
        use_cache: bool = True
    ) -> List[Dict[str, str]]:
        """
        Search for sold listings on a specific platform (async).

        Args:
            isbn: ISBN to search for
            platform: Platform name ('ebay', 'abebooks', 'mercari', 'amazon')
            num_results: Number of results to return (max 100)
            use_cache: Whether to use cached results

        Returns:
            List of search results with url, title, snippet, position
        """
        if platform not in self.PLATFORM_QUERIES:
            raise ValueError(f"Unknown platform: {platform}. Must be one of: {list(self.PLATFORM_QUERIES.keys())}")

        # Build query
        query_template = self.PLATFORM_QUERIES[platform]
        query = query_template.format(isbn=isbn)
        query_hash = self._get_query_hash(query)

        # Check cache (sync operation)
        if use_cache:
            cached_results = self._get_cached_results(query_hash)
            if cached_results is not None:
                logger.info(f"  Using cached results for {platform}")
                return cached_results[:num_results]

        # Acquire rate limit token and semaphore slot
        async with self.semaphore:
            await self.rate_limiter.acquire(1)

            # Make API request
            headers = {
                'X-API-KEY': self.api_key,
                'Content-Type': 'application/json'
            }

            payload = {
                'q': query,
                'num': num_results,
                'gl': 'us',
                'hl': 'en'
            }

            logger.info(f"Searching {platform} for ISBN {isbn}")

            try:
                async with self.session.post(self.API_URL, json=payload, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Serper API error: {response.status}")
                        return []

                    data = await response.json()

                    # Extract organic results
                    organic_results = data.get('organic', [])

                    results = []
                    for idx, result in enumerate(organic_results[:num_results], 1):
                        results.append({
                            'url': result.get('link', ''),
                            'title': result.get('title', ''),
                            'snippet': result.get('snippet', ''),
                            'position': idx
                        })

                    logger.info(f"Found {len(results)} results for {isbn} on {platform}")

                    # Cache results (sync operation)
                    if results:
                        self._cache_results(query_hash, query, platform, isbn, results)

                    # Track usage (sync operation)
                    self._track_usage(platform)

                    return results

            except Exception as e:
                logger.error(f"Error searching {platform} for {isbn}: {e}")
                return []

    async def search_multiple_platforms(
        self,
        isbn: str,
        platforms: List[str] = None,
        num_results: int = 5,
        use_cache: bool = True
    ) -> Dict[str, List[Dict]]:
        """
        Search multiple platforms concurrently.

        Args:
            isbn: ISBN to search for
            platforms: List of platforms (default: all)
            num_results: Results per platform
            use_cache: Whether to use cached results

        Returns:
            Dict mapping platform to list of results
        """
        if platforms is None:
            platforms = list(self.PLATFORM_QUERIES.keys())

        # Create concurrent tasks for all platforms
        tasks = [
            self.search(isbn, platform, num_results, use_cache)
            for platform in platforms
        ]

        # Execute all searches concurrently
        results_list = await asyncio.gather(*tasks)

        # Map results back to platforms
        results = {
            platform: results_list[i]
            for i, platform in enumerate(platforms)
        }

        total_found = sum(len(r) for r in results.values())
        logger.info(f"Total results for {isbn} across {len(platforms)} platforms: {total_found}")

        return results
