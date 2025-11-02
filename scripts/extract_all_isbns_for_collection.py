#!/usr/bin/env python3
"""
Extract all 19,249 ISBNs from metadata_cache.db and prioritize for AbeBooks collection.

Prioritization factors:
1. Quality score from metadata_cache.db
2. Amazon rank from training_data.db (if available)
3. Existing market data availability
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple
import json

def load_metadata_isbns() -> Dict[str, float]:
    """Load all ISBNs from metadata cache with quality scores."""
    cache_path = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"

    conn = sqlite3.connect(cache_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT isbn, quality_score, title
        FROM cached_books
        WHERE isbn IS NOT NULL
        ORDER BY quality_score DESC
    """)

    isbns = {}
    for isbn, quality_score, title in cursor.fetchall():
        isbns[isbn] = {
            'quality_score': quality_score or 0.0,
            'title': title or ''
        }

    conn.close()
    print(f"✓ Loaded {len(isbns)} ISBNs from metadata_cache.db")
    return isbns

def load_training_data() -> Dict[str, Dict]:
    """Load Amazon market data from catalog.db (primary) or training_data.db."""
    # Try catalog.db first (main database)
    catalog_path = Path("/Users/nickcuskey/ISBN/catalog.db")
    training_path = Path("/Users/nickcuskey/ISBN/training_data.db")

    db_path = None
    if catalog_path.exists() and catalog_path.stat().st_size > 0:
        db_path = catalog_path
    elif training_path.exists() and training_path.stat().st_size > 0:
        db_path = training_path

    if not db_path:
        print("! No training/catalog data found - using metadata only")
        return {}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check what columns exist
        cursor.execute("SELECT * FROM books LIMIT 0")
        columns = [description[0] for description in cursor.description]

        # Build query based on available columns
        select_fields = ['isbn']
        if 'amazon_rank' in columns:
            select_fields.append('amazon_rank')
        if 'amazon_reviews_count' in columns:
            select_fields.append('amazon_reviews_count')
        if 'amazon_rating' in columns:
            select_fields.append('amazon_rating')
        if 'sold_count' in columns:
            select_fields.append('sold_count')

        query = f"""
            SELECT {', '.join(select_fields)}
            FROM books
            WHERE isbn IS NOT NULL
        """

        cursor.execute(query)

        training_data = {}
        for row in cursor.fetchall():
            isbn = row[0]
            data = {}
            for i, field in enumerate(select_fields[1:], 1):  # Skip isbn
                data[field] = row[i]

            training_data[isbn] = data

        conn.close()
        print(f"✓ Loaded Amazon data for {len(training_data)} ISBNs from {db_path.name}")
        return training_data
    except Exception as e:
        print(f"! Error loading training data: {e}")
        return {}

def check_existing_abebooks_data(isbns: List[str]) -> Dict[str, bool]:
    """Check which ISBNs already have AbeBooks data collected."""
    catalog_path = Path("/Users/nickcuskey/ISBN/catalog.db")

    if not catalog_path.exists():
        return {}

    conn = sqlite3.connect(catalog_path)
    cursor = conn.cursor()

    # Check if abebooks fields exist
    cursor.execute("PRAGMA table_info(books)")
    columns = [col[1] for col in cursor.fetchall()]

    has_abebooks = any('abebooks' in col for col in columns)

    if not has_abebooks:
        conn.close()
        return {}

    # Check which ISBNs have AbeBooks data
    isbn_placeholders = ','.join('?' * len(isbns))
    cursor.execute(f"""
        SELECT isbn
        FROM books
        WHERE isbn IN ({isbn_placeholders})
        AND abebooks_min_price IS NOT NULL
    """, isbns)

    existing = {row[0]: True for row in cursor.fetchall()}
    conn.close()

    print(f"✓ Found {len(existing)} ISBNs with existing AbeBooks data")
    return existing

