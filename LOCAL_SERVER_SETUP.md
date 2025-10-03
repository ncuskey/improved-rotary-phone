# LotHelper Local Server Setup - Mac Mini

This guide shows you how to run the LotHelper web app on your Mac Mini as a persistent server accessible from other devices on your local network.

## Overview

Your Mac Mini will:
- ✅ Run the FastAPI web server 24/7
- ✅ Be accessible from any device on your local network
- ✅ Use a local SQLite database (or PostgreSQL if preferred)
- ✅ Auto-start when the Mac boots
- ✅ No internet connection required (except for ISBN lookups)

## Quick Start

### Step 1: Find Your Mac Mini's Local IP

```bash
# Get your local IP address
ipconfig getifaddr en0  # WiFi
# or
ipconfig getifaddr en1  # Ethernet
```

Example output: `192.168.1.100`

### Step 2: Start the Server

```bash
cd /Users/nickcuskey/ISBN/isbn_web
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Step 3: Access from Any Device

From any device on your network:
- Open browser to: `http://192.168.1.100:8000`
- Replace `192.168.1.100` with your Mac Mini's IP

That's it! 🎉

---

## Permanent Setup

For a production-ready local server that auto-starts:

### Option 1: Using launchd (macOS Native - Recommended)

Create a launchd service that starts automatically:

1. **Create the launch agent file:**

```bash
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

2. **Create logs directory:**

```bash
mkdir -p /Users/nickcuskey/ISBN/logs
```

3. **Load the service:**

```bash
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist
```

4. **Check if it's running:**

```bash
launchctl list | grep lothelper
curl http://localhost:8000
```

**Service Management Commands:**

```bash
# Start
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist

# Stop
launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist

# Restart (stop then start)
launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist && \
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist

# View logs
tail -f /Users/nickcuskey/ISBN/logs/lothelper-stdout.log
tail -f /Users/nickcuskey/ISBN/logs/lothelper-stderr.log
```

### Option 2: Using Screen (Simpler, Manual)

Run the server in a detached screen session:

```bash
# Start a screen session
screen -S lothelper

# Inside screen, run the server
cd /Users/nickcuskey/ISBN/isbn_web
uvicorn main:app --host 0.0.0.0 --port 8000

# Detach from screen: Press Ctrl+A, then D

# Reattach later
screen -r lothelper

# Kill the session
screen -X -S lothelper quit
```

---

## Network Access Setup

### Access from Local Network

Once running on `0.0.0.0:8000`, any device on your network can access it:

**From iPhone/iPad:**
- Open Safari
- Go to `http://192.168.1.100:8000`

**From Another Mac/PC:**
- Open browser
- Go to `http://192.168.1.100:8000`

**From Windows:**
- Same URL in any browser

### Set a Static IP (Recommended)

To prevent your Mac Mini's IP from changing:

1. **System Settings** → **Network**
2. Select your connection (WiFi or Ethernet)
3. Click **Details**
4. Go to **TCP/IP** tab
5. Change **Configure IPv4** to **Using DHCP with manual address**
6. Enter your desired IP: `192.168.1.100`
7. Click **OK**

### Use a Hostname (Even Better)

Instead of remembering the IP, use the Mac's hostname:

```bash
# Check your hostname
hostname

# Example: macmini.local
```

Then access from any device:
- `http://macmini.local:8000`

Much easier to remember!

---

## Database Configuration

### Option 1: SQLite (Default - Easiest)

The app uses SQLite by default - no setup needed!

Database location: `/Users/nickcuskey/ISBN/isbn_web/isbn_optimizer.db`

**Pros:**
- ✅ Zero configuration
- ✅ Fast for single user
- ✅ Perfect for local network

**Cons:**
- ❌ One concurrent writer
- ❌ Not ideal for many users

### Option 2: PostgreSQL (If Needed)

For multiple simultaneous users:

```bash
# Install PostgreSQL
brew install postgresql@14

# Start PostgreSQL
brew services start postgresql@14

# Create database
createdb isbn_optimizer

# Set DATABASE_URL
export DATABASE_URL="postgresql://localhost/isbn_optimizer"

# Run migrations (if needed)
cd /Users/nickcuskey/ISBN
python -m isbn_lot_optimizer.database
```

---

## Security & Access Control

### Local Network Only (Default)

By default, your server is only accessible from your local network.
- ✅ Safe from internet attacks
- ✅ No firewall configuration needed
- ✅ Fast local speeds

