# Installation Guide

Complete setup instructions for the ISBN Lot Optimizer (Improved Rotary Phone).

---

## Quick Start

### 1. Clone and Install Dependencies

```bash
# Clone the repository
git clone <repository-url>
cd ISBN

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)

Create a `.env` file in the project root:

```bash
# eBay APIs
export EBAY_APP_ID=your-finding-app-id              # Finding API (sold/unsold)
export EBAY_CLIENT_ID=your-browse-client-id         # Browse API (active comps)
export EBAY_CLIENT_SECRET=your-browse-client-secret
export EBAY_MARKETPLACE=EBAY_US                     # Optional (default)

# BookScouter (multi-vendor buyback)
export BOOKSCOUTER_API_KEY=your-bookscouter-api-key

# BooksRun (CLI bulk quotes only)
export BOOKSRUN_KEY=your-booksrun-api-key

# Hardcover (series detection)
export HARDCOVER_API_TOKEN=Bearer your-hardcover-token

# Optional proxy
export HTTP_PROXY=http://proxy:8080
export HTTPS_PROXY=http://proxy:8080
```

See [Configuration](configuration.md) for detailed environment variable documentation.

### 3. Launch the Application

**Desktop GUI:**
```bash
python -m isbn_lot_optimizer
```

**Web Interface:**
```bash
uvicorn isbn_web.main:app --reload
# Visit http://localhost:8000
```

**CLI Tools:**
```bash
python -m lothelper booksrun-sell --in isbns.csv --out quotes.csv
```

---

## Local Server Setup (Mac Mini)

Run the web app on your Mac Mini as a persistent server accessible from other devices.

### Quick Start - One Command

```bash
cd /Users/nickcuskey/ISBN
./setup_local_server.sh
```

This automatically:
- ✅ Sets up the FastAPI web server
- ✅ Configures auto-start on boot
- ✅ Creates log directories
- ✅ Makes it accessible from your local network

### Manual Setup

#### Find Your Mac Mini's Local IP

```bash
ipconfig getifaddr en0  # WiFi
# or
ipconfig getifaddr en1  # Ethernet
```

Example: `192.168.1.100`

#### Start Server Manually (Testing)

```bash
cd isbn_web
uvicorn main:app --host 0.0.0.0 --port 8000
```

Access from any device on your network:
- `http://192.168.1.100:8000`
- Or `http://macmini.local:8000`

---

## Permanent Local Server (launchd)

### Create Launch Agent

```bash
mkdir -p ~/Library/LaunchAgents
mkdir -p /Users/nickcuskey/ISBN/logs

cat > ~/Library/LaunchAgents/com.lothelper.webapp.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lothelper.webapp</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/uvicorn</string>
        <string>main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/nickcuskey/ISBN/isbn_web</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/nickcuskey/ISBN/logs/lothelper-stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/nickcuskey/ISBN/logs/lothelper-stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
EOF
```

### Load the Service

```bash
# Start the service
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist

# Check if running
launchctl list | grep lothelper
curl http://localhost:8000
```

### Service Management

```bash
# Start
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist

# Stop
launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist

# Restart
launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist && \
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist

# View logs
tail -f /Users/nickcuskey/ISBN/logs/lothelper-stdout.log
tail -f /Users/nickcuskey/ISBN/logs/lothelper-stderr.log
```

### Alternative: Screen Session

For temporary sessions without auto-start:

```bash
# Start detached session
screen -S lothelper

# Run server (inside screen)
cd /Users/nickcuskey/ISBN/isbn_web
uvicorn main:app --host 0.0.0.0 --port 8000

# Detach: Ctrl+A, then D
# Reattach: screen -r lothelper
# Kill: screen -X -S lothelper quit
```

---

## Network Access

### Access from Local Devices

Once running on `0.0.0.0:8000`, any device on your network can access:

**iPhone/iPad:**
- Open Safari → `http://192.168.1.100:8000`
- Or `http://macmini.local:8000`

**Another Mac/PC:**
- Any browser → `http://192.168.1.100:8000`

### Set Static IP (Recommended)

Prevent IP address changes:

1. **System Settings** → **Network**
2. Select connection (WiFi/Ethernet)
3. **Details** → **TCP/IP**
4. **Configure IPv4** → **Using DHCP with manual address**
5. Enter desired IP: `192.168.1.100`
6. Click **OK**

### Use Hostname (Easier)

```bash
# Check hostname
hostname
# Example: macmini.local
```

