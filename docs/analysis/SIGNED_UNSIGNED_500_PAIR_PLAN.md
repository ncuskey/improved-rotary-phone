# Signed/Unsigned Book Pairs: 500-Pair Collection Plan

## Executive Summary

**Goal**: Collect 500 signed/unsigned book pairs for ML training
**Current Status**: 30 signed books collected
**Time to Complete**: 4-6 weeks
**Expected Model Improvement**: is_signed feature importance 2.3% → 6-10%

---

## Phase 1: Validate Initial 30 Pairs (Week 1)

### Step 1.1: Collect Unsigned Counterparts
```bash
# Collect unsigned comps for existing 30 signed ISBNs
python3 scripts/collect_unsigned_pairs.py --limit 30 \
  2>&1 | tee /tmp/unsigned_pairs_initial.log
```

**Expected Results**:
- 25-28 complete pairs (83-93% success rate)
- Unsigned comps should have 5-50 sold items each
- ETA: 30 minutes

### Step 1.2: Analyze Signing Premium
```bash
# Create analysis script
python3 scripts/analyze_signing_premium.py --pairs 30
```

**Key Metrics to Calculate**:
- Median signing premium: Expected +$2-8 (20-50%)
- Premium by author tier:
  - Bestselling authors: 30-60% premium
  - Mid-tier: 15-30% premium
  - Unknown: 0-15% premium
- Volume impact: Do signed books sell faster/slower?

**Decision Point**: If premium < 10%, signing may not be worth modeling

---

## Phase 2: Strategic ISBN Discovery (Weeks 2-3)

### Challenge: Finding 500 Signable Books

eBay doesn't directly search for "books that exist in both signed and unsigned versions." We need to be strategic:

### Strategy 2.1: Target Popular Authors
Popular authors are MORE LIKELY to have signed editions available:

**Top 50 Contemporary Authors to Target**:
- Thriller/Mystery: Lee Child, James Patterson, Michael Connelly, Harlan Coben, David Baldacci
- Literary Fiction: Margaret Atwood, Colson Whitehead, Jennifer Egan, Jonathan Franzen
- Fantasy/Sci-Fi: Brandon Sanderson, Patrick Rothfuss, N.K. Jemisin, Andy Weir
- Horror: Stephen King, Joe Hill, Paul Tremblay, Josh Malerman
- Historical: Ken Follett, Hilary Mantel, Anthony Doerr

**Collection Method**:
```bash
# Search for signed books by author
python3 scripts/discover_signed_isbns.py \
  --author "Lee Child" \
  --min-comps 5 \
  --output /tmp/lee_child_signed.txt
```

### Strategy 2.2: Mine Recent Bestsellers
Books from past 5-10 years are MORE LIKELY to have:
- Active secondary market (both signed & unsigned)
- Good sold comp data
- Consistent condition/edition information

**Target Lists**:
- NYT Bestseller lists (2015-2024)
- Goodreads Choice Awards winners
- BookTok/BookTube viral books
- Major literary prize winners

### Strategy 2.3: Leverage Book Signing Events
Authors who do signing tours = high availability of signed copies:

**Sources**:
- Author websites (tour dates)
- Bookstore event calendars (B&N, indie bookstores)
- Convention appearances (ThrillerFest, BookCon, etc.)

**Collection Approach**:
```bash
# Target books from authors with 2023-2024 signing tours
cat /tmp/signing_tour_authors.txt | \
  xargs -I {} python3 scripts/discover_signed_isbns.py --author "{}"
```

---

## Phase 3: Scaled Collection Pipeline (Weeks 3-5)

### 3.1: Parallel Collection Architecture

**5 Parallel Collectors** (same approach as metadata collection):
- Each collector handles 100 signed ISBNs
- Stagger start times by 2 seconds
- Rate limit: 1 request/second per collector
- ETA per batch: 100 books × 1 sec = ~2 minutes

```bash
# Split 500 ISBNs into 5 batches
split -l 100 -d /tmp/signed_isbns_500.txt /tmp/signed_batch_

# Launch 5 parallel collectors
for i in {0..4}; do
  python3 scripts/collect_training_data_poc.py \
    --category signed_hardcover \
    --isbn-file /tmp/signed_batch_0$i \
    --limit 100 \
    > /tmp/signed_collection_batch_$i.log 2>&1 &
  sleep 2
done
```

### 3.2: Unsigned Counterpart Collection

After signed collection completes:
```bash
# Collect unsigned pairs for all 500 ISBNs
python3 scripts/collect_unsigned_pairs.py --limit 500 \
  2>&1 | tee /tmp/unsigned_pairs_500.log
```

**Expected Timeline**:
- Signed collection: 2-3 days (including discovery + collection)
- Unsigned collection: 1 day
- **Total**: 3-4 days per 100 pairs

---

## Phase 4: Data Quality & Validation (Week 5-6)

### 4.1: Pair Validation

