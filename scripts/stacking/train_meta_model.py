#!/usr/bin/env python3
"""
Train meta-model for stacking ensemble.

Trains a Ridge regression model to optimally combine predictions from
eBay, AbeBooks, and Amazon specialist models.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import joblib
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def train_meta_model():
    """Train and save Ridge regression meta-model."""
    print("=" * 80)
    print("TRAINING STACKING META-MODEL")
    print("=" * 80)

    # Load OOF predictions
    print("\n1. Loading out-of-fold predictions...")
    model_dir = Path(__file__).parent.parent.parent / 'isbn_lot_optimizer' / 'models' / 'stacking'
    oof_path = model_dir / 'oof_predictions.pkl'

    oof_data = joblib.load(oof_path)
    meta_X = oof_data['meta_X']
    meta_y = oof_data['meta_y']

    print(f"   Loaded {len(meta_X)} samples")
    print(f"   Features: {meta_X.shape[1]} (eBay, AbeBooks, Amazon predictions)")
    print(f"   Target range: ${meta_y.min():.2f} - ${meta_y.max():.2f}")
    print(f"   Target mean: ${meta_y.mean():.2f}")

    # Display feature statistics
    print("\n2. Feature statistics:")
    feature_names = ['eBay', 'AbeBooks', 'Amazon']
    for i, name in enumerate(feature_names):
        non_zero = np.count_nonzero(meta_X[:, i])
        coverage = non_zero / len(meta_X) * 100
        mean_val = meta_X[meta_X[:, i] > 0, i].mean() if non_zero > 0 else 0
        print(f"   {name:10s}: {non_zero:4d} / {len(meta_X)} ({coverage:5.1f}%), mean ${mean_val:.2f}")

    # Split data
    print("\n3. Splitting train/test (80/20)...")
    X_train, X_test, y_train, y_test = train_test_split(
        meta_X, meta_y, test_size=0.2, random_state=42
    )
    print(f"   Train: {len(X_train)} samples")
    print(f"   Test:  {len(X_test)} samples")

    # Train with cross-validation to find optimal alpha
    print("\n4. Training Ridge regression with CV for alpha selection...")
    alphas = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

    ridge_cv = RidgeCV(alphas=alphas, cv=5, scoring='neg_mean_absolute_error')
    ridge_cv.fit(X_train, y_train)

    best_alpha = ridge_cv.alpha_
    print(f"   Best alpha: {best_alpha}")

    # Train final model with best alpha
    print("\n5. Training final Ridge model...")
    model = Ridge(alpha=best_alpha, random_state=42)
    model.fit(X_train, y_train)

    # Display coefficients
    print("\n6. Model coefficients (weights):")
    for name, coef in zip(feature_names, model.coef_):
        print(f"   {name:10s}: {coef:.4f}")
    print(f"   Intercept: {model.intercept_:.4f}")

    # Evaluate
    print("\n7. Evaluating meta-model...")
    y_train_pred = model.predict(X_train)
    y_test_pred = model.predict(X_test)

    train_mae = mean_absolute_error(y_train, y_train_pred)
    test_mae = mean_absolute_error(y_test, y_test_pred)
    train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
    test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
    train_r2 = r2_score(y_train, y_train_pred)
    test_r2 = r2_score(y_test, y_test_pred)

    print("\n" + "=" * 80)
    print("META-MODEL PERFORMANCE")
    print("=" * 80)
    print(f"\nTraining Metrics:")
    print(f"  MAE:  ${train_mae:.2f}")
    print(f"  RMSE: ${train_rmse:.2f}")
    print(f"  R²:   {train_r2:.3f}")

    print(f"\nTest Metrics:")
    print(f"  MAE:  ${test_mae:.2f}")
    print(f"  RMSE: ${test_rmse:.2f}")
    print(f"  R²:   {test_r2:.3f}")

    # Comparison with individual models (using test set)
    print("\n" + "=" * 80)
    print("COMPARISON: META-MODEL VS INDIVIDUAL SPECIALISTS")
    print("=" * 80)

    # Individual model MAE on test set
    ebay_test_mae = mean_absolute_error(y_test, X_test[:, 0])
    abebooks_test_mae = mean_absolute_error(y_test, X_test[:, 1])
    amazon_test_mae = mean_absolute_error(y_test, X_test[:, 2])

    print(f"\nTest MAE comparison:")
    print(f"  eBay specialist:      ${ebay_test_mae:.2f}")
    print(f"  AbeBooks specialist:  ${abebooks_test_mae:.2f}")
    print(f"  Amazon specialist:    ${amazon_test_mae:.2f}")
    print(f"  Meta-model (stacked): ${test_mae:.2f}")

    # Best individual model
    best_individual_mae = min(ebay_test_mae, abebooks_test_mae, amazon_test_mae)
    improvement = (best_individual_mae - test_mae) / best_individual_mae * 100

    print(f"\nImprovement over best individual model:")
    print(f"  Best individual: ${best_individual_mae:.2f}")
    print(f"  Stacked:         ${test_mae:.2f}")
    if improvement > 0:
        print(f"  Improvement:     {improvement:.1f}% better!")
    else:
        print(f"  Change:          {-improvement:.1f}% worse")

    # Save model
    print("\n" + "=" * 80)
    print("SAVING META-MODEL")
    print("=" * 80)

    model_path = model_dir / 'meta_model.pkl'
    joblib.dump(model, model_path)
    print(f"✓ Saved model: {model_path}")

    # Save metadata
    metadata = {
        'model_type': 'Ridge',
        'alpha': float(best_alpha),
        'n_features': 3,
        'feature_names': feature_names,
        'coefficients': {name: float(coef) for name, coef in zip(feature_names, model.coef_)},
        'intercept': float(model.intercept_),
        'training_samples': len(X_train),
        'test_samples': len(X_test),
        'train_mae': float(train_mae),
        'test_mae': float(test_mae),
        'train_rmse': float(train_rmse),
        'test_rmse': float(test_rmse),
        'train_r2': float(train_r2),
        'test_r2': float(test_r2),
        'ebay_test_mae': float(ebay_test_mae),
        'abebooks_test_mae': float(abebooks_test_mae),
        'amazon_test_mae': float(amazon_test_mae),
        'improvement_pct': float(improvement),
        'trained_at': datetime.now().isoformat(),
    }

    metadata_path = model_dir / 'meta_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Saved metadata: {metadata_path}")

    print("\n" + "=" * 80)
    print("META-MODEL TRAINING COMPLETE")
    print("=" * 80)
    print(f"\nStacking ensemble:")
    print(f"  Test MAE: ${test_mae:.2f}")
    print(f"  Test R²:  {test_r2:.3f}")
    print(f"  Improvement: {improvement:.1f}% over best specialist")
    print("=" * 80 + "\n")

    return {
        'model': model,
        'metadata': metadata,
        'test_mae': test_mae,
        'test_r2': test_r2,
        'improvement': improvement,
    }


if __name__ == "__main__":
    train_meta_model()
