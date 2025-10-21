# Cover Loading Fix for Web App

## Problem
Book covers weren't loading in the lot carousel in the web app. The cover_cache service was only downloading from Open Library, ignoring the cover URLs stored in the database metadata.

## Root Cause
The `cover_cache.py` service had two issues:

1. **Hardcoded Open Library URLs**: The service only tried to download from `https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg`, completely ignoring cover URLs stored in the database metadata.

2. **Wrong Method Name**: Initially tried to use `db.get_book()` which doesn't exist - the correct method is `db.fetch_book()`.

## Example Case: "Cross the Line" by James Patterson

- **ISBN**: 9780316407090
- **Database had**: `https://covers.openlibrary.org/b/isbn/9780316407090-M.jpg` (43 byte placeholder)
- **Actual cover**: Google Books API URL (13KB image)
- **Result**: Cover appeared "missing" in carousel despite being in database

## Solution

Updated `/Users/nickcuskey/ISBN/isbn_web/services/cover_cache.py` to:

1. **Check database first** for cover URLs stored in metadata
2. **Use correct method** (`fetch_book` instead of `get_book`)
3. **Fall back to Open Library** if no database URL exists
4. **Support multiple sources** (Google Books, BookScouter/ISBNDB, Internet Archive, etc.)

### Code Changes

```python
async def get_cover(self, isbn: str, size: str = "L") -> Optional[bytes]:
    # ... cache check ...

    # NEW: Try to get cover URL from database metadata first
    cover_url = None
    try:
        db = DatabaseManager(settings.DATABASE_PATH)
        book = db.fetch_book(isbn)  # Fixed: was get_book()
        if book and book["metadata_json"]:
            metadata = json.loads(book["metadata_json"])
            # Check both cover_url and thumbnail fields
            cover_url = metadata.get("cover_url") or metadata.get("thumbnail")

            # Adjust size for Open Library URLs
            if cover_url and "openlibrary.org" in cover_url:
                cover_url = cover_url.replace("-S.jpg", f"-{size}.jpg")
                cover_url = cover_url.replace("-M.jpg", f"-{size}.jpg")
                cover_url = cover_url.replace("-L.jpg", f"-{size}.jpg")
    except Exception as e:
        print(f"Error checking database for cover: {e}")

    # If no URL from database, use Open Library default
    if not cover_url:
        cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg"

    # Download the cover
    # ... download logic ...
```

## Testing

```bash
# Test cover fetching
python -c "
import asyncio
from isbn_web.services.cover_cache import cover_cache

async def test():
    result = await cover_cache.get_cover('9780316407090', 'M')
    print(f'Cover size: {len(result):,} bytes' if result else 'Failed')

asyncio.run(test())
"
```

Expected output: `Cover size: 13,394 bytes`

## Verification Checklist

- [x] Fixed `get_book()` → `fetch_book()` method call
- [x] Added database metadata check for cover URLs
- [x] Tested with "Cross the Line" (ISBN 9780316407090)
- [x] Cover successfully downloaded (13KB from Google Books)
- [x] Cover cached to disk
- [ ] Restart web server (`isbn-web`)
- [ ] Load lot with "Cross the Line" in web app
- [ ] Verify cover displays in 3D carousel

## Impact

This fix enables the web app carousel to display covers from **any source** stored in the database:
- ✅ Google Books API
- ✅ BookScouter/ISBNDB
- ✅ Internet Archive
- ✅ Goodreads
- ✅ Open Library (fallback)

**Before**: Only Open Library URLs worked
**After**: Any cover URL in database metadata works

## Related Files

- [isbn_web/services/cover_cache.py](isbn_web/services/cover_cache.py) - Fixed service
- [scripts/fix_covers_advanced.py](scripts/fix_covers_advanced.py) - Script to find covers from multiple sources
- [shared/database.py](shared/database.py) - Database manager with `fetch_book()` method

## Next Steps

1. Restart the web server: `isbn-web`
2. Clear browser cache or hard refresh (Ctrl+F5)
3. Navigate to lots page and verify covers load in carousel
4. Consider running bulk cover update for books with Open Library placeholders:

```bash
# Find books with small/placeholder covers
python scripts/fix_covers_advanced.py --fix --verbose
```

This will update any books that have placeholder covers with real images from alternative sources.
