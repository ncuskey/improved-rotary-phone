#!/usr/bin/env python3
"""
Analyze platform scaling relationships to predict prices across platforms.
Calculate conversion factors and validate cross-platform price estimation.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import statistics

def load_multi_platform_books():
    """Load books with pricing data from multiple platforms."""
    catalog_db = Path.home() / ".isbn_lot_optimizer" / "catalog.db"
    conn = sqlite3.connect(catalog_db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            isbn,
            title,
            authors,
            condition,
            estimated_price,
            ebay_sold_count,
            sold_comps_median,
            abebooks_min_price,
            abebooks_avg_price,
            abebooks_seller_count,
            signed,
            edition,
            metadata_json,
            cover_type
        FROM books
        WHERE estimated_price IS NOT NULL
          AND abebooks_min_price IS NOT NULL
          AND abebooks_min_price > 0
    """)

    books = []
    for row in cursor.fetchall():
        metadata = json.loads(row[12]) if row[12] else {}
        raw = metadata.get('raw', {})

        amazon_rank = raw.get('AmazonSalesRank')
        amazon_count = raw.get('AmazonCount')
        binding = raw.get('Binding')
        edition = raw.get('Edition', '') or row[11] or ''
        page_count = raw.get('NumberOfPages')

        books.append({
            'isbn': row[0],
            'title': row[1],
            'authors': row[2],
            'condition': row[3],
            'binding': binding,
            'estimated_price': row[4],
            'sold_comps_median': row[6],
            'ebay_sold_count': row[5],
            'abebooks_min_price': row[7],
            'abebooks_avg_price': row[8],
            'abebooks_seller_count': row[9],
            'is_signed': row[10],
            'is_first_edition': 'first' in edition.lower() if edition else False,
            'amazon_rank': amazon_rank,
            'amazon_count': amazon_count,
            'page_count': page_count,
            'cover_type': row[13],
        })

    conn.close()
    return books

