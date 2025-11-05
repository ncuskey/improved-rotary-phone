"""
API endpoints for sold listing history and statistics.

Provides access to sold listing data collected from eBay, Mercari, and Amazon.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from shared.sold_stats import SoldStatistics
from shared.sold_features import extract_sold_ml_features


router = APIRouter(prefix="/api/books", tags=["sold_history"])


class SoldStatisticsResponse(BaseModel):
    """Response model for sold statistics."""
    isbn: str
    platform: Optional[str]
    total_sales: int
    single_sales: int
    lot_count: int
    min_price: Optional[float]
    max_price: Optional[float]
    avg_price: Optional[float]
    median_price: Optional[float]
    p25_price: Optional[float]
    p75_price: Optional[float]
    std_dev: Optional[float]
    avg_sales_per_month: Optional[float]
    data_completeness: float
    from_cache: bool


class SoldListingResponse(BaseModel):
    """Response model for individual sold listings."""
    isbn: str
    platform: str
    url: str
    title: Optional[str]
    price: Optional[float]
    condition: Optional[str]
    sold_date: Optional[str]
    is_lot: bool
    scraped_at: str


class SoldMLFeaturesResponse(BaseModel):
    """Response model for ML features from sold data."""
    isbn: str
    features: Dict[str, Any]
    feature_count: int
    has_sold_data: bool


@router.get("/{isbn}/sold-statistics", response_model=SoldStatisticsResponse)
async def get_sold_statistics(
    isbn: str,
    platform: Optional[str] = Query(None, description="Platform filter (ebay, mercari, amazon, or null for all)"),
    days_lookback: int = Query(365, description="Days of history to analyze", ge=1, le=730),
    use_cache: bool = Query(True, description="Use cached statistics")
):
    """
    Get aggregated sold listing statistics for an ISBN.

    Returns price statistics, sales volume, and velocity metrics.
    Data is cached for 7 days by default.

    Example:
        GET /api/books/9780307387899/sold-statistics
        GET /api/books/9780307387899/sold-statistics?platform=ebay
        GET /api/books/9780307387899/sold-statistics?days_lookback=180
    """
    stats_engine = SoldStatistics()

    try:
        stats = stats_engine.get_statistics(
            isbn,
            platform=platform,
            days_lookback=days_lookback,
            use_cache=use_cache
        )

        return SoldStatisticsResponse(**stats)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving statistics: {str(e)}")


@router.get("/{isbn}/sold-listings", response_model=List[SoldListingResponse])
async def get_sold_listings(
    isbn: str,
    platform: Optional[str] = Query(None, description="Platform filter"),
    limit: int = Query(50, description="Maximum listings to return", ge=1, le=500)
):
    """
    Get individual sold listings for an ISBN.

    Returns raw sold listing data from the database.

    Example:
        GET /api/books/9780307387899/sold-listings
        GET /api/books/9780307387899/sold-listings?platform=ebay&limit=20
    """
    import sqlite3

    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if platform:
            query = """
                SELECT isbn, platform, url, title, price, condition, sold_date,
                       is_lot, datetime(scraped_at)
                FROM sold_listings
                WHERE isbn = ? AND platform = ?
                ORDER BY sold_date DESC, scraped_at DESC
                LIMIT ?
            """
            cursor.execute(query, (isbn, platform, limit))
        else:
            query = """
                SELECT isbn, platform, url, title, price, condition, sold_date,
                       is_lot, datetime(scraped_at)
                FROM sold_listings
                WHERE isbn = ?
                ORDER BY sold_date DESC, scraped_at DESC
                LIMIT ?
            """
            cursor.execute(query, (isbn, limit))

        rows = cursor.fetchall()
        conn.close()

        listings = []
        for row in rows:
            listings.append(SoldListingResponse(
                isbn=row[0],
                platform=row[1],
                url=row[2],
                title=row[3],
                price=row[4],
                condition=row[5],
                sold_date=row[6],
                is_lot=bool(row[7]),
                scraped_at=row[8]
            ))

        return listings

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving listings: {str(e)}")


@router.get("/{isbn}/sold-ml-features", response_model=SoldMLFeaturesResponse)
async def get_sold_ml_features(
    isbn: str,
    days_lookback: int = Query(365, description="Days of history to analyze", ge=1, le=730)
):
    """
    Get ML-ready features extracted from sold listing data.

    Returns feature dict suitable for price estimation models.

    Example:
        GET /api/books/9780307387899/sold-ml-features
    """
    try:
        features = extract_sold_ml_features(isbn, days_lookback=days_lookback)

        # Count non-null features
        feature_count = sum(1 for v in features.values() if v is not None and v != 0 and v != False)

        return SoldMLFeaturesResponse(
            isbn=isbn,
            features=features,
            feature_count=feature_count,
            has_sold_data=features.get('sold_has_data', False)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting features: {str(e)}")


@router.get("/{isbn}/sold-multi-platform", response_model=Dict[str, SoldStatisticsResponse])
async def get_sold_multi_platform(
    isbn: str,
    days_lookback: int = Query(365, description="Days of history to analyze", ge=1, le=730)
):
    """
    Get sold statistics for all platforms plus aggregated.

    Returns:
        {
            "all": {...},
            "ebay": {...},
            "mercari": {...},
            "amazon": {...}
        }

    Example:
        GET /api/books/9780307387899/sold-multi-platform
    """
    stats_engine = SoldStatistics()

    try:
        all_stats = stats_engine.get_multi_platform_statistics(isbn, days_lookback=days_lookback)

        response = {}
        for platform, stats in all_stats.items():
            response[platform] = SoldStatisticsResponse(**stats)

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving multi-platform statistics: {str(e)}")
