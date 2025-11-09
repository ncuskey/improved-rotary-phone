"""
Shared training utilities for stacking specialist models.

Implements best practices:
- Log transform for target variable
- GroupKFold by ISBN to prevent leakage
- Temporal weighting for recent data
- MAPE metric for interpretability
"""

import numpy as np
from datetime import datetime
from typing import Tuple, List
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error


def apply_log_transform(y_train: np.ndarray, y_test: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Apply log transform to target variable (best practice for price prediction).

    Args:
        y_train: Training targets
        y_test: Test targets

    Returns:
        Tuple of (y_train_log, y_test_log, y_train_original, y_test_original)
    """
    y_train_original = y_train.copy()
    y_test_original = y_test.copy()
    y_train_log = np.log1p(y_train)
    y_test_log = np.log1p(y_test)

    return y_train_log, y_test_log, y_train_original, y_test_original


def inverse_log_transform(predictions_log: np.ndarray) -> np.ndarray:
    """
    Inverse log transform to get actual prices.

    Args:
        predictions_log: Predictions in log space

    Returns:
        Predictions in original price space
    """
    return np.expm1(predictions_log)


def group_train_test_split(X: np.ndarray, y: np.ndarray, isbns: List[str],
                           n_splits: int = 5) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Split data using GroupKFold by ISBN to prevent leakage.

    Best practice: Prevents same ISBN from appearing in both train and test sets.

    Args:
        X: Feature matrix
        y: Target vector
        isbns: List of ISBNs (groups)
        n_splits: Number of folds (default: 5)

    Returns:
        Tuple of (X_train, X_test, y_train, y_test)
    """
    # Convert ISBNs to array for GroupKFold
    isbn_groups = np.array(isbns)

    # Use GroupKFold with n_splits, use last fold as test set
    gkf = GroupKFold(n_splits=n_splits)
    train_idx, test_idx = list(gkf.split(X, y, groups=isbn_groups))[-1]

    X_train = X[train_idx]
    X_test = X[test_idx]
    y_train = y[train_idx]
    y_test = y[test_idx]

    print(f"   Train: {len(X_train)} samples")
    print(f"   Test:  {len(X_test)} samples")
    print(f"   Unique ISBNs in train: {len(set(isbn_groups[train_idx]))}")
    print(f"   Unique ISBNs in test:  {len(set(isbn_groups[test_idx]))}")

    return X_train, X_test, y_train, y_test


def calculate_temporal_weights(timestamps: List, decay_days: float = 365.0) -> np.ndarray:
    """
    Calculate exponential time decay weights for training samples.

    Best practice: Weight recent sales higher than old sales to capture market shifts.

    Args:
        timestamps: List of timestamps (datetime objects or ISO strings)
        decay_days: Half-life for exponential decay (default: 1 year)

    Returns:
        Array of weights (1.0 = most recent, decays exponentially with age)
        Missing timestamps receive weight=1.0 (neutral)
    """
    if not timestamps or len(timestamps) == 0:
        return None

    # Convert timestamp strings to datetime objects, track indices
    datetime_objects = []
    valid_indices = []
    for i, ts in enumerate(timestamps):
        if ts is None:
            continue
        if isinstance(ts, str):
            try:
                datetime_objects.append(datetime.fromisoformat(ts.replace('Z', '+00:00')))
                valid_indices.append(i)
            except:
                continue
        elif isinstance(ts, datetime):
            datetime_objects.append(ts)
            valid_indices.append(i)

    if len(datetime_objects) == 0:
        return None

    # Find most recent timestamp
    most_recent = max(datetime_objects)

    # Calculate days since most recent
    days_old = np.array([(most_recent - ts).days for ts in datetime_objects])

    # Exponential decay: weight = exp(-days_old * ln(2) / decay_days)
    valid_weights = np.exp(-days_old * np.log(2) / decay_days)

    # Create full weight array with 1.0 for missing timestamps
    weights = np.ones(len(timestamps))
    for i, valid_idx in enumerate(valid_indices):
        weights[valid_idx] = valid_weights[i]

    # Normalize so mean weight = 1.0
    weights = weights / weights.mean()

    return weights


def calculate_price_type_weights(price_types: List[str], sold_weight: float = 3.0) -> np.ndarray:
    """
    Calculate sample weights based on price type (sold vs listing).

    Best practice: Weight SOLD prices higher than LISTING prices since sold prices
    are ground truth (actual market value) while listing prices are just asking prices.

    Args:
        price_types: List of price types ('sold' or 'listing')
        sold_weight: Weight multiplier for sold prices (default: 3.0)

    Returns:
        Array of weights (sold prices weighted 3x higher than listing prices)
    """
    if not price_types or len(price_types) == 0:
        return np.ones(0)

    weights = np.ones(len(price_types))
    for i, price_type in enumerate(price_types):
        if price_type == 'sold':
            weights[i] = sold_weight

    # Normalize so mean weight = 1.0
    weights = weights / weights.mean()

    return weights


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                   use_log_target: bool = True) -> dict:
    """
    Compute comprehensive metrics for model evaluation.

    Args:
        y_true: True target values (in original space)
        y_pred: Predicted values (in original space)
        use_log_target: Whether log transform was used

    Returns:
        Dict with mae, rmse, r2, mape metrics
    """
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)

    # Compute MAPE (handle division by zero)
    try:
        mape = mean_absolute_percentage_error(y_true, y_pred) * 100
    except:
        mape = 0.0

    return {
        'mae': float(mae),
        'rmse': float(rmse),
        'r2': float(r2),
        'mape': float(mape)
    }


def remove_outliers(X: np.ndarray, y: np.ndarray, isbns: List[str],
                   threshold: float = 3.0) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Remove outliers using Z-score method.

    Args:
        X: Feature matrix
        y: Target vector
        isbns: List of ISBNs
        threshold: Z-score threshold (default: 3.0)

    Returns:
        Tuple of (X_clean, y_clean, isbns_clean)
    """
    z_scores = np.abs((y - np.mean(y)) / np.std(y))
    mask = z_scores < threshold

    n_removed = len(y) - np.sum(mask)
    print(f"   Removed {n_removed} outliers ({n_removed/len(y)*100:.1f}%)")
    print(f"   Training samples: {np.sum(mask)}")

    return X[mask], y[mask], [isbn for i, isbn in enumerate(isbns) if mask[i]]
