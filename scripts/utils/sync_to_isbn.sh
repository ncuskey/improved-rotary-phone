#!/bin/bash
# Sync changes from improved-rotary-phone to ISBN directory for isbn-web shortcut
# Usage: ./sync_to_isbn.sh

set -e

SOURCE_DIR="/Users/nickcuskey/improved-rotary-phone"
TARGET_DIR="/Users/nickcuskey/ISBN"

echo "🔄 Syncing changes to ISBN directory for isbn-web shortcut..."
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo ""

# Web templates and components
echo "📄 Syncing web templates..."
cp "$SOURCE_DIR/isbn_web/templates/base.html" "$TARGET_DIR/isbn_web/templates/base.html"
cp "$SOURCE_DIR/isbn_web/templates/lot_details.html" "$TARGET_DIR/isbn_web/templates/lot_details.html"
cp "$SOURCE_DIR/isbn_web/templates/components/lot_detail.html" "$TARGET_DIR/isbn_web/templates/components/lot_detail.html"
cp "$SOURCE_DIR/isbn_web/templates/components/lots_table.html" "$TARGET_DIR/isbn_web/templates/components/lots_table.html"
cp "$SOURCE_DIR/isbn_web/templates/components/carousel.html" "$TARGET_DIR/isbn_web/templates/components/carousel.html"
cp "$SOURCE_DIR/isbn_web/templates/components/lot_edit_form.html" "$TARGET_DIR/isbn_web/templates/components/lot_edit_form.html"

# API routes
echo "🔌 Syncing API routes..."
cp "$SOURCE_DIR/isbn_web/api/routes/lots.py" "$TARGET_DIR/isbn_web/api/routes/lots.py"

# Service layer
echo "⚙️ Syncing service layer..."
cp "$SOURCE_DIR/isbn_lot_optimizer/service.py" "$TARGET_DIR/isbn_lot_optimizer/service.py"

echo ""
echo "✅ Sync complete!"
echo ""
echo "🔄 Restarting isbn-web server..."
pkill -f 'uvicorn isbn_web.main:app' || true
sleep 2
isbn-web &
echo ""
echo "🎉 Ready! The isbn-web shortcut now has the latest changes."
echo ""
