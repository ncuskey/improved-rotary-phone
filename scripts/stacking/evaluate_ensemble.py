#!/usr/bin/env python3
"""
Comprehensive evaluation of stacking ensemble vs unified model.

Compares performance on the same test set to provide fair comparison.
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.stacking.data_loader import load_platform_training_data
from isbn_lot_optimizer.ml.feature_extractor import FeatureExtractor, PlatformFeatureExtractor


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


def predict_stacked(records, ebay_model, ebay_scaler, abebooks_model, abebooks_scaler,
                    amazon_model, amazon_scaler, meta_model, platform_extractor):
    """Generate stacked ensemble predictions."""
    predictions = []

    for record in records:
        metadata, market, bookscouter = create_simple_objects(record)

        # Get predictions from each specialist
        # eBay prediction
        ebay_features = platform_extractor.extract_for_platform(
            'ebay', metadata, market, bookscouter,
            record.get('condition', 'Good'), record.get('abebooks')
        )
        ebay_X = ebay_scaler.transform(ebay_features.values.reshape(1, -1))
        ebay_pred = ebay_model.predict(ebay_X)[0]

        # AbeBooks prediction (0 if no data)
        if record.get('abebooks'):
            abebooks_features = platform_extractor.extract_for_platform(
                'abebooks', metadata, market, bookscouter,
                record.get('condition', 'Good'), record.get('abebooks')
            )
            abebooks_X = abebooks_scaler.transform(abebooks_features.values.reshape(1, -1))
            abebooks_pred = abebooks_model.predict(abebooks_X)[0]
        else:
            abebooks_pred = 0.0

        # Amazon prediction (0 if no data)
        if bookscouter and bookscouter.amazon_lowest_price:
            amazon_features = platform_extractor.extract_for_platform(
                'amazon', metadata, market, bookscouter,
                record.get('condition', 'Good'), record.get('abebooks')
            )
            amazon_X = amazon_scaler.transform(amazon_features.values.reshape(1, -1))
            amazon_pred = amazon_model.predict(amazon_X)[0]
        else:
            amazon_pred = 0.0

        # Combine with meta-model
        meta_features = np.array([[ebay_pred, abebooks_pred, amazon_pred]])
        final_pred = meta_model.predict(meta_features)[0]
        predictions.append(final_pred)

    return np.array(predictions)


def predict_unified(records, unified_model, unified_scaler, unified_extractor):
    """Generate unified model predictions."""
    predictions = []

    for record in records:
        metadata, market, bookscouter = create_simple_objects(record)

        features = unified_extractor.extract(
            metadata, market, bookscouter,
            record.get('condition', 'Good'), record.get('abebooks')
        )

        X = unified_scaler.transform(features.values.reshape(1, -1))
        pred = unified_model.predict(X)[0]
        predictions.append(pred)

    return np.array(predictions)


def evaluate_ensemble():
    """Comprehensive evaluation of stacking vs unified model."""
    print("=" * 80)
    print("STACKING ENSEMBLE VS UNIFIED MODEL - COMPREHENSIVE EVALUATION")
    print("=" * 80)

    # Load models
    print("\n1. Loading models...")
    model_dir = Path(__file__).parent.parent.parent / 'isbn_lot_optimizer' / 'models'
    stacking_dir = model_dir / 'stacking'

    # Load stacking models
    ebay_model = joblib.load(stacking_dir / 'ebay_model.pkl')
    ebay_scaler = joblib.load(stacking_dir / 'ebay_scaler.pkl')
    abebooks_model = joblib.load(stacking_dir / 'abebooks_model.pkl')
    abebooks_scaler = joblib.load(stacking_dir / 'abebooks_scaler.pkl')
    amazon_model = joblib.load(stacking_dir / 'amazon_model.pkl')
    amazon_scaler = joblib.load(stacking_dir / 'amazon_scaler.pkl')
    meta_model = joblib.load(stacking_dir / 'meta_model.pkl')

    # Load unified model
    unified_model = joblib.load(model_dir / 'price_v1.pkl')
    unified_scaler = joblib.load(model_dir / 'scaler_v1.pkl')

    print("   ✓ Loaded stacking ensemble (7 models)")
    print("   ✓ Loaded unified model")

    # Load test data
    print("\n2. Loading test data...")
    platform_data = load_platform_training_data()
    ebay_records, ebay_targets = platform_data['ebay']

    print(f"   Test set: {len(ebay_records)} books with eBay targets")

    # Generate predictions
    print("\n3. Generating predictions...")
    platform_extractor = PlatformFeatureExtractor()
    unified_extractor = FeatureExtractor()

    stacked_preds = predict_stacked(
        ebay_records, ebay_model, ebay_scaler, abebooks_model, abebooks_scaler,
        amazon_model, amazon_scaler, meta_model, platform_extractor
    )

    unified_preds = predict_unified(ebay_records, unified_model, unified_scaler, unified_extractor)

    y_true = np.array(ebay_targets)

    print("   ✓ Stacked predictions generated")
    print("   ✓ Unified predictions generated")

    # Calculate metrics
    print("\n4. Calculating metrics...")

    # Stacked metrics
    stacked_mae = mean_absolute_error(y_true, stacked_preds)
    stacked_rmse = np.sqrt(mean_squared_error(y_true, stacked_preds))
    stacked_r2 = r2_score(y_true, stacked_preds)

    # Unified metrics
    unified_mae = mean_absolute_error(y_true, unified_preds)
    unified_rmse = np.sqrt(mean_squared_error(y_true, unified_preds))
    unified_r2 = r2_score(y_true, unified_preds)

    # Comparison
    print("\n" + "=" * 80)
    print("PERFORMANCE COMPARISON")
    print("=" * 80)

    print(f"\n{'Metric':<15} {'Unified':<15} {'Stacked':<15} {'Change':<15}")
    print("-" * 80)

    mae_change = unified_mae - stacked_mae
    mae_pct = (mae_change / unified_mae) * 100
    print(f"{'MAE':<15} ${unified_mae:<14.2f} ${stacked_mae:<14.2f} ${mae_change:+6.2f} ({mae_pct:+5.1f}%)")

    rmse_change = unified_rmse - stacked_rmse
    rmse_pct = (rmse_change / unified_rmse) * 100
    print(f"{'RMSE':<15} ${unified_rmse:<14.2f} ${stacked_rmse:<14.2f} ${rmse_change:+6.2f} ({rmse_pct:+5.1f}%)")

    r2_change = stacked_r2 - unified_r2
    r2_pct = (r2_change / abs(unified_r2)) * 100 if unified_r2 != 0 else 0
    print(f"{'R²':<15} {unified_r2:<15.3f} {stacked_r2:<15.3f} {r2_change:+7.3f} ({r2_pct:+5.1f}%)")

    # Win/lose summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if stacked_mae < unified_mae:
        print(f"\n✅ Stacking is {mae_pct:.1f}% better (lower MAE)")
    else:
        print(f"\n❌ Stacking is {-mae_pct:.1f}% worse (higher MAE)")

    if stacked_r2 > unified_r2:
        improvement = ((stacked_r2 - unified_r2) / abs(unified_r2)) * 100 if unified_r2 != 0 else 0
        print(f"✅ Stacking explains {improvement:.1f}% more variance (higher R²)")
    else:
        decline = ((unified_r2 - stacked_r2) / unified_r2) * 100 if unified_r2 != 0 else 0
        print(f"❌ Stacking explains {decline:.1f}% less variance (lower R²)")

    # Recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)

    if stacked_mae < unified_mae and stacked_r2 > unified_r2:
        print("\n✅ RECOMMENDATION: Use stacking ensemble")
        print("   - Better accuracy (lower MAE)")
        print("   - Better variance explained (higher R²)")
    elif stacked_mae > unified_mae and stacked_r2 < unified_r2:
        print("\n❌ RECOMMENDATION: Keep unified model")
        print("   - Lower error (better MAE)")
        print("   - Better variance explained (higher R²)")
    else:
        print("\n⚖️  RECOMMENDATION: Mixed results")
        if stacked_mae < unified_mae:
            print("   ✓ Stacking has lower MAE (better accuracy)")
        else:
            print("   ✗ Unified has lower MAE (better accuracy)")
        if stacked_r2 > unified_r2:
            print("   ✓ Stacking has higher R² (explains more variance)")
        else:
            print("   ✗ Unified has higher R² (explains more variance)")
        print("\n   Consider hybrid approach or continue data collection")

    print("=" * 80 + "\n")

    # Save evaluation report
    report = {
        'test_samples': len(ebay_records),
        'unified': {
            'mae': float(unified_mae),
            'rmse': float(unified_rmse),
            'r2': float(unified_r2),
        },
        'stacked': {
            'mae': float(stacked_mae),
            'rmse': float(stacked_rmse),
            'r2': float(stacked_r2),
        },
        'improvement': {
            'mae_change': float(mae_change),
            'mae_pct': float(mae_pct),
            'r2_change': float(r2_change),
            'r2_pct': float(r2_pct),
        }
    }

    report_path = stacking_dir / 'evaluation_report.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"Saved evaluation report: {report_path}\n")

    return report


if __name__ == "__main__":
    evaluate_ensemble()
