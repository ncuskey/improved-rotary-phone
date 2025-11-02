#!/usr/bin/env python3
"""
Safe Catalog Enrichment from eBay Sold Listings

This script enriches the catalog database by:
1. Fetching eBay sold listings for catalog ISBNs
2. Extracting book features from eBay listing titles
3. Safely applying features to catalog using preservation pattern

Usage:
    # Dry-run (preview changes)
    python3 scripts/enrich_from_ebay.py --dry-run

    # Enrich first 100 books
    python3 scripts/enrich_from_ebay.py --limit 100

    # Enrich specific ISBNs
    python3 scripts/enrich_from_ebay.py --isbn-file /tmp/catalog_isbns.txt --limit 100
"""

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value.strip('"').strip("'")

from scripts.backup_database import backup_database
from shared.enrichment_helpers import (
    FieldChange,
    preserve_existing_data,
    validate_changes,
    safe_enrichment_summary
)
from shared.ebay_sold_comps import get_sold_comps
from shared.feature_detector import parse_all_features

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_database_connection(db_path: Path) -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def fetch_books_to_enrich(
    conn: sqlite3.Connection,
    isbn_file: Optional[Path] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Fetch books that need enrichment from eBay data.

    Args:
        conn: Database connection
        isbn_file: Optional file with ISBNs to process
        limit: Maximum number of books to process

    Returns:
        List of book dictionaries
    """
    cursor = conn.cursor()

    if isbn_file:
        # Load ISBNs from file
        isbns = []
        with open(isbn_file, 'r') as f:
            for line in f:
                isbn = line.strip()
                if isbn:
                    isbns.append(isbn)

        if limit:
            isbns = isbns[:limit]

        # Build query for specific ISBNs
        placeholders = ','.join('?' * len(isbns))
        query = f"""
            SELECT isbn, title, cover_type, signed, edition, dust_jacket
            FROM books
            WHERE isbn IN ({placeholders})
        """
        cursor.execute(query, isbns)
    else:
        # Get all books (or up to limit)
        query = """
            SELECT isbn, title, cover_type, signed, edition, dust_jacket
            FROM books
        """
        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)

    books = [dict(row) for row in cursor.fetchall()]
    logger.info(f"Fetched {len(books)} books for enrichment")
    return books


def enrich_from_ebay(book: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Enrich a single book by fetching eBay sold comps and extracting features.

    Args:
        book: Dictionary with book data

    Returns:
        Dictionary with detected feature values, or None if no eBay data
    """
    isbn = book['isbn']

    try:
        # Fetch eBay sold comps
        comps = get_sold_comps(isbn)

        if not comps:
            logger.debug(f"{isbn}: No eBay sold comps found")
            return None

        # Extract features from all comp titles
        # Note: Only extract features that the feature detector actually supports
        detected_features = {
            'cover_type': None,
            'signed': None,
            'edition': None,
            'dust_jacket': None,
        }

        # Aggregate features across multiple listings
        cover_types = []
        signed_count = 0
        editions = []
        dust_jackets = []

        # Get samples from the result
        samples = comps.get('samples', [])

        for sample in samples:
            title = sample.get('title', '')
            if not title:
                continue

            # Parse features from this listing title
            features = parse_all_features(title)

            if features.cover_type:
                cover_types.append(features.cover_type)
            if features.signed:
                signed_count += 1
            if features.edition:
                editions.append(features.edition)
            if features.dust_jacket:
                dust_jackets.append(features.dust_jacket)

        # Use most common values
        if cover_types:
            detected_features['cover_type'] = max(set(cover_types), key=cover_types.count)

        if signed_count >= 2:  # At least 2 listings say signed
            detected_features['signed'] = True

        if editions:
            detected_features['edition'] = max(set(editions), key=editions.count)

        if dust_jackets:
            # dust_jacket is boolean, so take True if any listing has it
            detected_features['dust_jacket'] = True

        return detected_features

    except Exception as e:
        logger.error(f"{isbn}: Error enriching from eBay: {e}")
        return None


def propose_changes(books: List[Dict[str, Any]]) -> List[FieldChange]:
    """
    Generate proposed changes for all books.

    This applies the safe preservation pattern:
    - New value used if detected from eBay
    - Existing value preserved if eBay detection returns None
    """
    changes = []

    for i, book in enumerate(books, 1):
        isbn = book['isbn']
        logger.info(f"[{i}/{len(books)}] Processing {isbn}...")

        # Get eBay enrichment
        enriched = enrich_from_ebay(book)

        if not enriched:
            continue

        # For each field, propose change with safe preservation
        # Note: Only process fields that the feature detector supports
        for field in ['cover_type', 'signed', 'edition', 'dust_jacket']:
            new_value = enriched.get(field)
            old_value = book.get(field)

            # Apply safe preservation pattern
            safe_new_value = preserve_existing_data(new_value, old_value)

            # Only create change if value actually changed
            if safe_new_value != old_value:
                change = FieldChange(
                    isbn=isbn,
                    field=field,
                    old_value=old_value,
                    new_value=safe_new_value
                )
                changes.append(change)

                logger.info(
                    f"  {isbn}: {field} {old_value} -> {safe_new_value}"
                )

    return changes


def apply_changes(
    conn: sqlite3.Connection,
    changes: List[FieldChange],
    dry_run: bool = True
):
    """
    Apply validated changes to the database.

    Args:
        conn: Database connection
        changes: List of validated changes to apply
        dry_run: If True, don't actually commit changes
    """
    if not changes:
        logger.info("No changes to apply")
        return

    # Group changes by ISBN for efficient updates
    changes_by_isbn: Dict[str, List[FieldChange]] = {}
    for change in changes:
        if change.isbn not in changes_by_isbn:
            changes_by_isbn[change.isbn] = []
        changes_by_isbn[change.isbn].append(change)

    cursor = conn.cursor()

    # Apply changes
    for isbn, isbn_changes in changes_by_isbn.items():
        # Build UPDATE statement
        set_clauses = []
        params = {}

        for change in isbn_changes:
            set_clauses.append(f"{change.field} = :{change.field}")
            params[change.field] = change.new_value

        params['isbn'] = isbn

        query = f"""
            UPDATE books
            SET {', '.join(set_clauses)}
            WHERE isbn = :isbn
        """

        if dry_run:
            logger.info(f"[DRY-RUN] Would execute: {query}")
            logger.info(f"[DRY-RUN] With params: {params}")
        else:
            cursor.execute(query, params)
            logger.debug(f"Updated {isbn}: {len(isbn_changes)} fields")

    if not dry_run:
        conn.commit()
        logger.info(f"Committed {len(changes)} field changes")


def main():
    parser = argparse.ArgumentParser(
        description="Safe catalog enrichment from eBay sold listings",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would change without making changes'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip data loss validation (USE WITH CAUTION)'
    )
    parser.add_argument(
        '--db-path',
        type=Path,
        default=Path.home() / '.isbn_lot_optimizer' / 'catalog.db',
        help='Path to database file'
    )
    parser.add_argument(
        '--isbn-file',
        type=Path,
        help='File with ISBNs to process (one per line)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of books to process'
    )

    args = parser.parse_args()

    # Expand path
    db_path = args.db_path.expanduser().resolve()

    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return 1

    logger.info("=" * 70)
    logger.info("CATALOG ENRICHMENT FROM EBAY")
    logger.info("=" * 70)
    logger.info(f"Database: {db_path}")
    logger.info(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    if args.limit:
        logger.info(f"Limit: {args.limit} books")
    logger.info("=" * 70)

    # STEP 1: Create backup (unless dry-run)
    if not args.dry_run:
        logger.info("\nStep 1: Creating backup...")
        try:
            backup_path = backup_database(
                db_path,
                reason="pre-ebay-enrichment"
            )
            logger.info(f"✓ Backup created: {backup_path}")
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return 1
    else:
        logger.info("\nStep 1: Skipping backup (dry-run mode)")

    # STEP 2: Connect to database
    logger.info("\nStep 2: Connecting to database...")
    conn = get_database_connection(db_path)
    logger.info("✓ Connected")

    # STEP 3: Fetch books
    logger.info("\nStep 3: Fetching books...")
    books = fetch_books_to_enrich(conn, args.isbn_file, args.limit)
    logger.info(f"✓ Fetched {len(books)} books")

    if not books:
        logger.info("No books to enrich")
        return 0

    # STEP 4: Propose changes (collect eBay data + extract features)
    logger.info("\nStep 4: Collecting eBay data and extracting features...")
    changes = propose_changes(books)
    logger.info(f"✓ Generated {len(changes)} proposed changes")

    if not changes:
        logger.info("No changes needed")
        return 0

    # STEP 5: Validate changes
    logger.info("\nStep 5: Validating changes...")
    try:
        data_loss, stats = validate_changes(
            changes,
            allow_data_loss=args.force
        )

        logger.info("✓ Validation passed")
        logger.info(f"  Improvements: {stats['improvements']}")
        logger.info(f"  Data losses: {stats['data_loss']}")
        logger.info(f"  No changes: {stats['no_change']}")

    except ValueError as e:
        logger.error(f"✗ Validation failed: {e}")
        logger.error("Use --force to override, or fix enrichment logic")
        return 1

    # STEP 6: Show summary
    logger.info("\nStep 6: Enrichment summary...")
    summary = safe_enrichment_summary(len(books), changes)
    logger.info(f"  Books processed: {summary['total_books']}")
    logger.info(f"  Books with changes: {summary['books_with_changes']}")
    logger.info(f"  Improvement rate: {summary['improvement_rate']:.1%}")
    logger.info(f"  Data loss rate: {summary['data_loss_rate']:.1%}")

    # STEP 7: Create change preview
    if args.dry_run:
        logger.info("\n" + "=" * 70)
        logger.info("CHANGE PREVIEW (DRY-RUN)")
        logger.info("=" * 70)

        # Show first 20 changes
        for change in changes[:20]:
            symbol = "  ✗" if change.is_data_loss else "  ✓"
            logger.info(
                f"{symbol} {change.isbn}: {change.field} "
                f"{change.old_value} -> {change.new_value}"
            )

        if len(changes) > 20:
            logger.info(f"  ... and {len(changes) - 20} more changes")

    # STEP 8: Apply changes
    logger.info("\nStep 7: Applying changes...")
    apply_changes(conn, changes, dry_run=args.dry_run)

    if args.dry_run:
        logger.info("✓ Dry-run complete (no changes made)")
        logger.info("\nTo apply changes, run without --dry-run flag")
    else:
        logger.info("✓ Changes applied successfully")

    # Close connection
    conn.close()

    logger.info("\n" + "=" * 70)
    logger.info("ENRICHMENT COMPLETE")
    logger.info("=" * 70)

    return 0


if __name__ == "__main__":
    exit(main())
