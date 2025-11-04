"""
Sold listing statistics engine.

Computes aggregated statistics from sold_listings data and caches results
in sold_statistics table. Provides ML features and sell-through analysis.
"""

import sqlite3
import statistics
import time
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime, timedelta


class SoldStatistics:
    """Computes and caches sold listing statistics."""

    CACHE_TTL_DAYS = 7  # Re-compute stats every 7 days

    def __init__(self, db_path: Path = None):
        """
        Initialize statistics engine.

        Args:
            db_path: Path to catalog.db
        """
        self.db_path = db_path or Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    def _get_sold_listings(
        self,
        isbn: str,
        platform: Optional[str] = None,
        days_lookback: int = 365
    ) -> List[Dict[str, Any]]:
        """
        Retrieve sold listings from database.

        Args:
            isbn: ISBN to query
            platform: Optional platform filter (None = all platforms)
            days_lookback: How many days back to look

        Returns:
            List of sold listing dicts
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days_lookback)).strftime('%Y-%m-%d')

        if platform:
            query = """
                SELECT isbn, platform, price, condition, sold_date, is_lot, title
                FROM sold_listings
                WHERE isbn = ? AND platform = ? AND (sold_date >= ? OR sold_date IS NULL)
            """
            cursor.execute(query, (isbn, platform, cutoff_date))
        else:
            query = """
                SELECT isbn, platform, price, condition, sold_date, is_lot, title
                FROM sold_listings
                WHERE isbn = ? AND (sold_date >= ? OR sold_date IS NULL)
            """
            cursor.execute(query, (isbn, cutoff_date))

        rows = cursor.fetchall()
        conn.close()

        listings = []
        for row in rows:
            listings.append({
                'isbn': row[0],
                'platform': row[1],
                'price': row[2],
                'condition': row[3],
                'sold_date': row[4],
                'is_lot': bool(row[5]),
                'title': row[6]
            })

        return listings

    def _compute_statistics(self, listings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compute statistics from listing data.

        Args:
            listings: List of sold listing dicts

        Returns:
            Dict with computed statistics
        """
        if not listings:
            return {
                'total_sales': 0,
                'lot_count': 0,
                'single_sales': 0,
                'min_price': None,
                'max_price': None,
                'avg_price': None,
                'median_price': None,
                'std_dev': None,
                'p25_price': None,
                'p75_price': None,
                'avg_sales_per_month': None,
                'data_completeness': 0.0
            }

        # Separate lots from single sales
        single_sales = [l for l in listings if not l['is_lot']]
        lot_sales = [l for l in listings if l['is_lot']]

        # Price statistics (exclude lots)
        prices = [l['price'] for l in single_sales if l['price'] is not None and l['price'] > 0]

        if prices:
            prices_sorted = sorted(prices)
            n = len(prices)

            # Percentiles
            p25_index = int(n * 0.25)
            p75_index = int(n * 0.75)

            price_stats = {
                'min_price': round(min(prices), 2),
                'max_price': round(max(prices), 2),
                'avg_price': round(statistics.mean(prices), 2),
                'median_price': round(statistics.median(prices), 2),
                'std_dev': round(statistics.stdev(prices), 2) if len(prices) > 1 else 0.0,
                'p25_price': round(prices_sorted[p25_index], 2),
                'p75_price': round(prices_sorted[p75_index], 2)
            }
        else:
            price_stats = {
                'min_price': None,
                'max_price': None,
                'avg_price': None,
                'median_price': None,
                'std_dev': None,
                'p25_price': None,
                'p75_price': None
            }

        # Sales velocity (sales per month)
        dated_sales = [l for l in listings if l['sold_date']]
        if dated_sales:
            dates = [datetime.strptime(l['sold_date'], '%Y-%m-%d') for l in dated_sales]
            date_range_days = (max(dates) - min(dates)).days
            if date_range_days > 0:
                months = date_range_days / 30.0
                avg_sales_per_month = round(len(dated_sales) / months, 2)
            else:
                avg_sales_per_month = len(dated_sales)  # All sold on same day
        else:
            avg_sales_per_month = None

        # Data completeness (% with price and condition)
        complete_records = sum(
            1 for l in listings
            if l['price'] is not None and l['condition'] is not None
        )
        data_completeness = round(complete_records / len(listings) * 100, 1) if listings else 0.0

        return {
            'total_sales': len(listings),
            'lot_count': len(lot_sales),
            'single_sales': len(single_sales),
            **price_stats,
            'avg_sales_per_month': avg_sales_per_month,
            'data_completeness': data_completeness
        }

    def _get_cached_statistics(
        self,
        isbn: str,
        platform: Optional[str],
        days_lookback: int
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached statistics if not expired.

        Args:
            isbn: ISBN
            platform: Platform filter (None = all)
            days_lookback: Days lookback window

        Returns:
            Cached stats dict or None if expired/missing
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        current_time = int(time.time())

        platform_filter = platform if platform else ''

        cursor.execute("""
            SELECT * FROM sold_statistics
            WHERE isbn = ? AND (platform = ? OR platform IS NULL) AND days_lookback = ? AND expires_at > ?
        """, (isbn, platform_filter, days_lookback, current_time))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # Map row to dict
        return {
            'id': row[0],
            'isbn': row[1],
            'platform': row[2],
            'days_lookback': row[3],
            'total_sales': row[4],
            'lot_count': row[5],
            'single_sales': row[6],
            'min_price': row[7],
            'max_price': row[8],
            'avg_price': row[9],
            'median_price': row[10],
            'std_dev': row[11],
            'p25_price': row[12],
            'p75_price': row[13],
            'active_listings': row[14],
            'sell_through_rate': row[15],
            'avg_sales_per_month': row[16],
            'data_completeness': row[17],
            'computed_at': row[18],
            'expires_at': row[19]
        }

    def _cache_statistics(
        self,
        isbn: str,
        platform: Optional[str],
        days_lookback: int,
        stats: Dict[str, Any]
    ):
        """
        Save computed statistics to cache.

        Args:
            isbn: ISBN
            platform: Platform filter (None = all)
            days_lookback: Days lookback window
            stats: Computed statistics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        current_time = int(time.time())
        expires_at = current_time + (self.CACHE_TTL_DAYS * 24 * 60 * 60)

        platform_value = platform if platform else None

        cursor.execute("""
            INSERT OR REPLACE INTO sold_statistics
            (isbn, platform, days_lookback, total_sales, lot_count, single_sales,
             min_price, max_price, avg_price, median_price, std_dev,
             p25_price, p75_price, avg_sales_per_month, data_completeness,
             computed_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """, (
            isbn,
            platform_value,
            days_lookback,
            stats['total_sales'],
            stats['lot_count'],
            stats['single_sales'],
            stats['min_price'],
            stats['max_price'],
            stats['avg_price'],
            stats['median_price'],
            stats['std_dev'],
            stats['p25_price'],
            stats['p75_price'],
            stats['avg_sales_per_month'],
            stats['data_completeness'],
            expires_at
        ))

        conn.commit()
        conn.close()

    def get_statistics(
        self,
        isbn: str,
        platform: Optional[str] = None,
        days_lookback: int = 365,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get sold listing statistics for an ISBN.

        Retrieves from cache if available and not expired, otherwise computes.

        Args:
            isbn: ISBN to analyze
            platform: Optional platform filter ('ebay', 'mercari', 'amazon', or None for all)
            days_lookback: How many days back to analyze (default: 365)
            use_cache: Whether to use cached results (default: True)

        Returns:
            Dict with statistics:
            {
                'isbn': str,
                'platform': str or None,
                'total_sales': int,
                'lot_count': int,
                'single_sales': int,
                'min_price': float,
                'max_price': float,
                'avg_price': float,
                'median_price': float,
                'std_dev': float,
                'p25_price': float,
                'p75_price': float,
                'avg_sales_per_month': float,
                'data_completeness': float,
                'from_cache': bool
            }
        """
        # Check cache
        if use_cache:
            cached = self._get_cached_statistics(isbn, platform, days_lookback)
            if cached:
                cached['from_cache'] = True
                return cached

        # Compute fresh statistics
        listings = self._get_sold_listings(isbn, platform, days_lookback)
        stats = self._compute_statistics(listings)

        stats['isbn'] = isbn
        stats['platform'] = platform
        stats['days_lookback'] = days_lookback
        stats['from_cache'] = False

        # Cache results
        if use_cache:
            self._cache_statistics(isbn, platform, days_lookback, stats)

        return stats

    def get_multi_platform_statistics(
        self,
        isbn: str,
        days_lookback: int = 365,
        use_cache: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all platforms plus aggregated.

        Args:
            isbn: ISBN to analyze
            days_lookback: Days lookback window
            use_cache: Use cached results

        Returns:
            Dict mapping platform to statistics:
            {
                'all': {...},
                'ebay': {...},
                'mercari': {...},
                'amazon': {...}
            }
        """
        results = {}

        # Get aggregated (all platforms)
        results['all'] = self.get_statistics(isbn, None, days_lookback, use_cache)

        # Get per-platform
        for platform in ['ebay', 'mercari', 'amazon']:
            results[platform] = self.get_statistics(isbn, platform, days_lookback, use_cache)

        return results


if __name__ == "__main__":
    # Test statistics engine
    print("Testing Sold Statistics Engine")
    print("=" * 80)
    print()

    stats_engine = SoldStatistics()

    # Test with a sample ISBN (won't have data yet, but tests the flow)
    test_isbn = "9780307387899"

    print(f"Getting statistics for ISBN {test_isbn}...")
    stats = stats_engine.get_statistics(test_isbn)

    print(f"Results:")
    print(f"  Total sales: {stats['total_sales']}")
    print(f"  Single sales: {stats['single_sales']}")
    print(f"  Lot sales: {stats['lot_count']}")

    if stats['avg_price']:
        print(f"  Avg price: ${stats['avg_price']:.2f}")
        print(f"  Price range: ${stats['min_price']:.2f} - ${stats['max_price']:.2f}")
        print(f"  Median: ${stats['median_price']:.2f}")
        print(f"  P25-P75: ${stats['p25_price']:.2f} - ${stats['p75_price']:.2f}")
    else:
        print("  No price data available")

    print(f"  Data completeness: {stats['data_completeness']:.1f}%")
    print(f"  From cache: {stats['from_cache']}")
    print()

    print("Multi-platform statistics:")
    multi_stats = stats_engine.get_multi_platform_statistics(test_isbn)

    for platform, platform_stats in multi_stats.items():
        print(f"  {platform}: {platform_stats['total_sales']} sales")
    print()
