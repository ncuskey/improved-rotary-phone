# Code Map: Incremental Lot Update Fix

**Date**: November 16, 2025
**Type**: Bug Fix
**Status**: ✅ Complete

## Overview

Fixed a critical bug where incremental lot updates (triggered when accepting books in the iOS app) accidentally deleted all lots and only restored the affected ones, causing most lots to disappear from the Lots tab.

## Problem Statement

When users accepted a book in the iOS app, it triggered an incremental lot update that was supposed to update only the affected lots (e.g., "Lee Child Collection" and "Jack Reacher Series"). However, due to an architectural flaw, the system deleted **ALL lots** from the database and only saved back the 1-2 affected lots, causing 6+ other lots to vanish.

### Symptoms

- User reports "the lots seem to have disappeared"
- After accepting a book in iOS app, Lots tab shows only 1-2 lots instead of 8
- Other author lots (Connelly, Berry, Baldacci, etc.) missing
- Series lots for unrelated authors gone

### Root Cause

The `update_lots_for_isbn()` method in `isbn_lot_optimizer/service.py` was designed for incremental updates but used `save_lots()`, which internally calls `replace_lots()`. The `replace_lots()` method performs a **full replacement**:

```python
# service.py:2548 - Incremental update tries to save ONLY affected lots
self.save_lots(enriched_candidates)  # Only 1-2 lots

# service.py:2094 - save_lots() calls replace_lots()
self.db.replace_lots(payloads)

# database.py:753 - replace_lots() DELETES ALL LOTS!
conn.execute("DELETE FROM lots")  # 💥 All lots deleted
conn.executemany("INSERT INTO lots...", payloads)  # Only 1-2 lots restored
```

**The architectural flaw**: `save_lots()` was designed for full regeneration (replace everything), but `update_lots_for_isbn()` tried to use it for incremental updates (update only affected lots). This mismatch caused the deletion bug.

## Changes Made

### 1. Add `upsert_lots()` Method
**File**: `shared/database.py`
**Lines**: 775-808
**Action**: Created new database method for incremental updates

**Implementation**:
```python
def upsert_lots(self, lots: Iterable[Dict[str, Any]]) -> None:
    """Update or insert lots without deleting unaffected ones.

    Uses INSERT OR REPLACE to update only the specified lots,
    preserving all other lots in the database. This is ideal for
    incremental lot updates where only affected lots need to be refreshed.
    """
    lot_payloads = list(lots)
    for payload in lot_payloads:
        payload["book_isbns"] = json.dumps(payload.get("book_isbns", []))
        payload.setdefault("justification", "")

    _log("upsert_lots", count=len(lot_payloads))
    with self._get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO lots (
                name, strategy, book_isbns,
                estimated_value, probability_label, probability_score,
                sell_through, justification,
                lot_market_value, lot_optimal_size, lot_per_book_price,
                lot_comps_count, use_lot_pricing,
                updated_at
            ) VALUES (
                :name, :strategy, :book_isbns,
                :estimated_value, :probability_label, :probability_score,
                :sell_through, :justification,
                :lot_market_value, :lot_optimal_size, :lot_per_book_price,
                :lot_comps_count, :use_lot_pricing,
                CURRENT_TIMESTAMP
            )
            """,
            lot_payloads,
        )
```

**Key Features**:
- Uses `INSERT OR REPLACE` to update only specified lots
- Relies on `UNIQUE(name, strategy)` constraint (already exists in schema)
- Preserves all unaffected lots in database
- Same payload format as `replace_lots()` for compatibility

### 2. Update Incremental Update Logic
**File**: `isbn_lot_optimizer/service.py`
**Lines**: 2540-2543
**Action**: Replaced delete + save pattern with direct upsert

**Before**:
```python
# Delete old versions of affected lots from database
with timer("Delete old affected lots", log=True, record=True):
    affected_names = [(lot.name, lot.strategy) for lot in enriched_candidates]
    for name, strategy in affected_names:
        self.db.delete_lot_by_name_and_strategy(name, strategy)

# Save enriched lots to database
with timer("Save updated lots", log=True, record=True):
    self.save_lots(enriched_candidates)  # BUG: This deletes ALL lots!
```

**After**:
```python
# Upsert enriched lots to database (preserves unaffected lots)
with timer("Upsert updated lots", log=True, record=True):
    payloads = [self._lot_to_payload(lot) for lot in enriched_candidates]
    self.db.upsert_lots(payloads)  # Only updates affected lots
```

**Changes**:
- Removed `delete_lot_by_name_and_strategy()` calls (unnecessary with UPSERT)
- Replaced `save_lots()` with direct `upsert_lots()` call
- Convert lots to payloads inline using `_lot_to_payload()`
- Clearer intent: "Upsert" explicitly means "update or insert"

## Technical Details

### SQLite UPSERT Pattern

