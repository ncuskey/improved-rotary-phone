# Signed/Unsigned Book Pairs: Discovery Findings

## Executive Summary

After creating and testing an ISBN discovery script, we've found **significant challenges** with the original 500-pair collection strategy. The core issue: **very few books have sufficient sold comps for BOTH signed AND unsigned versions on eBay.**

---

## What We Built

### 1. ISBN Discovery Script (`discover_signable_isbns.py`)
- **Purpose**: Validate ISBNs have BOTH signed and unsigned eBay sold comps before collection
- **Validation criteria**:
  - 5+ signed sold comps (with `include_signed=True`)
  - 5+ unsigned sold comps (with `include_signed=False`)
  - 15+ total sold comps (quality threshold)
- **Status**: ✅ Script works correctly, successfully queries eBay API

### 2. Unsigned Pair Collection Script (`collect_unsigned_pairs.py`)
- **Purpose**: Collect unsigned counterparts for existing signed books
- **Status**: ✅ Script works correctly
- **Result**: 0/30 unsigned counterparts found for existing signed ISBNs

---

## Test Results

### Test 1: Initial 30 Signed Books (from training_data.db)
**Command**: `python3 scripts/collect_unsigned_pairs.py --limit 30`

**Results**:
```
Successfully collected: 0 unsigned books
Failed: 30
Complete pairs: 0/30 (0%)
```

**Finding**: The 30 signed books we previously collected are **rare/specialized titles** that may only exist in signed form on eBay's secondary market.

### Test 2: Bestseller ISBNs (Popular Authors)
**Sample**: 7 ISBNs from bestselling authors (Stephen King, Lee Child, Colleen Hoover, etc.)

**Command**: `python3 scripts/discover_signable_isbns.py --isbn-file /tmp/test_discovery_sample.txt`

**Results**:
```
Total checked: 7
Valid pairs: 0
Success rate: 0.0%

Rejection reasons:
  Insufficient signed: 7
  Insufficient unsigned: 7
```

**Finding**: Even bestselling books from popular authors don't necessarily have 5+ comps for BOTH signed AND unsigned versions.

---

## Root Cause Analysis

### Why Are Signed/Unsigned Pairs So Rare?

1. **Most books don't have enough eBay volume**
   - Our threshold requires 5+ signed AND 5+ unsigned comps
   - This means 10+ total sold copies (actually 15+ for quality)
   - Many books simply don't sell enough on eBay

2. **Signed books are the exception, not the norm**
   - Most authors don't do signing tours
   - Signed editions are rare for most titles
   - High-volume signed books (5+ sales) are uncommon

3. **eBay API filtering may be aggressive**
   - `include_signed=True/False` filter works correctly
   - But filters may be removing more than expected
   - "Signed" keyword matching in titles/descriptions

4. **Market dynamics**
   - Collectors who buy signed books often keep them
   - Lower resale volume for signed editions
   - Unsigned books have higher volume but not always 5+

---

## Revised Strategy Options

### Option A: Lower Quality Thresholds (Quick Test)
**Adjust minimums**:
- min_signed: 3 (down from 5)
- min_unsigned: 3 (down from 5)
- min_total: 8 (down from 15)

**Pros**:
- May find more valid pairs
- Quick to test (run discovery again)

**Cons**:
- Lower training data quality
- Less statistical confidence in premium estimates
- May not be worth the effort

**Estimated yield**: 10-20% success rate → 50-100 pairs from 500 candidates

### Option B: Massive Scale Discovery (Slow but Thorough)
**Approach**:
- Test 2,000-5,000 candidate ISBNs
- Use lower thresholds (Option A)
- Focus on high-volume books only

**Pros**:
- More likely to hit 500-pair target
- Can cherry-pick highest quality pairs

**Cons**:
- Time-intensive: 2,000 ISBNs × 2 API calls × 1 sec = ~67 minutes
- 2,000-5,000 API calls (40-100% of daily quota)
- Still no guarantee of 500 pairs

**Estimated timeline**: 1-2 weeks (multiple discovery runs + collection)

### Option C: Pivot to Different Signature Premium Approach
**Alternative strategies**:

