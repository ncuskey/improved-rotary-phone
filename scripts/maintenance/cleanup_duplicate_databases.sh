#!/bin/bash
#
# Database Cleanup Script
# Safely removes duplicate and empty database files
#

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${HOME}/backups/isbn_databases_cleanup_${TIMESTAMP}"
LOG_FILE="/tmp/db_cleanup_${TIMESTAMP}.log"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "DATABASE CLEANUP SCRIPT"
echo "========================================================================"
echo "Timestamp: $(date)" | tee -a "$LOG_FILE"
echo "Backup directory: ${BACKUP_DIR}" | tee -a "$LOG_FILE"
echo "Log file: ${LOG_FILE}" | tee -a "$LOG_FILE"
echo ""

# Create backup directory
echo -e "${GREEN}Creating backup directory...${NC}" | tee -a "$LOG_FILE"
mkdir -p "${BACKUP_DIR}"
echo "✓ Backup directory created: ${BACKUP_DIR}" | tee -a "$LOG_FILE"
echo ""

# Backup active databases before any deletion
echo "========================================================================"
echo "STEP 1: BACKING UP ACTIVE DATABASES"
echo "========================================================================"
echo "" | tee -a "$LOG_FILE"

ACTIVE_DBS=(
    "${HOME}/.isbn_lot_optimizer/catalog.db"
    "${HOME}/.isbn_lot_optimizer/metadata_cache.db"
    "${HOME}/.isbn_lot_optimizer/training_data.db"
    "${HOME}/.isbn_lot_optimizer/unified_index.db"
)

for db in "${ACTIVE_DBS[@]}"; do
    if [ -f "$db" ]; then
        filename=$(basename "$db")
        echo "Backing up: $db" | tee -a "$LOG_FILE"
        cp "$db" "${BACKUP_DIR}/${filename}"

        # Verify backup
        if [ -f "${BACKUP_DIR}/${filename}" ]; then
            orig_size=$(du -h "$db" | cut -f1)
            backup_size=$(du -h "${BACKUP_DIR}/${filename}" | cut -f1)
            echo "  ✓ Backup verified: ${BACKUP_DIR}/${filename} ($backup_size)" | tee -a "$LOG_FILE"
        else
            echo -e "  ${RED}✗ BACKUP FAILED!${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    else
        echo "  ⓘ Database not found (skipping): $db" | tee -a "$LOG_FILE"
    fi
done
echo ""
echo -e "${GREEN}✓ All active databases backed up successfully${NC}" | tee -a "$LOG_FILE"
echo ""

# List of empty/duplicate databases to delete
echo "========================================================================"
echo "STEP 2: DELETING EMPTY/DUPLICATE DATABASES"
echo "========================================================================"
echo "" | tee -a "$LOG_FILE"

DATABASES_TO_DELETE=(
    # Empty duplicates in project root
    "/Users/nickcuskey/ISBN/catalog.db"
    "/Users/nickcuskey/ISBN/isbn_catalog.db"
    "/Users/nickcuskey/ISBN/isbn_optimizer.db"
    "/Users/nickcuskey/ISBN/training_data.db"
    "/Users/nickcuskey/ISBN/metadata_cache.db"

    # Empty duplicates in subdirectories
    "/Users/nickcuskey/ISBN/isbn_lot_optimizer/books.db"
    "/Users/nickcuskey/ISBN/isbn_lot_optimizer/catalog.db"
    "/Users/nickcuskey/ISBN/isbn_lot_optimizer/training.db"
    "/Users/nickcuskey/ISBN/isbn_lot_optimizer/metadata_cache.db"
    "/Users/nickcuskey/ISBN/isbn_lot_optimizer/data/catalog.db"
)

DELETED_COUNT=0
SKIPPED_COUNT=0

for db in "${DATABASES_TO_DELETE[@]}"; do
    if [ -f "$db" ]; then
        size=$(du -h "$db" | cut -f1)
        echo "Checking: $db ($size)" | tee -a "$LOG_FILE"

        # Extra safety: verify it's empty or has 0 records
        record_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM books" 2>/dev/null || \
                      sqlite3 "$db" "SELECT COUNT(*) FROM cached_books" 2>/dev/null || \
                      sqlite3 "$db" "SELECT COUNT(*) FROM training_books" 2>/dev/null || \
                      echo "0")

        if [ "$record_count" = "0" ] || [ ! -s "$db" ]; then
            echo "  → Deleting (empty or 0 records)..." | tee -a "$LOG_FILE"
            rm "$db"
            if [ ! -f "$db" ]; then
                echo -e "  ${GREEN}✓ Deleted successfully${NC}" | tee -a "$LOG_FILE"
                DELETED_COUNT=$((DELETED_COUNT + 1))
            else
                echo -e "  ${RED}✗ Delete failed${NC}" | tee -a "$LOG_FILE"
            fi
        else
            echo -e "  ${YELLOW}⚠ SKIPPED: Contains $record_count records (safety check)${NC}" | tee -a "$LOG_FILE"
            SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        fi
    else
        echo "  ⓘ Not found (already deleted?): $db" | tee -a "$LOG_FILE"
    fi
    echo "" | tee -a "$LOG_FILE"
done

echo "========================================================================"
echo "CLEANUP SUMMARY"
echo "========================================================================"
echo "" | tee -a "$LOG_FILE"
echo "Deleted: $DELETED_COUNT databases" | tee -a "$LOG_FILE"
echo "Skipped (safety check): $SKIPPED_COUNT databases" | tee -a "$LOG_FILE"
echo ""

# List remaining databases in project
echo "Remaining databases in project directory:" | tee -a "$LOG_FILE"
remaining=$(find /Users/nickcuskey/ISBN -name "*.db" -type f -not -path "*/backups/*" -not -path "*/.venv/*" 2>/dev/null | wc -l)
echo "  Total: $remaining" | tee -a "$LOG_FILE"
find /Users/nickcuskey/ISBN -name "*.db" -type f -not -path "*/backups/*" -not -path "*/.venv/*" 2>/dev/null | while read db; do
    size=$(du -h "$db" | cut -f1)
    echo "  - $db ($size)" | tee -a "$LOG_FILE"
done
echo ""

# Verify official databases still exist
echo "Verifying official databases:" | tee -a "$LOG_FILE"
for db in "${ACTIVE_DBS[@]}"; do
    if [ -f "$db" ]; then
        size=$(du -h "$db" | cut -f1)
        echo -e "  ${GREEN}✓${NC} $db ($size)" | tee -a "$LOG_FILE"
    else
        echo -e "  ${RED}✗ MISSING: $db${NC}" | tee -a "$LOG_FILE"
    fi
done
echo ""

echo "========================================================================"
echo "CLEANUP COMPLETE"
echo "========================================================================"
echo "" | tee -a "$LOG_FILE"
echo -e "${GREEN}✓ Database cleanup completed successfully${NC}" | tee -a "$LOG_FILE"
echo ""
echo "Backups saved to: ${BACKUP_DIR}/" | tee -a "$LOG_FILE"
echo "Full log: ${LOG_FILE}" | tee -a "$LOG_FILE"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Verify your applications still work correctly"
echo "2. Complete training_data.db migration (38 missing ISBNs)"
echo "3. Run ml model training to verify everything works"
