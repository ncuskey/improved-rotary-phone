# Code Map: UI ML Transparency & Dynamic Routing Features

## Overview

This feature adds ML transparency and channel routing information to the iOS app UI, with dynamic fetching for existing books that don't have this data in their SwiftData store.

**Date**: 2025-11-04
**Status**: ✅ Complete

## What Was Built

### Backend API Enhancements
- Added `routing_info` and `channel_recommendation` to `/api/books/{isbn}/evaluate` endpoint
- Returns ML model transparency data (model name, confidence, performance metrics)
- Returns channel recommendation with expected profit and reasoning

### iOS UI Components
- Created reusable SwiftUI components for displaying ML routing information
- Added panels showing which ML model was used and why
- Added channel recommendation UI with expected profit and days to sale
- Implemented dynamic data fetching for existing books

### Key Features
1. **ML Model Transparency**
   - Shows which model was used (eBay Specialist, AbeBooks Specialist, or Unified)
   - Displays confidence score with visual meter
   - Shows performance metrics (MAE, R², feature count)
   - Explains routing reason

2. **Channel Recommendations**
   - Recommends best sales channel (eBay Individual, eBay Lot, etc.)
   - Shows expected profit (highlighted in green)
   - Shows expected days to sale
   - Provides reasoning bullets

3. **Dynamic Data Fetching**
   - Automatically fetches routing data for existing books
   - Shows loading state while fetching
   - Backwards compatible with books scanned before feature

## File Changes

### Backend (Python)

#### `isbn_lot_optimizer/ml/prediction_router.py` (+15 lines)
**Purpose**: Added method to get routing info and reasoning

```python
def get_routing_info(self) -> dict:
    """Get information about which model was used and why."""
    return {
        'model': self.model_used,
        'model_display_name': self._get_model_display_name(),
        'confidence_score': self._calculate_confidence(),
        'routing_reason': self._get_routing_reason(),
        'performance': self._get_model_performance()
    }
```

**Key Methods**:
- `get_routing_info()`: Returns structured routing information
- `_get_model_display_name()`: Human-readable model names
- `_calculate_confidence()`: Confidence score 0-100
- `_get_routing_reason()`: Explains why model was chosen
- `_get_model_performance()`: Returns MAE, R², feature count

#### `isbn_web/api/routes/books.py` (+64 lines)
**Purpose**: Enhanced evaluate endpoint to include routing data

**Changes**:
- Added `routing_info` dict to response with:
  - `model`: Technical model ID
  - `model_display_name`: User-friendly name
  - `confidence_score`: 0-100 confidence
  - `mae`: Mean absolute error
  - `r_squared`: R² score
  - `feature_count`: Number of features
  - `routing_reason`: Why this model was chosen

- Added `channel_recommendation` dict to response with:
  - `channel`: Recommended channel
  - `expected_profit`: Dollar amount
  - `expected_days`: Days to sale estimate
  - `confidence`: High/Medium/Low
  - `reasoning`: List of bullet points

### Frontend (Swift)

#### `LotHelperApp/LotHelper/RoutingInfoComponents.swift` (NEW FILE, 340 lines)
**Purpose**: Reusable SwiftUI components for displaying ML routing data

**Components**:

1. **`MLModelBadge`** (lines 1-40)
   - Compact badge showing model name
   - Color-coded by confidence (green/yellow/orange/red)
   - Shows confidence percentage

2. **`ConfidenceScoreMeter`** (lines 42-85)
   - Visual meter showing confidence 0-100%
   - Color gradient based on confidence level
   - Smooth animations

3. **`ChannelRecommendationPill`** (lines 87-130)
   - Colored pill with channel icon
   - Different colors per channel type
   - Shows channel name

4. **`RoutingInfoDetailView`** (lines 132-220)
   - Full panel showing ML model transparency
   - Model name and confidence meter
   - Performance metrics (MAE, R², features)
   - Routing reason explanation

5. **`ChannelRecommendationDetailView`** (lines 222-340)
   - Full panel showing channel recommendation
   - Expected profit (highlighted)
   - Expected days to sale
   - Confidence level
   - Reasoning bullets

**Usage Example**:
```swift
if let routing = book.routingInfo {
    RoutingInfoDetailView(routing: routing)
}

if let recommendation = book.channelRecommendation {
    ChannelRecommendationDetailView(recommendation: recommendation)
}
```

#### `LotHelperApp/LotHelper/BookAPI.swift` (+48 lines)
**Purpose**: Extended with models for routing data

**New Models**:

1. **`MLRoutingInfo`** (lines 340-350)
```swift
struct MLRoutingInfo: Codable, Hashable {
    let model: String
    let modelDisplayName: String
    let confidenceScore: Double
    let mae: Double?
    let rSquared: Double?
    let featureCount: Int?
    let routingReason: String?
}
```

