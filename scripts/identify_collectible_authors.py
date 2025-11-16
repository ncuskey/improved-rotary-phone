#!/usr/bin/env python3
"""
Identify collectible authors from candidates based on genre, awards, and market signals.

Focuses on authors whose first editions or signed books would have collector value.
"""

import json
from pathlib import Path
from typing import List, Dict, Any


# Known collectible genres/categories
COLLECTIBLE_GENRES = {
    "horror": ["R.L. Stine", "Joe Lansdale", "Jonathan Maberry", "Anne Rice"],
    "sci-fi": ["Isaac Asimov", "Ursula K. Le Guin", "Andre Norton", "Alan Dean Foster",
               "Charles Stross", "Seanan McGuire", "Eric Flint", "Ben Aaronovitch"],
    "fantasy": ["Neil Gaiman", "Mercedes Lackey", "Barbara Hambly", "Kelley Armstrong",
                "Douglas Adams", "Tui T Sutherland"],
    "mystery": ["Lee Child", "Jeffery Deaver", "Lawrence Block", "Rhys Bowen", "Blake Pierce"],
    "romance": ["Nora Roberts", "Jayne Ann Krentz", "Susan Mallery", "Diana Palmer",
                "Debbie Macomber", "Heather Graham", "Lisa Jackson", "Sherryl Woods"],
    "children": ["Enid Blyton", "Tui T Sutherland", "Eve Bunting"],
    "thriller": ["James Patterson", "Gayle Lynds", "David Hagberg", "Paul Finch"],
}

# Known award winners or nominees
AWARD_WINNERS = {
    "Isaac Asimov": ["Hugo", "Nebula", "Locus"],
    "Ursula K. Le Guin": ["Hugo", "Nebula", "National Book Award"],
    "Neil Gaiman": ["Hugo", "Nebula", "Newbery", "Carnegie"],
    "Ray Bradbury": ["Hugo", "Nebula", "National Medal of Arts"],
    "Douglas Adams": ["Cult following", "British cultural icon"],
    "Anne Rice": ["Literary icon", "Gothic horror pioneer"],
    "Nora Roberts": ["RITA Awards", "Quill Awards"],
    "Lee Child": ["Thriller Award", "International bestseller"],
    "Stephen King": ["Bram Stoker", "World Fantasy", "National Medal of Arts"],
}

# Suggest collectibility multipliers
def suggest_multiplier(author: Dict[str, Any]) -> Dict[str, Any]:
    """
    Suggest signed and first edition multipliers for an author.

    Returns:
        {
            "signed_multiplier": float,
            "first_edition_multiplier": float,
            "reasoning": str
        }
    """
    name = author['name']
    series_count = author.get('series_count', 0)
    total_books = author.get('total_books', 0)

    # Default multipliers for unknown authors
    signed_mult = 3.0
    first_ed_mult = 1.5
    reasoning = "Established series author"

    # Check if in collectible genres
    is_collectible_genre = False
    genre = None
    for g, authors in COLLECTIBLE_GENRES.items():
        if name in authors:
            is_collectible_genre = True
            genre = g
            break

    # Check if award winner
    has_awards = name in AWARD_WINNERS

    # Calculate multipliers
    if has_awards and is_collectible_genre:
        # Award winner in collectible genre = highly collectible
        signed_mult = 25.0
        first_ed_mult = 6.0
        reasoning = f"Award winner in {genre}, highly collectible"

    elif has_awards:
        # Award winner
        signed_mult = 15.0
        first_ed_mult = 4.0
        reasoning = "Award-winning author"

    elif is_collectible_genre and total_books >= 50:
        # Prolific in collectible genre
        signed_mult = 12.0
        first_ed_mult = 3.0
        reasoning = f"Prolific {genre} author"

    elif is_collectible_genre:
        # Collectible genre
        signed_mult = 8.0
        first_ed_mult = 2.5
        reasoning = f"Established {genre} author"

    elif total_books >= 100:
        # Very prolific (may have dedicated fanbase)
        signed_mult = 6.0
        first_ed_mult = 2.0
        reasoning = "Very prolific, likely has collector following"

    elif series_count >= 10:
        # Multiple series (established author)
        signed_mult = 5.0
        first_ed_mult = 2.0
        reasoning = "Multiple series, established author"

    return {
        "signed_multiplier": signed_mult,
        "first_edition_multiplier": first_ed_mult,
        "reasoning": reasoning,
        "genre": genre,
        "awards": AWARD_WINNERS.get(name, [])
    }


