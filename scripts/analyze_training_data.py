"""
Analyze ML training data quality to identify issues.

Checks for:
- Target price distribution and outliers
- Feature completeness by feature
- Correlation between features and target
- Data quality issues
"""

import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np


def load_training_data(db_path: Path) -> List[dict]:
    """Load training data from database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            isbn,
            sold_comps_median,
            json_extract(bookscouter_json, '$.amazon_lowest_price') as amazon_price,
            metadata_json,
            market_json,
            bookscouter_json
        FROM books
        WHERE bookscouter_json IS NOT NULL
        AND json_extract(bookscouter_json, '$.amazon_lowest_price') IS NOT NULL
        AND CAST(json_extract(bookscouter_json, '$.amazon_lowest_price') AS REAL) > 0
    """)

    records = []
    for row in cursor.fetchall():
        isbn, sold_median, amazon_price, metadata_json, market_json, bookscouter_json = row

        metadata = json.loads(metadata_json) if metadata_json else {}
        market = json.loads(market_json) if market_json else {}
        bookscouter = json.loads(bookscouter_json) if bookscouter_json else {}

        # Calculate target (same as training script)
        if sold_median and sold_median > 0:
            target = sold_median * 0.6 + amazon_price * 0.7 * 0.4
        else:
            target = amazon_price * 0.7

        records.append({
            'isbn': isbn,
            'target': target,
            'sold_median': sold_median,
            'amazon_price': amazon_price,
            'metadata': metadata,
            'market': market,
            'bookscouter': bookscouter
        })

    conn.close()
    return records


def analyze_target_distribution(records: List[dict]):
    """Analyze target price distribution."""
    targets = [r['target'] for r in records]

    print("\n" + "=" * 70)
    print("TARGET PRICE DISTRIBUTION")
    print("=" * 70)

    print(f"\nTotal samples: {len(targets)}")
    print(f"Min:     ${min(targets):.2f}")
    print(f"Max:     ${max(targets):.2f}")
    print(f"Mean:    ${np.mean(targets):.2f}")
    print(f"Median:  ${np.median(targets):.2f}")
    print(f"Std Dev: ${np.std(targets):.2f}")

    # Percentiles
    print(f"\nPercentiles:")
    for p in [10, 25, 50, 75, 90, 95, 99]:
        print(f"  {p}th: ${np.percentile(targets, p):.2f}")

    # Outliers (IQR method)
    q1, q3 = np.percentile(targets, [25, 75])
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    outliers = [t for t in targets if t < lower_bound or t > upper_bound]

    print(f"\nOutliers (IQR method):")
    print(f"  IQR: ${iqr:.2f}")
    print(f"  Bounds: [${lower_bound:.2f}, ${upper_bound:.2f}]")
    print(f"  Outlier count: {len(outliers)} ({len(outliers)/len(targets)*100:.1f}%)")

    if outliers:
        print(f"  Outlier range: ${min(outliers):.2f} - ${max(outliers):.2f}")


def analyze_feature_completeness(records: List[dict]):
    """Analyze feature completeness by feature."""
    print("\n" + "=" * 70)
    print("FEATURE COMPLETENESS ANALYSIS")
    print("=" * 70)

    # Amazon features (bookscouter)
    amazon_rank_count = sum(1 for r in records if r['bookscouter'].get('amazon_sales_rank'))
    amazon_count_count = sum(1 for r in records if r['bookscouter'].get('amazon_count'))
    amazon_price_count = sum(1 for r in records if r['bookscouter'].get('amazon_lowest_price'))

    # Metadata features
    page_count_count = sum(1 for r in records if r['metadata'].get('page_count'))
    rating_count = sum(1 for r in records if r['metadata'].get('average_rating'))
    reviews_count = sum(1 for r in records if r['metadata'].get('ratings_count'))
    pub_year_count = sum(1 for r in records if r['metadata'].get('published_year'))

    total = len(records)

    print(f"\nTotal records: {total}\n")
    print(f"Amazon Features:")
    print(f"  Sales Rank:     {amazon_rank_count:4d} ({amazon_rank_count/total*100:5.1f}%)")
    print(f"  Seller Count:   {amazon_count_count:4d} ({amazon_count_count/total*100:5.1f}%)")
    print(f"  Lowest Price:   {amazon_price_count:4d} ({amazon_price_count/total*100:5.1f}%)")

    print(f"\nMetadata Features:")
    print(f"  Page Count:     {page_count_count:4d} ({page_count_count/total*100:5.1f}%)")
    print(f"  Rating:         {rating_count:4d} ({rating_count/total*100:5.1f}%)")
    print(f"  Reviews Count:  {reviews_count:4d} ({reviews_count/total*100:5.1f}%)")
    print(f"  Pub Year:       {pub_year_count:4d} ({pub_year_count/total*100:5.1f}%)")

    # Overall completeness
    completeness_scores = []
    for r in records:
        present = 0
        total_features = 7

        if r['bookscouter'].get('amazon_sales_rank'):
            present += 1
        if r['bookscouter'].get('amazon_count'):
            present += 1
        if r['bookscouter'].get('amazon_lowest_price'):
            present += 1
        if r['metadata'].get('page_count'):
            present += 1
        if r['metadata'].get('average_rating'):
            present += 1
        if r['metadata'].get('ratings_count'):
            present += 1
        if r['metadata'].get('published_year'):
            present += 1

        completeness_scores.append(present / total_features)

    print(f"\nOverall Feature Completeness:")
    print(f"  Average: {np.mean(completeness_scores)*100:.1f}%")
    print(f"  Median:  {np.median(completeness_scores)*100:.1f}%")
    print(f"  Min:     {min(completeness_scores)*100:.1f}%")
    print(f"  Max:     {max(completeness_scores)*100:.1f}%")


