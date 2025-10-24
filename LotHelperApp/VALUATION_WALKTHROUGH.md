# LotHelper Valuation & Purchase Decision Walkthrough

This document explains the complete valuation and purchase decision process in LotHelper, from scanning a book to receiving a BUY/DON'T BUY recommendation.

---

## 📚 Overview: The Decision Pipeline

```
Scan ISBN → Fetch Data → Calculate Valuations → Analyze Profit → Make Decision
```

---

## 1️⃣ **Data Collection Phase**

When you scan a book's ISBN, the app fetches data from multiple sources:

### **Source 1: Your Backend API** (`lothelper.clevergirl.app`)
- **Endpoint**: `POST /isbn` → `GET /api/books/{isbn}/evaluate`
- **Provides**:
  - Book metadata (title, author, cover, etc.)
  - **Estimated Price** (eBay sold comps median + heuristics)
  - **Probability Score** (0-100, machine learning confidence)
  - **Probability Label** ("Strong confidence", "Worth buying", "Risky", etc.)
  - **Justification** (reasons for the score)
  - **eBay Market Data** (active/sold counts, sell-through rate)
  - **BookScouter results** (buyback offers + Amazon data)
  - **BooksRun offer** (alternative buyback)

### **Source 2: Live eBay Pricing** (via Token Broker)
- **Fetches live active listings** for the ISBN
- **Calculates real-time stats**:
  - Minimum, Median, Maximum prices
  - Number of active listings
  - Last sold date (if available)
- **This data can override backend estimates** (live data is preferred)

### **Source 3: BookScouter API** (via Backend)
- **URL**: `https://api.bookscouter.com/services/v1/book/{isbn}`
- **Provides**:
  - **Buyback offers** from 30+ vendors (Decluttr, TextbookRush, etc.)
  - **Best buyback price** (highest offer)
  - **Amazon marketplace data**:
    - `amazonLowestPrice` - Cheapest Amazon listing
    - `amazonSalesRank` - Sales velocity indicator (lower = faster selling)
    - `amazonCount` - Number of Amazon sellers
    - `amazonTradeInPrice` - Amazon's trade-in value

---

## 2️⃣ **Valuation Calculation Phase**

The app calculates **three independent profit paths**:

### **Path A: eBay Route**

**Step 1: Determine Sale Price**
```swift
// Priority order:
1. Live eBay median (if available and > 0) ← Most accurate
2. Backend estimated price (eBay sold comps + ML adjustments)
```

**Step 2: Calculate eBay Fees**
```swift
// eBay fee structure for books:
Referral Fee: 13.25% of sale price
Transaction Fee: $0.30 flat

Example: $20.00 sale
- Referral Fee: $20.00 × 0.1325 = $2.65
- Transaction Fee: $0.30
- Total Fees: $2.95
- Net Proceeds: $20.00 - $2.95 = $17.05
```

**Step 3: Calculate Profit**
```swift
Net Profit = Net Proceeds - Purchase Price
Example: $17.05 - $5.00 = $12.05 profit
```

**Notes**:
- Assumes buyer pays shipping (standard eBay practice)
- No listing fees (most sellers use free listings)

---

### **Path B: Amazon Route**

**Step 1: Use Amazon Lowest Price**
```swift
// From BookScouter API:
amazonLowestPrice = $25.00  // Current cheapest Amazon listing
```

**Step 2: Calculate Amazon Fees**
```swift
// Amazon fee structure for books (seller-fulfilled):
Referral Fee: 15% of sale price
Closing Fee: $1.80 flat

Example: $25.00 sale
- Referral Fee: $25.00 × 0.15 = $3.75
- Closing Fee: $1.80
- Total Fees: $5.55
- Net Proceeds: $25.00 - $5.55 = $19.45
```

**Step 3: Calculate Profit**
```swift
Net Profit = Net Proceeds - Purchase Price
Example: $19.45 - $5.00 = $14.45 profit
```

