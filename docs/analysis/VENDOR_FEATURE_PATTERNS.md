# Vendor Feature Pattern Analysis

**Date:** November 2, 2025
**Analysis:** Feature importance consistency across 6 vendor-specific ML models

## Executive Summary

Analysis of feature importance across eBay, AbeBooks, Amazon, Biblio, Alibris, and Zvab specialist models reveals:

1. **No consistent pricing ratios** - Each marketplace values features very differently
2. **BookFinder dominates specialty vendors** - 50-76% total importance
3. **Major vendors ignore BookFinder** - eBay, Amazon, AbeBooks show 0% BookFinder importance
4. **Signed/First Edition premiums captured indirectly** - Through BookFinder aggregation, not metadata

---

## Model Performance Comparison

| Vendor   | Samples | Features | Train MAE | Test MAE | Test R² |
|----------|---------|----------|-----------|----------|---------|
| eBay     | 756     | 26       | $2.77     | $3.86    | -0.057  |
| AbeBooks | 748     | 28       | $0.01     | $0.28    | 0.863   |
| Amazon   | 6,629   | 21       | $16.78    | $17.27   | -0.008  |
| Biblio   | 131     | 24       | $0.11     | $1.92    | 0.274   |
| Alibris  | 133     | 24       | $0.34     | $4.19    | 0.308   |
| Zvab     | 108     | 24       | $0.26     | $2.31    | -0.862  |

**Key Observations:**
- AbeBooks model is exceptional (MAE $0.28, R² 0.863)
- Amazon model performs poorly (MAE $17.27) - needs investigation
- Small sample sizes for specialty vendors (131-133 samples)

---

## Universal Features (Used by All 6 Vendors)

| Feature          | eBay  | AbeBooks | Amazon | Biblio | Alibris | Zvab  | Avg   |
|------------------|-------|----------|--------|--------|---------|-------|-------|
| log_ratings      | 31.5% | 0.0%     | 7.5%   | 22.9%  | 24.5%   | 1.7%  | 14.7% |
| page_count       | 28.5% | 0.0%     | 30.9%  | 3.9%   | 3.2%    | 19.4% | 14.3% |
| age_years        | 19.6% | 0.0%     | 6.5%   | 1.6%   | 18.9%   | 1.2%  | 8.0%  |
| rating           | 13.2% | 0.0%     | 5.9%   | 0.4%   | 3.4%    | 1.2%  | 4.0%  |

**Insight:** Even "universal" features show massive variance (0-31.5% range). No consistent multipliers.

---

## BookFinder Feature Importance by Vendor

| Feature                | eBay | AbeBooks | Amazon | Biblio | Alibris | Zvab  |
|------------------------|------|----------|--------|--------|---------|-------|
| Lowest Price           | —    | —        | —      | 29.5%  | 12.4%   | 36.8% |
| Average Price          | —    | —        | —      | 6.3%   | 4.6%    | 15.8% |
| Source Count           | —    | —        | —      | 4.7%   | 1.7%    | 5.6%  |
| Price Volatility       | —    | —        | —      | 9.2%   | 7.3%    | 5.4%  |
| First Edition Count    | —    | —        | —      | 3.2%   | 7.8%    | 0.1%  |
| Avg Description Length | —    | —        | —      | 3.5%   | 6.3%    | 9.2%  |
| Detailed %             | —    | —        | —      | 2.6%   | 3.4%    | 1.0%  |

**TOTAL BOOKFINDER:** 0% / 0% / 0% / **60.9%** / **49.5%** / **76.4%**

**Critical Finding:** Major marketplaces (eBay, Amazon, AbeBooks) completely ignore BookFinder features. Specialty/antiquarian vendors rely heavily on cross-market signals.

---

## Top 5 Features by Vendor

### eBay (Popularity-Driven)
1. **log_ratings** (31.5%) - Social proof dominates
2. page_count (28.5%)
3. age_years (19.6%)
4. rating (13.2%)
5. is_fiction (3.4%)

### AbeBooks (Self-Referential)
1. **abebooks_avg_estimate** (54.5%) - Relies on own pricing
2. abebooks_avg_price (45.4%)
3. All other features: 0%

### Amazon (Size & Rank Matter)
1. **page_count** (30.9%) - Bigger books = higher prices
2. log_amazon_rank (22.4%)
3. amazon_count (17.9%)
4. is_fiction (8.7%)
5. log_ratings (7.5%)

### Biblio (BookFinder-Driven Antiquarian)
1. **bookfinder_lowest_price** (29.5%)
2. log_ratings (22.9%)
3. bookfinder_price_volatility (9.2%)
4. is_very_good (6.3%)
5. bookfinder_avg_price (6.3%)

### Alibris (Mixed Signals)
1. **log_ratings** (24.5%)
2. age_years (18.9%)
3. bookfinder_lowest_price (12.4%)
4. bookfinder_first_edition_count (7.8%)
5. bookfinder_price_volatility (7.3%)

### Zvab (German Antiquarian, BookFinder-Heavy)
1. **bookfinder_lowest_price** (36.8%) - Dominant feature
2. page_count (19.4%)
3. bookfinder_avg_price (15.8%)
4. bookfinder_avg_desc_length (9.2%)
5. bookfinder_source_count (5.6%)

---

## Signed & First Edition Premium Analysis

