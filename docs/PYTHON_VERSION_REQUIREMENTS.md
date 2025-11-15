# Python Version Requirements

## Overview

This project **requires Python 3.11** for all machine learning training tasks due to XGBoost/OpenMP compatibility requirements on macOS ARM64.

## The Problem

XGBoost requires the OpenMP runtime library (`libomp.dylib`) for parallelization. On this system:
- Python 3.13+ has architecture compatibility issues with the installed OpenMP library
- OpenMP library is ARM64 but Python 3.13's XGBoost expects x86_64
- This causes `XGBoostError: Library not loaded: @rpath/libomp.dylib`

Python 3.11 has been verified to work correctly with XGBoost and OpenMP on this system.

## Solutions Implemented

### 1. Virtual Environment (Python 3.11)

The `.venv` has been recreated with Python 3.11:

```bash
# Already done, but for reference:
rm -rf .venv
/Users/nickcuskey/.pyenv/versions/3.11.13/bin/python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Verify the version:
```bash
.venv/bin/python3 --version
# Should output: Python 3.11.13
```

### 2. Automatic Version Checks

All training scripts now include automatic version checks via `shared/python_version_check.py`:

```python
from shared.python_version_check import check_python_version
check_python_version()
```

Scripts with version checks:
- `scripts/train_price_model.py`
- `scripts/train_edition_premium_model.py`
- `scripts/stacking/train_ebay_model.py`
- `scripts/stacking/train_abebooks_model.py`
- `scripts/stacking/train_amazon_model.py`
- `scripts/stacking/train_meta_model.py`
- `scripts/stacking/train_alibris_model.py`
- `scripts/stacking/train_biblio_model.py`
- `scripts/stacking/train_zvab_model.py`

If you run a training script with the wrong Python version, you'll see:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                        PYTHON VERSION ERROR                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

This script requires Python 3.11 for XGBoost/OpenMP compatibility.

Current version: 3.13.x
Required version: 3.11.x

SOLUTION:
1. Use the virtual environment:
   .venv/bin/python3 scripts/train_price_model.py

2. Or use Python 3.11 directly:
   /Users/nickcuskey/.pyenv/versions/3.11.13/bin/python3 scripts/train_price_model.py
```

### 3. Convenient Wrapper Script

Use `scripts/ml_train` for all ML training tasks:

```bash
# Train main price model
./scripts/ml_train scripts/train_price_model.py

# Train edition premium model
./scripts/ml_train scripts/train_edition_premium_model.py

# Train stacking ensemble models
./scripts/ml_train scripts/stacking/train_ebay_model.py
./scripts/ml_train scripts/stacking/train_abebooks_model.py
```

The wrapper:
- Ensures Python 3.11 is used
- Sets PYTHONPATH correctly
- Provides clear error messages if version is wrong

## Best Practices

### ✅ DO

```bash
# Use the venv (now Python 3.11)
.venv/bin/python3 scripts/train_price_model.py

# Or use the wrapper script
./scripts/ml_train scripts/train_price_model.py

# Or use Python 3.11 directly with PYTHONPATH
PYTHONPATH=/Users/nickcuskey/ISBN /Users/nickcuskey/.pyenv/versions/3.11.13/bin/python3 scripts/train_price_model.py
```

### ❌ DON'T

```bash
# Don't use system Python (might be 3.13+)
python3 scripts/train_price_model.py

# Don't use wrong Python version
python3.13 scripts/train_price_model.py

# Don't forget PYTHONPATH when not using wrapper
/Users/nickcuskey/.pyenv/versions/3.11.13/bin/python3 scripts/train_price_model.py  # Missing PYTHONPATH
```

## Troubleshooting

### Error: "XGBoost Library could not be loaded"

**Cause**: Using Python 3.13+ instead of Python 3.11

**Solution**: Use one of the approved methods above (venv, wrapper, or direct Python 3.11 with PYTHONPATH)

### Error: "No module named 'shared'"

**Cause**: PYTHONPATH not set correctly

**Solution**: Use the wrapper script or set PYTHONPATH manually:
```bash
PYTHONPATH=/Users/nickcuskey/ISBN .venv/bin/python3 scripts/train_price_model.py
```

### Venv has wrong Python version

**Solution**: Recreate the venv:
```bash
rm -rf .venv
/Users/nickcuskey/.pyenv/versions/3.11.13/bin/python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install xgboost scikit-learn pandas numpy aiohttp beautifulsoup4 lxml
```

## Technical Details

### Why Python 3.11 Specifically?

- **Python 3.11**: Works correctly with XGBoost and OpenMP on ARM64 macOS
- **Python 3.12**: May work but not extensively tested
- **Python 3.13+**: Has known compatibility issues with OpenMP library architecture

### System Information

- OS: macOS ARM64 (Apple Silicon)
- Python 3.11 location: `/Users/nickcuskey/.pyenv/versions/3.11.13/bin/python3`
- OpenMP library: Installed via Homebrew (ARM64)
- XGBoost version: 3.1.1 (verified compatible with Python 3.11)

### Dependencies Requiring Python 3.11

The following packages require Python 3.11 for proper operation:
- `xgboost>=3.0.0` (OpenMP dependency)
- `scikit-learn` (used with XGBoost)

Other packages work with any Python version but are installed in the Python 3.11 venv for consistency.

## Future Considerations

If you upgrade to a newer Python version in the future:

1. **Test XGBoost compatibility first**:
   ```bash
   python3.XX -c "import xgboost; print('OK')"
   ```

2. **If it fails**, check OpenMP library:
   ```bash
   brew info libomp
   python3.XX -c "import xgboost; xgb.XGBRegressor()"
   ```

3. **Update this documentation** if you successfully migrate to a newer Python version

4. **Update `shared/python_version_check.py`** with the new required version

## References

- XGBoost Issue: [Architecture compatibility with OpenMP on ARM64](https://github.com/dmlc/xgboost/issues/)
- OpenMP Installation: `brew install libomp`
- pyenv Python Installation: `pyenv install 3.11.13`
