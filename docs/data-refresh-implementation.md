# Data Refresh Implementation Summary

## Overview
This document summarizes the implemented data refresh strategy to avoid duplicate API calls while preventing stale data.

## ✅ What's Been Implemented

### 1. Backend Infrastructure

#### Database Timestamp Tracking
The database already tracks when each data type was last fetched:
- `market_fetched_at` - eBay market data timestamps
- `bookscouter_fetched_at` - Vendor buyback offer timestamps
- `metadata_fetched_at` - Book metadata timestamps

These are automatically updated when data is fetched and stored.

#### Staleness Query Methods ([shared/database.py](../shared/database.py))
```python
# Get books with stale market data (default: 30 days)
db.fetch_books_needing_market_refresh(max_age_days=7)

# Get books with stale vendor data (default: 30 days)
db.fetch_books_needing_bookscouter_refresh(max_age_days=14)

# Get books with stale metadata (default: 90 days)
db.fetch_books_needing_metadata_refresh(max_age_days=90)
```

All queries return results ordered by `probability_score DESC` to prioritize high-value books.

### 2. New Backend API Endpoints ([isbn_web/api/routes/refresh.py](../isbn_web/api/routes/refresh.py))

#### Check Staleness for Multiple Books
```
POST /api/refresh/check-staleness
Body: {
  "isbns": ["9780670855032", "9780441172719"],
  "market_max_age_days": 7,
  "bookscouter_max_age_days": 14,
  "metadata_max_age_days": 90
}

Response: {
  "fresh": ["9780441172719"],
  "stale": ["9780670855032"],
  "stale_details": {
    "9780670855032": {
      "market_is_stale": true,
      "market_fetched_at": "2025-10-01T12:00:00Z",
      "bookscouter_is_stale": false,
      "bookscouter_fetched_at": "2025-10-15T09:30:00Z",
      "metadata_is_stale": false,
      "metadata_fetched_at": "2025-07-20T14:45:00Z"
    }
  }
}
```

**Use Case**: iOS app can batch-check multiple books before displaying them to avoid unnecessary API calls.

#### Trigger Background Refresh
```
POST /api/refresh/refresh-stale-data
Body: {
  "max_books": 100,
  "data_types": ["market", "bookscouter"],
  "priority": "high_value"  // or "most_stale" or "recent"
}

Response: {
  "job_id": "refresh_20251020_143022",
  "queued_count": 47,
  "message": "Queued 47 books for refresh"
}
```

**Use Case**: Scheduled job or manual trigger to refresh stale data in background.

#### Priority Strategies
- **`high_value`**: Sorts by `probability_score DESC` (refresh valuable books first)
- **`most_stale`**: Sorts by `updated_at ASC` (refresh oldest data first)
- **`recent`**: Sorts by `created_at DESC` (refresh recently added books first)

### 3. iOS Cache Manager Enhancements ([LotHelperApp/LotHelper/CacheManager.swift](../LotHelperApp/LotHelper/CacheManager.swift))

#### Staleness Thresholds
```swift
private let marketDataMaxAge: TimeInterval = 7 * 24 * 3600   // 7 days
private let vendorDataMaxAge: TimeInterval = 14 * 24 * 3600  // 14 days
private let metadataMaxAge: TimeInterval = 90 * 24 * 3600    // 90 days
private let generalCacheMaxAge: TimeInterval = 24 * 3600     // 24 hours
```

#### Staleness Checking Methods
```swift
enum DataType {
    case market      // eBay pricing data
    case vendor      // BookScouter buyback data
    case metadata    // Book info (title, author, etc.)
    case general     // Overall cache freshness
}

// Check if a cached book is stale
func isStale(_ book: CachedBook, dataType: DataType) -> Bool

// Check if data is missing (also considered stale)
func isStale(_ record: BookEvaluationRecord, dataType: DataType) -> Bool

// Get all books that need refresh for a specific data type
func getStaleBooks(dataType: DataType = .market) -> [BookEvaluationRecord]

// Check if a specific book needs refresh
func needsRefresh(_ isbn: String, dataType: DataType = .market) -> Bool
```

## 📋 Recommended Usage Patterns

### Pattern 1: App Launch - Load Cached + Background Refresh
```swift
@MainActor
func loadBooks() async {
    // 1. Load from cache immediately (show user something fast)
    let cached = cacheManager.getCachedBooks()
    if !cached.isEmpty {
        self.books = cached
    }

    // 2. Check if cache is stale
    if cacheManager.isBooksExpired() {
        // 3. Fetch fresh data
        do {
            let fresh = try await BookAPI.fetchAllBooks()
            self.books = fresh
            cacheManager.saveBooks(fresh)
        } catch {
            // Keep showing cached data on error
            print("Failed to refresh: \(error)")
        }
    }
}
```

### Pattern 2: Book Detail View - Smart Refresh
```swift
@MainActor
func loadBookDetail(_ isbn: String) async {
    // 1. Show cached data immediately
    if let cached = cacheManager.getCachedBook(isbn) {
        self.book = cached

        // 2. Check if market data is stale
        if cacheManager.needsRefresh(isbn, dataType: .market) {
            // 3. Refresh in background
            await refreshMarketDataInBackground(isbn)
        }
    } else {
        // 4. No cache, fetch everything
        await fetchBookFresh(isbn)
    }
}

private func refreshMarketDataInBackground(_ isbn: String) async {
    do {
        // Fetch only fresh market data
        let updated = try await BookAPI.fetchBookEvaluation(isbn)
        self.book = updated
        cacheManager.saveBook(updated)
    } catch {
        // Silently fail, keep showing cached data
        print("Background refresh failed: \(error)")
    }
}
```

