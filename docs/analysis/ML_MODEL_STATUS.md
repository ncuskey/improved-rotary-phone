# ML Model Status - November 2, 2025

## Current Production Model: Unified GradientBoostingRegressor

**Performance:**
- Test MAE: **$3.59**
- Test RMSE: $4.78
- Test R²: 0.016
- Training samples: 5,506 books

**Features:** 93 total features including:
- AbeBooks pricing (7 features)
- AbeBooks platform scaling (3 features)
- **BookFinder aggregator (13 NEW features)** ✨
  - Price signals: lowest, avg, volatility, source count
  - Collectibility: signed counts, first edition counts
  - Quality: description length, detailed percentage
- Amazon ranking (2 features)
- eBay market signals (4 features)
- Book attributes (page count, age, ratings, etc.)
- Condition & physical characteristics

**Top Features by Importance:**
1. abebooks_competitive_estimate (17.5%)
2. page_count (9.8%)
3. log_amazon_rank (9.3%)
4. age_years (7.9%)
5. log_ratings (6.1%)

**BookFinder Feature Status:**
- Currently **low importance** (<1.5% each) due to sparse coverage
- Only ~300 of 6,261 samples have BookFinder data (~5%)
- Expected to become **much more important** as scraping completes

## Stacking Ensemble - Attempted, Not Production Ready

**Why Not Used:**
- Test MAE: $5.26 (46% worse than unified)
- Individual specialist models are overfitting (many negative test R²)
- Combining poor predictions yields poor ensemble

**Models Trained:**
- eBay specialist (756 samples) - MAE $3.86
- AbeBooks specialist (748 samples) - MAE $0.28 ✓
- Amazon specialist (6,629 samples) - MAE $17.27
- Biblio specialist (131 samples) - MAE $2.76
- Alibris specialist (133 samples) - MAE $4.19
- Zvab specialist (108 samples) - MAE $2.31

**Meta-model coefficients:** Ridge regression with 6 features
- Shows interesting patterns (negative weights for diversification)
- But overall performance worse than unified

## Future Roadmap

### Short-term (After BookFinder scrape completes ~1,000 ISBNs)
1. **Retrain unified model** - BookFinder features should gain importance
2. **Expected improvement**: MAE < $3.00 with rich BookFinder data

### Medium-term (Research & experimentation)
1. **Fix stacking overfitting**:
   - Add regularization to specialist models
   - Increase cross-validation folds
   - Use ElasticNet or Lasso for meta-model
   - Try blending instead of stacking
2. **Regional Amazon models** - Separate models for US/UK/DE/etc markets
3. **Feature engineering**:
   - Interaction terms (signed × first_edition)
   - Temporal features (days since publication)
   - Seller reputation metrics from BookFinder

### Long-term (Advanced techniques)
1. **Neural network ensemble** - Deep learning for complex patterns
2. **Uncertainty quantification** - Confidence intervals for predictions
3. **Active learning** - Intelligently select books for manual pricing
4. **Real-time model updates** - Incremental learning as new data arrives

## Monitoring Recommendations

1. **Track MAE over time** as BookFinder data accumulates
2. **Monitor feature importance shifts** when BookFinder coverage increases
3. **A/B test** unified vs stacking when specialist models improve
4. **Retrain quarterly** as market conditions change

## Data Collection Progress

- BookFinder scraping: **300+ ISBNs** with 28,861+ offers
- Target: 19,000 ISBNs from metadata cache
- ETA: ~79 hours for full collection
- Monitoring: Active with iMessage alerts