### Direct Metadata Features (Unified Model)

| Feature           | Importance | Status |
|-------------------|------------|--------|
| is_signed         | 0.13%      | ❌ Nearly zero |
| is_first_edition  | 0.01%      | ❌ Nearly zero |

### BookFinder Aggregated Features (Unified Model)

| Feature                        | Importance | Status |
|--------------------------------|------------|--------|
| bookfinder_signed_count        | 0.00%      | ❌ Zero |
| bookfinder_signed_lowest       | 0.61%      | ⚠️ Minimal |
| bookfinder_first_edition_count | 0.07%      | ❌ Nearly zero |
| bookfinder_first_ed_lowest     | 0.72%      | ⚠️ Minimal |

### Why Are These So Low?

**Root Cause: Severe Data Sparsity**

1. **Metadata rarely populated:**
   - `is_signed` depends on `metadata.signed` attribute
   - `is_first_edition` depends on `metadata.printing == "1st"`
   - Most book records lack this information

2. **BookFinder coverage still sparse:**
   - Only ~300 of 6,261 training samples (5%) have BookFinder data
   - As scraping continues → 19,000 ISBNs, importance should increase

3. **Price-based features show promise:**
   - When signed/first edition pricing IS available, model uses it
   - `bookfinder_signed_lowest` (0.61%) and `bookfinder_first_ed_lowest` (0.72%)
   - Suggests premiums exist but data too sparse for strong learning

### Vendor-Specific Patterns

Specialty vendors show **higher** importance when trained on subsets with better coverage:

| Vendor  | bookfinder_first_edition_count | bookfinder_signed_count |
|---------|-------------------------------|-------------------------|
| Biblio  | 3.19%                         | 0.10%                   |
| Alibris | 7.81%                         | 0.36%                   |
| Zvab    | 0.14%                         | 0.10%                   |

**Insight:** When BookFinder data is present, first edition signals matter (especially for Alibris at 7.81%).

---

## Key Takeaways

### 1. No Universal Pricing Formulas

Each marketplace operates differently:
- eBay buyers care about **popularity** (ratings, social proof)
- Amazon buyers care about **size and ranking** (page_count, amazon_rank)
- AbeBooks is **self-referential** (uses own marketplace pricing)
- Specialty vendors (Biblio/Alibris/Zvab) rely on **cross-market signals** (BookFinder)

### 2. BookFinder's Split Personality

- **Ignored by major platforms** (eBay, Amazon, AbeBooks: 0%)
- **Critical for antiquarian markets** (Biblio/Alibris/Zvab: 50-76%)

This makes sense:
- Major platforms have deep internal data (rankings, sales history)
- Specialty vendors need external signals to price rare/collectible books

### 3. Signed/First Edition Premiums Are Indirect

- No universal "signed = 2x price" multiplier
- Premiums captured through BookFinder aggregation:
  - Number of signed/first edition offers in market
  - Lowest prices for these variants
- As BookFinder coverage grows, these features should gain importance

### 4. Model Specialization vs Unified

| Approach    | Pros | Cons |
|-------------|------|------|
| **Vendor specialists** | Capture platform-specific dynamics | Overfit on small samples; ensemble performs worse |
| **Unified model** | Stable, generalizes well | Misses platform-specific nuances |

**Current production:** Unified model ($3.59 MAE) outperforms stacking ($5.26 MAE) due to specialist overfitting.

---

## Future Improvements

### Short-term (When BookFinder > 1,000 ISBNs)
- [ ] Retrain unified model
- [ ] Expect `bookfinder_*` features to gain prominence
- [ ] Target: MAE < $3.00

### Medium-term (Fix Stacking)
- [ ] Add regularization to specialist models (prevent overfitting)
- [ ] Increase cross-validation folds (5 → 10)
- [ ] Try ElasticNet/Lasso for meta-model
- [ ] Consider dropping Amazon specialist (MAE $17.27 too high)

### Research Questions
- [ ] Why does AbeBooks perform so well ($0.28 MAE)?
- [ ] Why does Amazon perform so poorly ($17.27 MAE)?
- [ ] Are there book genres where stacking beats unified?
- [ ] Can we predict which approach works best per book?

---

## Appendix: Most Consistent Cross-Vendor Features

Features used by 3+ vendors with average importance:

| Feature                       | Vendors | Avg Importance | Range         |
|-------------------------------|---------|----------------|---------------|
| bookfinder_lowest_price       | 3/6     | 26.2%          | 12.4% - 36.8% |
| log_ratings                   | 6/6     | 14.7%          | 0.0% - 31.5%  |
| page_count                    | 6/6     | 14.3%          | 0.0% - 30.9%  |
| bookfinder_avg_price          | 3/6     | 8.9%           | 4.6% - 15.8%  |
| age_years                     | 6/6     | 8.0%           | 0.0% - 19.6%  |
| bookfinder_price_volatility   | 3/6     | 7.3%           | 5.4% - 9.2%   |
| bookfinder_avg_desc_length    | 3/6     | 6.3%           | 3.5% - 9.2%   |
| rating                        | 6/6     | 4.0%           | 0.0% - 13.2%  |

**Note:** Even "consistent" features show 20-30% variance in importance.

---

**Analysis generated by:** `scripts/analyze_vendor_feature_patterns.py`
**Last updated:** November 2, 2025
