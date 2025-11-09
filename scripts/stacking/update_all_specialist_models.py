#!/usr/bin/env python3
"""
Apply ML best practices fixes to all specialist stacking models.

Updates all models with:
- Log transform for target variable
- GroupKFold by ISBN to prevent leakage
- MAPE metric for interpretability
"""

import sys
from pathlib import Path

# List of specialist models to update
SPECIALIST_MODELS = [
    ('amazon', 'train_amazon_model.py'),
    ('ebay', 'train_ebay_model.py'),
    ('biblio', 'train_biblio_model.py'),
    ('alibris', 'train_alibris_model.py'),
    ('zvab', 'train_zvab_model.py'),
]


def update_imports(content: str) -> str:
    """Update imports to include training utilities."""
    # Remove old sklearn.metrics imports
    old_import = "from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score"
    if old_import in content:
        content = content.replace(old_import, "")

    # Remove train_test_split from imports
    content = content.replace(
        "from sklearn.model_selection import train_test_split, RandomizedSearchCV",
        "from sklearn.model_selection import RandomizedSearchCV"
    )

    # Add training_utils import after data_loader import
    if "from scripts.stacking.data_loader import load_platform_training_data" in content:
        content = content.replace(
            "from scripts.stacking.data_loader import load_platform_training_data\n",
            """from scripts.stacking.data_loader import load_platform_training_data
from scripts.stacking.training_utils import (
    apply_log_transform,
    inverse_log_transform,
    group_train_test_split,
    compute_metrics,
    remove_outliers
)
"""
        )

    return content


def update_extract_features(content: str) -> str:
    """Update extract_features to return ISBNs."""
    # Add isbns list
    content = content.replace(
        """    X = []
    y = []
    completeness_scores = []""",
        """    X = []
    y = []
    isbns = []
    completeness_scores = []"""
    )

    # Append ISBN in loop
    content = content.replace(
        """        X.append(features.values)
        y.append(target)
        completeness_scores.append(features.completeness)

    return np.array(X), np.array(y), completeness_scores""",
        """        X.append(features.values)
        y.append(target)
        isbns.append(record['isbn'])
        completeness_scores.append(features.completeness)

    return np.array(X), np.array(y), isbns, completeness_scores"""
    )

    return content


def remove_duplicate_outlier_function(content: str) -> str:
    """Remove duplicate outlier removal function."""
    # Remove the standalone remove_outliers function
    lines = content.split('\n')
    new_lines = []
    skip_until = None

    for i, line in enumerate(lines):
        if 'def remove_outliers(X, y, threshold' in line:
            # Skip this function and the next few lines until we hit the next function
            skip_until = 'def train_'
            continue

        if skip_until and skip_until in line:
            skip_until = None
            new_lines.append(line)
            continue

        if not skip_until:
            new_lines.append(line)

    return '\n'.join(new_lines)


