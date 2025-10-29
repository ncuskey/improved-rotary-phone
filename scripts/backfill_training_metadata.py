#!/usr/bin/env python3
"""
Backfill metadata for existing training books.

The POC collector stored books without populating cover_type, signed, and printing fields.
This script infers these fields from:
1. collection_category (primary source)
2. metadata_json title/binding parsing (secondary)
3. Heuristic detection patterns

Usage:
    python3 scripts/backfill_training_metadata.py [--dry-run]
"""

import argparse
import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Dict, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def infer_from_category(category: str) -> Tuple[Optional[str], int, Optional[str]]:
    """
    Infer physical attributes from collection category.

    Args:
        category: Collection category (e.g., 'first_edition_hardcover')

    Returns:
        Tuple of (cover_type, signed, printing)
    """
    if not category:
        return None, 0, None

    category_lower = category.lower()

    # Cover type inference
    cover_type = None
    if 'hardcover' in category_lower:
        cover_type = 'Hardcover'
    elif 'mass_market' in category_lower:
        cover_type = 'Mass Market'
    elif 'paperback' in category_lower:
        cover_type = 'Paperback'

    # Signed inference
    signed = 1 if 'signed' in category_lower else 0

    # Printing/edition inference
    printing = None
    if 'first_edition' in category_lower:
        printing = '1st'

    return cover_type, signed, printing


def parse_title_for_attributes(title: str) -> Tuple[Optional[str], int, Optional[str]]:
    """
    Parse book title for physical attribute keywords.

    Args:
        title: Book title

    Returns:
        Tuple of (cover_type_hint, signed_hint, printing_hint)
    """
    if not title:
        return None, 0, None

    title_lower = title.lower()

    # Cover type hints
    cover_hint = None
    if re.search(r'\b(hardcover|hardback|hc)\b', title_lower):
        cover_hint = 'Hardcover'
    elif re.search(r'\bmass market\b', title_lower):
        cover_hint = 'Mass Market'
    elif re.search(r'\b(paperback|pb)\b', title_lower):
        cover_hint = 'Paperback'

    # Signed hints
    signed_hint = 1 if re.search(r'\b(signed|autographed)\b', title_lower) else 0

    # Edition hints
    printing_hint = None
    if re.search(r'\b(first edition|1st edition)\b', title_lower):
        printing_hint = '1st'
    elif re.search(r'\bfirst printing\b', title_lower):
        printing_hint = '1st'

    return cover_hint, signed_hint, printing_hint


def parse_binding_field(binding: Optional[str]) -> Optional[str]:
    """
    Parse Google Books binding field to cover_type.

    Args:
        binding: Binding string from Google Books (e.g., 'HARDCOVER', 'Paperback')

    Returns:
        Standardized cover_type or None
    """
    if not binding:
        return None

    binding_lower = binding.lower()

    if 'hardcover' in binding_lower or 'hardback' in binding_lower:
        return 'Hardcover'
    elif 'mass market' in binding_lower:
        return 'Mass Market'
    elif 'paperback' in binding_lower:
        return 'Paperback'

    return None


def infer_metadata(
    category: str,
    metadata_json: Optional[str]
) -> Tuple[Optional[str], int, Optional[str]]:
    """
    Infer physical attributes using all available data.

    Args:
        category: Collection category
        metadata_json: Serialized metadata dict

    Returns:
        Tuple of (cover_type, signed, printing)
    """
    # Start with category inference (most reliable)
    cover_type, signed, printing = infer_from_category(category)

    # Parse metadata for additional hints
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)

            # Parse title
            title = metadata.get('title', '')
            title_cover, title_signed, title_printing = parse_title_for_attributes(title)

            # Use title hints if category didn't provide them
            if not cover_type:
                cover_type = title_cover
            if not signed and title_signed:
                signed = title_signed
            if not printing:
                printing = title_printing

            # Check binding field (Google Books)
            binding = metadata.get('binding') or metadata.get('format')
            if not cover_type and binding:
                cover_type = parse_binding_field(binding)

        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"Failed to parse metadata: {e}")

    return cover_type, signed, printing


