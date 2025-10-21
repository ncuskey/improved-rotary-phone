# Book Cover Checker & Fixer Guide

## Overview
The ISBN Lot Optimizer now includes tools to check for missing or broken book covers and automatically fix them by downloading from multiple sources.

## 🎯 Features

### 1. **Cover Statistics**
- Count total books with/without covers
- Calculate coverage percentage
- Identify which books need cover images

### 2. **Cover Validation**
- Check if cover URLs are accessible
- Verify images are valid (not 404s or placeholders)
- Test multiple cover sources

### 3. **Automatic Cover Fixing**
- Download missing covers from Open Library
- Try multiple image sizes (L, M, S)
- Update database with working URLs
- Background processing for large batches

## 📋 Usage

### Command Line Script

**Check for missing covers:**
```bash
python scripts/check_missing_covers.py --check-only
```

**Fix missing covers:**
```bash
python scripts/check_missing_covers.py --fix
```

**Force recheck all covers:**
```bash
python scripts/check_missing_covers.py --fix --force-redownload
```

**Custom database path:**
```bash
python scripts/check_missing_covers.py --db /path/to/books.db --fix
```

### API Endpoints

#### Get Cover Statistics
```bash
curl http://localhost:8000/api/covers/stats
```

**Response:**
```json
{
  "total_books": 250,
  "with_covers": 230,
  "without_covers": 20,
  "coverage_percentage": 92.0,
  "missing_isbns": ["9780670855032", "9780441172719", ...]
}
```

#### Check Specific ISBNs
```bash
curl -X POST http://localhost:8000/api/covers/check \
  -H "Content-Type: application/json" \
  -d '{
    "isbns": ["9780670855032", "9780441172719"]
  }'
```

**Response:**
```json
{
  "total_checked": 2,
  "valid": 1,
  "missing": 1,
  "details": {
    "9780670855032": {
      "status": "valid",
      "has_cover": true,
      "cover_url": "https://covers.openlibrary.org/b/isbn/9780670855032-L.jpg",
      "content_type": "image/jpeg"
    },
    "9780441172719": {
      "status": "no_cover_url",
      "has_cover": false
    }
  }
}
```

#### Fix Missing Covers
```bash
# Fix all books with missing covers
curl -X POST http://localhost:8000/api/covers/fix \
  -H "Content-Type: application/json" \
  -d '{}'

# Fix specific ISBNs
curl -X POST http://localhost:8000/api/covers/fix \
  -H "Content-Type: application/json" \
  -d '{
    "isbns": ["9780670855032", "9780441172719"],
    "force_recheck": false
  }'
```

**Response:**
```json
{
  "job_id": "fix_covers_20251020_143022",
  "books_queued": 20,
  "message": "Queued 20 books for cover fixing"
}
```

## 🔍 How It Works

### Detection Strategy

The system identifies missing covers by checking:
1. **No metadata:** Book has no `metadata_json` field
2. **No URL fields:** Metadata doesn't contain `cover_url` or `thumbnail`
3. **Null values:** Fields exist but are set to `null`
4. **Broken links:** URLs return 404 or non-image content

### Cover Sources (Priority Order)

1. **Open Library (Large)**
   - `https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg`
   - Best quality, primary source

2. **Open Library (Medium)**
   - `https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg`
   - Fallback if large not available

3. **Google Books** (Future)
   - From metadata enrichment
   - Requires API key

### Validation Process

```python
# Check if URL returns valid image
1. Send HEAD request to cover URL
2. Verify HTTP 200 status
3. Check Content-Type is image/*
4. Verify Content-Length > 1KB (not placeholder)
5. Download and check for placeholder patterns
```

### Database Updates

When a cover is found:
```python
metadata["cover_url"] = working_url
metadata["thumbnail"] = working_url  # Update both fields
```

## 📊 Database Queries

### Count Books With/Without Covers
```python
from shared.database import DatabaseManager

db = DatabaseManager("path/to/books.db")
stats = db.count_books_with_covers()

print(f"Total: {stats['total']}")
print(f"With covers: {stats['with_covers']} ({stats['coverage_percentage']:.1f}%)")
print(f"Without covers: {stats['without_covers']}")
```

### Get Books Missing Covers
```python
missing = db.fetch_books_with_missing_covers()
for book in missing:
    print(f"{book['isbn']}: {book['title']}")
```

## 🛠️ Integration Examples

### iOS App - Check Cover Before Display

```swift
extension BookCardView {
    func checkCoverAvailability(_ url: String) async -> Bool {
        guard let coverURL = URL(string: url) else { return false }

        do {
            let (_, response) = try await URLSession.shared.data(from: coverURL)
            guard let httpResponse = response as? HTTPURLResponse else { return false }

            return httpResponse.statusCode == 200
        } catch {
            return false
        }
    }
}
```

### Web App - Fetch Covers on Demand

```javascript
// Check cover stats on dashboard load
async function loadCoverStats() {
  const response = await fetch('/api/covers/stats');
  const stats = await response.json();

  document.getElementById('cover-stats').innerHTML = `
    ${stats.with_covers}/${stats.total_books} books have covers
    (${stats.coverage_percentage.toFixed(1)}%)
  `;

  if (stats.without_covers > 0) {
    showFixCoversButton(stats.without_covers);
  }
}

// Trigger fix for missing covers
async function fixMissingCovers() {
  const response = await fetch('/api/covers/fix', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  });

  const result = await response.json();
  console.log(`Fixing ${result.books_queued} covers...`);
}
```

