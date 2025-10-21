# Data Refresh Strategy

## Overview
This document outlines the strategy for avoiding duplicate API calls while preventing stale data across the ISBN Lot Optimizer system.

## Data Staleness Thresholds

Different data types have different staleness characteristics:

| Data Type | Staleness Period | Rationale |
|-----------|-----------------|-----------|
| **eBay Market Data** | 7 days | Prices and demand fluctuate; refresh weekly for active sourcing |
| **Vendor Buyback Prices** | 14 days | Buyback offers change less frequently than market prices |
| **Book Metadata** | 90 days | Title, author, ISBN data rarely changes |
| **Series Information** | 90 days | Series structure is relatively static |

## Backend Infrastructure

### Timestamp Tracking
The database tracks fetch timestamps for each data type:
- `market_fetched_at` - eBay market data (active/sold listings, prices)
- `bookscouter_fetched_at` - Vendor buyback offers
- `metadata_fetched_at` - Book metadata (title, author, etc.)

### Staleness Queries
The `DatabaseManager` provides methods to identify stale data:
```python
db.fetch_books_needing_market_refresh(max_age_days=7)
db.fetch_books_needing_bookscouter_refresh(max_age_days=14)
db.fetch_books_needing_metadata_refresh(max_age_days=90)
```

## Refresh Strategies

### 1. On-Demand Refresh (User-Initiated)
**When**: User explicitly requests fresh data (pull-to-refresh, refresh button)
**What**: Refresh all data types for displayed books
**Implementation**:
- iOS: Pull-to-refresh gesture on book list
- Web: "Refresh" button on book detail page
- Endpoint: `POST /api/books/{isbn}/refresh`

### 2. Background Refresh (Automatic)
**When**: App launches or periodic background task
**What**: Refresh only stale data (based on thresholds above)
**Implementation**:
- Identify stale books using database queries
- Batch refresh in background (prioritize high-value books)
- Rate-limit API calls (1 req/sec for eBay, 10 req/sec for BookScouter)

### 3. Smart Refresh (Context-Aware)
**When**: User views specific book details
**What**: Check staleness, refresh if needed
**Implementation**:
- iOS: When navigating to book detail view
- Web: When clicking on a book
- Logic: If `market_fetched_at < NOW - 7 days`, auto-refresh

### 4. Bulk Import Optimization
**When**: Importing large CSV of ISBNs
**What**: Check existing data first, only fetch missing/stale
**Implementation**:
```python
for isbn in csv_isbns:
    existing = db.fetch_book(isbn)
    if not existing or is_stale(existing):
        fetch_and_update(isbn)
    else:
        use_cached(existing)
```

## iOS Client Caching

### SwiftData Cache
- **Primary Cache**: SwiftData stores all book records locally
- **Expiration**: Books include `lastUpdated` timestamp
- **Invalidation**: Compare with staleness thresholds on app launch

### Cache-First Strategy
```swift
1. Check SwiftData for book
2. If exists and fresh (< 7 days old):
   - Use cached data
3. If exists but stale OR missing:
   - Display cached data (if available)
   - Fetch fresh data in background
   - Update UI when fresh data arrives
```

### iOS Implementation
```swift
@MainActor
func loadBook(_ isbn: String) async {
    // 1. Show cached data immediately
    if let cached = cacheManager.getBook(isbn) {
        self.book = cached

        // 2. Check staleness
        if cached.needsRefresh {
            // 3. Fetch fresh data in background
            await refreshBookInBackground(isbn)
        }
    } else {
        // 4. No cache, fetch fresh
        await fetchBook(isbn)
    }
}

private func refreshBookInBackground(_ isbn: String) async {
    do {
        let fresh = try await BookAPI.fetchBookEvaluation(isbn)
        self.book = fresh
        cacheManager.saveBook(fresh)
    } catch {
        // Keep showing cached data on error
        print("Background refresh failed: \(error)")
    }
}
```

## Backend API Endpoints