Access from any device: `http://macmini.local:8000`

---

## Database Configuration

### SQLite (Default - Recommended)

Zero configuration needed! Database auto-created at:
- `~/.isbn_lot_optimizer/catalog.db`

**Pros:**
- ✅ No setup required
- ✅ Fast for single user
- ✅ Perfect for local network

**Cons:**
- ❌ One concurrent writer
- ❌ Not ideal for many simultaneous users

### PostgreSQL (Optional)

For multiple simultaneous users:

```bash
# Install
brew install postgresql@14
brew services start postgresql@14

# Create database
createdb isbn_optimizer

# Set environment
export DATABASE_URL="postgresql://localhost/isbn_optimizer"

# Run migrations (if needed)
python -m isbn_lot_optimizer.database
```

---

## Performance Tuning

### Multiple Users

```bash
# Run with multiple workers
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Monitor Resources

```bash
# Check memory usage
top -pid $(pgrep -f "uvicorn main:app")

# Check port usage
lsof -i :8000
```

---

## Security

### Local Network Only (Default)

By default, accessible only from local network:
- ✅ Safe from internet attacks
- ✅ No firewall configuration needed
- ✅ Fast local speeds

### Add Authentication (Optional)

See [Configuration](configuration.md) for HTTP Basic Auth setup.

### Firewall

macOS Firewall is usually off. If enabled:
- Allow Python/uvicorn
- Or add exception for port 8000

---

## Maintenance

### Backup Database

**SQLite:**
```bash
# Backup
cp ~/.isbn_lot_optimizer/catalog.db \
   backups/catalog_$(date +%Y%m%d).db

# Restore
cp backups/catalog_20250101.db \
   ~/.isbn_lot_optimizer/catalog.db
```

**PostgreSQL:**
```bash
pg_dump isbn_optimizer > backup.sql
psql isbn_optimizer < backup.sql
```

### Update Application

```bash
# Stop service
launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist

# Update code
git pull

# Install dependencies
source .venv/bin/activate
pip install -r requirements.txt

# Start service
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist
```

### View Logs

```bash
# Real-time logs
tail -f logs/lothelper-stdout.log

# Errors only
tail -f logs/lothelper-stderr.log

# Search logs
grep "error" logs/*.log
```

---

## Troubleshooting

### Server Won't Start

**Port already in use:**
```bash
lsof -i :8000
# Kill the process or use different port
```

**Check logs:**
```bash
tail -f logs/lothelper-stderr.log
```

### Can't Access from Other Devices

**Verify IP:**
```bash
ipconfig getifaddr en0
```

**Test locally:**
```bash
curl http://localhost:8000
```

**Ping from other device:**
```bash
ping 192.168.1.100
# or
ping macmini.local
```

**Check Firewall:**
- System Settings → Network → Firewall
- Add exception for port 8000 if enabled

### Database Locked

SQLite limitation - one write at a time. Solutions:
- Use PostgreSQL for multiple users
- Reduce concurrent write operations

---

## Local vs Cloud Comparison

| Feature | Mac Mini Server | Railway/Render |
|---------|----------------|----------------|
| Cost | ✅ Free (electricity) | 💰 Monthly fee |
| Speed | ✅ Very fast (local) | 🌐 Internet dependent |
| Setup | ⚙️ One-time | ☁️ Quick deploy |
| Maintenance | 🔧 You manage | ✅ Auto-managed |
| Access | 🏠 Local network | 🌍 Anywhere |
| Privacy | ✅ Your hardware | ☁️ Their servers |

**Best for:**
- **Local Server:** Home use, multiple devices, full control
- **Cloud:** Remote access, sharing outside network

---

## Remote Access (Optional)

### Tailscale (Recommended)

Secure remote access without port forwarding:

1. Install: https://tailscale.com/download/mac
2. Connect your Mac Mini
3. Install on other devices
4. Access: `http://100.x.x.x:8000`

### ngrok (Temporary)

Quick temporary public URL:

```bash
brew install ngrok
ngrok http 8000
# Use provided URL
```

**Note:** Free tier has limits, URL changes each session.

---

## Summary

**Quick setup:**
```bash
cd isbn_web
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Permanent service:**
- Use launchd config above
- Auto-starts on boot
- Runs 24/7

**Access:**
- Local: `http://macmini.local:8000`
- Or: `http://192.168.1.100:8000`

**Next steps:**
- [Configuration](configuration.md) - Environment variables and settings
- [Deployment](../deployment/overview.md) - Cloud deployment options
