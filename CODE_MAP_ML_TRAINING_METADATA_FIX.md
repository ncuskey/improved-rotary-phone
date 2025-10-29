# Code Map: ML Training Data & Metadata Fix

**Date**: October 29, 2025
**Feature**: Strategic ML training data collection with critical metadata fix
**Status**: ✅ Complete - Model improved 13.3% from baseline

---

## Overview

This code map documents the strategic ML training data collection system and the critical metadata fix that unlocked model improvements.

**Key Achievement**: Discovered and fixed metadata gap where 152 strategically collected books had NULL physical attributes, preventing model from learning hardcover/signed/first edition premiums.

---

## Core Components

### 1. Training Data Collection System

#### `scripts/collect_training_data_poc.py`
**Purpose**: Collect books with high-quality eBay sold comps for ML training

**Key Methods**:
- `extract_physical_attributes(metadata)` - **NEW**: Extract cover_type, signed, printing from metadata
  - Uses collection category as primary source
  - Parses titles for keywords ("First Edition", "Signed", "Hardcover")
  - Checks Google Books binding field
- `collect_book_data(isbn)` - Fetch metadata, market data, BookScouter data
- `check_sold_comps(isbn)` - Validate book has sufficient comps (5+)
- `store_book(book_data)` - Save to training_data.db with extracted attributes

**Usage**:
```bash
python3 scripts/collect_training_data_poc.py \
  --category signed_hardcover \
  --limit 50 \
  --isbn-file /tmp/signed_isbns.txt
```

**Categories Supported**:
- `first_edition_hardcover` - First edition hardcover books
- `signed_hardcover` - Signed/autographed hardcover books
- `mass_market_paperback` - Mass market paperback editions

**Data Sources**:
1. eBay Finding API (Track B - active listing estimates)
2. Google Books / OpenLibrary (metadata)
3. BookScouter (Amazon rank, offers) - optional

**Location**: `scripts/collect_training_data_poc.py:243-314` (extract_physical_attributes)

---

#### `scripts/backfill_training_metadata.py`
**Purpose**: Fix metadata for existing 152 books that had NULL physical attributes

**Key Functions**:
- `infer_from_category(category)` - Infer attributes from collection category
- `parse_title_for_attributes(title)` - Parse title for keywords
- `parse_binding_field(binding)` - Parse Google Books binding
- `infer_metadata(category, metadata_json)` - Combine all sources
- `backfill_metadata(dry_run)` - Apply updates to database

**Results**:
- Updated 55 books with metadata
- 45 hardcovers (29.6%)
- 12 signed (7.9%)
- 33 first editions (21.7%)

**Usage**:
```bash
# Dry run to preview changes
python3 scripts/backfill_training_metadata.py --dry-run

# Apply changes
python3 scripts/backfill_training_metadata.py
```

**Location**: `scripts/backfill_training_metadata.py`

---

#### `scripts/discover_isbns_curated.py`
**Purpose**: Generate curated ISBN lists for targeted collection

**ISBN Sources**:
- Popular series (Harry Potter, Twilight, Hunger Games)
- Award winners (Pulitzer, National Book Award, Hugo)
- Bestsellers (Colleen Hoover, Taylor Jenkins Reid, Kristin Hannah)
- Classic literature (Gatsby, Mockingbird, Orwell)
- Genre series (Jack Reacher, Alex Cross, Millennium trilogy)

**Total ISBNs**: 300+ across multiple rounds

**Usage**:
```bash
python3 scripts/discover_isbns_curated.py \
  --category first_edition_hardcover \
  --limit 100 \
  --output /tmp/first_edition_isbns.txt
```

**Location**: `scripts/discover_isbns_curated.py`

---

#### `scripts/migrate_catalog_to_training.py`
**Purpose**: Migrate books from catalog.db to training_data.db

**Selection Criteria**:
- 8+ eBay sold comps
- $5+ median price
- Has complete metadata

**Usage**:
```bash
python3 scripts/migrate_catalog_to_training.py \
  --limit 100 \
  --threshold 8
```

**Results**: Migrated 100 books from catalog (Phase 2)

**Location**: `scripts/migrate_catalog_to_training.py`

---

### 2. Model Training System

#### `scripts/train_price_model.py`
**Purpose**: Train XGBoost price estimation model

**Key Changes**:
- Loads from both catalog.db (742 books) and training_data.db (152 books)
- Lowered threshold to 5+ comps (for Track B estimates)
- Extracts cover_type, signed, printing from dedicated fields

**Training Configuration**:
```python
XGBRegressor(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_alpha=1.0,    # L1 regularization
    reg_lambda=1.0,   # L2 regularization
)
```

