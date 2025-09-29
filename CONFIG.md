
# Configuration

The app uses a local SQLite database and optional API credentials.

## Database
- Path: `~/.isbn_lot_optimizer/catalog.db`
- Tables: `books`, `lots`

## Environment Variables
- `EBAY_APP_ID` (optional): eBay Finding API App ID to enable sell-through and price comps.
- `HTTP_PROXY` / `HTTPS_PROXY` (optional): if you need to route requests through a proxy.

Create a local `.env` (or export in your shell) to set variables, e.g.:

```bash
export EBAY_APP_ID=your-app-id
```

## Tunables (edit in-code)
- Minimum single-listing price: `$10` (see `probability.py` → `score_probability` under "Single-item resale under $10").
- Condition weights: `CONDITION_WEIGHTS` in `probability.py`.
- Edition bonus: `EDITION_KEYWORDS` in `probability.py`.
- Demand keywords: `HIGH_DEMAND_KEYWORDS` in `probability.py`.

## Author Cleanup & Thumbnails
- The GUI includes an interactive Author Cleanup reviewer (Tools → Author Cleanup…) that lets you normalize author names cluster-by-cluster with visual context.
- Sample book thumbnails are displayed to help verify the correct author form.
- Thumbnails are fetched from metadata sources (Google Books/Open Library) and cached under `~/.isbn_lot_optimizer/covers/` with SHA-256 filenames.
- Image support uses `Pillow` and `requests` (both listed in `requirements.txt`). If these libraries are not available, the reviewer still works but will omit thumbnails.
