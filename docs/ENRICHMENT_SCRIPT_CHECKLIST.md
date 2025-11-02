# Enrichment Script Checklist

**MANDATORY REQUIREMENTS FOR ALL DATABASE ENRICHMENT SCRIPTS**

This checklist must be followed for all scripts that modify database records. Failure to follow these requirements can result in catastrophic data loss.

---

## Quick Start

Use the template at `/scripts/safe_enrichment_template.py` as your starting point. It includes all mandatory patterns.

---

## Mandatory Requirements

### 1. Dry-Run Mode ✓ REQUIRED

**Requirement:** Script MUST support `--dry-run` flag to preview changes without applying them.

**Implementation:**
```python
parser.add_argument(
    '--dry-run',
    action='store_true',
    help='Show what would change without making changes'
)

# In apply_changes():
if dry_run:
    logger.info(f"[DRY-RUN] Would execute: {query}")
else:
    cursor.execute(query)
    conn.commit()
```

**Testing:**
```bash
# ALWAYS test with dry-run first!
python my_enrichment_script.py --dry-run

# Review output, then run for real
python my_enrichment_script.py
```

**Why:** Allows you to catch mistakes before they cause damage.

---

### 2. Automatic Backup ✓ REQUIRED

**Requirement:** Script MUST create a backup before making changes (unless in dry-run mode).

**Implementation:**
```python
from scripts.backup_database import backup_database

if not args.dry_run:
    logger.info("Creating backup...")
    backup_path = backup_database(
        db_path,
        reason="pre-enrichment"
    )
    logger.info(f"✓ Backup created: {backup_path}")
```

**Why:** If something goes wrong, you can restore in seconds instead of losing data permanently.

---

### 3. Safe Data Preservation Pattern ✓ REQUIRED

**Requirement:** Script MUST preserve existing data when new detection returns None.

**NEVER DO THIS:**
```python
# ✗ WRONG - Overwrites existing data with None
update_book(isbn, cover_type=features.cover_type)
```

**ALWAYS DO THIS:**
```python
# ✓ CORRECT - Preserves existing data when detection returns None
from shared.enrichment_helpers import preserve_existing_data

new_cover = preserve_existing_data(
    features.cover_type,  # New value from detection
    book['cover_type']    # Existing value in DB
)
update_book(isbn, cover_type=new_cover)
```

**Why:** Feature detection may return None when applied to wrong data source or when features aren't present. Never delete existing good data.

---

### 4. Change Validation ✓ REQUIRED

**Requirement:** Script MUST validate changes before committing to catch data loss.

**Implementation:**
```python
from shared.enrichment_helpers import validate_changes, FieldChange

# Collect all proposed changes
changes = []
for book in books:
    old_value = book['cover_type']
    new_value = detect_cover_type(book)
    safe_new_value = preserve_existing_data(new_value, old_value)

    if safe_new_value != old_value:
        changes.append(FieldChange(
            isbn=book['isbn'],
            field='cover_type',
            old_value=old_value,
            new_value=safe_new_value
        ))

# Validate - will raise error if data loss detected
try:
    validate_changes(changes, allow_data_loss=args.force)
except ValueError as e:
    logger.error(f"Validation failed: {e}")
    sys.exit(1)
```

**Why:** Catches bugs before they cause data loss. Validation will fail if script tries to delete existing data.

---

### 5. Audit Logging ✓ REQUIRED

**Requirement:** Script MUST log all changes for audit trail.

**Implementation:**
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log each change
logger.info(f"{isbn}: cover_type {old_value} -> {new_value}")
```

**Why:** Provides trail of what changed, when, and why. Essential for debugging issues.

---

### 6. Statistical Summary ✓ REQUIRED

**Requirement:** Script MUST show before/after statistics.

**Implementation:**
```python
from shared.enrichment_helpers import safe_enrichment_summary

