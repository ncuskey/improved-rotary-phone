"""
eBay Hybrid Model Training Script - Baseline vs Text Embeddings

This script compares two approaches for eBay sold price prediction:
1. Baseline: Traditional XGBoost with 26 tabular features
2. Hybrid: XGBoost with 26 tabular + 384 text embedding features (410 total)

The goal is to evaluate whether text embeddings from book descriptions improve
prediction accuracy, especially for collectible/low-data segments.

Usage:
    python3 scripts/stacking/train_ebay_hybrid.py

Outputs:
    - Baseline model performance (MAE, R²)
    - Hybrid model performance (MAE, R²)
    - Comparison report
    - Feature importance analysis
"""

import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime
import numpy as np
from sklearn.model_selection import train_test_split, GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from isbn_lot_optimizer.ml.feature_extractor import PlatformFeatureExtractor, get_bookfinder_features
from scripts.stacking.data_loader import load_platform_training_data
from scripts.stacking.training_utils import calculate_temporal_weights
from isbn_lot_optimizer.ml.text_embeddings import (
    TextEmbedder,
    extract_descriptions_from_records,
    augment_features_with_embeddings
)


def create_simple_objects(record):
    """Create simple objects for feature extraction (from train_ebay_model.py)."""
    class SimpleMetadata:
        def __init__(self, d, cover_type, signed, printing):
            self.title = d.get('title')
            self.authors = d.get('authors')
            self.publisher = d.get('publisher')
            self.published_year = d.get('published_year') or d.get('publication_year')
            self.page_count = d.get('page_count')
            self.binding = d.get('binding')
            self.cover_type = cover_type
            self.signed = signed
            self.printing = printing
            self.average_rating = d.get('average_rating')
            self.ratings_count = d.get('ratings_count')
            self.list_price = d.get('list_price')
            self.categories = d.get('categories', [])

    class SimpleMarket:
        def __init__(self, d):
            self.sold_count = d.get('sold_comps_count') or d.get('sold_count')
            self.active_count = d.get('active_count', 0)
            self.active_median_price = d.get('active_median_price', 0)
            sold_median = d.get('sold_comps_median')
            self.sold_avg_price = d.get('sold_avg_price') or sold_median
            if self.sold_count and self.active_count and (self.sold_count + self.active_count) > 0:
                self.sell_through_rate = self.sold_count / (self.sold_count + self.active_count)
            else:
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
    """Extract eBay-specific features from records."""
    X = []
    y = []
    isbns = []
    timestamps = []

    for record, target in zip(records, targets):
        metadata, market, bookscouter = create_simple_objects(record)
        bookfinder_data = get_bookfinder_features(record['isbn'], str(catalog_db_path))

        features = extractor.extract_for_platform(
            platform='ebay',
            metadata=metadata,
            market=market,
            bookscouter=bookscouter,
            condition=record.get('condition', 'Good'),
            abebooks=record.get('abebooks'),
            bookfinder=bookfinder_data,
            sold_comps=record.get('sold_comps')
        )

        X.append(features.values)
        y.append(target)
        isbns.append(record['isbn'])
        timestamps.append(record.get('ebay_timestamp'))

    return np.array(X), np.array(y), isbns, timestamps


def load_ebay_data_with_descriptions():
    """
    Load eBay training data, extract features, and get descriptions.

    Returns:
        Tuple of (X, y, isbns, timestamps, descriptions)
    """
    print("=" * 80)
    print("LOADING EBAY TRAINING DATA")
    print("=" * 80)

    # Load platform data
    platform_data = load_platform_training_data()
    ebay_records, ebay_targets = platform_data['ebay']

    print(f"\n✓ Loaded {len(ebay_records)} eBay training books")

    # Extract tabular features
    print("\nExtracting tabular features...")
    extractor = PlatformFeatureExtractor()
    catalog_db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    X, y, isbns, timestamps = extract_features(ebay_records, ebay_targets, extractor, catalog_db_path)

    print(f"✓ Features extracted: {X.shape[1]} features from {len(X)} books")

    # Extract descriptions from cached_books table
    print("\nExtracting descriptions from database...")
    cache_db = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'
    conn = sqlite3.connect(cache_db)
    cursor = conn.cursor()

    isbn_to_desc = {}
    cursor.execute("SELECT isbn, description FROM cached_books WHERE description IS NOT NULL")
    for row in cursor.fetchall():
        isbn, desc = row
        isbn_to_desc[isbn] = desc
    conn.close()

    # Match descriptions to ISBNs
    descriptions = []
    desc_count = 0
    for isbn in isbns:
        desc = isbn_to_desc.get(isbn)
        descriptions.append(desc)
        if desc:
            desc_count += 1

    print(f"✓ Descriptions found: {desc_count} / {len(isbns)} ({desc_count/len(isbns)*100:.1f}%)")

    return X, y, isbns, timestamps, descriptions