## ⚙️ Configuration

### Cover Cache Directory

Covers are cached locally to avoid repeated downloads:

**Backend:**
```python
# In isbn_web/config.py
COVER_CACHE_DIR = Path.home() / ".isbn_lot_optimizer" / "covers"
```

**Script:**
```python
# Default: ~/.isbn_lot_optimizer/covers
# Custom:
checker = CoverChecker(db_path, cache_dir=Path("/custom/cache"))
```

### Rate Limiting

The background fixer includes rate limiting to be respectful to Open Library:

```python
# In _fix_covers_background()
await asyncio.sleep(0.5)  # 2 requests per second max
```

Adjust this value if needed:
- **Faster:** `0.2` = 5 req/sec
- **Slower:** `1.0` = 1 req/sec

### Timeout Settings

```python
# In CoverChecker
timeout: float = 10.0  # Seconds to wait for download
```

## 📈 Monitoring

### Check Progress in Logs

```bash
# Watch cover fix job progress
tail -f /path/to/app.log | grep "cover"
```

**Example output:**
```
INFO: ✅ Fixed cover for: Ship of Magic
INFO: ❌ No cover found for: The Great Dune Trilogy
INFO: Cover fix job fix_covers_20251020_143022 progress: 10/20
INFO: Cover fix job fix_covers_20251020_143022 complete: 18 successful, 2 errors
```

### Query Statistics

```bash
# Get current stats
curl http://localhost:8000/api/covers/stats | jq
```

## 🐛 Troubleshooting

### Problem: Script finds "missing" covers that exist
**Cause:** Metadata JSON might use different field names
**Solution:** Check what fields your metadata uses:
```bash
sqlite3 ~/.isbn_lot_optimizer/books.db \
  "SELECT metadata_json FROM books LIMIT 1;"
```

### Problem: Covers download but still show as missing
**Cause:** Database not updating properly
**Solution:** Verify writes are succeeding:
```python
# Check if cover_url is in metadata after fix
row = db.fetch_book("9780670855032")
print(json.loads(row["metadata_json"]).get("cover_url"))
```

### Problem: OpenLibrary returns placeholders
**Cause:** Some ISBNs don't have covers in their database
**Solution:** This is expected, not all books have covers available

### Problem: Too slow to check all books
**Solution:** Use --fix without --force-redownload to only fix known missing:
```bash
python scripts/check_missing_covers.py --fix
# Skips books that already have cover_url
```

## 🎯 Best Practices

### ✅ Do:
- Run `--check-only` first to see scope
- Use `--fix` on regular schedule (weekly/monthly)
- Monitor logs for failed downloads
- Cache covers locally when possible
- Respect Open Library rate limits

### ❌ Don't:
- Don't use `--force-redownload` frequently (wastes bandwidth)
- Don't download covers for every page view (cache them)
- Don't ignore failed downloads (some ISBNs legitimately have no covers)
- Don't hammer Open Library API (use delays)

## 📚 Related Files

- [scripts/check_missing_covers.py](scripts/check_missing_covers.py) - CLI script
- [isbn_web/api/routes/covers_check.py](isbn_web/api/routes/covers_check.py) - API endpoints
- [isbn_web/services/cover_cache.py](isbn_web/services/cover_cache.py) - Caching service
- [shared/database.py](shared/database.py) - Database queries (lines 483-538)
- [isbn_lot_optimizer/metadata.py](isbn_lot_optimizer/metadata.py) - Metadata enrichment

## 🚀 Quick Start

**1. Check your current coverage:**
```bash
python scripts/check_missing_covers.py --check-only
```

**2. Fix missing covers:**
```bash
python scripts/check_missing_covers.py --fix
```

**3. Monitor via API:**
```bash
curl http://localhost:8000/api/covers/stats
```

**4. Schedule regular fixes (optional):**
```bash
# Add to crontab (runs weekly on Sunday at 3 AM)
0 3 * * 0 cd /path/to/ISBN && python scripts/check_missing_covers.py --fix
```

## 📊 Example Output

```
Checking 250 books for cover images...
------------------------------------------------------------
Progress: 10/250 (8 valid, 2 missing, 0 broken)
Progress: 20/250 (17 valid, 3 missing, 0 broken)
  ✅ Fixed: Ship of Magic -> https://covers.openlibrary.org/b/isbn/9780670855032-L.jpg
Progress: 30/250 (26 valid, 3 missing, 1 broken)
  ✅ Fixed: Dune -> https://covers.openlibrary.org/b/isbn/9780441172719-L.jpg
  ❌ No cover found: The Great Unknown Book

============================================================
SUMMARY
============================================================
Total books:      250
Checked:          250
Valid covers:     230 (92.0%)
Missing covers:   15 (6.0%)
Broken covers:    5 (2.0%)

Fixed:            18
Failed to fix:    2
```

## 🎉 Summary

The cover checker system:
- ✅ **Detects missing covers** automatically
- ✅ **Downloads from multiple sources** (Open Library, etc.)
- ✅ **Validates images** (no placeholders or 404s)
- ✅ **Updates database** with working URLs
- ✅ **API + CLI** for flexibility
- ✅ **Background processing** for large batches
- ✅ **Rate limited** to respect API limits

Your book catalog will look more professional with complete cover coverage! 📚✨
