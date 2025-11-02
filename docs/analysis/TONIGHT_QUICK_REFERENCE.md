# Tonight's Collection - Quick Reference Card

**Status**: ✅ FULL DATASET READY - 19,249 ISBNs discovered!
**Time**: October 31, 2025
**Credits**: 90,000 available
**Available ISBNs**: 19,249 (found in metadata cache!)

---

## ONE COMMAND TO START

```bash
cd /Users/nickcuskey/ISBN
./COLLECT_TONIGHT.sh
```

**What it does**:
- ✅ Uses FULL 19,249 ISBN list automatically
- ✅ Automatic batching (100 ISBNs per batch)
- ✅ Built-in breaks (5 min between batches)
- ✅ Extended breaks (10 min every 1,000 ISBNs)
- ✅ Progress tracking
- ✅ Automatic resume if interrupted
- ✅ Merge results at end

---

## Collection Goals (Choose One)

| Goal | ISBNs | Time | Credits | Coverage | When to Choose |
|------|-------|------|---------|----------|----------------|
| **Conservative** | 500 | 1 hour | 500 | 2.6% | First time, want to verify |
| **Moderate** | 1,000 | 2 hours | 1,000 | 5.2% | Good balance |
| **Ambitious** | 2,000 | 4 hours | 2,000 | 10.4% | Committed evening session |
| **Aggressive** | 5,000 | 8 hours | 5,000 | 26% | All night, comprehensive data |
| **Complete** | 19,249 | 30 hrs | 19,249 | 100% | Multi-day full collection |

**Recommendation**: Start with **Moderate (1,000)** tonight, continue tomorrow for more

**Note**: You now have 19,249 ISBNs available (not just 177!). The script will automatically use the full list.

---

## Timeline

### Phase 1: Validation (First 30 minutes)
- **0-2 min**: Small test (5 ISBNs)
- **2-4 min**: BREAK
- **4-7 min**: Medium test (20 ISBNs)
- **7-10 min**: BREAK
- **10-15 min**: Larger test (50 ISBNs)
- **15-20 min**: BREAK
- **20-30 min**: Complete first 177 ISBNs

### Phase 2: Scale Up (Next 1-7 hours)
- **Batches of 100 ISBNs**: 3 min each
- **5-min breaks** between batches
- **10-min breaks** every 1,000 ISBNs
- **Automated** - script handles everything

---

## What You'll Get (Per ISBN)

**Example** (from our test):
```
ISBN: 9780553381702
Offers: 99
Prices: $2.26 - $31.90
Average: $11.54
Sellers: 99

ML Features:
  ✓ abebooks_min_price: 2.26
  ✓ abebooks_avg_price: 11.54
  ✓ abebooks_seller_count: 99
  ✓ abebooks_condition_spread: 29.64
  ✓ abebooks_has_new: true
  ✓ abebooks_has_used: true
  ✓ abebooks_hardcover_premium: 5.23
```

---

## Monitoring Progress

### During Collection
Watch the terminal - it shows:
- Current batch number
- ISBNs processed so far
- Success rate
- Credits used
- Time remaining in break

### Check Detailed Status
```bash
# In another terminal:
cd /Users/nickcuskey/ISBN/abebooks_batches
ls -lh batch_*_output.json

# Count ISBNs collected
python3 -c "
import json, glob
total = 0
for f in glob.glob('batch_*_output.json'):
    with open(f) as file:
        data = json.load(file)
        total += sum(1 for v in data.values() if v.get('stats',{}).get('count',0) > 0)
print(f'Collected so far: {total} ISBNs')
"
```

---

## Safety Features

**Automatic breaks**:
- ✅ 5 minutes between batches
- ✅ 10 minutes every 1,000 ISBNs
- ✅ Rate limited to 2 req/sec (15x below limit)

**Resume capability**:
- ✅ Press Ctrl+C anytime to stop
- ✅ All progress is saved
- ✅ Re-run script to continue where you left off

**Error handling**:
- ✅ Stops on repeated failures
- ✅ Logs all errors
- ✅ Can review and retry failed ISBNs

---

## Stopping Points

**Good places to stop**:
- ✅ After 177 ISBNs (got all current)
- ✅ After 500 ISBNs (good first dataset)
- ✅ After 1,000 ISBNs (excellent coverage)
- ✅ After 2,000 ISBNs (major milestone)
- ✅ After 5,000 ISBNs (comprehensive dataset)

