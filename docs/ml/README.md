# ML System Documentation Index

**Last Updated:** November 9, 2025

This directory contains comprehensive documentation for the LotHelper ML price prediction system, including specialist models, training procedures, audit reports, and system architecture.

---

## Quick Links

### System Overview
- **[ML System Comprehensive Report](ML_SYSTEM_COMPREHENSIVE_REPORT.md)** ⭐ START HERE
  - Complete system architecture and current state
  - All 7 specialist models documented
  - Performance metrics and feature engineering details
  - Production deployment status

### Recent Updates (November 2025)
- **[ML Audit Summary (Nov 9, 2025)](ML_AUDIT_SUMMARY_2025_11_09.md)**
  - Temporal weighting audit and implementation
  - Before/after comparison tables
  - Implementation patterns and best practices

- **[Lot Model Temporal Weighting Implementation](ML_AUDIT_LOT_TEMPORAL_WEIGHTING.md)**
  - Detailed implementation report for lot specialist
  - Technical architecture and validation
  - Performance analysis and future recommendations

### Code Mapping
- **[Lot Temporal Weighting Code Map](../../CODE_MAP_LOT_TEMPORAL_WEIGHTING.md)**
  - Line-by-line code changes with explanations
  - Training pipeline flow diagrams
  - Testing and deployment procedures

### Historical Reports
- **[Stacking Ensemble Implementation Report](../../docs/analysis/STACKING_ENSEMBLE_REPORT.md)**
  - Original stacking architecture design (Nov 1, 2025)
  - Base model + meta-model implementation
  - Initial performance analysis

---

## Documentation by Topic

### Architecture & Design

| Document | Description | Last Updated |
|----------|-------------|--------------|
| [ML System Comprehensive Report](ML_SYSTEM_COMPREHENSIVE_REPORT.md) | Complete system architecture, all models | Nov 9, 2025 |
| [Stacking Ensemble Report](../../docs/analysis/STACKING_ENSEMBLE_REPORT.md) | Stacking architecture design | Nov 1, 2025 |

### Model Training & Implementation

| Document | Description | Last Updated |
|----------|-------------|--------------|
| [ML Audit Lot Temporal Weighting](ML_AUDIT_LOT_TEMPORAL_WEIGHTING.md) | Lot model implementation details | Nov 9, 2025 |
| [ML Audit Summary](ML_AUDIT_SUMMARY_2025_11_09.md) | Temporal weighting audit results | Nov 9, 2025 |
| [ML Phase 2 & 3 Complete](ML_PHASE2_PHASE3_COMPLETE.md) | Platform scaling features | Oct 2025 |
| [ML Phase 4 Book Attributes](ML_PHASE4_BOOK_ATTRIBUTES.md) | Signed/first edition features | Oct 2025 |

### Data Collection

| Document | Description | Last Updated |
|----------|-------------|--------------|
| [Training Data Collection POC](TRAINING_DATA_COLLECTION_POC.md) | Data collection strategy | Oct 2025 |
| [POC Results](POC_RESULTS.md) | Collection POC validation | Oct 2025 |
| [POC Collector Complete](POC_COLLECTOR_COMPLETE.md) | Production collector implementation | Oct 2025 |
| [Decodo Collection Status](DECODO_COLLECTION_STATUS.md) | eBay sold comps collection | Oct 2025 |

### Analysis & Results

| Document | Description | Last Updated |
|----------|-------------|--------------|
| [ML Phase 1 Results](ML_PHASE1_RESULTS.md) | Initial model results | Sep 2025 |
| [Platform Pricing Analysis](../../docs/analysis/PLATFORM_PRICING_ANALYSIS.md) | Cross-platform price analysis | Nov 2025 |
| [AbeBooks ML Impact Report](../../docs/analysis/ABEBOOKS_ML_IMPACT_REPORT.md) | AbeBooks data impact | Nov 2025 |

---

## System Components

### Specialist Models (Production)

