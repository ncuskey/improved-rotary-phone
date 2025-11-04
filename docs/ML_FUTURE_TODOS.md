# ML Model Future Improvements

## Immediate Next Steps (When BookFinder Scrape Reaches ~1,000 ISBNs)

- [ ] **Retrain unified model** with richer BookFinder coverage
- [ ] **Analyze feature importance changes** - BookFinder features should gain prominence
- [ ] **Document MAE improvement trajectory** as data accumulates
- [ ] **Target**: Push MAE below $3.00

## Stacking Ensemble Revival (Medium Priority)

### Problem to Solve
Current stacking performs 46% worse than unified model due to specialist overfitting.

### Fixes to Try

#### 1. Regularization Improvements
- [ ] Add stronger regularization to specialist models
- [ ] Tune `min_samples_leaf` and `min_samples_split` hyperparameters
- [ ] Try `max_features` to reduce overfitting
- [ ] Experiment with `subsample < 0.8` for more aggressive regularization

#### 2. Cross-Validation Tuning
- [ ] Increase folds from 5 to 10 for more robust OOF predictions
- [ ] Try stratified K-fold on price bins
- [ ] Implement nested CV for hyperparameter tuning

#### 3. Meta-Model Alternatives
- [ ] Try ElasticNet (L1+L2) instead of Ridge (L2 only)
- [ ] Experiment with Lasso for automatic feature selection
- [ ] Test simple averaging/blending as baseline
- [ ] Try XGBoost for meta-model (may capture non-linear relationships)

#### 4. Feature Engineering for Stacking
- [ ] Add prediction confidence scores from each specialist
- [ ] Include feature availability flags (which platforms have data)
- [ ] Add variance/disagreement between specialist predictions
- [ ] Create interaction terms between predictions

#### 5. Data Quality
- [ ] Filter out specialists with MAE > $5
- [ ] Weight specialists by their cross-validation performance
- [ ] Consider dropping Amazon specialist (MAE $17.27 is too high)

## Regional Amazon Models

### Motivation
Amazon has data from 10+ countries with different currencies and market dynamics.

### Implementation
- [ ] Group Amazon data by country (US, UK, DE, FR, etc.)
- [ ] Train separate models for high-volume countries (US, UK, DE)
- [ ] Analyze price differences across regions
- [ ] Add currency conversion features
- [ ] Consider regional purchasing power adjustments

## Advanced Feature Engineering

### BookFinder Feature Interactions
- [ ] `signed × first_edition` - Premium for signed first editions
- [ ] `price_volatility × source_count` - Market uncertainty with competition
- [ ] `oldworld_count / total_offers` - Antiquarian market ratio

### Temporal Features
- [ ] Days since publication
- [ ] Days since last sale (if available)
- [ ] Seasonality indicators (holidays, back-to-school)
- [ ] Publication year bins (vintage, classic, contemporary)

### Seller/Market Quality
- [ ] Avg description length per vendor (quality proxy)
- [ ] Vendor diversity (Shannon entropy of source_count)
- [ ] Price spread as % of average (market efficiency)

## Neural Network Experimentation

### Architecture Ideas
- [ ] Separate embeddings for categorical features (condition, binding, vendor)
- [ ] Multi-input architecture (metadata branch + pricing branch)
- [ ] Attention mechanism to weigh different price sources
- [ ] Ensemble of neural networks with different architectures

### Frameworks to Try
- [ ] TensorFlow/Keras for rapid prototyping
- [ ] PyTorch for custom architectures
- [ ] LightGBM + neural network hybrid

## Uncertainty Quantification

### Techniques
- [ ] Quantile regression (predict 10th, 50th, 90th percentiles)
- [ ] Prediction intervals via bootstrapping
- [ ] Conformal prediction for guaranteed coverage
- [ ] Ensemble disagreement as uncertainty proxy

### Use Cases
- [ ] Flag high-uncertainty books for manual review
- [ ] Show confidence ranges in UI
- [ ] Adjust bidding strategy based on uncertainty

## Active Learning

### Goal
Intelligently select books for manual pricing to maximize model improvement.

### Strategies
- [ ] Uncertainty sampling (prioritize high-uncertainty books)
- [ ] Query-by-committee (books where specialists disagree)
- [ ] Diversity sampling (cover feature space uniformly)
- [ ] Error-driven sampling (focus on systematic errors)

## Real-Time Model Updates

### Infrastructure
- [ ] Implement incremental learning (update weights without full retrain)
- [ ] Set up automated retraining pipeline (weekly/monthly)
- [ ] A/B testing framework for model comparison
- [ ] Model monitoring dashboard (track MAE, bias, feature drift)

### Triggers for Retraining
- [ ] MAE degrades > 10% from baseline
- [ ] New data accumulates > 1,000 samples
- [ ] Quarterly scheduled retrains
- [ ] Significant market events (e.g., platform policy changes)

## Evaluation & Monitoring

### Metrics to Track
- [ ] MAE by price range (under $10, $10-$50, over $50)
- [ ] MAE by book category (textbooks, fiction, collectibles)
- [ ] MAE by condition
- [ ] Feature importance stability over time
- [ ] Prediction bias (systematic over/under-estimation)

### Dashboards to Build
- [ ] Real-time prediction quality monitoring
- [ ] Feature importance trends
- [ ] Data coverage visualization (which books have which features)
- [ ] Error analysis (where is model failing?)

## Research Questions

### To Investigate
- [ ] Why does AbeBooks have such low MAE ($0.28)? Can we learn from that?
- [ ] Why does Amazon perform so poorly (MAE $17.27)? Data quality issue?
- [ ] Are there book genres where stacking works better than unified?
- [ ] Can we predict which modeling approach (unified vs stacking) will work best for a given book?
- [ ] What's the optimal trade-off between model complexity and data sparsity?

## Resources & Papers to Review

### Stacking & Ensembles
- [ ] "Stacked Generalization" (Wolpert, 1992) - original paper
- [ ] Netflix Prize winning solutions (stacking at scale)
- [ ] Kaggle competitions using stacking effectively

### Pricing Models
- [ ] Academic papers on book valuation
- [ ] Collectibles pricing models
- [ ] Time series models for market trends

### Data Collection
- [ ] Web scraping best practices for dynamic content
- [ ] Anti-detection techniques
- [ ] Rate limiting strategies

---

**Last Updated:** November 2, 2025  
**Status:** Unified model in production ($3.59 MAE), BookFinder data collection ongoing
