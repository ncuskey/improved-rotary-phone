# LotHelper - ISBN Book Scanner & Lot Optimizer

**Smart book scanning app with multi-platform profit analysis, series completion tracking, and AI-powered buy decisions.**

---

## 🎯 **Overview**

LotHelper helps book resellers make instant buy/reject decisions by:
- Analyzing profit across 3 exit strategies (eBay, Amazon, Buyback)
- Tracking series to build complete high-value lots
- Providing retroactive "go back and get it" recommendations
- Using ML confidence scores for risk assessment

---

## ✨ **Key Features**

### **1. Multi-Platform Valuation**
- **eBay**: Live pricing + historical sold data (13.25% + $0.30 fees)
- **Amazon**: Lowest marketplace price (15% + $1.80 fees)
- **Buyback**: Guaranteed instant offers (no fees)
- Shows best profit path automatically

### **2. Series Completion Tracking**
- Detects when scanning books from same series
- Lowers profit thresholds for series building
- Shows previously scanned books with location & time
- Recommends "go back and get" rejected books
- Complete series sell for 2-3x individual book value

### **3. Intelligent Buy Decisions**
- 6-tier decision tree with confidence scoring
- $10+ profit = strong buy
- $5-10 profit = conditional buy (with confidence/velocity)
- $3+ profit for series completion
- Guaranteed buyback = always buy
- Rejects losses and thin margins

### **4. Real-Time Data Integration**
- Backend API for book evaluation
- BookScouter API for buyback offers + Amazon data
- Live eBay pricing via token broker
- Cached results for offline use

### **5. Location-Aware Scanning**
- Tracks where you found each book
- Shows scan history by location
- Acceptance rate per store
- Time-based relevance ("15 min ago", "yesterday")

---

## 📊 **Recent Updates (October 2025)**

### **Amazon Pricing Integration**
- Added Amazon lowest price to profit calculations
- Third exit strategy alongside eBay and Buyback
- Amazon fees: 15% referral + $1.80 closing
- Displays Amazon sales rank for velocity assessment

### **Retroactive Series Detection**
- Checks scan history for previously rejected books
- Shows location & time of previous series scans
- Prompts to "go back and get" books when series is identified
- Both accepted books AND rejected scans trigger series logic

### **Enhanced Profit Display**
- Shows all three profit paths side-by-side
- Color-coded indicators (green = best)
- Fee breakdowns for transparency
- Net profit after all costs

### **Comprehensive Testing**
- 35 test scenarios for buy decision logic
- Amazon fee calculation tests
- Series completion tests
- Edge case handling

---

## 🏗️ **Architecture**

```
┌─────────────────────────────────────────────────────┐
│                   LotHelper App                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐│
│  │  Scanner UI  │  │ Valuation    │  │  Cache   ││
│  │  (SwiftUI)   │→│ Engine       │→│ (SwiftData││
│  └──────────────┘  └──────────────┘  └──────────┘│
│         ↓                  ↓                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐│
│  │  Series      │  │ Buy Decision │  │  History ││
│  │  Detector    │→│ Logic        │  │  Tracking││
│  └──────────────┘  └──────────────┘  └──────────┘│
│                                                     │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│              Backend APIs & Data Sources            │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────────┐  ┌──────────────────────────┐│
│  │ LotHelper API   │  │  BookScouter API         ││
│  │ (Evaluation)    │  │  (Buyback + Amazon)      ││
│  └─────────────────┘  └──────────────────────────┘│
│           ↓                      ↓                  │
│  ┌─────────────────┐  ┌──────────────────────────┐│
│  │ eBay Token      │  │  Scan History DB         ││
│  │ Broker (Live)   │  │  (catalog.db)            ││
│  └─────────────────┘  └──────────────────────────┘│
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 📁 **Project Structure**

```
LotHelperApp/
├── LotHelper/                      # Main app
│   ├── ScannerReviewView.swift    # ⭐ Core scanning interface
│   ├── BookAPI.swift               # Backend API client
│   ├── EbayAPI.swift               # eBay pricing integration
│   ├── CachedBook.swift            # SwiftData models
│   ├── CacheManager.swift          # Database operations
│   ├── ScanHistoryView.swift      # Location-based history
│   └── LotRecommendationsView.swift # Series lot builder
│
├── LotHelperTests/
│   └── ScannerReviewViewTests.swift # ⭐ 35 comprehensive tests
│
├── Documentation/
│   ├── VALUATION_WALKTHROUGH.md    # ⭐ Complete decision logic
│   ├── SERIES_COMPLETION_FEATURE.md # Series tracking guide
│   ├── RETROACTIVE_SERIES_DETECTION.md # "Go back" feature
│   └── ANALYZE_SCANS.md            # Bulk analysis tool
│
└── Tools/
    ├── bulk_analysis.py            # Batch book analyzer
    └── run_analysis.py             # Test scanner with real ISBNs