**Usage**:
```bash
python3 scripts/train_price_model.py
```

**Output**: Saves model to `isbn_lot_optimizer/models/price_v1.pkl`

**Location**: `scripts/train_price_model.py:66-117` (load_training_data)

---

#### `isbn_lot_optimizer/ml/feature_extractor.py`
**Purpose**: Extract numerical features from book data for ML model

**Physical Attribute Features** (lines 184-205):
```python
# Reads from metadata object attributes
cover_type = getattr(metadata, 'cover_type', None)
features["is_hardcover"] = 1 if cover_type == "Hardcover" else 0
features["is_paperback"] = 1 if cover_type == "Paperback" else 0
features["is_mass_market"] = 1 if cover_type == "Mass Market" else 0
features["is_signed"] = 1 if getattr(metadata, 'signed', False) else 0
features["is_first_edition"] = 1 if getattr(metadata, 'printing', None) == "1st" else 0
```

**Critical**: This is why metadata fix was necessary - feature extractor expects dedicated fields, not JSON blobs.

**Location**: `isbn_lot_optimizer/ml/feature_extractor.py:184-205`

---

#### `isbn_lot_optimizer/collection_strategies.py`
**Purpose**: Define collection targets and priorities

**Priority 1 Categories** (updated with Track B threshold):
```python
CollectionTarget(
    category='signed_hardcover',
    min_comps=5,  # Lowered for Track B estimates
    target_count=200,
    priority=1,
)

CollectionTarget(
    category='first_edition_hardcover',
    min_comps=5,  # Lowered for Track B estimates
    target_count=400,
    priority=1,
)

CollectionTarget(
    category='mass_market_paperback',
    min_comps=5,  # Lowered for Track B estimates
    target_count=150,
    priority=1,
)
```

**Location**: `isbn_lot_optimizer/collection_strategies.py`

---

### 3. Database Schema

#### Training Data Database: `~/.isbn_lot_optimizer/training_data.db`

**Table**: `training_books`

```sql
CREATE TABLE training_books (
    isbn TEXT PRIMARY KEY,
    title TEXT,
    authors TEXT,
    publication_year INTEGER,

    -- Physical attributes (FIX: Now properly populated)
    cover_type TEXT,              -- 'Hardcover', 'Paperback', 'Mass Market'
    printing TEXT,                -- '1st', '2nd', etc.
    signed INTEGER DEFAULT 0,     -- 1 if signed/autographed
    page_count INTEGER,

    -- Price data (ground truth for training)
    sold_avg_price REAL,
    sold_median_price REAL,
    sold_count INTEGER,

    -- JSON data blobs
    metadata_json TEXT,           -- Full metadata from Google Books
    market_json TEXT,             -- eBay market stats
    bookscouter_json TEXT,        -- Amazon/BookScouter data

    -- Collection metadata
    collection_category TEXT,      -- Category collected under
    collection_priority INTEGER,
    comp_quality_score REAL,

    -- Timestamps
    collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**Current State**:
- 152 books total
- 45 hardcovers (29.6%)
- 10 mass market (6.6%)
- 12 signed (7.9%)
- 33 first editions (21.7%)

---

## Model Performance

### Progressive Training Results

| Phase | Training Books | Test MAE | Test R² | Notes |
|-------|----------------|----------|---------|-------|
| Baseline | 0 | $3.75 | -0.027 | Original - useless |
| Phase 1 | 23 | $3.96 | 0.165 | First improvement |
| Phase 2 | 100 | $3.40 | 0.159 | Better MAE |
| Phase 3 | 135 | $3.42 | 0.229 | Strong R² |
| Phase 4 | 152 | $3.29 | 0.216 | Before metadata fix |
| **Phase 4 Corrected** | **152** | **$3.25** | **0.227** | ⭐ After metadata fix |

**Total Improvement**: 13.3% better MAE, R² from -0.027 to 0.227 (explains 22.7% of variance!)

---

## Critical Bug Fixed

### The Metadata Gap

**Problem**: All 152 training_data books had NULL physical attributes
- `cover_type`: NULL (0 books had format recorded)
- `signed`: 0 (0 books marked as signed)
- `printing`: NULL (0 books had edition recorded)

**Root Cause**: POC collector stored `metadata_json` blob but didn't populate dedicated `cover_type/signed/printing` fields that feature extractor reads.

**Impact**: Model couldn't learn hardcover/signed/first edition premiums despite strategic collection targeting these attributes.

**Fix**:
1. Created backfill script to infer attributes from category/title/binding
2. Enhanced POC collector to extract attributes during collection
3. Retrained model with corrected metadata

**Result**: MAE improved $3.29 → $3.25 (1.2%), R² improved 0.216 → 0.227 (5%)

---

## Documentation

### `MODEL_RETRAIN_RESULTS.md`
**Purpose**: Track progressive model improvements across phases

**Sections**:
- Progressive training results (baseline → Phase 4)
- Feature importance evolution
- Phase-by-phase collection details
- Phase 4 metadata fix analysis

### `TRAINING_DATA_DEFICIENCY_ANALYSIS.md`
**Purpose**: Comprehensive analysis of training data gaps

**Deficiencies Identified**:
1. **NULL physical attributes** (CRITICAL) - Fixed ✅
2. **Price range imbalance** - 62% in $5-10 range, only 9% $15+
3. **Format coverage gaps** - 0 trade paperbacks, 10 mass market
4. **Genre balance** - Fiction heavy, limited non-fiction/textbooks

**Recommendations**: Targeted collection of 80-110 books across 3 priorities

### `EBAY_API_FIX.md`
**Purpose**: Document eBay API investigation and Track B solution

**Key Findings**:
- Track A (Marketplace Insights) - Application rejected
- Track B (active listing estimates) - Working, 5-42 comps per book
- POC collector fixed to load .env for credentials

---

## Integration Points

### iOS App Integration
**File**: `LotHelperApp/LotHelper/BookAPI.swift`

Model called via `/api/books/{isbn}/estimate` endpoint:
```swift
struct PriceEstimate: Codable {
    let estimated_price: Double
    let model_version: String
    let confidence: String  // "low", "medium", "high"
}
```

### Python API Integration
**File**: `isbn_lot_optimizer/ml/estimator.py`

```python
from isbn_lot_optimizer.ml.estimator import get_ml_estimator

