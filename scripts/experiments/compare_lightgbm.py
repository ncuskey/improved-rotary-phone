#!/usr/bin/env python3
"""
Compare LightGBM vs GradientBoostingRegressor performance.
Quick test to see if LightGBM offers improvement over current model.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import GradientBoostingRegressor
import lightgbm as lgb

# Import from existing training script
from scripts.train_price_model import load_training_data, extract_features, remove_outliers
from isbn_lot_optimizer.ml.feature_extractor import FeatureExtractor

print("=" * 80)
print("LIGHTGBM VS GRADIENTBOOSTINGREGRESSOR COMPARISON")
print("=" * 80)

# Load data using existing functions
print("\n1. Loading training data...")
book_records, target_prices = load_training_data()

print("\n2. Extracting features...")
extractor = FeatureExtractor()
X, y, completeness_scores = extract_features(book_records, target_prices, extractor)

# Remove outliers
X, y = remove_outliers(X, y)
print(f"   Training with {len(X)} samples after outlier removal")

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print(f"\n3. Split: {len(X_train)} train, {len(X_test)} test\n")

# Feature scaling
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# ==================== MODEL 1: GradientBoostingRegressor ====================
print("=" * 80)
print("MODEL 1: GradientBoostingRegressor (CURRENT)")
print("=" * 80)

gb_model = GradientBoostingRegressor(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    min_samples_split=6,
    min_samples_leaf=3,
    random_state=42,
    loss='squared_error'
)

print("Training...")
gb_model.fit(X_train_scaled, y_train)

gb_train_pred = gb_model.predict(X_train_scaled)
gb_test_pred = gb_model.predict(X_test_scaled)

gb_train_mae = mean_absolute_error(y_train, gb_train_pred)
gb_test_mae = mean_absolute_error(y_test, gb_test_pred)
gb_train_rmse = np.sqrt(mean_squared_error(y_train, gb_train_pred))
gb_test_rmse = np.sqrt(mean_squared_error(y_test, gb_test_pred))
gb_test_r2 = r2_score(y_test, gb_test_pred)

print("\nResults:")
print(f"  Train MAE:  ${gb_train_mae:.2f}")
print(f"  Test MAE:   ${gb_test_mae:.2f}")
print(f"  Train RMSE: ${gb_train_rmse:.2f}")
print(f"  Test RMSE:  ${gb_test_rmse:.2f}")
print(f"  Test R²:    {gb_test_r2:.3f}")

# ==================== MODEL 2: LightGBM ====================
print("\n" + "=" * 80)
print("MODEL 2: LightGBM")
print("=" * 80)

lgb_model = lgb.LGBMRegressor(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    num_leaves=15,  # Roughly 2^depth - 1
    min_child_samples=3,
    random_state=42,
    verbosity=-1
)

print("Training...")
lgb_model.fit(X_train_scaled, y_train)

lgb_train_pred = lgb_model.predict(X_train_scaled)
lgb_test_pred = lgb_model.predict(X_test_scaled)

lgb_train_mae = mean_absolute_error(y_train, lgb_train_pred)
lgb_test_mae = mean_absolute_error(y_test, lgb_test_pred)
lgb_train_rmse = np.sqrt(mean_squared_error(y_train, lgb_train_pred))
lgb_test_rmse = np.sqrt(mean_squared_error(y_test, lgb_test_pred))
lgb_test_r2 = r2_score(y_test, lgb_test_pred)

print("\nResults:")
print(f"  Train MAE:  ${lgb_train_mae:.2f}")
print(f"  Test MAE:   ${lgb_test_mae:.2f}")
print(f"  Train RMSE: ${lgb_train_rmse:.2f}")
print(f"  Test RMSE:  ${lgb_test_rmse:.2f}")
print(f"  Test R²:    {lgb_test_r2:.3f}")

# ==================== COMPARISON ====================
print("\n" + "=" * 80)
print("COMPARISON SUMMARY")
print("=" * 80)

print(f"\n{'Metric':<20} {'GradientBoosting':>18} {'LightGBM':>18} {'Improvement':>18}")
print("-" * 80)

mae_diff = gb_test_mae - lgb_test_mae
mae_pct = (mae_diff / gb_test_mae) * 100
print(f"{'Test MAE':<20} ${gb_test_mae:>17.2f} ${lgb_test_mae:>17.2f} ${mae_diff:>9.2f} ({mae_pct:+.1f}%)")

rmse_diff = gb_test_rmse - lgb_test_rmse
rmse_pct = (rmse_diff / gb_test_rmse) * 100
print(f"{'Test RMSE':<20} ${gb_test_rmse:>17.2f} ${lgb_test_rmse:>17.2f} ${rmse_diff:>9.2f} ({rmse_pct:+.1f}%)")

r2_diff = lgb_test_r2 - gb_test_r2
r2_pct = (r2_diff / abs(gb_test_r2)) * 100 if gb_test_r2 != 0 else 0
print(f"{'Test R²':<20} {gb_test_r2:>18.3f} {lgb_test_r2:>18.3f} {r2_diff:>12.3f} ({r2_pct:+.1f}%)")

print("\n" + "=" * 80)
if lgb_test_mae < gb_test_mae:
    improvement = ((gb_test_mae - lgb_test_mae) / gb_test_mae) * 100
    print(f"✅ LightGBM is {improvement:.1f}% better (lower MAE)")
elif lgb_test_mae > gb_test_mae:
    decline = ((lgb_test_mae - gb_test_mae) / gb_test_mae) * 100
    print(f"❌ LightGBM is {decline:.1f}% worse (higher MAE)")
else:
    print("⚖️  LightGBM and GradientBoosting are equivalent")

if lgb_test_r2 > gb_test_r2:
    improvement = ((lgb_test_r2 - gb_test_r2) / abs(gb_test_r2)) * 100 if gb_test_r2 != 0 else 0
    print(f"✅ LightGBM explains {improvement:.1f}% more variance (higher R²)")

print("=" * 80)

# ==================== FEATURE IMPORTANCE COMPARISON ====================
print("\n" + "=" * 80)
print("TOP 10 FEATURE IMPORTANCE COMPARISON")
print("=" * 80)

feature_names = FeatureExtractor.get_feature_names()

gb_importance = dict(zip(feature_names, gb_model.feature_importances_))
lgb_importance = dict(zip(feature_names, lgb_model.feature_importances_))

gb_top = sorted(gb_importance.items(), key=lambda x: x[1], reverse=True)[:10]
lgb_top = sorted(lgb_importance.items(), key=lambda x: x[1], reverse=True)[:10]

print(f"\n{'Rank':<6} {'GradientBoosting':^45} {'LightGBM':^45}")
print(f"{'':6} {'Feature':<30} {'Importance':>14} {'Feature':<30} {'Importance':>14}")
print("-" * 100)

for i in range(10):
    gb_feat, gb_imp = gb_top[i]
    lgb_feat, lgb_imp = lgb_top[i]
    print(f"{i+1:<6} {gb_feat:<30} {gb_imp:>14.4f} {lgb_feat:<30} {lgb_imp:>14.4f}")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)

if lgb_test_mae < gb_test_mae - 0.10:  # At least $0.10 improvement
    print("\n✅ RECOMMENDATION: Switch to LightGBM")
    print(f"   - Lower test MAE by ${gb_test_mae - lgb_test_mae:.2f}")
    print(f"   - Better generalization (R² improvement)")
elif lgb_test_mae > gb_test_mae + 0.10:  # $0.10 worse
    print("\n❌ RECOMMENDATION: Keep GradientBoostingRegressor")
    print(f"   - LightGBM performs worse by ${lgb_test_mae - gb_test_mae:.2f}")
else:
    print("\n⚖️  RECOMMENDATION: Models are equivalent")
    print("   - Performance difference is negligible (<$0.10 MAE)")
    print("   - Keep current GradientBoostingRegressor for consistency")

print("=" * 80 + "\n")
