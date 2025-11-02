"""
Helper functions for safe database enrichment operations.

This module provides validation and safety checks to prevent data loss
during enrichment operations.

Usage:
    from shared.enrichment_helpers import (
        preserve_existing_data,
        validate_changes,
        count_data_loss
    )

    # Always preserve existing data when enrichment returns None
    new_cover = preserve_existing_data(detected_cover, existing_cover)

    # Validate changes before committing
    losing_data = validate_changes(books, proposed_changes)
    if losing_data:
        print(f"WARNING: {len(losing_data)} books would lose data!")
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class FieldChange:
    """Represents a proposed change to a database field."""
    isbn: str
    field: str
    old_value: Any
    new_value: Any

    @property
    def is_data_loss(self) -> bool:
        """Check if this change would delete data (something -> None)."""
        return self.old_value is not None and self.new_value is None

    @property
    def is_improvement(self) -> bool:
        """Check if this change adds or improves data (None -> something, or different value)."""
        if self.old_value is None and self.new_value is not None:
            return True
        if self.old_value != self.new_value and self.new_value is not None:
            return True
        return False

    @property
    def is_no_change(self) -> bool:
        """Check if values are the same."""
        return self.old_value == self.new_value


def preserve_existing_data(new_value: Any, existing_value: Any) -> Any:
    """
    Preserve existing data when new detection returns None.

    This is the core safety pattern: NEVER overwrite good data with None.

    Args:
        new_value: Value from new detection/enrichment (may be None)
        existing_value: Current value in database (may be None)

    Returns:
        The new value if it exists, otherwise the existing value

    Examples:
        >>> preserve_existing_data("Hardcover", "Paperback")
        'Hardcover'  # New detection found different value - use it

        >>> preserve_existing_data(None, "Hardcover")
        'Hardcover'  # New detection found nothing - keep existing

        >>> preserve_existing_data("Paperback", None)
        'Paperback'  # No existing data - use new detection

        >>> preserve_existing_data(None, None)
        None  # Both empty - remain empty
    """
    return new_value if new_value is not None else existing_value


def validate_changes(
    changes: List[FieldChange],
    allow_data_loss: bool = False
) -> Tuple[List[FieldChange], Dict[str, int]]:
    """
    Validate proposed changes and identify potential data loss.

    Args:
        changes: List of proposed field changes
        allow_data_loss: If False, raises exception when data loss detected

    Returns:
        Tuple of (changes_with_data_loss, statistics_dict)

    Raises:
        ValueError: If data loss detected and allow_data_loss=False

    Example:
        >>> changes = [
        ...     FieldChange("123", "cover_type", "Hardcover", None),
        ...     FieldChange("456", "cover_type", None, "Paperback"),
        ... ]
        >>> losing_data, stats = validate_changes(changes)
        ValueError: Refusing to delete data from 1 books!
    """
    # Categorize changes
    data_loss = []
    improvements = []
    no_changes = []

    for change in changes:
        if change.is_data_loss:
            data_loss.append(change)
        elif change.is_improvement:
            improvements.append(change)
        elif change.is_no_change:
            no_changes.append(change)

    # Statistics
    stats = {
        'total_changes': len(changes),
        'data_loss': len(data_loss),
        'improvements': len(improvements),
        'no_change': len(no_changes),
    }

    # Log summary
    logger.info(f"Change validation: {stats}")

    if data_loss:
        logger.warning(f"Data loss detected in {len(data_loss)} changes:")
        for change in data_loss[:10]:  # Show first 10
            logger.warning(
                f"  {change.isbn}: {change.field} "
                f"{change.old_value} -> {change.new_value}"
            )
        if len(data_loss) > 10:
            logger.warning(f"  ... and {len(data_loss) - 10} more")

    # Raise if data loss and not allowed
    if data_loss and not allow_data_loss:
        raise ValueError(
            f"Refusing to delete data from {len(data_loss)} books! "
            f"Use --force to override or fix the enrichment logic."
        )

    return data_loss, stats


def count_data_loss(
    books: List[Dict[str, Any]],
    field_name: str,
    new_values: Dict[str, Any]
) -> int:
    """
    Count how many books would lose data if updates were applied.

    Args:
        books: List of book dictionaries with current data
        field_name: Name of field being updated
        new_values: Dictionary mapping ISBN to new values

    Returns:
        Count of books that would lose data

    Example:
        >>> books = [
        ...     {'isbn': '123', 'cover_type': 'Hardcover'},
        ...     {'isbn': '456', 'cover_type': None},
        ... ]
        >>> new_values = {'123': None, '456': 'Paperback'}
        >>> count_data_loss(books, 'cover_type', new_values)
        1  # Book '123' would lose 'Hardcover'
    """
    loss_count = 0

    for book in books:
        isbn = book.get('isbn')
        old_value = book.get(field_name)
        new_value = new_values.get(isbn)

        # Data loss: had data, now would be None
        if old_value is not None and new_value is None:
            loss_count += 1
            logger.debug(
                f"Data loss: {isbn} {field_name}: "
                f"{old_value} -> {new_value}"
            )

    return loss_count


def create_change_log(changes: List[FieldChange]) -> str:
    """
    Create a human-readable log of changes for audit purposes.

    Args:
        changes: List of field changes to document

    Returns:
        Formatted string summarizing all changes

    Example:
        >>> changes = [FieldChange("123", "cover_type", "Hardcover", "Paperback")]
        >>> print(create_change_log(changes))
        ENRICHMENT CHANGE LOG
        =====================
        Total changes: 1

        ISBN 123:
          cover_type: Hardcover -> Paperback
    """
    lines = [
        "ENRICHMENT CHANGE LOG",
        "=" * 70,
        f"Total changes: {len(changes)}",
        ""
    ]

    # Group by ISBN
    by_isbn: Dict[str, List[FieldChange]] = {}
    for change in changes:
        if change.isbn not in by_isbn:
            by_isbn[change.isbn] = []
        by_isbn[change.isbn].append(change)

    # Format each ISBN's changes
    for isbn, isbn_changes in sorted(by_isbn.items()):
        lines.append(f"ISBN {isbn}:")
        for change in isbn_changes:
            symbol = "  ✗" if change.is_data_loss else "  ✓"
            lines.append(
                f"{symbol} {change.field}: "
                f"{change.old_value} -> {change.new_value}"
            )
        lines.append("")

    return "\n".join(lines)


def safe_enrichment_summary(
    total_books: int,
    changes: List[FieldChange]
) -> Dict[str, Any]:
    """
    Generate a statistical summary of enrichment operation.

    Args:
        total_books: Total number of books processed
        changes: List of all proposed changes

    Returns:
        Dictionary with enrichment statistics

    Example:
        >>> changes = [
        ...     FieldChange("123", "cover_type", None, "Hardcover"),
        ...     FieldChange("456", "signed", False, True),
        ... ]
        >>> summary = safe_enrichment_summary(100, changes)
        >>> print(summary['improvement_rate'])
        0.02  # 2% of books improved
    """
    data_loss, stats = validate_changes(changes, allow_data_loss=True)

    return {
        'total_books': total_books,
        'books_with_changes': len(set(c.isbn for c in changes)),
        'total_field_changes': len(changes),
        'improvements': stats['improvements'],
        'data_losses': stats['data_loss'],
        'no_changes': stats['no_change'],
        'improvement_rate': stats['improvements'] / total_books if total_books > 0 else 0,
        'data_loss_rate': stats['data_loss'] / total_books if total_books > 0 else 0,
    }


class EnrichmentValidator:
    """
    Context manager for safe enrichment operations with validation.

    Usage:
        with EnrichmentValidator() as validator:
            for book in books:
                old_value = book['cover_type']
                new_value = detect_cover_type(book['title'])
                validator.propose_change(
                    book['isbn'],
                    'cover_type',
                    old_value,
                    new_value
                )

            # Automatically validates on exit
    """

    def __init__(self, allow_data_loss: bool = False):
        self.changes: List[FieldChange] = []
        self.allow_data_loss = allow_data_loss

    def propose_change(
        self,
        isbn: str,
        field: str,
        old_value: Any,
        new_value: Any
    ):
        """Propose a field change for validation."""
        # Apply safe preservation pattern
        safe_new_value = preserve_existing_data(new_value, old_value)

        change = FieldChange(isbn, field, old_value, safe_new_value)
        self.changes.append(change)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Validate all changes on exit."""
        if exc_type is None and self.changes:
            try:
                validate_changes(self.changes, self.allow_data_loss)
                logger.info(f"Validation passed: {len(self.changes)} changes safe")
            except ValueError as e:
                logger.error(f"Validation failed: {e}")
                raise
        return False  # Don't suppress exceptions


# Convenience function for quick validation
def quick_validate(
    books: List[Dict],
    field: str,
    get_new_value_func: callable
) -> List[FieldChange]:
    """
    Quick validation helper for simple enrichment scripts.

    Args:
        books: List of book dictionaries
        field: Name of field to enrich
        get_new_value_func: Function that takes a book and returns new value

    Returns:
        List of validated changes (safe to apply)

    Example:
        >>> def get_cover_type(book):
        ...     return detect_cover_type(book['title'])
        >>> changes = quick_validate(books, 'cover_type', get_cover_type)
        >>> # Apply changes if validation passed
    """
    with EnrichmentValidator() as validator:
        for book in books:
            isbn = book.get('isbn')
            old_value = book.get(field)
            new_value = get_new_value_func(book)
            validator.propose_change(isbn, field, old_value, new_value)

        return validator.changes
