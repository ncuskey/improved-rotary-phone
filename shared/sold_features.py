"""
ML feature extraction from sold listing data.

Converts sold statistics into ML-ready features for price estimation models.
"""

from typing import Dict, Any, Optional
from pathlib import Path

from shared.sold_stats import SoldStatistics


def extract_sold_ml_features(
    isbn: str,
    db_path: Path = None,
    days_lookback: int = 365,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Extract ML features from sold listing statistics.

    Features include:
    - sold_avg_price: Average sold price across all platforms
    - sold_median_price: Median sold price
    - sold_min_price: Minimum sold price
    - sold_max_price: Maximum sold price
    - sold_price_spread: Price range (max - min)
    - sold_price_cv: Coefficient of variation (std_dev / mean)
    - sold_sales_count: Total number of sales
    - sold_sales_per_month: Sales velocity
    - ebay_avg_price: eBay-specific average
    - mercari_avg_price: Mercari-specific average
    - amazon_has_listing: Whether Amazon has/had this book
    - sold_data_completeness: % of records with complete data
    - sold_has_data: Whether any sold data exists

    Args:
        isbn: ISBN to extract features for
        db_path: Path to catalog.db
        days_lookback: How many days back to analyze
        use_cache: Use cached statistics

    Returns:
        Dict of ML features (values are None if no data available)
    """
    stats_engine = SoldStatistics(db_path)

    # Get multi-platform statistics
    all_stats = stats_engine.get_multi_platform_statistics(
        isbn,
        days_lookback=days_lookback,
        use_cache=use_cache
    )

    # Extract aggregated features
    agg_stats = all_stats['all']
    ebay_stats = all_stats['ebay']
    mercari_stats = all_stats['mercari']
    amazon_stats = all_stats['amazon']

    # Build feature dict
    features = {
        # Aggregated price features
        'sold_avg_price': agg_stats.get('avg_price'),
        'sold_median_price': agg_stats.get('median_price'),
        'sold_min_price': agg_stats.get('min_price'),
        'sold_max_price': agg_stats.get('max_price'),
        'sold_p25_price': agg_stats.get('p25_price'),
        'sold_p75_price': agg_stats.get('p75_price'),

        # Derived price features
        'sold_price_spread': None,
        'sold_price_cv': None,  # Coefficient of variation

        # Volume features
        'sold_sales_count': agg_stats.get('total_sales', 0),
        'sold_single_sales_count': agg_stats.get('single_sales', 0),
        'sold_lot_sales_count': agg_stats.get('lot_count', 0),
        'sold_sales_per_month': agg_stats.get('avg_sales_per_month'),

        # Platform-specific price features
        'ebay_sold_avg_price': ebay_stats.get('avg_price'),
        'ebay_sold_sales_count': ebay_stats.get('total_sales', 0),
        'mercari_sold_avg_price': mercari_stats.get('avg_price'),
        'mercari_sold_sales_count': mercari_stats.get('total_sales', 0),
        'amazon_sold_avg_price': amazon_stats.get('avg_price'),
        'amazon_sold_sales_count': amazon_stats.get('total_sales', 0),

        # Presence indicators
        'amazon_has_listing': amazon_stats.get('total_sales', 0) > 0,
        'ebay_has_sold_data': ebay_stats.get('total_sales', 0) > 0,
        'mercari_has_sold_data': mercari_stats.get('total_sales', 0) > 0,

        # Data quality
        'sold_data_completeness': agg_stats.get('data_completeness', 0.0),
        'sold_has_data': agg_stats.get('total_sales', 0) > 0,
    }

    # Compute derived features
    if features['sold_min_price'] and features['sold_max_price']:
        features['sold_price_spread'] = round(
            features['sold_max_price'] - features['sold_min_price'], 2
        )

    if features['sold_avg_price'] and agg_stats.get('std_dev'):
        # Coefficient of variation (normalized volatility)
        features['sold_price_cv'] = round(
            agg_stats['std_dev'] / features['sold_avg_price'], 3
        )

    return features


def get_all_ml_features(isbn: str, db_path: Path = None) -> Dict[str, Any]:
    """
    Get all ML features including sold data for comprehensive price estimation.

    Combines:
    - Sold listing features (from sold_stats)
    - Can be extended to include other feature sources

    Args:
        isbn: ISBN to extract features for
        db_path: Path to catalog.db

    Returns:
        Dict with all ML features
    """
    features = {}

    # Get sold features
    sold_features = extract_sold_ml_features(isbn, db_path)
    features.update(sold_features)

    # Future: Add other feature sources here
    # - BookFinder features
    # - AbeBooks features
    # - Metadata features (page count, age, etc.)

    return features


if __name__ == "__main__":
    # Test feature extraction
    print("Testing Sold ML Feature Extraction")
    print("=" * 80)
    print()

    test_isbn = "9780307387899"

    print(f"Extracting features for ISBN {test_isbn}...")
    features = extract_sold_ml_features(test_isbn)

    print()
    print("Extracted Features:")
    print("-" * 80)

    # Group features by category
    price_features = {k: v for k, v in features.items() if 'price' in k}
    volume_features = {k: v for k, v in features.items() if 'sales' in k or 'count' in k}
    platform_features = {k: v for k, v in features.items() if any(p in k for p in ['ebay', 'mercari', 'amazon'])}
    quality_features = {k: v for k, v in features.items() if 'completeness' in k or 'has_' in k}

    print("\nPrice Features:")
    for key, value in price_features.items():
        if value is not None:
            if isinstance(value, float):
                if 'cv' in key:
                    print(f"  {key}: {value:.3f}")
                else:
                    print(f"  {key}: ${value:.2f}")
            else:
                print(f"  {key}: {value}")

    print("\nVolume Features:")
    for key, value in volume_features.items():
        if value is not None:
            print(f"  {key}: {value}")

    print("\nPlatform Features:")
    for key, value in platform_features.items():
        if value is not None and value != 0:
            if isinstance(value, float):
                print(f"  {key}: ${value:.2f}")
            else:
                print(f"  {key}: {value}")

    print("\nData Quality:")
    for key, value in quality_features.items():
        print(f"  {key}: {value}")

    print()