def categorize_authors(candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
    """Categorize authors by collectibility level."""

    categories = {
        "high_priority": [],  # Award winners, genre icons (15x+)
        "medium_priority": [],  # Collectible genres, prolific (8x-15x)
        "low_priority": [],  # Established but less collectible (3x-8x)
    }

    for author in candidates:
        collectibility = suggest_multiplier(author)
        author_entry = {**author, **collectibility}

        signed_mult = collectibility['signed_multiplier']

        if signed_mult >= 15.0:
            categories['high_priority'].append(author_entry)
        elif signed_mult >= 8.0:
            categories['medium_priority'].append(author_entry)
        else:
            categories['low_priority'].append(author_entry)

    return categories


def main():
    """Main execution."""
    candidates_path = Path.home() / "ISBN" / "famous_author_candidates.json"

    if not candidates_path.exists():
        print(f"Error: {candidates_path} not found")
        print("Run rank_series_authors.py first")
        return

    with open(candidates_path, 'r') as f:
        data = json.load(f)

    candidates = data['candidates']

    print("Categorizing authors by collectibility...")
    categories = categorize_authors(candidates)

    # Print high priority authors
    print("\n" + "=" * 100)
    print("HIGH PRIORITY - HIGHLY COLLECTIBLE AUTHORS (Award Winners, Genre Icons)")
    print("=" * 100)
    print(f"{'Author':<35} {'Signed':<8} {'FirstEd':<8} {'Reasoning':<45}")
    print("-" * 100)

    for author in categories['high_priority']:
        name = author['name'][:33]
        signed = f"{author['signed_multiplier']:.0f}x"
        first_ed = f"{author['first_edition_multiplier']:.1f}x"
        reasoning = author['reasoning'][:43]
        print(f"{name:<35} {signed:<8} {first_ed:<8} {reasoning:<45}")

    print(f"\nTotal: {len(categories['high_priority'])} authors")

    # Print medium priority authors
    print("\n" + "=" * 100)
    print("MEDIUM PRIORITY - COLLECTIBLE GENRE AUTHORS")
    print("=" * 100)
    print(f"{'Author':<35} {'Signed':<8} {'FirstEd':<8} {'Genre':<15} {'Books':<8}")
    print("-" * 100)

    for author in categories['medium_priority'][:20]:
        name = author['name'][:33]
        signed = f"{author['signed_multiplier']:.0f}x"
        first_ed = f"{author['first_edition_multiplier']:.1f}x"
        genre = (author.get('genre') or 'N/A')[:13]
        books = author['total_books']
        print(f"{name:<35} {signed:<8} {first_ed:<8} {genre:<15} {books:<8}")

    print(f"\nTotal: {len(categories['medium_priority'])} authors (showing top 20)")

    # Generate enriched JSON
    output_path = Path.home() / "ISBN" / "collectible_authors_enriched.json"
    output_data = {
        "_metadata": {
            "generated_at": "2025-11-15",
            "total_candidates": len(candidates),
            "high_priority": len(categories['high_priority']),
            "medium_priority": len(categories['medium_priority']),
            "low_priority": len(categories['low_priority']),
        },
        "high_priority": categories['high_priority'],
        "medium_priority": categories['medium_priority'],
        "low_priority": categories['low_priority']
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✓ Saved enriched candidates to {output_path}")

    # Print summary
    print("\n" + "=" * 100)
    print("RECOMMENDATIONS")
    print("=" * 100)
    print(f"1. HIGH PRIORITY ({len(categories['high_priority'])} authors):")
    print(f"   - Add to famous_people.json immediately")
    print(f"   - These are award winners and genre icons")
    print(f"   - Signed books: 15x-25x multipliers")
    print(f"   - First editions: 4x-6x multipliers")
    print()
    print(f"2. MEDIUM PRIORITY ({len(categories['medium_priority'])} authors):")
    print(f"   - Review and add collectible genre authors")
    print(f"   - Focus on horror, sci-fi, fantasy, mystery")
    print(f"   - Signed books: 8x-12x multipliers")
    print(f"   - First editions: 2.5x-3x multipliers")
    print()
    print(f"3. LOW PRIORITY ({len(categories['low_priority'])} authors):")
    print(f"   - Romance, thriller, general fiction")
    print(f"   - Add selectively based on specific collectible signals")
    print(f"   - Signed books: 3x-6x multipliers")

    # Generate suggested additions for famous_people.json
    print("\n" + "=" * 100)
    print("SUGGESTED ADDITIONS TO famous_people.json")
    print("=" * 100)
    print("High priority authors to add:\n")

    for author in categories['high_priority'][:10]:
        name = author['name']
        signed_mult = author['signed_multiplier']
        genre = author.get('genre', 'N/A')
        reasoning = author['reasoning']

        print(f'    "{name}": {{')
        print(f'      "signed_multiplier": {signed_mult},')
        print(f'      "fame_tier": "bestselling_author",')
        print(f'      "genres": ["{genre}"],')
        print(f'      "notes": "{reasoning}"')
        print(f'    }},')


if __name__ == "__main__":
    main()
