# Phase 4: Major Repository Restructure

**Goal:** Separate the three apps cleanly and extract shared components into a common module.

---

## Proposed Structure

```
ISBN/
├── apps/
│   ├── desktop/              # Desktop GUI (from isbn_lot_optimizer)
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── app.py            # CLI argument parsing
│   │   ├── gui.py            # Tkinter GUI
│   │   └── features/
│   │       ├── clipboard_import.py
│   │       └── bulk_helper.py
│   │
│   ├── web/                  # Web app (from isbn_web)
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   ├── templates/
│   │   ├── static/
│   │   └── services/
│   │
│   ├── ios/                  # iOS app (LotHelperApp - no change)
│   │   └── LotHelper/
│   │
│   └── cli/                  # CLI tools (from lothelper)
│       ├── __init__.py
│       ├── __main__.py
│       └── commands/
│
├── shared/                   # Common components (NEW!)
│   ├── __init__.py
│   ├── database.py           # DatabaseManager
│   ├── models.py             # Data classes
│   ├── constants.py          # Shared constants
│   ├── utils.py              # ISBN normalization, helpers
│   │
│   ├── services/             # External API integrations
│   │   ├── __init__.py
│   │   ├── metadata.py       # Google Books, OpenLibrary
│   │   ├── market.py         # eBay Finding + Browse
│   │   ├── ebay_auth.py      # OAuth
│   │   ├── bookscouter.py    # Multi-vendor buyback
│   │   ├── booksrun.py       # BooksRun API
│   │   └── hardcover.py      # Hardcover series API
│   │
│   ├── series/               # Series detection
│   │   ├── __init__.py
│   │   ├── integration.py    # Main integration
│   │   ├── database.py       # Series database ops
│   │   ├── matcher.py        # Fuzzy matching
│   │   └── lots.py           # Series lot generation
│   │
│   └── lots/                 # Lot generation
│       ├── __init__.py
│       ├── generator.py      # Lot generation (from lots.py)
│       ├── scoring.py        # Scoring logic (from lot_scoring.py)
│       ├── market.py         # Market snapshots (from lot_market.py)
│       └── probability.py    # Probability scoring
│
├── services/                 # Supporting services
│   └── token-broker/
│
├── scripts/                  # Maintenance scripts
├── tests/                    # All tests
├── docs/                     # Documentation
├── data/                     # Data files
└── README.md
```

---

## Categorization

### Shared Components (Goes to `shared/`)

**Core:**
- `database.py` - Used by all apps
- `models.py` - Data structures used everywhere
- `constants.py` - Shared constants
- `utils.py` - ISBN normalization, helpers
- `author_aliases.py` - Author canonicalization
- `author_match.py` - Author matching logic

**Services (External APIs):**
- `metadata.py` - Metadata APIs
- `market.py` - eBay market data
- `ebay_auth.py` - OAuth
- `ebay_sold_comps.py` - eBay sold comps
- `bookscouter.py` - BookScouter API
- `booksrun.py` - BooksRun API
- `services/hardcover.py` - Already in services/

**Series:**
- `series_integration.py`
- `series_database.py`
- `series_matcher.py`
- `series_lots.py`
- Deprecated: `series_index.py`, `series_catalog.py`, `series_finder.py`

**Lots:**
- `lots.py` → `shared/lots/generator.py`
- `lot_scoring.py` → `shared/lots/scoring.py`
- `lot_market.py` → `shared/lots/market.py`
- `probability.py` → `shared/lots/probability.py`
- `book_routing.py` - Book routing logic

**Business Logic:**
- `service.py` - BookService (core business logic, stays shared)

### Desktop App Specific (Goes to `apps/desktop/`)

- `__init__.py`
- `__main__.py`
- `app.py` - CLI argument parsing
- `gui.py` - Tkinter GUI
- `clipboard_import.py` - Clipboard parsing
- `bulk_helper.py` - Vendor bundle optimization

### Web App Specific (Already in `isbn_web/`)

- Just rename `isbn_web/` → `apps/web/`
- Already well-structured

### CLI Tools (Goes to `apps/cli/`)

- Rename `lothelper/` → `apps/cli/`

---

## Migration Steps

### Step 1: Create New Structure

```bash
mkdir -p shared/{services,series,lots}
mkdir -p apps/{desktop,web,cli}
```

### Step 2: Move Shared Components

```bash
# Core
mv isbn_lot_optimizer/database.py shared/
mv isbn_lot_optimizer/models.py shared/
mv isbn_lot_optimizer/constants.py shared/
mv isbn_lot_optimizer/utils.py shared/
mv isbn_lot_optimizer/author_aliases.py shared/
mv isbn_lot_optimizer/author_match.py shared/
mv isbn_lot_optimizer/service.py shared/

# Services
mv isbn_lot_optimizer/metadata.py shared/services/
mv isbn_lot_optimizer/market.py shared/services/
mv isbn_lot_optimizer/ebay_auth.py shared/services/
mv isbn_lot_optimizer/ebay_sold_comps.py shared/services/
mv isbn_lot_optimizer/bookscouter.py shared/services/
mv isbn_lot_optimizer/booksrun.py shared/services/
mv isbn_lot_optimizer/services/hardcover.py shared/services/
mv isbn_lot_optimizer/services/series_resolver.py shared/services/

# Series
mv isbn_lot_optimizer/series_integration.py shared/series/integration.py
mv isbn_lot_optimizer/series_database.py shared/series/database.py
mv isbn_lot_optimizer/series_matcher.py shared/series/matcher.py
mv isbn_lot_optimizer/series_lots.py shared/series/lots.py
# Deprecated (keep for now)
mv isbn_lot_optimizer/series_*.py shared/series/

# Lots
mv isbn_lot_optimizer/lots.py shared/lots/generator.py
mv isbn_lot_optimizer/lot_scoring.py shared/lots/scoring.py
mv isbn_lot_optimizer/lot_market.py shared/lots/market.py
mv isbn_lot_optimizer/probability.py shared/lots/probability.py
mv isbn_lot_optimizer/book_routing.py shared/lots/routing.py
```