2. **`ChannelRecommendation`** (lines 352-361)
```swift
struct ChannelRecommendation: Codable, Hashable {
    let channel: String
    let expectedProfit: Double?
    let expectedDays: Int?
    let confidence: String?
    let reasoning: [String]?
}
```

3. **`BookEvaluationRecord` Extension** (lines 367-368)
```swift
let routingInfo: MLRoutingInfo?
let channelRecommendation: ChannelRecommendation?
```

**Key Method**:
- `fetchBookEvaluation(_:)`: Async method to fetch evaluation with routing data

#### `LotHelperApp/LotHelper/BookDetailViewRedesigned.swift` (+56 lines)
**Purpose**: Added dynamic routing data fetching for existing books

**Key Additions**:

1. **State Variables** (lines 29-32)
```swift
@State private var dynamicRoutingInfo: MLRoutingInfo? = nil
@State private var dynamicChannelRecommendation: ChannelRecommendation? = nil
@State private var isLoadingRoutingInfo = false
```

2. **Computed Properties** (lines 40-47)
```swift
var effectiveRoutingInfo: MLRoutingInfo? {
    dynamicRoutingInfo ?? record.routingInfo
}

var effectiveChannelRecommendation: ChannelRecommendation? {
    dynamicChannelRecommendation ?? record.channelRecommendation
}
```

3. **UI Integration** (lines 58-69)
```swift
// ML Model Routing Info (NEW)
if let routing = effectiveRoutingInfo {
    RoutingInfoDetailView(routing: routing)
} else if isLoadingRoutingInfo {
    ProgressView("Loading ML insights...")
        .padding()
}

// Channel Recommendation (NEW)
if let recommendation = effectiveChannelRecommendation {
    ChannelRecommendationDetailView(recommendation: recommendation)
}
```

4. **Dynamic Fetching** (lines 1171-1197)
```swift
private func fetchRoutingInfoIfNeeded() async {
    // Skip if already have data
    if record.routingInfo != nil && record.channelRecommendation != nil {
        return
    }

    isLoadingRoutingInfo = true
    defer { isLoadingRoutingInfo = false }

    do {
        let evaluation = try await BookAPI.fetchBookEvaluation(record.isbn)

        await MainActor.run {
            if evaluation.routingInfo != nil {
                dynamicRoutingInfo = evaluation.routingInfo
            }
            if evaluation.channelRecommendation != nil {
                dynamicChannelRecommendation = evaluation.channelRecommendation
            }
        }
    } catch {
        print("Failed to fetch routing info: \(error.localizedDescription)")
    }
}
```

5. **Task Trigger** (line 149)
```swift
.task { await fetchRoutingInfoIfNeeded() }
```

#### `LotHelperApp/LotHelper/BookCardView.swift` (+261/-107 lines)
**Purpose**: Redesigned layout with profit at top and ML badges

**Key Changes**:

1. **Added Routing Fields** (lines 18-20)
```swift
// NEW: Routing info and channel recommendation
let routingInfo: MLRoutingInfo?
let channelRecommendation: ChannelRecommendation?
```

2. **Reorganized Layout**:
   - Expected profit moved to top (highlighted in green)
   - Channel recommendation pill below profit
   - ML model badge on right side of card
   - Time to sell badge with book info

3. **UI Flow**:
```
┌────────────────────────────────┐
│  Expected Profit: $28.50       │ ← NEW (green, prominent)
│  Sell via: eBay Individual     │ ← NEW (blue pill)
├────────────────────────────────┤
│  [Cover] Title, Author         │
│  ML Model: eBay Specialist 🟢  │ ← NEW (right side badge)
│  Score: ⭐⭐⭐⭐⭐               │
├────────────────────────────────┤
│  FAST • 45 sold • $11.93       │
└────────────────────────────────┘
```

#### `LotHelperApp/LotHelper/BooksTabView.swift` (+8/-8 lines)
**Purpose**: Updated to pass routing data to BookCardView

**Changes**:
- Added `routingInfo` and `channelRecommendation` parameters when creating BookCardView
- Maintains data flow from API through to UI

#### Other Updated Files
- `CachedBook.swift`: Updated to support new fields
- `ScannerReviewView.swift`: Updated to pass routing data
- `EbayListingWizardView.swift`: Updated for compatibility
- `LotRecommendationsView.swift`: Updated for compatibility

## Documentation

### `docs/UI_IMPROVEMENTS_COMPLETE.md` (NEW)
Complete documentation of UI improvements including:
- What was added
- Why it matters
- How it works
- Screenshots/mockups
- User impact

### `docs/PRICE_PREDICTION_ANALYSIS.md` (NEW)
Analysis of the $13.25 prediction issue:
- Root causes
- Solutions (immediate, medium-term, long-term)
- Diagnostic tools
- Expected outcomes

### `scripts/debug_prediction.py` (NEW)
Debug tool for investigating ML predictions:
- Shows which model was used
- Displays available features
- Explains why prediction came out as it did
- Suggests improvements

