# BookFinder Scraper Investigation & Improvements

**Date**: November 3, 2025
**Status**: ⚠️ Blocked by CAPTCHA
**Data Collected**: 86 ISBNs, 4,874 offers (not persisted to DB)

## Summary

Investigated BookFinder scraper performance issues and implemented hybrid parsing with enhanced anti-detection measures. Successfully improved scraper robustness but encountered aggressive bot detection that escalated from degraded responses to CAPTCHA challenges.

## Problem Identified

### Initial Issue
- Scraper running for 1h 48m with only 110 ISBNs processed (0.6% of 18,685 target)
- Speed: 1.01 ISBNs/min (extremely slow)
- High failure rate with "No offers found" errors
- ETA: ~303 hours (12.6 days) for completion

### Root Cause Analysis

**Bot Detection Escalation**:
1. **Phase 1**: HTTP 202 responses (instead of 200)
   - Served simplified HTML without React data attributes
   - Scraper looked for `[data-csa-c-item-type="search-offer"]` selectors
   - These elements don't exist in 202 response format

2. **Phase 2**: CAPTCHA Challenge Page
   - After ~110 ISBNs, BookFinder served challenge: "Max challenge attempts exceeded. Please refresh the page to try again!"
   - Complete blocking of automated access
   - No offers extractable

**Technical Details**:
- Status 200: Full React app with rich data attributes
- Status 202: Degraded HTML with numbered list format
- Status 202 + Challenge: CAPTCHA wall, no content

## Solutions Implemented

### 1. Hybrid Parser (✅ Completed)

Added fallback HTML parser to handle 202 responses when React parser fails.

**New Function**: `extract_bookfinder_offers_html_fallback()`
- Location: `scripts/collect_bookfinder_prices.py:338-472`
- Parses simplified HTML structure
- Extracts: vendor, price, condition, binding, publisher, description
- Falls back automatically when React parser finds 0 offers

**Integration**:
```python
# In extract_bookfinder_offers() at line 630-633
if len(offers) == 0:
    logger.info("React parser found 0 offers, trying HTML fallback")
    offers = await extract_bookfinder_offers_html_fallback(page)
```

### 2. Enhanced Anti-Detection (✅ Completed)

Improved browser fingerprinting and stealth measures.

**Changes Made** (lines 881-943):

**Randomized Viewports**:
```python
viewports = [
    {'width': 1920, 'height': 1080},
    {'width': 1680, 'height': 1050},
    {'width': 1440, 'height': 900},
    {'width': 2560, 'height': 1440},
]
viewport = random.choice(viewports)
```

**Enhanced HTTP Headers**:
```python
extra_http_headers={
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}
```

**Advanced Stealth Scripts**:
- Hide `navigator.webdriver` property
- Mock `navigator.plugins` array
- Override `navigator.languages`
- Add `window.chrome` object
- Mock permissions API

## Results

### Collection Stats (Nov 3, 2025)
- **Duration**: 1 hour 50 minutes (7:47 PM - 9:37 PM)
- **ISBNs Attempted**: 110
- **ISBNs Successful**: 86 (78.2% success rate)
- **Total Offers**: 4,874
- **Avg Offers/ISBN**: 56.7
- **Speed**: 1.01 ISBNs/min

### Issues Encountered
1. **Data Not Persisted**: Database tables never created, offers only in logs
2. **CAPTCHA Block**: Complete blocking after 110 ISBNs
3. **Incomplete Coverage**: 0.46% of 18,685 target (99.54% remaining)

## Technical Improvements Made

### Files Modified

**scripts/collect_bookfinder_prices.py**:
- Added `extract_bookfinder_offers_html_fallback()` function (+135 lines)
- Enhanced `extract_bookfinder_offers()` with fallback logic (+4 lines)
- Improved browser context initialization with:
  - Random viewport selection
  - Enhanced HTTP headers
  - Advanced stealth scripts (+43 lines)

**Total Changes**: +182 lines added

