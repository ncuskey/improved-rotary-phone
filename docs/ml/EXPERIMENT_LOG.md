# ML Experiment Log

**Purpose:** Track all machine learning experiments, successes, and failures to inform future modeling decisions.

**Guidelines:**
- All experiments logged regardless of outcome
- Failed experiments are learning opportunities
- Include metrics, hypothesis, and conclusions
- Reference detailed reports for complex experiments

---

## Experiment Index

| Date | Experiment | Status | Test MAE Delta | Key Finding |
|------|------------|--------|----------------|-------------|
| 2025-11-09 | Text Embeddings (Hybrid Model) | ❌ FAILED | -29.3% | Tabular features dominate; text adds noise |
| 2025-11-09 | Temporal Sample Weighting | ✅ SUCCESS | +5-8% | Recent data more predictive than stale data |
| 2025-11-01 | Amazon FBM Integration | ✅ SUCCESS | +45% | FBM sellers > Amazon official pricing |
| 2025-10-28 | Signed Book Premium | ✅ SUCCESS | +12% | Signed flag improves collectible pricing |
| 2025-10-15 | Stacking Ensemble Architecture | ✅ SUCCESS | N/A | Platform specialists outperform unified model |

---

## Detailed Experiments

### 1. Text Embeddings (Hybrid Model) - FAILED

**Date:** November 9, 2025
**Hypothesis:** Adding text embeddings from book descriptions will improve eBay price prediction, especially for collectibles.

**Design:**
- **Baseline:** 24 tabular features (existing eBay specialist)
- **Hybrid:** 24 tabular + 384 text embedding features (all-MiniLM-L6-v2)
- **Data:** 11,134 eBay sold books (84.7% with descriptions)
- **Temporal weighting:** 365-day half-life on both models

**Results:**

| Metric | Baseline | Hybrid | Delta |
|--------|----------|--------|-------|
| Test MAE | $1.77 | $2.29 | **-29.3%** |
| Test R² | 0.926 | 0.917 | -1.0% |
| Features | 24 | 408 | +1600% |

**Conclusion:**
- Text embeddings **degraded** performance by 29.3% MAE
- Hybrid model overfits (train R² = 0.987, test R² = 0.917)
- Baseline tabular features already capture price signal
- Descriptions contain generic publisher text, not price-relevant info

**Recommendation:**
- ✅ Keep baseline 24-feature model in production
- ❌ Disable text embeddings for eBay pipeline
- 🔬 Revisit only if new structured appraisal data becomes available

**Full Report:** [TEXT_EMBEDDINGS_EXPERIMENT.md](TEXT_EMBEDDINGS_EXPERIMENT.md)

---

### 2. Temporal Sample Weighting - SUCCESS

**Date:** November 9, 2025
**Hypothesis:** Recent training data is more predictive than old data due to market dynamics.

**Design:**
- Exponential decay with 365-day half-life
- Applied to: eBay, AbeBooks, Amazon, Lot models
- Weight formula: `weight = 2^(-days_ago / 365)`

**Results:**

| Model | Before (MAE) | After (MAE) | Improvement |
|-------|-------------|-------------|-------------|
| Amazon | $0.23 | $0.18 | **+21.7%** |
| Lot | $1.28 | $1.13 | **+11.7%** |
| eBay | $1.89 | $1.77 | **+6.3%** |
| AbeBooks | $0.31 | $0.29 | **+6.5%** |

**Conclusion:**
- Temporal weighting significantly improves generalization
- Market prices drift over time; recent data more relevant
- Especially effective for fast-moving markets (Amazon, Lot)

**Recommendation:**
- ✅ Enable temporal weighting for all platform specialists
- ✅ Use 365-day half-life as standard
- 🔧 Consider platform-specific decay rates in future

**Full Report:** [ML_AUDIT_SUMMARY_2025_11_09.md](ML_AUDIT_SUMMARY_2025_11_09.md)

---

### 3. Amazon FBM Integration - SUCCESS

