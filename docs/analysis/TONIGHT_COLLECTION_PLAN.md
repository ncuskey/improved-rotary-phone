# Tonight's Incremental Collection Plan

**Goal**: Collect as much data as possible while respecting rate limits
**Credits Available**: 90,000
**ISBNs Available**: 177 (can generate more if needed)
**Strategy**: Gradual scale-up with breaks

---

## Phase 1: Validation (5-10 minutes)

### Batch 1A: Tiny Test (5 ISBNs)
**When**: Now (after current rate limit clears ~10 min)
**Size**: 5 ISBNs
**Time**: ~30 seconds collection
**Credits**: 5
**Break After**: 2 minutes

**Command**:
```bash
head -5 /tmp/prioritized_test.txt > /tmp/batch_1a.txt
python3 scripts/collect_abebooks_bulk.py --isbn-file /tmp/batch_1a.txt --output batch_1a.json
```

**Success Criteria**:
- ✅ All 5 ISBNs collected successfully
- ✅ Average 10+ offers per ISBN
- ✅ No rate limit errors

---

### Batch 1B: Small Test (20 ISBNs)
**When**: 2 minutes after Batch 1A
**Size**: 20 ISBNs
**Time**: ~1 minute
**Credits**: 20
**Break After**: 3 minutes

**Command**:
```bash
head -25 /tmp/prioritized_test.txt | tail -20 > /tmp/batch_1b.txt
python3 scripts/collect_abebooks_bulk.py --isbn-file /tmp/batch_1b.txt --output batch_1b.json
```

**Cumulative**: 25 ISBNs, 25 credits

---

## Phase 2: Scale Up (20-30 minutes)

### Batch 2A: Medium (50 ISBNs)
**When**: 3 minutes after Batch 1B
**Size**: 50 ISBNs
**Time**: ~2 minutes
**Credits**: 50
**Break After**: 5 minutes

**Command**:
```bash
head -75 /tmp/prioritized_test.txt | tail -50 > /tmp/batch_2a.txt
python3 scripts/collect_abebooks_bulk.py --isbn-file /tmp/batch_2a.txt --output batch_2a.json --resume
```

**Cumulative**: 75 ISBNs, 75 credits

---

### Batch 2B: Complete Current Set (102 ISBNs)
**When**: 5 minutes after Batch 2A
**Size**: 102 ISBNs (remaining from 177 total)
**Time**: ~3 minutes
**Credits**: 102
**Break After**: 10 minutes

**Command**:
```bash
tail -102 /tmp/prioritized_test.txt > /tmp/batch_2b.txt
python3 scripts/collect_abebooks_bulk.py --isbn-file /tmp/batch_2b.txt --output batch_2b.json --resume
```

**Cumulative**: 177 ISBNs, 177 credits (0.2% of budget)

**Checkpoint**: Review results, verify quality

---

## Phase 3: Generate More ISBNs (5 minutes)

**Goal**: Get more ISBNs from databases to continue

**Command**:
```bash
python3 scripts/prioritize_isbns_for_collection.py \
  --all \
  --output tonight_full_collection.txt \
  --limit 10000
```

**Expected**: Find all available ISBNs in databases (may be 177-1000+ depending on data)

---

## Phase 4: Bulk Collection (1-3 hours)

**Strategy**: Collect in batches of 200 with 5-minute breaks

### Batch Sequence (200 ISBNs each)

| Batch | ISBNs | Time | Credits | Break |
|-------|-------|------|---------|-------|
| 3A | 200 | 5 min | 200 | 5 min |
| 3B | 200 | 5 min | 200 | 5 min |
| 3C | 200 | 5 min | 200 | 5 min |
| 3D | 200 | 5 min | 200 | 5 min |
| 3E | 200 | 5 min | 200 | 10 min |

**Per cycle (1000 ISBNs)**:
- Collection time: 25 minutes
- Break time: 30 minutes
- Total: 55 minutes
- Credits: 1,000

**Repeat cycles** until:
- All ISBNs collected, OR
- 10,000 ISBNs collected, OR
- It's time to stop for the night

---

## Automated Script

Use the automated script (creates this for you):
```bash
./COLLECT_TONIGHT.sh
```

**Features**:
- Automatic batching
- Built-in breaks
- Progress tracking
- Resume capability
- Stops if errors detected

---

## Safety Limits

### Rate Limiting
- **Max**: 30 req/sec (Decodo limit)
- **Our rate**: 2 req/sec (15x safety margin)
- **Batch size**: 200 ISBNs max
- **Break time**: 5 minutes between batches
- **Extended break**: Every 1000 ISBNs (10 minutes)

### Stop Conditions
- ❌ 3+ consecutive failures
- ❌ Rate limit errors
- ❌ Midnight (call it a night!)
- ✅ All ISBNs collected

---

## Progress Tracking

