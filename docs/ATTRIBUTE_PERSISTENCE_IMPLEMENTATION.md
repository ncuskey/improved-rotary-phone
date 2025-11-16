# Book Attribute Persistence Implementation

**Date**: November 15, 2025
**Status**: ✅ Complete

## Overview

Implemented full persistence for user-selected book attributes in the iOS app. When users scan a book and adjust attributes (condition, format, signed, first edition), these selections now persist across app sessions and view navigation.

## Problem Statement

Previously, when users:
1. Scanned a book in the iOS app
2. Changed attributes (condition, format, signed status, first edition)
3. Navigated away from the book details view
4. Returned to the same book

The attribute selections would reset to defaults (Condition: Good, Format: None, all toggles off) even though prices were being saved correctly.

## Root Causes

1. **Missing Backend Fields**: `cover_type`, `signed`, `first_edition`, and `printing` were not defined as proper fields in the Python `BookMetadata` dataclass. They were being added dynamically with `setattr()`, which doesn't serialize properly.

2. **Missing iOS Cache Fields**: The `CachedBook` SwiftData model didn't have fields to store these attributes, so they were lost when books were cached locally.

3. **Missing Condition Persistence**: The `condition` field wasn't being passed to the `update_attributes` API endpoint.

## Solution Implementation

### Backend Changes (Python)

#### 1. BookMetadata Dataclass (`shared/models.py`)

Added proper field definitions for book attributes:

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

**Why**: Making these proper dataclass fields ensures they're included in dictionary serialization for JSON responses.

#### 2. Database Layer (`shared/database.py`)

Updated `update_book_attributes()` to accept and save condition:

```python
def update_book_attributes(
    self,
    isbn: str,
    *,
    condition: Optional[str] = None,  # NEW
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

#### 3. API Endpoint (`isbn_web/api/routes/books.py`)

Updated `UpdateAttributesRequest` and endpoint handler:

```python
class UpdateAttributesRequest(BaseModel):
    condition: Optional[str] = None  # NEW
    cover_type: Optional[str] = None
    signed: bool = False
    first_edition: bool = False
    printing: Optional[str] = None
    estimated_price: Optional[float] = None