summary = safe_enrichment_summary(len(books), changes)
logger.info(f"Books processed: {summary['total_books']}")
logger.info(f"Books with changes: {summary['books_with_changes']}")
logger.info(f"Improvements: {summary['improvements']}")
logger.info(f"Data losses: {summary['data_losses']}")
logger.info(f"Improvement rate: {summary['improvement_rate']:.1%}")
```

**Why:** Helps validate enrichment is working as expected. Red flag if you see high "data loss" count.

---

### 7. Feature Detection Rules ✓ REQUIRED

**Requirement:** If using `feature_detector.py`, MUST follow data source rules from `/docs/FEATURE_DETECTION_GUIDELINES.md`.

**DO apply feature detection to:**
- ✓ eBay listing titles
- ✓ AbeBooks/Alibris listing titles
- ✓ Training data from eBay searches
- ✓ User-entered book descriptions

**DO NOT apply feature detection to:**
- ✗ Catalog book titles (ISBN metadata)
- ✗ Google Books API results
- ✗ Open Library metadata
- ✗ Basic ISBNdb lookup results

**Why:** Feature detector is trained on marketplace listings. Applying it to ISBN metadata returns None (correctly), but enrichment scripts then delete existing data (incorrectly).

---

## Optional but Recommended

### 8. Force Flag (Optional)

Allow overriding data loss validation with `--force` flag:

```python
parser.add_argument(
    '--force',
    action='store_true',
    help='Skip data loss validation (USE WITH CAUTION)'
)

validate_changes(changes, allow_data_loss=args.force)
```

**Use case:** Sometimes you intentionally want to clear bad data.

---

### 9. Test on Sample Data First (Recommended)

Before running on full database, test on small sample:

```python
# In fetch_books_to_enrich():
query = """
    SELECT ... FROM books
    WHERE ...
    LIMIT 10  -- Test on small sample first!
"""
```

**Process:**
1. Run with `LIMIT 10` and `--dry-run`
2. Verify changes look correct
3. Remove LIMIT and run for real

---

## Pre-Flight Checklist

Before running ANY enrichment script, verify:

- [ ] Started from `/scripts/safe_enrichment_template.py` template
- [ ] Includes `--dry-run` flag
- [ ] Creates backup before changes (unless dry-run)
- [ ] Uses `preserve_existing_data()` for all field updates
- [ ] Validates changes with `validate_changes()`
- [ ] Logs all changes
- [ ] Shows statistical summary
- [ ] If using feature_detector, applied to correct data source
- [ ] Tested on sample data with `--dry-run` first
- [ ] Reviewed dry-run output - no unexpected data loss

---

## Example: Good vs Bad

### ❌ BAD Example (Data Loss Likely)

```python
#!/usr/bin/env python3
"""Broken enrichment script - DO NOT USE"""
import sqlite3
from shared.feature_detector import parse_all_features

conn = sqlite3.connect('catalog.db')
cursor = conn.cursor()

# Get books
cursor.execute("SELECT isbn, title, cover_type FROM books")

for isbn, title, old_cover in cursor.fetchall():
    # BUG 1: No feature detection data source check
    # BUG 2: Applying to catalog title (ISBN metadata)
    features = parse_all_features(title)

    # BUG 3: Overwrites existing data with None!
    cursor.execute(
        "UPDATE books SET cover_type = ? WHERE isbn = ?",
        (features.cover_type, isbn)
    )

# BUG 4: No backup, no dry-run, no validation
conn.commit()
print("Done!")  # BUG 5: No statistics, no logging
```

**Problems:**
- No backup (data loss is permanent)
- No dry-run (can't preview changes)
- No data preservation (deletes existing data)
- No validation (doesn't catch data loss)
- Applied feature detection to wrong data source
- No logging or statistics

**Result:** CATASTROPHIC DATA LOSS (see `/CATALOG_ENRICHMENT_INCIDENT_REPORT.md`)

---

### ✅ GOOD Example (Safe)

```python
#!/usr/bin/env python3
"""Safe enrichment script"""
import argparse
import logging
import sqlite3
from pathlib import Path

