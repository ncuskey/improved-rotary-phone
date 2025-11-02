#!/usr/bin/env python3
"""
Train Amazon specialist model for stacking ensemble.

Trains a GradientBoostingRegressor optimized for Amazon pricing prediction
using Amazon-specific features (sales rank, book attributes, categories).
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import joblib
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.stacking.data_loader import load_platform_training_data
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


def extract_features(records, targets, extractor):
    """Extract Amazon-specific features from records."""
    X = []
    y = []
    completeness_scores = []

    for record, target in zip(records, targets):
        metadata, market, bookscouter = create_simple_objects(record)

        features = extractor.extract_for_platform(
            platform='amazon',
            metadata=metadata,
            market=market,
            bookscouter=bookscouter,
            condition=record.get('condition', 'Good'),
            abebooks=record.get('abebooks')
        )

        X.append(features.values)
        y.append(target)
        completeness_scores.append(features.completeness)

    return np.array(X), np.array(y), completeness_scores


def remove_outliers(X, y, threshold=3.0):
    """Remove outliers using Z-score method."""
    z_scores = np.abs((y - np.mean(y)) / np.std(y))
    mask = z_scores < threshold
    return X[mask], y[mask]


def train_amazon_model():
    """Train and save Amazon specialist model."""
    print("=" * 80)
    print("TRAINING AMAZON SPECIALIST MODEL")
    print("=" * 80)

    # Load data
    print("\n1. Loading Amazon training data...")
    platform_data = load_platform_training_data()
    amazon_records, amazon_targets = platform_data['amazon']

    print(f"\n   Loaded {len(amazon_records)} Amazon books")
    print(f"   Target range: ${min(amazon_targets):.2f} - ${max(amazon_targets):.2f}")
    print(f"   Target mean: ${np.mean(amazon_targets):.2f}")

    # Extract features
    print("\n2. Extracting Amazon-specific features...")
    extractor = PlatformFeatureExtractor()
    X, y, completeness = extract_features(amazon_records, amazon_targets, extractor)

    feature_names = PlatformFeatureExtractor.get_platform_feature_names('amazon')
    print(f"   Features extracted: {len(feature_names)} features")
    print(f"   Average completeness: {np.mean(completeness):.1%}")

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

    # Train model
    print("\n6. Training GradientBoostingRegressor...")
    model = GradientBoostingRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_split=6,
        min_samples_leaf=3,
        random_state=42,
        loss='squared_error',
        verbose=0
    )

    model.fit(X_train_scaled, y_train)
    print("   Training complete!")

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
    print("AMAZON MODEL PERFORMANCE")
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
    model_path = model_dir / 'amazon_model.pkl'
    joblib.dump(model, model_path)
    print(f"✓ Saved model: {model_path}")

    # Save scaler
    scaler_path = model_dir / 'amazon_scaler.pkl'
    joblib.dump(scaler, scaler_path)
    print(f"✓ Saved scaler: {scaler_path}")

    # Save metadata
    metadata = {
        'platform': 'amazon',
        'model_type': 'GradientBoostingRegressor',
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
        'feature_importance': {name: float(imp) for name, imp in importance.items()},
        'top_features': [(name, float(imp)) for name, imp in top_features],
        'trained_at': datetime.now().isoformat(),
    }

    metadata_path = model_dir / 'amazon_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Saved metadata: {metadata_path}")

    print("\n" + "=" * 80)
    print("AMAZON MODEL TRAINING COMPLETE")
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
    train_amazon_model()