**Notes**:
- Assumes seller-fulfilled (you ship it)
- Buyer pays shipping separately
- Amazon fees are typically higher than eBay (~15% vs ~13%)
- But Amazon prices can also be higher, offsetting the fees

---

### **Path C: Buyback Route**

**Step 1: Use Best Buyback Offer**
```swift
// From BookScouter API:
bestPrice = $12.00  // Highest vendor offer
bestVendor = "Decluttr"
```

**Step 2: Calculate Profit (No Fees!)**
```swift
Net Profit = Buyback Offer - Purchase Price
Example: $12.00 - $5.00 = $7.00 profit

// No fees because:
- Vendor pays shipping (you print free label)
- Instant payout (no waiting for sale)
- Guaranteed acceptance (if condition matches)
```

**Notes**:
- **Zero risk** - guaranteed sale
- **Zero effort** - print label, ship, get paid
- **Lower profit** - typically 30-50% less than marketplace sales
- **Instant liquidity** - money in days, not weeks/months

---

## 3️⃣ **Decision Logic Phase**

The app uses a **rule-based decision tree** to determine BUY/DON'T BUY:

### **Priority Order (Checked Top to Bottom)**

#### **RULE 1: Guaranteed Buyback Profit** 🟢 HIGHEST PRIORITY
```swift
IF buybackProfit > $0
THEN → BUY (Guaranteed profit via [vendor])

Example:
- Purchase Price: $3.00
- Best Buyback: $10.00
- Profit: $7.00
→ Decision: "BUY - Guaranteed $7.00 profit via Decluttr"

Why this is #1: ZERO RISK. You can't lose money.
```

---

#### **RULE 2: Strong Profit ($10+)** 🟢
```swift
IF bestProfit ≥ $10.00
THEN → BUY (Net profit $X.XX via [platform])

Example:
- eBay: $12.05 profit
- Amazon: $14.45 profit ← Best
- Buyback: $7.00 profit
→ Decision: "BUY - Net profit $14.45 via Amazon"

Variations:
- IF confidence_score ≥ 60 OR label contains "high"
  THEN → "Strong: $X.XX net via [platform]"
```

**Why $10 threshold?**
- Covers time/effort (listing, shipping, customer service)
- Provides margin for errors (condition issues, returns)
- Ensures meaningful profit after potential price drops

---

#### **RULE 3: Moderate Profit ($5-10)** 🟡 CONDITIONAL
```swift
IF bestProfit ≥ $5.00 AND < $10.00
THEN check additional conditions:

  IF confidence_score ≥ 70 OR label contains "high"
  THEN → BUY (Good confidence + $X.XX via [platform])

  ELSE IF amazonSalesRank < 100,000
  THEN → BUY (Fast-moving + $X.XX via [platform])

  ELSE → DON'T BUY (Only $X.XX profit - needs higher confidence)

Example 1: HIGH CONFIDENCE
- Best Profit: $7.50 (via eBay)
- Confidence Score: 75
- Amazon Rank: 250,000
→ Decision: "BUY - Good confidence + $7.50 via eBay"

Example 2: FAST MOVER
- Best Profit: $6.00 (via Amazon)
- Confidence Score: 55
- Amazon Rank: 45,000 ← Bestseller
→ Decision: "BUY - Fast-moving + $6.00 via Amazon"

Example 3: REJECT
- Best Profit: $7.00 (via eBay)
- Confidence Score: 50
- Amazon Rank: 800,000 ← Slow mover
→ Decision: "DON'T BUY - Only $7.00 profit - needs higher confidence"
```

**Why these conditions?**
- **High confidence** = ML model predicts good sale probability
- **Amazon rank < 100k** = Book sells frequently, reduces time-to-sale risk

---