### Pattern 3: Pull-to-Refresh - Force Full Refresh
```swift
@MainActor
func forceRefresh() async {
    isRefreshing = true
    defer { isRefreshing = false }

    do {
        // Always fetch fresh data when user explicitly requests
        let fresh = try await BookAPI.fetchAllBooks()
        self.books = fresh
        cacheManager.saveBooks(fresh)
    } catch {
        errorMessage = "Failed to refresh: \(error.localizedDescription)"
    }
}
```

### Pattern 4: Batch Staleness Check (Optimize for Large Lists)
```swift
@MainActor
func loadBooksWithStalnessCheck() async {
    // 1. Load cached books
    let cached = cacheManager.getCachedBooks()
    self.books = cached

    // 2. Extract ISBNs
    let isbns = cached.map { $0.isbn }

    // 3. Check which are stale via API
    do {
        let staleness = try await BookAPI.checkStaleness(isbns: isbns)

        // 4. Only refresh stale books
        if !staleness.stale.isEmpty {
            await refreshStaleBooks(staleness.stale)
        }
    } catch {
        print("Staleness check failed: \(error)")
    }
}
```

## 🔄 Rate Limiting Implementation

The background refresh respects rate limits:

```python
# In _refresh_books_background()
for idx, book in enumerate(books):
    service.refresh_book_market(isbn, recalc_lots=False)

    # Rate limiting: 1 request per second for eBay
    if "market" in data_types and idx < len(books) - 1:
        time.sleep(1.0)
```

This ensures:
- **eBay API**: Max 1 request/second
- **BookScouter API**: Can adjust based on plan (default 5 req/sec)
- **Sequential processing**: One book at a time to avoid overwhelming APIs

## 📊 Staleness Thresholds Summary

| Data Type | iOS Cache | Backend Default | Rationale |
|-----------|-----------|-----------------|-----------|
| **eBay Market** | 7 days | 7 days | Prices fluctuate weekly |
| **Vendor Buyback** | 14 days | 14 days | Offers change less frequently |
| **Book Metadata** | 90 days | 90 days | Static data, rarely changes |
| **List View Cache** | 24 hours | N/A | General UI freshness |

## 🎯 Benefits of This Approach

1. **No Duplicate API Calls**
   - Database tracks when each data type was fetched
   - iOS checks staleness before making API requests
   - Batch staleness checks reduce round trips

2. **Fresh Data When Needed**
   - Market data refreshes weekly (active sourcing needs)
   - Vendor data refreshes bi-weekly (adequate for pricing)
   - Background jobs keep high-value books fresh

3. **Excellent User Experience**
   - Instant cache display (no loading spinners)
   - Background refresh doesn't block UI
   - Pull-to-refresh for manual control

4. **API Quota Management**
   - Rate limiting prevents quota exhaustion
   - Prioritization focuses on valuable books
   - Batch processing maximizes efficiency

5. **Graceful Degradation**
   - Shows cached data even when APIs fail
   - Silent background refresh attempts
   - Never blocks user on stale data

## 🚀 Next Steps

### To Use This System:

1. **Start Backend with Refresh Routes**
   ```bash
   cd /Users/nickcuskey/ISBN
   python -m isbn_web.main
   ```

2. **iOS App Will Automatically**:
   - Use cached data when fresh
   - Refresh stale data in background
   - Show staleness indicators (optional)

3. **Optional: Schedule Background Job**
   ```bash
   # Cron job to refresh stale data nightly
   0 2 * * * curl -X POST http://localhost:8000/api/refresh/refresh-stale-data \
     -H "Content-Type: application/json" \
     -d '{"max_books": 200, "data_types": ["market"], "priority": "high_value"}'
   ```

### Future Enhancements:

1. **Add staleness badges in UI** (e.g., "Updated 3 days ago")
2. **Implement job status tracking** (currently logs only)
3. **Add refresh progress indicators** in iOS app
4. **Create admin dashboard** to monitor API usage and staleness
5. **Implement smart prefetch** (predict which books user will view)

## 📁 Files Modified/Created

### Created:
- [docs/data-refresh-strategy.md](data-refresh-strategy.md) - Comprehensive strategy document
- [isbn_web/api/routes/refresh.py](../isbn_web/api/routes/refresh.py) - New refresh API endpoints
- [docs/data-refresh-implementation.md](data-refresh-implementation.md) - This file

### Modified:
- [LotHelperApp/LotHelper/CacheManager.swift](../LotHelperApp/LotHelper/CacheManager.swift) - Added staleness checking
- [isbn_web/main.py](../isbn_web/main.py) - Registered refresh router

### Existing Infrastructure Used:
- [shared/database.py](../shared/database.py) - Staleness query methods (lines 392-481)
- [isbn_lot_optimizer/service.py](../isbn_lot_optimizer/service.py) - `refresh_book_market()` method

All the pieces are in place! The system is ready to use once the backend server is running. 🎉