def update_training_pipeline(content: str, platform: str) -> str:
    """Update the training pipeline to use GroupKFold and log transform."""

    # Update feature extraction call
    content = content.replace(
        f"    X, y, completeness = extract_features({platform}_records, {platform}_targets",
        f"    X, y, isbns, completeness = extract_features({platform}_records, {platform}_targets"
    )

    # Update outlier removal
    content = content.replace(
        "    X_clean, y_clean = remove_outliers(X, y)",
        "    X_clean, y_clean, isbns_clean = remove_outliers(X, y, isbns, threshold=3.0)"
    )

    # Replace train_test_split with GroupKFold
    old_split = """    # Split data
    print("\\n4. Splitting train/test (80/20)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X_clean, y_clean, test_size=0.2, random_state=42
    )
    print(f"   Train: {len(X_train)} samples")
    print(f"   Test:  {len(X_test)} samples")"""

    new_split = """    # Split data using GroupKFold by ISBN (prevents leakage)
    print("\\n4. Splitting train/test with GroupKFold by ISBN...")
    X_train, X_test, y_train, y_test = group_train_test_split(X_clean, y_clean, isbns_clean, n_splits=5)"""

    content = content.replace(old_split, new_split)

    # Add log transform step
    scale_section = """    # Scale features
    print("\\n5. Scaling features...")"""

    log_and_scale = """    # Apply log transform (best practice)
    print("\\n5. Applying log transform to target...")
    y_train_log, y_test_log, y_train_orig, y_test_orig = apply_log_transform(y_train, y_test)

    # Scale features
    print("\\n6. Scaling features...")"""

    content = content.replace(scale_section, log_and_scale)

    # Update step numbering for training
    content = content.replace(
        '    print("\\n6. Training XGBoost model',
        '    print("\\n7. Training XGBoost model'
    )

    # Update model fitting to use log targets
    content = content.replace(
        "    random_search.fit(X_train_scaled, y_train)",
        "    # Fit on log-transformed targets\n    random_search.fit(X_train_scaled, y_train_log)"
    )

    # Update evaluation section
    old_eval = """    # Evaluate
    print("\\n7. Evaluating model...")
    y_train_pred = model.predict(X_train_scaled)
    y_test_pred = model.predict(X_test_scaled)

    train_mae = mean_absolute_error(y_train, y_train_pred)
    test_mae = mean_absolute_error(y_test, y_test_pred)
    train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
    test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
    train_r2 = r2_score(y_train, y_train_pred)
    test_r2 = r2_score(y_test, y_test_pred)"""

    new_eval = """    # Evaluate
    print("\\n8. Evaluating model...")
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
    test_mape = test_metrics['mape']"""

    content = content.replace(old_eval, new_eval)

    # Add MAPE to output
    content = content.replace(
        """    print(f"  R²:   {test_r2:.3f}")

    # Feature importance""",
        """    print(f"  R²:   {test_r2:.3f}")
    print(f"  MAPE: {test_mape:.1f}%")

    # Feature importance"""
    )

    # Update metadata
    old_metadata_start = """    metadata = {
        'platform': '""" + platform + """',
        'model_type': 'XGBRegressor',"""

    new_metadata_start = """    metadata = {
        'platform': '""" + platform + """',
        'model_type': 'XGBRegressor',
        'version': 'v2_log_target_groupkfold',"""

    content = content.replace(old_metadata_start, new_metadata_start)

    # Add new fields to metadata
    content = content.replace(
        """        'test_r2': float(test_r2),
        'cv_mae': float(cv_mae),
        'hyperparameters':""",
        """        'test_r2': float(test_r2),
        'test_mape': float(test_mape),
        'cv_mae': float(cv_mae),
        'use_log_target': True,
        'use_groupkfold': True,
        'hyperparameters':"""
    )

    return content


def update_model_file(model_path: Path, platform: str) -> bool:
    """Update a single model file with all fixes."""
    try:
        print(f"\n{'='*80}")
        print(f"Updating {platform.upper()} model...")
        print(f"{'='*80}")

        # Read original content
        with open(model_path, 'r') as f:
            content = f.read()

        # Apply all transformations
        print("  1. Updating imports...")
        content = update_imports(content)

        print("  2. Updating extract_features to return ISBNs...")
        content = update_extract_features(content)

        print("  3. Removing duplicate outlier function...")
        content = remove_duplicate_outlier_function(content)

        print("  4. Updating training pipeline...")
        content = update_training_pipeline(content, platform)

        # Write updated content
        with open(model_path, 'w') as f:
            f.write(content)

        print(f"  ✓ Successfully updated {model_path.name}")
        return True

    except Exception as e:
        print(f"  ✗ Error updating {model_path.name}: {e}")
        return False


def main():
    """Update all specialist models."""
    script_dir = Path(__file__).parent

    print("=" * 80)
    print("UPDATING ALL SPECIALIST MODELS WITH ML BEST PRACTICES")
    print("=" * 80)
    print("\nApplying fixes:")
    print("  • Log transform for target variable")
    print("  • GroupKFold by ISBN (prevents leakage)")
    print("  • MAPE metric for interpretability")
    print()

    success_count = 0
    failed_models = []

    for platform, filename in SPECIALIST_MODELS:
        model_path = script_dir / filename

        if not model_path.exists():
            print(f"\n⚠ Warning: {filename} not found, skipping...")
            failed_models.append((platform, "File not found"))
            continue

        if update_model_file(model_path, platform):
            success_count += 1
        else:
            failed_models.append((platform, "Update failed"))

    # Summary
    print("\n" + "=" * 80)
    print("UPDATE SUMMARY")
    print("=" * 80)
    print(f"\nSuccessfully updated: {success_count}/{len(SPECIALIST_MODELS)} models")

    if failed_models:
        print("\nFailed models:")
        for platform, reason in failed_models:
            print(f"  • {platform}: {reason}")
        return 1
    else:
        print("\n✓ All specialist models successfully updated!")
        print("\nNext steps:")
        print("  1. Run each training script to verify changes")
        print("  2. Compare new metrics with previous versions")
        print("  3. Retrain meta-model with improved specialist predictions")
        return 0


if __name__ == "__main__":
    sys.exit(main())
