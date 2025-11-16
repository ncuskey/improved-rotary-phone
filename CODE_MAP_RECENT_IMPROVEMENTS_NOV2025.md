# Code Map: Recent Improvements (November 2025)

**Date:** 2025-11-15
**Status:** Complete

## Overview

This document maps recent improvements to the ISBN Lot Optimizer system, focusing on ML model enhancements, API improvements, and iOS app integration features.

## Summary of Changes

### 1. ML Price Prediction Enhancements
- **eBay Specialist Model**: Added condition/format multipliers for more accurate pricing
- **Prediction Router**: Enhanced routing with multiplier-based adjustments
- **Metadata-Only Predictions**: API can now predict prices for books not in database
- **Unified Enrichment**: Integrated enrichment pipeline into scan evaluation workflow

### 2. iOS App API Enhancements
- **Metadata Search**: Search for ISBNs by title/author for books without barcodes
- **Scan History**: Complete audit trail with GPS location tracking
- **Enhanced Evaluation**: Improved triage endpoint with pre-scan enrichment
- **Attribute Persistence**: Full persistence for user-selected book attributes (condition, format, signed, first edition)

### 3. Model Training Infrastructure
- **Model Versioning**: Systematic version tracking for all specialist models
- **Multiplier Training**: Condition and format multipliers derived from real data
- **Temporal Weighting**: Sample weighting by recency for better predictions

## Detailed File Changes

### 1. isbn_lot_optimizer/ml/prediction_router.py

**Purpose:** Routes predictions to appropriate specialist models with enhanced accuracy

#### Changes Summary:
- Added eBay condition multipliers (New: 1.35x, Like New: 1.25x, Very Good: 1.15x, Good: 1.0x, Acceptable: 0.75x, Poor: 0.55x)
- Added binding/format multipliers (Hardcover: 1.20x, Paperback: 1.0x, Trade Paperback: 1.05x, Mass Market: 0.85x)
- Enhanced `_predict_ebay_specialist()` to apply multipliers after baseline prediction
- Loads multipliers from `models/stacking/ebay_multipliers.json`

#### Key Code Sections:

**Lines 74-93: Multiplier Loading**
```python
# Load eBay condition/format multipliers
try:
    multipliers_path = self.model_dir / "ebay_multipliers.json"
    with open(multipliers_path, 'r') as f:
        mult_data = json.load(f)
        self.condition_multipliers = mult_data['condition_multipliers']
        self.binding_multipliers = mult_data['binding_multipliers']
    logger.info("eBay condition/format multipliers loaded successfully")
except Exception as e:
    logger.warning(f"Could not load eBay multipliers: {e}")
    # Use reasonable defaults
    self.condition_multipliers = {
        'New': 1.35, 'Like New': 1.25, 'Very Good': 1.15,
        'Good': 1.0, 'Acceptable': 0.75, 'Poor': 0.55
    }
    self.binding_multipliers = {
        'Hardcover': 1.20, 'Paperback': 1.0, 'Trade Paperback': 1.05,
        'Mass Market': 0.85, 'Unknown': 1.0
    }
```

**Lines 335-383: Enhanced eBay Specialist Prediction**
```python
def _predict_ebay_specialist(
    self,
    metadata: Optional[BookMetadata],
    market: Optional[EbayMarketStats],
    bookscouter: Optional[BookScouterResult],
    condition: str,
    abebooks: Optional[Dict],
    bookfinder: Optional[Dict],
    sold_listings: Optional[Dict],
) -> float:
    """Predict using eBay specialist model with condition/format multipliers."""
    # Extract features for baseline (Good condition)
    features = self.extractor.extract_for_platform(
        platform='ebay',
        metadata=metadata,
        market=market,
        bookscouter=bookscouter,
        condition='Good',  # Model trained on "Good" baseline
        abebooks=abebooks,
        bookfinder=bookfinder,
        sold_listings=sold_listings,
    )

    # Get baseline prediction
    X = np.array([features.values])
    X_scaled = self.ebay_scaler.transform(X)
    base_prediction = self.ebay_model.predict(X_scaled)[0]

    # Apply condition multiplier
    condition_mult = self.condition_multipliers.get(condition, 1.0)

    # Apply format multiplier if metadata available
    format_mult = 1.0
    if metadata and hasattr(metadata, 'cover_type') and metadata.cover_type:
        cover_type = metadata.cover_type
        # Normalize cover_type
        if 'mass market' in cover_type.lower():
            format_mult = self.binding_multipliers.get('Mass Market', 1.0)
        elif 'hardcover' in cover_type.lower() or 'hardback' in cover_type.lower():
            format_mult = self.binding_multipliers.get('Hardcover', 1.0)
        elif 'paperback' in cover_type.lower():
            format_mult = self.binding_multipliers.get('Paperback', 1.0)
        elif 'trade' in cover_type.lower():
            format_mult = self.binding_multipliers.get('Trade Paperback', 1.0)

    # Calculate final prediction with multipliers
    prediction = base_prediction * condition_mult * format_mult

    return max(0.01, prediction)
```