def calculate_scaling_factors(books):
    """Calculate platform scaling factors by various segments."""

    print(f"\n{'='*80}")
    print("PLATFORM SCALING FACTOR ANALYSIS")
    print(f"{'='*80}\n")

    # Overall scaling factors
    ebay_prices = [b['estimated_price'] for b in books]
    abe_mins = [b['abebooks_min_price'] for b in books]
    abe_avgs = [b['abebooks_avg_price'] for b in books]

    ratios_to_min = [e/a for e, a in zip(ebay_prices, abe_mins)]
    ratios_to_avg = [e/a for e, a in zip(ebay_prices, abe_avgs)]

    print(f"Overall Scaling Factors (n={len(books)}):")
    print(f"  eBay → AbeBooks min:")
    print(f"    Mean ratio:   {statistics.mean(ratios_to_min):.2f}x")
    print(f"    Median ratio: {statistics.median(ratios_to_min):.2f}x")
    print(f"    Std dev:      {statistics.stdev(ratios_to_min):.2f}")
    print(f"    Min/Max:      {min(ratios_to_min):.2f}x / {max(ratios_to_min):.2f}x")

    print(f"\n  eBay → AbeBooks avg:")
    print(f"    Mean ratio:   {statistics.mean(ratios_to_avg):.2f}x")
    print(f"    Median ratio: {statistics.median(ratios_to_avg):.2f}x")
    print(f"    Std dev:      {statistics.stdev(ratios_to_avg):.2f}")
    print(f"    Min/Max:      {min(ratios_to_avg):.2f}x / {max(ratios_to_avg):.2f}x")

    # Scaling by condition
    print(f"\n{'='*80}")
    print("SCALING FACTORS BY CONDITION")
    print(f"{'='*80}\n")

    by_condition = defaultdict(list)
    for book in books:
        cond = book['condition'] or 'Unknown'
        ratio = book['estimated_price'] / book['abebooks_min_price']
        by_condition[cond].append(ratio)

    for cond in sorted(by_condition.keys()):
        ratios = by_condition[cond]
        if len(ratios) >= 5:
            print(f"{cond:15s} (n={len(ratios):3d}): "
                  f"Mean={statistics.mean(ratios):5.2f}x  "
                  f"Median={statistics.median(ratios):5.2f}x  "
                  f"StdDev={statistics.stdev(ratios):4.2f}")

    # Scaling by binding
    print(f"\n{'='*80}")
    print("SCALING FACTORS BY BINDING")
    print(f"{'='*80}\n")

    by_binding = defaultdict(list)
    for book in books:
        binding = book['binding'] or 'Unknown'
        ratio = book['estimated_price'] / book['abebooks_min_price']
        by_binding[binding].append(ratio)

    for binding in sorted(by_binding.keys()):
        ratios = by_binding[binding]
        if len(ratios) >= 3:
            print(f"{binding:20s} (n={len(ratios):3d}): "
                  f"Mean={statistics.mean(ratios):5.2f}x  "
                  f"Median={statistics.median(ratios):5.2f}x  "
                  f"StdDev={statistics.stdev(ratios):4.2f}")

    # Scaling by price tier
    print(f"\n{'='*80}")
    print("SCALING FACTORS BY ABEBOOKS PRICE TIER")
    print(f"{'='*80}\n")

    price_tiers = {
        'Ultra-cheap ($0-2)': (0, 2),
        'Budget ($2-5)': (2, 5),
        'Mid-tier ($5-10)': (5, 10),
        'Premium ($10-20)': (10, 20),
        'High-end ($20+)': (20, 999),
    }

    for tier_name, (min_price, max_price) in price_tiers.items():
        tier_books = [b for b in books
                      if min_price <= b['abebooks_min_price'] < max_price]
        if tier_books:
            ratios = [b['estimated_price'] / b['abebooks_min_price']
                     for b in tier_books]
            print(f"{tier_name:25s} (n={len(tier_books):3d}): "
                  f"Mean={statistics.mean(ratios):5.2f}x  "
                  f"Median={statistics.median(ratios):5.2f}x  "
                  f"StdDev={statistics.stdev(ratios):4.2f}")

    # Scaling by seller competition
    print(f"\n{'='*80}")
    print("SCALING FACTORS BY ABEBOOKS SELLER COUNT")
    print(f"{'='*80}\n")

    competition_tiers = {
        'Low (1-20 sellers)': (1, 20),
        'Medium (21-60 sellers)': (21, 60),
        'High (61-100 sellers)': (61, 100),
        'Very high (100+ sellers)': (100, 999),
    }

    for tier_name, (min_count, max_count) in competition_tiers.items():
        tier_books = [b for b in books
                      if min_count <= b['abebooks_seller_count'] <= max_count]
        if tier_books:
            ratios = [b['estimated_price'] / b['abebooks_min_price']
                     for b in tier_books]
            print(f"{tier_name:30s} (n={len(tier_books):3d}): "
                  f"Mean={statistics.mean(ratios):5.2f}x  "
                  f"Median={statistics.median(ratios):5.2f}x  "
                  f"StdDev={statistics.stdev(ratios):4.2f}")

    # Scaling by special features
    print(f"\n{'='*80}")
    print("SCALING FACTORS BY SPECIAL FEATURES")
    print(f"{'='*80}\n")

    signed = [b['estimated_price'] / b['abebooks_min_price']
              for b in books if b['is_signed']]
    unsigned = [b['estimated_price'] / b['abebooks_min_price']
                for b in books if not b['is_signed']]

    if signed and len(signed) >= 2 and unsigned and len(unsigned) >= 2:
        print(f"Signed (n={len(signed):3d}):           "
              f"Mean={statistics.mean(signed):5.2f}x  "
              f"Median={statistics.median(signed):5.2f}x  "
              f"StdDev={statistics.stdev(signed):4.2f}")
        print(f"Unsigned (n={len(unsigned):3d}):         "
              f"Mean={statistics.mean(unsigned):5.2f}x  "
              f"Median={statistics.median(unsigned):5.2f}x  "
              f"StdDev={statistics.stdev(unsigned):4.2f}")
    elif signed or unsigned:
        print(f"Signed books: {len(signed)} (insufficient for comparison)")
        print(f"Unsigned books: {len(unsigned)}")

    first_ed = [b['estimated_price'] / b['abebooks_min_price']
                for b in books if b['is_first_edition']]
    not_first = [b['estimated_price'] / b['abebooks_min_price']
                 for b in books if not b['is_first_edition']]

    if first_ed and len(first_ed) >= 2 and not_first and len(not_first) >= 2:
        print(f"\nFirst Edition (n={len(first_ed):3d}):    "
              f"Mean={statistics.mean(first_ed):5.2f}x  "
              f"Median={statistics.median(first_ed):5.2f}x  "
              f"StdDev={statistics.stdev(first_ed):4.2f}")
        print(f"Not First (n={len(not_first):3d}):       "
              f"Mean={statistics.mean(not_first):5.2f}x  "
              f"Median={statistics.median(not_first):5.2f}x  "
              f"StdDev={statistics.stdev(not_first):4.2f}")

    return {
        'overall_mean': statistics.mean(ratios_to_min),
        'overall_median': statistics.median(ratios_to_min),
        'by_condition': by_condition,
        'by_binding': by_binding,
    }