The `INSERT OR REPLACE` statement works with the existing `UNIQUE(name, strategy)` constraint on the `lots` table:

```sql
-- Existing schema (no changes needed)
CREATE TABLE lots (
    ...
    name TEXT NOT NULL,
    strategy TEXT NOT NULL,
    ...
    UNIQUE(name, strategy)  -- This enables INSERT OR REPLACE
);

-- New upsert behavior
INSERT OR REPLACE INTO lots (...) VALUES (...);
-- If (name, strategy) exists: UPDATE the row
-- If (name, strategy) doesn't exist: INSERT new row
-- Other rows: UNTOUCHED
```

### Why This Works

1. **Unique Constraint**: The `UNIQUE(name, strategy)` constraint identifies which row to replace
2. **INSERT OR REPLACE**: Updates matching rows, inserts new rows, leaves others alone
3. **Atomic Operation**: Single SQL statement, no race conditions
4. **Efficient**: No need to query existing lots first

### Comparison with Previous Approach

| Aspect | Before (Broken) | After (Fixed) |
|--------|----------------|---------------|
| Method | `delete_lot_by_name_and_strategy()` + `save_lots()` | `upsert_lots()` |
| SQL Operations | DELETE individual lots + DELETE ALL + INSERT affected | INSERT OR REPLACE affected only |
| Unaffected Lots | Deleted by `replace_lots()` | Preserved |
| Database Calls | 3-4 (delete each + delete all + insert) | 1 (single executemany) |
| Race Conditions | Possible (separate deletes) | None (atomic upsert) |

## Files Modified

**shared/database.py** (lines 775-808)
- Added `upsert_lots()` method with `INSERT OR REPLACE` logic
- Mirrors `replace_lots()` structure for compatibility

**isbn_lot_optimizer/service.py** (lines 2540-2543)
- Replaced delete + save pattern with direct upsert call
- Removed unnecessary `delete_lot_by_name_and_strategy()` loop
- Converts lots to payloads inline

## Impact

**Before**:
- User accepts 1 Lee Child book in iOS app
- System updates "Lee Child Collection" + "Jack Reacher Series" (2 lots)
- `save_lots()` deletes all 8 lots, inserts only 2
- Result: 6 lots vanish (Connelly, Berry, Baldacci, etc.)

**After**:
- User accepts 1 Lee Child book in iOS app
- System updates "Lee Child Collection" + "Jack Reacher Series" (2 lots)
- `upsert_lots()` updates only those 2 lots
- Result: All 8 lots remain, 2 updated with fresh data

## Testing

The fix was verified by code review:

1. **Database Schema Verification**: Confirmed `UNIQUE(name, strategy)` constraint exists
2. **Logic Review**: Verified `INSERT OR REPLACE` semantics preserve unaffected rows
3. **Code Path Analysis**: Traced execution from iOS app through incremental update

**Expected Behavior**:
- ✅ Accepting books in iOS app triggers incremental lot updates
- ✅ Only affected lots are refreshed (author + series lots for that book)
- ✅ All other lots remain untouched in database
- ✅ Lots tab continues to show all lots

## Related Code

### iOS Book Acceptance Flow

```
iOS App (LotHelper)
  ↓
POST /api/books/{isbn}/accept (recalc_lots=False)
  ↓
isbn_web/api/routes/books.py:669-680
  ↓
Background task: service.update_lots_for_isbn(isbn)
  ↓
isbn_lot_optimizer/service.py:2485-2555
  ↓
db.upsert_lots(affected_lots)  ← Fixed here
  ↓
shared/database.py:775-808
```

### Lot Identification

Lots are uniquely identified by `(name, strategy)` tuple:
- Name: "Lee Child Collection", "Jack Reacher Series", etc.
- Strategy: "author", "series", "series_incomplete", etc.

This natural key enables UPSERT without needing to look up lot IDs.

## Future Enhancements

Potential improvements:
1. **Batch UPSERT**: Accumulate multiple incremental updates, upsert in batch
2. **Metrics**: Track upsert vs full regeneration performance
3. **Validation**: Add tests to prevent regression to delete-all pattern
4. **Documentation**: Document when to use `upsert_lots()` vs `replace_lots()`

## Lessons Learned

1. **Semantic Naming**: `save_lots()` implied "save these lots" but actually meant "replace all lots"
2. **Method Contracts**: Clear documentation of whether methods are incremental or full-replacement
3. **Database Patterns**: UPSERT is ideal for incremental updates with natural keys
4. **Architecture Alignment**: Incremental update systems need incremental database operations

## References

- **SQLite INSERT OR REPLACE**: https://www.sqlite.org/lang_conflict.html
- **Database Schema**: `docs/DATABASE_STRUCTURE.md`
- **Lot System Overview**: `isbn_lot_optimizer/lots.py`
- **Series Lot System**: `isbn_lot_optimizer/series_lots.py`
