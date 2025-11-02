# Decodo Core Plan: Cost-Benefit Analysis for Book Data Scraping

**Date**: October 31, 2025
**Core Plan Credits Available**: ~90,000 credits
**Current Issue**: Using expensive Advanced credits for Amazon scraping

---

## Executive Summary

**Recommendation**: Switch to AbeBooks scraping with Core plan for maximum value. Save Advanced credits for emergency use.

**Key Findings**:
- **AbeBooks**: Best ROI - provides unique market depth data not available elsewhere
- **Amazon**: Use official Product Advertising API instead (free tier available)
- **eBay**: Use official Finding API instead (free, 5K calls/day)
- **Core plan is ideal for sites without free APIs** (AbeBooks, Alibris, BookFinder)

---

## Scraping Target Comparison

### 1. AbeBooks 🥇 **HIGHEST PRIORITY**

**Cost**: ~1 credit per ISBN = **90,000 ISBNs** with Core plan

**Data Provided**:
- Multiple seller prices (10-50+ offers per book)
- Condition-specific pricing (New, Like New, Very Good, Good, Fair)
- Binding-specific pricing (Hardcover vs Softcover premiums)
- Seller count (market liquidity indicator)
- Price distribution (min, max, avg, median)

**ML Features Extracted**:
```python
{
    "abebooks_min_price": float,          # Lowest available price
    "abebooks_avg_price": float,          # Average market price
    "abebooks_seller_count": int,         # Market depth
    "abebooks_condition_spread": float,   # Price variance by condition
    "abebooks_has_new": bool,             # New copies available
    "abebooks_has_used": bool,            # Used market exists
    "abebooks_hardcover_premium": float   # HC vs SC price difference
}
```

**Value Proposition**:
- ✅ **Unique data** - No free API alternative
- ✅ **Market depth** - Multiple sellers show true demand
- ✅ **Condition analysis** - Critical for used book lots
- ✅ **Competitive intelligence** - See what others charge
- ✅ **Lot valuation** - Bulk purchase price guidance

**Technical Feasibility**:
- ✅ Core plan "universal" target supports it
- ✅ Standard HTML parsing (no complex JavaScript)
- ⚠️  May have light bot protection (render_js=true helps)
- ✅ Rate limit: 30 req/s (overkill for our needs)

**Use Cases**:
1. **ML model training** - Condition premiums, binding differentials
2. **Lot purchase decisions** - "Is $2/book a good deal?"
3. **Pricing strategy** - Optimal listing prices
4. **Market analysis** - Which books have deep markets

**Cost per Feature**: ~1.4 credits per feature (7 features)

**ROI Score**: ⭐⭐⭐⭐⭐ (5/5)

---

### 2. Amazon Product Data ⚠️ **SWITCH TO FREE API**

**Current Cost**: Using Advanced credits (expensive!)
**Better Alternative**: Amazon Product Advertising API (PA-API)

**Why NOT to use Decodo for Amazon**:
- ❌ Amazon has a **free official API** (PA-API 5.0)
- ❌ Wasting expensive Advanced credits
- ❌ Core plan may not support `amazon_product` target
- ❌ HTML parsing when structured JSON is available

**Amazon PA-API Benefits**:
- ✅ **FREE** for associates with sales
- ✅ Structured JSON (no parsing needed)
- ✅ Official, stable, won't break
- ✅ Rate limit: 8,640 requests/day (free tier)
- ✅ All data: rank, price, rating, reviews, details

**Action Required**:
1. Apply for Amazon Associates account
2. Get PA-API credentials
3. Stop using Decodo Advanced credits for Amazon

**ROI Score**: ⭐⭐⭐⭐⭐ (5/5) - **But use free API instead!**

---

### 3. eBay Sold Items ⚠️ **USE OFFICIAL API**

**Decodo Cost**: ~1 credit per ISBN
**Better Alternative**: eBay Finding API (Free)

**Why NOT to scrape eBay with Decodo**:
- ❌ eBay has **free official API** (Finding API)
- ❌ `findCompletedItems` gives sold comps
- ❌ Wasting credits on available data

**eBay Finding API Benefits**:
- ✅ **FREE** with developer account
- ✅ 5,000 calls per day
- ✅ Structured XML/JSON
- ✅ Official, reliable
- ✅ Advanced filtering (condition, price range, etc.)

**Action Required**:
1. Create eBay Developer account
2. Register for Finding API
3. Use `findCompletedItems` for sold comps

**ROI Score**: ⭐⭐⭐⭐⭐ (5/5) - **But use free API instead!**

---

### 4. Alibris 🥈 **SECOND PRIORITY**