def test_prediction_accuracy(books, scaling_factors):
    """Test how well scaling factors predict eBay prices from AbeBooks."""

    print(f"\n{'='*80}")
    print("PREDICTION ACCURACY TESTING")
    print(f"{'='*80}\n")

    # Test different scaling approaches
    approaches = {
        'Mean scaling (6.18x)': scaling_factors['overall_mean'],
        'Median scaling (5.00x)': scaling_factors['overall_median'],
        'Conservative (3.00x)': 3.0,
        'Moderate (4.00x)': 4.0,
        'Use AbeBooks avg (1.9x)': None,  # Special case
    }

    for approach_name, scale_factor in approaches.items():
        errors = []
        absolute_errors = []

        for book in books:
            actual_ebay = book['estimated_price']

            if scale_factor is None:
                # Use AbeBooks avg with 1.9x scaling
                predicted_ebay = book['abebooks_avg_price'] * 1.9
            else:
                predicted_ebay = book['abebooks_min_price'] * scale_factor

            error = predicted_ebay - actual_ebay
            errors.append(error)
            absolute_errors.append(abs(error))

        mae = statistics.mean(absolute_errors)
        rmse = (statistics.mean([e**2 for e in errors]))**0.5
        mean_error = statistics.mean(errors)

        # Calculate percentage within tolerance
        within_20pct = sum(1 for ae, b in zip(absolute_errors, books)
                          if ae / b['estimated_price'] <= 0.20) / len(books) * 100
        within_50pct = sum(1 for ae, b in zip(absolute_errors, books)
                          if ae / b['estimated_price'] <= 0.50) / len(books) * 100

        print(f"{approach_name:25s}:")
        print(f"  MAE:  ${mae:.2f}")
        print(f"  RMSE: ${rmse:.2f}")
        print(f"  Bias: ${mean_error:+.2f} ({'over' if mean_error > 0 else 'under'}estimation)")
        print(f"  Within 20%: {within_20pct:.1f}%")
        print(f"  Within 50%: {within_50pct:.1f}%")
        print()

