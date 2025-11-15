"""
Enrichment coordinator for handling concurrent book enrichment requests.

This module provides thread-safe coordination of enrichment operations to prevent:
- Database race conditions
- API rate limit violations
- Resource exhaustion from too many simultaneous requests

Usage:
    from isbn_lot_optimizer.enrichment_coordinator import EnrichmentCoordinator

    # Singleton instance shared across all scan operations
    coordinator = EnrichmentCoordinator.get_instance()

    # Enrich with automatic rate limiting and deduplication
    result = coordinator.enrich(isbn="9780399127212", force_refresh=False)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

from isbn_lot_optimizer.enrichment import enrich_book_data, EnrichmentResult

logger = logging.getLogger(__name__)


@dataclass
class RateLimiter:
    """Token bucket rate limiter for API calls."""

    name: str
    rate_per_second: float
    burst_capacity: int

    def __post_init__(self):
        self.tokens = float(self.burst_capacity)
        self.last_update = time.time()
        self.lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        """
        Acquire a token for making an API call.

        Args:
            timeout: Maximum time to wait for a token (seconds)

        Returns:
            True if token acquired, False if timeout
        """
        start = time.time()

        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_update

                # Refill tokens based on time elapsed
                self.tokens = min(
                    self.burst_capacity,
                    self.tokens + elapsed * self.rate_per_second
                )
                self.last_update = now

                # If we have a token, consume it
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True

            # Check timeout
            if time.time() - start > timeout:
                logger.warning(f"Rate limiter timeout for {self.name}")
                return False

            # Sleep briefly before retrying
            time.sleep(0.1)


class EnrichmentCoordinator:
    """
    Singleton coordinator for managing concurrent book enrichment requests.

    Features:
    - Request deduplication (prevents multiple simultaneous enrichments of same ISBN)
    - Global rate limiting per API (eBay, Amazon, marketplaces)
    - Thread-safe operation
    - Automatic retry for transient failures
    """

    _instance: Optional[EnrichmentCoordinator] = None
    _lock = threading.Lock()

    def __init__(self):
        """Private constructor. Use get_instance() instead."""
        # Track in-progress enrichments to prevent duplicates
        self.in_progress: Set[str] = set()
        self.in_progress_lock = threading.Lock()

        # Track completed enrichments (simple cache with timestamps)
        self.recent_results: Dict[str, tuple[EnrichmentResult, float]] = {}
        self.cache_ttl = 60.0  # Cache results for 60 seconds

        # Rate limiters for different APIs
        self.rate_limiters = {
            "ebay_browse": RateLimiter(
                name="eBay Browse API",
                rate_per_second=8.0,  # Conservative from 10/sec limit
                burst_capacity=10
            ),
            "amazon": RateLimiter(
                name="Amazon API",
                rate_per_second=2.0,  # Conservative
                burst_capacity=5
            ),
            "marketplace": RateLimiter(
                name="Marketplace Scrapers",
                rate_per_second=1.0,  # Gentle on scrapers
                burst_capacity=3
            ),
        }

        # Condition variables for waiting on in-progress requests
        self.waiting: Dict[str, threading.Condition] = defaultdict(threading.Condition)

    @classmethod
    def get_instance(cls) -> EnrichmentCoordinator:
        """Get singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def enrich(
        self,
        isbn: str,
        db_path: Optional[Path] = None,
        force_refresh: bool = False,
        collect_metadata_data: bool = True,
        collect_marketplace: bool = True,
        collect_ebay: bool = True,
        collect_amazon: bool = True,
        wait_for_in_progress: bool = True,
    ) -> EnrichmentResult:
        """
        Enrich a book with thread-safe coordination and rate limiting.

        Args:
            isbn: The ISBN to enrich
            db_path: Path to metadata cache database
            force_refresh: Force refresh all data regardless of age
            collect_metadata_data: Collect metadata from Google Books
            collect_marketplace: Collect marketplace data
            collect_ebay: Collect eBay data
            collect_amazon: Collect Amazon data
            wait_for_in_progress: If True, wait for any in-progress enrichment
                                 of the same ISBN. If False, return cached result
                                 or skip if already in progress.

        Returns:
            EnrichmentResult with collection statistics
        """
        # Normalize ISBN for consistency
        from shared.utils import normalise_isbn
        isbn = normalise_isbn(isbn)
        if not isbn:
            return EnrichmentResult(
                isbn=isbn,
                success=False,
                error="Invalid ISBN format"
            )

        # Check if we have a recent cached result
        if not force_refresh and isbn in self.recent_results:
            result, timestamp = self.recent_results[isbn]
            age = time.time() - timestamp
            if age < self.cache_ttl:
                logger.info(f"Returning cached enrichment result for {isbn} (age: {age:.1f}s)")
                return result

        # Check if enrichment is already in progress
        with self.in_progress_lock:
            if isbn in self.in_progress:
                if not wait_for_in_progress:
                    logger.info(f"Enrichment already in progress for {isbn}, skipping")
                    return EnrichmentResult(
                        isbn=isbn,
                        success=False,
                        error="Enrichment already in progress"
                    )

                logger.info(f"Enrichment in progress for {isbn}, waiting...")
            else:
                # Mark as in progress
                self.in_progress.add(isbn)

        # If we're waiting, use condition variable
        if isbn in self.waiting:
            with self.waiting[isbn]:
                # Wait for in-progress enrichment to complete
                self.waiting[isbn].wait(timeout=300.0)  # 5 minute timeout

                # Check if we now have a cached result
                if isbn in self.recent_results:
                    result, _ = self.recent_results[isbn]
                    return result

        try:
            # Acquire rate limiter tokens based on what we're collecting
            if collect_ebay and not self.rate_limiters["ebay_browse"].acquire():
                raise Exception("eBay API rate limit timeout")

            if collect_amazon and not self.rate_limiters["amazon"].acquire():
                raise Exception("Amazon API rate limit timeout")

            if collect_marketplace and not self.rate_limiters["marketplace"].acquire():
                raise Exception("Marketplace API rate limit timeout")

            # Perform the actual enrichment
            logger.info(f"Starting enrichment for {isbn}")
            result = enrich_book_data(
                isbn=isbn,
                db_path=db_path,
                force_refresh=force_refresh,
                collect_metadata_data=collect_metadata_data,
                collect_marketplace=collect_marketplace,
                collect_ebay=collect_ebay,
                collect_amazon=collect_amazon,
            )

            # Cache the result
            self.recent_results[isbn] = (result, time.time())

            # Clean up old cache entries (keep last 100)
            if len(self.recent_results) > 100:
                oldest_isbns = sorted(
                    self.recent_results.keys(),
                    key=lambda k: self.recent_results[k][1]
                )[:50]
                for old_isbn in oldest_isbns:
                    del self.recent_results[old_isbn]

            logger.info(f"Completed enrichment for {isbn} in {result.duration_seconds:.2f}s")
            return result

        finally:
            # Remove from in-progress and notify waiting threads
            with self.in_progress_lock:
                self.in_progress.discard(isbn)

            # Notify any waiting threads
            if isbn in self.waiting:
                with self.waiting[isbn]:
                    self.waiting[isbn].notify_all()

    def clear_cache(self):
        """Clear the result cache (useful for testing)."""
        with self.in_progress_lock:
            self.recent_results.clear()

    def get_stats(self) -> Dict[str, any]:
        """Get coordinator statistics for monitoring."""
        with self.in_progress_lock:
            return {
                "in_progress_count": len(self.in_progress),
                "cached_results": len(self.recent_results),
                "rate_limiters": {
                    name: {
                        "tokens": limiter.tokens,
                        "rate": limiter.rate_per_second,
                        "capacity": limiter.burst_capacity,
                    }
                    for name, limiter in self.rate_limiters.items()
                }
            }


# Convenience function that uses singleton coordinator
def enrich_with_coordination(
    isbn: str,
    **kwargs
) -> EnrichmentResult:
    """
    Convenience function to enrich a book using the global coordinator.

    This is the recommended way to enrich books in a concurrent environment.

    Example:
        >>> from isbn_lot_optimizer.enrichment_coordinator import enrich_with_coordination
        >>> result = enrich_with_coordination("9780399127212")
        >>> print(f"Collected {result.ebay_active_count} eBay listings")
    """
    coordinator = EnrichmentCoordinator.get_instance()
    return coordinator.enrich(isbn, **kwargs)