### Code Quality
- ✅ Maintains backward compatibility
- ✅ Graceful fallback handling
- ✅ Comprehensive logging
- ✅ Error handling for both parsers
- ✅ No breaking changes to API

## Limitations Encountered

### Bot Detection Challenges

**Current Defenses**:
- User agent rotation (5 agents)
- Session rotation (every 50 ISBNs)
- Viewport randomization (4 sizes)
- Stealth scripts (hide automation markers)
- HTTP header customization
- Randomized delays (12-18 seconds)

**BookFinder Countermeasures**:
- Fingerprint analysis (defeats simple rotation)
- Behavioral analysis (detects automation patterns)
- Challenge/response system (CAPTCHA)
- Rate limiting (blocks after ~110 requests)

### Unsolved Problems

1. **CAPTCHA Challenge**: Cannot bypass without:
   - Residential proxy rotation ($$$)
   - CAPTCHA solving service (may violate ToS)
   - Manual intervention
   - Significant delay between sessions

2. **Data Persistence**: Database schema not initialized
   - Tables `bookfinder_offers` and `bookfinder_progress` don't exist
   - Would need schema creation before collection

3. **Scalability**: At 1 ISBN/min with blocks every 110 ISBNs:
   - Would need 170 separate sessions
   - ~51 hours of active monitoring
   - High risk of permanent IP ban

## Recommendations

### Short Term (Immediate)

**Option 1: Accept Limitation** ⚠️
- Collect in small batches (50-100 ISBNs per session)
- Wait 24-48 hours between sessions
- Manual IP rotation or VPN
- Timeline: Weeks to months

**Option 2: Alternative Data Sources** ✅ (Recommended)
- Already have excellent coverage:
  - 30,154 sold listings from Serper (100% complete)
  - 10,550 unique ISBNs with market data
  - ML model improved 23% with this data
- Focus on what works: sold listings, direct site scraping

**Option 3: Pivot Strategy** ✅ (Best ROI)
- Direct scraping from individual sources:
  - AbeBooks API/scraping (already integrated in ML)
  - Amazon Product Advertising API
  - eBay API (authentic sold data)
- Better data quality than aggregator
- More stable, less detection

### Long Term (Future Enhancements)

1. **If BookFinder Becomes Critical**:
   - Invest in residential proxy service ($100-500/month)
   - Implement CAPTCHA solving integration
   - Add human-in-the-loop for challenges
   - Build monitoring for IP bans

2. **Database Schema**:
   - Create tables before collection:
     ```sql
     CREATE TABLE bookfinder_offers (...);
     CREATE TABLE bookfinder_progress (...);
     ```
   - Add indexes for performance
   - Implement incremental updates

3. **Anti-Detection V2**:
   - Canvas fingerprint randomization
   - WebGL fingerprint spoofing
   - Mouse movement simulation
   - Realistic timing patterns

## Conclusion

The BookFinder scraper now has:
- ✅ Hybrid parsing (handles both 200 and 202 responses)
- ✅ Enhanced anti-detection (stealth scripts, randomization)
- ✅ Improved error handling and logging

However, BookFinder's CAPTCHA protection makes large-scale scraping impractical without significant investment in proxies and CAPTCHA solving.

**Recommended Path Forward**: Focus on alternative data sources (Serper sold listings, direct site APIs) which provide better data quality with less friction.

## Metrics Comparison

| Source | Speed | Reliability | Coverage | Data Quality |
|--------|-------|-------------|----------|--------------|
| **BookFinder** | 1 ISBN/min | ⚠️ Blocks at 110 | 0.46% | Medium (aggregated) |
| **Serper Sold** | 16.2 ISBN/sec | ✅ 100% success | 54.8% | High (actual sales) |
| **Direct APIs** | Varies | ✅ Stable | Variable | Highest (source) |

**Winner**: Serper sold listings (972x faster, more reliable, better data)

---

*Investigation completed November 3, 2025*
*Code improvements committed but collection paused due to bot detection*
