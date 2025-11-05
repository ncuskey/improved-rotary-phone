"""
Train ML price estimation model.

Trains an XGBoost regression model on collected book pricing data.
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import joblib
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.ml.feature_extractor import FeatureExtractor, get_bookfinder_features, get_sold_listings_features
from shared.models import BookMetadata, EbayMarketStats, BookScouterResult
from shared.lot_detector import is_lot


def load_amazon_pricing_data(cache_db_path: Path) -> List:
    """
    Load training data from metadata_cache with amazon_pricing.

    Args:
        cache_db_path: Path to metadata_cache.db

    Returns:
        List of book records
    """
    conn = sqlite3.connect(cache_db_path)
    cursor = conn.cursor()

    # Query books from metadata cache with pricing
    query = """
    SELECT
        c.isbn,
        c.title,
        c.authors,
        c.publisher,
        c.publication_year,
        c.binding,
        c.page_count,
        p.median_used_good,
        p.median_used_very_good,
        p.offer_count
    FROM cached_books c
    JOIN amazon_pricing p ON c.isbn = p.isbn
    WHERE p.median_used_good IS NOT NULL
       OR p.median_used_very_good IS NOT NULL
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    print(f"Loaded {len(rows)} book records from metadata_cache.db")
    return rows


def load_training_data(db_path: Path, min_samples: int = 20) -> Tuple[List, List]:
    """
    Load training data from database.

    Args:
        db_path: Path to catalog.db
        min_samples: Minimum number of samples required

    Returns:
        Tuple of (book_records, target_prices)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query books with both Amazon and eBay data (including AbeBooks if available)
    query = """
    SELECT
        isbn,
        metadata_json,
        market_json,
        bookscouter_json,
        condition,
        estimated_price,
        sold_comps_median,
        json_extract(bookscouter_json, '$.amazon_lowest_price') as amazon_price,
        cover_type,
        signed,
        printing,
        abebooks_min_price,
        abebooks_avg_price,
        abebooks_seller_count,
        abebooks_condition_spread,
        abebooks_has_new,
        abebooks_has_used,
        abebooks_hardcover_premium
    FROM books
    WHERE bookscouter_json IS NOT NULL
      AND json_extract(bookscouter_json, '$.amazon_lowest_price') IS NOT NULL
      AND CAST(json_extract(bookscouter_json, '$.amazon_lowest_price') AS REAL) > 0
    ORDER BY updated_at DESC
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    print(f"Loaded {len(rows)} book records from catalog.db")

    # ALSO load from training_data.db (strategic collection)
    training_db_path = Path.home() / '.isbn_lot_optimizer' / 'training_data.db'
    if training_db_path.exists():
        conn_training = sqlite3.connect(training_db_path)
        cursor_training = conn_training.cursor()

        # Query training books - these have sold_avg_price as ground truth
        training_query = """
        SELECT
            isbn,
            metadata_json,
            market_json,
            bookscouter_json,
            'Good' as condition,
            sold_avg_price,
            sold_median_price,
            NULL as amazon_price,
            cover_type,
            signed,
            printing,
            NULL as abebooks_min_price,
            NULL as abebooks_avg_price,
            NULL as abebooks_seller_count,
            NULL as abebooks_condition_spread,
            NULL as abebooks_has_new,
            NULL as abebooks_has_used,
            NULL as abebooks_hardcover_premium
        FROM training_books
        WHERE sold_avg_price IS NOT NULL
          AND sold_count >= 5
        """

        cursor_training.execute(training_query)
        training_rows = cursor_training.fetchall()
        conn_training.close()

        print(f"Loaded {len(training_rows)} additional book records from training_data.db")
        rows.extend(training_rows)

    if len(rows) < min_samples:
        raise ValueError(f"Insufficient training data: {len(rows)} samples (need at least {min_samples})")

    # ALSO load from metadata_cache.db (Amazon pricing data)
    cache_db_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'
    if cache_db_path.exists():
        cache_rows = load_amazon_pricing_data(cache_db_path)
        print(f"Loaded {len(cache_rows)} additional book records from metadata_cache.db")

        # Convert metadata_cache format to match catalog.db format
        # Format: (isbn, metadata_json, market_json, bookscouter_json, condition, estimated_price, sold_comps_median, amazon_price, cover_type, signed, printing)
        for cache_row in cache_rows:
            isbn_cache, title, authors, publisher, pub_year, binding, page_count, price_good, price_vg, offer_count = cache_row

            # Create minimal metadata JSON
            metadata_dict = {
                'title': title,
                'authors': authors,
                'publisher': publisher,
                'published_year': pub_year,
                'page_count': page_count,
            }

            # Convert to format expected by training pipeline
            # Use price_good as target (same as training approach)
            if price_good and price_good > 0:
                rows.append((
                    isbn_cache,
                    json.dumps(metadata_dict),
                    None,  # No market_json
                    None,  # No bookscouter_json
                    'Good',  # Default condition
                    None,  # No estimated_price
                    None,  # No sold_comps_median
                    price_good,  # Use as amazon_price for target
                    binding,  # cover_type
                    False,  # not signed
                    None,  # no printing info
                    None,  # abebooks_min_price
                    None,  # abebooks_avg_price
                    None,  # abebooks_seller_count
                    None,  # abebooks_condition_spread
                    None,  # abebooks_has_new
                    None,  # abebooks_has_used
                    None,  # abebooks_hardcover_premium
                ))

    print(f"Total training samples: {len(rows)}")

    # Parse records and create target variable
    book_records = []
    target_prices = []

    for row in rows:
        isbn, metadata_json, market_json, bookscouter_json, condition, estimated_price, sold_comps_median, amazon_price, cover_type, signed, printing, \
        abebooks_min, abebooks_avg, abebooks_count, abebooks_spread, abebooks_has_new, abebooks_has_used, abebooks_hc_premium = row

        # Parse JSON fields - just use dict form instead of instantiating models
        # This avoids type errors from extra fields in database
        metadata_dict = json.loads(metadata_json) if metadata_json else None
        market_dict = json.loads(market_json) if market_json else None
        bookscouter_dict = json.loads(bookscouter_json) if bookscouter_json else None

        # Build AbeBooks dict if data exists
        abebooks_dict = None
        if abebooks_min or abebooks_avg or abebooks_count:
            abebooks_dict = {
                'abebooks_min_price': abebooks_min,
                'abebooks_avg_price': abebooks_avg,
                'abebooks_seller_count': abebooks_count,
                'abebooks_condition_spread': abebooks_spread,
                'abebooks_has_new': abebooks_has_new,
                'abebooks_has_used': abebooks_has_used,
                'abebooks_hardcover_premium': abebooks_hc_premium,
            }

        # CRITICAL: Skip lot listings to prevent contaminating training data
        # Check title in metadata_dict for lot patterns
        if metadata_dict and 'title' in metadata_dict:
            title = metadata_dict['title']
            if is_lot(title):
                # Skip this record - it's a lot listing
                continue

        # Create simplified objects with only fields we need
        class SimpleMetadata:
            def __init__(self, d, cover_type, signed, printing):
                self.page_count = d.get('page_count')
                self.published_year = d.get('published_year')
                self.average_rating = d.get('average_rating')
                self.ratings_count = d.get('ratings_count')
                self.list_price = d.get('list_price')
                self.categories = d.get('categories', [])
                # Book attributes from database
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

        metadata = SimpleMetadata(metadata_dict, cover_type, signed, printing) if metadata_dict else None
        market = SimpleMarket(market_dict) if market_dict else None
        bookscouter = SimpleBookscouter(bookscouter_dict) if bookscouter_dict else None

        # Use simpler target: eBay when available, Amazon * 0.7 otherwise
        # This reduces noise from blending mismatched price sources
        if sold_comps_median and sold_comps_median > 0:
            # Prefer eBay sold comps (actual market price)
            target = sold_comps_median
        elif amazon_price and amazon_price > 0:
            # Fall back to Amazon with eBay discount
            target = amazon_price * 0.7
        else:
            # Skip books without valid pricing data
            continue

        book_records.append({
            "isbn": isbn,
            "metadata": metadata,
            "market": market,
            "bookscouter": bookscouter,
            "condition": condition or "Good",
            "abebooks": abebooks_dict,
        })
        target_prices.append(target)

    return book_records, target_prices


