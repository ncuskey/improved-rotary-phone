#!/bin/bash
#
# Database Diagnostics Script
# Generates comprehensive report on all databases for cleanup planning
#

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_DIR="/tmp/db_diagnostics_${TIMESTAMP}"
mkdir -p "${REPORT_DIR}"

echo "========================================================================"
echo "DATABASE DIAGNOSTICS REPORT"
echo "========================================================================"
echo "Timestamp: $(date)"
echo "Report directory: ${REPORT_DIR}"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Find all .db files
echo "Finding all .db files..."
DB_FILES=$(find /Users/nickcuskey/ISBN -name "*.db" -type f 2>/dev/null | sort)
DB_FILES+=$'\n'$(find ~/.isbn_lot_optimizer -name "*.db" -type f 2>/dev/null | sort)

echo "Found $(echo "$DB_FILES" | wc -l) database files:"
echo "$DB_FILES"
echo ""

echo "========================================================================"
echo "1. FILE SIZE ANALYSIS"
echo "========================================================================"
echo "" | tee "${REPORT_DIR}/01_file_sizes.txt"

for db in $DB_FILES; do
    if [ -f "$db" ]; then
        size=$(du -h "$db" | cut -f1)
        echo "$size    $db" | tee -a "${REPORT_DIR}/01_file_sizes.txt"
    fi
done
echo ""

echo "========================================================================"
echo "2. RECORD COUNTS BY DATABASE"
echo "========================================================================"
echo "" | tee "${REPORT_DIR}/02_record_counts.txt"

for db in $DB_FILES; do
    if [ -f "$db" ]; then
        echo -e "${YELLOW}Database: $db${NC}" | tee -a "${REPORT_DIR}/02_record_counts.txt"

        # Check for books/cached_books table
        books_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM books" 2>/dev/null || echo "0")
        cached_books_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM cached_books" 2>/dev/null || echo "0")
        training_books_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM training_books" 2>/dev/null || echo "0")
        isbn_index_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM isbn_index" 2>/dev/null || echo "0")

        if [ "$books_count" != "0" ]; then
            echo "  books table: $books_count records" | tee -a "${REPORT_DIR}/02_record_counts.txt"
        fi
        if [ "$cached_books_count" != "0" ]; then
            echo "  cached_books table: $cached_books_count records" | tee -a "${REPORT_DIR}/02_record_counts.txt"
        fi
        if [ "$training_books_count" != "0" ]; then
            echo "  training_books table: $training_books_count records" | tee -a "${REPORT_DIR}/02_record_counts.txt"
        fi
        if [ "$isbn_index_count" != "0" ]; then
            echo "  isbn_index table: $isbn_index_count records" | tee -a "${REPORT_DIR}/02_record_counts.txt"
        fi

        if [ "$books_count" = "0" ] && [ "$cached_books_count" = "0" ] && [ "$training_books_count" = "0" ] && [ "$isbn_index_count" = "0" ]; then
            echo -e "  ${RED}EMPTY or UNKNOWN SCHEMA${NC}" | tee -a "${REPORT_DIR}/02_record_counts.txt"
        fi
        echo "" | tee -a "${REPORT_DIR}/02_record_counts.txt"
    fi
done

echo "========================================================================"
echo "3. OFFICIAL DATABASE ANALYSIS"
echo "========================================================================"
echo ""

# catalog.db analysis
CATALOG_DB="${HOME}/.isbn_lot_optimizer/catalog.db"
echo -e "${GREEN}=== catalog.db (Active Inventory) ===${NC}" | tee "${REPORT_DIR}/03_catalog_analysis.txt"
if [ -f "$CATALOG_DB" ]; then
    sqlite3 "$CATALOG_DB" <<EOF | tee -a "${REPORT_DIR}/03_catalog_analysis.txt"
.mode column
.headers on
SELECT
    'Total Books' as metric,
    COUNT(*) as value
FROM books
UNION ALL
SELECT
    'Status=ACCEPT',
    SUM(CASE WHEN status='ACCEPT' THEN 1 ELSE 0 END)
