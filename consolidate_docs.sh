#!/bin/bash
# Phase 2 - Move remaining documentation files to docs/

# App documentation
cp IOS_APP.md docs/apps/ios.md
cp CAMERA_SCANNER_README.md docs/apps/camera-scanner.md
cp WEB_README.md docs/apps/web-temp.md
cp MOBILE_OPTIMIZATION.md docs/apps/mobile-temp.md
cp ISBN_WEB_COMMAND.md docs/apps/commands-temp.md

# Feature documentation
cp SERIES_INTEGRATION.md docs/features/series-integration-temp.md
cp SERIES_LOTS_FEATURE.md docs/features/series-lots-temp.md
cp SOLD_COMPS.md docs/features/sold-comps.md

# Development documentation
cp CODEMAP.md docs/development/codemap.md
cp REFACTORING_2025.md docs/development/refactoring-2025.md
cp CHANGELOG.md docs/development/changelog.md

# Todo
cp AUTOSTART.md docs/todo/autostart.md
cp CAMERA_SCANNER_TODO.md docs/todo/camera-scanner.md

echo "✓ Documentation files copied to docs/"
echo "  Note: Some files marked -temp need manual merging"
echo "  See PHASE2_STATUS.md for details"