def extract_features_for_training(
    book_records: List[dict],
    feature_extractor: FeatureExtractor,
    catalog_db_path: Path
) -> Tuple[np.ndarray, List[float]]:
    """
    Extract features from book records.

    Args:
        book_records: List of book record dicts
        feature_extractor: FeatureExtractor instance
        catalog_db_path: Path to catalog.db for querying BookFinder data

    Returns:
        Tuple of (feature_matrix, completeness_scores)
    """
    feature_matrix = []
    completeness_scores = []

    for record in book_records:
        # Query BookFinder aggregator data
        bookfinder_data = get_bookfinder_features(record["isbn"], str(catalog_db_path))

        # Query sold listings data (NEW)
        sold_listings_data = get_sold_listings_features(record["isbn"], str(catalog_db_path))

        features = feature_extractor.extract(
            metadata=record["metadata"],
            market=record["market"],
            bookscouter=record["bookscouter"],
            condition=record["condition"],
            abebooks=record.get("abebooks"),
            bookfinder=bookfinder_data,
            sold_listings=sold_listings_data,
        )

        feature_matrix.append(features.values)
        completeness_scores.append(features.completeness)

    return np.array(feature_matrix), completeness_scores


def train_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    model_dir: Path
) -> dict:
    """
    Train XGBoost model with hyperparameter tuning and save artifacts.

    Args:
        X_train: Training features
        y_train: Training targets
        X_test: Test features
        y_test: Test targets
        model_dir: Directory to save model files

    Returns:
        Dict with training metrics
    """
    import xgboost as xgb
    from sklearn.model_selection import RandomizedSearchCV

    print("\nTraining XGBoost model with hyperparameter tuning...")

    # Feature scaling
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

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

    # Base XGBoost model
    base_model = xgb.XGBRegressor(
        objective='reg:squarederror',
        random_state=42,
        n_jobs=-1,
        tree_method='hist',  # Faster training
    )

    # Randomized search with cross-validation
    print("  Searching for best hyperparameters (50 iterations, 3-fold CV)...")
    random_search = RandomizedSearchCV(
        estimator=base_model,
        param_distributions=param_distributions,
        n_iter=50,  # Try 50 random combinations
        cv=3,       # 3-fold cross-validation
        scoring='neg_mean_absolute_error',
        n_jobs=-1,
        random_state=42,
        verbose=1
    )

    # Fit with hyperparameter search
    random_search.fit(X_train_scaled, y_train)

    # Get best model
    model = random_search.best_estimator_
    best_params = random_search.best_params_

    print("\n  Best hyperparameters found:")
    for param, value in best_params.items():
        print(f"    {param:20s} = {value}")
    print(f"    Best CV MAE: ${-random_search.best_score_:.2f}")

    # Evaluate
    train_pred = model.predict(X_train_scaled)
    test_pred = model.predict(X_test_scaled)

    train_mae = mean_absolute_error(y_train, train_pred)
    test_mae = mean_absolute_error(y_test, test_pred)
    train_rmse = np.sqrt(mean_squared_error(y_train, train_pred))
    test_rmse = np.sqrt(mean_squared_error(y_test, test_pred))
    test_r2 = r2_score(y_test, test_pred)

    print("\nTraining Results:")
    print(f"  Train MAE: ${train_mae:.2f}")
    print(f"  Test MAE:  ${test_mae:.2f}")
    print(f"  Train RMSE: ${train_rmse:.2f}")
    print(f"  Test RMSE:  ${test_rmse:.2f}")
    print(f"  Test R²:    {test_r2:.3f}")

    # Feature importance
    feature_names = FeatureExtractor.get_feature_names()
    feature_importance = dict(zip(feature_names, model.feature_importances_))
    sorted_importance = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)

    print("\nTop 10 Most Important Features:")
    for feature, importance in sorted_importance[:10]:
        print(f"  {feature:25s}  {importance:.4f}")

    # Save model artifacts
    model_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, model_dir / "price_v1.pkl")
    joblib.dump(scaler, model_dir / "scaler_v1.pkl")

    metadata = {
        "version": "v3_xgboost_tuned",
        "model_type": "XGBRegressor",
        "train_date": datetime.now().isoformat(),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "train_mae": float(train_mae),
        "test_mae": float(test_mae),
        "train_rmse": float(train_rmse),
        "test_rmse": float(test_rmse),
        "test_r2": float(test_r2),
        "cv_mae": float(-random_search.best_score_),
        "feature_importance": {k: float(v) for k, v in feature_importance.items()},
        "hyperparameters": {k: (int(v) if isinstance(v, (np.integer, int)) else float(v))
                           for k, v in best_params.items()},
        "optimization": {
            "method": "RandomizedSearchCV",
            "n_iter": 50,
            "cv_folds": 3,
            "scoring": "neg_mean_absolute_error"
        }
    }

    with open(model_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n✓ Model saved to {model_dir}/")

    return metadata


def main():
    """Main entry point for model training."""
    import argparse

    parser = argparse.ArgumentParser(description="Train ML price estimation model")
    parser.add_argument(
        "--db",
        type=str,
        default=str(Path.home() / ".isbn_lot_optimizer" / "catalog.db"),
        help="Path to catalog.db"
    )
    parser.add_argument(
        "--model-dir",
        type=str,
        default=None,
        help="Directory to save model (default: isbn_lot_optimizer/models)"
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Test set size (default: 0.2)"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    if args.model_dir:
        model_dir = Path(args.model_dir)
    else:
        # Default to package models directory
        package_dir = Path(__file__).parent.parent / "isbn_lot_optimizer"
        model_dir = package_dir / "models"

    print("=" * 70)
    print("ML Price Estimation Model Training")
    print("=" * 70)

    # Load training data
    print("\n1. Loading training data...")
    book_records, target_prices = load_training_data(db_path)

    # Extract features
    print("\n2. Extracting features...")
    feature_extractor = FeatureExtractor()
    X, completeness_scores = extract_features_for_training(book_records, feature_extractor, db_path)
    y = np.array(target_prices)

    avg_completeness = np.mean(completeness_scores)
    print(f"   Average feature completeness: {avg_completeness:.1%}")

    # Remove outliers (IQR method)
    q1, q3 = np.percentile(y, [25, 75])
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    outlier_mask = (y >= lower_bound) & (y <= upper_bound)
    X_filtered = X[outlier_mask]
    y_filtered = y[outlier_mask]

    n_outliers = len(y) - len(y_filtered)
    print(f"\n   Removed {n_outliers} outliers (${lower_bound:.2f} - ${upper_bound:.2f})")
    print(f"   Training with {len(y_filtered)} samples")

    # Train/test split
    print(f"\n3. Splitting data ({100*(1-args.test_size):.0f}% train, {100*args.test_size:.0f}% test)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X_filtered, y_filtered, test_size=args.test_size, random_state=42
    )
    print(f"   Train: {len(X_train)} samples")
    print(f"   Test:  {len(X_test)} samples")

    # Train model
    print("\n4. Training model...")
    metadata = train_model(X_train, y_train, X_test, y_test, model_dir)

    print("\n" + "=" * 70)
    print("Training Complete!")
    print("=" * 70)
    print(f"Model version: {metadata['version']}")
    print(f"Test MAE: ${metadata['test_mae']:.2f}")
    print(f"Test RMSE: ${metadata['test_rmse']:.2f}")
    print(f"Test R²: {metadata['test_r2']:.3f}")
    print(f"\nModel ready for use. Integration instructions:")
    print(f"  1. Model automatically loaded from: {model_dir}/")
    print(f"  2. Call get_ml_estimator() in your code")
    print(f"  3. Monitor predictions in production")

    return 0


if __name__ == "__main__":
    sys.exit(main())
