# Phase 3: Configurable Thresholds - Testing Guide

## Overview
Phase 3 adds user-configurable decision thresholds that allow fine-tuning the buy/skip/review decision logic without code changes.

## What Was Implemented

### 1. Decision Thresholds Model
Located: `LotHelperApp/LotHelper/ScannerReviewView.swift` (lines 36-95)

**Configurable Parameters:**
- **Minimum Auto-Buy Profit**: $1-$15 (default: $5)
- **Slow-Moving Threshold**: $3-$20 (default: $8)
- **Uncertainty Threshold**: $1-$10 (default: $3)
- **Minimum Confidence Score**: 30-80% (default: 50%)
- **Low Confidence Threshold**: 10-50% (default: 30%)
- **Minimum Comps Required**: 1-10 (default: 3)
- **Max Slow-Moving TTS**: 60-365 days (default: 180)
- **Require Profit Data**: Boolean (default: true)

**Presets:**
- **Conservative**: Higher profit requirements, more comps, stricter criteria
- **Balanced**: Default values, recommended for most users
- **Aggressive**: Lower profit requirements, fewer comps, higher risk/volume

### 2. Settings UI
Located: `LotHelperApp/LotHelper/DecisionThresholdsSettingsView.swift`

**Features:**
- Quick preset selection (Conservative/Balanced/Aggressive)
- Individual slider controls for each threshold
- Real-time value display
- Auto-save on change
- Reset to defaults button

**Access:**
- Toolbar button (slider icon) in Scanner Review View
- Presents as a modal sheet

### 3. Persistence
**Storage**: UserDefaults (JSON encoded)
**Key**: `"decisionThresholds"`
**Load**: Automatic on view initialization
**Save**: Automatic on any threshold change

## Testing Scenarios

### Scenario 1: Preset Selection
**Objective**: Verify presets apply correct values

**Steps:**
1. Open Scanner Review View
2. Tap slider icon (⚙️) in toolbar
3. Tap "Conservative (High Profit, Low Risk)"
4. Verify settings:
   - Min Auto-Buy Profit: $8.00
   - Min Confidence: 60%
   - Min Comps: 5
   - Max Slow TTS: 120 days
5. Scan a marginal book ($6 profit, 40 comps)
   - **Expected**: Should SKIP (doesn't meet $8 threshold)
6. Tap "Aggressive (Low Profit, High Volume)"
7. Scan same book
   - **Expected**: Should BUY (meets $3 threshold)

### Scenario 2: Custom Threshold Configuration
**Objective**: Verify custom settings affect decisions

**Steps:**
1. Reset to Balanced preset
2. Set Min Auto-Buy Profit to $10
3. Scan book with $8 profit, 70% confidence
   - **Expected**: SKIP ("Only $8.00 profit - needs higher confidence")
4. Lower Min Auto-Buy Profit to $5
5. Scan same book
   - **Expected**: BUY ("Good confidence + $8.00 via eBay")

### Scenario 3: Needs Review Triggers
**Objective**: Verify review thresholds work correctly

**Steps:**
1. Set Min Comps Required to 5
2. Scan book with only 2 comps
   - **Expected**: NEEDS REVIEW ("Only 2 comparable listings found")
3. Set Min Comps Required to 2
4. Scan same book
   - **Expected**: No longer flagged for insufficient comps
5. Set Max Slow-Moving TTS to 90 days
6. Scan slow book with 120-day TTS and $7 profit
   - **Expected**: NEEDS REVIEW ("Slow velocity + thin margin")

### Scenario 4: Confidence Thresholds
**Objective**: Verify confidence scoring affects decisions

**Steps:**
1. Set Min Confidence Score to 70%
2. Scan book with 60% confidence, $10 profit
   - **Expected**: Review or tempered recommendation
3. Lower Min Confidence Score to 40%
4. Scan same book
   - **Expected**: Stronger BUY recommendation

### Scenario 5: Persistence Across Sessions
**Objective**: Verify settings persist after app restart

**Steps:**
1. Set custom thresholds:
   - Min Auto-Buy: $7.50
   - Min Confidence: 55%
   - Min Comps: 4
2. Close app completely (swipe away)
3. Reopen app
4. Check settings
   - **Expected**: All values match step 1
5. Scan a book
   - **Expected**: Decisions use custom thresholds

### Scenario 6: Real-World Validation
**Objective**: Test with actual book data

**Test Books:**
1. **High-Value Book** (Harry Potter first edition)
   - Conservative: Should BUY
   - Balanced: Should BUY
   - Aggressive: Should BUY

2. **Marginal Book** ($4 profit, 45% confidence, 8 comps)
   - Conservative: Should SKIP
   - Balanced: Should SKIP or REVIEW
   - Aggressive: Should BUY

3. **Uncertain Book** (2 comps, no buyback, $8 estimate)
   - Conservative: NEEDS REVIEW (min 5 comps)
   - Balanced: NEEDS REVIEW (min 3 comps fails)
   - Aggressive: May BUY or REVIEW

4. **Slow-Moving Book** (250-day TTS, $6 profit)
   - Conservative: NEEDS REVIEW (TTS > 120 days)
   - Balanced: NEEDS REVIEW (TTS > 180 days fails at 250)
   - Aggressive: May BUY (TTS threshold 240 days)

## Expected Behavior

### Auto-Buy Conditions (with default balanced thresholds)
- Buyback profit > $0 (always prioritized)
- Net profit ≥ $10 (strong buy threshold = 2x min)
- Net profit ≥ $5 with confidence ≥ 50%
- Net profit ≥ $5 with high confidence label
- Series completion with ≥ $3 profit

### Needs Review Conditions
- Total comps < 3
- Conflicting signals (profitable buyback + negative eBay)
- Slow velocity (TTS > 180 days) + thin margin (< $8)
- Low confidence (< 30%) + minimal profit (< $3)
- No profit data + moderate confidence (< 50%)

### Skip Conditions
- Net profit below minimum threshold
- Loss after fees
- Insufficient confidence for profit level

## UI Validation Checklist

- [ ] Slider icon visible in toolbar
- [ ] Settings sheet opens on tap
- [ ] Preset buttons apply correct values
- [ ] Sliders move smoothly
- [ ] Values display correctly next to sliders
- [ ] Changes auto-save (check UserDefaults)
- [ ] Reset button restores defaults
- [ ] Done button dismisses sheet
- [ ] Settings persist across app restarts

## Integration Validation

- [ ] Thresholds loaded on view init
- [ ] Decision logic uses current thresholds
- [ ] All 4 call sites pass thresholds parameter
- [ ] Concerns list shows relevant threshold violations
- [ ] Buy/skip reasons reflect threshold-based decisions

## Success Criteria

✅ **Phase 3 Complete When:**
1. All presets apply correct threshold values
2. Custom thresholds affect buy/skip/review decisions
3. Settings persist across app sessions
4. UI responds smoothly to threshold changes
5. Decision logic correctly uses all threshold parameters
6. App builds and runs without errors

## Notes

- Thresholds are device-local (not synced across devices)
- Changes take effect immediately for new scans
- Previous decisions in database are not recalculated
- Conservative preset recommended for beginners
- Aggressive preset for high-volume, experienced users
- Balanced preset suitable for most use cases

## Future Enhancements (Phase 4+)

- Export/import threshold configurations
- Threshold analytics (track decision accuracy by preset)
- A/B testing different threshold combinations
- Machine learning to suggest optimal thresholds
- Seasonal threshold adjustments
- Category-specific thresholds (fiction vs. textbooks)
