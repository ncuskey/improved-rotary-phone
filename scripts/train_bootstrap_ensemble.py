#!/usr/bin/env python3
"""
Train bootstrap ensemble for confidence scoring.

Trains N bootstrap models and evaluates confidence calibration.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sklearn.model_selection import train_test_split

from isbn_lot_optimizer.ml.bootstrap_ensemble import BootstrapEnsemble
from isbn_lot_optimizer.ml.training import load_training_data, extract_ml_features, remove_outliers


def train_bootstrap_ensemble():
    """Train and evaluate bootstrap ensemble."""
    print("=" * 80)
    print("BOOTSTRAP ENSEMBLE TRAINING")
    print("=" * 80)

    # Load training data
    print("\n1. Loading training data...")
    books = load_training_data()
    print(f"   Loaded {len(books)} books")

    # Extract features
    print("\n2. Extracting features...")
    X, y, completeness_scores = extract_ml_features(books)
    print(f"   Features extracted: {X.shape[1]} features")
    print(f"   Average completeness: {np.mean(completeness_scores):.1%}")

    # Remove outliers
    print("\n3. Removing outliers...")
    X_clean, y_clean = remove_outliers(X, y)
    print(f"   Removed {len(X) - len(X_clean)} outliers")
    print(f"   Training samples: {len(X_clean)}")

    # Split data
    print("\n4. Splitting train/test (80/20)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X_clean, y_clean, test_size=0.2, random_state=42
    )
    print(f"   Train: {len(X_train)} samples")
    print(f"   Test:  {len(X_test)} samples")

    # Train bootstrap ensemble
    print("\n5. Training bootstrap ensemble...")
    print(f"   Training 10 models on bootstrap samples")

    # Use best hyperparameters from Phase 2
    model_params = {
        'objective': 'reg:squarederror',
        'n_estimators': 500,
        'max_depth': 5,
        'learning_rate': 0.05,
        'subsample': 0.7,
        'colsample_bytree': 0.7,
        'min_child_weight': 1,
        'gamma': 0.1,
        'reg_alpha': 1,
        'reg_lambda': 100,
        'random_state': 42,
        'n_jobs': -1,
    }

    ensemble = BootstrapEnsemble(n_models=10, random_state=42)
    ensemble.fit(X_train, y_train, model_params)

    # Evaluate on test set
    print("\n6. Evaluating bootstrap ensemble...")
    metrics = ensemble.evaluate(X_test, y_test)

    print("\n" + "=" * 80)
    print("BOOTSTRAP ENSEMBLE PERFORMANCE")
    print("=" * 80)

    print(f"\nPrediction Metrics:")
    print(f"  MAE:  ${metrics['mae']:.2f}")
    print(f"  RMSE: ${metrics['rmse']:.2f}")

    print(f"\nConfidence Metrics:")
    print(f"  Mean prediction std:   ${metrics['mean_std']:.2f}")
    print(f"  Median prediction std: ${metrics['median_std']:.2f}")

    print(f"\nCalibration (Coverage):")
    print(f"  90% CI: {metrics['ci_90_coverage']:.1%} (expected: {metrics['expected_ci_90_coverage']:.1%})")
    print(f"  95% CI: {metrics['ci_95_coverage']:.1%} (expected: {metrics['expected_ci_95_coverage']:.1%})")

    # Check calibration quality
    ci_90_error = abs(metrics['ci_90_coverage'] - 0.90)
    ci_95_error = abs(metrics['ci_95_coverage'] - 0.95)

    print(f"\n  Calibration quality:")
    if ci_90_error < 0.05 and ci_95_error < 0.05:
        print(f"    ✓ Well calibrated (within 5% of expected)")
    elif ci_90_error < 0.10 and ci_95_error < 0.10:
        print(f"    ~ Reasonably calibrated (within 10% of expected)")
    else:
        print(f"    ✗ Poorly calibrated (>10% deviation)")

    # Show example predictions
    print("\n" + "=" * 80)
    print("EXAMPLE PREDICTIONS WITH CONFIDENCE")
    print("=" * 80)

    n_examples = 5
    for i in range(n_examples):
        result = ensemble.predict(X_test[i])
        true_price = y_test[i]

        in_90 = result.confidence_interval_90[0] <= true_price <= result.confidence_interval_90[1]
        in_95 = result.confidence_interval_95[0] <= true_price <= result.confidence_interval_95[1]

        print(f"\nExample {i + 1}:")
        print(f"  Prediction:  ${result.mean:.2f} ± ${result.std:.2f}")
        print(f"  True price:  ${true_price:.2f}")
        print(f"  90% CI:      ${result.confidence_interval_90[0]:.2f} - ${result.confidence_interval_90[1]:.2f} {'✓' if in_90 else '✗'}")
        print(f"  95% CI:      ${result.confidence_interval_95[0]:.2f} - ${result.confidence_interval_95[1]:.2f} {'✓' if in_95 else '✗'}")

    # Save ensemble
    print("\n" + "=" * 80)
    print("SAVING BOOTSTRAP ENSEMBLE")
    print("=" * 80)

    model_dir = Path(__file__).parent.parent / 'isbn_lot_optimizer' / 'models' / 'bootstrap'
    ensemble.save(model_dir)
    print(f"\n✓ Bootstrap ensemble saved to {model_dir}")

    # Save evaluation metrics
    import json
    metrics_path = model_dir / 'evaluation_metrics.json'
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"✓ Evaluation metrics saved to {metrics_path}")

    print("\n" + "=" * 80)
    print("BOOTSTRAP ENSEMBLE TRAINING COMPLETE")
    print("=" * 80)
    print(f"\nMAE: ${metrics['mae']:.2f}")
    print(f"Mean confidence std: ${metrics['mean_std']:.2f}")
    print(f"90% CI coverage: {metrics['ci_90_coverage']:.1%}")
    print("=" * 80 + "\n")

    return ensemble, metrics


if __name__ == "__main__":
    train_bootstrap_ensemble()
