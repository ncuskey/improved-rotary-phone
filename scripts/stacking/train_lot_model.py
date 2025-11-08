#!/usr/bin/env python3
"""
Train Lot specialist model for stacking ensemble.

Trains an XGBoost model optimized for predicting book lot prices based on:
- Lot characteristics (size, completeness)
- Series popularity and metadata
- Individual book pricing data when available
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import joblib
import numpy as np
import sqlite3
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Check Python version for XGBoost/OpenMP compatibility
from shared.python_version_check import check_python_version
check_python_version()


def load_lot_training_data():
    """Load lot training data from series_lot_comps table with completion percentage."""
    cache_db = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

    if not cache_db.exists():
        print(f"Error: {cache_db} not found")
        return [], []

    conn = sqlite3.connect(cache_db)
    cursor = conn.cursor()

    # First, get the inferred series size (max lot_size per series)
    series_sizes_query = """
    SELECT
        series_id,
        MAX(lot_size) as inferred_series_size
    FROM series_lot_comps
    WHERE lot_size > 0
    GROUP BY series_id
    """

    cursor.execute(series_sizes_query)
    series_sizes = dict(cursor.fetchall())

    # Load lots with valid pricing data
    # Use both sold and active listings (active represent market expectations)
    query = """
    SELECT
        series_id,
        series_title,
        author_name,
        lot_size,
        is_complete_set,
        condition,
        price,
        is_sold,
        price_per_book
    FROM series_lot_comps
    WHERE price IS NOT NULL
      AND price >= 2.0  -- Minimum reasonable price
      AND lot_size > 0
      AND lot_size <= 50  -- Filter out unrealistic lot sizes
    ORDER BY scraped_at DESC
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    records = []
    targets = []

    for row in rows:
        series_id = row[0]
        lot_size = row[3]
        inferred_series_size = series_sizes.get(series_id, lot_size)

        record = {
            'series_id': series_id,
            'series_title': row[1],
            'author_name': row[2],
            'lot_size': lot_size,
            'is_complete_set': bool(row[4]),
            'condition': row[5],
            'price': row[6],
            'is_sold': bool(row[7]),
            'price_per_book': row[8],
            'inferred_series_size': inferred_series_size,
            'completion_pct': lot_size / inferred_series_size if inferred_series_size > 0 else 0,
        }
        records.append(record)
        targets.append(row[6])  # price

    return records, np.array(targets)


def extract_lot_features(records):
    """Extract lot-specific features from records including completion percentage."""
    X = []

    # Condition mapping
    condition_map = {
        'https://schema.org/NewCondition': 1.0,
        'https://schema.org/UsedCondition': 0.6,
        'https://schema.org/RefurbishedCondition': 0.8,
        'https://schema.org/DamagedCondition': 0.3,
    }

    for record in records:
        features = []

        # Lot characteristics
        features.append(record['lot_size'])  # Number of books in lot
        features.append(1 if record['is_complete_set'] else 0)  # Complete set indicator
        features.append(1 if record['is_sold'] else 0)  # Sold vs active listing

        # Price per book (if available)
        features.append(record['price_per_book'] if record['price_per_book'] else 0)

        # Condition (normalized)
        condition_value = condition_map.get(record['condition'], 0.5)
        features.append(condition_value)

        # Lot size bins (categorical encoded as binary features)
        features.append(1 if record['lot_size'] <= 3 else 0)  # Small lot
        features.append(1 if 4 <= record['lot_size'] <= 7 else 0)  # Medium lot
        features.append(1 if 8 <= record['lot_size'] <= 12 else 0)  # Large lot
        features.append(1 if record['lot_size'] > 12 else 0)  # Very large lot

        # Series popularity proxy (series with more lots are likely more popular)
        # This will be same for all lots in a series, but helps model learn series value
        features.append(record['series_id'])  # Will be normalized during scaling

        # Completion percentage features (based on analysis showing U-shaped pricing curve)
        completion_pct = record['completion_pct']
        features.append(completion_pct)  # Linear completion percentage
        features.append(completion_pct ** 2)  # Quadratic term to capture U-shaped curve

        # Near-complete indicator (90%+ completion gets premium pricing)
        is_near_complete = 1 if completion_pct >= 0.9 else 0
        features.append(is_near_complete)

        # Complete set marketing premium (interaction term)
        # Analysis showed 42% premium when marketed as "complete set" vs not
        complete_set_premium = 1 if (record['is_complete_set'] and is_near_complete) else 0
        features.append(complete_set_premium)

        # Inferred series size (helps model understand scale)
        features.append(record['inferred_series_size'])

        X.append(features)

    return np.array(X)


