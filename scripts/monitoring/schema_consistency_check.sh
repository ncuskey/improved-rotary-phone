#!/bin/bash
#
# Schema Consistency Check
# Verifies that shared fields between catalog.db and metadata_cache.db stay in sync
#
# Schedule with cron (weekly on Sunday):
#   0 7 * * SUN /path/to/schema_consistency_check.sh
#

set -e

CATALOG_DB="${HOME}/.isbn_lot_optimizer/catalog.db"
METADATA_CACHE_DB="${HOME}/.isbn_lot_optimizer/metadata_cache.db"
REPORT_FILE="/tmp/schema_check_$(date +%Y%m%d_%H%M%S).txt"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "SCHEMA CONSISTENCY CHECK"
echo "========================================================================"
echo "Date: $(date)" | tee "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

if [ ! -f "$CATALOG_DB" ]; then
    echo -e "${RED}✗ catalog.db not found at: $CATALOG_DB${NC}" | tee -a "$REPORT_FILE"
    exit 1
fi

if [ ! -f "$METADATA_CACHE_DB" ]; then
    echo -e "${RED}✗ metadata_cache.db not found at: $METADATA_CACHE_DB${NC}" | tee -a "$REPORT_FILE"
    exit 1
fi

ISSUES_FOUND=0

# 1. CHECK FIELD EXISTENCE IN BOTH DATABASES
echo "=== CHECKING SHARED FIELDS ===" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Fields that should exist in both databases
SHARED_FIELDS=(
    "isbn"
    "title"
    "authors"
    "publication_year"
    "cover_type"
    "signed"
    "printing"
    "sold_comps_median"
    "sold_comps_count"
    "market_json"
    "bookscouter_json"
)

echo "Checking for shared fields in both databases..." | tee -a "$REPORT_FILE"

for field in "${SHARED_FIELDS[@]}"; do
    # Check catalog.db
    catalog_has=$(sqlite3 "$CATALOG_DB" "PRAGMA table_info(books);" | grep -c "^[0-9]*|$field|" || echo "0")

    # Check metadata_cache.db
    cache_has=$(sqlite3 "$METADATA_CACHE_DB" "PRAGMA table_info(cached_books);" | grep -c "^[0-9]*|$field|" || echo "0")

    if [ "$catalog_has" = "1" ] && [ "$cache_has" = "1" ]; then
        echo -e "  ${GREEN}✓${NC} $field: Present in both databases" | tee -a "$REPORT_FILE"
    elif [ "$catalog_has" = "1" ] && [ "$cache_has" = "0" ]; then
        echo -e "  ${YELLOW}⚠${NC} $field: Only in catalog.db (MISSING from metadata_cache.db)" | tee -a "$REPORT_FILE"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    elif [ "$catalog_has" = "0" ] && [ "$cache_has" = "1" ]; then
        echo -e "  ${YELLOW}⚠${NC} $field: Only in metadata_cache.db (MISSING from catalog.db)" | tee -a "$REPORT_FILE"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    else
        echo -e "  ${RED}✗${NC} $field: MISSING from both databases" | tee -a "$REPORT_FILE"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
done

echo "" | tee -a "$REPORT_FILE"

# 2. CHECK FOR SCHEMA DRIFT (new columns added to one but not the other)
echo "=== SCHEMA DRIFT DETECTION ===" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Get column counts
CATALOG_COLUMNS=$(sqlite3 "$CATALOG_DB" "PRAGMA table_info(books);" | wc -l)
CACHE_COLUMNS=$(sqlite3 "$METADATA_CACHE_DB" "PRAGMA table_info(cached_books);" | wc -l)

echo "catalog.db books table: $CATALOG_COLUMNS columns" | tee -a "$REPORT_FILE"
echo "metadata_cache.db cached_books table: $CACHE_COLUMNS columns" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Fields that should ONLY be in catalog.db (user-facing features)
CATALOG_ONLY_FIELDS=(
    "status"
    "probability_label"
    "probability_score"
    "probability_reasons"
    "source_json"
    "abebooks_min_price"
    "abebooks_avg_price"
)

# Fields that should ONLY be in metadata_cache.db (training features)
CACHE_ONLY_FIELDS=(
    "training_quality_score"
    "in_training"
    "last_enrichment_at"
    "binding"
    "language"
    "isbn13"
    "isbn10"
    "thumbnail_url"
    "description"
)