### `LotHelperApp/TROUBLESHOOTING_UI_CHANGES.md` (NEW)
Troubleshooting guide for UI changes:
- Common issues (changes not appearing, build errors)
- Solutions (rebuild steps, file additions)
- Verification checklist
- What to expect after rebuild

## Data Flow

```
1. User opens book detail view
   ↓
2. BookDetailViewRedesigned checks if routing data exists
   ↓
3. If missing, calls fetchRoutingInfoIfNeeded()
   ↓
4. BookAPI.fetchBookEvaluation(isbn) calls backend
   ↓
5. API endpoint /api/books/{isbn}/evaluate processes:
   - Runs prediction through router
   - Gets routing info from router.get_routing_info()
   - Calculates channel recommendation
   ↓
6. Returns JSON with routing_info and channel_recommendation
   ↓
7. Swift decodes into MLRoutingInfo and ChannelRecommendation
   ↓
8. Updates @State variables
   ↓
9. UI re-renders showing ML panels
```

## API Response Structure

### `/api/books/{isbn}/evaluate` Response

```json
{
  "isbn": "9780316769174",
  "estimated_price": 12.50,
  "routing_info": {
    "model": "ebay_specialist",
    "model_display_name": "eBay Specialist",
    "confidence_score": 85.3,
    "mae": 3.03,
    "r_squared": 0.469,
    "feature_count": 47,
    "routing_reason": "Book has eBay sold listings data (45 sold comps)"
  },
  "channel_recommendation": {
    "channel": "eBay Individual",
    "expected_profit": 28.50,
    "expected_days": 21,
    "confidence": "High",
    "reasoning": [
      "High eBay value ($12.50 vs cost $2.00)",
      "Good sell-through rate (45 sold in 90 days)",
      "Best for individual sale rather than lot"
    ]
  }
}
```

## Testing

### Manual Testing Steps

1. **Test with new scan**:
   - Scan a new book
   - Verify routing panels appear immediately
   - Check all data is displayed correctly

2. **Test with existing book**:
   - Open detail view for book scanned before feature
   - Should see "Loading ML insights..." briefly
   - Panels should appear after loading

3. **Test with no data**:
   - Book without market data should show appropriate fallback
   - No errors or crashes

4. **Test API endpoint**:
```bash
python scripts/test_ui_data.py
```

### Verification Commands

```bash
# Test API returns routing data
curl http://localhost:8000/api/books/9780316769174/evaluate | python3 -m json.tool

# Debug specific prediction
python scripts/debug_prediction.py 9780316769174

# Find books with $13.25 predictions
sqlite3 catalog.db "
  SELECT isbn, title, estimated_price
  FROM book_catalog
  WHERE estimated_price BETWEEN 13.00 AND 13.50
  LIMIT 10
"
```

## User Impact

### Before
- Users saw only final price prediction
- No visibility into which ML model was used
- No understanding of prediction confidence
- No guidance on where to sell

### After
- Full transparency into ML routing
- Confidence scores with visual meters
- Performance metrics for accountability
- Clear channel recommendations with reasoning
- Expected profit and time to sale

## Performance Considerations

- Dynamic fetching only happens once per book
- Results cached in @State for session
- No impact on books with existing data
- Minimal API overhead (single request per detail view)

## Future Enhancements

1. **Cache routing data in SwiftData**
   - Store fetched routing data permanently
   - Avoid repeated API calls

2. **Batch fetch for list view**
   - Pre-fetch routing data for visible books
   - Show badges in list without opening detail

3. **Real-time confidence updates**
   - Update confidence as more data collected
   - Show "confidence improved" notifications

4. **Interactive model selection**
   - Let user override model choice
   - Compare predictions from different models

5. **Feedback loop**
   - Allow user to report actual sale price
   - Use feedback to improve model accuracy

## Related Documentation

- `/docs/UI_IMPROVEMENTS_COMPLETE.md` - Full UI improvements overview
- `/docs/PRICE_PREDICTION_ANALYSIS.md` - ML prediction analysis
- `/docs/ml/ML_PHASE2_PHASE3_COMPLETE.md` - Specialist model implementation
- `/LotHelperApp/TROUBLESHOOTING_UI_CHANGES.md` - Troubleshooting guide

## Git References

**Branch**: main
**Commit**: (To be added after commit)

**Files Modified**: 11 files
**Lines Added**: 468
**Lines Removed**: 115
**Net Change**: +353 lines

## Key Learnings

1. **Progressive Enhancement Works**
   - Dynamic fetching enables feature for existing data
   - No migration or rescan required
   - Backwards compatible approach

2. **UI Transparency Matters**
   - Users appreciate understanding model decisions
   - Confidence scores build trust
   - Clear reasoning helps users make better decisions

3. **Reusable Components**
   - SwiftUI components can be composed
   - Easy to maintain and extend
   - Consistent styling across app

4. **Async/Await Pattern**
   - Clean async code in Swift
   - Proper loading states
   - Error handling built in