estimator = get_ml_estimator()
price = estimator.estimate_price(metadata, market, bookscouter, condition)
```

---

## Testing

### Validation Scripts
- `scripts/audit_training_data_lots.py` - Audit training data quality
- Manual validation via retraining and comparing metrics

### Test Coverage
See `tests/TEST_SUITE_SUMMARY.md` for comprehensive test documentation

---

## Next Steps

### Phase 2 Targeted Collection (Planned)

**Priority 1: Price Range Balance** (30-40 books, $15-35 range)
- Collectible signed first editions
- Out-of-print hardcovers
- Special editions

**Priority 2: Format Coverage** (30-40 books)
- 20 trade paperbacks (currently 0!)
- 15 more mass market
- 10 more signed books

**Priority 3: Genre Balance** (20-30 books)
- 15 non-fiction (business, biography, history)
- 5-10 textbooks
- 5 children's books

**Expected Results**: MAE → $2.90-3.10 (18-23% total improvement), R² → 0.30-0.35

---

## Key Learnings

1. **Metadata quality is critical** - JSON blobs alone aren't enough, must extract to dedicated fields
2. **Validation is essential** - Always verify data quality before training
3. **Strategic collection works** - Targeted collection + proper metadata extraction yields measurable improvements
4. **Track B (estimates) are good enough** - Don't need real sold data (Track A) to make progress
5. **Curated ISBNs effective** - Popular books/series have better comp availability

---

## File Locations

**Scripts**:
- `scripts/collect_training_data_poc.py` - POC collector (enhanced)
- `scripts/backfill_training_metadata.py` - Metadata backfill (new)
- `scripts/discover_isbns_curated.py` - ISBN discovery (new)
- `scripts/migrate_catalog_to_training.py` - Catalog migration (new)
- `scripts/train_price_model.py` - Model training (enhanced)

**Core Code**:
- `isbn_lot_optimizer/ml/feature_extractor.py` - Feature extraction
- `isbn_lot_optimizer/ml/estimator.py` - ML estimator interface
- `isbn_lot_optimizer/collection_strategies.py` - Collection targets

**Documentation**:
- `MODEL_RETRAIN_RESULTS.md` - Training results
- `TRAINING_DATA_DEFICIENCY_ANALYSIS.md` - Deficiency analysis
- `EBAY_API_FIX.md` - API investigation

**Database**:
- `~/.isbn_lot_optimizer/training_data.db` - Training books (152 total)
- `~/.isbn_lot_optimizer/catalog.db` - Catalog books (742 total)

**Models**:
- `isbn_lot_optimizer/models/price_v1.pkl` - Trained XGBoost model
- `isbn_lot_optimizer/models/scaler_v1.pkl` - Feature scaler
- `isbn_lot_optimizer/models/metadata.json` - Model metadata