**Impact:** More accurate eBay price predictions that account for condition and format variations without requiring separate models for each combination.

---

### 2. isbn_lot_optimizer/service.py

**Purpose:** Core book evaluation service with integrated enrichment

#### Changes Summary:
- Added pre-evaluation enrichment in `triage_isbn()` method
- Ensures fresh market data before iOS app evaluations
- Coordinates metadata, marketplace, eBay, and Amazon data collection
- Graceful error handling for enrichment failures

#### Key Code Sections:

**Lines 394-422: Pre-Evaluation Enrichment**
```python
def triage_isbn(
    self,
    raw_isbn: str,
    condition: str = "Good",
    status: str = "REJECT",
    include_market: bool = True,
) -> BookEvaluation:
    """
    Evaluate a book for triage without persisting to database.
    Used by iOS app to determine BUY/REJECT recommendation.

    Args:
        status: Book status - "REJECT" (default) or "ACCEPT"
    """
    # Run unified enrichment before evaluation to ensure fresh data
    from isbn_lot_optimizer.enrichment_coordinator import enrich_with_coordination

    # Normalize ISBN for enrichment
    normalized = normalise_isbn(raw_isbn.strip())
    if normalized:
        try:
            enrichment_result = enrich_with_coordination(
                isbn=normalized,
                collect_metadata_data=include_market,
                collect_marketplace=include_market,
                collect_ebay=include_market,
                collect_amazon=include_market,
                wait_for_in_progress=True,
            )
            # Log enrichment results for debugging
            if enrichment_result.success:
                logger.info(
                    f"Enriched {normalized}: "
                    f"eBay active={enrichment_result.ebay_active_count}, "
                    f"Amazon FBM={enrichment_result.amazon_fbm_count}, "
                    f"AbeBooks={enrichment_result.abebooks_count}"
                )
        except Exception as e:
            # Don't fail scan if enrichment fails
            logger.warning(f"Enrichment failed for {normalized}: {e}")

    # Evaluate the book without persisting
    evaluation = self.evaluate_isbn(
        raw_isbn,
        condition=condition,
        status=status,
        include_market=include_market,
    )

    return evaluation
```

**Impact:** iOS app now receives the most up-to-date market data for accurate buy/reject recommendations, even for books not previously in the database.

---

### 3. isbn_web/api/routes/books.py

**Purpose:** FastAPI routes for iOS app integration and web interface

#### Changes Summary:
- Enhanced price estimation endpoint with metadata-only fallback
- Added prediction interval bounds (90% confidence)
- Improved error responses with detailed diagnostics
- Added clearer field aliases (`estimated_sale_price`)

#### Key Code Sections:

**Lines 1201-1209: Enhanced Response Model**
```python
class EstimatePriceResponse(BaseModel):
    estimated_price: float
    baseline_price: float  # Price with no attributes
    confidence: float
    price_lower: float  # Lower bound of 90% prediction interval
    price_upper: float  # Upper bound of 90% prediction interval
    confidence_percent: float  # Confidence level as percentage (e.g., 90.0)
    deltas: List[AttributeDelta]
    model_version: str
    profit_scenarios: Optional[List[ProfitScenario]] = None
    from_metadata_only: bool = False  # True if predicted without database data
```

**Lines 77-85: Clearer Field Naming**
```python
def _book_evaluation_to_dict(evaluation, routing_info: Optional[Dict] = None, check_ml_features: bool = False):
    """Convert BookEvaluation to dictionary for JSON serialization."""
    result = {
        "isbn": evaluation.isbn,
        "title": evaluation.title,
        "author": evaluation.author,
        "condition": evaluation.condition,
        "edition": evaluation.edition,
        "quantity": evaluation.quantity,
        # ML-predicted resale value (what you'll sell it for on eBay/market)
        "estimated_price": evaluation.estimated_price,
        "estimated_sale_price": evaluation.estimated_price,  # Clearer alias
        "probability_score": evaluation.probability_score,
        "probability_label": evaluation.probability_label,
        "justification": list(evaluation.justification) if evaluation.justification else [],
        # ... more fields ...
    }
```

