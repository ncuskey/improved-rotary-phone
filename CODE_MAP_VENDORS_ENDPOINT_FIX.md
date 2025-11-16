# Code Map: Vendors Endpoint Fix

**Date**: November 16, 2025
**Type**: Bug Fix
**Status**: ✅ Complete

## Overview

Fixed the Vendors tab in the iOS app which was showing "Error Loading Vendors. The data couldn't be read because it isn't in the correct format." The issue was caused by a routing conflict and response format mismatch between the API and iOS app.

## Problem Statement

When users tapped the Vendors tab in the iOS app, they saw an error message instead of their books grouped by buyback vendor. The endpoint existed but wasn't working due to two issues:

1. **Route Ordering Problem**: The `/api/books/grouped_by_vendor` endpoint was being caught by the `/{isbn}` wildcard route
2. **Response Format Mismatch**: API response didn't match the iOS data models

### Error Observed
```
Error Loading Vendors
The data couldn't be read because it isn't in the correct format.
```

### Root Cause Analysis

When the iOS app called `/api/books/grouped_by_vendor.json`, it received:
```html
<div class="p-4 text-center">
    <p class="text-xs text-red-600">Invalid ISBN</p>
</div>
```

This HTML response indicates FastAPI matched the route to `@router.get("/{isbn}")` instead of the intended `/grouped_by_vendor` endpoint.

## Changes Made

### 1. Fix Route Ordering
**File**: `isbn_web/api/routes/books.py`
**Action**: Moved lines 1779-1848 to line 755 (before the wildcard route)

**Why**: FastAPI matches routes in the order they're defined. The wildcard route `/{isbn}` at line 756 was matching `/grouped_by_vendor` first because it appears earlier in the file.

**Before**:
```python
Line 756: @router.get("/{isbn}", response_class=HTMLResponse)
...
Line 1779: @router.get("/grouped_by_vendor")
Line 1780: @router.get("/grouped_by_vendor.json")
```

**After**:
```python
Line 755: @router.get("/grouped_by_vendor")
Line 756: @router.get("/grouped_by_vendor.json")
...
Line 826: @router.get("/{isbn}", response_class=HTMLResponse)
```

### 2. Fix Response Format
**File**: `isbn_web/api/routes/books.py`
**Lines**: 796-813

Changed API response to match iOS model expectations defined in `LotHelperApp/LotHelper/VendorsTabView.swift`.

**iOS Models**:
```swift
struct VendorGroup: Identifiable, Codable {
    let vendor: String
    let bookCount: Int
    let totalValue: Double
    let books: [VendorBook]

    enum CodingKeys: String, CodingKey {
        case vendor
        case bookCount = "book_count"
        case totalValue = "total_value"
        case books
    }
}

struct VendorBook: Codable {
    let isbn: String
    let title: String
    let authors: [String]?  // Array, not string
    let thumbnail: String?
    let estimatedPrice: Double
    let condition: String

    enum CodingKeys: String, CodingKey {
        case isbn
        case title
        case authors
        case thumbnail
        case estimatedPrice = "estimated_price"
        case condition
    }
}
```

**Changes**:

**Book Response** (lines 796-803):
```python
# Before
"authors": ", ".join(book.metadata.authors) if book.metadata and book.metadata.authors else "Unknown Author",
"offer_price": best_offer.price,
# No thumbnail field

# After
"authors": list(book.metadata.authors) if book.metadata and book.metadata.authors else [],
"thumbnail": book.metadata.thumbnail if book.metadata else None,
"estimated_price": best_offer.price,
```

**Group Response** (lines 809-814):
```python
# Before
"vendor_name": vendor_data["vendor_name"],
"vendor_id": vendor_data["vendor_id"],

# After
"vendor": vendor_data["vendor_name"],  # iOS expects "vendor" not "vendor_name"
# Removed vendor_id (not in iOS model)
```

## Testing

### Before Fix
```bash
$ curl http://localhost:8000/api/books/grouped_by_vendor.json
<div class="p-4 text-center">
    <p class="text-xs text-red-600">Invalid ISBN</p>
</div>
```

### After Fix
```bash
$ curl http://localhost:8000/api/books/grouped_by_vendor.json | python3 -m json.tool
[
    {
        "vendor": "World of Books - Sell Your Books",
        "book_count": 5,
        "total_value": 1.46,
        "books": [
            {
                "isbn": "9780316166300",
                "title": "The Scarecrow",
                "authors": ["Connelly. Michael"],
                "thumbnail": "https://m.media-amazon.com/images/I/41LgHRfNZCL._SL75_.jpg",
                "estimated_price": 0.25,
                "condition": "Good"
            },
            ...
        ]
    },
    {
        "vendor": "BooksRun",
        "book_count": 2,
        "total_value": 0.21,
        "books": [...]
    }
]
```

## Files Modified

**isbn_web/api/routes/books.py**
- Moved `/grouped_by_vendor` route definition before `/{isbn}` wildcard
- Changed response format to match iOS models
- Updated field names: `vendor_name` → `vendor`, `offer_price` → `estimated_price`
- Changed authors from string to array
- Added thumbnail field

## Impact

**Before**: Vendors tab showed error, endpoint returned HTML
**After**: Vendors tab works correctly, showing books grouped by buyback vendor

Users can now:
- See which books have buyback offers
- View books grouped by vendor (World of Books, BooksRun, etc.)
- See total value per vendor
- Identify best vendors for bulk selling

## Related Files

- **iOS UI**: `LotHelperApp/LotHelper/VendorsTabView.swift` - Vendors tab implementation
- **API Endpoint**: `isbn_web/api/routes/books.py:755-825` - Vendors endpoint
- **Data Models**: Lines 255-287 in VendorsTabView.swift

## Technical Details

### FastAPI Route Matching

FastAPI uses path operation priority:
1. Static paths (e.g., `/grouped_by_vendor`) match first
2. Dynamic paths (e.g., `/{isbn}`) match after static paths
3. BUT routes are evaluated in definition order within each priority level

Since both routes are at the same level (`/books/...`), definition order matters. The fix ensures specific routes come before wildcards.

### Why This Matters

The wildcard route `/{isbn}` accepts ANY string and tries to normalize it as an ISBN. When it receives `"grouped_by_vendor"`, it:
1. Tries to normalize it as an ISBN → fails
2. Returns the "Invalid ISBN" HTML error template
3. iOS app receives HTML instead of JSON → parsing fails

By moving the specific route first, FastAPI matches it correctly and returns JSON.

## Future Considerations

To prevent similar issues:
1. **Route Organization**: Keep specific routes before wildcard routes
2. **API Testing**: Add integration tests for all iOS-consumed endpoints
3. **Type Safety**: Consider using Pydantic models for API responses
4. **Documentation**: Document expected response formats for iOS team

## Lessons Learned

1. **Route Order Matters**: In FastAPI, specific routes must come before wildcard routes
2. **Format Alignment**: API responses must match client model expectations exactly
3. **Error Messages**: HTML error responses to JSON-expecting clients show as "format" errors
4. **Testing**: Test endpoints directly via curl/Postman, not just through UI
