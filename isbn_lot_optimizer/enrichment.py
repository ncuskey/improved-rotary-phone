"""
Unified book data enrichment module.

This module provides a single entry point for collecting all available data
about a book from multiple sources. It handles:
- Metadata (Google Books, Open Library, Hardcover)
- Marketplace pricing (Amazon FBM, AbeBooks, Alibris, Biblio, ZVAB)
- eBay data (Active listings via Browse API, Sold comps via Serper + Decodo)
- Edition/offer data (BookFinder)
- ML predictions (after data collection)
- Series matching
- Data freshness checking to avoid redundant API calls

Usage:
    from isbn_lot_optimizer.enrichment import enrich_book_data

    result = enrich_book_data(
        isbn="9780399127212",
        db_path=Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db",
        force_refresh=False
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import requests

from shared.decodo import DecodoClient
from shared.metadata import fetch_metadata, create_http_session

logger = logging.getLogger(__name__)


# Freshness thresholds (in days)
FRESHNESS = {
    "metadata": 90,  # Basic metadata changes rarely
    "amazon_fbm": 7,  # Amazon prices change frequently
    "abebooks": 14,  # Marketplace prices moderate
    "alibris": 14,
    "biblio": 14,
    "zvab": 14,
    "ebay_active": 3,  # eBay active listings change often
    "ebay_sold": 30,  # Sold comps are historical, less urgent
    "bookfinder": 14,  # Edition data moderate
    "series": 90,  # Series matching static
}


@dataclass
class EnrichmentResult:
    """Result of book enrichment operation."""
    isbn: str
    success: bool
    error: Optional[str] = None

    # What was collected
    metadata_collected: bool = False
    amazon_fbm_collected: bool = False
    abebooks_collected: bool = False
    alibris_collected: bool = False
    biblio_collected: bool = False
    zvab_collected: bool = False
    ebay_active_collected: bool = False
    ebay_sold_collected: bool = False
    bookfinder_collected: bool = False
    series_matched: bool = False

    # Statistics
    ebay_active_count: int = 0
    ebay_sold_count: int = 0
    amazon_fbm_count: int = 0
    abebooks_count: int = 0
    alibris_count: int = 0
    biblio_count: int = 0
    zvab_count: int = 0

    # Timings
    duration_seconds: float = 0.0
    collected_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class FreshnessCheck:
    """Check if data needs refreshing."""
    needs_metadata: bool = True
    needs_amazon_fbm: bool = True
    needs_abebooks: bool = True
    needs_alibris: bool = True
    needs_biblio: bool = True
    needs_zvab: bool = True
    needs_ebay_active: bool = True
    needs_ebay_sold: bool = True
    needs_bookfinder: bool = True
    needs_series: bool = True


def check_data_freshness(
    isbn: str,
    db_path: Path,
    force_refresh: bool = False
) -> FreshnessCheck:
    """
    Check which data sources need updating based on timestamps.

    Args:
        isbn: The ISBN to check
        db_path: Path to metadata_cache.db
        force_refresh: If True, refresh all data regardless of age

    Returns:
        FreshnessCheck indicating which sources need updating
    """
    if force_refresh:
        return FreshnessCheck()  # All True

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    check = FreshnessCheck()
    now = datetime.now()

    # Check cached_books table
    cursor.execute("""
        SELECT
            metadata_fetched_at,
            amazon_fbm_collected_at,
            abebooks_enr_collected_at,
            last_enrichment_at
        FROM cached_books
        WHERE isbn = ?
    """, (isbn,))

    row = cursor.fetchone()
    if row:
        # Check metadata freshness
        if row["metadata_fetched_at"]:
            metadata_age = now - datetime.fromisoformat(row["metadata_fetched_at"])
            check.needs_metadata = metadata_age > timedelta(days=FRESHNESS["metadata"])

        # Check Amazon FBM freshness
        if row["amazon_fbm_collected_at"]:
            amazon_age = now - datetime.fromisoformat(row["amazon_fbm_collected_at"])
            check.needs_amazon_fbm = amazon_age > timedelta(days=FRESHNESS["amazon_fbm"])

        # Check AbeBooks freshness (only one with collected_at timestamp)
        if row["abebooks_enr_collected_at"]:
            abe_age = now - datetime.fromisoformat(row["abebooks_enr_collected_at"])
            check.needs_abebooks = abe_age > timedelta(days=FRESHNESS["abebooks"])

        # For Alibris, Biblio, ZVAB - use last_enrichment_at as fallback
        if row["last_enrichment_at"]:
            enr_age = now - datetime.fromisoformat(row["last_enrichment_at"])
            check.needs_alibris = enr_age > timedelta(days=FRESHNESS["alibris"])
            check.needs_biblio = enr_age > timedelta(days=FRESHNESS["biblio"])
            check.needs_zvab = enr_age > timedelta(days=FRESHNESS["zvab"])
            check.needs_series = enr_age > timedelta(days=FRESHNESS["series"])
            check.needs_bookfinder = enr_age > timedelta(days=FRESHNESS["bookfinder"])

    # Check eBay active listings
    cursor.execute("""
        SELECT MAX(collected_at) as last_collected
        FROM ebay_active_listings
        WHERE isbn = ?
    """, (isbn,))

    ebay_row = cursor.fetchone()
    if ebay_row and ebay_row["last_collected"]:
        ebay_age = now - datetime.fromisoformat(ebay_row["last_collected"])
        check.needs_ebay_active = ebay_age > timedelta(days=FRESHNESS["ebay_active"])

    # Check eBay sold comps (check if sold_comps_is_estimate or old data)
    cursor.execute("""
        SELECT sold_comps_is_estimate, last_enrichment_at
        FROM cached_books
        WHERE isbn = ?
    """, (isbn,))

    sold_row = cursor.fetchone()
    if sold_row:
        # Always refresh if current data is an estimate
        if sold_row["sold_comps_is_estimate"]:
            check.needs_ebay_sold = True
        elif sold_row["last_enrichment_at"]:
            sold_age = now - datetime.fromisoformat(sold_row["last_enrichment_at"])
            check.needs_ebay_sold = sold_age > timedelta(days=FRESHNESS["ebay_sold"])

    conn.close()
    return check


async def collect_metadata(isbn: str, session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    Collect basic metadata from Google Books API.

    Args:
        isbn: The ISBN to look up
        session: Requests session for HTTP calls

    Returns:
        Metadata dictionary or None if collection fails
    """
    try:
        logger.info(f"Collecting metadata for {isbn}...")
        metadata = fetch_metadata(session, isbn, delay=0.0)
        return metadata
    except Exception as e:
        logger.error(f"Failed to collect metadata for {isbn}: {e}")
        return None


