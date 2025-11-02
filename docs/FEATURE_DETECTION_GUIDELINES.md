# Feature Detection Guidelines

## Purpose

This document defines **when and where** to apply the `shared/feature_detector.py` module to extract book features (signed, edition, printing, cover_type, dust_jacket) from text.

## Critical Rule: Data Source Matters

The feature detector is designed to parse **marketplace listing titles** that contain rich feature information. It should **NEVER** be applied to basic ISBN metadata titles.

---

## ✅ DO Apply Feature Detection To:

### 1. eBay Listing Titles
**Why:** eBay sellers include detailed features to attract buyers

**Examples:**
```
✓ "The Martian by Andy Weir - SIGNED First Edition Hardcover w/DJ"
   Features: signed=True, edition="1st", cover_type="Hardcover", dust_jacket=True

✓ "Harry Potter Philosopher's Stone 1st/1st UK Edition"
   Features: edition="1st", printing="1st"

✓ "Stephen King IT - Mass Market Paperback Book Club Edition"
   Features: cover_type="Mass Market", special_features={"book club"}
```

**Implementation:**
```python
from shared.ebay_sold_comps import get_sold_comps
from shared.feature_detector import parse_all_features

# eBay listings include features in titles
sold_comps = get_sold_comps(isbn)
for comp in sold_comps:
    features = parse_all_features(comp['title'])  # ✓ CORRECT
    # Features will be detected from rich eBay titles
```

### 2. Training Data Collection
**Why:** Training data is collected specifically from eBay listings

**Examples:**
```python
# scripts/collect_training_data_poc.py
# Searches eBay for books with specific features (signed, first edition, etc.)
listing_title = "The Night Watchman Louise Erdrich SIGNED First Edition"
features = parse_all_features(listing_title)  # ✓ CORRECT
```

### 3. User-Entered Descriptions
**Why:** Users may describe their books using marketplace language

**Examples:**
```
User input: "I have a signed first edition hardcover with dust jacket"
features = parse_all_features(user_description)  # ✓ CORRECT
```

### 4. Other Marketplace Listings
**Why:** Similar to eBay, other marketplaces use feature-rich titles

- AbeBooks listings
- Amazon third-party seller listings
- Alibris listings
- BookFinder results

---

## ❌ DO NOT Apply Feature Detection To:

### 1. Catalog Book Titles (ISBN Metadata)
**Why:** These are basic publication titles without feature information

**Examples:**
```
✗ "The Night Watchman: Pulitzer Prize Winning Fiction"
   - This is a publication title, NOT a marketplace listing
   - Feature detection will return None for everything
   - Applying detection would be wasted CPU cycles

✗ "All the Light We Cannot See: A Novel"
   - Basic subtitle, no features present

✗ "The Martian: A Novel"
   - Generic title from ISBN database
```

**What NOT to do:**
```python
# catalog.db contains ISBN metadata titles - DO NOT parse!
book = get_book_from_catalog(isbn)
features = parse_all_features(book.title)  # ✗ WRONG! Will return empty
```

### 2. Metadata Cache Titles
**Why:** Comes from ISBN APIs (Google Books, Open Library, etc.)

**Examples from metadata_cache.db:**
```
✗ "1984"
✗ "To Kill a Mockingbird"
✗ "The Great Gatsby: The Authorized Text"
```

### 3. Google Books API Results
**Why:** Google provides publication metadata, not marketplace information

### 4. Open Library API Results
**Why:** Open Library provides bibliographic data, not sales listings

---

## The Data Loss Incident: Case Study

### What Happened (December 2024)

A script called `enrich_catalog_features.py` applied feature detection to catalog book titles:

```python
# THE BUG: Applied eBay feature detection to ISBN metadata titles
for isbn, title in catalog_books:
    features = parse_all_features(title)  # ✗ WRONG DATA SOURCE

    # Catalog titles like "The Night Watchman: Pulitzer Prize Winning Fiction"
    # have NO features, so detection correctly returns None

    # But then we overwrote existing good data with None!
    update_book(isbn,
        cover_type=features.cover_type,  # None - deletes existing data!
        printing=features.printing,      # None - deletes existing data!
        edition=features.edition          # None - deletes existing data!
    )
```

### Impact
- **287 feature fields deleted** from 127 books
- **125 cover_type values lost**
- **64 printing values lost**
- **98 edition values lost**

### Root Cause
Applied **eBay listing feature detection** to **ISBN metadata titles**

---

## How Features Enter the Database

### Correct Workflow

```
1. User scans ISBN
   ├─→ Fetch ISBN metadata (title, author, year)
   │   └─→ Store in catalog.db (NO feature detection)
   │
   └─→ Search eBay for sold comps
       └─→ Parse eBay listing titles for features (✓ USE feature_detector)
           └─→ Store features in catalog.db
```

### Feature Sources by Database

| Database | Feature Source | Apply Detection? |
|----------|----------------|------------------|
| `catalog.db` | Mixed: ISBN metadata (title) + eBay enrichment (features) | Only on eBay data |
| `training_data.db` | eBay listings | ✓ Yes |
| `metadata_cache.db` | ISBN APIs | ✗ No |

---

## Implementation Checklist

Before applying `parse_all_features()` to any text, ask:

- [ ] **Is this text from a marketplace listing?** (eBay, AbeBooks, etc.)
- [ ] **Was this text entered by a human describing a book for sale?**
- [ ] **Does this text potentially contain words like "signed", "first edition", "hardcover"?**

If NO to all three → **DO NOT apply feature detection**

---

## Safe Enrichment Pattern

When enriching existing data, always preserve existing values:

```python
# SAFE: Preserve existing data when detection returns nothing
new_cover_type = features.cover_type or old_cover_type
new_printing = features.printing or old_printing
new_edition = features.edition or old_edition
new_signed = features.signed or old_signed

# Only update if we have NEW information
if new_cover_type != old_cover_type:
    logger.info(f"{isbn}: cover_type {old_cover_type} -> {new_cover_type}")
    update_book(isbn, cover_type=new_cover_type)
```

**NEVER** do this:
```python
# DANGEROUS: Overwrites existing data with None
update_book(isbn, cover_type=features.cover_type)  # ✗ WRONG
```

---

## Reference: Feature Detector Capabilities

The `feature_detector.py` module can extract:

- **Signed/Autographed:** `signed` (boolean), 20+ patterns
- **Edition:** `edition` (1st, 2nd, limited, special, anniversary, etc.)
- **Printing:** `printing` (1st, 2nd, early, later)
- **Cover Type:** `cover_type` (Hardcover, Paperback, Mass Market)
- **Dust Jacket:** `dust_jacket` (boolean)
- **Special Features:** `special_features` (ex-library, book club, ARC, etc.)

See `/Users/nickcuskey/ISBN/shared/feature_detector.py` for full pattern list.

---

## Questions?

If you're unsure whether to apply feature detection to a particular data source:

1. **Check the source:** Is it from a marketplace or an ISBN API?
2. **Look at examples:** Do the titles contain features like "signed" or "first edition"?
3. **When in doubt, don't apply it** - Feature detection on the wrong data source causes no harm (returns None), but **enrichment scripts that overwrite data** can cause significant damage

---

## Document History

- **2025-01-31:** Created after catalog enrichment data loss incident
- **Purpose:** Prevent future misapplication of feature detection to wrong data sources