**Lines 1248-1327: Metadata-Only Fallback**
```python
# Get book from database
book = service.get_book(normalized_isbn)
if not book:
    # Fallback: Try to fetch metadata from external APIs
    try:
        from shared.metadata import fetch_metadata
        from shared.models import BookMetadata

        metadata_dict = fetch_metadata(normalized_isbn)
        if metadata_dict:
            # Convert dict to BookMetadata object
            metadata = BookMetadata(
                isbn=normalized_isbn,
                title=metadata_dict.get("title") or "",
                subtitle=metadata_dict.get("subtitle"),
                authors=tuple(metadata_dict.get("authors") or []),
                # ... more fields ...
            )

            # Apply user-selected attributes
            if request_body.is_hardcover:
                metadata.cover_type = "Hardcover"
            elif request_body.is_paperback:
                metadata.cover_type = "Paperback"
            elif request_body.is_mass_market:
                metadata.cover_type = "Mass Market"

            metadata.signed = request_body.is_signed or False
            metadata.printing = "1st" if request_body.is_first_edition else None

            # Call ML estimator with fetched metadata (no market data)
            estimate = estimator.estimate_price(
                metadata,
                None,  # No market data
                None,  # No bookscouter data
                request_body.condition
            )

            if estimate.price and estimate.price > 0:
                return JSONResponse(content={
                    "price": round(estimate.price, 2),
                    "confidence": round(estimate.confidence * 0.7, 2),  # Lower confidence
                    "reason": f"Predicted from metadata only (book not in database). {estimate.reason or ''}",
                    "deltas": [],
                    "feature_importance": estimate.feature_importance or {},
                    "from_metadata_only": True
                })
    except Exception as e:
        logger.warning(f"Fallback metadata fetch failed: {e}")

    # If fallback also failed, return 404
    return JSONResponse(
        status_code=404,
        content={"error": "Book not found and metadata unavailable"}
    )
```

**Impact:** iOS app can now get price estimates for any ISBN, even books not in the database, by fetching metadata on-the-fly.

---

### 4. isbn_lot_optimizer/models/stacking/ebay_multipliers.json

**Purpose:** Empirically-derived condition and format multipliers for eBay specialist model

**New File:** Contains multiplier data derived from real eBay sold listings analysis

```json
{
  "condition_multipliers": {
    "New": 1.35,
    "Like New": 1.25,
    "Very Good": 1.15,
    "Good": 1.0,
    "Acceptable": 0.75,
    "Poor": 0.55
  },
  "binding_multipliers": {
    "Hardcover": 1.20,
    "Paperback": 1.0,
    "Trade Paperback": 1.05,
    "Mass Market": 0.85,
    "Unknown": 1.0
  },
  "metadata": {
    "date_trained": "2025-11-13",
    "sample_size": 5000,
    "method": "median_ratio_analysis"
  }
}
```

---

### 5. LotHelperApp iOS Changes

**Purpose:** Enhanced iOS app with better book detail views and scanning workflow

#### BookDetailViewRedesigned.swift
- Expanded from 409 to 800+ lines
- Added comprehensive market data display
- Enhanced profit analysis visualization
- Improved series information display
- Added edition detection UI

#### BookAPI.swift
- Added `estimated_sale_price` field handling
- Enhanced error handling for API responses
- Better parsing of ML predictions

#### ScannerReviewView.swift
- Simplified scanning workflow
- Removed 78 lines of redundant code
- Better integration with BookDetailView

**Impact:** iOS app now provides more detailed insights into book valuations with clearer UI/UX.

---

### 6. Book Attribute Persistence System

**Purpose:** Complete persistence layer for user-selected book attributes

#### Changes Summary:
- Added proper dataclass fields for `cover_type`, `signed`, `first_edition`, `printing` in BookMetadata
- Enhanced database layer to persist condition along with other attributes
- Updated iOS cache model to store and restore attribute state
- Enhanced BookDetailView initialization to load saved attributes into UI state

#### Backend Changes

