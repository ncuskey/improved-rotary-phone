#!/bin/bash
#
# Enhanced Enrichment Workflow with Signed Book Sync
#
# This script runs the complete data enrichment and signed book sync workflow.
# It ensures training data has the latest signed book information before model training.
#
# Usage:
#   ./scripts/enrich_and_sync_workflow.sh [--skip-enrichment] [--skip-sync]
#

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Flags
SKIP_ENRICHMENT=false
SKIP_SYNC=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --skip-enrichment)
            SKIP_ENRICHMENT=true
            shift
            ;;
        --skip-sync)
            SKIP_SYNC=true
            shift
            ;;
        --help)
            echo "Enhanced Enrichment Workflow with Signed Book Sync"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --skip-enrichment    Skip market data enrichment step"
            echo "  --skip-sync          Skip signed book sync step"
            echo "  --help               Show this help message"
            echo ""
            exit 0
            ;;
    esac
done

echo -e "${BLUE}================================================================================${NC}"
echo -e "${BLUE}ENHANCED ENRICHMENT WORKFLOW${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo ""

# Step 1: Market Data Enrichment
if [ "$SKIP_ENRICHMENT" = false ]; then
    echo -e "${GREEN}[1/2] Running market data enrichment...${NC}"
    echo ""

    if [ -f "scripts/enrich_metadata_cache_market_data.py" ]; then
        python3 scripts/enrich_metadata_cache_market_data.py
        echo ""
        echo -e "${GREEN}✓ Market data enrichment complete${NC}"
    else
        echo -e "${YELLOW}⚠ Enrichment script not found, skipping...${NC}"
    fi
else
    echo -e "${YELLOW}[1/2] Skipping market data enrichment (--skip-enrichment)${NC}"
fi

echo ""

# Step 2: Signed Book Status Sync
if [ "$SKIP_SYNC" = false ]; then
    echo -e "${GREEN}[2/2] Syncing signed book status to training data...${NC}"
    echo ""

    if [ -f "scripts/sync_signed_status_to_training.py" ]; then
        python3 scripts/sync_signed_status_to_training.py
        echo ""
        echo -e "${GREEN}✓ Signed book sync complete${NC}"
    else
        echo -e "${RED}✗ Sync script not found: scripts/sync_signed_status_to_training.py${NC}"
        echo -e "${YELLOW}  Run from project root to install${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}[2/2] Skipping signed book sync (--skip-sync)${NC}"
fi

echo ""
echo -e "${BLUE}================================================================================${NC}"
echo -e "${BLUE}WORKFLOW COMPLETE${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo -e "  1. Train/retrain models: ${YELLOW}python3 scripts/stacking/train_ebay_model.py${NC}"
echo -e "  2. Test predictions:     ${YELLOW}curl -X POST http://localhost:8111/api/books/{ISBN}/estimate_price${NC}"
echo ""