def calculate_priority_score(isbn: str, metadata: Dict, training: Dict, has_abebooks: bool) -> float:
    """
    Calculate priority score for an ISBN.

    Factors:
    - Quality score (0-1): Higher is better
    - Amazon rank: Lower is better (higher score)
    - Reviews count: More is better
    - Rating: Higher is better
    - No existing AbeBooks data: Preferred (collect new data first)
    """
    score = 0.0

    # Quality score (0-100 points)
    score += metadata.get('quality_score', 0.0) * 100

    # Amazon rank (0-200 points) - prioritize books with sales rank
    if training.get('amazon_rank'):
        rank = training['amazon_rank']
        # Top 1,000: 200 pts, Top 10k: 150 pts, Top 100k: 100 pts, etc.
        if rank <= 1000:
            score += 200
        elif rank <= 10000:
            score += 150
        elif rank <= 100000:
            score += 100
        elif rank <= 1000000:
            score += 50

    # Reviews count (0-50 points)
    reviews = training.get('amazon_reviews_count', 0)
    if reviews > 0:
        score += min(reviews / 100, 50)  # Cap at 50 points

    # Rating (0-25 points)
    rating = training.get('amazon_rating', 0.0)
    score += rating * 5  # 5-star = 25 points

    # Sold count (0-25 points)
    sold = training.get('sold_count', 0)
    if sold > 0:
        score += min(sold, 25)

    # Penalty for already having AbeBooks data (-100 points)
    # We want to collect new data first
    if has_abebooks:
        score -= 100

    return score

def prioritize_all_isbns(output_file: Path, limit: int = None):
    """Main function to prioritize all ISBNs."""
    print("\n" + "="*70)
    print("Extracting and Prioritizing ALL ISBNs for AbeBooks Collection")
    print("="*70 + "\n")

    # Load data from all sources
    metadata_isbns = load_metadata_isbns()
    training_data = load_training_data()

    # Check for existing AbeBooks data
    all_isbns = list(metadata_isbns.keys())
    existing_abebooks = check_existing_abebooks_data(all_isbns)

    print(f"\n{'='*70}")
    print("Calculating priority scores...")
    print("="*70 + "\n")

    # Calculate scores for all ISBNs
    isbn_scores = []
    for isbn in all_isbns:
        metadata = metadata_isbns[isbn]
        training = training_data.get(isbn, {})
        has_abebooks = existing_abebooks.get(isbn, False)

        score = calculate_priority_score(isbn, metadata, training, has_abebooks)

        isbn_scores.append({
            'isbn': isbn,
            'score': score,
            'title': metadata.get('title', '')[:50],  # Truncate for readability
            'quality': metadata.get('quality_score', 0.0),
            'amazon_rank': training.get('amazon_rank'),
            'has_abebooks': has_abebooks
        })

    # Sort by score (highest first)
    isbn_scores.sort(key=lambda x: x['score'], reverse=True)

    # Apply limit if specified
    if limit:
        isbn_scores = isbn_scores[:limit]

    # Write to output file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        for item in isbn_scores:
            f.write(f"{item['isbn']}\n")

    print(f"\n{'='*70}")
    print("PRIORITIZATION COMPLETE")
    print("="*70 + "\n")
    print(f"Total ISBNs extracted: {len(metadata_isbns)}")
    print(f"ISBNs with Amazon data: {len(training_data)}")
    print(f"ISBNs with existing AbeBooks data: {len(existing_abebooks)}")
    print(f"ISBNs prioritized: {len(isbn_scores)}")
    print(f"\nOutput file: {output_file}")

    # Show top 20
    print(f"\n{'='*70}")
    print("TOP 20 PRIORITIZED ISBNs")
    print("="*70)
    print(f"\n{'Rank':<6} {'ISBN':<15} {'Score':<8} {'Quality':<9} {'Rank':<12} {'Has AB':<8} {'Title':<30}")
    print("-" * 110)

    for i, item in enumerate(isbn_scores[:20], 1):
        rank_str = f"#{item['amazon_rank']:,}" if item['amazon_rank'] else "N/A"
        has_ab = "Yes" if item['has_abebooks'] else "No"
        print(f"{i:<6} {item['isbn']:<15} {item['score']:<8.1f} {item['quality']:<9.2f} {rank_str:<12} {has_ab:<8} {item['title']:<30}")

    # Show statistics
    with_amazon = sum(1 for x in isbn_scores if x['amazon_rank'])
    without_abebooks = sum(1 for x in isbn_scores if not x['has_abebooks'])

    print(f"\n{'='*70}")
    print("STATISTICS")
    print("="*70)
    print(f"ISBNs with Amazon rank data: {with_amazon:,} ({with_amazon*100/len(isbn_scores):.1f}%)")
    print(f"ISBNs without AbeBooks data: {without_abebooks:,} ({without_abebooks*100/len(isbn_scores):.1f}%)")
    print(f"ISBNs needing collection: {without_abebooks:,}")

    return isbn_scores

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Extract and prioritize all ISBNs for collection')
    parser.add_argument('--output', type=str, default='/tmp/prioritized_all_19k.txt',
                       help='Output file path')
    parser.add_argument('--limit', type=int, default=None,
                       help='Limit number of ISBNs (default: all)')

    args = parser.parse_args()

    output_path = Path(args.output)
    prioritize_all_isbns(output_path, args.limit)
