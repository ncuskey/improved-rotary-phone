#!/usr/bin/env python3
"""
Train specialist model for signed/autographed books.

This model learns the premium (or discount) associated with signed copies.
It's trained only on books where signed=True to capture the unique pricing
dynamics of autographed books.
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import warnings
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

from isbn_lot_optimizer.ml.feature_extractor import FeatureExtractor
from scripts.stacking.data_loader import load_unified_cross_platform_data

warnings.filterwarnings('ignore')


def main():
    print("=" * 70)
    print("Training Signed Books Specialist Model")
    print("=" * 70)
    print()

    # Load all training data
    print("Loading training data...")
    all_books, all_targets = load_unified_cross_platform_data()
    print(f"  Total books loaded: {len(all_books)}")

    # Filter for signed books only
    signed_books = []
    signed_targets = []
    for book, target in zip(all_books, all_targets):
        # Check book level first (data_loader puts it there), then metadata
        is_signed = book.get('signed', False) or book.get('metadata', {}).get('signed', False)
        if is_signed:
            signed_books.append(book)
            signed_targets.append(target)

    print(f"  Signed books: {len(signed_books)}")
    print()

    if len(signed_books) < 50:
        print("⚠️  Not enough signed books for training (need at least 50)")
        print(f"   Found: {len(signed_books)}")
        print("   Collect more signed book data first")
        return

    # Extract features
    print("Extracting features from signed books...")
    extractor = FeatureExtractor()
    X = []
    y = []

    for book, target in zip(signed_books, signed_targets):
        try:
            features = extractor.extract(book)
            X.append(features)
            y.append(target)
        except Exception as e:
            print(f"  Warning: Failed to extract features: {e}")
            continue

    X = pd.DataFrame(X)
    y = np.array(y)

    print(f"  Feature matrix: {X.shape}")
    print(f"  Target vector: {y.shape}")
    print(f"  Price range: ${y.min():.2f} - ${y.max():.2f}")
    print(f"  Mean price: ${y.mean():.2f}")
    print(f"  Median price: ${np.median(y):.2f}")
    print()

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    print(f"Train samples: {len(X_train)}")
    print(f"Test samples: {len(X_test)}")
    print()

    # Train model
    print("Training XGBoost model...")
    model = XGBRegressor(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        random_state=42,
        n_jobs=-1,
    )

    model.fit(X_train, y_train)

    # Evaluate
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)

    train_mae = mean_absolute_error(y_train, y_pred_train)
    test_mae = mean_absolute_error(y_test, y_pred_test)
    train_rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
    test_rmse = np.sqrt(mean_squared_error(y_test, y_pred_test))
    test_r2 = r2_score(y_test, y_pred_test)

    print()
    print("=" * 70)
    print("Model Performance")
    print("=" * 70)
    print(f"Train MAE: ${train_mae:.2f}")
    print(f"Test MAE:  ${test_mae:.2f}")
    print(f"Train RMSE: ${train_rmse:.2f}")
    print(f"Test RMSE:  ${test_rmse:.2f}")
    print(f"Test R²:    {test_r2:.3f}")
    print()

    # Feature importance
    feature_importance = dict(zip(X.columns, model.feature_importances_))
    top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:10]

    print("Top 10 Important Features:")
    for feat, importance in top_features:
        print(f"  {feat:40s} {importance:.4f}")
    print()

    # Save model
    model_dir = Path.home() / "ISBN" / "isbn_lot_optimizer" / "models" / "stacking"
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "signed_model.pkl"
    scaler_path = model_dir / "signed_scaler.pkl"  # Placeholder for consistency
    metadata_path = model_dir / "signed_metadata.json"

    print(f"Saving model to {model_path}...")
    joblib.dump(model, model_path)

    # Save identity scaler (no scaling for now)
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    scaler.fit(X_train)  # Fit but won't use for now
    joblib.dump(scaler, scaler_path)

    # Save metadata
    metadata = {
        "version": "v1_signed_specialist",
        "model_type": "XGBRegressor",
        "train_date": datetime.now().isoformat(),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "train_mae": float(train_mae),
        "test_mae": float(test_mae),
        "train_rmse": float(train_rmse),
        "test_rmse": float(test_rmse),
        "test_r2": float(test_r2),
        "feature_importance": {k: float(v) for k, v in feature_importance.items()},
        "features": list(X.columns),
    }

    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"  Model: {model_path}")
    print(f"  Scaler: {scaler_path}")
    print(f"  Metadata: {metadata_path}")
    print()
    print("✅ Signed specialist model training complete!")
    print()


if __name__ == "__main__":
    main()