FROM books
UNION ALL
SELECT
    'Status=REJECT',
    SUM(CASE WHEN status='REJECT' THEN 1 ELSE 0 END)
FROM books
UNION ALL
SELECT
    'With Market Data',
    SUM(CASE WHEN market_json IS NOT NULL AND market_json != '{}' THEN 1 ELSE 0 END)
FROM books
UNION ALL
SELECT
    'With BookScouter',
    SUM(CASE WHEN bookscouter_json IS NOT NULL AND bookscouter_json != '{}' THEN 1 ELSE 0 END)
FROM books
UNION ALL
SELECT
    'With Cover Type',
    SUM(CASE WHEN cover_type IS NOT NULL THEN 1 ELSE 0 END)
FROM books
UNION ALL
SELECT
    'With Signed Flag',
    SUM(CASE WHEN signed IS NOT NULL THEN 1 ELSE 0 END)
FROM books
UNION ALL
SELECT
    'With AbeBooks Data',
    SUM(CASE WHEN abebooks_avg_price IS NOT NULL THEN 1 ELSE 0 END)
FROM books;
EOF
else
    echo "  NOT FOUND" | tee -a "${REPORT_DIR}/03_catalog_analysis.txt"
fi
echo ""

# metadata_cache.db analysis
METADATA_CACHE_DB="${HOME}/.isbn_lot_optimizer/metadata_cache.db"
echo -e "${GREEN}=== metadata_cache.db (Training Database) ===${NC}" | tee "${REPORT_DIR}/04_metadata_cache_analysis.txt"
if [ -f "$METADATA_CACHE_DB" ]; then
    sqlite3 "$METADATA_CACHE_DB" <<EOF | tee -a "${REPORT_DIR}/04_metadata_cache_analysis.txt"
.mode column
.headers on
SELECT
    'Total ISBNs' as metric,
    COUNT(*) as value
FROM cached_books
UNION ALL
SELECT
    'Training Eligible (in_training=1)',
    SUM(CASE WHEN in_training=1 THEN 1 ELSE 0 END)
FROM cached_books
UNION ALL
SELECT
    'Avg Quality Score',
    CAST(AVG(training_quality_score) * 1000 AS INTEGER) / 1000.0
FROM cached_books WHERE in_training=1
UNION ALL
SELECT
    'With Market Data',
    SUM(CASE WHEN market_json IS NOT NULL AND market_json != '{}' THEN 1 ELSE 0 END)
FROM cached_books WHERE in_training=1
UNION ALL
SELECT
    'With Cover Type',
    SUM(CASE WHEN cover_type IS NOT NULL THEN 1 ELSE 0 END)
FROM cached_books WHERE in_training=1
UNION ALL
SELECT
    'With Signed Flag',
    SUM(CASE WHEN signed IS NOT NULL THEN 1 ELSE 0 END)
FROM cached_books WHERE in_training=1
UNION ALL
SELECT
    'Stale Market Data (>30 days)',
    SUM(CASE WHEN market_fetched_at IS NULL OR market_fetched_at < datetime('now', '-30 days') THEN 1 ELSE 0 END)
FROM cached_books WHERE in_training=1;
EOF
else
    echo "  NOT FOUND" | tee -a "${REPORT_DIR}/04_metadata_cache_analysis.txt"
fi
echo ""

