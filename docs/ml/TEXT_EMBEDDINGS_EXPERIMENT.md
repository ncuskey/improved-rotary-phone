# Text Embeddings Experiment Report

**Date:** November 9, 2025
**Experiment:** Hybrid Model (Tabular + Text Embeddings) vs Baseline (Tabular Only)
**Platform:** eBay Sold Price Prediction
**Status:** ❌ FAILED - Baseline Outperforms Hybrid

---

## Executive Summary

Text embeddings from book descriptions **degraded** eBay price prediction performance by 29.3% MAE. The baseline model with 24 tabular features outperforms the hybrid model with 408 features (24 tabular + 384 text embeddings).

**Recommendation:** Keep baseline model in production. Disable text embeddings for eBay pipeline.

---

## Experiment Design

### Hypothesis

Adding semantic text embeddings from book descriptions will improve price prediction accuracy, especially for:
- Collectible books with subjective value
- Low-data segments (sold_comps_count < 10)
- Books with rich condition descriptions

### Models Compared

| Model | Features | Description |
|-------|----------|-------------|
| **Baseline** | 24 tabular | Existing eBay specialist model with market data, condition, sold comps |
| **Hybrid** | 408 (24 + 384) | Baseline + text embeddings from book descriptions |

### Text Embedding Architecture

- **Model:** all-MiniLM-L6-v2 (sentence-transformers)
- **Embedding Dimension:** 384
- **Input:** Book descriptions from `cached_books.description`
- **Coverage:** 9,435 / 11,134 books (84.7%)
- **Missing Descriptions:** Replaced with zero vectors

### Training Configuration

```python
GradientBoostingRegressor(
    n_estimators=200,
    learning_rate=0.1,
    max_depth=5,
    min_samples_split=10,
    min_samples_leaf=4,
    subsample=0.8,
    random_state=42
)
```

- **Temporal Weighting:** Enabled (365-day half-life)
- **Train/Test Split:** 80/20 (8,907 / 2,227 samples)
- **Target:** eBay sold price (log-transformed)

---

## Results

### Performance Comparison

| Metric | Baseline | Hybrid | Delta |
|--------|----------|--------|-------|
| **Test MAE** | $1.77 | $2.29 | **-29.3% worse** |
| **Test R²** | 0.926 | 0.917 | **-1.0% worse** |
| Train MAE | $1.52 | $1.71 | -12.5% |
| Train R² | 0.971 | 0.987 | +1.6% |
| Features | 24 | 408 | +1600% |

### Key Findings

1. **Performance Degradation**
   - Hybrid model is **$0.52 worse** per prediction on test set
   - R² drops from 0.926 to 0.917 (worse generalization)

2. **Overfitting Evidence**
   - Hybrid model: Train R² = 0.987, Test R² = 0.917 (gap = 0.070)
   - Baseline model: Train R² = 0.971, Test R² = 0.926 (gap = 0.045)
   - Hybrid model memorizes training data but generalizes poorly

3. **Feature Importance**
   - 384 text embedding dimensions added 1600% more parameters
   - No corresponding improvement in test performance
   - Text features likely capture noise, not signal

---

## Why Text Embeddings Failed

### 1. Strong Tabular Features Already Capture Signal

Existing 24 features already encode price-relevant information:
- `sold_comps_median` - Direct market pricing signal
- `sold_comps_count` - Data confidence
- `condition` - Physical state
- `active_count` / `active_median_price` - Supply/demand
- `sell_through_rate` - Market velocity

### 2. Descriptions Don't Drive eBay Pricing

Book descriptions on eBay typically contain:
- Publisher synopsis (generic across all copies)
- Condition notes (already captured in `condition` field)
- Shipping information (not price-relevant)

Descriptions rarely include:
- First edition statements (captured in metadata)
- Signed book information (captured in `signed` field)
- Rarity indicators (captured in `sold_comps_count`)

### 3. High Dimensionality Without Structure

- 384 embedding dimensions add noise without semantic structure
- Model must learn which dimensions correlate with price
- Insufficient training data (8,907 samples) to learn 384 feature interactions

### 4. Domain Mismatch

Text embeddings work well for:
- Sentiment analysis
- Document classification
- Semantic search

But **not** for:
- Quantitative price prediction driven by market supply/demand
- Structured data domains where tabular features dominate

---

## Comparison to Successful Use Cases

### Where Text Embeddings Would Help

| Domain | Why Text Would Help |
|--------|---------------------|
| Fine art pricing | Provenance descriptions contain unique value signals |
| Real estate | Property descriptions encode subjective desirability |
| Fashion resale | Style descriptions capture trend-based pricing |
| Collectible appraisals | Expert notes contain rarity/condition insights |

### Why eBay Books Are Different

- **Commodity market:** Most books have multiple identical copies
- **Objective pricing:** Condition + market data dominates
- **Standardized descriptions:** Publisher text is generic