### Real-time Progress
```bash
# Check current collection status
ls -lh batch_*.json

# Count successful collections
python3 -c "
import json, glob
total = 0
success = 0
for f in glob.glob('batch_*.json'):
    with open(f) as file:
        data = json.load(file)
        total += len(data)
        success += sum(1 for v in data.values() if v.get('stats',{}).get('count',0) > 0)
print(f'Collected: {success}/{total} ({100*success/total:.1f}%)')
print(f'Credits used: ~{total}')
"
```

### After Each Phase
1. Check success rate (should be 90%+)
2. Review sample data quality
3. Confirm no rate limit errors
4. Decide to continue or stop

---

## Timeline Estimates

### Conservative (with breaks)
- Phase 1 (Validation): 15 minutes, 25 ISBNs
- Phase 2 (Scale Up): 30 minutes, 177 ISBNs
- Phase 3 (Generate More): 5 minutes
- Phase 4 (Bulk): 55 min per 1,000 ISBNs

**Total for 5,000 ISBNs**: ~4-5 hours
**Total for 10,000 ISBNs**: ~8-9 hours

### Aggressive (shorter breaks)
- Cut breaks in half
- Increase batch size to 500
- Risk: More likely to hit rate limits

**Total for 5,000 ISBNs**: ~2-3 hours
**Total for 10,000 ISBNs**: ~4-5 hours

---

## Tonight's Goal Options

### Conservative Goal: 2,000 ISBNs
- **Time**: ~2 hours
- **Credits**: 2,000 (2% of budget)
- **Risk**: Very low
- **Recommendation**: ✅ Safe, good first run

### Moderate Goal: 5,000 ISBNs
- **Time**: ~4 hours
- **Credits**: 5,000 (6% of budget)
- **Risk**: Low
- **Recommendation**: ✅ Excellent balance

### Aggressive Goal: 10,000 ISBNs
- **Time**: ~8 hours
- **Credits**: 10,000 (11% of budget)
- **Risk**: Medium (longer session)
- **Recommendation**: ⚠️ Only if you'll monitor it

---

## Checkpoints

### After 177 ISBNs (Phase 2 complete)
**Decision point**:
- ✅ Everything working well? → Continue to Phase 3
- ⚠️ Issues? → Review and adjust
- ❌ Major problems? → Stop and troubleshoot

### After 1,000 ISBNs
**Decision point**:
- Review data quality
- Check ML feature extraction
- Estimate remaining time
- Decide final goal for tonight

### After 5,000 ISBNs
**Decision point**:
- Major milestone reached!
- Good stopping point
- OR continue to 10K if time permits

---

## Emergency Stops

### If Rate Limited
1. Stop immediately
2. Wait 10 minutes
3. Test with 1 ISBN
4. Resume with longer breaks

### If Errors Spike
1. Check last 10 results
2. Identify pattern
3. Fix if simple (parser issue)
4. OR stop and investigate tomorrow

### If It's Late
1. Note current progress
2. All data is saved with --resume
3. Can continue tomorrow
4. Sleep is important! 😴

---

## Output Management

### File Naming
```
batch_1a.json         (5 ISBNs)
batch_1b.json         (20 ISBNs)
batch_2a.json         (50 ISBNs)
batch_2b.json         (102 ISBNs)
batch_3a.json         (200 ISBNs)
...
```

### Consolidation
After collection, merge all batches:
```bash
python3 scripts/merge_collection_results.py batch_*.json -o tonight_complete.json
```

---

## Success Metrics

### Data Quality
- ✅ 90%+ success rate
- ✅ Average 10+ offers per ISBN
- ✅ Price ranges look reasonable
- ✅ All 7 ML features extracted

### Performance
- ✅ No rate limit errors
- ✅ Collection speed: ~2-3 min per 100 ISBNs
- ✅ Stable throughout session

### Coverage
- ✅ 177+ ISBNs minimum
- ✅ 2,000+ ISBNs good
- ✅ 5,000+ ISBNs excellent
- ✅ 10,000+ ISBNs amazing!

---

## Next Steps After Tonight

### Tomorrow Morning
1. Review all collected data
2. Merge batch files
3. Calculate success rate
4. Integrate into ML model
5. Measure improvements

### This Week
1. Train updated price model
2. Validate predictions
3. Set up monthly refresh schedule
4. Generate more ISBNs if needed

---

## Ready to Start?

**Run**:
```bash
./COLLECT_TONIGHT.sh
```

**Or manual**:
```bash
# Phase 1A (wait 10 min from last test first!)
head -5 /tmp/prioritized_test.txt > /tmp/batch_1a.txt
python3 scripts/collect_abebooks_bulk.py --isbn-file /tmp/batch_1a.txt --output batch_1a.json

# Wait 2 minutes, then continue...
```

**Your goal for tonight**: Collect as many ISBNs as comfortable

**Remember**: Quality > Quantity. Better to collect 2,000 good records than rush 10,000 with errors.

**Good luck! 🚀**