# training_data.db analysis
TRAINING_DATA_DB="${HOME}/.isbn_lot_optimizer/training_data.db"
echo -e "${YELLOW}=== training_data.db (DEPRECATED) ===${NC}" | tee "${REPORT_DIR}/05_training_data_analysis.txt"
if [ -f "$TRAINING_DATA_DB" ]; then
    training_books=$(sqlite3 "$TRAINING_DATA_DB" "SELECT COUNT(*) FROM training_books" 2>/dev/null || echo "0")
    echo "  Training books: $training_books" | tee -a "${REPORT_DIR}/05_training_data_analysis.txt"

    if [ "$training_books" != "0" ]; then
        echo "  ${YELLOW}WARNING: training_data.db still contains $training_books records${NC}" | tee -a "${REPORT_DIR}/05_training_data_analysis.txt"
        echo "  Checking if they exist in metadata_cache.db..." | tee -a "${REPORT_DIR}/05_training_data_analysis.txt"

        # Check overlap
        missing_count=$(sqlite3 <<EOF
ATTACH DATABASE '$TRAINING_DATA_DB' AS training;
ATTACH DATABASE '$METADATA_CACHE_DB' AS cache;
SELECT COUNT(DISTINCT t.isbn)
FROM training.training_books t
LEFT JOIN cache.cached_books c ON t.isbn = c.isbn
WHERE c.isbn IS NULL;
EOF
)
        echo "  ISBNs in training_data.db NOT in metadata_cache.db: $missing_count" | tee -a "${REPORT_DIR}/05_training_data_analysis.txt"

        if [ "$missing_count" != "0" ]; then
            echo -e "  ${RED}MIGRATION INCOMPLETE: $missing_count ISBNs need to be migrated${NC}" | tee -a "${REPORT_DIR}/05_training_data_analysis.txt"
        else
            echo -e "  ${GREEN}MIGRATION COMPLETE: All ISBNs exist in metadata_cache.db${NC}" | tee -a "${REPORT_DIR}/05_training_data_analysis.txt"
        fi
    fi
else
    echo "  NOT FOUND (already deprecated)" | tee -a "${REPORT_DIR}/05_training_data_analysis.txt"
fi
echo ""

# unified_index.db analysis
UNIFIED_INDEX_DB="${HOME}/.isbn_lot_optimizer/unified_index.db"
echo -e "${GREEN}=== unified_index.db (Deduplication) ===${NC}" | tee "${REPORT_DIR}/06_unified_index_analysis.txt"
if [ -f "$UNIFIED_INDEX_DB" ]; then
    sqlite3 "$UNIFIED_INDEX_DB" <<EOF | tee -a "${REPORT_DIR}/06_unified_index_analysis.txt"
.mode column
.headers on
SELECT
    'Total Indexed ISBNs' as metric,
    COUNT(*) as value
FROM isbn_index
UNION ALL
SELECT
    'Marked in_training',
    SUM(in_training)
FROM isbn_index
UNION ALL
SELECT
    'Marked in_cache',
    SUM(in_cache)
FROM isbn_index;
EOF
else
    echo "  NOT FOUND" | tee -a "${REPORT_DIR}/06_unified_index_analysis.txt"
fi
echo ""

echo "========================================================================"
echo "4. DUPLICATE DATABASE IDENTIFICATION"
echo "========================================================================"
echo "" | tee "${REPORT_DIR}/07_duplicates.txt"

echo -e "${YELLOW}Checking for duplicate databases (same file in multiple locations)...${NC}" | tee -a "${REPORT_DIR}/07_duplicates.txt"
echo ""

# Check for catalog.db duplicates
echo "catalog.db locations:" | tee -a "${REPORT_DIR}/07_duplicates.txt"
find /Users/nickcuskey/ISBN -name "catalog.db" -type f 2>/dev/null | while read db; do
    size=$(du -h "$db" | cut -f1)
    count=$(sqlite3 "$db" "SELECT COUNT(*) FROM books" 2>/dev/null || echo "ERROR")
    echo "  $db ($size, $count records)" | tee -a "${REPORT_DIR}/07_duplicates.txt"
done
echo "" | tee -a "${REPORT_DIR}/07_duplicates.txt"

# Check for metadata_cache.db duplicates
echo "metadata_cache.db locations:" | tee -a "${REPORT_DIR}/07_duplicates.txt"
find /Users/nickcuskey/ISBN -name "metadata_cache.db" -type f 2>/dev/null | while read db; do
    size=$(du -h "$db" | cut -f1)
    count=$(sqlite3 "$db" "SELECT COUNT(*) FROM cached_books" 2>/dev/null || echo "ERROR")
    echo "  $db ($size, $count records)" | tee -a "${REPORT_DIR}/07_duplicates.txt"