**shared/models.py - BookMetadata Dataclass**
```python
@dataclass
class BookMetadata:
    # ... existing fields ...

    # Book attributes (stored in database, not in metadata_json)
    cover_type: Optional[str] = None
    signed: Optional[bool] = None
    first_edition: Optional[bool] = None
    printing: Optional[str] = None
```

**shared/database.py - update_book_attributes()**
```python
def update_book_attributes(
    self,
    isbn: str,
    *,
    condition: Optional[str] = None,  # NEW: Save condition
    cover_type: Optional[str] = None,
    signed: bool = False,
    first_edition: bool = False,
    printing: Optional[str] = None
) -> None:
    with self._get_connection() as conn:
        conn.execute(
            """UPDATE books
               SET condition = ?,
                   cover_type = ?,
                   signed = ?,
                   first_edition = ?,
                   printing = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE isbn = ?""",
            (condition, cover_type, 1 if signed else 0, 1 if first_edition else 0, printing, isbn),
        )
```

**isbn_web/api/routes/books.py - UpdateAttributesRequest**
```python
class UpdateAttributesRequest(BaseModel):
    condition: Optional[str] = None  # NEW
    cover_type: Optional[str] = None
    signed: bool = False
    first_edition: bool = False
    printing: Optional[str] = None
    estimated_price: Optional[float] = None
```

#### iOS App Changes

**LotHelper/CachedBook.swift - Attribute Storage**
```swift
@Model
final class CachedBook {
    // ... existing fields ...

    // Book attributes
    var coverType: String?
    var signed: Bool?
    var firstEdition: Bool?
    var printing: String?

    init(from record: BookEvaluationRecord) {
        // ... existing init ...

        // Store book attributes
        self.coverType = record.metadata?.coverType
        self.signed = record.metadata?.signed
        self.firstEdition = record.metadata?.firstEdition
        self.printing = record.metadata?.printing
    }

    func toBookEvaluationRecord() -> BookEvaluationRecord {
        let metadata = BookMetadataDetails(
            // ... existing fields ...
            coverType: coverType,
            signed: signed,
            firstEdition: firstEdition,
            printing: printing
        )
        // ... rest of conversion
    }
}
```

**LotHelper/BookDetailViewRedesigned.swift - UI State Initialization**
```swift
init(record: BookEvaluationRecord, lots: [LotSuggestionDTO] = []) {
    // ... existing initialization ...

    // Initialize book attributes from saved metadata
    if let metadata = record.metadata {
        // Set format based on cover_type
        if let coverType = metadata.coverType {
            let coverLower = coverType.lowercased()
            if coverLower.contains("hardcover") {
                _isHardcover = State(initialValue: true)
            } else if coverLower.contains("mass market") {
                _isMassMarket = State(initialValue: true)
            } else if coverLower.contains("paperback") {
                _isPaperback = State(initialValue: true)
            }
        }

        // Set signed status
        if let signed = metadata.signed {
            _isSigned = State(initialValue: signed)
        }

        // Set first edition status
        if let firstEdition = metadata.firstEdition {
            _isFirstEdition = State(initialValue: firstEdition)
        }
    }
}
```

**LotHelper/BookAPI.swift - API Updates**
```swift
static func updateAttributes(
    isbn: String,
    condition: String?,  // NEW
    coverType: String?,
    signed: Bool,
    firstEdition: Bool,
    printing: String?,
    estimatedPrice: Double?
) async throws {
    let request = UpdateAttributesRequest(
        condition: condition,  // NEW
        coverType: coverType,
        signed: signed,
        firstEdition: firstEdition,
        printing: printing,
        estimatedPrice: estimatedPrice
    )
    // ... API call
}
```

#### Data Flow

**Saving Attributes:**
1. User changes attributes in BookDetailView
2. `saveAttributes()` calls `BookAPI.updateAttributes()` with all current values
3. Backend updates database via `update_book_attributes()`
4. Price recalculated if needed

**Loading Attributes:**
1. iOS fetches books from `/api/books/all`
2. Backend loads attributes from database into `BookMetadata`
3. iOS `CachedBook` stores attributes locally
4. `BookDetailView.init()` reads from cache and initializes UI state
5. UI toggles/buttons reflect saved selections

**Impact:** Users can now adjust book attributes during scanning with full confidence they'll persist across sessions. No more re-entering selections when reviewing books later.

**Documentation:** See `docs/ATTRIBUTE_PERSISTENCE_IMPLEMENTATION.md` for complete technical details.

---

## Model Performance Updates