#### **RULE 4: Small Profit ($1-5)** 🔴 USUALLY REJECT
```swift
IF bestProfit > $0 AND < $5.00
THEN:

  IF confidence_score ≥ 80 AND label contains "high"
  THEN → BUY (Very high confidence offsets low margin)

  ELSE → DON'T BUY (Net profit only $X.XX - too thin)

Example:
- Best Profit: $3.50
- Confidence Score: 85 ← Very high
→ Decision: "BUY - Very high confidence offsets low margin"
```

**Why usually reject?**
- $1-5 profit doesn't justify effort
- Risk of loss from condition issues or returns
- Better to pass and find higher-margin books

---

#### **RULE 5: Loss or Break-Even** 🔴 ALWAYS REJECT
```swift
IF bestProfit ≤ $0
THEN → DON'T BUY (Would lose $X.XX after fees)

Example:
- Purchase Price: $10.00
- Best eBay: $8.00 (after fees: $6.74)
- Profit: -$3.26
→ Decision: "DON'T BUY - Would lose $3.26 after eBay fees"
```

---

#### **RULE 6: No Pricing Data** 🟡 CONFIDENCE ONLY
```swift
IF no_pricing_available
THEN:

  IF confidence_score ≥ 80 AND label contains "high"
  THEN → BUY (Very high confidence but verify pricing)

  ELSE → DON'T BUY (Insufficient profit margin or confidence)
```

**When this happens:**
- ISBN not found on eBay/Amazon
- BookScouter has no data
- Rare or out-of-print book
- New release not yet in market data

---

## 4️⃣ **Supporting Metrics**

### **Confidence Score (0-100)**
Generated by your backend's ML model:
- **80-100**: "Strong confidence" 🟢
- **60-79**: "Worth buying" 🔵
- **40-59**: "Risky" 🟠
- **0-39**: "Don't buy" 🔴

**What it considers:**
- Historical eBay sold data
- Sell-through rate
- Amazon sales rank
- Buyback offer presence/strength
- Rarity (low supply = higher risk)
- Edition/condition factors

### **Amazon Sales Rank Thresholds**
Indicates how fast books sell:
- **< 50k**: Bestseller 🟢 (sells multiple times per day)
- **50k-100k**: High demand 🔵 (sells daily)
- **100k-300k**: Solid demand 🟡 (sells weekly)
- **300k-500k**: Moderate 🟠 (sells monthly)
- **500k-1M**: Average ⚪ (sells occasionally)
- **> 1M**: Slow moving 🔴 (sells rarely)

**Why it matters:**
- Lower rank = faster sale = less storage time
- Fast movers reduce cash-flow risk
- Slow movers tie up capital longer

### **Sell-Through Rate**
```
Sell-Through = (Sold in 30 days) / (Active Listings) × 100%

Examples:
- 50 sold, 100 active = 50% sell-through (good)
- 10 sold, 200 active = 5% sell-through (oversaturated)
```

**What it means:**
- **> 30%**: Strong demand, limited supply (good to buy)
- **10-30%**: Normal market
- **< 10%**: Oversupply, hard to sell (avoid)

---

## 5️⃣ **Real-World Example Walkthrough**

Let's walk through a complete evaluation:

### **Book Scanned:** Harry Potter Prisoner of Azkaban (Hardcover, 1st Edition)
**ISBN:** 9780439136365
**Purchase Price:** $5.00

---

### **Step 1: Data Fetched**

**Backend API:**
- Estimated Price: $22.00 (eBay sold comps median)
- Confidence Score: 78
- Probability Label: "Worth buying"
- Justification: ["Strong eBay sold history", "Good demand indicated by Amazon rank", "Multiple buyback offers"]

**Live eBay:**
- Active Count: 47
- Sold (30d): 23
- Sell-Through: 48.9%
- Median Active: $24.50 ← Use this (live > backend)

**BookScouter:**
- Best Buyback: $9.50 (Decluttr)
- Amazon Lowest: $28.00
- Amazon Rank: 35,420 (Bestseller!)
- Amazon Sellers: 34