**Date:** November 1, 2025
**Hypothesis:** Third-party FBM sellers provide better pricing signal than Amazon's official prices.

**Design:**
- Added Amazon FBM data to specialist model
- Features: `fbm_lowest_price`, `fbm_count`
- Compared to baseline using Amazon rank + lowest price

**Results:**
- Test MAE: $0.41 → $0.18 (**+56% improvement**)
- Test R²: 0.989 → 0.996
- Feature importance: `fbm_lowest_price` = 99.6%

**Conclusion:**
- FBM sellers create market equilibrium pricing
- Amazon's official prices less predictive than competitive marketplace
- Traditional features (rank, count) have near-zero importance

**Recommendation:**
- ✅ FBM data now primary signal for Amazon specialist
- ✅ Continue collecting FBM data for all ISBNs
- 📊 Monitor FBM coverage (currently ~70% of training set)

**Full Report:** [ML_SYSTEM_COMPREHENSIVE_REPORT.md](ML_SYSTEM_COMPREHENSIVE_REPORT.md)

---

### 4. Signed Book Premium - SUCCESS

**Date:** October 28, 2025
**Hypothesis:** Signed books command premium pricing; model should learn this signal.

**Design:**
- Added `signed` boolean feature to all specialists
- Trained on 126 signed books from eBay sold comps
- Tested delta predictions: unsigned → signed

**Results:**
- Average premium: $12.50 per signed book
- Feature importance: 3.2% (significant for binary feature)
- API now returns `deltas[]` array showing signed premium

**Conclusion:**
- Model successfully learns signed book premium
- Premium varies by author/genre (range: $5-$50)
- Improves collectible segment accuracy

**Recommendation:**
- ✅ Keep `signed` feature in all models
- ✅ Collect more signed book training data
- 🔧 Consider author-specific signed premiums

**Full Report:** [ML_PHASE4_BOOK_ATTRIBUTES.md](ML_PHASE4_BOOK_ATTRIBUTES.md)

---

### 5. Stacking Ensemble Architecture - SUCCESS

**Date:** October 15, 2025
**Hypothesis:** Platform-specific specialists will outperform single unified model.

**Design:**
- 7 specialist models: eBay, AbeBooks, Amazon, Lot, Biblio, Alibris, Zvab
- Each specialist trained on platform-specific features
- Meta-model combines specialist predictions (Ridge regression)

**Results:**

| Specialist | Features | Test MAE | Test R² | Status |
|------------|----------|----------|---------|--------|
| Amazon | 27 | $0.18 | 0.996 | ✅ Prod |
| AbeBooks | 28 | $0.29 | 0.873 | ✅ Prod |
| Lot | 15 | $1.13 | 0.980 | ✅ Prod |
| eBay | 24 | $1.77 | 0.926 | ✅ Prod |

**Conclusion:**
- Specialist models capture platform-specific pricing dynamics
- Each platform has unique features (e.g., Amazon FBM, eBay sold comps)
- Significantly outperforms unified model approach

**Recommendation:**
- ✅ Maintain specialist architecture as production standard
- ✅ Train meta-model when all specialists mature
- 🔧 Add Biblio/Alibris/Zvab specialists when data sufficient

**Full Report:** [../../docs/analysis/STACKING_ENSEMBLE_REPORT.md](../../docs/analysis/STACKING_ENSEMBLE_REPORT.md)

---

## Lessons Learned

### Principles from Failed Experiments

1. **Parsimony Beats Complexity**
   - More features ≠ better performance
   - Simple models with strong features generalize better
   - Example: 24 features outperform 408 features

2. **Domain Knowledge Matters**
   - Text embeddings work for sentiment, not commodity pricing
   - Understand what drives target variable before adding features
   - eBay pricing = market data > subjective text

3. **Baselines Are Essential**
   - Always compare to simple, interpretable baseline
   - Clear metrics make experiment conclusions indisputable
   - Controlled experiments prevent false positives

4. **Overfitting Is Real**
   - High train R², low test R² = overfitting
   - Regularization can't fix fundamentally noisy features
   - Remove features if they don't improve test performance

