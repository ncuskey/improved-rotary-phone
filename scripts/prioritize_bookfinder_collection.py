#!/usr/bin/env python3
"""
Prioritize ISBNs for BookFinder collection.

Ranks ISBNs from metadata_cache that don't have BookFinder data yet,
prioritizing by quality indicators:
- Has sold listing data (proven market demand)
- Publication year (prefer recent and classic)
- Page count (prefer substantial books)
- Has rich metadata
- Price range (prefer mid-to-high value books)

Outputs tiered lists for phased collection:
- Tier 1: High-quality ISBNs (2,000) - Target first
- Tier 2: Medium-quality ISBNs (3,000) - Second wave
- Tier 3: Remaining ISBNs (rest) - Comprehensive coverage
"""

import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

# Add project to path
sys.path.insert(0, str(Path.home() / "ISBN"))


def calculate_priority_score(row: Tuple) -> float:
    """
    Calculate priority score for an ISBN based on quality indicators.

    Args:
        row: (isbn, pub_year, page_count, has_sold_data, avg_sold_price)

    Returns:
        Priority score (higher = higher priority)
    """
    isbn, pub_year, page_count, has_sold_data, avg_sold_price = row
    score = 0.0

    # Has sold listing data (proven market demand) - HUGE boost
    if has_sold_data:
        score += 50.0

        # Price range bonus (prefer mid-to-high value books for better learning signal)
        if avg_sold_price:
            if 15.0 <= avg_sold_price <= 50.0:
                score += 20.0  # Sweet spot
            elif 10.0 <= avg_sold_price < 15.0:
                score += 10.0  # Decent
            elif avg_sold_price >= 50.0:
                score += 15.0  # Collectible potential

    # Publication year (prefer recent and classics)
    if pub_year:
        if pub_year >= 2015:
            score += 15.0  # Recent books
        elif pub_year >= 2000:
            score += 10.0  # Modern books
        elif pub_year < 1980:
            score += 20.0  # Classic/collectible potential
        elif pub_year < 2000:
            score += 5.0  # Older but not classic
    else:
        score -= 10.0  # Missing pub year is bad signal

    # Page count (prefer substantial books, penalize very short books)
    if page_count:
        if 200 <= page_count <= 600:
            score += 10.0  # Standard novel range
        elif page_count > 600:
            score += 5.0   # Long books
        elif page_count < 100:
            score -= 5.0   # Pamphlets/chapbooks
    else:
        score -= 5.0  # Missing page count

    return score


