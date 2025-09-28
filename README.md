<<<<<<< HEAD
# Improved Rotary Phone (ISBN Lot Optimizer)

Improved Rotary Phone is a desktop and CLI toolkit for cataloguing second-hand
books, estimating resale value, and assembling profitable eBay lots. The GUI is
built with Tkinter and drives a background service that persists scans,
retrieves market intelligence, and updates lot recommendations in real time.

## Highlights
- Barcode-friendly GUI for scanning ISBNs with condition and edition tracking.
- Background refresh jobs with unified progress feedback for cover prefetching
  and metadata/market updates.
- eBay Finding API integration for sell-through and pricing statistics.
- Monte Carlo based lot optimiser that favours cohesive sets and recency.
- Persistent SQLite catalogue stored in `~/.isbn_lot_optimizer/` with optional
  CSV import/export workflows.

## Quick Start
1. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. (Optional) expose eBay credentials for richer market data:
   ```bash
   export EBAY_APP_ID=<your-app-id>
   ```
3. Launch the GUI:
   ```bash
   python -m isbn_lot_optimizer
   ```
4. Scan or type an ISBN, choose a condition, and press Enter. The app persists
   the book, runs metadata + market lookups, refreshes lot recommendations, and
   updates the status bar with progress as background jobs complete.

## Command Line Usage
The toolkit also supports headless workflows. Examples:

```bash
# Import a CSV of ISBNs
python -m isbn_lot_optimizer --no-gui --import data/isbn_batch.csv

# Scan a single ISBN without opening the GUI
python -m isbn_lot_optimizer --no-gui --scan 9780316769488 --condition "Very Good"

# Refresh metadata for the latest titles
python -m isbn_lot_optimizer --no-gui --refresh-metadata --limit 100
```

## Development Notes
- Source lives in `isbn_lot_optimizer/`; see `CODEMAP.md` for an overview.
- Run a quick syntax check before committing:
  ```bash
  python -m py_compile isbn_lot_optimizer/*.py
  ```
- The GUI uses background threads for long-running operations. Any new service
  hooks should report progress through `_start_progress`, `_update_progress`,
  and `_finish_progress` to keep the status bar accurate.

## Licensing
This repository currently ships without an explicit licence. Add one before
publishing binaries or distributing widely.
=======
# improved-rotary-phone
LotHelper
>>>>>>> 659cfea46e2523246e71b66e56a4f568641ab4cb