### Add Basic Authentication (Optional)

If you want password protection:

1. **Install httpx:**
```bash
pip install python-multipart
```

2. **Add to your FastAPI app** (in `isbn_web/main.py`):

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "yourpassword")
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    return credentials.username

# Add to your routes
@app.get("/", dependencies=[Depends(verify_credentials)])
async def read_root():
    # Your code here
```

### Firewall

macOS Firewall is usually off by default. If enabled:
- Allow incoming connections to Python/uvicorn
- Or add exception for port 8000

---

## Performance Tuning

### For Multiple Users

If multiple people will use it simultaneously:

```bash
# Run with more workers
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Memory Management

Monitor resource usage:
```bash
# Check memory usage
top -pid $(pgrep -f "uvicorn main:app")

# Check port
lsof -i :8000
```

---

## Troubleshooting

### Server Won't Start

**Check if port is in use:**
```bash
lsof -i :8000
# If something is using it, kill it or use a different port
```

**Check logs:**
```bash
tail -f /Users/nickcuskey/ISBN/logs/lothelper-stderr.log
```

### Can't Access from Other Devices

**Check Mac Mini's IP:**
```bash
ipconfig getifaddr en0
```

**Test from Mac Mini first:**
```bash
curl http://localhost:8000
```

**Ping Mac Mini from other device:**
```bash
ping 192.168.1.100  # or ping macmini.local
```

**Check Firewall:**
- System Settings → Network → Firewall
- If on, add exception for port 8000

### Database Locked

If using SQLite and getting "database locked" errors:
- Only one write operation at a time
- Consider PostgreSQL for multiple users

---

## Maintenance

### Backup Database

**SQLite:**
```bash
# Backup
cp /Users/nickcuskey/ISBN/isbn_web/isbn_optimizer.db \
   /Users/nickcuskey/ISBN/backups/isbn_optimizer_$(date +%Y%m%d).db

# Restore
cp /Users/nickcuskey/ISBN/backups/isbn_optimizer_20250101.db \
   /Users/nickcuskey/ISBN/isbn_web/isbn_optimizer.db
```

**PostgreSQL:**
```bash
# Backup
pg_dump isbn_optimizer > backup.sql

# Restore
psql isbn_optimizer < backup.sql
```

### Update Application

```bash
# Stop service
launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist

# Update code
cd /Users/nickcuskey/ISBN
git pull

# Install any new dependencies
pip install -r requirements.txt

# Start service
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist
```

### View Logs

```bash
# Real-time logs
tail -f /Users/nickcuskey/ISBN/logs/lothelper-stdout.log

# Errors only
tail -f /Users/nickcuskey/ISBN/logs/lothelper-stderr.log

# Search logs
grep "error" /Users/nickcuskey/ISBN/logs/*.log
```

---

## Comparison: Local vs Cloud

| Feature | Mac Mini Server | Railway/Render |
|---------|----------------|----------------|
| Cost | ✅ Free (electricity) | 💰 Monthly fee |
| Speed | ✅ Very fast (local) | 🌐 Internet dependent |
| Setup | ⚙️ One-time setup | ☁️ Quick deploy |
| Maintenance | 🔧 You manage | ✅ Auto-managed |
| Access | 🏠 Local network only | 🌍 Anywhere |
| Privacy | ✅ Your hardware | ☁️ Their servers |

**Best For:**
- **Local Server:** Home use, multiple devices, full control
- **Cloud:** Remote access, shared with others outside network

---

## Advanced: Remote Access (Optional)

Want to access from outside your home network?

### Option 1: Tailscale (Easiest)

Secure remote access without port forwarding:

1. Install Tailscale: https://tailscale.com/download/mac
2. Sign up and connect your Mac Mini
3. Install Tailscale on other devices
4. Access via: `http://100.x.x.x:8000`

### Option 2: ngrok (Temporary)

Quick temporary public URL:

```bash
# Install ngrok
brew install ngrok

# Start tunnel
ngrok http 8000

# Use the provided URL
```

**Note:** Free tier has limits, URL changes each time.

---

## Summary

**Quick Setup:**
```bash
cd /Users/nickcuskey/ISBN/isbn_web
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Access from network:**
- `http://192.168.1.100:8000`
- Or `http://macmini.local:8000`

**Permanent service:**
- Use launchd config above
- Auto-starts on boot
- Runs 24/7

**Your Mac Mini = Perfect LotHelper Server!** 🖥️✨