**Cost**: ~1 credit per ISBN = **90,000 ISBNs** with Core plan

**Data Provided**:
- Used book marketplace (different inventory than AbeBooks)
- Pricing and condition data
- Signed/collectible book indicators
- International seller coverage

**ML Features**:
```python
{
    "alibris_min_price": float,
    "alibris_avg_price": float,
    "alibris_seller_count": int,
    "alibris_has_collectible": bool
}
```

**Value Proposition**:
- ✅ Different sellers than AbeBooks (more market coverage)
- ✅ Good for rare/collectible books
- ✅ No free API alternative
- ⚠️  Some overlap with AbeBooks data

**Technical Feasibility**:
- ✅ Core plan "universal" target
- ⚠️  May have CAPTCHA protection
- ✅ Similar structure to AbeBooks

**ROI Score**: ⭐⭐⭐⭐ (4/5) - Good, but AbeBooks is more valuable

---

### 5. BookFinder 🥉 **THIRD PRIORITY**

**Cost**: ~1 credit per ISBN

**Data Provided**:
- Price aggregation from 100,000+ booksellers
- Comparison across Amazon, AbeBooks, Alibris, etc.
- New and used price ranges
- Availability indicators

**ML Features**:
```python
{
    "bookfinder_lowest_price": float,
    "bookfinder_source_count": int,
    "bookfinder_new_vs_used_spread": float
}
```

**Value Proposition**:
- ✅ Single source for comprehensive pricing
- ✅ Validates other data sources
- ✅ Shows absolute market floor price
- ⚠️  Data is aggregated (less detail than direct sources)

**Technical Feasibility**:
- ✅ Core plan "universal" target
- ⚠️  Complex page structure (aggregation site)
- ⚠️  Parsing may be fragile

**ROI Score**: ⭐⭐⭐ (3/5) - Useful for validation, but indirect

---

### 6. ThriftBooks ⚠️ **LOW PRIORITY**

**Cost**: ~1 credit per ISBN

**Data Provided**:
- Single retailer pricing
- Condition grades
- In-stock availability

**Why LOW priority**:
- ❌ Only one seller's data (not market-wide)
- ❌ ThriftBooks pricing is already on Amazon/AbeBooks
- ❌ Limited unique value
- ⚠️  May have aggressive bot protection

**ROI Score**: ⭐⭐ (2/5) - Low value per credit

---

### 7. WatchCount (eBay Analytics) ⚠️ **ADVANCED CREDITS ONLY**

**Cost**: ~1 Advanced credit per ISBN (expensive!)

**Challenges**:
- ❌ Has CAPTCHA protection
- ❌ Requires Advanced plan (4.5K credits remaining)
- ❌ Alternative: eBay official API (free)
- ⚠️  Rate limit issues observed

**Recommendation**: Use eBay Finding API instead (free, no CAPTCHA)

**ROI Score**: ⭐ (1/5) - Not worth Advanced credits

---

## Recommended Strategy

### Phase 1: Switch Amazon to Free API ✅ **IMMEDIATE**

**Action**: Stop using Decodo for Amazon
- Set up Amazon PA-API
- Save 90K Core credits for AbeBooks
- Save 4.5K Advanced credits for emergencies

**Impact**:
- $0 cost for Amazon data (vs burning credits)
- Frees up all credits for unique data sources

---

### Phase 2: Bulk AbeBooks Collection 📚 **CORE PLAN**

**Target**: Collect 5,000-10,000 high-value books

**Selection Criteria**:
1. Books you frequently encounter in lots
2. Books with existing Amazon data (for correlation)
3. Books with high Amazon sales rank (< 100K)
4. First edition/collectible categories
5. Books in your specialist genres

**Cost**: 5,000-10,000 credits (5-11% of Core plan budget)

**Expected Value**:
- 7 new ML features per book
- Market depth indicators
- Condition premium coefficients
- Lot purchase confidence scores

**Script Usage**:
```bash
# Test with 50 books first
python3 scripts/collect_abebooks_bulk.py --limit 50

# Full collection (5000 books)
python3 scripts/collect_abebooks_bulk.py --limit 5000 --resume
```

---

### Phase 3: Targeted Alibris Collection 🎯 **OPTIONAL**

**Target**: Books not found on AbeBooks or rare/collectible titles

**Cost**: 1,000-2,000 credits

**Use When**:
- AbeBooks returns zero results
- Targeting collectible/signed books
- Need broader market coverage

---

### Phase 4: Reserve Remaining Credits 💾