Ensure high-quality pairs:
```python
# scripts/validate_pairs.py
def validate_pair(signed_data, unsigned_data):
    """Validate a signed/unsigned pair."""
    checks = []

    # Must have sufficient comps (5+)
    checks.append(signed_data['count'] >= 5)
    checks.append(unsigned_data['count'] >= 5)

    # Prices should be reasonable (not outliers)
    checks.append(5 <= signed_data['median'] <= 100)
    checks.append(5 <= unsigned_data['median'] <= 100)

    # Signed should be >= unsigned (or very close)
    checks.append(signed_data['median'] >= unsigned_data['median'] * 0.9)

    # Same ISBN (sanity check)
    checks.append(signed_data['isbn'] == unsigned_data['isbn'])

    return all(checks)
```

### 4.2: Data Cleaning

Remove problematic pairs:
- Outliers (signed < unsigned)
- Insufficient volume (< 5 comps)
- Extreme premiums (> 200%) - likely different editions
- Missing metadata

**Expected Attrition**: 15-20% (500 collected → 400-425 usable pairs)

---

## Phase 5: Model Retraining (Week 6)

### 5.1: Training Data Integration

Combine all data sources:
```python
# Training data composition
sources = {
    'catalog.db': 742,           # Your inventory
    'training_data.db': 177,     # Previously collected
    'metadata_cache.db': 5921,   # Decodo/Amazon data
    'signed_pairs.db': 500,      # NEW: Signed books
    'unsigned_pairs.db': 500     # NEW: Unsigned counterparts
}

# Total: ~7,840 training samples
```

### 5.2: Feature Engineering

Add premium calculation features:
```python
features = {
    'is_signed': bool,                    # Existing feature
    'signing_premium_median': float,      # NEW: Median premium for author
    'signing_premium_pct': float,         # NEW: % premium for author
    'author_signing_frequency': float,    # NEW: How often author signs
}
```

### 5.3: Training & Evaluation

```bash
# Retrain with signed/unsigned pairs
python3 scripts/train_price_model.py \
  --include-signed-pairs \
  --min-pairs 400 \
  > /tmp/model_training_with_pairs.log 2>&1
```

**Expected Model Improvements**:
| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Test MAE | $3.62 | $3.30-3.50 | -3-9% |
| is_signed importance | 2.3% | 6-10% | +3-8pp |
| Signed book accuracy | Poor | Good | Significant |

---

## Resource Requirements

### API Quota Usage

**eBay API** (5,000 calls/day limit):
- Signed discovery: ~100 calls/day × 5 days = 500 calls
- Signed collection: 500 calls
- Unsigned collection: 500 calls
- **Total**: 1,500 calls (~30% of daily quota)

**Safe to run alongside other collections**

### Time Investment

| Phase | Duration | Effort |
|-------|----------|--------|
| Phase 1: Validate 30 pairs | 1 day | Low |
| Phase 2: ISBN discovery | 1-2 weeks | Medium |
| Phase 3: Scaled collection | 3-4 days | Low (automated) |
| Phase 4: Data validation | 2-3 days | Medium |
| Phase 5: Model retraining | 1 day | Low |
| **Total** | **4-6 weeks** | **Medium** |

### Cost Analysis

**All Free** (using free eBay API):
- eBay sold comps: Free
- Google Books metadata: Free
- Decodo pricing: Already collected
- Model training: Local compute

---

## Success Metrics

### Collection Metrics
- [ ] 500+ signed ISBNs collected
- [ ] 500+ unsigned ISBNs collected
- [ ] 400+ valid pairs after filtering
- [ ] 80%+ pair success rate

### Model Performance
- [ ] Test MAE improves by 3-9%
- [ ] is_signed feature importance > 5%
- [ ] Signed book predictions within $2 of actual
- [ ] Premium estimates ±20% accuracy

### Business Impact
- [ ] Can accurately price signed inventory
- [ ] Identify undervalued signed books to purchase
- [ ] Optimize pricing for signed items in lots
- [ ] Build "signing premium" knowledge base

---

## Risk Mitigation

### Risk 1: Insufficient Signed Book Availability
**Mitigation**:
- Start with top 100 popular authors
- Expand to BookTok/recent bestsellers
- Accept lower comp counts (3+ instead of 5+)

### Risk 2: Unsigned Counterparts Not Available
**Mitigation**:
- Many books have BOTH on eBay naturally
- Focus on books with high total volume (50+ total sales)
- Collect signed first, then validate unsigned availability

### Risk 3: Data Quality Issues
**Mitigation**:
- Implement strict validation checks
- Manual review of top 50 pairs
- Remove outliers aggressively (> 3σ)

---

## Next Steps (Immediate)

1. **Test unsigned collection** (30 min):
   ```bash
   python3 scripts/collect_unsigned_pairs.py --limit 30
   ```

2. **Analyze initial premium** (1 hour):
   ```bash
   python3 scripts/analyze_signing_premium.py
   ```

3. **If premium > 15%**, proceed with Phase 2 ISBN discovery

4. **If premium < 15%**, reconsider strategy or target higher-tier authors

---

## Conclusion

With **500 signed/unsigned pairs**, the model will learn:
- Base signature premium by author tier
- Premium variance by condition/edition
- Which books command the highest premiums
- When signing adds little/no value

This data will make the pricing model **significantly more accurate** for signed inventory and create a **competitive advantage** in the signed book market.

**Expected ROI**:
- Better pricing decisions: +10-20% profit on signed books
- Avoid overpaying: Identify overpriced signed items
- Strategic purchases: Target high-premium authors
