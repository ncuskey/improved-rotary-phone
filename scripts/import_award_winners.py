#!/usr/bin/env python3
"""
Import award-winning authors from CSV into famous_people.json.

Usage:
    python3 scripts/import_award_winners.py /path/to/award_winners.csv
"""

import sys
import csv
import json
from pathlib import Path


# Award tier multipliers (signed book premiums)
AWARD_TIERS = {
    # Tier 1: Most prestigious literary awards
    'National Book Award': {'multiplier': 12, 'tier': 'major_award'},
    'Booker Prize': {'multiplier': 15, 'tier': 'major_award'},
    'International Booker Prize': {'multiplier': 12, 'tier': 'major_award'},
    'Women\'s Prize for Fiction': {'multiplier': 10, 'tier': 'major_award'},
    'National Book Critics Circle Award': {'multiplier': 10, 'tier': 'major_award'},

    # Tier 2: Genre awards (still collectible)
    'Hugo Award': {'multiplier': 8, 'tier': 'genre_award'},
    'Nebula Award': {'multiplier': 8, 'tier': 'genre_award'},

    # Tier 3: Children's/YA awards
    'Newbery Medal': {'multiplier': 6, 'tier': 'childrens_award'},
    'Caldecott Medal': {'multiplier': 6, 'tier': 'childrens_award'},
}


def get_award_info(award_name):
    """
    Get multiplier and tier for an award.

    Returns (multiplier, tier) or (8, 'award_winner') as default.
    """
    # Try exact match first
    if award_name in AWARD_TIERS:
        info = AWARD_TIERS[award_name]
        return info['multiplier'], info['tier']

    # Try partial matches
    for key, info in AWARD_TIERS.items():
        if key in award_name:
            return info['multiplier'], info['tier']

    # Default for unrecognized awards
    return 8, 'award_winner'


def normalize_author_name(name):
    """
    Normalize author name for consistency.

    Examples:
        "John Smith" -> "John Smith"
        "Smith, John" -> "John Smith"
    """
    name = name.strip()

    # Handle "Last, First" format
    if ',' in name:
        parts = name.split(',', 1)
        if len(parts) == 2:
            last, first = parts
            name = f"{first.strip()} {last.strip()}"

    # Handle translator notation: "Name (translated by ...)"
    if '(translated by' in name.lower():
        name = name.split('(translated by')[0].strip()

    return name


def determine_genre(award_name):
    """Determine genre based on award type."""
    if 'Poetry' in award_name:
        return ['poetry']
    elif 'Fiction' in award_name:
        return ['literary fiction']
    elif 'Nonfiction' in award_name or 'Biography' in award_name:
        return ['non-fiction']
    elif 'Translated' in award_name:
        return ['international literature']
    elif 'Hugo' in award_name or 'Nebula' in award_name:
        return ['science fiction', 'fantasy']
    elif 'Newbery' in award_name or 'Caldecott' in award_name or 'Young People' in award_name:
        return ['children\'s literature', 'young adult']
    else:
        return ['literary fiction']


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/import_award_winners.py <csv_file> [--yes]")
        print()
        print("Example: python3 scripts/import_award_winners.py /Users/nickcuskey/Downloads/award_winners_part1.csv --yes")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    auto_yes = '--yes' in sys.argv or '-y' in sys.argv
    if not csv_path.exists():
        print(f"Error: File not found: {csv_path}")
        sys.exit(1)

    # Load existing famous_people.json
    famous_people_path = Path(__file__).parent.parent / 'shared' / 'famous_people.json'
    with open(famous_people_path, 'r') as f:
        famous_people = json.load(f)

    print(f"Current famous_people.json: {len(famous_people)} entries")
    print()

    # Parse CSV
    new_authors = {}
    skipped = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            award = row['Award']
            author = normalize_author_name(row['Author'])
            work = row['Work']
            year = row['Year']

            # Skip if already exists
            if author in famous_people:
                skipped.append(author)
                continue

            # Skip illustrators for now
            if 'Illustrator' in award:
                skipped.append(f"{author} (illustrator)")
                continue

            # Get award info
            multiplier, tier = get_award_info(award)
            genres = determine_genre(award)

            # Add to new authors
            new_authors[author] = {
                'type': 'author',
                'fame_tier': tier,
                'signed_multiplier': multiplier,
                'genres': genres,
                'notable_works': [work],
                'awards': [f"{award} ({year})"],
                'notes': f"{award} winner {year}"
            }

    print(f"=== IMPORT SUMMARY ===")
    print(f"CSV authors: {len(list(csv.DictReader(open(csv_path))))} total")
    print(f"New authors to add: {len(new_authors)}")
    print(f"Skipped (already exists): {len(skipped)}")
    print()

    if skipped:
        print("Already in database:")
        for name in skipped[:10]:
            print(f"  - {name}")
        if len(skipped) > 10:
            print(f"  ... and {len(skipped) - 10} more")
        print()

    if not new_authors:
        print("No new authors to add!")
        sys.exit(0)

    # Show preview
    print("NEW AUTHORS TO ADD:")
    print()
    for i, (name, info) in enumerate(list(new_authors.items())[:5], 1):
        print(f"{i}. {name}")
        print(f"   Multiplier: {info['signed_multiplier']}x")
        print(f"   Award: {info['awards'][0]}")
        print(f"   Genres: {', '.join(info['genres'])}")
        print()

    if len(new_authors) > 5:
        print(f"... and {len(new_authors) - 5} more")
        print()

    # Confirm
    if not auto_yes:
        response = input(f"Add {len(new_authors)} new authors to famous_people.json? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("Cancelled.")
            sys.exit(0)
    else:
        print(f"Auto-confirming (--yes flag): Adding {len(new_authors)} authors...")

    # Merge and save
    famous_people.update(new_authors)

    # Sort alphabetically
    famous_people = dict(sorted(famous_people.items()))

    with open(famous_people_path, 'w') as f:
        json.dump(famous_people, f, indent=2)

    print()
    print(f"✓ Successfully added {len(new_authors)} authors")
    print(f"✓ Total in database: {len(famous_people)}")
    print()
    print(f"Updated: {famous_people_path}")


if __name__ == '__main__':
    main()
