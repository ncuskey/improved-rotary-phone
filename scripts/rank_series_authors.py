#!/usr/bin/env python3
"""
Rank authors from series database to identify candidates for famous_people.json.

Ranks authors based on:
1. Number of series they've written
2. Average books per series
3. Total book count across all series
4. Presence in existing famous_people.json

Helps identify prolific/popular authors who may be collectible.
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict


def load_famous_people() -> Dict[str, Dict]:
    """Load existing famous_people.json."""
    famous_path = Path.home() / "ISBN" / "shared" / "famous_people.json"
    try:
        with open(famous_path, 'r') as f:
            data = json.load(f)

        # Flatten the categorized structure
        famous = {}
        for category, people in data.items():
            if category.startswith('_') or category == 'name_variations':
                continue
            for name, person_data in people.items():
                famous[name.lower()] = person_data

        return famous
    except Exception as e:
        print(f"Warning: Could not load famous_people.json: {e}")
        return {}


def get_series_authors(db_path: Path) -> List[Dict[str, Any]]:
    """Get all authors with their series statistics."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    query = """
    SELECT
        a.name,
        a.name_normalized,
        COUNT(DISTINCT s.id) as series_count,
        SUM(s.book_count) as total_books,
        AVG(s.book_count) as avg_books_per_series,
        MAX(s.book_count) as longest_series
    FROM authors a
    LEFT JOIN series s ON a.id = s.author_id
    GROUP BY a.id, a.name
    HAVING series_count > 0
    ORDER BY series_count DESC, total_books DESC
    """

    cursor = conn.execute(query)
    authors = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return authors


def calculate_fame_score(author: Dict[str, Any]) -> float:
    """
    Calculate a fame/popularity score for ranking.

    Higher scores indicate more prolific/popular authors.

    Factors:
    - Number of series (weight: 10)
    - Total books (weight: 1)
    - Longest series (weight: 2)
    - Average books per series (weight: 3)
    """
    series_count = author.get('series_count', 0)
    total_books = author.get('total_books', 0) or 0
    longest_series = author.get('longest_series', 0) or 0
    avg_books = author.get('avg_books_per_series', 0) or 0

    score = (
        (series_count * 10) +      # Multiple series = prolific
        (total_books * 1) +         # Total output
        (longest_series * 2) +      # Long-running series = popular
        (avg_books * 3)             # Consistent series = established
    )

    return score


def rank_authors(db_path: Path) -> List[Dict[str, Any]]:
    """Rank all series authors by collectibility potential."""
    print("Loading series authors from database...")
    authors = get_series_authors(db_path)

    print(f"Found {len(authors)} authors with series")

    print("Loading existing famous_people.json...")
    famous_people = load_famous_people()

    print(f"Found {len(famous_people)} existing famous people")

    # Calculate scores and check if already famous
    for author in authors:
        author['fame_score'] = calculate_fame_score(author)
        author['in_famous_db'] = author['name'].lower() in famous_people

        if author['in_famous_db']:
            author['famous_data'] = famous_people[author['name'].lower()]
        else:
            author['famous_data'] = None

    # Sort by fame score
    authors.sort(key=lambda x: x['fame_score'], reverse=True)

    return authors


def print_top_authors(authors: List[Dict[str, Any]], limit: int = 50):
    """Print the top N authors."""
    print("\n" + "=" * 100)
    print(f"TOP {limit} PROLIFIC AUTHORS (by fame score)")
    print("=" * 100)
    print(f"{'Rank':<6} {'Author':<35} {'Series':<8} {'Books':<8} {'Avg/S':<8} {'Longest':<8} {'Score':<10} {'Famous?':<10}")
    print("-" * 100)

    for i, author in enumerate(authors[:limit], 1):
        name = author['name'][:33]
        series_count = author['series_count']
        total_books = int(author['total_books']) if author['total_books'] else 0
        avg_books = f"{author['avg_books_per_series']:.1f}" if author['avg_books_per_series'] else "0.0"
        longest = author['longest_series'] or 0
        score = f"{author['fame_score']:.0f}"
        in_db = "✓" if author['in_famous_db'] else ""

        print(f"{i:<6} {name:<35} {series_count:<8} {total_books:<8} {avg_books:<8} {longest:<8} {score:<10} {in_db:<10}")


def print_genre_analysis(authors: List[Dict[str, Any]]):
    """Analyze which genres/categories are most represented."""
    print("\n" + "=" * 100)
    print("AUTHORS NOT YET IN FAMOUS DATABASE")
    print("=" * 100)

    not_famous = [a for a in authors if not a['in_famous_db']]

    print(f"\nTop 30 candidates to add to famous_people.json:")
    print("-" * 100)
    print(f"{'Rank':<6} {'Author':<40} {'Series':<8} {'Books':<8} {'Score':<10}")
    print("-" * 100)

    for i, author in enumerate(not_famous[:30], 1):
        name = author['name'][:38]
        series_count = author['series_count']
        total_books = int(author['total_books']) if author['total_books'] else 0
        score = f"{author['fame_score']:.0f}"

        print(f"{i:<6} {name:<40} {series_count:<8} {total_books:<8} {score:<10}")


def generate_candidates_json(authors: List[Dict[str, Any]], output_path: Path):
    """Generate JSON file with candidates to add to famous_people.json."""
    not_famous = [a for a in authors if not a['in_famous_db']]

    # Take top 50 candidates
    candidates = []
    for author in not_famous[:50]:
        candidate = {
            "name": author['name'],
            "series_count": author['series_count'],
            "total_books": int(author['total_books']) if author['total_books'] else 0,
            "avg_books_per_series": round(author['avg_books_per_series'], 1) if author['avg_books_per_series'] else 0,
            "longest_series": author['longest_series'] or 0,
            "fame_score": round(author['fame_score'], 1),
            "suggested_tier": suggest_tier(author),
            "notes": generate_notes(author)
        }
        candidates.append(candidate)

    output_data = {
        "_metadata": {
            "generated_at": "2025-11-15",
            "total_candidates": len(candidates),
            "source": "series_database.db authors table",
            "ranking_criteria": "series_count, total_books, longest_series, avg_books_per_series"
        },
        "candidates": candidates
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✓ Saved {len(candidates)} candidates to {output_path}")


def suggest_tier(author: Dict[str, Any]) -> str:
    """Suggest a fame tier based on statistics."""
    series_count = author['series_count']
    total_books = author['total_books'] or 0
    longest = author['longest_series'] or 0

    # Very prolific = bestselling_author tier
    if series_count >= 5 or total_books >= 30 or longest >= 15:
        return "bestselling_author"

    # Established series writer
    elif series_count >= 3 or total_books >= 15:
        return "established_series_author"

    # Has significant series
    else:
        return "series_author"


def generate_notes(author: Dict[str, Any]) -> str:
    """Generate notes about the author."""
    series_count = author['series_count']
    total_books = author['total_books'] or 0
    longest = author['longest_series'] or 0

    notes = []

    if series_count >= 5:
        notes.append(f"Prolific: {series_count} series")

    if total_books >= 30:
        notes.append(f"High output: {total_books} books")

    if longest >= 15:
        notes.append(f"Long-running series: {longest} books")

    if not notes:
        notes.append(f"{series_count} series, {total_books} books")

    return ", ".join(notes)


def main():
    """Main execution."""
    db_path = Path.home() / ".isbn_lot_optimizer" / "catalog.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return

    print(f"Analyzing authors from: {db_path}")
    print()

    authors = rank_authors(db_path)

    # Print top authors
    print_top_authors(authors, limit=50)

    # Print candidates not yet in famous database
    print_genre_analysis(authors)

    # Generate JSON file with candidates
    output_path = Path.home() / "ISBN" / "famous_author_candidates.json"
    generate_candidates_json(authors, output_path)

    # Statistics
    print("\n" + "=" * 100)
    print("STATISTICS")
    print("=" * 100)
    total_authors = len(authors)
    in_famous = len([a for a in authors if a['in_famous_db']])
    not_in_famous = total_authors - in_famous

    print(f"Total series authors: {total_authors}")
    print(f"Already in famous_people.json: {in_famous} ({in_famous/total_authors*100:.1f}%)")
    print(f"Not yet in famous_people.json: {not_in_famous} ({not_in_famous/total_authors*100:.1f}%)")
    print()
    print(f"Suggested next steps:")
    print(f"1. Review famous_author_candidates.json")
    print(f"2. Research top candidates (Wikipedia, Goodreads, awards)")
    print(f"3. Add high-profile authors to famous_people.json with appropriate multipliers")
    print(f"4. Focus on genres with collectible markets: sci-fi, fantasy, horror, mystery")


if __name__ == "__main__":
    main()