```

---

## 🔑 **Key Files & Line Numbers**

### **Core Valuation Logic**
- **Fee Calculations**: `ScannerReviewView.swift:1086-1112`
  - eBay: 13.25% + $0.30
  - Amazon: 15% + $1.80

- **Profit Calculation**: `ScannerReviewView.swift:1114-1220`
  - All three exit strategies
  - Returns 7-tuple with breakdowns

- **Buy Decision Tree**: `ScannerReviewView.swift:1272-1354`
  - 6 rules in priority order
  - Series completion bonus (Rule 1.5)
  - Confidence & velocity factors

### **Series Detection**
- **Check Logic**: `ScannerReviewView.swift:1335-1410`
  - Queries CachedBook for accepted books
  - Checks scan history (future: backend API)
  - Returns previous scans with location/time

- **UI Display**: `ScannerReviewView.swift:258-408`
  - Series context card
  - Previous scan list
  - "Go back" prompts

### **Data Models**
- **BookEvaluationRecord**: `BookAPI.swift:214-261`
- **CachedBook**: `CachedBook.swift:11-254`
- **PreviousSeriesScan**: `ScannerReviewView.swift:1325-1333`

### **API Integration**
- **Fetch Evaluation**: `BookAPI.swift:475-520`
- **Scan History**: `BookAPI.swift:706-743`
- **BookScouter Data**: `BookAPI.swift:150-178`

---

## 🧪 **Testing**

### **Run Unit Tests**
```bash
xcodebuild test -scheme LotHelper -destination 'platform=iOS Simulator,name=iPhone 17'
```

### **Test Coverage**
- ✅ ISBN normalization & validation (3 tests)
- ✅ eBay fee calculations (3 tests)
- ✅ Amazon fee calculations (4 tests)
- ✅ Profit calculations (5 tests)
- ✅ Buy decision logic (10 tests)
- ✅ UI helper functions (6 tests)
- ✅ Edge cases (4 tests)
- **Total: 35 tests**

### **Bulk Analysis Tool**
Test with real ISBNs:
```bash
python3 bulk_analysis.py
# Then paste ISBNs one per line
```

Or use the pre-populated analyzer:
```bash
python3 run_analysis.py
# Analyzes 20 books from your database
```

---

## 📈 **Buy Decision Rules**

### **Priority Order**

1. **Buyback > Cost** → Always BUY (guaranteed profit)
2. **Profit ≥ $10** → BUY (worth effort)
3. **Series Completion** → BUY if profit ≥ $3 (strategic value)
4. **Profit $5-10** → Conditional (needs confidence ≥70 OR rank <100k)
5. **Profit $1-5** → Usually REJECT (unless confidence ≥80)
6. **Loss** → Always REJECT

### **Series Bonuses**

| Books in Series | Normal Threshold | Series Threshold |
|----------------|------------------|------------------|
| 1-2 books | $5+ profit | **$3+ profit** |
| 3+ books | $5+ profit | **$1+ profit** |
| 3+ books (high confidence) | No losses | **Accept up to -$2** |

---

## 🔄 **Data Flow**

### **Scanning a Book**

```
1. User scans ISBN
   ↓
2. Fetch book evaluation (Backend API)
   → Metadata (title, author, series)
   → Estimated price (eBay comps)
   → Confidence score (ML model)
   → BookScouter data (buyback + Amazon)
   ↓
3. Fetch live eBay pricing (Token Broker)
   ↓
4. Check series completion (Local DB + History)
   ↓
5. Calculate 3 profit paths
   → eBay: price - 13.25% - $0.30 - cost
   → Amazon: price - 15% - $1.80 - cost
   → Buyback: offer - cost
   ↓
6. Apply decision rules
   → Check buyback profit
   → Check series context
   → Check profit thresholds
   → Check confidence/velocity
   ↓
7. Display recommendation
   → BUY/DON'T BUY + reason
   → All 3 profit paths
   → Series context (if applicable)
   ↓
8. User accepts/rejects
   ↓
9. Save to database
   → CachedBook (if accepted)
   → Scan history (always)