### Principles from Successful Experiments

1. **Temporal Dynamics Matter**
   - Market prices drift over time
   - Weight recent data more heavily
   - 365-day half-life works well for book resale

2. **Platform-Specific Features Win**
   - Each marketplace has unique pricing dynamics
   - Amazon FBM ≠ AbeBooks comps ≠ eBay sold listings
   - Specialist models capture these differences

3. **Controlled Feature Addition**
   - Add one feature category at a time
   - Measure delta impact on test set
   - Only keep features that improve generalization

4. **Data Quality > Data Quantity**
   - 84.7% description coverage wasn't enough
   - Text quality matters more than availability
   - Structured data (FBM prices) > unstructured (descriptions)

---

## Future Experiment Ideas

### High Priority

1. **Author-Specific Signed Premiums**
   - Hypothesis: Signed premium varies by author popularity
   - Design: Add author × signed interaction features
   - Expected: Better collectible pricing for rare authors

2. **Platform-Specific Decay Rates**
   - Hypothesis: Fast markets need faster decay (Amazon > eBay)
   - Design: Tune half-life per platform (180d / 365d / 730d)
   - Expected: 2-5% MAE improvement on volatile platforms

3. **Condition Embeddings**
   - Hypothesis: "Very Good" means different things per platform
   - Design: Learn condition embeddings from price distributions
   - Expected: Better cross-platform condition calibration

### Medium Priority

4. **Multi-Task Learning (Price + Sell-Through)**
   - Hypothesis: Joint prediction improves both targets
   - Design: Shared encoder, dual prediction heads
   - Expected: Better generalization via auxiliary task
   - Blocker: Need sell-through data (currently 0% coverage)

5. **Series Completion Premium**
   - Hypothesis: Complete series worth > sum of parts
   - Design: Add `completion_percentage` interaction features
   - Expected: Better lot pricing for near-complete series

### Low Priority (Blocked)

6. **Deep Learning (Transformer)**
   - Hypothesis: Attention mechanism captures book-author relationships
   - Design: Transformer encoder over (title, author, publisher)
   - Blocker: Need 10x more training data (~100k samples)

7. **Market Regime Detection**
   - Hypothesis: Pricing shifts during market events (COVID, inflation)
   - Design: Hidden Markov Model over temporal price distributions
   - Blocker: Need longer time series (3+ years)

---

## Experiment Workflow

### 1. Hypothesis Formation

- What are we testing?
- Why do we believe it will improve performance?
- What domain knowledge supports this?

### 2. Experimental Design

- Baseline: Current production model
- Treatment: Modified model with new feature/architecture
- Controlled variables: Same train/test split, hyperparameters, seed

### 3. Metric Selection

- Primary: Test MAE (mean absolute error in dollars)
- Secondary: Test R² (generalization quality)
- Diagnostic: Train/test gap (overfitting detection)

### 4. Implementation

- Create experiment script in `/scripts/experiments/`
- Log all hyperparameters and data versions
- Save artifacts: models, predictions, feature importance

### 5. Analysis

- Compare baseline vs treatment metrics
- Check for overfitting (train/test gap)
- Analyze feature importance if applicable
- Document unexpected findings

### 6. Decision

- **Success:** Deploy to production, update models
- **Failure:** Document why, preserve code for future
- **Unclear:** Run additional ablation studies

### 7. Documentation

- Update this log with results
- Create detailed report for complex experiments
- Share findings with team

---

## References

- **ML System Overview:** [ML_SYSTEM_COMPREHENSIVE_REPORT.md](ML_SYSTEM_COMPREHENSIVE_REPORT.md)
- **Training Scripts:** `/scripts/stacking/train_*.py`
- **Model Artifacts:** `/isbn_lot_optimizer/models/stacking/`
- **Experiment Scripts:** `/scripts/experiments/` (archived)

---

**Last Updated:** November 9, 2025
**Next Experiment:** TBD based on production performance monitoring
**Maintained By:** ML Team
