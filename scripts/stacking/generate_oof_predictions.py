#!/usr/bin/env python3
"""
Generate out-of-fold predictions for stacking ensemble meta-model.

Uses 5-fold cross-validation to generate predictions from each base model
without overfitting. These OOF predictions become features for the meta-model.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Tuple

import joblib
import numpy as np
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.stacking.data_loader import load_platform_training_data
from scripts.stacking.training_utils import apply_log_transform, inverse_log_transform
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


def extract_platform_features(records, platform, extractor, catalog_db_path):
    """Extract platform-specific features from records."""
    from isbn_lot_optimizer.ml.feature_extractor import get_bookfinder_features

    X = []
    for record in records:
        metadata, market, bookscouter = create_simple_objects(record)

        # Query BookFinder features
        bookfinder_data = get_bookfinder_features(record['isbn'], str(catalog_db_path))

        features = extractor.extract_for_platform(
            platform=platform,
            metadata=metadata,
            market=market,
            bookscouter=bookscouter,
            condition=record.get('condition', 'Good'),
            abebooks=record.get('abebooks'),
            bookfinder=bookfinder_data,
            amazon_fbm=record.get('amazon_fbm')
        )
        X.append(features.values)
    return np.array(X)


def generate_oof_for_platform(
    platform: str,
    records: list,
    targets: list,
    catalog_db_path: Path,
    n_folds: int = 5
) -> Tuple[np.ndarray, Dict]:
    """
    Generate out-of-fold predictions for a single platform.

    Args:
        platform: Platform name ('ebay', 'abebooks', 'amazon', 'biblio', 'alibris', 'zvab')
        records: List of book records
        targets: List of target prices
        catalog_db_path: Path to catalog database for BookFinder features
        n_folds: Number of CV folds (default: 5)

    Returns:
        Tuple of (oof_predictions, metadata)
    """
    print(f"\n{platform.upper()} Out-of-Fold Predictions:")
    print("-" * 60)

    extractor = PlatformFeatureExtractor()
    X = extract_platform_features(records, platform, extractor, catalog_db_path)
    y = np.array(targets)

    # Initialize OOF predictions array
    oof_predictions = np.zeros(len(y))

    # 5-fold cross-validation
    kfold = KFold(n_splits=n_folds, shuffle=True, random_state=42)

    for fold, (train_idx, val_idx) in enumerate(kfold.split(X), 1):
        print(f"  Fold {fold}/{n_folds}: ", end="", flush=True)

        # Split data
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        # Apply log transform
        y_train_log = np.log1p(y_train)

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)

        # Train model
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

        model.fit(X_train_scaled, y_train_log)

        # Generate OOF predictions (inverse transform back to original scale)
        y_val_pred_log = model.predict(X_val_scaled)
        oof_predictions[val_idx] = np.expm1(y_val_pred_log)

        # Calculate fold MAE
        fold_mae = np.mean(np.abs(y_val - oof_predictions[val_idx]))
        print(f"MAE ${fold_mae:.2f}")

    # Calculate overall OOF metrics
    oof_mae = np.mean(np.abs(y - oof_predictions))
    oof_mse = np.mean((y - oof_predictions) ** 2)
    oof_rmse = np.sqrt(oof_mse)

    # R² score
    ss_res = np.sum((y - oof_predictions) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    oof_r2 = 1 - (ss_res / ss_tot)

    print(f"\n  Overall OOF Metrics:")
    print(f"    MAE:  ${oof_mae:.2f}")
    print(f"    RMSE: ${oof_rmse:.2f}")
    print(f"    R²:   {oof_r2:.3f}")

    metadata = {
        'platform': platform,
        'n_samples': len(y),
        'n_folds': n_folds,
        'oof_mae': float(oof_mae),
        'oof_rmse': float(oof_rmse),
        'oof_r2': float(oof_r2),
        'target_mean': float(np.mean(y)),
        'target_std': float(np.std(y)),
    }

    return oof_predictions, metadata


def generate_all_oof_predictions():
    """Generate OOF predictions for all platforms and save."""
    print("=" * 80)
    print("GENERATING OUT-OF-FOLD PREDICTIONS FOR STACKING META-MODEL")
    print("=" * 80)

    # Load platform-specific data
    print("\nLoading platform data...")
    platform_data = load_platform_training_data()
    catalog_db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    # We need a common dataset for meta-model training
    # Use catalog books that have eBay targets (the final prediction target)
    ebay_records, ebay_targets = platform_data['ebay']

    print(f"\nMeta-model training set: {len(ebay_records)} books with eBay targets")

    # For each book in the eBay dataset, we'll generate predictions from all available specialists
    # Some books won't have data for all platforms, which is fine - we'll use 0 as fallback

    # Extract ISBNs for matching
    ebay_isbns = [record['isbn'] for record in ebay_records]
    isbn_to_idx = {isbn: i for i, isbn in enumerate(ebay_isbns)}

    # Generate OOF predictions for each platform
    print("\n" + "=" * 80)
    print("GENERATING PLATFORM-SPECIFIC OOF PREDICTIONS")
    print("=" * 80)

    # eBay predictions (on the same dataset)
    ebay_oof, ebay_meta = generate_oof_for_platform('ebay', ebay_records, ebay_targets, catalog_db_path)

    # AbeBooks predictions (need to map to eBay dataset)
    abebooks_records, abebooks_targets = platform_data['abebooks']
    abebooks_isbns = [record['isbn'] for record in abebooks_records]

    # Create mapping: which eBay books have AbeBooks data
    abebooks_available = [isbn in abebooks_isbns for isbn in ebay_isbns]
    abebooks_indices = [isbn_to_idx[isbn] for isbn in abebooks_isbns if isbn in isbn_to_idx]

    if abebooks_indices:
        # Generate OOF for AbeBooks books
        abebooks_records_subset = [abebooks_records[abebooks_isbns.index(ebay_isbns[i])]
                                   for i in abebooks_indices]
        abebooks_targets_subset = [abebooks_targets[abebooks_isbns.index(ebay_isbns[i])]
                                   for i in abebooks_indices]
        abebooks_oof_subset, abebooks_meta = generate_oof_for_platform('abebooks', abebooks_records_subset, abebooks_targets_subset
        , catalog_db_path)

        # Map back to full eBay dataset (use 0 for books without AbeBooks data)
        abebooks_oof = np.zeros(len(ebay_isbns))
        for i, oof_pred in zip(abebooks_indices, abebooks_oof_subset):
            abebooks_oof[i] = oof_pred
    else:
        abebooks_oof = np.zeros(len(ebay_isbns))
        abebooks_meta = {'platform': 'abebooks', 'n_samples': 0}

    # Amazon predictions (need to map to eBay dataset)
    amazon_records, amazon_targets = platform_data['amazon']
    amazon_isbns = [record['isbn'] for record in amazon_records]

    # Create mapping
    amazon_available = [isbn in amazon_isbns for isbn in ebay_isbns]
    amazon_indices = [isbn_to_idx[isbn] for isbn in amazon_isbns if isbn in isbn_to_idx]

    if amazon_indices:
        # Generate OOF for Amazon books
        amazon_records_subset = [amazon_records[amazon_isbns.index(ebay_isbns[i])]
                                for i in amazon_indices]
        amazon_targets_subset = [amazon_targets[amazon_isbns.index(ebay_isbns[i])]
                                for i in amazon_indices]
        amazon_oof_subset, amazon_meta = generate_oof_for_platform('amazon', amazon_records_subset, amazon_targets_subset
        , catalog_db_path)

        # Map back to full eBay dataset
        amazon_oof = np.zeros(len(ebay_isbns))
        for i, oof_pred in zip(amazon_indices, amazon_oof_subset):
            amazon_oof[i] = oof_pred
    else:
        amazon_oof = np.zeros(len(ebay_isbns))
        amazon_meta = {'platform': 'amazon', 'n_samples': 0}

    # Biblio predictions (need to map to eBay dataset)
    biblio_records, biblio_targets = platform_data['biblio']
    biblio_isbns = [record['isbn'] for record in biblio_records]
    biblio_available = [isbn in biblio_isbns for isbn in ebay_isbns]
    biblio_indices = [isbn_to_idx[isbn] for isbn in biblio_isbns if isbn in isbn_to_idx]
    
    if biblio_indices:
        biblio_records_subset = [biblio_records[biblio_isbns.index(ebay_isbns[i])] for i in biblio_indices]
        biblio_targets_subset = [biblio_targets[biblio_isbns.index(ebay_isbns[i])] for i in biblio_indices]
        biblio_oof_subset, biblio_meta = generate_oof_for_platform('biblio', biblio_records_subset, biblio_targets_subset, catalog_db_path)
        biblio_oof = np.zeros(len(ebay_isbns))
        for i, oof_pred in zip(biblio_indices, biblio_oof_subset):
            biblio_oof[i] = oof_pred
    else:
        biblio_oof = np.zeros(len(ebay_isbns))
        biblio_meta = {'platform': 'biblio', 'n_samples': 0}

    # Alibris predictions
    alibris_records, alibris_targets = platform_data['alibris']
    alibris_isbns = [record['isbn'] for record in alibris_records]
    alibris_available = [isbn in alibris_isbns for isbn in ebay_isbns]
    alibris_indices = [isbn_to_idx[isbn] for isbn in alibris_isbns if isbn in isbn_to_idx]
    
    if alibris_indices:
        alibris_records_subset = [alibris_records[alibris_isbns.index(ebay_isbns[i])] for i in alibris_indices]
        alibris_targets_subset = [alibris_targets[alibris_isbns.index(ebay_isbns[i])] for i in alibris_indices]
        alibris_oof_subset, alibris_meta = generate_oof_for_platform('alibris', alibris_records_subset, alibris_targets_subset, catalog_db_path)
        alibris_oof = np.zeros(len(ebay_isbns))
        for i, oof_pred in zip(alibris_indices, alibris_oof_subset):
            alibris_oof[i] = oof_pred
    else:
        alibris_oof = np.zeros(len(ebay_isbns))
        alibris_meta = {'platform': 'alibris', 'n_samples': 0}

    # Zvab predictions
    zvab_records, zvab_targets = platform_data['zvab']
    zvab_isbns = [record['isbn'] for record in zvab_records]
    zvab_available = [isbn in zvab_isbns for isbn in ebay_isbns]
    zvab_indices = [isbn_to_idx[isbn] for isbn in zvab_isbns if isbn in isbn_to_idx]
    
    if zvab_indices:
        zvab_records_subset = [zvab_records[zvab_isbns.index(ebay_isbns[i])] for i in zvab_indices]
        zvab_targets_subset = [zvab_targets[zvab_isbns.index(ebay_isbns[i])] for i in zvab_indices]
        zvab_oof_subset, zvab_meta = generate_oof_for_platform('zvab', zvab_records_subset, zvab_targets_subset, catalog_db_path)
        zvab_oof = np.zeros(len(ebay_isbns))
        for i, oof_pred in zip(zvab_indices, zvab_oof_subset):
            zvab_oof[i] = oof_pred
    else:
        zvab_oof = np.zeros(len(ebay_isbns))
        zvab_meta = {'platform': 'zvab', 'n_samples': 0}

    # Stack predictions into meta-features
    print("\n" + "=" * 80)
    print("CREATING META-MODEL TRAINING DATA")
    print("=" * 80)

    meta_X = np.column_stack([ebay_oof, abebooks_oof, amazon_oof, biblio_oof, alibris_oof, zvab_oof])
    meta_y = np.array(ebay_targets)

    print(f"\nMeta-model features shape: {meta_X.shape}")
    print(f"Meta-model target shape: {meta_y.shape}")

    print(f"\nFeature availability:")
    print(f"  eBay predictions:     {len(ebay_isbns)} / {len(ebay_isbns)} (100.0%)")
    print(f"  AbeBooks predictions: {sum(abebooks_available)} / {len(ebay_isbns)} ({sum(abebooks_available) / len(ebay_isbns) * 100:.1f}%)")
    print(f"  Amazon predictions:   {sum(amazon_available)} / {len(ebay_isbns)} ({sum(amazon_available) / len(ebay_isbns) * 100:.1f}%)")
    print(f"  Biblio predictions:   {sum(biblio_available)} / {len(ebay_isbns)} ({sum(biblio_available) / len(ebay_isbns) * 100:.1f}%)")
    print(f"  Alibris predictions:  {sum(alibris_available)} / {len(ebay_isbns)} ({sum(alibris_available) / len(ebay_isbns) * 100:.1f}%)")
    print(f"  Zvab predictions:     {sum(zvab_available)} / {len(ebay_isbns)} ({sum(zvab_available) / len(ebay_isbns) * 100:.1f}%)")

    # Save OOF predictions and metadata
    print("\n" + "=" * 80)
    print("SAVING OOF PREDICTIONS")
    print("=" * 80)

    output_dir = Path(__file__).parent.parent.parent / 'isbn_lot_optimizer' / 'models' / 'stacking'
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save features and targets
    oof_data = {
        'meta_X': meta_X,
        'meta_y': meta_y,
        'ebay_isbns': ebay_isbns,
        'ebay_oof': ebay_oof,
        'abebooks_oof': abebooks_oof,
        'amazon_oof': amazon_oof,
        'biblio_oof': biblio_oof,
        'alibris_oof': alibris_oof,
        'zvab_oof': zvab_oof,
    }

    oof_path = output_dir / 'oof_predictions.pkl'
    joblib.dump(oof_data, oof_path)
    print(f"✓ Saved OOF predictions: {oof_path}")

    # Save metadata
    metadata = {
        'n_samples': len(ebay_isbns),
        'n_features': 6,
        'feature_names': ['ebay_pred', 'abebooks_pred', 'amazon_pred', 'biblio_pred', 'alibris_pred', 'zvab_pred'],
        'ebay_metadata': ebay_meta,
        'abebooks_metadata': abebooks_meta,
        'amazon_metadata': amazon_meta,
        'biblio_metadata': biblio_meta,
        'alibris_metadata': alibris_meta,
        'zvab_metadata': zvab_meta,
    }

    metadata_path = output_dir / 'oof_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Saved metadata: {metadata_path}")

    print("\n" + "=" * 80)
    print("OOF GENERATION COMPLETE")
    print("=" * 80)
    print(f"\nMeta-model training data:")
    print(f"  Samples: {len(ebay_isbns)}")
    print(f"  Features: 6 (ebay, abebooks, amazon, biblio, alibris, zvab predictions)")
    print(f"  Target: eBay sold comps")
    print("=" * 80 + "\n")

    return oof_data, metadata


if __name__ == "__main__":
    generate_all_oof_predictions()