---

### **Step 2: Calculate Three Profit Paths**

**A. eBay Route:**
```
Sale Price: $24.50 (live median)
Fees: $24.50 × 0.1325 + $0.30 = $3.55
Net Proceeds: $24.50 - $3.55 = $20.95
Profit: $20.95 - $5.00 = $15.95 ✨
```

**B. Amazon Route:**
```
Sale Price: $28.00 (lowest listing)
Fees: $28.00 × 0.15 + $1.80 = $6.00
Net Proceeds: $28.00 - $6.00 = $22.00
Profit: $22.00 - $5.00 = $17.00 ✨✨ BEST!
```

**C. Buyback Route:**
```
Offer: $9.50 (Decluttr)
Fees: $0.00 (vendor pays shipping)
Net Proceeds: $9.50
Profit: $9.50 - $5.00 = $4.50
```

---

### **Step 3: Decision Logic**

```swift
// Check RULE 1: Guaranteed buyback?
buybackProfit = $4.50 > $0 ✓
→ Could trigger, but let's continue to find best profit

// Check RULE 2: Best profit ≥ $10?
bestProfit = max($15.95, $17.00, $4.50) = $17.00 ✓
→ This triggers!

// Since best profit is $17.00 via Amazon:
platform = "Amazon"
confidence_score = 78 ≥ 60 ✓
→ Use "Strong" variant

DECISION: BUY ✅
REASON: "Strong: $17.00 net via Amazon"
```

---

### **Step 4: UI Display**

The scanner shows:

```
┌────────────────────────────────────┐
│  ✓ BUY                             │
│  Strong: $17.00 net via Amazon     │
├────────────────────────────────────┤
│  🛒 eBay Route: (Live)             │
│  Sale: $24.50                      │
│  Fees: -$3.55                      │
│  Cost: -$5.00                      │
│  Net: $15.95                       │
├────────────────────────────────────┤
│  🛒 Amazon Route: (Lowest Price)   │
│      Rank: #35k                    │
│  Sale: $28.00                      │
│  Fees: -$6.00                      │
│  Cost: -$5.00                      │
│  Net: $17.00 ← Best!               │
├────────────────────────────────────┤
│  🔄 Buyback Route: (Decluttr)      │
│  Offer: $9.50                      │
│  Cost: -$5.00                      │
│  Net: $4.50                        │
└────────────────────────────────────┘

Confidence Score: 78/100 (WORTH BUYING)
Amazon Rank: #35k (Bestseller)
Sell-Through: 48.9% (Strong demand)
```

---

## 6️⃣ **Special Cases & Edge Scenarios**

### **Case 1: Free Books (Purchase Price = $0)**
```
All profits are pure gain!

Example:
- eBay Net: $17.05 → Profit: $17.05
- Amazon Net: $19.45 → Profit: $19.45
- Buyback: $12.00 → Profit: $12.00

→ Almost always BUY (unless condition is terrible)
```

---

### **Case 2: High Fees Erode Margin**
```
Book sells for $10.00 on Amazon:
- Fees: $10.00 × 0.15 + $1.80 = $3.30
- Net: $6.70
- If cost > $6.70 → LOSS

This is why low-price books ($5-15) are risky!
Better to focus on $20+ books.
```

---

### **Case 3: No Market Data (Rare Books)**
```
If no eBay/Amazon/Buyback data:
→ Rely purely on confidence score

IF score ≥ 80 → Cautious BUY
ELSE → DON'T BUY (too risky without data)
```

---

### **Case 4: Conflicting Signals**
```
Scenario:
- High confidence score (85)
- But low profit ($6.00)
- Slow Amazon rank (750,000)

Decision Process:
1. Not guaranteed buyback (skip Rule 1)
2. Not $10+ profit (skip Rule 2)
3. Check Rule 3:
   - Profit $5-10: ✓
   - Confidence ≥ 70: ✓
   - Amazon rank < 100k: ✗
   → Conflict!

4. High confidence wins → BUY
   "Good confidence + $6.00 via eBay"

BUT: Warning displayed about slow rank
```