def get_feature_names():
    """Return list of feature names in order."""
    return [
        'lot_size',
        'is_complete_set',
        'is_sold',
        'price_per_book',
        'condition_score',
        'is_small_lot',
        'is_medium_lot',
        'is_large_lot',
        'is_very_large_lot',
        'series_id',
        'completion_pct',
        'completion_pct_squared',
        'is_near_complete',
        'complete_set_premium',
        'inferred_series_size',
    ]


def remove_outliers(X, y, threshold=3.0):
    """Remove outliers using Z-score method."""
    z_scores = np.abs((y - np.mean(y)) / np.std(y))
    mask = z_scores < threshold
    return X[mask], y[mask]


def train_lot_model():
    """Train and save lot specialist model."""
    print("=" * 80)
    print("TRAINING LOT SPECIALIST MODEL")
    print("=" * 80)

    # Load data
    print("\n1. Loading lot training data...")
    records, targets = load_lot_training_data()

    print(f"\n   Loaded {len(records)} lot listings")
    print(f"   Target range: ${min(targets):.2f} - ${max(targets):.2f}")
    print(f"   Target mean: ${np.mean(targets):.2f}")
    print(f"   Target median: ${np.median(targets):.2f}")

    # Extract features
    print("\n2. Extracting lot-specific features...")
    X = extract_lot_features(records)
    y = targets

    feature_names = get_feature_names()
    print(f"   Features extracted: {len(feature_names)} features")

    # Remove outliers
    print("\n3. Removing outliers...")
    X_clean, y_clean = remove_outliers(X, y)
    print(f"   Removed {len(X) - len(X_clean)} outliers ({(len(X) - len(X_clean)) / len(X) * 100:.1f}%)")
    print(f"   Training samples: {len(X_clean)}")

    # Split data
    print("\n4. Splitting train/test (80/20)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X_clean, y_clean, test_size=0.2, random_state=42
    )
    print(f"   Train: {len(X_train)} samples")
    print(f"   Test:  {len(X_test)} samples")

    # Scale features
    print("\n5. Scaling features...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train model with hyperparameter tuning
    print("\n6. Training XGBoost model with hyperparameter tuning...")

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

    random_search.fit(X_train_scaled, y_train)
    model = random_search.best_estimator_
    best_params = random_search.best_params_
    cv_mae = -random_search.best_score_

    print("\n   Best hyperparameters found:")
    for param, value in sorted(best_params.items()):
        print(f"    {param:20s} = {value}")
    print(f"    Best CV MAE: ${cv_mae:.2f}")
    print("\n   Training complete!")

    # Evaluate
    print("\n7. Evaluating model...")
    y_train_pred = model.predict(X_train_scaled)
    y_test_pred = model.predict(X_test_scaled)

    train_mae = mean_absolute_error(y_train, y_train_pred)
    test_mae = mean_absolute_error(y_test, y_test_pred)
    train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
    test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
    train_r2 = r2_score(y_train, y_train_pred)
    test_r2 = r2_score(y_test, y_test_pred)

    print("\n" + "=" * 80)
    print("LOT MODEL PERFORMANCE")
    print("=" * 80)
    print(f"\nTraining Metrics:")
    print(f"  MAE:  ${train_mae:.2f}")
    print(f"  RMSE: ${train_rmse:.2f}")
    print(f"  R²:   {train_r2:.3f}")

    print(f"\nTest Metrics:")
    print(f"  MAE:  ${test_mae:.2f}")
    print(f"  RMSE: ${test_rmse:.2f}")
    print(f"  R²:   {test_r2:.3f}")

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
    model_path = model_dir / 'lot_model.pkl'
    joblib.dump(model, model_path)
    print(f"✓ Saved model: {model_path}")

    # Save scaler
    scaler_path = model_dir / 'lot_scaler.pkl'
    joblib.dump(scaler, scaler_path)
    print(f"✓ Saved scaler: {scaler_path}")

    # Save metadata
    metadata = {
        'platform': 'lot',
        'model_type': 'XGBRegressor',
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
        'cv_mae': float(cv_mae),
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

    metadata_path = model_dir / 'lot_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Saved metadata: {metadata_path}")

    print("\n" + "=" * 80)
    print("LOT MODEL TRAINING COMPLETE")
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
    train_lot_model()