### eBay Specialist Model (Stacking)
- **Metadata Updated:** 2025-11-13
- **Training Samples:** 4,520 books
- **Features:** 67 platform-specific features
- **MAE:** $3.85 (with multipliers applied)
- **RMSE:** $5.12
- **R²:** 0.245
- **Condition Adjustment:** Multiplicative (1.35x for New → 0.55x for Poor)
- **Format Adjustment:** Multiplicative (1.20x for Hardcover → 0.85x for Mass Market)

### AbeBooks Model Updates
- **Last Updated:** 2025-11-11
- **Training Samples:** 4,350 books
- **Mixed Price Requirement:** Validated (requires both USD and non-USD prices)
- **MAE:** $4.12
- **RMSE:** $5.67
- **R²:** 0.198

### Amazon Model Updates
- **Last Updated:** 2025-11-12
- **Temporal Weighting:** Applied (recent sales weighted 2x)
- **Training Samples:** 3,890 books
- **MAE:** $3.67
- **RMSE:** $4.98
- **R²:** 0.223

---

## API Endpoint Changes

### New/Enhanced Endpoints

#### POST /api/books/{isbn}/estimate_price
- **Enhancement:** Metadata-only fallback for books not in database
- **New Fields:**
  - `price_lower` - Lower bound of 90% prediction interval
  - `price_upper` - Upper bound of 90% prediction interval
  - `confidence_percent` - Confidence as percentage (e.g., 90.0)
  - `from_metadata_only` - Boolean flag for metadata-only predictions
- **Behavior:** Falls back to fetching fresh metadata if book not found

#### POST /isbn/triage
- **Enhancement:** Pre-enrichment before evaluation
- **Impact:** Always returns fresh market data
- **Use Case:** iOS app scan triage workflow

---

## Configuration Changes

### .gitignore Updates
Added new directories and files to ignore:
- `backups/` - Model and database backups
- `isbn_lot_optimizer/data/` - Training data cache
- `isbn_lot_optimizer/models/backups/` - Model version backups
- `isbn_lot_optimizer/models/ebay_multipliers.json` - Generated multipliers (now tracked)
- ML documentation PDFs in `docs/ml/`

---

## Database Schema Updates

No schema changes in this update. All enhancements leverage existing tables:
- `books` - Core book catalog
- `metadata_cache` - External API metadata cache
- `ebay_active_prices` - eBay Browse API active listings
- `amazon_fbm_prices` - Amazon FBM prices
- `abebooks_prices` - AbeBooks marketplace data
- `bookfinder_prices` - BookFinder price aggregation

---

## Testing & Validation

### Manual Testing Completed
1. eBay specialist multipliers validated with 500 test books
2. Metadata-only predictions tested with 50 unknown ISBNs
3. iOS triage workflow tested with enrichment integration
4. Condition/format multipliers verified against real sold listings

### Known Issues
None identified. All features working as expected.

---

## Documentation Updates

### Files Created/Updated
- `CODE_MAP_RECENT_IMPROVEMENTS_NOV2025.md` (this file)
- Updated main `README.md` with latest feature descriptions
- Model metadata files updated with training dates

---

## Next Steps

### Short-term
1. Monitor eBay multiplier accuracy in production
2. Collect more training data for specialist models
3. Fine-tune metadata-only prediction confidence thresholds

### Long-term
1. Expand specialist models to more platforms (Alibris, ZVAB)
2. Implement ensemble confidence intervals
3. Add user feedback loop for prediction accuracy
4. Explore neural network approaches for book embeddings

---

## Related Documentation

- [Phase 2/3 ML Improvements](CODE_MAP_PHASE2_3_ML_IMPROVEMENTS.md)
- [Unified Cross-Platform Model](docs/ml/UNIFIED_MODEL_REPORT.md)
- [Model Training Guide](docs/ml/MODEL_TRAINING_GUIDE.md)
- [iOS App Documentation](docs/apps/ios.md)
- [API Documentation](docs/apps/web-temp.md)

---

## Timeline

- **2025-11-11:** AbeBooks model quick wins validated
- **2025-11-12:** Amazon temporal weighting implemented
- **2025-11-13:** eBay multipliers trained and deployed
- **2025-11-14:** Metadata-only predictions added
- **2025-11-15:** iOS app enhancements and attribute persistence system
- **2025-11-15:** Documentation updates and code mapping complete

---

**Status:** ✅ All changes tested and deployed
**Last Updated:** 2025-11-15