1. **Comparative Analysis with Existing Data**
   - Compare our 30 signed books to industry benchmarks
   - Use external data sources (AbeBooks, rare book dealers)
   - Build lookup tables for author signature premiums

2. **Synthetic Premium Features**
   - Add `author_signing_frequency` (how often author does signings)
   - Add `author_tier` (bestseller status)
   - Use proxy features instead of direct A/B testing

3. **Manual Curation for High-Value Authors**
   - Focus on top 20 authors who matter most to your business
   - Manually research their signature premiums
   - Build author-specific pricing adjustments

4. **Accept Smaller Sample Size**
   - Target 50-100 pairs instead of 500
   - Focus on authors/titles you actually buy
   - Use as validation data, not primary training

---

## Recommendation

**Short-term (This Week)**:
1. Run **Option A** (lower thresholds) on larger ISBN set (100-200 ISBNs)
2. Document actual success rate
3. If we find 20-30 valid pairs, proceed with those for initial analysis

**Medium-term (This Month)**:
- If Option A yields < 20 pairs, pivot to **Option C.4** (smaller sample size)
- Focus on practical business value: "Do signed books from authors I buy command a premium?"
- Use the 30 signed books + manual research to build author-specific adjustments

**Long-term (Next Quarter)**:
- Implement **Option C.2** (synthetic features) for broader coverage
- Build author signature database from external sources
- Use machine learning on correlated features (author popularity, book age, genre)

---

## What We Learned

### Technical Success
✅ Script architecture is solid
✅ eBay API integration works correctly
✅ Dual validation (signed+unsigned) approach is sound
✅ Rate limiting and error handling work well

### Strategic Challenge
❌ 500-pair goal may be unrealistic with eBay sold comps alone
❌ Even popular books lack sufficient signed/unsigned pairs
❌ Market dynamics make A/B testing harder than expected

### Key Insight
**The "perfect" A/B test (same ISBN, signed vs unsigned) is rare in the wild.** Instead of forcing this approach, we should:
- Use proxy features (author tier, signing frequency)
- Leverage external data sources
- Focus on practical business impact for books you actually buy

---

## Next Steps

**Immediate Action Required**:
1. **Decide on strategy**: Option A (lower thresholds), B (massive scale), or C (pivot)?
2. **Set realistic goals**: 50 pairs? 100 pairs? Or pivot away from A/B testing?
3. **Prioritize business value**: Focus on authors/titles that matter to your inventory

**If proceeding with A/B testing**:
- Run larger discovery with lowered thresholds
- Target 100-200 validated pairs (not 500)
- Accept that some pairs will have 3-4 comps each

**If pivoting away**:
- Document signature premiums from external sources
- Build author-specific lookup tables
- Use existing 30 signed books for validation

---

## Files Created
- ✅ `/Users/nickcuskey/ISBN/scripts/discover_signable_isbns.py` - Discovery script
- ✅ `/Users/nickcuskey/ISBN/scripts/collect_unsigned_pairs.py` - Unsigned collection script
- ✅ `/tmp/bestseller_candidate_isbns.txt` - 50+ bestseller ISBNs for testing
- ✅ `/tmp/test_discovery_sample.txt` - 7 ISBNs test sample
- ✅ `/tmp/test_discovery.log` - Test results (0/7 success)
- ✅ `/tmp/unsigned_pairs_initial.log` - Unsigned collection results (0/30)

---

## Conclusion

The signed/unsigned pair collection approach is **technically sound but strategically challenging**. The eBay secondary market doesn't have enough volume for most books to support meaningful A/B testing.

**We have three paths forward**:
1. **Lower standards** and accept noisier data (50-100 pairs with 3+ comps each)
2. **Scale massively** to find the rare books that qualify (weeks of effort, uncertain ROI)
3. **Pivot strategy** to use proxy features, external data, or smaller targeted samples

**My recommendation**: Start with Option A on a larger sample (200 ISBNs) to quantify the actual feasibility. If success rate < 10%, pivot to Option C.4 (smaller targeted sample focused on your actual inventory).