---

## Recommendations

### 1. Keep Baseline Model in Production ✅

- Maintain 24-feature tabular model as eBay specialist
- No deployment of hybrid model
- Continue temporal weighting and GroupKFold CV

### 2. Disable Text Embeddings for eBay Pipeline ❌

- Remove text embedding generation from eBay training script
- Set `include_text_embeddings: false` in `model_config.json`
- Archive hybrid model code in `/experiments/text/`

### 3. Document Experiment in Audit Log 📝

- Add to `docs/ml/EXPERIMENT_LOG.md`
- Reference: "Hybrid Model (MiniLM) - Nov 9, 2025 - FAILED"
- Preserve full results for future reference

### 4. Revisit Text Embeddings Only If:

- **Textual data changes:** eBay adds structured appraisal notes
- **Correlation improves:** New text fields show >0.2 correlation with price
- **Domain-specific model:** Fine-tuned LM on book-condition statements
- **Multi-task learning:** Joint prediction of price + sell-through rate

---

## Future Research Paths

If text embeddings are reconsidered, these approaches may work better:

### 1. Short Descriptions Only

- Filter descriptions to ≤40 words
- Focus on condition-specific language
- Reduce noise from generic publisher text

### 2. Conditional Embeddings

- Embed only when `condition` field is missing or ambiguous
- Use text as fallback signal, not primary feature

### 3. Domain-Specific Fine-Tuning

- Fine-tune compact LM (e.g., DistilBERT) on book condition statements
- Train on (description → condition grade) mapping
- May outperform general-purpose MiniLM

### 4. Multi-Task Learning

- Jointly predict price + sell-through rate
- Forces model to extract semantically meaningful features
- Increases text utility beyond single-target prediction

---

## Technical Details

### Feature Extraction Code

```python
# Text embeddings module
from isbn_lot_optimizer.ml.text_embeddings import TextEmbedder, augment_features_with_embeddings

# Generate embeddings
embedder = TextEmbedder(model_name='all-MiniLM-L6-v2')
X_hybrid = augment_features_with_embeddings(X_tabular, descriptions, embedder)

# Result: X_hybrid.shape = (n_samples, 408)
```

### Training Script

Location: `scripts/stacking/train_ebay_hybrid.py`

Key functions:
- `load_ebay_data_with_descriptions()` - Extracts descriptions from `metadata_cache.db`
- `train_baseline_model()` - Trains tabular-only model
- `train_hybrid_model()` - Trains tabular + text model
- Outputs comparison report with MAE/R² deltas

### Artifacts

```
isbn_lot_optimizer/
├── ml/
│   └── text_embeddings.py          # Text embedding module (preserved for future)
scripts/
└── stacking/
    └── train_ebay_hybrid.py         # Experiment script (archived)
docs/
└── ml/
    ├── TEXT_EMBEDDINGS_EXPERIMENT.md  # This report
    └── EXPERIMENT_LOG.md              # Experiment index
```

---

## Lessons Learned

### 1. Parsimony Beats Complexity

> "Everything should be made as simple as possible, but no simpler." - Einstein

Simpler model with strong tabular features generalizes better than complex model with high-dimensional embeddings.

### 2. Controlled Baselines Matter

Clear baseline comparison made the conclusion indisputable:
- Same train/test split
- Same hyperparameters
- Same temporal weighting
- Only difference: text embeddings

### 3. Text ≠ Signal in Every Domain

Only include embeddings when text is semantically tied to target:
- **Good:** Sentiment → star rating
- **Good:** Product review → helpfulness score
- **Bad:** Generic description → objective price

### 4. Regularization Limits

More features without domain structure = overfitting:
- 384 dimensions without structure added noise
- Model learned training-specific patterns
- Failed to generalize to test set

---

## Conclusion

For eBay resale pricing, structured tabular features outperform hybrid text-tabular models. Text embeddings degraded performance by 29.3% MAE due to:

1. Strong existing tabular features
2. Descriptions lacking price-relevant information
3. High dimensionality without semantic structure
4. Domain mismatch (commodity market vs subjective text)

**Recommendation:** Keep models lean, feature-driven, and retrain periodically with fresh market data rather than adding high-dimensional embeddings.

---

## References

- **Training Script:** `scripts/stacking/train_ebay_hybrid.py`
- **Text Embeddings Module:** `isbn_lot_optimizer/ml/text_embeddings.py`
- **Baseline Model:** `isbn_lot_optimizer/models/stacking/ebay_model.pkl`
- **Full Results:** `/tmp/train_ebay_hybrid_v3.log`
- **Sentence Transformers:** https://www.sbert.net/docs/pretrained_models.html

---

**Last Updated:** November 9, 2025
**Next Review:** Only if new textual data sources become available
**Status:** CLOSED - Baseline model remains in production