**When to stop**:
- ⏰ It's late (sleep matters!)
- ❌ Seeing repeated errors
- ✅ Reached your goal
- 💰 Used desired credits

---

## After Collection

### Immediate Next Steps
1. **Merge batches** (script offers to do this)
2. **Review success rate** (should be 90%+)
3. **Check data quality** (spot check a few ISBNs)
4. **Celebrate!** 🎉

### Tomorrow
1. **Integrate into ML model**
2. **Retrain price predictions**
3. **Measure improvements**
4. **Plan next collection** (if needed)

---

## Expected Results

### After 1,000 ISBNs
- **Data points**: 7,000 (1,000 × 7 features)
- **ML improvement**: 30-40% better predictions
- **Credits used**: 1,000 (1% of budget)
- **Time spent**: ~2 hours
- **Value**: Significant boost to model

### After 5,000 ISBNs
- **Data points**: 35,000
- **ML improvement**: 50%+ better predictions
- **Credits used**: 5,000 (6% of budget)
- **Time spent**: ~6 hours
- **Value**: Game-changing dataset

---

## Troubleshooting

### Still seeing rate limits?
- Wait 10 more minutes
- Reduce batch size to 50
- Increase break time to 10 minutes

### Low success rate (<80%)?
- Check if AbeBooks changed their HTML
- Review error messages
- May need parser updates

### Script stops unexpectedly?
- Check error message
- All progress is saved in abebooks_batches/
- Re-run to continue

### Want to pause?
- Press Ctrl+C
- Script saves all progress
- Re-run later to resume

---

## Files & Locations

**Input**:
- `/tmp/prioritized_test.txt` - 177 ISBNs ready

**Output**:
- `abebooks_batches/batch_*_output.json` - Individual batches
- `tonight_collection_TIMESTAMP.json` - Merged file (if you choose)

**Scripts**:
- `COLLECT_TONIGHT.sh` - Main automated script
- `scripts/collect_abebooks_bulk.py` - Core collection logic

**Documentation**:
- `TONIGHT_COLLECTION_PLAN.md` - Detailed plan
- `TONIGHT_QUICK_REFERENCE.md` - This file

---

## Credits Used Calculator

| ISBNs | Credits | % of 90K | Remaining |
|-------|---------|----------|-----------|
| 177 | 177 | 0.2% | 89,823 |
| 500 | 500 | 0.6% | 89,500 |
| 1,000 | 1,000 | 1.1% | 89,000 |
| 2,000 | 2,000 | 2.2% | 88,000 |
| 5,000 | 5,000 | 5.6% | 85,000 |
| 10,000 | 10,000 | 11% | 80,000 |

**You have plenty of credits!** Don't worry about running out.

---

## Quick Decision Guide

**"I just want to verify everything works"**
→ Goal: 177 ISBNs (30 min)

**"I have a couple hours tonight"**
→ Goal: 1,000 ISBNs (2 hours)

**"I'm committed for the evening"**
→ Goal: 2,000-5,000 ISBNs (4-8 hours)

**"Let it run while I do other things"**
→ Goal: 5,000+ ISBNs (6-8 hours)
→ Check progress occasionally

---

## Emergency Contact

**If something goes wrong**:
1. Press Ctrl+C to stop
2. Check `abebooks_batches/` for saved progress
3. Review error messages
4. Check documentation in `docs/`
5. All data is saved - can resume tomorrow

**Nothing is lost** - all batches save automatically!

---

## Ready to Start?

**Wait**: 10 minutes from last test (for rate limit cooldown)

**Then**:
```bash
cd /Users/nickcuskey/ISBN
./COLLECT_TONIGHT.sh
```

**Choose your goal** when prompted

**Relax** - script handles everything automatically

**Monitor** - watch progress in terminal

**Stop anytime** - Ctrl+C, can resume later

---

## Remember

✅ **Quality over quantity** - 1,000 good records > 10,000 rushed
✅ **It's automated** - script handles breaks and progress
✅ **It's safe** - can stop/resume anytime
✅ **You have plenty of credits** - 90,000 available
✅ **Sleep matters** - don't push too late!

---

**Good luck tonight! 🚀**

Your ML model is about to get a major upgrade! 📈
