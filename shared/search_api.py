"""
Serper.dev Google Search API client for discovering sold listings.

Provides unified interface for searching multiple platforms (eBay, AbeBooks,
Mercari, Amazon) to find sold/completed book listings.

Cost: $50 for 50,000 searches (valid 6 months)
Rate limit: 50 queries/second
"""

import os
import hashlib
import json
import time
import logging
from typing import List, Dict, Optional
from pathlib import Path
import sqlite3

import requests


logger = logging.getLogger(__name__)


class SerperSearchAPI:
    """Serper.dev Google Search API client with caching and rate limiting."""

    API_URL = "https://google.serper.dev/search"
    RATE_LIMIT = 50  # queries per second
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
        Initialize Serper API client.

        Args:
            api_key: Serper API key (reads from X-API-KEY env var if not provided)
            cache_db_path: Path to SQLite cache database
        """
        self.api_key = api_key or os.getenv('X-API-KEY')
        if not self.api_key:
            raise ValueError("Serper API key required (X-API-KEY environment variable)")

        self.cache_db_path = cache_db_path or Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
        self._init_cache_db()

        # Rate limiting
        self._last_request_time = 0
        self._min_request_interval = 1.0 / self.RATE_LIMIT

        # Usage tracking
        self._searches_this_session = 0

    def _init_cache_db(self):
        """Initialize search cache table in database."""
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

        # Usage tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS serper_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                searches_used INTEGER NOT NULL,
                platform TEXT,
                timestamp INTEGER NOT NULL
            )
        """)

        conn.commit()
        conn.close()
        logger.debug(f"Search cache initialized at {self.cache_db_path}")

    def _get_query_hash(self, query: str) -> str:
        """Generate hash for cache key."""
        return hashlib.sha256(query.encode()).hexdigest()

    def _get_cached_results(self, query_hash: str) -> Optional[List[Dict]]:
        """Retrieve cached search results if not expired."""
        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        current_time = int(time.time())

        cursor.execute("""
            SELECT response_json, expires_at
            FROM search_cache
            WHERE query_hash = ? AND expires_at > ?
        """, (query_hash, current_time))

        row = cursor.fetchone()
        conn.close()

        if row:
            logger.debug(f"Cache HIT for query hash {query_hash[:8]}...")
            response_json, expires_at = row
            return json.loads(response_json)

        logger.debug(f"Cache MISS for query hash {query_hash[:8]}...")
        return None

    def _cache_results(
        self,
        query_hash: str,
        query: str,
        platform: str,
        isbn: str,
        results: List[Dict]
    ):
        """Cache search results."""
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
        """Track API usage for budget monitoring."""
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

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time

        if time_since_last_request < self._min_request_interval:
            sleep_time = self._min_request_interval - time_since_last_request
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    def search(
        self,
        isbn: str,
        platform: str,
        num_results: int = 10,
        use_cache: bool = True
    ) -> List[Dict[str, str]]:
        """
        Search for sold listings on a specific platform.

        Args:
            isbn: ISBN to search for
            platform: Platform name ('ebay', 'abebooks', 'mercari', 'amazon')
            num_results: Number of results to return (max 100)
            use_cache: Whether to use cached results

        Returns:
            List of search results:
            [
                {
                    'url': 'https://...',
                    'title': '...',
                    'snippet': '...',
                    'position': 1
                },
                ...
            ]
        """
        if platform not in self.PLATFORM_QUERIES:
            raise ValueError(f"Unknown platform: {platform}. Must be one of: {list(self.PLATFORM_QUERIES.keys())}")

        # Build query
        query_template = self.PLATFORM_QUERIES[platform]
        query = query_template.format(isbn=isbn)
        query_hash = self._get_query_hash(query)

        # Check cache
        if use_cache:
            cached_results = self._get_cached_results(query_hash)
            if cached_results is not None:
                return cached_results

        # Rate limiting
        self._rate_limit()

        # Make API request
        logger.info(f"Searching {platform} for ISBN {isbn}")
        logger.debug(f"Query: {query}")

        try:
            response = requests.post(
                self.API_URL,
                headers={
                    'X-API-KEY': self.api_key,
                    'Content-Type': 'application/json'
                },
                json={
                    'q': query,
                    'num': num_results
                },
                timeout=30
            )

            response.raise_for_status()
            data = response.json()

            # Track usage
            self._track_usage(platform)

            # Parse results
            results = []
            for idx, result in enumerate(data.get('organic', [])[:num_results], 1):
                results.append({
                    'url': result.get('link', ''),
                    'title': result.get('title', ''),
                    'snippet': result.get('snippet', ''),
                    'position': idx
                })

            logger.info(f"Found {len(results)} results for {isbn} on {platform}")

            # Cache results
            if use_cache:
                self._cache_results(query_hash, query, platform, isbn, results)

            return results

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.error("Rate limit exceeded (429). Try again later.")
                raise
            elif e.response.status_code == 401:
                logger.error("Invalid API key (401)")
                raise ValueError("Invalid Serper API key")
            else:
                logger.error(f"HTTP error: {e}")
                raise

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

    def search_multiple_platforms(
        self,
        isbn: str,
        platforms: List[str] = None,
        num_results: int = 10,
        use_cache: bool = True
    ) -> Dict[str, List[Dict]]:
        """
        Search multiple platforms for an ISBN.

        Args:
            isbn: ISBN to search for
            platforms: List of platform names (None = all platforms)
            num_results: Number of results per platform
            use_cache: Whether to use cached results

        Returns:
            Dict mapping platform names to result lists:
            {
                'ebay': [{...}, {...}],
                'abebooks': [{...}, {...}],
                ...
            }
        """
        if platforms is None:
            platforms = list(self.PLATFORM_QUERIES.keys())

        results = {}
        for platform in platforms:
            try:
                results[platform] = self.search(isbn, platform, num_results, use_cache)
            except Exception as e:
                logger.error(f"Failed to search {platform} for {isbn}: {e}")
                results[platform] = []

        total_results = sum(len(r) for r in results.values())
        logger.info(f"Total results for {isbn} across {len(platforms)} platforms: {total_results}")

        return results

    def get_usage_stats(self, days_back: int = 30) -> Dict:
        """
        Get API usage statistics.

        Args:
            days_back: Number of days to look back

        Returns:
            {
                'total_searches': 1234,
                'by_platform': {'ebay': 500, 'abebooks': 300, ...},
                'by_date': {'2024-11-01': 50, '2024-11-02': 45, ...},
                'session_searches': 10
            }
        """
        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        cutoff_timestamp = int(time.time()) - (days_back * 24 * 60 * 60)

        # Total searches
        cursor.execute("""
            SELECT COUNT(*) FROM serper_usage
            WHERE timestamp > ?
        """, (cutoff_timestamp,))
        total_searches = cursor.fetchone()[0]

        # By platform
        cursor.execute("""
            SELECT platform, COUNT(*)
            FROM serper_usage
            WHERE timestamp > ?
            GROUP BY platform
        """, (cutoff_timestamp,))
        by_platform = dict(cursor.fetchall())

        # By date
        cursor.execute("""
            SELECT date, SUM(searches_used)
            FROM serper_usage
            WHERE timestamp > ?
            GROUP BY date
            ORDER BY date DESC
        """, (cutoff_timestamp,))
        by_date = dict(cursor.fetchall())

        conn.close()

        return {
            'total_searches': total_searches,
            'by_platform': by_platform,
            'by_date': by_date,
            'session_searches': self._searches_this_session,
            'estimated_remaining_credits': 50000 - total_searches  # Assumes $50 purchase
        }

    def clear_cache(self, older_than_days: Optional[int] = None):
        """
        Clear search cache.

        Args:
            older_than_days: Only clear entries older than N days (None = clear all)
        """
        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        if older_than_days is not None:
            cutoff_timestamp = int(time.time()) - (older_than_days * 24 * 60 * 60)
            cursor.execute("DELETE FROM search_cache WHERE timestamp < ?", (cutoff_timestamp,))
            deleted = cursor.rowcount
            logger.info(f"Cleared {deleted} cache entries older than {older_than_days} days")
        else:
            cursor.execute("DELETE FROM search_cache")
            deleted = cursor.rowcount
            logger.info(f"Cleared all {deleted} cache entries")

        conn.commit()
        conn.close()