def backfill_metadata(dry_run: bool = False):
    """
    Backfill metadata for all training books.

    Args:
        dry_run: If True, only show what would be updated
    """
    db_path = Path.home() / '.isbn_lot_optimizer' / 'training_data.db'

    if not db_path.exists():
        logger.error(f"Training database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Fetch all books
    cursor.execute("""
        SELECT isbn, title, collection_category, metadata_json, cover_type, signed, printing
        FROM training_books
    """)
    books = cursor.fetchall()

    logger.info(f"Found {len(books)} books in training database")
    logger.info("")

    stats = {
        'total': len(books),
        'cover_type_updated': 0,
        'signed_updated': 0,
        'printing_updated': 0,
        'no_changes': 0,
    }

    updates = []

    for isbn, title, category, metadata_json, existing_cover, existing_signed, existing_printing in books:
        # Infer metadata
        cover_type, signed, printing = infer_metadata(category, metadata_json)

        # Determine what needs updating
        needs_update = False
        changes = []

        if cover_type and not existing_cover:
            changes.append(f"cover_type={cover_type}")
            stats['cover_type_updated'] += 1
            needs_update = True
        else:
            cover_type = existing_cover

        if signed and not existing_signed:
            changes.append(f"signed={signed}")
            stats['signed_updated'] += 1
            needs_update = True
        else:
            signed = existing_signed or 0

        if printing and not existing_printing:
            changes.append(f"printing={printing}")
            stats['printing_updated'] += 1
            needs_update = True
        else:
            printing = existing_printing

        if needs_update:
            logger.info(f"{isbn} ({title[:50]}...)")
            logger.info(f"  Category: {category}")
            logger.info(f"  Updates: {', '.join(changes)}")
            updates.append((cover_type, signed, printing, isbn))
        else:
            stats['no_changes'] += 1

    logger.info("")
    logger.info("=" * 70)
    logger.info("Backfill Summary")
    logger.info("=" * 70)
    logger.info(f"Total books: {stats['total']}")
    logger.info(f"Cover type updated: {stats['cover_type_updated']}")
    logger.info(f"Signed updated: {stats['signed_updated']}")
    logger.info(f"Printing updated: {stats['printing_updated']}")
    logger.info(f"No changes needed: {stats['no_changes']}")
    logger.info("")

    if dry_run:
        logger.info("DRY RUN - No changes were made to the database")
    else:
        # Apply updates
        cursor.executemany("""
            UPDATE training_books
            SET cover_type = ?, signed = ?, printing = ?, updated_at = CURRENT_TIMESTAMP
            WHERE isbn = ?
        """, updates)

        conn.commit()
        logger.info(f"✓ Updated {len(updates)} books")

    conn.close()

    # Show distribution after backfill
    logger.info("")
    logger.info("=" * 70)
    logger.info("Post-Backfill Distribution")
    logger.info("=" * 70)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN cover_type = 'Hardcover' THEN 1 END) as hardcovers,
            COUNT(CASE WHEN cover_type = 'Paperback' THEN 1 END) as paperbacks,
            COUNT(CASE WHEN cover_type = 'Mass Market' THEN 1 END) as mass_market,
            COUNT(CASE WHEN signed = 1 THEN 1 END) as signed,
            COUNT(CASE WHEN printing LIKE '%1st%' THEN 1 END) as first_editions
        FROM training_books
    """)

    total, hardcovers, paperbacks, mass_market, signed_count, first_eds = cursor.fetchone()

    logger.info(f"Total books: {total}")
    logger.info(f"Hardcovers: {hardcovers} ({hardcovers/total*100:.1f}%)")
    logger.info(f"Paperbacks: {paperbacks} ({paperbacks/total*100:.1f}%)")
    logger.info(f"Mass Market: {mass_market} ({mass_market/total*100:.1f}%)")
    logger.info(f"Signed: {signed_count} ({signed_count/total*100:.1f}%)")
    logger.info(f"First Editions: {first_eds} ({first_eds/total*100:.1f}%)")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Backfill metadata for training books')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    args = parser.parse_args()

    backfill_metadata(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