def recommend_features(books, scaling_factors):
    """Recommend ML features based on scaling analysis."""

    print(f"\n{'='*80}")
    print("RECOMMENDED ML FEATURES FOR CROSS-PLATFORM SCALING")
    print(f"{'='*80}\n")

    print("1. PLATFORM RATIO FEATURES:")
    print("   - ebay_abebooks_min_ratio = estimated_price / abebooks_min_price")
    print("   - ebay_abebooks_avg_ratio = estimated_price / abebooks_avg_price")
    print("   - Helps model learn platform premiums")
    print()

    print("2. SCALED PRICE FEATURES:")
    print("   - abebooks_scaled_to_ebay = abebooks_min_price * 5.0  # Use median")
    print("   - abebooks_premium = estimated_price - abebooks_scaled_to_ebay")
    print("   - Helps model see collectibility signal")
    print()

    print("3. MARKET SEGMENT FEATURES:")
    print("   - is_collectible_market = (ebay_abebooks_min_ratio > 2.0)")
    print("   - is_commodity_market = (0.8 <= ebay_abebooks_min_ratio <= 1.2)")
    print("   - collectibility_score = ebay_abebooks_min_ratio / 2.0  # Normalized")
    print()

    print("4. COMPETITION-ADJUSTED SCALING:")
    print("   - High competition (60+ sellers): Scale by 3.5x")
    print("   - Medium competition (20-60): Scale by 5.0x")
    print("   - Low competition (1-20): Scale by 7.5x")
    print("   - abebooks_competitive_estimate = abebooks_min * competition_scale")
    print()

    print("5. PRICE TIER SCALING:")
    print("   - Ultra-cheap ($0-2): Scale by 8.5x (highest premium)")
    print("   - Budget ($2-5): Scale by 5.5x")
    print("   - Mid-tier ($5-10): Scale by 3.0x")
    print("   - Premium ($10+): Scale by 1.5x (prices converge)")
    print()

    print("6. FALLBACK ESTIMATION:")
    print("   - When eBay data missing: Use abebooks_avg_price * 2.0")
    print("   - When AbeBooks missing: Use ebay_price / 5.0 for floor estimate")
    print()

    # Calculate what % of predictions would be within 20% using best approach
    best_within_20 = 0
    best_approach = None

    # Test adaptive scaling by competition tier
    errors = []
    for book in books:
        actual = book['estimated_price']
        sellers = book['abebooks_seller_count']

        # Adaptive scaling by competition
        if sellers >= 60:
            scale = 3.5
        elif sellers >= 20:
            scale = 5.0
        else:
            scale = 7.5

        predicted = book['abebooks_min_price'] * scale
        error_pct = abs(predicted - actual) / actual
        errors.append(error_pct)

    within_20 = sum(1 for e in errors if e <= 0.20) / len(errors) * 100

    print(f"\n{'='*80}")
    print("ADAPTIVE SCALING PERFORMANCE")
    print(f"{'='*80}\n")
    print(f"Competition-aware scaling (3.5x-7.5x based on seller count):")
    print(f"  Predictions within 20%: {within_20:.1f}%")
    print(f"  Predictions within 50%: {sum(1 for e in errors if e <= 0.50) / len(errors) * 100:.1f}%")
    print()

def analyze_outliers(books):
    """Identify books where scaling breaks down."""

    print(f"\n{'='*80}")
    print("SCALING OUTLIERS (Where Simple Ratios Fail)")
    print(f"{'='*80}\n")

    # Calculate expected vs actual
    outliers = []
    for book in books:
        expected = book['abebooks_min_price'] * 5.0  # Use median scale
        actual = book['estimated_price']
        error_pct = abs(expected - actual) / actual

        if error_pct > 0.5:  # More than 50% error
            outliers.append((error_pct, expected, actual, book))

    outliers.sort(key=lambda x: x[0], reverse=True)

    print("Top 20 books where 5.0x scaling fails (>50% error):\n")
    print(f"{'Error':>6s} | {'Expected':>8s} | {'Actual':>7s} | {'AbeBooks':>8s} | {'Title':<45s}")
    print("-" * 100)

    for error_pct, expected, actual, book in outliers[:20]:
        title = book['title'][:42] + '...' if len(book['title']) > 45 else book['title']
        print(f"{error_pct*100:5.1f}% | ${expected:7.2f} | ${actual:6.2f} | "
              f"${book['abebooks_min_price']:7.2f} | {title:<45s}")

    print(f"\nTotal outliers (>50% error): {len(outliers)} out of {len(books)} "
          f"({len(outliers)/len(books)*100:.1f}%)")

if __name__ == "__main__":
    print(f"\n{'='*80}")
    print(f"CROSS-PLATFORM PRICE SCALING ANALYSIS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}")

    books = load_multi_platform_books()
    print(f"\nAnalyzing {len(books)} books with both eBay and AbeBooks data...")

    scaling_factors = calculate_scaling_factors(books)
    test_prediction_accuracy(books, scaling_factors)
    recommend_features(books, scaling_factors)
    analyze_outliers(books)

    print(f"\n{'='*80}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*80}\n")
