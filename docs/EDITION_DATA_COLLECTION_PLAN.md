# Edition Data Collection Plan
## Full 18,702 ISBN Collection with Serper + Decodo

### Overview
Collect first edition vs later edition pricing data for ML training using:
- **Serper API** for marketplace discovery (cheap, fast)
- **Decodo Core** for page scraping when needed (30 req/sec)

### Cost Estimate

**Total ISBNs:** 18,702

**Serper Costs:**
- 1 search per ISBN = 18,702 searches
- Cost: Minimal (we have credits)

**Decodo Costs:**
- ~10 listings per ISBN = ~187,000 listings
- All need scraping (prices not in snippets)
- **Credits needed: 187,000**

**Current Status:**
- Have: 90,000 credits
- Need: 187,000 credits
- **Purchase needed: 100,000-200,000 credits**
- Cost: ~$200-400

### Timeline
- Serper phase: ~2 hours (rate limited to 3/sec)
- Decodo phase: ~2-3 hours (30 req/sec)
- **Total: ~4-5 hours**

### Implementation Status

#### ✅ Completed
1. Database schema (`edition_offers` table)
2. Serper integration and testing
3. Edition classification algorithms
4. Price extraction from HTML
5. Marketplace detection

#### 🔄 In Progress
- Decodo scraping integration

#### ⏳ Pending
- Full pipeline testing
- Credit purchase
- Production run
- Monitoring setup

### Next Steps

1. **Purchase Decodo Credits**
   - Go to Decodo dashboard
   - Buy 100K-200K credits package
   - Update credentials in `.env` if needed

2. **Test Full Pipeline**
   ```bash
   # Test with 5 ISBNs (will use ~50 Decodo credits)
   PYTHONPATH=/Users/nickcuskey/ISBN ./.venv/bin/python3.11 \\
     scripts/collect_edition_data_with_decodo.py --limit=5
   ```

3. **Launch Full Collection**
   ```bash
   # Run in background with logging
   PYTHONPATH=/Users/nickcuskey/ISBN ./.venv/bin/python3.11 \\
     scripts/collect_edition_data_with_decodo.py \\
     > /tmp/edition_collection_full.log 2>&1 &

   # Monitor progress
   tail -f /tmp/edition_collection_full.log
   ```

4. **Monitor Credit Usage**
   - Check Decodo dashboard periodically
   - Script logs credit usage every 100 ISBNs
   - Expected consumption: ~10 credits/ISBN

### Data Quality Checks

After collection completes, verify:
- Total ISBNs with data: should be close to 18,702
- Avg offers per ISBN: should be 5-10
- First edition coverage: >80% of ISBNs
- Later edition coverage: >80% of ISBNs
- Price ranges: reasonable ($5-$500 typical)

### Fallback Plan

If credits run out mid-collection:
1. Script will resume from last completed ISBN
2. Purchase more credits
3. Rerun script (will skip completed ISBNs)

### Success Criteria

Collection is successful when:
- ✅ At least 15,000 ISBNs have both first and later edition data
- ✅ Average 5+ offers per ISBN
- ✅ Edition classification confidence >0.7 for >70% of offers
- ✅ No major data quality issues

Then proceed to model retraining!