echo "Checking catalog-only fields..." | tee -a "$REPORT_FILE"
for field in "${CATALOG_ONLY_FIELDS[@]}"; do
    catalog_has=$(sqlite3 "$CATALOG_DB" "PRAGMA table_info(books);" | grep -c "^[0-9]*|$field|" || echo "0")

    if [ "$catalog_has" = "1" ]; then
        echo -e "  ${GREEN}✓${NC} $field: Present in catalog.db" | tee -a "$REPORT_FILE"
    else
        echo -e "  ${RED}✗${NC} $field: MISSING from catalog.db" | tee -a "$REPORT_FILE"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
done

echo "" | tee -a "$REPORT_FILE"

echo "Checking cache-only fields..." | tee -a "$REPORT_FILE"
for field in "${CACHE_ONLY_FIELDS[@]}"; do
    cache_has=$(sqlite3 "$METADATA_CACHE_DB" "PRAGMA table_info(cached_books);" | grep -c "^[0-9]*|$field|" || echo "0")

    if [ "$cache_has" = "1" ]; then
        echo -e "  ${GREEN}✓${NC} $field: Present in metadata_cache.db" | tee -a "$REPORT_FILE"
    else
        echo -e "  ${YELLOW}⚠${NC} $field: MISSING from metadata_cache.db" | tee -a "$REPORT_FILE"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
done

echo "" | tee -a "$REPORT_FILE"

# 3. DATA SYNC CHECK (sample ISBNs)
echo "=== DATA SYNC CHECK (Sample) ===" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# Get 5 random ISBNs that exist in both databases
COMMON_ISBNS=$(sqlite3 <<EOF
ATTACH DATABASE '$CATALOG_DB' AS catalog;
ATTACH DATABASE '$METADATA_CACHE_DB' AS cache;
SELECT c.isbn
FROM catalog.books c
INNER JOIN cache.cached_books mc ON c.isbn = mc.isbn
WHERE c.cover_type IS NOT NULL OR c.signed IS NOT NULL
LIMIT 5;
EOF
)

if [ -z "$COMMON_ISBNS" ]; then
    echo -e "${YELLOW}⚠ No common ISBNs with attributes found for comparison${NC}" | tee -a "$REPORT_FILE"
else
    echo "Checking attribute consistency for sample ISBNs..." | tee -a "$REPORT_FILE"

    for isbn in $COMMON_ISBNS; do
        # Compare cover_type
        catalog_cover=$(sqlite3 "$CATALOG_DB" "SELECT cover_type FROM books WHERE isbn='$isbn'" 2>/dev/null || echo "NULL")
        cache_cover=$(sqlite3 "$METADATA_CACHE_DB" "SELECT cover_type FROM cached_books WHERE isbn='$isbn'" 2>/dev/null || echo "NULL")

        if [ "$catalog_cover" != "$cache_cover" ]; then
            echo -e "  ${YELLOW}⚠${NC} $isbn: cover_type mismatch (catalog: $catalog_cover, cache: $cache_cover)" | tee -a "$REPORT_FILE"
            ISSUES_FOUND=$((ISSUES_FOUND + 1))
        else
            echo -e "  ${GREEN}✓${NC} $isbn: cover_type in sync" | tee -a "$REPORT_FILE"
        fi
    done
fi

echo "" | tee -a "$REPORT_FILE"

# 4. SUMMARY AND RECOMMENDATIONS
echo "========================================================================"
echo "SUMMARY"
echo "========================================================================"
echo "" | tee -a "$REPORT_FILE"

if [ $ISSUES_FOUND -eq 0 ]; then
    echo -e "${GREEN}✓ All schema consistency checks passed${NC}" | tee -a "$REPORT_FILE"
else
    echo -e "${YELLOW}⚠ Found $ISSUES_FOUND potential issues${NC}" | tee -a "$REPORT_FILE"
    echo "" | tee -a "$REPORT_FILE"
    echo "RECOMMENDATIONS:" | tee -a "$REPORT_FILE"
    echo "1. Review schema changes and ensure both databases are updated together" | tee -a "$REPORT_FILE"
    echo "2. Run migration scripts to sync missing fields" | tee -a "$REPORT_FILE"
    echo "3. Update organic growth sync to include all shared fields" | tee -a "$REPORT_FILE"
fi

echo "" | tee -a "$REPORT_FILE"
echo "Full report saved to: $REPORT_FILE"
echo ""
echo -e "${GREEN}To schedule this check weekly, add to crontab:${NC}"
echo "  0 7 * * SUN $(realpath $0)"