from scripts.backup_database import backup_database
from shared.enrichment_helpers import (
    preserve_existing_data,
    validate_changes,
    FieldChange,
    safe_enrichment_summary
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    # ✓ Create backup
    if not args.dry_run:
        backup_path = backup_database(db_path, "pre-enrichment")
        logger.info(f"Backup: {backup_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get books
    cursor.execute("SELECT isbn, title, cover_type FROM books")
    books = [dict(row) for row in cursor.fetchall()]

    # ✓ Collect changes with safe preservation
    changes = []
    for book in books:
        # ✓ Only enrich if data came from eBay
        # (In this example, we skip if from catalog)
        if not book.get('ebay_title'):
            continue

        from shared.feature_detector import parse_all_features
        features = parse_all_features(book['ebay_title'])

        # ✓ Preserve existing data
        new_cover = preserve_existing_data(
            features.cover_type,
            book['cover_type']
        )

        if new_cover != book['cover_type']:
            changes.append(FieldChange(
                isbn=book['isbn'],
                field='cover_type',
                old_value=book['cover_type'],
                new_value=new_cover
            ))

    # ✓ Validate changes
    try:
        validate_changes(changes, allow_data_loss=args.force)
    except ValueError as e:
        logger.error(f"Validation failed: {e}")
        return 1

    # ✓ Show statistics
    summary = safe_enrichment_summary(len(books), changes)
    logger.info(f"Improvements: {summary['improvements']}")
    logger.info(f"Data losses: {summary['data_losses']}")

    # ✓ Apply changes (or dry-run)
    if not args.dry_run:
        for change in changes:
            cursor.execute(
                "UPDATE books SET cover_type = ? WHERE isbn = ?",
                (change.new_value, change.isbn)
            )
            logger.info(f"{change.isbn}: cover_type updated")
        conn.commit()
        logger.info("✓ Changes committed")
    else:
        logger.info("✓ Dry-run complete (no changes made)")

    conn.close()
    return 0

if __name__ == "__main__":
    exit(main())
```

**Why this is safe:**
- ✓ Creates backup before changes
- ✓ Supports dry-run mode
- ✓ Preserves existing data
- ✓ Validates all changes
- ✓ Logs everything
- ✓ Shows statistics
- ✓ Only applies feature detection to eBay listings

---

## Code Review Checklist

Before approving an enrichment script PR, verify:

### Safety Features
- [ ] Includes `--dry-run` flag
- [ ] Creates backup before changes
- [ ] Uses `preserve_existing_data()` pattern
- [ ] Validates changes before commit
- [ ] Handles errors gracefully

### Data Source Validation
- [ ] If using feature_detector, applied to marketplace listings only
- [ ] Never applied to catalog/ISBN metadata titles
- [ ] Data source clearly documented in script comments

### Testing
- [ ] Script tested with `--dry-run` on sample data
- [ ] Dry-run output reviewed - no unexpected data loss
- [ ] Statistics make sense (high improvement rate, low data loss rate)

### Documentation
- [ ] Script includes usage examples in docstring
- [ ] Logging shows clear progress
- [ ] Statistics displayed at end

---

## Emergency Recovery

If an enrichment script causes data loss:

1. **Stop the script immediately** (Ctrl+C)

2. **Restore from backup:**
   ```bash
   # List available backups
   python scripts/restore_database.py --list --db-name catalog

   # Restore most recent
   python scripts/restore_database.py --latest --db-name catalog
   ```

3. **Investigate what went wrong:**
   - Check logs for patterns
   - Was feature detection applied to wrong data source?
   - Was safe preservation pattern used?
   - Did validation run?

4. **Fix the script** using this checklist

5. **Test thoroughly** with --dry-run before running again

---

## Reference

- Template: `/scripts/safe_enrichment_template.py`
- Helpers: `/shared/enrichment_helpers.py`
- Guidelines: `/docs/FEATURE_DETECTION_GUIDELINES.md`
- Incident Report: `/CATALOG_ENRICHMENT_INCIDENT_REPORT.md`

---

## Document History

- **2025-01-31:** Created after catalog enrichment data loss incident
- **Purpose:** Ensure all future enrichment scripts include mandatory safety features
