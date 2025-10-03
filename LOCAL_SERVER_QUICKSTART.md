# LotHelper Mac Mini Server - Quick Start

## 🚀 One-Command Setup

```bash
cd /Users/nickcuskey/ISBN
./setup_local_server.sh
```

That's it! Your Mac Mini will now run LotHelper 24/7 and auto-start on boot.

## 📱 Access From Any Device

Once running, access from any device on your network:

```
http://macmini.local:8000
```

Or use your Mac Mini's IP (find it with `ipconfig getifaddr en0`):

```
http://192.168.1.XXX:8000
```

## 📋 Quick Commands

```bash
# View logs
tail -f /Users/nickcuskey/ISBN/logs/lothelper-stdout.log

# Stop server
launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist

# Start server
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist

# Check if running
launchctl list | grep lothelper
```

## 🔧 Manual Start (for testing)

If you just want to test without installing the service:

```bash
cd /Users/nickcuskey/ISBN/isbn_web
uvicorn main:app --host 0.0.0.0 --port 8000
```

Press `Ctrl+C` to stop.

## 📚 More Information

- **Full Guide:** See `LOCAL_SERVER_SETUP.md`
- **Troubleshooting:** See `LOCAL_SERVER_SETUP.md` Troubleshooting section
- **Cloud Deployment:** See `DEPLOYMENT.md` for Railway/Render

## ✅ What You Get

- ✅ Server runs 24/7
- ✅ Auto-starts on Mac boot
- ✅ Access from iPhone/iPad/any device on network
- ✅ Fast local speeds
- ✅ No monthly cloud costs
- ✅ Full privacy - your data stays local

## 🎯 Perfect For

- Home use with multiple devices
- Fast local network access
- Full control over your data
- No internet dependency (except ISBN lookups)

---

**Need cloud access instead?** See `QUICK_DEPLOY.md` for Railway deployment.