---

## 7️⃣ **Key Takeaways for Buyers**

### **What Makes a "Good Buy"?**
1. **Profit ≥ $10** (or $5+ with high confidence)
2. **Multiple exit strategies** (eBay + Amazon + Buyback)
3. **Amazon rank < 100k** (fast mover)
4. **Sell-through > 30%** (strong demand)
5. **Buyback floor exists** (downside protection)

### **Red Flags to Avoid:**
1. **Only one exit strategy** (high risk if that channel fails)
2. **Profit < $5** (not worth effort)
3. **Amazon rank > 500k + low confidence** (slow mover + uncertain)
4. **No buyback offers** (no safety net if marketplace doesn't work)
5. **Oversaturated market** (sell-through < 10%)

### **The "Safety Hierarchy":**
```
Buyback > Amazon > eBay
 (Risk)   Low    Med   High

Buyback: Guaranteed, instant, zero effort
Amazon:  Higher prices, but stricter standards
eBay:    Most flexible, but requires customer service
```

---

## 8️⃣ **Behind the Scenes: ML Confidence Score**

Your backend's probability model considers:

### **Positive Signals (+score):**
- Strong eBay sold history (many recent sales)
- Amazon rank < 100k (fast mover)
- Multiple buyback offers (demand indicator)
- High sell-through rate (>30%)
- First edition / special edition
- Good condition (Like New, Very Good)

### **Negative Signals (-score):**
- Rare/obscure (low sales volume = risky)
- Oversaturated market (too many sellers)
- Low buyback offers (< $3)
- Poor condition (Acceptable, Good)
- Ex-library / book club editions
- Outdated textbooks (new editions available)

### **Score Calibration:**
The model is trained to be **conservative**:
- 80+ score → ~85% actual sell rate
- 70-79 score → ~70% actual sell rate
- 60-69 score → ~60% actual sell rate
- <60 score → <50% actual sell rate

This means if it says "Strong confidence", you can **trust it**.

---

## 🎯 **Decision Framework Summary**

```
┌─────────────────────────────────────────────┐
│  1. Scan ISBN                               │
│  2. Fetch market data (3 sources)          │
│  3. Calculate 3 profit paths                │
│  4. Find best profit                        │
│  5. Check decision rules (1→6)              │
│  6. Display recommendation + all options    │
│  7. You decide: Accept, Reject, or Manual   │
└─────────────────────────────────────────────┘

Key Philosophy:
- Transparent: Show ALL calculations
- Conservative: Prefer to pass than lose money
- Flexible: Show all exit strategies
- Data-driven: ML + real market data
- You're in control: Final decision is yours
```

---

## 📊 **Quick Reference: Decision Rules**

| Condition | Profit | Confidence | Rank | Decision |
|-----------|--------|------------|------|----------|
| Buyback > Cost | Any | Any | Any | **BUY** ✅ |
| Best ≥ $10 | $10+ | Any | Any | **BUY** ✅ |
| Best $5-10 | $5-10 | ≥70 | Any | **BUY** ✅ |
| Best $5-10 | $5-10 | Any | <100k | **BUY** ✅ |
| Best $5-10 | $5-10 | <70 | >100k | **REJECT** ❌ |
| Best $1-5 | $1-5 | ≥80 | Any | **BUY** 🟡 |
| Best $1-5 | $1-5 | <80 | Any | **REJECT** ❌ |
| Best ≤ $0 | Loss | Any | Any | **REJECT** ❌ |
| No data | None | ≥80 | Any | **BUY** 🟡 |
| No data | None | <80 | Any | **REJECT** ❌ |

---

**Questions or want to adjust thresholds?** All the logic is in `ScannerReviewView.swift:1175-1249` (makeBuyDecision function).
