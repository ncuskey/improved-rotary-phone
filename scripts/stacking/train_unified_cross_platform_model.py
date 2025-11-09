#!/usr/bin/env python3
"""
Train unified cross-platform model for book price prediction.

This model uses eBay sold prices as the universal ground truth target,
and leverages listing prices from all platforms (Amazon, AbeBooks, eBay listings)
as features to learn cross-platform relationships.

Key advantages over specialist models:
- Uses real sold prices (no synthetic targets)
- Learns cross-platform relationships from data
- Validates against ground truth (eBay sold)
- Statistically sound (no ratio assumptions)
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import joblib
import numpy as np
from sklearn.model_selection import RandomizedSearchCV, GroupKFold
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Check Python version for XGBoost/OpenMP compatibility
from shared.python_version_check import check_python_version
check_python_version()

from scripts.stacking.data_loader import load_unified_cross_platform_data
from scripts.stacking.training_utils import (
    apply_log_transform,
    inverse_log_transform,
    compute_metrics,
    calculate_temporal_weights,
    calculate_price_type_weights
)


def extract_unified_features(records):
    """
    Extract cross-platform features from unified training records.

    Features include:
    - eBay sold stats (min, max, count)
    - eBay listing prices (median, count, spread)
    - Amazon FBM prices (median, count, spread)
    - AbeBooks prices (median, count, spread)
    - Cross-platform ratios (amazon/ebay, abebooks/ebay)
    - Platform availability flags
    - Metadata (page count, age, binding, etc.)

    Returns:
        X: Feature matrix
        y: Target vector (eBay sold prices)
        isbns: ISBN list for GroupKFold
        timestamps: Timestamps for temporal weighting
        price_types: Price types for price type weighting
        feature_names: List of feature names
    """
    X = []
    y = []
    isbns = []
    timestamps = []
    price_types = []

    for record in records:
        features = []

        # === eBay Sold Features (target-related but useful for spread/range) ===
        features.append(record.get('ebay_sold_count') or 0)
        features.append(record.get('ebay_sold_min') or 0)
        features.append(record.get('ebay_sold_max') or 0)

        # Calculate eBay sold price spread
        ebay_sold_min = record.get('ebay_sold_min') or 0
        ebay_sold_max = record.get('ebay_sold_max') or 0
        if ebay_sold_max > 0:
            ebay_sold_spread = (ebay_sold_max - ebay_sold_min) / ebay_sold_max
        else:
            ebay_sold_spread = 0
        features.append(ebay_sold_spread)

        # === eBay Listing Features (key signal for listing→sold relationship) ===
        ebay_listing_median = record.get('ebay_listing_median') or 0
        ebay_listing_count = record.get('ebay_listing_count') or 0
        ebay_listing_min = record.get('ebay_listing_min') or 0
        ebay_listing_max = record.get('ebay_listing_max') or 0

        features.append(ebay_listing_median)
        features.append(ebay_listing_count)
        features.append(ebay_listing_min)
        features.append(ebay_listing_max)

        # eBay listing price spread
        if ebay_listing_max > 0:
            ebay_listing_spread = (ebay_listing_max - ebay_listing_min) / ebay_listing_max
        else:
            ebay_listing_spread = 0
        features.append(ebay_listing_spread)

        # eBay listing/sold ratio (seller optimism metric)
        ebay_listing_to_sold_ratio = record.get('ebay_listing_to_sold_ratio') or 0
        features.append(ebay_listing_to_sold_ratio)

        # === Amazon FBM Features (strongest cross-platform signal) ===
        amazon_median = record.get('amazon_fbm_median') or 0
        amazon_count = record.get('amazon_fbm_count') or 0
        amazon_min = record.get('amazon_fbm_min') or 0
        amazon_max = record.get('amazon_fbm_max') or 0
        amazon_rating = record.get('amazon_fbm_avg_rating') or 0

        features.append(amazon_median)
        features.append(amazon_count)
        features.append(amazon_min)
        features.append(amazon_max)
        features.append(amazon_rating)

        # Amazon price spread
        if amazon_max > 0:
            amazon_spread = (amazon_max - amazon_min) / amazon_max
        else:
            amazon_spread = 0
        features.append(amazon_spread)

        # === AbeBooks Features (niche academic/collectible signal) ===
        abebooks_median = record.get('abebooks_median') or 0
        abebooks_count = record.get('abebooks_count') or 0
        abebooks_min = record.get('abebooks_min') or 0
        abebooks_max = record.get('abebooks_max') or 0
        abebooks_spread = record.get('abebooks_spread') or 0
        abebooks_has_new = int(record.get('abebooks_has_new') or 0)
        abebooks_has_used = int(record.get('abebooks_has_used') or 0)
        abebooks_hc_premium = record.get('abebooks_hc_premium') or 0

        features.append(abebooks_median)
        features.append(abebooks_count)
        features.append(abebooks_min)
        features.append(abebooks_max)
        features.append(abebooks_spread)
        features.append(abebooks_has_new)
        features.append(abebooks_has_used)
        features.append(abebooks_hc_premium)

        # === Cross-Platform Ratios (let model learn relationships) ===
        amazon_to_ebay_ratio = record.get('amazon_to_ebay_ratio') or 0
        abebooks_to_ebay_ratio = record.get('abebooks_to_ebay_ratio') or 0
        amazon_to_abebooks_ratio = record.get('amazon_to_abebooks_ratio') or 0

        features.append(amazon_to_ebay_ratio)
        features.append(abebooks_to_ebay_ratio)
        features.append(amazon_to_abebooks_ratio)

        # === Platform Availability Flags ===
        has_amazon = int(amazon_median > 0)
        has_abebooks = int(abebooks_median > 0)
        has_ebay_listing = int(ebay_listing_median > 0)

        features.append(has_amazon)
        features.append(has_abebooks)
        features.append(has_ebay_listing)

        # === Platform Price Consensus ===
        # Calculate consensus median from available platforms
        platform_prices = []
        if ebay_listing_median > 0:
            platform_prices.append(ebay_listing_median)
        if amazon_median > 0:
            platform_prices.append(amazon_median)
        if abebooks_median > 0:
            platform_prices.append(abebooks_median)

        if len(platform_prices) >= 2:
            platform_consensus = np.median(platform_prices)
            platform_spread_pct = np.std(platform_prices) / np.mean(platform_prices) if np.mean(platform_prices) > 0 else 0
            platform_agreement = 1.0 / (1.0 + platform_spread_pct)  # 0-1 scale, 1 = perfect agreement
        else:
            platform_consensus = 0
            platform_spread_pct = 0
            platform_agreement = 0

        features.append(platform_consensus)
        features.append(platform_spread_pct)
        features.append(platform_agreement)

        # === Metadata Features ===
        metadata = record.get('metadata', {})
        page_count = metadata.get('page_count') or 0
        pub_year = metadata.get('published_year') or 0

        # Calculate age
        current_year = datetime.now().year
        if pub_year and pub_year > 0:
            age_years = current_year - pub_year
        else:
            age_years = 0

        features.append(page_count)
        features.append(age_years)

        # Binding type (one-hot encoded)
        binding = (metadata.get('binding') or '').lower()
        is_hardcover = int('hard' in binding or 'hc' in binding)
        is_paperback = int('paper' in binding or 'pb' in binding)
        is_mass_market = int('mass' in binding)

        features.append(is_hardcover)
        features.append(is_paperback)
        features.append(is_mass_market)

        # Special attributes
        cover_type = record.get('cover_type', '').lower() if record.get('cover_type') else ''
        signed = record.get('signed', False)
        is_signed = int(bool(signed))

        features.append(is_signed)

        # === Market Stats Features ===
        market = record.get('market', {})
        # Note: Not all records have complete market stats from metadata_cache

        # Append features
        X.append(features)
        y.append(record['ebay_sold_median'])
        isbns.append(record['isbn'])
        timestamps.append(record.get('timestamp'))
        price_types.append(record.get('target_type', 'sold'))

    # Feature names for interpretability
    feature_names = [
        # eBay sold
        'ebay_sold_count', 'ebay_sold_min', 'ebay_sold_max', 'ebay_sold_spread',
        # eBay listing
        'ebay_listing_median', 'ebay_listing_count', 'ebay_listing_min', 'ebay_listing_max',
        'ebay_listing_spread', 'ebay_listing_to_sold_ratio',
        # Amazon FBM
        'amazon_median', 'amazon_count', 'amazon_min', 'amazon_max', 'amazon_rating',
        'amazon_spread',
        # AbeBooks
        'abebooks_median', 'abebooks_count', 'abebooks_min', 'abebooks_max',
        'abebooks_spread', 'abebooks_has_new', 'abebooks_has_used', 'abebooks_hc_premium',
        # Cross-platform ratios
        'amazon_to_ebay_ratio', 'abebooks_to_ebay_ratio', 'amazon_to_abebooks_ratio',
        # Platform availability
        'has_amazon', 'has_abebooks', 'has_ebay_listing',
        # Platform consensus
        'platform_consensus', 'platform_spread_pct', 'platform_agreement',
        # Metadata
        'page_count', 'age_years',
        # Binding
        'is_hardcover', 'is_paperback', 'is_mass_market',
        # Special
        'is_signed',
    ]

    return np.array(X), np.array(y), isbns, timestamps, price_types, feature_names


def train_unified_model():
    """Train and save unified cross-platform model."""
    print("=" * 80)
    print("TRAINING UNIFIED CROSS-PLATFORM MODEL")
    print("=" * 80)
    print("\nThis model uses eBay sold prices as ground truth targets,")
    print("and learns from Amazon, AbeBooks, and eBay listing prices as features.")
    print("\nKey advantages:")
    print("  - Real sold prices (no synthetic targets)")
    print("  - Learns cross-platform relationships from data")
    print("  - Validates against ground truth")
    print("  - Statistically sound approach")

    # Load unified training data
    print("\n1. Loading unified cross-platform training data...")
    records, targets = load_unified_cross_platform_data()

    print(f"\n   Loaded {len(records)} books with eBay sold targets")
    print(f"   Target range: ${min(targets):.2f} - ${max(targets):.2f}")
    print(f"   Target mean: ${np.mean(targets):.2f}")

    # Extract features
    print("\n2. Extracting cross-platform features...")
    X, y, isbns, timestamps, price_types, feature_names = extract_unified_features(records)

    print(f"   Features extracted: {len(feature_names)} features")
    print(f"   Feature matrix shape: {X.shape}")

    # Calculate quick wins weights
    print("\n3. Calculating temporal and price type weights...")
    temporal_weights = calculate_temporal_weights(timestamps, decay_days=365.0)
    price_type_weights = calculate_price_type_weights(price_types, sold_weight=3.0)

    # Combine weights
    if temporal_weights is not None and price_type_weights is not None:
        combined_weights = temporal_weights * price_type_weights
        print(f"   ✓ Temporal weighting: weight range {temporal_weights.min():.4f}-{temporal_weights.max():.4f}")
        print(f"   ✓ Price type weighting: mean sold weight {price_type_weights[np.array(price_types) == 'sold'].mean():.2f}x")
        print(f"   ✓ Combined weight range: {combined_weights.min():.4f}-{combined_weights.max():.4f}")
    else:
        combined_weights = None
        print(f"   ⚠ Weights unavailable, proceeding without weighting")

    # Remove outliers
    print("\n4. Removing outliers...")
    z_scores = np.abs((y - np.mean(y)) / np.std(y))
    outlier_mask = z_scores < 3.0

    X_clean = X[outlier_mask]
    y_clean = y[outlier_mask]
    isbns_clean = [isbn for i, isbn in enumerate(isbns) if outlier_mask[i]]

    if combined_weights is not None:
        combined_weights = combined_weights[outlier_mask]

    print(f"   Removed {len(X) - len(X_clean)} outliers ({(len(X) - len(X_clean)) / len(X) * 100:.1f}%)")
    print(f"   Training samples: {len(X_clean)}")

    # Split data using GroupKFold by ISBN (prevents leakage)
    print("\n5. Splitting train/test with GroupKFold by ISBN...")
    isbn_groups = np.array(isbns_clean)
    gkf = GroupKFold(n_splits=5)
    train_idx, test_idx = list(gkf.split(X_clean, y_clean, groups=isbn_groups))[-1]

    X_train = X_clean[train_idx]
    X_test = X_clean[test_idx]
    y_train = y_clean[train_idx]
    y_test = y_clean[test_idx]

    if combined_weights is not None:
        train_weights = combined_weights[train_idx]
        test_weights = combined_weights[test_idx]
    else:
        train_weights = None
        test_weights = None

    print(f"   Train: {len(X_train)} samples")
    print(f"   Test:  {len(X_test)} samples")
    print(f"   Unique ISBNs in train: {len(set(isbn_groups[train_idx]))}")
    print(f"   Unique ISBNs in test:  {len(set(isbn_groups[test_idx]))}")

    # Apply log transform
    print("\n6. Applying log transform to target...")
    y_train_log, y_test_log, y_train_orig, y_test_orig = apply_log_transform(y_train, y_test)

    # Scale features
    print("\n7. Scaling features...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train model with hyperparameter tuning
    print("\n8. Training XGBoost model with hyperparameter tuning...")

    param_distributions = {
        'n_estimators': [100, 200, 300, 400, 500],
        'max_depth': [3, 4, 5, 6, 7],
        'learning_rate': [0.01, 0.05, 0.1, 0.15, 0.2],
        'subsample': [0.6, 0.7, 0.8, 0.9, 1.0],
        'colsample_bytree': [0.6, 0.7, 0.8, 0.9, 1.0],
        'min_child_weight': [1, 2, 3, 4, 5],
        'gamma': [0, 0.1, 0.2, 0.3, 0.4],
        'reg_alpha': [0, 0.01, 0.1, 1],
        'reg_lambda': [1, 10, 100],
    }

    base_model = xgb.XGBRegressor(
        objective='reg:squarederror',
        random_state=42,
        n_jobs=-1,
        tree_method='hist',
    )

    print("   Searching for best hyperparameters (50 iterations, 3-fold CV)...")
    random_search = RandomizedSearchCV(
        estimator=base_model,
        param_distributions=param_distributions,
        n_iter=50,
        cv=3,
        scoring='neg_mean_absolute_error',
        n_jobs=-1,
        random_state=42,
        verbose=1
    )

    if train_weights is not None:
        print(f"   Using temporal + price type sample weighting (Quick Wins)")
        random_search.fit(X_train_scaled, y_train_log, sample_weight=train_weights)
    else:
        print(f"   Training without sample weighting")
        random_search.fit(X_train_scaled, y_train_log)

    model = random_search.best_estimator_
    best_params = random_search.best_params_
    cv_mae = -random_search.best_score_

    print("\n   Best hyperparameters found:")
    for param, value in sorted(best_params.items()):
        print(f"    {param:20s} = {value}")
    print(f"    Best CV MAE (log space): ${cv_mae:.2f}")
    print("\n   Training complete!")

    # Evaluate
    print("\n9. Evaluating model...")
    y_train_pred_log = model.predict(X_train_scaled)
    y_test_pred_log = model.predict(X_test_scaled)

    # Inverse transform to get actual prices
    y_train_pred = inverse_log_transform(y_train_pred_log)
    y_test_pred = inverse_log_transform(y_test_pred_log)

    # Compute metrics
    train_metrics = compute_metrics(y_train_orig, y_train_pred, use_log_target=True)
    test_metrics = compute_metrics(y_test_orig, y_test_pred, use_log_target=True)

    train_mae = train_metrics['mae']
    test_mae = test_metrics['mae']
    train_rmse = train_metrics['rmse']
    test_rmse = test_metrics['rmse']
    train_r2 = train_metrics['r2']
    test_r2 = test_metrics['r2']
    test_mape = test_metrics['mape']

    print("\n" + "=" * 80)
    print("UNIFIED MODEL PERFORMANCE")
    print("=" * 80)
    print(f"\nTraining Metrics:")
    print(f"  MAE:  ${train_mae:.2f}")
    print(f"  RMSE: ${train_rmse:.2f}")
    print(f"  R²:   {train_r2:.3f}")

    print(f"\nTest Metrics:")
    print(f"  MAE:  ${test_mae:.2f}")
    print(f"  RMSE: ${test_rmse:.2f}")
    print(f"  R²:   {test_r2:.3f}")
    print(f"  MAPE: {test_mape:.1f}%")

    print(f"\n✨ Baseline eBay specialist: 11.9% MAPE")
    if test_mape < 11.9:
        improvement = 11.9 - test_mape
        print(f"✅ IMPROVEMENT: {improvement:.1f} percentage points better!")
    else:
        print(f"⚠️  Performance similar to baseline (expected with limited eBay listing coverage)")

    # Feature importance
    print("\n" + "=" * 80)
    print("TOP 20 FEATURE IMPORTANCE")
    print("=" * 80)

    importance = dict(zip(feature_names, model.feature_importances_))
    top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:20]

    for i, (name, imp) in enumerate(top_features, 1):
        print(f"{i:2d}. {name:30s} {imp:.4f} ({imp*100:5.1f}%)")

    # Identify cross-platform features in top 20
    cross_platform_features = [name for name, imp in top_features if any(kw in name for kw in ['amazon', 'abebooks', 'ratio', 'platform'])]
    if cross_platform_features:
        print(f"\n✓ Cross-platform features in top 20: {len(cross_platform_features)}")
        print(f"  {', '.join(cross_platform_features[:5])}")

    # Save model artifacts
    print("\n" + "=" * 80)
    print("SAVING MODEL ARTIFACTS")
    print("=" * 80)

    model_dir = Path(__file__).parent.parent.parent / 'isbn_lot_optimizer' / 'models' / 'stacking'
    model_dir.mkdir(parents=True, exist_ok=True)

    # Save model
    model_path = model_dir / 'unified_cross_platform_model.pkl'
    joblib.dump(model, model_path)
    print(f"✓ Saved model: {model_path}")

    # Save scaler
    scaler_path = model_dir / 'unified_cross_platform_scaler.pkl'
    joblib.dump(scaler, scaler_path)
    print(f"✓ Saved scaler: {scaler_path}")

    # Save metadata
    metadata = {
        'model_type': 'UnifiedCrossPlatform',
        'algorithm': 'XGBRegressor',
        'version': 'v1_unified_ebay_sold_target',
        'description': 'Unified model using eBay sold prices as target, all platform listings as features',
        'n_features': len(feature_names),
        'feature_names': feature_names,
        'training_samples': len(X_train),
        'test_samples': len(X_test),
        'train_mae': float(train_mae),
        'test_mae': float(test_mae),
        'train_rmse': float(train_rmse),
        'test_rmse': float(test_rmse),
        'train_r2': float(train_r2),
        'test_r2': float(test_r2),
        'test_mape': float(test_mape),
        'cv_mae': float(cv_mae),
        'use_log_target': True,
        'use_groupkfold': True,
        'use_temporal_weighting': train_weights is not None,
        'use_price_type_weighting': train_weights is not None,
        'quick_wins': {
            'temporal_decay_days': 365.0,
            'sold_weight_multiplier': 3.0,
            'enabled': train_weights is not None
        },
        'hyperparameters': {k: v for k, v in best_params.items()},
        'optimization': {
            'method': 'RandomizedSearchCV',
            'n_iter': 50,
            'cv_folds': 3,
            'scoring': 'neg_mean_absolute_error'
        },
        'feature_importance': {name: float(imp) for name, imp in importance.items()},
        'top_features': [(name, float(imp)) for name, imp in top_features],
        'cross_platform_features': cross_platform_features,
        'trained_at': datetime.now().isoformat(),
        'target_source': 'ebay_sold_comps_median',
        'feature_sources': ['ebay_listings', 'amazon_fbm', 'abebooks', 'metadata'],
    }

    metadata_path = model_dir / 'unified_cross_platform_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Saved metadata: {metadata_path}")

    print("\n" + "=" * 80)
    print("UNIFIED MODEL TRAINING COMPLETE")
    print("=" * 80)
    print(f"\nModel saved to: {model_path}")
    print(f"Test MAE:  ${test_mae:.2f}")
    print(f"Test MAPE: {test_mape:.1f}%")
    print(f"Test R²:   {test_r2:.3f}")
    print("=" * 80 + "\n")

    return {
        'model': model,
        'scaler': scaler,
        'metadata': metadata,
        'test_mae': test_mae,
        'test_mape': test_mape,
        'test_r2': test_r2,
    }


if __name__ == "__main__":
    train_unified_model()