def train_baseline_model(X_train, y_train, X_test, y_test, sample_weight=None):
    """
    Train baseline XGBoost model with tabular features only.

    Returns:
        Tuple of (model, scaler, train_mae, test_mae, train_r2, test_r2)
    """
    print("\n" + "=" * 80)
    print("TRAINING BASELINE MODEL (Tabular Features Only)")
    print("=" * 80)

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train model
    print(f"\nTraining GradientBoostingRegressor...")
    print(f"  Features: {X_train.shape[1]}")
    print(f"  Training samples: {len(X_train)}")
    print(f"  Test samples: {len(X_test)}")

    model = GradientBoostingRegressor(
        n_estimators=200,
        learning_rate=0.1,
        max_depth=5,
        min_samples_split=10,
        min_samples_leaf=4,
        subsample=0.8,
        random_state=42,
        verbose=0
    )

    model.fit(X_train_scaled, y_train, sample_weight=sample_weight)

    # Evaluate
    y_train_pred = model.predict(X_train_scaled)
    y_test_pred = model.predict(X_test_scaled)

    train_mae = mean_absolute_error(y_train, y_train_pred)
    test_mae = mean_absolute_error(y_test, y_test_pred)
    train_r2 = r2_score(y_train, y_train_pred)
    test_r2 = r2_score(y_test, y_test_pred)

    print(f"\n✓ Baseline Model Performance:")
    print(f"  Train MAE: ${train_mae:.2f}")
    print(f"  Test MAE:  ${test_mae:.2f}")
    print(f"  Train R²:  {train_r2:.3f}")
    print(f"  Test R²:   {test_r2:.3f}")

    return model, scaler, train_mae, test_mae, train_r2, test_r2


def train_hybrid_model(X_train, y_train, X_test, y_test, descriptions_train, descriptions_test, sample_weight=None):
    """
    Train hybrid XGBoost model with tabular + text embedding features.

    Returns:
        Tuple of (model, scaler, embedder, train_mae, test_mae, train_r2, test_r2)
    """
    print("\n" + "=" * 80)
    print("TRAINING HYBRID MODEL (Tabular + Text Embeddings)")
    print("=" * 80)

    # Generate text embeddings
    print("\nGenerating text embeddings...")
    embedder = TextEmbedder()
    X_train_hybrid = augment_features_with_embeddings(X_train, descriptions_train, embedder)
    X_test_hybrid = augment_features_with_embeddings(X_test, descriptions_test, embedder)

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_hybrid)
    X_test_scaled = scaler.transform(X_test_hybrid)

    # Train model
    print(f"\nTraining GradientBoostingRegressor...")
    print(f"  Features: {X_train_hybrid.shape[1]} ({X_train.shape[1]} tabular + 384 text)")
    print(f"  Training samples: {len(X_train_hybrid)}")
    print(f"  Test samples: {len(X_test_hybrid)}")

    model = GradientBoostingRegressor(
        n_estimators=200,
        learning_rate=0.1,
        max_depth=5,
        min_samples_split=10,
        min_samples_leaf=4,
        subsample=0.8,
        random_state=42,
        verbose=0
    )

    model.fit(X_train_scaled, y_train, sample_weight=sample_weight)

    # Evaluate
    y_train_pred = model.predict(X_train_scaled)
    y_test_pred = model.predict(X_test_scaled)

    train_mae = mean_absolute_error(y_train, y_train_pred)
    test_mae = mean_absolute_error(y_test, y_test_pred)
    train_r2 = r2_score(y_train, y_train_pred)
    test_r2 = r2_score(y_test, y_test_pred)

    print(f"\n✓ Hybrid Model Performance:")
    print(f"  Train MAE: ${train_mae:.2f}")
    print(f"  Test MAE:  ${test_mae:.2f}")
    print(f"  Train R²:  {train_r2:.3f}")
    print(f"  Test R²:   {test_r2:.3f}")

    return model, scaler, embedder, train_mae, test_mae, train_r2, test_r2


