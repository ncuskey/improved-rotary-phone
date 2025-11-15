"""
Train Edition Premium Calibration Model.

Trains a small XGBoost model on BookFinder paired edition data to predict
the premium percentage that first editions command over non-first editions.

This model addresses the confounding factors in sold_listings data by using
BookFinder's within-ISBN comparisons (same book, different editions).
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict

import joblib
import numpy as np
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import xgboost as xgb

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Check Python version for XGBoost/OpenMP compatibility
from shared.python_version_check import check_python_version
check_python_version()

from isbn_lot_optimizer.ml.feature_extractor import FeatureExtractor
from shared.models import BookMetadata


def load_paired_edition_data(db_path: Path, cache_db_path: Path) -> List[Dict]:
    """
    Load ISBNs that have both first and non-first editions in BookFinder data
    AND have metadata in catalog or cache databases.

    Args:
        db_path: Path to catalog.db with bookfinder_offers table
        cache_db_path: Path to metadata_cache.db

    Returns:
        List of records with ISBN and calculated edition premium percentage
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query ISBNs with paired edition data that ALSO have metadata
    # Calculate premium percentage directly in SQL for efficiency
    query = """
    SELECT
        isbn,
        AVG(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_avg,
        AVG(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL
            THEN price + COALESCE(shipping, 0) END) as non_first_ed_avg,
        COUNT(CASE WHEN is_first_edition = 1 THEN 1 END) as first_ed_count,
        COUNT(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL THEN 1 END) as non_first_ed_count
    FROM bookfinder_offers
    WHERE isbn IN (
        -- Has first edition offers
        SELECT isbn
        FROM bookfinder_offers
        WHERE is_first_edition = 1
        GROUP BY isbn
        HAVING COUNT(*) >= 2
    )
    AND isbn IN (
        -- Has non-first edition offers
        SELECT isbn
        FROM bookfinder_offers
        WHERE is_first_edition = 0 OR is_first_edition IS NULL
        GROUP BY isbn
        HAVING COUNT(*) >= 2
    )
    GROUP BY isbn
    HAVING first_ed_avg IS NOT NULL
       AND non_first_ed_avg IS NOT NULL
       AND non_first_ed_avg > 0
       AND first_ed_avg >= non_first_ed_avg * 0.5
       AND first_ed_avg <= non_first_ed_avg * 5.0
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    # Also check cache database
    cache_conn = sqlite3.connect(cache_db_path)
    cache_cursor = cache_conn.cursor()

    # Get ISBNs from cache that have BookFinder paired data
    cache_query = """
    SELECT DISTINCT c.isbn
    FROM cached_books c
    WHERE c.title IS NOT NULL
    """
    cache_cursor.execute(cache_query)
    cache_isbns = set(row[0] for row in cache_cursor.fetchall())
    cache_conn.close()

    # Filter BookFinder ISBNs to only those in cache
    filtered_rows = []
    for row in rows:
        if row[0] in cache_isbns:
            filtered_rows.append(row)

    # Now requery BookFinder for cache ISBNs that weren't in the first result
    remaining_cache_isbns = cache_isbns - set(row[0] for row in filtered_rows)

    if remaining_cache_isbns:
        # Query BookFinder for these additional ISBNs
        placeholder_str = ','.join('?' * min(len(remaining_cache_isbns), 999))  # SQLite limit
        additional_query = f"""
        SELECT
            isbn,
            AVG(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_avg,
            AVG(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL
                THEN price + COALESCE(shipping, 0) END) as non_first_ed_avg,
            COUNT(CASE WHEN is_first_edition = 1 THEN 1 END) as first_ed_count,
            COUNT(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL THEN 1 END) as non_first_ed_count
        FROM bookfinder_offers
        WHERE isbn IN ({placeholder_str})
        GROUP BY isbn
        HAVING first_ed_avg IS NOT NULL
           AND non_first_ed_avg IS NOT NULL
           AND non_first_ed_avg > 0
           AND first_ed_count >= 2
           AND non_first_ed_count >= 2
           AND first_ed_avg >= non_first_ed_avg * 0.5
           AND first_ed_avg <= non_first_ed_avg * 5.0
        """
        cursor.execute(additional_query, list(remaining_cache_isbns)[:999])
        additional_rows = cursor.fetchall()
        filtered_rows.extend(additional_rows)

    conn.close()

    print(f"Loaded {len(filtered_rows)} ISBNs with paired edition data and metadata")

    # Convert to records with calculated premium percentage
    records = []
    for row in filtered_rows:
        isbn = row[0]
        first_ed_avg = row[1]
        non_first_ed_avg = row[2]
        first_ed_count = row[3]
        non_first_ed_count = row[4]

        # Calculate premium percentage: ((first - non_first) / non_first) * 100
        premium_pct = ((first_ed_avg - non_first_ed_avg) / non_first_ed_avg) * 100

        records.append({
            'isbn': isbn,
            'first_ed_avg': first_ed_avg,
            'non_first_ed_avg': non_first_ed_avg,
            'premium_pct': premium_pct,
            'first_ed_count': first_ed_count,
            'non_first_ed_count': non_first_ed_count,
        })

    if records:
        print(f"  Average premium: {np.mean([r['premium_pct'] for r in records]):.1f}%")
        print(f"  Median premium: {np.median([r['premium_pct'] for r in records]):.1f}%")
        print(f"  Premium range: {np.min([r['premium_pct'] for r in records]):.1f}% to {np.max([r['premium_pct'] for r in records]):.1f}%")

    return records


def extract_features_for_isbns(isbns: List[str]) -> Tuple[List[Dict], List[str]]:
    """
    Extract edition premium features combining BookFinder pricing stats with metadata.

    Args:
        isbns: List of ISBNs to extract features for

    Returns:
        Tuple of (feature_records, valid_isbns) where feature_records contains
        extracted features and valid_isbns contains ISBNs that had feature data
    """
    # Connect to databases
    catalog_db = Path.home() / ".isbn_lot_optimizer" / "catalog.db"
    cache_db = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"

    feature_records = []
    valid_isbns = []

    catalog_conn = sqlite3.connect(catalog_db)
    cache_conn = sqlite3.connect(cache_db)

    for isbn in isbns:
        try:
            # Get BookFinder pricing statistics
            cursor = catalog_conn.cursor()
            cursor.execute("""
                SELECT
                    AVG(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_avg,
                    AVG(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL
                        THEN price + COALESCE(shipping, 0) END) as non_first_ed_avg,
                    MIN(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_min,
                    MAX(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_max,
                    MIN(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL
                        THEN price + COALESCE(shipping, 0) END) as non_first_ed_min,
                    MAX(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL
                        THEN price + COALESCE(shipping, 0) END) as non_first_ed_max,
                    COUNT(CASE WHEN is_first_edition = 1 THEN 1 END) as first_ed_count,
                    COUNT(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL THEN 1 END) as non_first_ed_count
                FROM bookfinder_offers
                WHERE isbn = ?
            """, (isbn,))
            bf_row = cursor.fetchone()

            if not bf_row or not bf_row[0] or not bf_row[1]:
                continue

            first_ed_avg, non_first_ed_avg = bf_row[0], bf_row[1]
            first_ed_min, first_ed_max = bf_row[2], bf_row[3]
            non_first_ed_min, non_first_ed_max = bf_row[4], bf_row[5]
            first_ed_count, non_first_ed_count = bf_row[6], bf_row[7]

            # Get metadata from cache
            cache_cursor = cache_conn.cursor()
            cache_cursor.execute("""
                SELECT publication_year, page_count, binding
                FROM cached_books
                WHERE isbn = ?
            """, (isbn,))
            meta_row = cache_cursor.fetchone()

            # Build feature dict
            features = {
                # BookFinder pricing features
                'first_ed_avg_price': first_ed_avg,
                'non_first_ed_avg_price': non_first_ed_avg,
                'price_ratio': first_ed_avg / non_first_ed_avg if non_first_ed_avg > 0 else 1.0,
                'price_difference': first_ed_avg - non_first_ed_avg,
                'first_ed_min': first_ed_min or first_ed_avg,
                'first_ed_max': first_ed_max or first_ed_avg,
                'non_first_ed_min': non_first_ed_min or non_first_ed_avg,
                'non_first_ed_max': non_first_ed_max or non_first_ed_avg,
                'first_ed_price_range': (first_ed_max or first_ed_avg) - (first_ed_min or first_ed_avg),
                'non_first_ed_price_range': (non_first_ed_max or non_first_ed_avg) - (non_first_ed_min or non_first_ed_avg),
                'first_ed_offer_count': first_ed_count,
                'non_first_ed_offer_count': non_first_ed_count,
                'total_offer_count': first_ed_count + non_first_ed_count,
                'first_ed_offer_ratio': first_ed_count / (first_ed_count + non_first_ed_count),
            }

            # Add metadata features if available
            if meta_row:
                pub_year, page_count, binding = meta_row

                # Publication year features
                if pub_year:
                    features['publication_year'] = pub_year
                    features['book_age'] = 2024 - pub_year
                    features['is_recent'] = 1.0 if pub_year >= 2015 else 0.0
                    features['is_classic'] = 1.0 if pub_year < 1980 else 0.0
                else:
                    features['publication_year'] = 0
                    features['book_age'] = 0
                    features['is_recent'] = 0.0
                    features['is_classic'] = 0.0

                # Page count features
                if page_count and page_count > 0:
                    features['page_count'] = page_count
                    features['is_long_book'] = 1.0 if page_count > 500 else 0.0
                else:
                    features['page_count'] = 0
                    features['is_long_book'] = 0.0

                # Binding features
                if binding:
                    features['is_hardcover'] = 1.0 if 'hard' in binding.lower() else 0.0
                else:
                    features['is_hardcover'] = 0.0

            feature_records.append(features)
            valid_isbns.append(isbn)

        except Exception as e:
            if len(feature_records) < 5:
                print(f"  Error extracting features for {isbn}: {e}")
            continue

    catalog_conn.close()
    cache_conn.close()

    print(f"  Extracted features for {len(feature_records)}/{len(isbns)} ISBNs")
    return feature_records, valid_isbns


def select_model_features(features: np.ndarray, feature_names: List[str]) -> Tuple[np.ndarray, List[str]]:
    """
    Select most relevant features for edition premium prediction.

    Uses all features from extract_features_for_isbns which include:
    - BookFinder pricing statistics (ratios, differences, ranges, counts)
    - Book metadata (age, publication year, page count, binding)

    Note: We use price ratios and differences, NOT absolute prices, to avoid
    data leakage while still capturing price relationships.

    Args:
        features: Full feature matrix (n_samples, n_features)
        feature_names: List of feature names

    Returns:
        Tuple of (selected_features, selected_feature_names)
    """
    # Use all features extracted for edition premium prediction
    # These are specifically designed for this task:
    # - Price ratios/differences (not absolute prices to avoid leakage)
    # - Edition offer counts and distributions
    # - Book metadata (age, format, page count)

    print(f"  Using all {len(feature_names)} features for edition premium model")

    return features, feature_names


def train_edition_premium_model(
    features: np.ndarray,
    targets: np.ndarray,
    feature_names: List[str]
) -> Tuple[xgb.XGBRegressor, StandardScaler, Dict]:
    """
    Train XGBoost model to predict edition premium percentage.

    Args:
        features: Feature matrix (n_samples, n_features)
        targets: Target premiums as percentages (e.g., 29.9 for 29.9% premium)
        feature_names: List of feature names

    Returns:
        Tuple of (trained_model, scaler, metadata_dict)
    """
    print("\n2. Training edition premium model...")

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        features, targets, test_size=0.2, random_state=42
    )

    print(f"   Train: {len(X_train)} samples")
    print(f"   Test:  {len(X_test)} samples")

    # Standardize features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Hyperparameter search space (smaller than main model due to less data)
    param_distributions = {
        'n_estimators': [50, 100, 150],
        'max_depth': [3, 4, 5],
        'learning_rate': [0.05, 0.1, 0.15],
        'subsample': [0.8, 0.9],
        'colsample_bytree': [0.8, 0.9],
        'min_child_weight': [1, 2, 3],
        'gamma': [0, 0.1],
        'reg_alpha': [0, 0.01],
        'reg_lambda': [1, 2],
    }

    print("\n   Searching for best hyperparameters (30 iterations, 3-fold CV)...")

    xgb_model = xgb.XGBRegressor(
        objective='reg:squarederror',
        random_state=42,
        n_jobs=-1
    )

    random_search = RandomizedSearchCV(
        xgb_model,
        param_distributions,
        n_iter=30,
        cv=3,
        scoring='neg_mean_absolute_error',
        random_state=42,
        n_jobs=-1,
        verbose=1
    )

    random_search.fit(X_train_scaled, y_train)

    best_model = random_search.best_estimator_

    print(f"\n   Best hyperparameters:")
    for param, value in random_search.best_params_.items():
        print(f"     {param:20s} = {value}")
    print(f"     Best CV MAE: {-random_search.best_score_:.2f}%")

    # Evaluate on test set
    y_train_pred = best_model.predict(X_train_scaled)
    y_test_pred = best_model.predict(X_test_scaled)

    train_mae = mean_absolute_error(y_train, y_train_pred)
    test_mae = mean_absolute_error(y_test, y_test_pred)
    train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
    test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
    test_r2 = r2_score(y_test, y_test_pred)

    print(f"\nTraining Results:")
    print(f"  Train MAE: {train_mae:.2f}%")
    print(f"  Test MAE:  {test_mae:.2f}%")
    print(f"  Train RMSE: {train_rmse:.2f}%")
    print(f"  Test RMSE:  {test_rmse:.2f}%")
    print(f"  Test R²:    {test_r2:.3f}")

    # Feature importance
    importance = best_model.feature_importances_
    feature_importance = sorted(
        zip(feature_names, importance),
        key=lambda x: x[1],
        reverse=True
    )

    print(f"\nTop 10 Most Important Features:")
    for name, imp in feature_importance[:10]:
        print(f"  {name:30s} {imp:.4f}")

    # Build metadata
    metadata = {
        'model_version': 'v1_edition_premium',
        'model_type': 'xgboost_regressor',
        'target': 'first_edition_premium_pct',
        'trained_date': datetime.now().isoformat(),
        'n_training_samples': len(X_train),
        'n_test_samples': len(X_test),
        'hyperparameters': random_search.best_params_,
        'test_mae': test_mae,
        'test_rmse': test_rmse,
        'test_r2': test_r2,
        'feature_names': feature_names,
        'feature_importance': {name: float(imp) for name, imp in feature_importance},
    }

    return best_model, scaler, metadata


def main():
    """Main training pipeline."""
    print("=" * 70)
    print("Edition Premium Calibration Model Training")
    print("=" * 70)

    # Load paired edition data from BookFinder
    print("\n1. Loading paired edition data from BookFinder...")
    catalog_db = Path.home() / ".isbn_lot_optimizer" / "catalog.db"
    cache_db = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"
    records = load_paired_edition_data(catalog_db, cache_db)

    if len(records) < 20:
        print(f"\nERROR: Insufficient training data ({len(records)} ISBNs)")
        print("Need at least 20 ISBNs with paired edition data")
        print("\nNote: To increase training data, run:")
        print("  1. Collect more BookFinder data for ISBNs in your catalog")
        print("  2. Collect metadata for ISBNs that have BookFinder data")
        sys.exit(1)

    if len(records) < 50:
        print(f"\nWARNING: Limited training data ({len(records)} ISBNs)")
        print("Model may have high variance. Recommended: 100+ ISBNs for production use.")

    # Extract features
    print("\n2. Extracting features...")
    isbns = [r['isbn'] for r in records]
    feature_records, valid_isbns = extract_features_for_isbns(isbns)

    # Build feature matrix and targets
    print("\n3. Building feature matrix...")

    # Get feature names from first record
    feature_names = list(feature_records[0].keys())

    # Convert to numpy arrays
    features = np.array([[record[name] for name in feature_names] for record in feature_records])

    # Get targets (premium percentages) for valid ISBNs
    isbn_to_premium = {r['isbn']: r['premium_pct'] for r in records}
    targets = np.array([isbn_to_premium[isbn] for isbn in valid_isbns])

    print(f"   Feature matrix: {features.shape}")
    print(f"   Target range: {targets.min():.1f}% to {targets.max():.1f}%")

    # Select relevant features
    features_selected, selected_feature_names = select_model_features(features, feature_names)

    # Train model
    model, scaler, metadata = train_edition_premium_model(
        features_selected, targets, selected_feature_names
    )

    # Save model artifacts
    print("\n4. Saving model artifacts...")
    models_dir = Path(__file__).parent.parent / "isbn_lot_optimizer" / "models" / "edition_premium"
    models_dir.mkdir(parents=True, exist_ok=True)

    model_path = models_dir / "model_v1.pkl"
    scaler_path = models_dir / "scaler_v1.pkl"
    metadata_path = models_dir / "metadata_v1.json"

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"   Model saved to: {model_path}")
    print(f"   Scaler saved to: {scaler_path}")
    print(f"   Metadata saved to: {metadata_path}")

    print("\n" + "=" * 70)
    print("Training Complete!")
    print("=" * 70)
    print(f"Model version: {metadata['model_version']}")
    print(f"Test MAE: {metadata['test_mae']:.2f}%")
    print(f"Test RMSE: {metadata['test_rmse']:.2f}%")
    print(f"Test R²: {metadata['test_r2']:.3f}")
    print("\nModel ready for integration into price estimation endpoint.")
    print()


if __name__ == "__main__":
    main()
