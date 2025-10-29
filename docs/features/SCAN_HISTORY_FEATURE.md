# Scan History Feature

Complete audit trail for all book scans with location tracking.

## Overview

The scan history feature provides a permanent log of every book you scan, whether you accept or reject it. This helps you:

- **Avoid rescanning**: See books you've already evaluated
- **Track locations**: Know which stores have which books
- **Analyze patterns**: Understand your buying decisions over time
- **Location intelligence**: Remember productive scanning locations

## Database Schema

**Table:** `scan_history`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key (auto-increment) |
| `isbn` | TEXT | Book ISBN |
| `scanned_at` | TEXT | Timestamp (UTC) |
| `decision` | TEXT | ACCEPT, REJECT, SKIP, etc. |
| `title` | TEXT | Book title |
| `authors` | TEXT | Book authors |
| `estimated_price` | REAL | Estimated resale value |
| `probability_label` | TEXT | HIGH, MEDIUM, LOW |
| `probability_score` | REAL | Numerical score (0.0-1.0) |
| `location_name` | TEXT | Location name (e.g., "Barnes & Noble Downtown") |
| `location_address` | TEXT | Full address |
| `location_latitude` | REAL | GPS latitude |
| `location_longitude` | REAL | GPS longitude |
| `location_accuracy` | REAL | GPS accuracy in meters |
| `device_id` | TEXT | Device identifier |
| `app_version` | TEXT | App version |
| `notes` | TEXT | Optional notes |

**Indexes:**
- `isbn` - Fast lookup by book
- `scanned_at DESC` - Fast recent scans query
- `decision` - Filter by accept/reject
- `location_name` - Group by location

## API Methods

### DatabaseManager Methods

#### `log_scan()`
Log a book scan with full details:

```python
scan_id = db.log_scan(
    isbn='9780385497466',
    decision='ACCEPT',  # or 'REJECT', 'SKIP'
    title='The Brethren',
    authors='John Grisham',
    estimated_price=12.99,
    probability_label='MEDIUM',
    probability_score=0.65,
    location_name='Half Price Books Denver',
    location_address='1234 Main St, Denver, CO 80202',
    location_latitude=39.7392,
    location_longitude=-104.9903,
    location_accuracy=10.0,  # meters
    device_id='iPhone-ABC123',
    app_version='1.2.0',
    notes='Great condition, dust jacket intact'
)
```

#### `get_scan_history()`
Retrieve scan history with filters:

```python
# Get last 100 scans
scans = db.get_scan_history(limit=100)

# Filter by ISBN
scans = db.get_scan_history(isbn='9780385497466')

# Filter by location
scans = db.get_scan_history(location_name='Half Price Books Denver')

# Filter by decision
scans = db.get_scan_history(decision='REJECT')

# Combine filters
scans = db.get_scan_history(
    location_name='Half Price Books Denver',
    decision='ACCEPT',
    limit=50
)
```

#### `get_scan_locations()`
Get summary of all locations visited:

```python
locations = db.get_scan_locations()
# Returns:
# [
#   {
#     'location_name': 'Half Price Books Denver',
#     'scan_count': 45,
#     'accepted_count': 12,
#     'rejected_count': 33,
#     'last_scan': '2025-10-23 16:54:10'
#   },
#   ...
# ]
```

#### `get_scan_stats()`
Get overall statistics:

```python
stats = db.get_scan_stats()
# Returns:
# {
#   'total_scans': 714,
#   'unique_books': 650,
#   'accepted': 450,
#   'rejected': 250,
#   'skipped': 14,
#   'first_scan': '2025-01-15 10:00:00',
#   'last_scan': '2025-10-23 16:54:10',
#   'unique_locations': 8
# }
```

## Decision Types

Standard decision values:

- **`ACCEPT`** - Book added to catalog
- **`REJECT`** - Book rejected (too low value, poor condition, etc.)
- **`SKIP`** - Skipped for now (maybe revisit later)
- **`DUPLICATE`** - Already scanned this book
- **`ERROR`** - Scan failed or couldn't get data

## Use Cases

### 1. Avoid Rescans
Before evaluating a book, check if you've scanned it before:

```python
previous_scans = db.get_scan_history(isbn='9780385497466')
if previous_scans:
    last_scan = previous_scans[0]
    print(f"You scanned this on {last_scan['scanned_at']}")
    print(f"Decision: {last_scan['decision']}")
    print(f"Location: {last_scan['location_name']}")
```

### 2. Location Intelligence
See which locations are most productive:

```python
locations = db.get_scan_locations()
for loc in locations:
    accept_rate = loc['accepted_count'] / loc['scan_count'] * 100
    print(f"{loc['location_name']}: {accept_rate:.1f}% acceptance rate")
```

### 3. Track Store Inventory
See what books are at a specific location:

```python
store_scans = db.get_scan_history(
    location_name='Half Price Books Denver',
    decision='REJECT',  # Books you passed on
    limit=100
)
# These books might still be there!
```

### 4. Analyze Buying Patterns
```python
stats = db.get_scan_stats()
acceptance_rate = stats['accepted'] / stats['total_scans'] * 100
print(f"You accept {acceptance_rate:.1f}% of scanned books")
```

## Integration Points

### ✅ Completed