| Model | Purpose | Features | Performance | Status | Documentation |
|-------|---------|----------|-------------|--------|---------------|
| eBay | eBay sold comps pricing | 26 | MAE $4.51, R² 0.042 | ✅ Prod | [Comprehensive Report](ML_SYSTEM_COMPREHENSIVE_REPORT.md#ebay-model) |
| AbeBooks | AbeBooks marketplace | 28 | MAE $0.29, R² 0.873 | ✅ Prod | [Comprehensive Report](ML_SYSTEM_COMPREHENSIVE_REPORT.md#abebooks-model) |
| Amazon | Amazon marketplace | 27 | MAE $0.18, R² 0.996 | ✅ Prod | [Comprehensive Report](ML_SYSTEM_COMPREHENSIVE_REPORT.md#amazon-model) |
| Lot | Book series lots | 15 | MAE $1.13, R² 0.980 | ✅ Prod | [Lot Implementation](ML_AUDIT_LOT_TEMPORAL_WEIGHTING.md) |

### Specialist Models (Trained, Not in Ensemble)

| Model | Purpose | Status | Documentation |
|-------|---------|--------|---------------|
| Biblio | Biblio.com marketplace | ⏸️ Ready | [Comprehensive Report](ML_SYSTEM_COMPREHENSIVE_REPORT.md) |
| Alibris | Alibris marketplace | ⏸️ Ready | [Comprehensive Report](ML_SYSTEM_COMPREHENSIVE_REPORT.md) |
| Zvab | ZVAB German marketplace | ⏸️ Ready | [Comprehensive Report](ML_SYSTEM_COMPREHENSIVE_REPORT.md) |

### Meta-Model

| Component | Purpose | Status | Documentation |
|-----------|---------|--------|---------------|
| Meta-Model | Ensemble prediction (Ridge) | ⏸️ Not Prod | [Stacking Report](../../docs/analysis/STACKING_ENSEMBLE_REPORT.md) |

---

## Key Findings & Best Practices

### Model Performance Insights

1. **Amazon FBM Dominance** (99.6% feature importance)
   - Third-party FBM sellers provide more accurate pricing than Amazon itself
   - Traditional Amazon features (rank, count) have near-zero importance
   - Key learning: Market equilibrium from competitive sellers beats official pricing

2. **AbeBooks Direct Signal** (53.5% feature importance)
   - When predicting AbeBooks from AbeBooks features, model learns to denoise marketplace data
   - Achieves excellent performance (MAE $0.29, R² 0.873)
   - Key learning: Direct marketplace features are strongest predictors

3. **Lot Pricing Economics** (lot_size + price_per_book = 90.6%)
   - Lot pricing is simple quantity × value economics
   - Completion percentage has minimal impact (1.3% importance)
   - Key learning: Buyers value quantity over completeness for most series

4. **eBay Challenges** (R² 0.042)
   - Limited training data (726 books) causes high variance
   - Condition subjectivity affects pricing
   - Key learning: Need more training data to improve

### Training Best Practices

1. **Temporal Sample Weighting** ✅
   - Exponential decay with 365-day half-life
   - Automatically downweights stale data as it ages
   - Implemented: eBay, AbeBooks, Amazon, Lot
   - Pending: Biblio, Alibris, Zvab

2. **GroupKFold Cross-Validation** ✅
   - Prevents ISBN leakage across folds
   - Implemented: All ISBN-based models
   - Exception: Lot model (unique lot IDs)

3. **Log Transform for Target** ✅
   - Reduces outlier impact
   - Stabilizes variance
   - Applied: eBay, AbeBooks, Amazon (high variance platforms)

4. **Hyperparameter Tuning** ✅
   - RandomizedSearchCV (50 iterations, 3-fold CV)
   - Scoring: Negative MAE
   - Applied: Lot model (XGBoost)

---

## Training Scripts

### Individual Models
```bash
# Specialist models
python3 scripts/stacking/train_ebay_model.py
python3 scripts/stacking/train_abebooks_model.py
python3 scripts/stacking/train_amazon_model.py
python3 scripts/stacking/train_lot_model.py
python3 scripts/stacking/train_biblio_model.py
python3 scripts/stacking/train_alibris_model.py
python3 scripts/stacking/train_zvab_model.py

# Meta-model
python3 scripts/stacking/generate_oof_predictions.py
python3 scripts/stacking/train_meta_model.py
```

### Batch Training
```bash
# All models (parallel recommended)
python3 scripts/ml_train --all
```

---

## Data Collection Scripts

### Active Collections
```bash
# AbeBooks (Priority - ongoing)
python3 scripts/collect_abebooks_bulk.py \
  --isbn-file /tmp/abebooks_all_isbns.txt \
  --output abebooks_results_full.json \
  --resume

# Zvab (German market)
python3 scripts/collect_zvab_bulk.py \
  --isbn-file /tmp/zvab_all_isbns.txt \
  --output zvab_results_full.json \
  --resume

# Alibris (Alternative US marketplace)
python3 scripts/collect_alibris_bulk.py \
  --isbn-file /tmp/alibris_all_isbns.txt \
  --output alibris_results_full.json \
  --resume

# Amazon FBM (Ongoing as needed)
python3 scripts/collect_amazon_fbm_bulk.py \
  --isbn-file /tmp/amazon_fbm_isbns.txt
```

---

## Model Artifacts

### Location
```
isbn_lot_optimizer/models/stacking/
├── {model}_model.pkl      - Trained model (GradientBoosting or XGBoost)
├── {model}_scaler.pkl      - StandardScaler for features
└── {model}_metadata.json   - Metadata (performance, features, hyperparams)
```

### Metadata Fields (Standard)
```json
{
  "platform": "amazon",
  "model_type": "GradientBoostingRegressor",
  "n_features": 27,
  "feature_names": [...],
  "training_samples": 14449,
  "test_samples": 3612,
  "train_mae": 0.17,
  "test_mae": 0.18,
  "train_r2": 0.995,
  "test_r2": 0.996,
  "use_temporal_weighting": true,
  "use_groupkfold": true,
  "hyperparameters": {...},
  "feature_importance": {...},
  "trained_at": "2025-11-09T19:52:58.206496"
}
```

---

## API Integration

### Endpoint
```
POST /api/v1/books/{isbn}/estimate_price
```

### Enhanced Response (Nov 9, 2025)
```json
{
  "isbn": "9780316769174",
  "price": 15.50,
  "confidence": "medium",
  "from_metadata_only": false,
  "deltas": [
    {
      "attribute": "signed",
      "delta": 12.50,
      "description": "Price increase if signed"
    }
  ],
  "specialist_predictions": {
    "ebay": 18.30,
    "abebooks": 14.20,
    "amazon": 15.50
  }
}
```

---

## Recent Improvements

### November 9, 2025
- ✅ Temporal sample weighting for Amazon model
- ✅ Temporal sample weighting for Lot model
- ✅ API transparency: `deltas[]` array showing attribute impacts
- ✅ API transparency: `from_metadata_only` flag for data source indication
- ✅ Comprehensive documentation update

### October-November 2025
- ✅ Amazon FBM data integration (99.6% feature importance)
- ✅ Platform scaling features across all models
- ✅ Signed/first edition prediction capabilities
- ✅ BookFinder cross-platform calibration

---

## Roadmap

### Short-Term (Next 30 Days)
1. Complete AbeBooks collection (batch 192: 19,249 ISBNs)
2. Retrain all models with enriched dataset
3. Monitor production performance of updated models
4. Add temporal weight monitoring dashboards

### Medium-Term (Next 3 Months)
1. Implement temporal weighting for Biblio/Alibris/Zvab
2. Retrain meta-model with full AbeBooks data
3. Hyperparameter re-tuning with latest data
4. Quarterly model refresh

### Long-Term (6+ Months)
1. Dynamic decay tuning (platform-specific half-lives)
2. Advanced ensemble techniques (confidence weighting, attention)
3. Deep learning exploration (if sufficient data)

---

## Contributing

### Adding New Documentation
1. Create markdown file in `docs/ml/`
2. Add entry to this README index
3. Link from relevant sections
4. Update comprehensive report if system-level changes

### Updating Models
1. Train model using standard scripts
2. Update model artifacts in `isbn_lot_optimizer/models/stacking/`
3. Document changes in comprehensive report
4. Update metadata.json with new metrics

### Reporting Issues
- Model performance degradation → File issue with metrics
- Data collection failures → Check scripts in `scripts/collect_*.py`
- Training errors → Review `scripts/stacking/train_*.py` logs

---

## Contact & Support

**System Owner:** Nick Cuskey
**ML Architecture:** Claude Code (Anthropic)
**Last Audit:** November 9, 2025
**Next Review:** February 2026 (quarterly)

---

## Document Index

### Core Documentation
- [ML System Comprehensive Report](ML_SYSTEM_COMPREHENSIVE_REPORT.md) ⭐
- [ML Audit Summary (Nov 9, 2025)](ML_AUDIT_SUMMARY_2025_11_09.md)
- [Lot Model Temporal Weighting](ML_AUDIT_LOT_TEMPORAL_WEIGHTING.md)
- [Stacking Ensemble Report](../../docs/analysis/STACKING_ENSEMBLE_REPORT.md)

### Code Maps
- [Lot Temporal Weighting Code Map](../../CODE_MAP_LOT_TEMPORAL_WEIGHTING.md)

### Phase Documentation
- [ML Phase 1 Results](ML_PHASE1_RESULTS.md)
- [ML Phase 2 & 3 Complete](ML_PHASE2_PHASE3_COMPLETE.md)
- [ML Phase 4 Book Attributes](ML_PHASE4_BOOK_ATTRIBUTES.md)

### Data Collection
- [Training Data Collection POC](TRAINING_DATA_COLLECTION_POC.md)
- [POC Results](POC_RESULTS.md)
- [POC Collector Complete](POC_COLLECTOR_COMPLETE.md)
- [Decodo Collection Status](DECODO_COLLECTION_STATUS.md)
- [eBay API Fix](EBAY_API_FIX.md)

### Analysis
- [Platform Pricing Analysis](../../docs/analysis/PLATFORM_PRICING_ANALYSIS.md)
- [Platform Scaling Analysis](../../docs/analysis/PLATFORM_SCALING_ANALYSIS.md)
- [AbeBooks ML Impact Report](../../docs/analysis/ABEBOOKS_ML_IMPACT_REPORT.md)
- [Model Retrain Results](../../docs/analysis/MODEL_RETRAIN_RESULTS.md)

---

**Last Updated:** November 9, 2025
**Next Review:** February 2026
