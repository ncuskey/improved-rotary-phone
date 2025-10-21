# Repository Cleanup Plan
**Generated:** 2025-10-20

## Summary
This plan identifies vestigial files and proposes a cleaner repository structure with better organization for the three apps (Desktop, Web, iOS) and their shared components.

---

## Phase 1: Immediate Deletions (Safe - No Code Impact)

### Temporary/Build Files
```bash
# Delete temporary files that should never be committed
rm -f tmp.jpg
rm -f test-report.xml
rm -f books.db  # 18MB dev database - should be in ~/.isbn_lot_optimizer/
rm -f bookseries_complete.json  # 11MB - move to data/ or fetch on demand
```

### Duplicate Virtual Environment
```bash
# Remove duplicate venv (180MB wasted)
rm -rf ISBN_inner_venv/
```

### Demo Scripts (No longer needed)
```bash
rm -f create_sample_data.py
rm -f create_sample_lots.py
rm -f demo_lot_details.py
```

### Obsolete Deployment Configs
```bash
# Netlify config that explicitly says "DON'T USE NETLIFY"
rm -f netlify.toml

# Keep only the deployment platform you're actually using
# If not using Railway:
rm -f railway.json
# If not using Render:
rm -f render.yaml
```

**Estimated space saved:** ~220MB

---

## Phase 2: Documentation Consolidation

### Files to Merge and Delete

#### Setup Documentation
**Merge into docs/setup/installation.md:**
- LOCAL_SERVER_SETUP.md (486 lines)
- LOCAL_SERVER_QUICKSTART.md (77 lines)

**Action:** Create comprehensive installation guide combining both

#### Deployment Documentation
**Merge into docs/deployment/overview.md:**
- DEPLOYMENT.md (228 lines)
- QUICK_DEPLOY.md (57 lines)

**Action:** Create single deployment guide with platform-specific sections

#### Web App Documentation
**Merge into docs/apps/web.md:**
- WEB_README.md (303 lines)
- MOBILE_OPTIMIZATION.md (122 lines)
- ISBN_WEB_COMMAND.md (162 lines)

**Action:** Consolidate web app documentation

#### Camera Scanner Documentation
**Merge into docs/apps/camera-scanner.md:**
- CAMERA_SCANNER_README.md (166 lines)
- CAMERA_SCANNER_TODO.md (89 lines) → Move todos to GitHub Issues

#### Series Feature Documentation
**Merge into docs/features/series-integration.md:**
- SERIES_INTEGRATION.md (283 lines)
- SERIES_LOTS_FEATURE.md (273 lines)

**Action:** Consolidate series feature documentation

#### Delete After Consolidation
- NETLIFY_README.md (90 lines) - Just says "don't use Netlify"

**Result:** 21 markdown files → ~10 well-organized docs + main README

---

## Phase 3: Test Script Cleanup

### Current Test Scripts
```bash
test_phase2.sh
test_web_comprehensive.sh
test_web_scan.sh
```

**Options:**
1. **Delete if superseded by pytest:** Check if these are redundant
2. **Move to tests/integration/:** If still useful, organize properly
3. **Convert to pytest:** Rewrite as proper Python tests

**Recommendation:** Review each script, convert valuable tests to pytest, delete the rest

---

## Phase 4: Repository Restructure (Major)

### Goals
1. Separate the three apps clearly (desktop, web, iOS)
2. Extract shared components into common module
3. Better organize documentation
4. Move data files out of root

### New Structure

```
apps/
  ├── desktop/        # isbn_lot_optimizer → apps/desktop
  ├── web/            # isbn_web → apps/web
  └── ios/            # LotHelperApp → apps/ios

shared/               # NEW - Common components
  ├── database.py
  ├── models.py
  ├── utils.py
  ├── constants.py
  └── services/
      ├── metadata.py
      ├── market.py
      ├── bookscouter.py
      └── hardcover.py

cli/                  # lothelper → cli

docs/                 # NEW - All documentation
  ├── setup/
  ├── deployment/
  ├── apps/
  ├── features/
  └── development/

data/                 # NEW - Data files
  ├── .gitignore      # Ignore *.db, *.json
  └── samples/

assets/               # NEW - Static assets
  ├── audio/
  └── images/

services/             # NEW - Supporting services
  └── token-broker/

deployment/           # NEW - Deployment configs
  ├── Procfile
  ├── railway.json
  └── render.yaml
```

### Migration Strategy

**Step 1: Create shared module**
```bash
mkdir -p shared/services
# Move common files from isbn_lot_optimizer:
cp isbn_lot_optimizer/database.py shared/
cp isbn_lot_optimizer/models.py shared/
cp isbn_lot_optimizer/utils.py shared/
cp isbn_lot_optimizer/constants.py shared/
# Move service modules
cp isbn_lot_optimizer/metadata.py shared/services/
cp isbn_lot_optimizer/market.py shared/services/
# etc.
```