**Keep 70-80K credits in reserve for**:
- Weekly/monthly data refreshes
- New ISBN discoveries
- Seasonal pricing updates
- Model retraining cycles

**Maintenance Schedule**:
- Monthly: Refresh top 1,000 books (1K credits/month)
- Quarterly: Refresh top 5,000 books (5K credits/quarter)
- Yearly: Full refresh (90K credits)

---

## Credit Allocation Plan

| Use Case | Credits | % of Budget | ISBNs | Priority |
|----------|---------|-------------|-------|----------|
| **Initial AbeBooks collection** | 10,000 | 11% | 10,000 | 🔥 High |
| **Alibris collectibles** | 2,000 | 2% | 2,000 | 🎯 Medium |
| **Monthly refreshes (12 months)** | 12,000 | 13% | 1,000/mo | 🔄 Ongoing |
| **Quarterly full refresh** | 20,000 | 22% | 5,000/qtr | 🔄 Ongoing |
| **Reserve / Buffer** | 46,000 | 51% | - | 💾 Reserve |
| **TOTAL** | 90,000 | 100% | - | - |

---

## Implementation Checklist

### Immediate Actions (Week 1)

- [ ] **Stop using Decodo for Amazon** (save Advanced credits!)
- [ ] Set up Amazon PA-API credentials
- [ ] Test AbeBooks scraper with 10 ISBNs (verify Core plan access)
- [ ] Verify Decodo Core plan credentials and status
- [ ] Create prioritized ISBN list (10K books)

### Short Term (Week 2-3)

- [ ] Run AbeBooks collection for 1,000 test books
- [ ] Validate data quality and parsing accuracy
- [ ] Integrate AbeBooks features into ML model
- [ ] Measure ML model improvement with new features

### Medium Term (Month 1-2)

- [ ] Scale to 10,000 AbeBooks ISBNs
- [ ] Add Alibris scraper for collectibles
- [ ] Set up eBay Finding API for sold comps
- [ ] Establish monthly refresh schedule

### Long Term (Ongoing)

- [ ] Monitor credit usage vs budget
- [ ] Quarterly data refreshes
- [ ] Expand to new categories as budget allows
- [ ] Optimize scraping targets based on ML feature importance

---

## Expected ML Model Improvements

### Current State (Amazon only)
- Features: 7 Amazon features
- Training samples: ~750 books
- Feature completeness: 85%
- Test MAE: ~$0.87

### After AbeBooks Integration
- Features: **14 total** (7 Amazon + 7 AbeBooks)
- Training samples: 10,000+ books
- Feature completeness: **95%+**
- Expected Test MAE: **$0.40-0.50** (50% improvement!)

### New Capabilities
- ✅ Condition premium prediction
- ✅ Hardcover vs softcover pricing
- ✅ Market depth analysis (liquidity)
- ✅ Lot purchase recommendations
- ✅ Optimal listing price suggestions

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Core plan doesn't work** | High | Test with 10 ISBNs first; verify account status |
| **AbeBooks blocks scraping** | High | Use render_js=true; slower rate limits; contact Decodo |
| **Credits run out early** | Medium | Conservative allocation; monitor usage |
| **Parsing breaks** | Low | Robust parser with fallbacks; test regularly |
| **Data quality issues** | Low | Validation checks; manual spot checks |

---

## Success Metrics

### Collection Phase
- ✅ Successfully collect 10K AbeBooks ISBNs
- ✅ 90%+ success rate (9K+ valid results)
- ✅ Average 5+ offers per ISBN
- ✅ < 10K credits used

### ML Integration Phase
- ✅ All 7 AbeBooks features integrated
- ✅ Feature importance > 5% for top features
- ✅ Test MAE improves by 30%+
- ✅ R² score > 0.80

### Business Impact
- ✅ Lot purchase confidence score implemented
- ✅ Can predict individual book prices ±$0.50
- ✅ Optimal pricing recommendations validated
- ✅ ROI positive within 1 month

---

## Cost Per Feature Analysis

**AbeBooks** (7 features): ~1.4 credits per feature
**Alibris** (4 features): ~2.5 credits per feature
**BookFinder** (3 features): ~3.3 credits per feature

**Winner**: AbeBooks provides most features per credit spent

---

## Conclusion

**Use Core plan (90K credits) for AbeBooks scraping** - this is your highest-value target with no free alternative.

**Switch Amazon to PA-API (free)** - stop wasting Advanced credits.

**Use eBay Finding API (free)** - no need to scrape.

**Reserve Advanced credits (4.5K)** - only for heavily protected sites as needed.

This strategy maximizes your data collection ROI and provides the most valuable features for ML model improvement.