### Step 3: Move Desktop App

```bash
# Move desktop app
mv isbn_lot_optimizer apps/desktop

# Move specific features
mkdir -p apps/desktop/features
mv apps/desktop/clipboard_import.py apps/desktop/features/
mv apps/desktop/bulk_helper.py apps/desktop/features/
```

### Step 4: Move Web App

```bash
mv isbn_web apps/web
```

### Step 5: Move CLI

```bash
mv lothelper apps/cli
```

### Step 6: Update Imports

This is the tedious part - update all imports from:
```python
from isbn_lot_optimizer.database import DatabaseManager
```

To:
```python
from shared.database import DatabaseManager
```

**Files to update:**
- `apps/desktop/*.py`
- `apps/web/api/routes/*.py`
- `apps/web/services/*.py`
- `apps/cli/*.py`
- `shared/**/*.py` (internal imports)
- `tests/*.py`
- `scripts/*.py`

### Step 7: Update Entry Points

**Desktop:**
```python
# apps/desktop/__main__.py
from apps.desktop.app import main
```

**Web:**
```python
# apps/web/main.py
from shared.database import DatabaseManager
from shared.service import BookService
```

**CLI:**
```python
# apps/cli/__main__.py
from apps.cli.commands.booksrun_sell import main
```

### Step 8: Update Configuration Files

- `Procfile` - Update path to web app
- `railway.json` - Update start command
- `render.yaml` - Update start command
- `launch.sh` - Update module path
- `setup_local_server.sh` - Update paths
- `.mdc` - Update structure docs

---

## Import Changes Required

### Before (Current)
```python
from isbn_lot_optimizer.database import DatabaseManager
from isbn_lot_optimizer.models import BookMetadata
from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.utils import normalise_isbn
from isbn_lot_optimizer.metadata import get_metadata
from isbn_lot_optimizer.market import get_ebay_data
from isbn_lot_optimizer.bookscouter import get_buyback_quotes
from isbn_lot_optimizer.lots import generate_lots
from isbn_lot_optimizer.probability import score_probability
from isbn_web.config import get_settings
from lothelper.vendors.booksrun_client import BooksRunClient
```

### After (Phase 4)
```python
from shared.database import DatabaseManager
from shared.models import BookMetadata
from shared.service import BookService
from shared.utils import normalise_isbn
from shared.services.metadata import get_metadata
from shared.services.market import get_ebay_data
from shared.services.bookscouter import get_buyback_quotes
from shared.lots.generator import generate_lots
from shared.lots.probability import score_probability
from apps.web.config import get_settings
from apps.cli.vendors.booksrun_client import BooksRunClient
```

---

## Risks & Considerations

### High Risk
- **Import updates** - Must update ~50+ files with imports
- **Circular imports** - Shared modules importing each other
- **Entry points** - `__main__.py` files need correct paths
- **Tests** - All test imports need updating

### Medium Risk
- **Deployment configs** - Procfile, railway.json, etc.
- **Scripts** - All maintenance scripts import core modules
- **Documentation** - .mdc and docs need updating

### Low Risk
- **iOS app** - Doesn't import Python modules, no changes needed
- **Token broker** - Standalone Node.js, no changes
- **Data files** - Just files, no code changes

---

## Testing Strategy

After each major step:

1. **Syntax check:**
   ```bash
   python -m py_compile shared/**/*.py
   python -m py_compile apps/desktop/**/*.py
   python -m py_compile apps/web/**/*.py
   ```

2. **Import check:**
   ```bash
   python -c "from shared.database import DatabaseManager"
   python -c "from shared.service import BookService"
   python -c "from apps.web.main import app"
   ```

3. **Run tests:**
   ```bash
   pytest tests/
   ```

4. **Launch apps:**
   ```bash
   python -m apps.desktop --no-gui --stats
   uvicorn apps.web.main:app
   python -m apps.cli --help
   ```

---

## Rollback Plan

If something breaks badly:
```bash
git reset --hard HEAD~1
```

Or revert specific files:
```bash
git checkout HEAD~1 -- path/to/file
```

---

## Benefits After Phase 4

✅ **Clear separation** - Each app is independent
✅ **Explicit sharing** - `shared/` module shows what's common
✅ **Better imports** - `from shared.*` is clearer than `from isbn_lot_optimizer.*`
✅ **Easier testing** - Test shared components independently
✅ **Simpler onboarding** - New developers understand structure immediately
✅ **Future-proof** - Easy to add new apps (e.g., Android app)

---

## Estimated Time

- Planning & setup: 30 minutes ✓
- Moving files: 30 minutes
- Updating imports: 2-3 hours (tedious but straightforward)
- Testing & fixing: 1-2 hours
- Documentation updates: 30 minutes

**Total: 4-6 hours**

---

## Alternative: Incremental Approach

Instead of moving everything at once:

1. **Phase 4a:** Create `shared/` and move database.py + models.py only
2. **Phase 4b:** Move services one at a time
3. **Phase 4c:** Move lots modules
4. **Phase 4d:** Rename apps directories

This reduces risk but takes longer overall.

---

**Decision Point:** Full restructure now, or incremental approach?
