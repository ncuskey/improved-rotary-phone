#!/usr/bin/env python3
"""
Train AbeBooks specialist model for stacking ensemble.

Trains an XGBoost model with hyperparameter tuning optimized for AbeBooks pricing prediction
using AbeBooks-specific features (pricing signals, platform scaling, competition).
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import joblib
import numpy as np
from sklearn.model_selection import RandomizedSearchCV
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Check Python version for XGBoost/OpenMP compatibility
from shared.python_version_check import check_python_version
check_python_version()

from scripts.stacking.data_loader import load_platform_training_data
from scripts.stacking.training_utils import (
    apply_log_transform,
    inverse_log_transform,
    group_train_test_split,
    compute_metrics,
    remove_outliers,
    calculate_temporal_weights,
    calculate_price_type_weights
)
from isbn_lot_optimizer.ml.feature_extractor import PlatformFeatureExtractor


def create_simple_objects(record: dict):
    """Convert record dict to simple objects for feature extraction."""
    class SimpleMetadata:
        def __init__(self, d, cover_type, signed, printing):
            self.page_count = d.get('page_count')
            self.published_year = d.get('published_year')
            self.average_rating = d.get('average_rating')
            self.ratings_count = d.get('ratings_count')
            self.list_price = d.get('list_price')
            self.categories = d.get('categories', [])
            self.cover_type = cover_type
            self.signed = bool(signed)
            self.printing = printing

    class SimpleMarket:
        def __init__(self, d):
            self.sold_count = d.get('sold_count')
            self.active_count = d.get('active_count')
            self.active_median_price = d.get('active_median_price')
            self.sold_avg_price = d.get('sold_avg_price')
            self.sell_through_rate = d.get('sell_through_rate')

    class SimpleBookscouter:
        def __init__(self, d):
            self.amazon_sales_rank = d.get('amazon_sales_rank')
            self.amazon_count = d.get('amazon_count')
            self.amazon_lowest_price = d.get('amazon_lowest_price')

    metadata = SimpleMetadata(
        record['metadata'],
        record.get('cover_type'),
        record.get('signed', False),
        record.get('printing')
    ) if record['metadata'] else None

    market = SimpleMarket(record['market']) if record['market'] else None
    bookscouter = SimpleBookscouter(record['bookscouter']) if record['bookscouter'] else None

    return metadata, market, bookscouter


def extract_features(records, targets, extractor, catalog_db_path):
    """Extract AbeBooks-specific features from records."""
    from isbn_lot_optimizer.ml.feature_extractor import get_bookfinder_features

    X = []
    y = []
    isbns = []
    completeness_scores = []
    timestamps = []
    price_types = []

    for record, target in zip(records, targets):
        metadata, market, bookscouter = create_simple_objects(record)
        # Query BookFinder features for this ISBN
        bookfinder_data = get_bookfinder_features(record['isbn'], str(catalog_db_path))

        features = extractor.extract_for_platform(
            platform='abebooks',
            metadata=metadata,
            market=market,
            bookscouter=bookscouter,
            condition=record.get('condition', 'Good'),
            abebooks=record.get('abebooks'),
            bookfinder=bookfinder_data
        )

        X.append(features.values)
        y.append(target)
        isbns.append(record['isbn'])
        completeness_scores.append(features.completeness)

        # Extract timestamp and price type for quick wins
        timestamps.append(record.get('abebooks_timestamp'))
        price_types.append(record.get('abebooks_price_type', 'listing'))

    return np.array(X), np.array(y), isbns, completeness_scores, timestamps, price_types


def train_abebooks_model():
    """Train and save AbeBooks specialist model."""
    print("=" * 80)
    print("TRAINING ABEBOOKS SPECIALIST MODEL")
    print("=" * 80)

    # Load data
    print("\n1. Loading AbeBooks training data...")
    platform_data = load_platform_training_data()
    abebooks_records, abebooks_targets = platform_data['abebooks']

    print(f"\n   Loaded {len(abebooks_records)} AbeBooks books")
    print(f"   Target range: ${min(abebooks_targets):.2f} - ${max(abebooks_targets):.2f}")
    print(f"   Target mean: ${np.mean(abebooks_targets):.2f}")

    # Extract features
    print("\n2. Extracting AbeBooks-specific features...")
    extractor = PlatformFeatureExtractor()
    X, y, isbns, completeness, timestamps, price_types = extract_features(abebooks_records, abebooks_targets, extractor, Path.home() / '.isbn_lot_optimizer' / 'catalog.db')

    feature_names = PlatformFeatureExtractor.get_platform_feature_names('abebooks')
    print(f"   Features extracted: {len(feature_names)} features")
    print(f"   Average completeness: {np.mean(completeness):.1%}")

    # Calculate temporal and price type weights (Quick Wins)
    print("\n   Calculating temporal and price type weights...")
    temporal_weights = calculate_temporal_weights(timestamps, decay_days=365.0)
    price_type_weights = calculate_price_type_weights(price_types, sold_weight=3.0)

    # Combine weights (element-wise multiply)
    if temporal_weights is not None and price_type_weights is not None:
        combined_weights = temporal_weights * price_type_weights
        print(f"   ✓ Temporal weighting: weight range {temporal_weights.min():.4f}-{temporal_weights.max():.4f}")
        print(f"   ✓ Price type weighting: mean sold weight {price_type_weights[np.array(price_types) == 'sold'].mean() if any(pt == 'sold' for pt in price_types) else 0:.2f}x")
        print(f"   ✓ Combined weight range: {combined_weights.min():.4f}-{combined_weights.max():.4f}")
    else:
        combined_weights = None
        print(f"   ⚠ Temporal/price type weights unavailable, proceeding without weighting")

    # Remove outliers (need to track indices for weights)
    print("\n3. Removing outliers...")
    z_scores = np.abs((y - np.mean(y)) / np.std(y))
    outlier_mask = z_scores < 3.0

    X_clean = X[outlier_mask]
    y_clean = y[outlier_mask]
    isbns_clean = [isbn for i, isbn in enumerate(isbns) if outlier_mask[i]]

    # Apply same mask to weights if available
    if combined_weights is not None:
        combined_weights = combined_weights[outlier_mask]

    print(f"   Removed {len(X) - len(X_clean)} outliers ({(len(X) - len(X_clean)) / len(X) * 100:.1f}%)")
    print(f"   Training samples: {len(X_clean)}")

    # Split data using GroupKFold by ISBN (prevents leakage)
    print("\n4. Splitting train/test with GroupKFold by ISBN...")
    from sklearn.model_selection import GroupKFold

    isbn_groups = np.array(isbns_clean)
    gkf = GroupKFold(n_splits=5)
    train_idx, test_idx = list(gkf.split(X_clean, y_clean, groups=isbn_groups))[-1]

    X_train = X_clean[train_idx]
    X_test = X_clean[test_idx]
    y_train = y_clean[train_idx]
    y_test = y_clean[test_idx]

    # Split weights for train/test
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

    # Apply log transform (best practice)
    print("\n5. Applying log transform to target...")
    y_train_log, y_test_log, y_train_orig, y_test_orig = apply_log_transform(y_train, y_test)

    # Scale features
    print("\n6. Scaling features...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train model with hyperparameter tuning
    print("\n7. Training XGBoost model with hyperparameter tuning...")

    # Define hyperparameter search space
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

    # Fit on log-transformed targets with sample weights (Quick Wins)
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
    print("\n8. Evaluating model...")
    y_train_pred_log = model.predict(X_train_scaled)
    y_test_pred_log = model.predict(X_test_scaled)

    # Inverse transform to get actual prices
    y_train_pred = inverse_log_transform(y_train_pred_log)
    y_test_pred = inverse_log_transform(y_test_pred_log)

    # Compute metrics on original scale
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
    print("ABEBOOKS MODEL PERFORMANCE")
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

    # Feature importance
    print("\n" + "=" * 80)
    print("TOP 10 FEATURE IMPORTANCE")
    print("=" * 80)

    importance = dict(zip(feature_names, model.feature_importances_))
    top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]

    for i, (name, imp) in enumerate(top_features, 1):
        print(f"{i:2d}. {name:30s} {imp:.4f} ({imp*100:5.1f}%)")

    # Save model artifacts
    print("\n" + "=" * 80)
    print("SAVING MODEL ARTIFACTS")
    print("=" * 80)

    model_dir = Path(__file__).parent.parent.parent / 'isbn_lot_optimizer' / 'models' / 'stacking'
    model_dir.mkdir(parents=True, exist_ok=True)

    # Save model
    model_path = model_dir / 'abebooks_model.pkl'
    joblib.dump(model, model_path)
    print(f"✓ Saved model: {model_path}")

    # Save scaler
    scaler_path = model_dir / 'abebooks_scaler.pkl'
    joblib.dump(scaler, scaler_path)
    print(f"✓ Saved scaler: {scaler_path}")

    # Save metadata
    metadata = {
        'platform': 'abebooks',
        'model_type': 'XGBRegressor',
        'version': 'v3_quick_wins_temporal_price_type',
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
        'trained_at': datetime.now().isoformat(),
    }

    metadata_path = model_dir / 'abebooks_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Saved metadata: {metadata_path}")

    print("\n" + "=" * 80)
    print("ABEBOOKS MODEL TRAINING COMPLETE")
    print("=" * 80)
    print(f"\nModel saved to: {model_path}")
    print(f"Test MAE: ${test_mae:.2f}")
    print(f"Test R²:  {test_r2:.3f}")
    print("=" * 80 + "\n")

    return {
        'model': model,
        'scaler': scaler,
        'metadata': metadata,
        'test_mae': test_mae,
        'test_r2': test_r2,
    }


if __name__ == "__main__":
    train_abebooks_model()
