# Cache & Refresh Quick Reference Guide

## 🎯 How It Works

Your system now intelligently caches data and refreshes it only when stale, avoiding duplicate API calls while keeping data fresh.

## ⏰ Staleness Rules

| Data Type | Refresh Interval | Why |
|-----------|-----------------|-----|
| **eBay Prices** | Every 7 days | Prices change weekly |
| **Vendor Buyback** | Every 14 days | Offers more stable |
| **Book Metadata** | Every 90 days | Titles/authors don't change |

## 📱 iOS App Behavior

### When you open the app:
1. ✅ Shows cached books **instantly** (no waiting!)
2. 🔍 Checks if cache is >24 hours old
3. 🔄 Refreshes in background if stale
4. 📊 Updates UI when fresh data arrives

### When you view a book detail:
1. ✅ Shows cached data **immediately**
2. 🔍 Checks if market data is >7 days old
3. 🔄 Fetches fresh prices in background if needed
4. 💰 Updates profit calculations with fresh data

### When you pull-to-refresh:
1. 🔄 Always fetches fresh data (user requested it)
2. 💾 Updates cache with new data
3. ✨ Shows updated prices/offers

## 🔧 Backend API Endpoints

### Check if books need refresh:
```bash
curl -X POST http://localhost:8000/api/refresh/check-staleness \
  -H "Content-Type: application/json" \
  -d '{"isbns": ["9780670855032"]}'
```

### Trigger background refresh:
```bash
curl -X POST http://localhost:8000/api/refresh/refresh-stale-data \
  -H "Content-Type: application/json" \
  -d '{
    "max_books": 100,
    "data_types": ["market", "bookscouter"],
    "priority": "high_value"
  }'
```

## 💡 Best Practices

### ✅ Do:
- Let the app handle caching automatically
- Use pull-to-refresh when you want latest prices
- Run background refresh jobs for large catalogs
- Trust the cache for recently scanned books

### ❌ Don't:
- Manually clear cache unless troubleshooting
- Refresh all books at once (use background job)
- Worry about "old" metadata (90 days is fine)
- Disable cache to "always get fresh data" (wastes API calls)

## 🤖 Scheduled Background Refresh (Optional)

To automatically refresh stale data nightly:

**Option 1: Cron Job**
```bash
# Add to crontab (runs at 2 AM daily)
0 2 * * * cd /Users/nickcuskey/ISBN && curl -X POST http://localhost:8000/api/refresh/refresh-stale-data -H "Content-Type: application/json" -d '{"max_books": 200, "data_types": ["market"], "priority": "high_value"}'
```

**Option 2: iOS Background Refresh** (Future Enhancement)
```swift
// In AppDelegate or similar
BGTaskScheduler.shared.register(
    forTaskWithIdentifier: "com.yourapp.refresh",
    using: nil
) { task in
    Task {
        await refreshStaleBooks()
        task.setTaskCompleted(success: true)
    }
}
```

## 📊 Monitoring

### Check database staleness:
```python
from shared.database import DatabaseManager

db = DatabaseManager("path/to/books.db")

# Books with stale market data
stale_market = db.fetch_books_needing_market_refresh(max_age_days=7)
print(f"Books needing market refresh: {len(stale_market)}")

# Books with stale vendor data
stale_vendor = db.fetch_books_needing_bookscouter_refresh(max_age_days=14)
print(f"Books needing vendor refresh: {len(stale_vendor)}")
```

### Check iOS cache:
```swift
let cacheManager = CacheManager(modelContext: modelContext)

// Get stale books
let staleMarket = cacheManager.getStaleBooks(dataType: .market)
print("Books with stale market data: \(staleMarket.count)")

// Check specific book
let needsRefresh = cacheManager.needsRefresh("9780670855032", dataType: .market)
print("Book needs refresh: \(needsRefresh)")
```

## 🎓 Examples

### Example 1: Checking a single book
```bash
# Check if ISBN 9780670855032 needs refresh
curl -X POST http://localhost:8000/api/refresh/check-staleness \
  -H "Content-Type: application/json" \
  -d '{"isbns": ["9780670855032"]}'

# Response shows:
{
  "fresh": [],
  "stale": ["9780670855032"],
  "stale_details": {
    "9780670855032": {
      "market_is_stale": true,
      "market_fetched_at": "2025-10-01T12:00:00Z",
      "bookscouter_is_stale": false
    }
  }
}
```

### Example 2: Refresh top 50 valuable books
```bash
curl -X POST http://localhost:8000/api/refresh/refresh-stale-data \
  -H "Content-Type: application/json" \
  -d '{
    "max_books": 50,
    "data_types": ["market"],
    "priority": "high_value"
  }'

# Response:
{
  "job_id": "refresh_20251020_143022",
  "queued_count": 47,
  "message": "Queued 47 books for refresh"
}
```

### Example 3: Refresh oldest data first
```bash
curl -X POST http://localhost:8000/api/refresh/refresh-stale-data \
  -H "Content-Type: application/json" \
  -d '{
    "max_books": 100,
    "data_types": ["market", "bookscouter"],
    "priority": "most_stale"
  }'
```

## 🐛 Troubleshooting

### Problem: App shows old prices
**Solution**: Pull-to-refresh to force update, or check if backend is running.

### Problem: API quota exceeded
**Solution**: Reduce background refresh frequency or max_books count.

### Problem: Cache never refreshes
**Solution**: Check staleness thresholds in CacheManager.swift (may be too long).

### Problem: Too many API calls
**Solution**: Increase staleness thresholds (7 days → 14 days for market data).

## 📚 Related Documentation

- [data-refresh-strategy.md](docs/data-refresh-strategy.md) - Comprehensive strategy
- [data-refresh-implementation.md](docs/data-refresh-implementation.md) - Implementation details
- [shared/database.py](shared/database.py) - Database staleness queries
- [LotHelperApp/LotHelper/CacheManager.swift](LotHelperApp/LotHelper/CacheManager.swift) - iOS cache logic

## 🎉 Summary

Your system now:
- ✅ **Avoids duplicate API calls** (checks cache first)
- ✅ **Keeps data fresh** (auto-refreshes stale data)
- ✅ **Respects API limits** (rate limiting built-in)
- ✅ **Excellent UX** (instant cache, background refresh)
- ✅ **Prioritizes value** (refreshes profitable books first)

**The cache is your friend!** Trust it to handle the complexity. 🚀
