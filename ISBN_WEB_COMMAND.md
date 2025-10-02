# ISBN Web - Global Command

## Quick Start

Just type anywhere in your terminal:

```bash
isbn-web
```

That's it! This will:
1. ✅ Check if the server is running
2. ✅ Start the server if needed (on port 8000)
3. ✅ Open your browser to http://localhost:8000
4. ✅ Show you all access URLs for other devices

## Usage

```bash
# Start server and open browser
isbn-web
```

The command is smart:
- If server is already running → just opens browser
- If server is not running → starts it, then opens browser
- Accessible from any directory

## Stop the Server

```bash
pkill -f 'uvicorn isbn_web.main:app'
```

## Access from Other Devices

After running `isbn-web`, the terminal will show URLs like:

```
📱 Access URLs:
  • This Mac:      http://localhost:8000
  • Network:       http://192.168.4.50:8000
  • Hostname:      http://Mac-mini.local:8000
```

Use the Network or Hostname URL from your phone/tablet/other computers.

## Logs

Server logs are saved to:
```
/Users/nickcuskey/ISBN/logs/isbn-web.log
```

View them:
```bash
tail -f /Users/nickcuskey/ISBN/logs/isbn-web.log
```

## Comparison with Other Commands

| Command | What It Does |
|---------|-------------|
| `isbn` | Opens the desktop GUI app |
| `isbn-web` | Starts web server + opens browser |
| `./setup_local_server.sh` | Sets up 24/7 auto-start service |

## Examples

### Quick workflow for scanning books:

```bash
# Start the web app
isbn-web

# Use the web interface in your browser
# Scan ISBNs, review lots, etc.

# When done, stop the server
pkill -f 'uvicorn isbn_web.main:app'
```

### Keep it running permanently:

If you want the server to run 24/7 and auto-start on boot, use the setup script instead:

```bash
cd /Users/nickcuskey/ISBN
./setup_local_server.sh
```

Then you don't need `isbn-web` - just open your browser to `http://localhost:8000` anytime.

## Troubleshooting

### Port already in use

If you get an error that port 8000 is already in use:

```bash
# Kill any existing server
pkill -f 'uvicorn isbn_web.main:app'

# Wait a moment
sleep 2

# Try again
isbn-web
```

### Server won't start

Check the logs:
```bash
tail -f /Users/nickcuskey/ISBN/logs/isbn-web.log
```

**Common issue: "No module named uvicorn"**

If the logs show `No module named uvicorn`, the `isbn-web` script needs to use the virtual environment Python. The script should be configured to use:
```bash
/Users/nickcuskey/ISBN/.venv/bin/python
```

To fix this, update `/usr/local/bin/isbn-web` to set:
```bash
VENV_PYTHON="$ISBN_DIR/.venv/bin/python"
```

And use `"$VENV_PYTHON" -m uvicorn ...` instead of `python -m uvicorn ...`

### Browser doesn't open

The server might still be starting. Wait a few seconds and manually open:
```
http://localhost:8000
```

## Uninstall

To remove the command:
```bash
sudo rm /usr/local/bin/isbn-web
```

---

**Quick Reference:**
- **Start:** `isbn-web`
- **Stop:** `pkill -f 'uvicorn isbn_web.main:app'`
- **Logs:** `tail -f /Users/nickcuskey/ISBN/logs/isbn-web.log`