### Get Book with Staleness Info
```
GET /api/books/{isbn}/evaluate
Response includes:
{
  "isbn": "...",
  "metadata": {...},
  "market": {...},
  "bookscouter": {...},
  "_cache_info": {
    "market_fetched_at": "2025-10-15T10:30:00Z",
    "bookscouter_fetched_at": "2025-10-18T14:20:00Z",
    "metadata_fetched_at": "2025-08-01T09:00:00Z",
    "market_is_stale": false,
    "bookscouter_is_stale": false,
    "metadata_is_stale": false
  }
}
```

### Batch Staleness Check
```
POST /api/books/check-staleness
Body: {"isbns": ["123", "456", "789"]}
Response: {
  "stale": ["123"],        // Needs refresh
  "fresh": ["456", "789"]  // Cache is good
}
```

### Background Refresh Trigger
```
POST /api/jobs/refresh-stale-data
Body: {
  "max_books": 100,           // Limit batch size
  "data_types": ["market"],   // What to refresh
  "priority": "high_value"    // Prioritization strategy
}
Response: {
  "job_id": "abc123",
  "queued_count": 47
}
```

## Rate Limiting & API Quotas

### eBay API
- **Limit**: 5,000 calls/day
- **Strategy**: Prioritize high-probability books
- **Throttling**: 1 request/second max

### BookScouter API
- **Limit**: Typically 10-100 req/sec (check plan)
- **Strategy**: Batch requests when possible
- **Throttling**: 5 requests/second default

### Implementation
```python
from time import sleep, time

class RateLimiter:
    def __init__(self, calls_per_second: float):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0

    def wait(self):
        now = time()
        elapsed = now - self.last_call
        if elapsed < self.min_interval:
            sleep(self.min_interval - elapsed)
        self.last_call = time()

ebay_limiter = RateLimiter(1.0)  # 1 call/sec
bookscouter_limiter = RateLimiter(5.0)  # 5 calls/sec
```

## Prioritization Logic

When refreshing stale data, prioritize by:

1. **User Intent**: Books user is actively viewing > background refresh
2. **Business Value**: High probability score > low probability
3. **Staleness**: Very stale (>30 days) > moderately stale (7-14 days)
4. **Frequency**: Recently scanned books > old inventory

### Priority Score Formula
```python
def calculate_refresh_priority(book) -> float:
    base_score = book.probability_score  # 0.0 - 1.0

    # Age factor (more stale = higher priority)
    days_stale = (now - book.market_fetched_at).days
    age_multiplier = min(2.0, 1.0 + (days_stale / 30))

    # Recency factor (recently scanned = higher priority)
    days_since_scan = (now - book.created_at).days
    recency_multiplier = 1.0 if days_since_scan < 7 else 0.5

    return base_score * age_multiplier * recency_multiplier
```

## Monitoring & Observability

### Metrics to Track
- **Cache Hit Rate**: `cached_requests / total_requests`
- **API Call Volume**: Daily count per API (eBay, BookScouter, etc.)
- **Staleness Distribution**: Histogram of data age
- **Refresh Success Rate**: `successful_refreshes / attempted_refreshes`

### Logging
```python
import logging
logger = logging.getLogger("refresh")

logger.info(
    "Refresh complete",
    extra={
        "isbn": isbn,
        "data_type": "market",
        "was_stale": True,
        "age_days": 12,
        "api_calls": 2
    }
)
```

## Best Practices

### ✅ Do
- Always check cache before making API calls
- Use timestamp-based staleness checks
- Implement exponential backoff on API errors
- Prioritize high-value books for refresh
- Show cached data while fetching fresh data
- Log all API calls for quota monitoring

### ❌ Don't
- Don't refresh data that's already fresh
- Don't block UI on background refresh
- Don't retry failed API calls indefinitely
- Don't refresh all books at once (batch gradually)
- Don't ignore API rate limits

## Future Enhancements

1. **Predictive Refresh**: ML model to predict which books user will view next
2. **Smart Batching**: Group similar books for batch API requests
3. **CDN Integration**: Cache book covers and static metadata
4. **Webhook Updates**: Real-time updates when prices change significantly
5. **Quota Management**: Dynamic rate limiting based on remaining API quota