1. **Service Layer Integration** ✓
   - `BookService.log_scan()` method added
   - Automatic ACCEPT logging when books are persisted
   - Handles both full evaluations and minimal data

2. **Web API Endpoints** ✓
   - `POST /api/books/log-scan` - Log any scan decision with location
   - `GET /api/books/scan-history` - Query scan history with filters
   - `GET /api/books/scan-locations` - Get location summaries
   - `GET /api/books/scan-stats` - Get overall statistics

### 🔜 Next Steps (To Be Implemented)

1. **iOS App Location Tracking**
   - Add Core Location framework
   - Request location permissions ("When In Use")
   - Reverse geocode to get location names from coordinates
   - Send location data with all scan API calls
   - Store last location to reuse for quick scans

2. **UI Features**
   - "You scanned this before" warnings in iOS app
   - Scan history view in iOS Books tab
   - Location-based filtering
   - Location performance dashboard
   - Map view of scan locations

## REST API Endpoints

### POST /api/books/log-scan

Log a scan decision with optional location data.

**Request Body:**
```json
{
  "isbn": "9780385497466",
  "decision": "REJECT",
  "location_name": "Half Price Books Denver",
  "location_address": "1234 Main St, Denver, CO 80202",
  "location_latitude": 39.7392,
  "location_longitude": -104.9903,
  "location_accuracy": 10.0,
  "device_id": "iPhone-ABC123",
  "app_version": "1.2.0",
  "notes": "Price too high"
}
```

**Response:**
```json
{
  "success": true,
  "scan_id": 42,
  "isbn": "9780385497466",
  "decision": "REJECT"
}
```

### GET /api/books/scan-history

Query scan history with filters.

**Query Parameters:**
- `limit` (int): Max results (default 100)
- `isbn` (string): Filter by ISBN
- `location_name` (string): Filter by location
- `decision` (string): Filter by decision

**Example:** `/api/books/scan-history?location_name=Half%20Price%20Books&limit=50`

**Response:**
```json
{
  "scans": [
    {
      "id": 42,
      "isbn": "9780385497466",
      "scanned_at": "2025-10-23 16:54:10",
      "decision": "REJECT",
      "title": "The Brethren",
      "authors": "John Grisham",
      "estimated_price": 12.99,
      "probability_label": "MEDIUM",
      "probability_score": 0.65,
      "location_name": "Half Price Books Denver",
      "location_address": "1234 Main St, Denver, CO 80202",
      "location_latitude": 39.7392,
      "location_longitude": -104.9903,
      "notes": "Price too high"
    }
  ],
  "total": 1
}
```

### GET /api/books/scan-locations

Get summary of all scan locations.

**Response:**
```json
{
  "locations": [
    {
      "location_name": "Half Price Books Denver",
      "scan_count": 45,
      "accepted_count": 12,
      "rejected_count": 33,
      "last_scan": "2025-10-23 16:54:10"
    }
  ],
  "total": 1
}
```

### GET /api/books/scan-stats

Get overall scan statistics.

**Response:**
```json
{
  "total_scans": 714,
  "unique_books": 650,
  "accepted": 450,
  "rejected": 250,
  "skipped": 14,
  "first_scan": "2025-01-15 10:00:00",
  "last_scan": "2025-10-23 16:54:10",
  "unique_locations": 8
}
```

## Privacy Considerations

- Location data is optional
- Stored only on user's device/server
- Can be disabled in app settings
- location_name can be manually set (e.g., "Bookstore A") for privacy

## Example Workflow

```python
from pathlib import Path
from shared.database import DatabaseManager

db = DatabaseManager(Path.home() / '.isbn_lot_optimizer' / 'catalog.db')

# User scans a book
isbn = '9780385497466'

# Check if scanned before
previous = db.get_scan_history(isbn=isbn, limit=1)
if previous:
    print(f"⚠️  You saw this book on {previous[0]['scanned_at']}")
    print(f"   at {previous[0]['location_name']}")
    print(f"   Decision: {previous[0]['decision']}")

# ... evaluate book ...

# Log the decision
db.log_scan(
    isbn=isbn,
    decision='ACCEPT',  # or 'REJECT'
    title='The Brethren',
    authors='John Grisham',
    estimated_price=12.99,
    probability_label='MEDIUM',
    probability_score=0.65,
    location_name='Half Price Books',
    location_latitude=39.7392,
    location_longitude=-104.9903,
    app_version='1.0.0'
)
```

## View Your Scan History

Quick command to see your scan history:

```bash
python3 -c "
from pathlib import Path
from shared.database import DatabaseManager

db = DatabaseManager(Path.home() / '.isbn_lot_optimizer' / 'catalog.db')

# Get recent scans
scans = db.get_scan_history(limit=20)
for scan in scans:
    symbol = '✓' if scan['decision'] == 'ACCEPT' else '✗'
    print(f\"{symbol} {scan['scanned_at']}: {scan['title']}\")
    if scan['location_name']:
        print(f\"   @ {scan['location_name']}\")
"
```

## Database Location

`~/.isbn_lot_optimizer/catalog.db`

Table created automatically on first database access.

---

**Status:** Database schema complete, API methods implemented
**Next:** Service layer integration + iOS location tracking
**Created:** 2025-10-23