done
find ~/.isbn_lot_optimizer -name "metadata_cache.db" -type f 2>/dev/null | while read db; do
    size=$(du -h "$db" | cut -f1)
    count=$(sqlite3 "$db" "SELECT COUNT(*) FROM cached_books" 2>/dev/null || echo "ERROR")
    echo "  $db ($size, $count records)" | tee -a "${REPORT_DIR}/07_duplicates.txt"
done
echo "" | tee -a "${REPORT_DIR}/07_duplicates.txt"

# Check for training_data.db duplicates
echo "training_data.db locations:" | tee -a "${REPORT_DIR}/07_duplicates.txt"
find /Users/nickcuskey/ISBN -name "training_data.db" -type f 2>/dev/null | while read db; do
    size=$(du -h "$db" | cut -f1)
    count=$(sqlite3 "$db" "SELECT COUNT(*) FROM training_books" 2>/dev/null || echo "ERROR")
    echo "  $db ($size, $count records)" | tee -a "${REPORT_DIR}/07_duplicates.txt"
done
echo "" | tee -a "${REPORT_DIR}/07_duplicates.txt"

# List unknown/unclear databases
echo -e "${YELLOW}Unknown/unclear purpose databases:${NC}" | tee -a "${REPORT_DIR}/07_duplicates.txt"
for unknown_db in "isbn_optimizer.db" "isbn_catalog.db" "books.db" "training.db" "book_evaluations.db"; do
    find /Users/nickcuskey/ISBN -name "$unknown_db" -type f 2>/dev/null | while read db; do
        size=$(du -h "$db" | cut -f1)
        echo "  $db ($size)" | tee -a "${REPORT_DIR}/07_duplicates.txt"
    done
done
echo ""

echo "========================================================================"
echo "5. SCHEMA COMPARISON"
echo "========================================================================"
echo "" | tee "${REPORT_DIR}/08_schema_comparison.txt"

echo "catalog.db books table columns:" | tee -a "${REPORT_DIR}/08_schema_comparison.txt"
if [ -f "$CATALOG_DB" ]; then
    sqlite3 "$CATALOG_DB" "PRAGMA table_info(books);" | wc -l | xargs echo "  Total columns:" | tee -a "${REPORT_DIR}/08_schema_comparison.txt"
    sqlite3 "$CATALOG_DB" "PRAGMA table_info(books);" > "${REPORT_DIR}/catalog_schema.txt"
fi
echo ""

echo "metadata_cache.db cached_books table columns:" | tee -a "${REPORT_DIR}/08_schema_comparison.txt"
if [ -f "$METADATA_CACHE_DB" ]; then
    sqlite3 "$METADATA_CACHE_DB" "PRAGMA table_info(cached_books);" | wc -l | xargs echo "  Total columns:" | tee -a "${REPORT_DIR}/08_schema_comparison.txt"
    sqlite3 "$METADATA_CACHE_DB" "PRAGMA table_info(cached_books);" > "${REPORT_DIR}/metadata_cache_schema.txt"
fi
echo ""

# Check for AbeBooks fields in metadata_cache.db
echo "Checking for AbeBooks fields in metadata_cache.db:" | tee -a "${REPORT_DIR}/08_schema_comparison.txt"
if [ -f "$METADATA_CACHE_DB" ]; then
    abebooks_fields=$(sqlite3 "$METADATA_CACHE_DB" "PRAGMA table_info(cached_books);" | grep -i "abebooks" | wc -l)
    if [ "$abebooks_fields" = "0" ]; then
        echo -e "  ${RED}MISSING: No AbeBooks fields found${NC}" | tee -a "${REPORT_DIR}/08_schema_comparison.txt"
    else
        echo -e "  ${GREEN}FOUND: $abebooks_fields AbeBooks fields${NC}" | tee -a "${REPORT_DIR}/08_schema_comparison.txt"
    fi
fi
echo ""

echo "========================================================================"
echo "DIAGNOSTICS COMPLETE"
echo "========================================================================"
echo ""
echo "Full report saved to: ${REPORT_DIR}/"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo "1. Review the report files in ${REPORT_DIR}/"
echo "2. Identify databases safe to delete"
echo "3. Create backups before cleanup"
echo "4. Run database cleanup script"