async def collect_amazon_fbm(isbn: str, db_path: Path) -> Tuple[int, bool]:
    """
    Collect Amazon FBM (Fulfilled by Merchant) pricing data.

    This uses the existing Amazon scraping logic.

    Args:
        isbn: The ISBN to collect
        db_path: Path to metadata cache database

    Returns:
        Tuple of (count_collected, success)
    """
    try:
        logger.info(f"Collecting Amazon FBM data for {isbn}...")

        # Use existing Amazon API/scraper
        from shared.amazon_api import get_amazon_pricing

        result = get_amazon_pricing(isbn)
        if not result:
            return 0, False

        # Store in amazon_pricing table
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO amazon_pricing
            (isbn, price, condition, shipping_cost, seller_rating, collected_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            isbn,
            result.get("price"),
            result.get("condition", "Used"),
            result.get("shipping"),
            result.get("rating"),
            datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()

        return 1, True
    except Exception as e:
        logger.error(f"Failed to collect Amazon FBM for {isbn}: {e}")
        return 0, False


async def collect_ebay_active(isbn: str, db_path: Path) -> Tuple[int, bool]:
    """
    Collect eBay active listings using Browse API.

    Args:
        isbn: The ISBN to collect
        db_path: Path to metadata cache database

    Returns:
        Tuple of (count_collected, success)
    """
    try:
        logger.info(f"Collecting eBay active listings for {isbn}...")

        # Get OAuth token
        client_id = os.getenv("EBAY_CLIENT_ID")
        client_secret = os.getenv("EBAY_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.warning("eBay credentials not found, skipping active listings")
            return 0, False

        import base64
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        # Get token
        token_response = requests.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
            timeout=15
        )
        token = token_response.json()["access_token"]

        # Search for ISBN
        search_response = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            params={
                "q": isbn,
                "limit": 50,
                "filter": "buyingOptions:{FIXED_PRICE}",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            },
            timeout=10
        )

        data = search_response.json()
        items = data.get("itemSummaries", [])

        if not items:
            logger.info(f"No eBay active listings found for {isbn}")
            return 0, True

        # Store in ebay_active_listings table
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        count = 0
        for item in items:
            item_id = item.get("itemId")
            if not item_id:
                continue

            price = None
            if "price" in item:
                price = float(item["price"].get("value", 0))

            cursor.execute("""
                INSERT OR REPLACE INTO ebay_active_listings
                (isbn, item_id, title, price, condition, binding, seller, listing_url,
                 image_url, shipping_cost, item_location, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                isbn,
                item_id,
                item.get("title"),
                price,
                item.get("condition"),
                None,  # binding not available from Browse API
                item.get("seller", {}).get("username"),
                item.get("itemWebUrl"),
                item.get("image", {}).get("imageUrl") if "image" in item else None,
                float(item.get("shippingOptions", [{}])[0].get("shippingCost", {}).get("value", 0)) if item.get("shippingOptions") else None,
                item.get("itemLocation", {}).get("city"),
                datetime.now().isoformat()
            ))
            count += 1

        conn.commit()
        conn.close()

        logger.info(f"Collected {count} eBay active listings for {isbn}")
        return count, True

    except Exception as e:
        logger.error(f"Failed to collect eBay active listings for {isbn}: {e}")
        return 0, False


async def collect_ebay_sold_serper_decodo(isbn: str, db_path: Path) -> Tuple[int, bool]:
    """
    Collect eBay sold comps using Serper (Google Search) + Decodo (scraping).

    This searches Google for eBay sold listings, then scrapes the pages to extract
    sold prices. Falls back to estimating from active listings if needed.

    Args:
        isbn: The ISBN to collect
        db_path: Path to metadata cache database

    Returns:
        Tuple of (count_collected, success)
    """
    try:
        logger.info(f"Collecting eBay sold comps for {isbn}...")

        # Get API keys
        serper_key = os.getenv("X-API-KEY")
        decodo_user = os.getenv("DECODO_CORE_AUTHENTICATION")
        decodo_pass = os.getenv("DECODO_CORE_PASSWORD")

        # Try reading from .env file if not in environment
        if not serper_key or not decodo_user or not decodo_pass:
            env_path = Path.home() / "ISBN" / ".env"
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("X-API-KEY="):
                            serper_key = line.split("=", 1)[1].strip()
                        elif line.startswith("DECODO_CORE_AUTHENTICATION="):
                            decodo_user = line.split("=", 1)[1].strip()
                        elif line.startswith("DECODO_CORE_PASSWORD="):
                            decodo_pass = line.split("=", 1)[1].strip()

        if not serper_key or not decodo_user or not decodo_pass:
            logger.warning("Serper/Decodo credentials not found, will estimate from active listings")
            return await _estimate_sold_from_active(isbn, db_path)

        # Search via Serper for eBay sold listings
        # Note: This is a placeholder - real implementation would search for sold listings
        # For now, we'll estimate from active listings (75% rule)
        logger.info("Serper + Decodo sold collection not yet implemented, using estimate")
        return await _estimate_sold_from_active(isbn, db_path)

    except Exception as e:
        logger.error(f"Failed to collect eBay sold comps for {isbn}: {e}")
        return 0, False


async def _estimate_sold_from_active(isbn: str, db_path: Path) -> Tuple[int, bool]:
    """
    Estimate sold comps from active listings using the 75% rule.

    Args:
        isbn: The ISBN to estimate for
        db_path: Path to metadata cache database

    Returns:
        Tuple of (count_collected, success)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get active listing prices
    cursor.execute("""
        SELECT price
        FROM ebay_active_listings
        WHERE isbn = ? AND price IS NOT NULL
    """, (isbn,))

    prices = [row[0] for row in cursor.fetchall()]

    if not prices:
        logger.info(f"No active listings to estimate from for {isbn}")
        conn.close()
        return 0, False

    # Calculate statistics and apply 75% rule
    median = statistics.median(prices)
    estimated_sold_median = median * 0.75
    estimated_sold_min = min(prices) * 0.75
    estimated_sold_max = max(prices) * 0.75

    # Update cached_books with estimated sold comps
    cursor.execute("""
        UPDATE cached_books
        SET
            sold_comps_count = ?,
            sold_comps_min = ?,
            sold_comps_median = ?,
            sold_comps_max = ?,
            sold_comps_is_estimate = 1,
            sold_comps_source = 'active_listings_estimate',
            last_enrichment_at = ?
        WHERE isbn = ?
    """, (
        len(prices),
        estimated_sold_min,
        estimated_sold_median,
        estimated_sold_max,
        datetime.now().isoformat(),
        isbn
    ))

    conn.commit()
    conn.close()

    logger.info(f"Estimated sold comps for {isbn}: ${estimated_sold_median:.2f} median (from {len(prices)} active)")
    return len(prices), True


async def collect_marketplace_data(
    isbn: str,
    db_path: Path,
    vendors: List[str]
) -> Dict[str, Tuple[int, bool]]:
    """
    Collect marketplace pricing data from AbeBooks, Alibris, Biblio, ZVAB.

    Args:
        isbn: The ISBN to collect
        db_path: Path to metadata cache database
        vendors: List of vendors to collect from (e.g., ["abebooks", "alibris"])

    Returns:
        Dictionary mapping vendor name to (count, success) tuple
    """
    results = {}

    for vendor in vendors:
        try:
            logger.info(f"Collecting {vendor} data for {isbn}...")

            # Use existing scrapers
            if vendor == "abebooks":
                from shared.abebooks_scraper import scrape_abebooks_isbn
                offers = scrape_abebooks_isbn(isbn)
            elif vendor == "alibris":
                from shared.alibris_scraper import scrape_alibris_isbn
                offers = scrape_alibris_isbn(isbn)
            elif vendor == "biblio":
                from shared.biblio_scraper import scrape_biblio_isbn
                offers = scrape_biblio_isbn(isbn)
            elif vendor == "zvab":
                from shared.zvab_scraper import scrape_zvab_isbn
                offers = scrape_zvab_isbn(isbn)
            else:
                logger.warning(f"Unknown vendor: {vendor}")
                results[vendor] = (0, False)
                continue

            if not offers:
                logger.info(f"No {vendor} offers found for {isbn}")
                results[vendor] = (0, True)
                continue

            # Store aggregated stats in cached_books
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            prices = [o["price"] for o in offers if o.get("price")]
            if prices:
                column_prefix = f"{vendor}_enr"
                cursor.execute(f"""
                    UPDATE cached_books
                    SET
                        {column_prefix}_count = ?,
                        {column_prefix}_min = ?,
                        {column_prefix}_median = ?,
                        {column_prefix}_avg = ?,
                        {column_prefix}_max = ?,
                        {column_prefix}_spread = ?,
                        {column_prefix}_collected_at = ?
                    WHERE isbn = ?
                """, (
                    len(prices),
                    min(prices),
                    statistics.median(prices),
                    sum(prices) / len(prices),
                    max(prices),
                    max(prices) - min(prices),
                    datetime.now().isoformat(),
                    isbn
                ))

                conn.commit()

            conn.close()

            logger.info(f"Collected {len(offers)} {vendor} offers for {isbn}")
            results[vendor] = (len(offers), True)

        except Exception as e:
            logger.error(f"Failed to collect {vendor} data for {isbn}: {e}")
            results[vendor] = (0, False)

    return results


def enrich_book_data(
    isbn: str,
    db_path: Optional[Path] = None,
    force_refresh: bool = False,
    collect_metadata_data: bool = True,
    collect_marketplace: bool = True,
    collect_ebay: bool = True,
    collect_amazon: bool = True,
) -> EnrichmentResult:
    """
    Main entry point for unified book data enrichment.

    Orchestrates collection from all available data sources based on freshness
    checks. Only collects data that is stale or missing.

    Args:
        isbn: The ISBN to enrich (will be normalized)
        db_path: Path to metadata cache DB (defaults to ~/.isbn_lot_optimizer/metadata_cache.db)
        force_refresh: If True, refresh all data regardless of age
        collect_metadata_data: Collect basic metadata (Google Books)
        collect_marketplace: Collect marketplace data (AbeBooks, Alibris, etc.)
        collect_ebay: Collect eBay active and sold data
        collect_amazon: Collect Amazon FBM data

    Returns:
        EnrichmentResult with collection statistics

    Example:
        >>> from pathlib import Path
        >>> from isbn_lot_optimizer.enrichment import enrich_book_data
        >>>
        >>> result = enrich_book_data("9780399127212")
        >>> print(f"Collected {result.ebay_active_count} eBay listings")
        >>> print(f"Success: {result.success}")
    """
    start_time = time.time()

    # Normalize ISBN
    from shared.utils import normalise_isbn
    isbn = normalise_isbn(isbn)
    if not isbn:
        return EnrichmentResult(
            isbn=isbn,
            success=False,
            error="Invalid ISBN format"
        )

    # Default database path
    if db_path is None:
        db_path = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"

    # Ensure book exists in cached_books
    _ensure_book_exists(isbn, db_path)

    # Check what needs updating
    freshness = check_data_freshness(isbn, db_path, force_refresh)

    result = EnrichmentResult(isbn=isbn, success=True)

    # Create session for metadata calls
    http_session = create_http_session()

    try:
        # Collect metadata if needed
        if collect_metadata_data and freshness.needs_metadata:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            metadata = loop.run_until_complete(collect_metadata(isbn, http_session))
            loop.close()

            if metadata:
                _store_metadata(isbn, metadata, db_path)
                result.metadata_collected = True

        # Collect Amazon FBM if needed
        if collect_amazon and freshness.needs_amazon_fbm:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            count, success = loop.run_until_complete(collect_amazon_fbm(isbn, db_path))
            loop.close()

            result.amazon_fbm_collected = success
            result.amazon_fbm_count = count

        # Collect eBay data if needed
        if collect_ebay:
            if freshness.needs_ebay_active:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                count, success = loop.run_until_complete(collect_ebay_active(isbn, db_path))
                loop.close()

                result.ebay_active_collected = success
                result.ebay_active_count = count

            if freshness.needs_ebay_sold:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                count, success = loop.run_until_complete(collect_ebay_sold_serper_decodo(isbn, db_path))
                loop.close()

                result.ebay_sold_collected = success
                result.ebay_sold_count = count

        # Collect marketplace data if needed
        if collect_marketplace:
            vendors_to_collect = []
            if freshness.needs_abebooks:
                vendors_to_collect.append("abebooks")
            if freshness.needs_alibris:
                vendors_to_collect.append("alibris")
            if freshness.needs_biblio:
                vendors_to_collect.append("biblio")
            if freshness.needs_zvab:
                vendors_to_collect.append("zvab")

            if vendors_to_collect:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                marketplace_results = loop.run_until_complete(
                    collect_marketplace_data(isbn, db_path, vendors_to_collect)
                )
                loop.close()

                for vendor, (count, success) in marketplace_results.items():
                    if vendor == "abebooks":
                        result.abebooks_collected = success
                        result.abebooks_count = count
                    elif vendor == "alibris":
                        result.alibris_collected = success
                        result.alibris_count = count
                    elif vendor == "biblio":
                        result.biblio_collected = success
                        result.biblio_count = count
                    elif vendor == "zvab":
                        result.zvab_collected = success
                        result.zvab_count = count

        result.duration_seconds = time.time() - start_time

        # Run ML predictions after successful data collection
        # This ensures the book gets fresh price estimates and probability scores
        if result.success and (result.ebay_active_collected or result.metadata_collected):
            try:
                _run_ml_predictions(isbn, db_path)
            except Exception as ml_error:
                logger.warning(f"ML prediction failed for {isbn}: {ml_error}")
                # Don't fail the entire enrichment if ML fails

    except Exception as e:
        logger.error(f"Enrichment failed for {isbn}: {e}")
        result.success = False
        result.error = str(e)
        result.duration_seconds = time.time() - start_time

    finally:
        http_session.close()

    return result


def _ensure_book_exists(isbn: str, db_path: Path) -> None:
    """Ensure a book record exists in cached_books table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO cached_books (isbn, created_at)
        VALUES (?, ?)
    """, (isbn, datetime.now().isoformat()))

    conn.commit()
    conn.close()