**Step 2: Update imports**
- Update `isbn_lot_optimizer/` imports to use `shared.*`
- Update `isbn_web/` imports to use `shared.*`
- Test thoroughly after each change

**Step 3: Rename top-level packages**
```bash
git mv isbn_lot_optimizer apps/desktop
git mv isbn_web apps/web
git mv LotHelperApp apps/ios
git mv lothelper cli
git mv token-broker services/token-broker
```

**Step 4: Organize documentation**
```bash
mkdir -p docs/{setup,deployment,apps,features,development}
# Move and merge documentation files
```

**Step 5: Create data and assets directories**
```bash
mkdir -p data/samples
mkdir -p assets/{audio,images}
mv Cha-Ching.mp3 assets/audio/
```

**Step 6: Update all references**
- Update README.md with new structure
- Update CODEMAP.md
- Update requirements.txt paths
- Update deployment configs (Procfile, etc.)
- Update .gitignore

---

## Phase 5: .gitignore Updates

Add these to .gitignore:
```
# Development databases (use ~/.isbn_lot_optimizer/ instead)
books.db
*.db

# Large data files (fetch on demand)
bookseries_complete.json
*_complete.json

# Test outputs
test-report.xml
*.log

# Temporary files
tmp.*
*.tmp

# Data directory contents (except samples)
data/*.db
data/*.json
!data/samples/

# Both venv directories
venv/
ISBN_inner_venv/
```

---

## Scripts to Keep in scripts/

These are useful maintenance scripts - keep them:
- `scrape_bookseries_org.py` - Data collection
- `import_series_data.py` - Data import
- `match_books_to_series.py` - Data processing
- `prefetch_covers.py` - Cache warming
- `verify_series_lots.py` - Validation
- `test_series_lots.py` - Testing

Add a `scripts/README.md` explaining what each does.

---

## Deprecated Code to Address Later

Per REFACTORING_2025.md, these are deprecated but functional:
- `isbn_lot_optimizer/series_index.py`
- `isbn_lot_optimizer/series_catalog.py`
- `isbn_lot_optimizer/series_finder.py`

**Action:** Leave for now (already emit deprecation warnings). Remove in future major version.

---

## Implementation Order

### Quick Wins (Do First)
1. ✅ Delete temporary files (Phase 1) - **5 minutes**
2. ✅ Remove duplicate venv (Phase 1) - **1 minute**
3. ✅ Delete demo scripts (Phase 1) - **1 minute**
4. ✅ Update .gitignore (Phase 5) - **2 minutes**

### Medium Effort
5. ⏳ Consolidate documentation (Phase 2) - **2-3 hours**
6. ⏳ Review/cleanup test scripts (Phase 3) - **1 hour**

### Major Refactor (Plan Carefully)
7. 🎯 Restructure repository (Phase 4) - **1-2 days**
   - Requires thorough testing
   - Update all imports
   - Update deployment configs
   - Coordinate with any active development

---

## Benefits of Restructure

### Before
```
isbn_lot_optimizer/    # Desktop app + shared code (unclear boundary)
isbn_web/              # Web app + some duplicate code
LotHelperApp/          # iOS app
lothelper/             # CLI tools (confusing name)
21 markdown files      # Documentation scattered
```

### After
```
apps/                  # Clear app boundaries
  ├── desktop/
  ├── web/
  └── ios/

shared/                # Explicit shared components
  └── services/

cli/                   # Clear CLI tools

docs/                  # Organized documentation
  ├── setup/
  ├── deployment/
  ├── apps/
  ├── features/
  └── development/

data/                  # Data files separate from code
assets/                # Static assets organized
services/              # Supporting services
deployment/            # Deployment configs
```

**Advantages:**
- ✅ Clear separation of concerns
- ✅ Easier onboarding for new developers
- ✅ Better code reuse (explicit `shared` module)
- ✅ Simpler imports (`from shared.services import metadata`)
- ✅ Documentation organized by purpose
- ✅ Deployment configs in one place
- ✅ ~220MB saved immediately

---

## Testing Checklist

After each phase, verify:
- [ ] Desktop GUI launches and scans work
- [ ] Web app starts and core features work
- [ ] iOS app can fetch data from backend
- [ ] CLI tools execute successfully
- [ ] pytest suite passes
- [ ] Documentation links work
- [ ] Deployment configs still valid

---

## Questions Before Starting?

1. **Which deployment platform are you using?** (Railway, Render, both, neither?)
2. **Are the test shell scripts still useful?** (Or has pytest replaced them?)
3. **Do you want to keep the deprecated series modules?** (Or remove them now?)
4. **How aggressive should we be?** (Quick cleanup only, or full restructure?)
5. **Is there active development?** (Need to coordinate timing?)

---

**Next Steps:** Choose your approach and I can help execute any phase!