def prioritize_isbns():
    """Main prioritization function."""
    print("=" * 80)
    print("ISBN Prioritization for BookFinder Collection")
    print("=" * 80)
    print()

    # Database paths
    cache_db = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"
    catalog_db = Path.home() / ".isbn_lot_optimizer" / "catalog.db"
    training_db = Path.home() / "ISBN" / "isbn_lot_optimizer" / "training_data.db"

    if not cache_db.exists():
        print(f"ERROR: metadata_cache.db not found at {cache_db}")
        return 1

    print("1. Finding ISBNs without BookFinder data...")

    # Get ISBNs that have metadata but NO BookFinder data
    cache_conn = sqlite3.connect(cache_db)
    catalog_conn = sqlite3.connect(catalog_db) if catalog_db.exists() else None
    training_conn = sqlite3.connect(training_db) if training_db.exists() else None

    cache_cursor = cache_conn.cursor()

    # Get all ISBNs from metadata_cache
    cache_cursor.execute("""
        SELECT isbn, publication_year, page_count
        FROM cached_books
        WHERE isbn IS NOT NULL
    """)
    all_metadata = {row[0]: (row[1], row[2]) for row in cache_cursor.fetchall()}
    print(f"   Found {len(all_metadata):,} total ISBNs in metadata_cache")

    # Get ISBNs that already have BookFinder data
    existing_bf_isbns = set()
    if catalog_conn:
        catalog_cursor = catalog_conn.cursor()
        catalog_cursor.execute("SELECT DISTINCT isbn FROM bookfinder_offers")
        existing_bf_isbns = {row[0] for row in catalog_cursor.fetchall()}
        print(f"   Found {len(existing_bf_isbns):,} ISBNs with existing BookFinder data")
        catalog_conn.close()

    # ISBNs needing BookFinder data
    isbns_needing_bf = set(all_metadata.keys()) - existing_bf_isbns
    print(f"   Need to collect {len(isbns_needing_bf):,} ISBNs")
    print()

    print("2. Enriching with quality indicators...")

    # Get sold listing data for quality scoring
    sold_data = {}
    if training_conn:
        training_cursor = training_conn.cursor()
        training_cursor.execute("""
            SELECT isbn, AVG(price) as avg_price
            FROM sold_listings
            WHERE isbn IS NOT NULL
            GROUP BY isbn
        """)
        sold_data = {row[0]: row[1] for row in training_cursor.fetchall()}
        print(f"   Found {len(sold_data):,} ISBNs with sold listing data")
        training_conn.close()

    print()
    print("3. Calculating priority scores...")

    # Build scoring data
    scoring_data = []
    for isbn in isbns_needing_bf:
        pub_year, page_count = all_metadata.get(isbn, (None, None))
        has_sold_data = isbn in sold_data
        avg_sold_price = sold_data.get(isbn)

        row = (isbn, pub_year, page_count, has_sold_data, avg_sold_price)
        score = calculate_priority_score(row)
        scoring_data.append((isbn, score, pub_year, page_count, has_sold_data, avg_sold_price))

    # Sort by score (highest first)
    scoring_data.sort(key=lambda x: x[1], reverse=True)

    print(f"   Scored {len(scoring_data):,} ISBNs")
    print()

    # Show score distribution
    scores = [x[1] for x in scoring_data]
    print("Score Distribution:")
    print(f"   Max score:    {max(scores):.1f}")
    print(f"   75th %ile:    {sorted(scores)[int(len(scores) * 0.75)]:.1f}")
    print(f"   Median:       {sorted(scores)[len(scores) // 2]:.1f}")
    print(f"   25th %ile:    {sorted(scores)[int(len(scores) * 0.25)]:.1f}")
    print(f"   Min score:    {min(scores):.1f}")
    print()

    # Split into tiers
    tier1_size = 2000
    tier2_size = 3000

    tier1_isbns = scoring_data[:tier1_size]
    tier2_isbns = scoring_data[tier1_size:tier1_size + tier2_size]
    tier3_isbns = scoring_data[tier1_size + tier2_size:]

    print("4. Tier breakdown:")
    print(f"   Tier 1 (High-quality):   {len(tier1_isbns):,} ISBNs")
    print(f"      Avg score: {sum(x[1] for x in tier1_isbns) / len(tier1_isbns):.1f}")
    print(f"      With sold data: {sum(1 for x in tier1_isbns if x[4]):,} ({sum(1 for x in tier1_isbns if x[4]) / len(tier1_isbns) * 100:.1f}%)")
    print()
    print(f"   Tier 2 (Medium-quality): {len(tier2_isbns):,} ISBNs")
    print(f"      Avg score: {sum(x[1] for x in tier2_isbns) / len(tier2_isbns):.1f}")
    print(f"      With sold data: {sum(1 for x in tier2_isbns if x[4]):,} ({sum(1 for x in tier2_isbns if x[4]) / len(tier2_isbns) * 100:.1f}%)")
    print()
    print(f"   Tier 3 (Remaining):      {len(tier3_isbns):,} ISBNs")
    print(f"      Avg score: {sum(x[1] for x in tier3_isbns) / len(tier3_isbns):.1f}")
    print(f"      With sold data: {sum(1 for x in tier3_isbns if x[4]):,} ({sum(1 for x in tier3_isbns if x[4]) / len(tier3_isbns) * 100:.1f}%)")
    print()

    # Export tier lists
    output_dir = Path("/tmp")

    tier1_file = output_dir / "bookfinder_tier1_isbns.txt"
    tier2_file = output_dir / "bookfinder_tier2_isbns.txt"
    tier3_file = output_dir / "bookfinder_tier3_isbns.txt"

    print("5. Exporting tier lists...")

    with open(tier1_file, "w") as f:
        for isbn, score, pub_year, page_count, has_sold, avg_price in tier1_isbns:
            f.write(f"{isbn}\n")
    print(f"   Tier 1: {tier1_file}")

    with open(tier2_file, "w") as f:
        for isbn, score, pub_year, page_count, has_sold, avg_price in tier2_isbns:
            f.write(f"{isbn}\n")
    print(f"   Tier 2: {tier2_file}")

    with open(tier3_file, "w") as f:
        for isbn, score, pub_year, page_count, has_sold, avg_price in tier3_isbns:
            f.write(f"{isbn}\n")
    print(f"   Tier 3: {tier3_file}")
    print()

    # Export detailed CSV for analysis
    detail_file = output_dir / "bookfinder_priority_details.csv"
    with open(detail_file, "w") as f:
        f.write("isbn,tier,score,pub_year,page_count,has_sold_data,avg_sold_price\n")
        for isbn, score, pub_year, page_count, has_sold, avg_price in tier1_isbns:
            f.write(f"{isbn},1,{score:.1f},{pub_year or ''},{page_count or ''},{int(has_sold)},{avg_price or ''}\n")
        for isbn, score, pub_year, page_count, has_sold, avg_price in tier2_isbns:
            f.write(f"{isbn},2,{score:.1f},{pub_year or ''},{page_count or ''},{int(has_sold)},{avg_price or ''}\n")
        for isbn, score, pub_year, page_count, has_sold, avg_price in tier3_isbns:
            f.write(f"{isbn},3,{score:.1f},{pub_year or ''},{page_count or ''},{int(has_sold)},{avg_price or ''}\n")
    print(f"   Detail CSV: {detail_file}")
    print()

    # Show top 10 ISBNs in Tier 1
    print("Top 10 Tier 1 ISBNs (highest priority):")
    for i, (isbn, score, pub_year, page_count, has_sold, avg_price) in enumerate(tier1_isbns[:10], 1):
        sold_str = f"${avg_price:.2f} avg" if avg_price else "no sold data"
        print(f"   {i:2d}. {isbn} | Score: {score:.1f} | {pub_year or 'no year'} | {page_count or 'no pages'} pgs | {sold_str}")
    print()

    print("=" * 80)
    print("Prioritization Complete!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Start Tier 1 collection:")
    print(f"   ./.venv/bin/python3 scripts/collect_bookfinder_prices.py --isbn-file {tier1_file}")
    print()
    print("2. Enrich Tier 1 metadata (if needed):")
    print(f"   ./.venv/bin/python3 scripts/enrich_metadata_from_decodo.py --isbn-file {tier1_file}")
    print()
    print("3. Retrain model after Tier 1 completion:")
    print("   ./.venv/bin/python3.11 scripts/train_edition_premium_model.py")
    print()

    cache_conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(prioritize_isbns())