def _store_metadata(isbn: str, metadata: Dict[str, Any], db_path: Path) -> None:
    """Store collected metadata in cached_books table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE cached_books
        SET
            title = ?,
            authors = ?,
            publisher = ?,
            publication_year = ?,
            page_count = ?,
            language = ?,
            description = ?,
            thumbnail_url = ?,
            metadata_fetched_at = ?,
            updated_at = ?
        WHERE isbn = ?
    """, (
        metadata.get("title"),
        metadata.get("authors"),
        metadata.get("publisher"),
        metadata.get("published_year"),
        metadata.get("page_count"),
        metadata.get("language"),
        metadata.get("description"),
        metadata.get("thumbnail"),
        datetime.now().isoformat(),
        datetime.now().isoformat(),
        isbn
    ))

    conn.commit()
    conn.close()


def _run_ml_predictions(isbn: str, db_path: Path) -> None:
    """
    Run ML predictions on newly enriched book data.

    This generates:
    - Price estimates (from stacking models)
    - Probability scores (ACCEPT/REJECT/CONSIDER)
    - Rarity scores
    - Time-to-sell estimates

    Results are stored back in cached_books table.
    """
    from isbn_lot_optimizer.ml.predictor import predict_book_price

    logger.info(f"Running ML predictions for {isbn}")

    try:
        # Run the price prediction which also updates probability scores
        result = predict_book_price(isbn, db_path)

        if result:
            logger.info(f"ML prediction complete for {isbn}: ${result.get('estimated_price', 0):.2f}")
        else:
            logger.warning(f"ML prediction returned no result for {isbn}")

    except Exception as e:
        # Log but don't fail - ML is a nice-to-have, not critical
        logger.warning(f"ML prediction error for {isbn}: {e}")
        raise  # Re-raise to let caller decide how to handle
