"""
Background task for enriching series lot market data during scanning.

When a series book is scanned, this task:
1. Checks if we already have lot market data for that series
2. If not, queues a background enrichment job via the SeriesLotEnricher
3. Enriches the data asynchronously without blocking the scan workflow

This builds up series market intelligence over time as books are scanned.
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def should_enrich_series_lot_data(series_id: int, series_title: str) -> bool:
    """
    Check if we should enrich lot market data for this series.

    Returns True if:
    - Series exists in catalog
    - Series doesn't have market data yet (or data is stale)

    Args:
        series_id: ID from catalog.db series table
        series_title: Series title for logging

    Returns:
        bool: True if enrichment should be performed
    """
    import sqlite3
    from shared.db_monitor import monitored_connect

    metadata_cache_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

    try:
        conn = monitored_connect(str(metadata_cache_path))
        cursor = conn.cursor()

        # Check if series already has market data
        cursor.execute("""
            SELECT total_lots_found, enriched_at
            FROM series_lot_stats
            WHERE series_id = ?
        """, (series_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            # No data yet - should enrich
            logger.info(f"Series '{series_title}' (ID: {series_id}) has no market data - queuing enrichment")
            return True

        total_lots_found, enriched_at = row

        if total_lots_found == 0:
            # Previous enrichment found no lots - retry after 30 days
            from datetime import datetime, timedelta
            if enriched_at:
                enriched_date = datetime.fromisoformat(enriched_at)
                if datetime.now() - enriched_date > timedelta(days=30):
                    logger.info(f"Series '{series_title}' market data is stale (0 lots, {enriched_at}) - queuing re-enrichment")
                    return True

            # Too recent to retry
            return False

        # Has data - no need to enrich
        logger.debug(f"Series '{series_title}' already has market data ({total_lots_found} lots from {enriched_at})")
        return False

    except Exception as e:
        logger.error(f"Error checking series lot data for '{series_title}': {e}")
        return False


async def enrich_series_lot_data_async(series_id: int, series_title: str, author_name: Optional[str] = None):
    """
    Asynchronously enrich series lot market data in the background.

    This runs the SeriesLotEnricher for a single series without blocking the main workflow.

    Args:
        series_id: ID from catalog.db series table
        series_title: Series title
        author_name: Optional author name for better search queries
    """
    try:
        logger.info(f"Starting background enrichment for series: {series_title} (ID: {series_id})")

        # Import here to avoid circular deps
        from scripts.enrich_series_lot_market_data import SeriesLotEnricher

        # Create enricher with faster settings (fewer results to avoid blocking)
        enricher = SeriesLotEnricher(
            concurrency=1,  # Process one series at a time
            results_per_search=10,  # Moderate result count
            min_lots_required=2  # Minimum lots to consider valid data
        )

        # Build series dict for enrichment
        series_dict = {
            'series_id': series_id,
            'title': series_title,
            'author': author_name,
            'book_count': 0  # Not needed for single series enrichment
        }

        # Run enrichment (this is CPU-bound, so run in thread pool)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: asyncio.run(enricher.enrich_series(series_dict))
        )

        logger.info(f"Completed background enrichment for series: {series_title}")

    except Exception as e:
        logger.error(f"Error enriching series lot data for '{series_title}': {e}", exc_info=True)


def enrich_series_lot_data_background(
    series_id: int,
    series_title: str,
    author_name: Optional[str] = None
):
    """
    Trigger series lot enrichment as a background task (fire-and-forget).

    This checks if enrichment is needed and queues the async task without blocking.

    Args:
        series_id: ID from catalog.db series table
        series_title: Series title
        author_name: Optional author name for better search queries
    """
    # Check if enrichment is needed
    if not should_enrich_series_lot_data(series_id, series_title):
        return

    # Check if API credentials are available
    decodo_user = os.getenv('DECODO_CORE_USERNAME') or os.getenv('DECODO_AUTHENTICATION')
    decodo_pass = os.getenv('DECODO_CORE_PASSWORD') or os.getenv('DECODO_PASSWORD')
    serper_key = os.getenv('SERPER_API_KEY')

    if not (decodo_user and decodo_pass and serper_key):
        logger.debug(f"Skipping series lot enrichment for '{series_title}' - API credentials not configured")
        return

    try:
        # Create background task
        asyncio.create_task(
            enrich_series_lot_data_async(series_id, series_title, author_name)
        )
        logger.debug(f"Queued background enrichment task for series: {series_title}")
    except RuntimeError:
        # No event loop running (e.g., in tests) - skip
        logger.debug(f"Skipping background enrichment for '{series_title}' - no event loop")
