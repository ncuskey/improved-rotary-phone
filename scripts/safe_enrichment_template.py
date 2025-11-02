#!/usr/bin/env python3
"""
SAFE ENRICHMENT TEMPLATE

This is a template for creating safe database enrichment scripts.
ALL enrichment scripts must follow this pattern to prevent data loss.

See: /docs/ENRICHMENT_SCRIPT_CHECKLIST.md for requirements
See: /docs/FEATURE_DETECTION_GUIDELINES.md for feature detection rules

Usage:
    # Dry-run (preview changes without applying them)
    python safe_enrichment_template.py --dry-run

    # Apply changes
    python safe_enrichment_template.py

    # Force apply (skip data loss validation)
    python safe_enrichment_template.py --force

Example Implementation:
    Replace TODO sections below with your enrichment logic.
"""

import argparse
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Any

# Import safety helpers
from scripts.backup_database import backup_database
from shared.enrichment_helpers import (
    FieldChange,
    preserve_existing_data,
    validate_changes,
    create_change_log,
    safe_enrichment_summary
)

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


def fetch_books_to_enrich(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Fetch books that need enrichment.

    TODO: Customize this query for your enrichment needs.

    Example:
        # Enrich only books without cover_type
        SELECT isbn, title, cover_type FROM books WHERE cover_type IS NULL

        # Enrich all books
        SELECT isbn, title, cover_type FROM books
    """
    cursor = conn.cursor()

    # TODO: Replace with your query
    query = """
        SELECT isbn, title, author, cover_type, signed, edition, printing
        FROM books
        WHERE 1=1
        -- Add your WHERE clause here
        -- Example: WHERE cover_type IS NULL
    """

    cursor.execute(query)
    books = [dict(row) for row in cursor.fetchall()]

    logger.info(f"Fetched {len(books)} books for enrichment")
    return books


def perform_enrichment(book: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform enrichment logic for a single book.

    TODO: Implement your enrichment logic here.

    Args:
        book: Dictionary with book data (isbn, title, etc.)

    Returns:
        Dictionary with new/updated field values

    Example:
        from shared.feature_detector import parse_all_features
        # Only if book data is from eBay listing!
        features = parse_all_features(book['ebay_title'])
        return {
            'cover_type': features.cover_type,
            'signed': features.signed,
        }

    IMPORTANT:
        - See /docs/FEATURE_DETECTION_GUIDELINES.md for when to use feature_detector
        - NEVER apply feature detection to catalog book titles
        - ONLY apply to eBay/marketplace listing titles
    """
    # TODO: Replace with your enrichment logic
    # This example shows how to preserve existing data

    # Example: Detect something from the book
    # new_cover_type = detect_cover_type_somehow(book)

    # For this template, we just return None (no changes)
    return {
        'cover_type': None,
        'signed': None,
        'edition': None,
        'printing': None,
    }


def propose_changes(books: List[Dict[str, Any]]) -> List[FieldChange]:
    """
    Generate proposed changes for all books.

    This function applies the safe preservation pattern:
    - New value used if detected
    - Existing value preserved if new detection returns None
    """
    changes = []

    for book in books:
        isbn = book['isbn']

        # Perform enrichment
        new_values = perform_enrichment(book)

        # For each field, create change proposal
        for field, new_value in new_values.items():
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

                logger.debug(
                    f"{isbn}: {field} {old_value} -> {safe_new_value}"
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
        description="Safe database enrichment template",
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

    args = parser.parse_args()

    # Expand path
    db_path = args.db_path.expanduser().resolve()

    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return 1

    logger.info("=" * 70)
    logger.info("SAFE ENRICHMENT SCRIPT")
    logger.info("=" * 70)
    logger.info(f"Database: {db_path}")
    logger.info(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    logger.info("=" * 70)

    # STEP 1: Create backup (unless dry-run)
    if not args.dry_run:
        logger.info("\nStep 1: Creating backup...")
        try:
            backup_path = backup_database(
                db_path,
                reason="pre-enrichment"
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
    books = fetch_books_to_enrich(conn)
    logger.info(f"✓ Fetched {len(books)} books")

    if not books:
        logger.info("No books to enrich")
        return 0

    # STEP 4: Propose changes
    logger.info("\nStep 4: Generating proposed changes...")
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

    # STEP 7: Create change log
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
