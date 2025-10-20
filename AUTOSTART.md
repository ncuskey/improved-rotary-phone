# Automatic Server Startup on Mac

The LotHelper web server is configured to start automatically when your Mac boots up, ensuring that the service is always available after power failures or restarts.

## LaunchAgent Configuration

The server runs as a LaunchAgent (`com.lothelper.webapp`) which automatically:
- Starts when you log in (`RunAtLoad: true`)
- Restarts if it crashes (`KeepAlive: true`)
- Runs on port 8000 at `http://0.0.0.0:8000`

### Location
```
~/Library/LaunchAgents/com.lothelper.webapp.plist
```

## Managing the Service

### Check Status
```bash
launchctl list | grep lothelper
```
Output shows: `PID  ExitCode  Label`
- PID = process ID (service is running)
- ExitCode = 0 (healthy), -9 (killed), other (error)

### View Logs
```bash
# Standard output (INFO logs)
tail -f ~/ISBN/logs/lothelper-stdout.log

# Error output (ERROR/WARNING logs)
tail -f ~/ISBN/logs/lothelper-stderr.log
```

### Restart Service
```bash
launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist
```

### Stop Service
```bash
launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist
```

### Start Service
```bash
launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist
```

## Health Check

Test if the server is responding:
```bash
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
```

## Environment Variables

The LaunchAgent includes all necessary environment variables from `.env`:
- `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` - eBay API credentials
- `GOOGLE_BOOKS_API_KEY` - Google Books API key
- `BOOKSRUN_KEY` - BooksRun API key
- `HARDCOVER_API_TOKEN` - Hardcover API token
- `APP_DB` - Database path (~/.isbn_lot_optimizer/catalog.db)
- `MIN_SINGLE_PRICE` - Minimum single book price threshold

**Note**: If you update `.env`, you must also update the LaunchAgent plist file and reload it.

## Automatic Startup After Power Failure

The service will automatically start when:
1. The Mac boots up
2. You log in to your user account

No manual intervention is needed. The service will be available within seconds of login.

## Troubleshooting

### Service Won't Start
1. Check logs for errors: `tail -100 ~/ISBN/logs/lothelper-stderr.log`
2. Verify Python path: `/Users/nickcuskey/.pyenv/versions/3.11.13/Library/Frameworks/Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python`
3. Verify working directory exists: `/Users/nickcuskey/ISBN`
4. Check if port 8000 is already in use: `lsof -i :8000`

### Service Crashes Repeatedly
1. Check stderr logs for the root cause
2. Verify database file exists: `~/.isbn_lot_optimizer/catalog.db`
3. Ensure all dependencies are installed in the Python environment
4. Check disk space: `df -h`

### Update Environment Variables
1. Edit the plist file: `vim ~/Library/LaunchAgents/com.lothelper.webapp.plist`
2. Reload the service:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.lothelper.webapp.plist
   launchctl load ~/Library/LaunchAgents/com.lothelper.webapp.plist
   ```

## Related Services

### Cloudflare Tunnel

The LotHelper web server is exposed to the internet via Cloudflare Tunnel at `https://lothelper.clevergirl.app/`.

**Check tunnel status:**
```bash
cloudflared tunnel list
```

**Start tunnel manually:**
```bash
cloudflared tunnel run lothelper
```

**Configure tunnel for automatic startup:**
```bash
# Install as a service
sudo cloudflared service install
```

**Tunnel configuration location:**
```
~/.cloudflared/config.yml
```

The tunnel should show active connections (e.g., `2xden03, 2xsjc07`) when running properly.

### Token Broker Service

The token broker service (port 8787) should also be configured for automatic startup if needed. See `token-broker/` directory for details.