def analyze_target_correlations(records: List[dict]):
    """Analyze correlation between features and target."""
    print("\n" + "=" * 70)
    print("FEATURE-TARGET CORRELATIONS")
    print("=" * 70)

    targets = np.array([r['target'] for r in records])

    # Amazon rank
    ranks = []
    rank_targets = []
    for r in records:
        if r['bookscouter'].get('amazon_sales_rank'):
            ranks.append(math.log1p(r['bookscouter']['amazon_sales_rank']))
            rank_targets.append(r['target'])

    if ranks:
        corr = np.corrcoef(ranks, rank_targets)[0, 1]
        print(f"\nlog_amazon_rank: {corr:+.3f} (n={len(ranks)})")

    # Page count
    pages = []
    page_targets = []
    for r in records:
        if r['metadata'].get('page_count'):
            pages.append(r['metadata']['page_count'])
            page_targets.append(r['target'])

    if pages:
        corr = np.corrcoef(pages, page_targets)[0, 1]
        print(f"page_count:      {corr:+.3f} (n={len(pages)})")

    # Rating
    ratings = []
    rating_targets = []
    for r in records:
        if r['metadata'].get('average_rating'):
            ratings.append(r['metadata']['average_rating'])
            rating_targets.append(r['target'])

    if ratings:
        corr = np.corrcoef(ratings, rating_targets)[0, 1]
        print(f"rating:          {corr:+.3f} (n={len(ratings)})")

    # Reviews
    reviews = []
    review_targets = []
    for r in records:
        if r['metadata'].get('ratings_count'):
            reviews.append(math.log1p(r['metadata']['ratings_count']))
            review_targets.append(r['target'])

    if reviews:
        corr = np.corrcoef(reviews, review_targets)[0, 1]
        print(f"log_reviews:     {corr:+.3f} (n={len(reviews)})")


def analyze_price_sources(records: List[dict]):
    """Analyze breakdown of price sources."""
    print("\n" + "=" * 70)
    print("PRICE SOURCE ANALYSIS")
    print("=" * 70)

    ebay_only = sum(1 for r in records if r['sold_median'] and not r.get('amazon_price'))
    amazon_only = sum(1 for r in records if not r['sold_median'] and r.get('amazon_price'))
    both = sum(1 for r in records if r['sold_median'] and r.get('amazon_price'))

    print(f"\nPrice Sources:")
    print(f"  eBay only:   {ebay_only:4d} ({ebay_only/len(records)*100:5.1f}%)")
    print(f"  Amazon only: {amazon_only:4d} ({amazon_only/len(records)*100:5.1f}%)")
    print(f"  Both:        {both:4d} ({both/len(records)*100:5.1f}%)")

    # Analyze blending effect
    print(f"\nBlended Target Analysis (for books with both sources):")
    if both > 0:
        blended_records = [r for r in records if r['sold_median'] and r.get('amazon_price')]

        ebay_component = [r['sold_median'] * 0.6 for r in blended_records]
        amazon_component = [r['amazon_price'] * 0.7 * 0.4 for r in blended_records]

        print(f"  eBay component (60%):   Mean ${np.mean(ebay_component):.2f}")
        print(f"  Amazon component (40%): Mean ${np.mean(amazon_component):.2f}")

        # Check disagreement
        disagreements = []
        for r in blended_records:
            ratio = r['sold_median'] / r['amazon_price'] if r['amazon_price'] > 0 else 0
            if ratio < 0.5 or ratio > 2.0:
                disagreements.append(r)

        if disagreements:
            print(f"\n  High disagreement (2x+ difference): {len(disagreements)} books ({len(disagreements)/both*100:.1f}%)")


def main():
    """Main entry point."""
    db_path = Path.home() / ".isbn_lot_optimizer" / "catalog.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    print("=" * 70)
    print("ML TRAINING DATA ANALYSIS")
    print("=" * 70)

    print("\nLoading training data...")
    records = load_training_data(db_path)
    print(f"Loaded {len(records)} training samples")

    analyze_target_distribution(records)
    analyze_feature_completeness(records)
    analyze_target_correlations(records)
    analyze_price_sources(records)

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