def main():
    """Main training and comparison workflow."""
    print("\n" + "=" * 80)
    print("EBAY HYBRID MODEL EXPERIMENT")
    print("Baseline vs Text Embeddings Comparison")
    print("=" * 80)

    # Load data with features already extracted
    X_all, y_all, isbns, timestamps, descriptions = load_ebay_data_with_descriptions()

    print(f"\n✓ Data loading complete:")
    print(f"  Samples: {len(X_all)}")
    print(f"  Features: {X_all.shape[1]}")
    print(f"  Target range: ${y_all.min():.2f} - ${y_all.max():.2f}")

    # Calculate temporal weights
    print("\n" + "=" * 80)
    print("CALCULATING TEMPORAL WEIGHTS")
    print("=" * 80)
    temporal_weights = calculate_temporal_weights(timestamps, decay_days=365.0)

    if temporal_weights is not None:
        print(f"✓ Temporal weighting enabled (365-day half-life)")
        print(f"  Weight range: {temporal_weights.min():.4f} - {temporal_weights.max():.4f}")
    else:
        print("⚠ Temporal weights unavailable, proceeding without weighting")

    # Train/test split
    print("\n" + "=" * 80)
    print("TRAIN/TEST SPLIT")
    print("=" * 80)

    # Use GroupKFold to avoid ISBN leakage
    isbns_array = np.array(isbns)
    descriptions_array = np.array(descriptions, dtype=object)

    split_data = train_test_split(
        X_all, y_all, isbns_array, descriptions_array, temporal_weights,
        test_size=0.2,
        random_state=42
    )

    X_train, X_test, y_train, y_test, isbns_train, isbns_test, desc_train, desc_test, weights_train, weights_test = split_data

    print(f"✓ Split complete:")
    print(f"  Train: {len(X_train)} samples")
    print(f"  Test:  {len(X_test)} samples")

    # Train baseline model
    baseline_results = train_baseline_model(
        X_train, y_train, X_test, y_test,
        sample_weight=weights_train if temporal_weights is not None else None
    )
    baseline_model, baseline_scaler, baseline_train_mae, baseline_test_mae, baseline_train_r2, baseline_test_r2 = baseline_results

    # Train hybrid model
    hybrid_results = train_hybrid_model(
        X_train, y_train, X_test, y_test, desc_train.tolist(), desc_test.tolist(),
        sample_weight=weights_train if temporal_weights is not None else None
    )
    hybrid_model, hybrid_scaler, embedder, hybrid_train_mae, hybrid_test_mae, hybrid_train_r2, hybrid_test_r2 = hybrid_results

    # Comparison report
    print("\n" + "=" * 80)
    print("COMPARISON REPORT")
    print("=" * 80)

    mae_improvement = ((baseline_test_mae - hybrid_test_mae) / baseline_test_mae) * 100
    r2_improvement = ((hybrid_test_r2 - baseline_test_r2) / max(abs(baseline_test_r2), 0.001)) * 100

    print(f"\n{'Metric':<20} {'Baseline':<15} {'Hybrid':<15} {'Improvement':<15}")
    print("-" * 65)
    print(f"{'Test MAE':<20} ${baseline_test_mae:<14.2f} ${hybrid_test_mae:<14.2f} {mae_improvement:>+.1f}%")
    print(f"{'Test R²':<20} {baseline_test_r2:<15.3f} {hybrid_test_r2:<15.3f} {r2_improvement:>+.1f}%")
    print(f"{'Train MAE':<20} ${baseline_train_mae:<14.2f} ${hybrid_train_mae:<14.2f}")
    print(f"{'Train R²':<20} {baseline_train_r2:<15.3f} {hybrid_train_r2:<15.3f}")
    print(f"{'Features':<20} {X_train.shape[1]:<15} {X_train.shape[1] + 384:<15}")

    # Conclusion
    print("\n" + "=" * 80)
    print("CONCLUSION")
    print("=" * 80)

    if mae_improvement > 5:
        print(f"\n✓ SIGNIFICANT IMPROVEMENT: Text embeddings reduce MAE by {mae_improvement:.1f}%")
        print("  Recommendation: Deploy hybrid model to production")
    elif mae_improvement > 0:
        print(f"\n~ MARGINAL IMPROVEMENT: Text embeddings reduce MAE by {mae_improvement:.1f}%")
        print("  Recommendation: Consider A/B testing before full deployment")
    else:
        print(f"\n✗ NO IMPROVEMENT: Baseline model outperforms hybrid by {-mae_improvement:.1f}%")
        print("  Recommendation: Keep baseline model, embeddings not helpful for this task")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