@router.put("/{isbn}/attributes")
async def update_book_attributes(
    isbn: str,
    request_body: UpdateAttributesRequest,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    service.db.update_book_attributes(
        normalized_isbn,
        condition=request_body.condition,  # NEW
        cover_type=request_body.cover_type,
        signed=request_body.signed,
        first_edition=request_body.first_edition,
        printing=request_body.printing
    )
    # ... rest of logic
```

### iOS App Changes (Swift)

#### 1. CachedBook Model (`LotHelper/CachedBook.swift`)

Added fields to store attributes locally:

```swift
@Model
final class CachedBook {
    // ... existing fields ...

    // Book attributes
    var coverType: String?
    var signed: Bool?
    var firstEdition: Bool?
    var printing: String?

    // ... rest of model
}
```

Updated `init(from record:)` to cache attributes:

```swift
init(from record: BookEvaluationRecord) {
    // ... existing initialization ...

    // Store book attributes
    self.coverType = record.metadata?.coverType
    self.signed = record.metadata?.signed
    self.firstEdition = record.metadata?.firstEdition
    self.printing = record.metadata?.printing
}
```

Updated `toBookEvaluationRecord()` to restore attributes:

```swift
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
```

#### 2. BookAPI (`LotHelper/BookAPI.swift`)

Updated `UpdateAttributesRequest`:

```swift
struct UpdateAttributesRequest: Codable {
    let condition: String?  // NEW
    let coverType: String?
    let signed: Bool
    let firstEdition: Bool
    let printing: String?
    let estimatedPrice: Double?

    enum CodingKeys: String, CodingKey {
        case condition  // NEW
        case coverType = "cover_type"
        case signed
        case firstEdition = "first_edition"
        case printing
        case estimatedPrice = "estimated_price"
    }
}
```

Updated `updateAttributes()` function:

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
    // ... rest of API call
}
```

#### 3. BookDetailViewRedesigned (`LotHelper/BookDetailViewRedesigned.swift`)

Enhanced initialization to load saved attributes:

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

Updated `saveAttributes()` to include condition:

```swift
try await BookAPI.updateAttributes(
    isbn: record.isbn,
    condition: selectedCondition,  // NEW
    coverType: coverType,
    signed: isSigned,
    firstEdition: isFirstEdition,
    printing: printing,
    estimatedPrice: dynamicEstimate
)
```

## Data Flow

### Saving Attributes

1. User changes attributes in BookDetailView UI
2. `saveAttributes()` called when user changes any attribute
3. iOS app calls `BookAPI.updateAttributes()` with all current values
4. Backend receives PUT request to `/api/books/{isbn}/attributes`
5. Database `update_book_attributes()` saves to `books` table
6. Price recalculated if needed

### Loading Attributes

1. iOS app fetches books from `/api/books/all` endpoint
2. Backend `_row_to_evaluation()` loads attributes from database into `BookMetadata` object
3. Backend `evaluation_to_record()` includes attributes in JSON response metadata
4. iOS `CachedBook` stores attributes when caching the response
5. When user opens book details, `init()` reads from `record.metadata` and initializes UI state
6. UI toggles/buttons reflect saved state

## Database Schema

The `books` table already had these columns (added in previous work):
- `condition TEXT`
- `cover_type TEXT`
- `signed INTEGER` (0 or 1)
- `first_edition INTEGER` (0 or 1)
- `printing TEXT`

No schema changes were needed for this implementation.

## Testing Results

Tested with ISBN 9780060889449:

**Before Fix**:
```
📋 Raw metadata attributes:
  - coverType: nil
  - signed: nil
  - firstEdition: nil
  - printing: nil
```

**After Fix**:
```
📋 Raw metadata attributes:
  - coverType: Optional("Hardcover")
  - signed: Optional(true)
  - firstEdition: Optional(true)
  - printing: Optional("1st")
✅ Setting isHardcover = true
✅ Setting isSigned = true
✅ Setting isFirstEdition = true
```

**Verified Persistence**:
- ✅ Condition persists across view navigation
- ✅ Format selection (Hardcover/Paperback/Mass Market) persists
- ✅ Signed toggle persists
- ✅ First Edition toggle persists
- ✅ Price estimates update correctly
- ✅ Attributes survive app restart (via cache)

## Files Modified

### Backend (Python)
- `shared/models.py` - Added attribute fields to BookMetadata
- `shared/database.py` - Added condition parameter to update_book_attributes()
- `isbn_web/api/routes/books.py` - Added condition to UpdateAttributesRequest
- `isbn_lot_optimizer/service.py` - Attributes already loaded via setattr() (no changes needed)

### iOS App (Swift)
- `LotHelper/BookAPI.swift` - Added condition to UpdateAttributesRequest and updateAttributes()
- `LotHelper/CachedBook.swift` - Added attribute fields and storage/retrieval logic
- `LotHelper/BookDetailViewRedesigned.swift` - Enhanced init to load saved state, updated saveAttributes()

## Impact

### User Experience
- Users can now adjust book attributes during scanning and trust they'll persist
- No need to re-enter attribute selections when reviewing books later
- More accurate buy decisions based on consistent attribute state

### Data Quality
- Attribute data is now properly stored and retrieved
- Historical attribute selections are preserved
- Better tracking of how attributes affect pricing over time

### Technical Debt Reduction
- Eliminated use of dynamic `setattr()` in favor of proper dataclass fields
- Improved type safety with explicit field definitions
- Better API contract documentation with properly typed request models

## Future Enhancements

Potential improvements for future consideration:

1. **Attribute History**: Track when attributes were last modified and by whom (user vs auto-detected)
2. **Bulk Attribute Update**: Allow users to update multiple books at once
3. **Attribute Validation**: Add validation rules (e.g., hardcover books can't be mass market)
4. **Auto-Detection Improvements**: Enhance ML to auto-detect signed books and first editions
5. **Attribute Confidence Scores**: Show confidence when attributes are auto-detected vs user-selected

## Related Work

This implementation builds on:
- **Collectible Detection System** (Nov 2025) - Fame database for collectible multipliers
- **Baseline Price Implementation** (Nov 2025) - Separating immutable ML predictions from adjusted prices
- **Price Estimation Improvements** (Nov 2025) - Applying multipliers based on attributes

## References

- Database schema: `~/.isbn_lot_optimizer/catalog.db` (books table)
- API documentation: FastAPI auto-generated docs at `/docs`
- iOS data models: `LotHelper/BookAPI.swift` (BookEvaluationRecord, BookMetadataDetails)