```

---

## 🌐 **API Endpoints**

### **Backend API** (`lothelper.clevergirl.app`)

```
POST /isbn
→ Submit ISBN for processing
→ Returns: Job ID

GET /api/books/{isbn}/evaluate
→ Get full book evaluation
→ Returns: BookEvaluationRecord with all data

GET /api/books/scan-history?limit=100
→ Get scan history
→ Query params: isbn, location_name, decision
→ Returns: Array of ScanHistoryRecord

GET /api/books/scan-locations
→ Get location summaries
→ Returns: Array of ScanLocationSummary

GET /api/books/scan-stats
→ Get aggregate statistics
→ Returns: ScanStatistics
```

### **BookScouter API**

```
GET https://api.bookscouter.com/services/v1/book/{isbn}
→ Query param: apiKey
→ Returns: Buyback offers + Amazon data
   - bestPrice (highest buyback)
   - amazonLowestPrice
   - amazonSalesRank
   - offers[] (all vendors)
```

---

## 📊 **Real-World Performance**

### **Test Case: 20 Recent Scans**

**Without Series Logic:**
- 4 BUY recommendations (20%)
- Total profit: $123.71
- Average per book: $30.93

**With Series Logic:**
- 7 BUY recommendations (35%)
- Total profit: $216.50
- Average per book: $30.93
- **+75% more profit** from series building

### **Series Opportunity Example**

Michael Connelly books scanned:
- 6 books from 2 series (Bosch, Lincoln Lawyer)
- Without series: 1 accepted
- With series: 4-5 accepted
- **5x better outcome**

---

## 🛠️ **Development Setup**

### **Requirements**
- Xcode 15+
- iOS 17+
- Swift 5.9+
- SwiftData
- Python 3.8+ (for tools)

### **Installation**
```bash
# Clone repo
cd ~/ISBN/LotHelperApp

# Open in Xcode
open LotHelper.xcodeproj

# Build & run
⌘R
```

### **Environment**
- Simulator: iPhone 17
- Database: `~/.isbn_lot_optimizer/catalog.db`
- SwiftData: `~/Library/Developer/CoreSimulator/.../default.store`

---

## 📚 **Documentation**

### **User Guides**
- **[Valuation Walkthrough](VALUATION_WALKTHROUGH.md)** - Complete explanation of how decisions are made
- **[Series Completion Feature](SERIES_COMPLETION_FEATURE.md)** - Building profitable lots
- **[Retroactive Series Detection](RETROACTIVE_SERIES_DETECTION.md)** - "Go back and get it" feature

### **Analysis Tools**
- **[Analyze Scans Guide](ANALYZE_SCANS.md)** - How to batch analyze books
- **`bulk_analysis.py`** - Python script for testing
- **`run_analysis.py`** - Pre-populated test with 20 books

---

## 🎯 **Roadmap**

### **Phase 1: Complete** ✅
- Multi-platform profit calculation
- Series detection from local database
- Retroactive series recommendations
- Comprehensive testing

### **Phase 2: In Progress** 🚧
- Backend API for scan history lookup
- Cross-device series synchronization
- Enhanced location tracking

### **Phase 3: Planned** 📋
- Series progress tracking with visual indicators
- Smart alerts ("You're building Reacher series!")
- Series lot builder automation
- ROI analytics per series

### **Phase 4: Future** 🔮
- Smart routing ("These books at nearby store")
- Series completion probability
- Crowdsourced series data
- Auto-buy rules per series

---

## 🤝 **Contributing**

### **Code Style**
- SwiftUI for all UI
- SwiftData for persistence
- Async/await for networking
- Tests for all business logic

### **Testing**
- Add tests for new decision rules
- Test edge cases (no data, losses, etc.)
- Verify series detection logic

### **Documentation**
- Update line numbers in this README
- Add examples to walkthrough docs
- Document new API endpoints

---

## 📝 **License**

Copyright © 2025 Nick Cuskey. All rights reserved.

---

## 📞 **Support**

- Issues: Create GitHub issue
- Questions: Check documentation first
- Feature requests: Describe use case + expected behavior

---

## 🏆 **Key Achievements**

✅ **35 comprehensive tests** covering all decision logic
✅ **3 exit strategies** analyzed simultaneously
✅ **Series completion** with retroactive detection
✅ **Location tracking** for "go back" prompts
✅ **Real-time pricing** from eBay + BookScouter
✅ **ML confidence scores** for risk assessment
✅ **75% profit increase** with series logic

---

**Built with ❤️ for book resellers who want to maximize profit through strategic lot building.**
