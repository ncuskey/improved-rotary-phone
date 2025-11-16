#!/usr/bin/env python3
"""
Auto-enrich famous_people.json with high priority authors.

Non-interactive version that adds high priority + top 10 medium priority.
"""

import json
from pathlib import Path
from typing import Dict, Any


def load_famous_people() -> Dict[str, Any]:
    """Load existing famous_people.json."""
    famous_path = Path.home() / "ISBN" / "shared" / "famous_people.json"
    with open(famous_path, 'r') as f:
        return json.load(f)


def load_collectible_authors() -> Dict[str, Any]:
    """Load collectible authors analysis."""
    collectible_path = Path.home() / "ISBN" / "collectible_authors_enriched.json"
    with open(collectible_path, 'r') as f:
        return json.load(f)


def add_authors_to_category(famous_data: Dict, category: str, authors: list):
    """Add authors to a specific category in famous_people.json."""
    if category not in famous_data:
        famous_data[category] = {}

    added = []
    skipped = []

    for author in authors:
        name = author['name']

        # Check if already exists in any category
        exists = False
        for cat_name, cat_data in famous_data.items():
            if cat_name.startswith('_') or cat_name == 'name_variations':
                continue
            if name in cat_data:
                exists = True
                skipped.append((name, cat_name))
                break

        if not exists:
            # Add to category
            famous_data[category][name] = {
                "signed_multiplier": author['signed_multiplier'],
                "fame_tier": author.get('suggested_tier', 'bestselling_author'),
                "genres": [author.get('genre', 'fiction')] if author.get('genre') else ['fiction'],
                "notes": author.get('reasoning', 'Prolific series author')
            }
            added.append(name)

    return added, skipped


def main():
    """Main execution."""
    print("Loading existing famous_people.json...")
    famous_data = load_famous_people()

    print("Loading collectible authors analysis...")
    collectible_data = load_collectible_authors()

    # Count existing authors
    existing_count = 0
    for category in famous_data:
        if category.startswith('_') or category == 'name_variations':
            continue
        existing_count += len(famous_data[category])

    print(f"Current famous people count: {existing_count}")
    print()

    # Add high priority authors
    print("=" * 80)
    print("ADDING HIGH PRIORITY AUTHORS (Award Winners, Genre Icons)")
    print("=" * 80)

    high_priority = collectible_data['high_priority']
    added_high, skipped_high = add_authors_to_category(
        famous_data,
        'authors_bestselling',
        high_priority
    )

    print(f"Added {len(added_high)} high priority authors:")
    for name in added_high:
        author = next(a for a in high_priority if a['name'] == name)
        print(f"  ✓ {name} ({author['signed_multiplier']}x signed, {author.get('genre', 'N/A')})")

    if skipped_high:
        print(f"\nSkipped {len(skipped_high)} (already in database):")
        for name, category in skipped_high:
            print(f"  - {name} (in {category})")

    # Add top 10 medium priority
    print()
    print("=" * 80)
    print("ADDING TOP 10 MEDIUM PRIORITY AUTHORS (Collectible Genres)")
    print("=" * 80)

    medium_priority = collectible_data['medium_priority'][:10]

    added_medium, skipped_medium = add_authors_to_category(
        famous_data,
        'authors_bestselling',
        medium_priority
    )

    print(f"Added {len(added_medium)} medium priority authors:")
    for name in added_medium:
        author = next(a for a in medium_priority if a['name'] == name)
        print(f"  ✓ {name} ({author['signed_multiplier']}x signed, {author.get('genre', 'N/A')})")

    if skipped_medium:
        print(f"\nSkipped {len(skipped_medium)} (already in database):")
        for name, category in skipped_medium:
            print(f"  - {name} (in {category})")

    # Count new total
    new_count = 0
    for category in famous_data:
        if category.startswith('_') or category == 'name_variations':
            continue
        new_count += len(famous_data[category])

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Before: {existing_count} famous people")
    print(f"After:  {new_count} famous people")
    print(f"Added:  {new_count - existing_count} new authors")
    print()

    # Save
    famous_path = Path.home() / "ISBN" / "shared" / "famous_people.json"

    # Backup first
    backup_path = famous_path.with_suffix('.json.backup')
    with open(famous_path, 'r') as f:
        backup_data = f.read()
    with open(backup_path, 'w') as f:
        f.write(backup_data)
    print(f"✓ Backup saved to {backup_path}")

    # Save updated data
    with open(famous_path, 'w') as f:
        json.dump(famous_data, f, indent=2)
    print(f"✓ Saved updated famous_people.json ({new_count} authors)")

    print()
    print("=" * 80)
    print("NEW AUTHORS ADDED")
    print("=" * 80)
    print("These authors will now be detected for collectible first editions:")
    print()
    all_added = added_high + added_medium
    for name in all_added:
        print(f"  • {name}")

    print()
    print("Done!")


if __name__ == "__main__":
    main()
