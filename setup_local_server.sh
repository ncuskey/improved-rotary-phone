#!/bin/bash
# LotHelper Local Server Setup Script for Mac Mini
# This script sets up the web app to run automatically on boot

set -e  # Exit on error

echo "🚀 LotHelper Local Server Setup"
echo "================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
WEBAPP_DIR="$SCRIPT_DIR/isbn_web"

# Check if we're in the right directory
if [ ! -d "$WEBAPP_DIR" ]; then
    echo "❌ Error: isbn_web directory not found!"
    echo "   Make sure you're running this from the ISBN project root"
    exit 1
fi

# Check if Python is installed
if ! command -v python &> /dev/null; then
    echo "❌ Error: python not found!"
    exit 1
fi

# Get Python path
PYTHON_PATH=$(which python)
echo "✓ Found python at: $PYTHON_PATH"

# Check if uvicorn is installed
if ! python -c "import uvicorn" 2>/dev/null; then
    echo "❌ Error: uvicorn not installed!"
    echo "   Installing required dependencies..."
    pip install -r "$SCRIPT_DIR/requirements.txt"
fi

echo "✓ Dependencies installed"

# Create logs directory
LOGS_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOGS_DIR"
echo "✓ Created logs directory: $LOGS_DIR"

# Create the launchd plist file
PLIST_FILE="$HOME/Library/LaunchAgents/com.lothelper.webapp.plist"

echo "📝 Creating launchd service configuration..."

cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lothelper.webapp</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>isbn_web.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <true/>
    
    <key>StandardOutPath</key>
    <string>$LOGS_DIR/lothelper-stdout.log</string>
    
    <key>StandardErrorPath</key>
    <string>$LOGS_DIR/lothelper-stderr.log</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
EOF

echo "✓ Created service file: $PLIST_FILE"

# Unload if already running
if launchctl list | grep -q "com.lothelper.webapp"; then
    echo "⚠️  Service already running, stopping it first..."
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
fi

# Load the service
echo "🔄 Loading service..."
launchctl load "$PLIST_FILE"

# Wait a moment for the service to start
sleep 2

# Check if it's running
if launchctl list | grep -q "com.lothelper.webapp"; then
    echo "✅ Service loaded successfully!"
else
    echo "⚠️  Service may not be running. Check logs:"
    echo "   tail -f $LOGS_DIR/lothelper-stderr.log"
    exit 1
fi

# Get local IP
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "unknown")
HOSTNAME=$(hostname)

echo ""
echo "🎉 Setup Complete!"
echo "=================="
echo ""
echo "Your LotHelper server is now running and will start automatically on boot."
echo ""
echo "Access the web app from:"
echo "  • This Mac:          http://localhost:8000"
echo "  • Local network IP:  http://$LOCAL_IP:8000"
echo "  • Hostname:          http://$HOSTNAME:8000"
echo ""
echo "Service Management Commands:"
echo "  • Stop:    launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist"
echo "  • Start:   launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist"
echo "  • Restart: Run unload then load"
echo ""
echo "View Logs:"
echo "  • tail -f $LOGS_DIR/lothelper-stdout.log"
echo "  • tail -f $LOGS_DIR/lothelper-stderr.log"
echo ""
echo "For more information, see LOCAL_SERVER_SETUP.md"
echo ""

# Test if server is responding
echo "Testing server..."
sleep 1
if curl -s http://localhost:8000 > /dev/null; then
    echo "✅ Server is responding!"
else
    echo "⚠️  Server may not be ready yet. Wait a few seconds and try:"
    echo "   curl http://localhost:8000"
fi

echo ""
echo "🖥️  Your Mac Mini is now a LotHelper server!"
