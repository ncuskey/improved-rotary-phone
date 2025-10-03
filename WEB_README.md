# ISBN Lot Optimizer - Web Application

A modern web-based interface for the ISBN Lot Optimizer, built with FastAPI, HTMX, and Alpine.js.

## Features

- **Real-time ISBN Scanning** - Scan barcodes with automatic metadata and market lookups
- **Interactive Dashboard** - View books, lots, and detailed information in one interface
- **Compact, Efficient Layout** - Optimized viewport usage with scrollable tables and detail panes
- **Search & Filter** - Quickly find books by ISBN, title, or author
- **Market Intelligence** - eBay market stats, BooksRun offers, and probability scoring
- **Responsive Design** - Works on desktop, tablet, and mobile devices
- **Tabbed Interface** - Switch between Books and Lots views seamlessly

## Quick Start

### 1. Install Dependencies

```bash
# Ensure you're in the project directory
cd /Users/nickcuskey/ISBN

# Activate virtual environment
source .venv/bin/activate

# Install web dependencies (if not already installed)
pip install fastapi uvicorn jinja2 python-multipart sse-starlette
```

### 2. Run the Development Server

```bash
# Start the server
uvicorn isbn_web.main:app --reload

# Or specify host and port
uvicorn isbn_web.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Open in Browser

Navigate to: **http://127.0.0.1:8000**

## Usage

### Scanning Books

1. Enter an ISBN in the input field (or use a barcode scanner)
2. Select the book condition
3. Optionally add edition notes
4. Press Enter or click "Scan ISBN"
5. The book will be added to your catalog and displayed in the table

### Viewing Book Details

- Click any book row in the table to see detailed information in the right panel
- Details include: cover image, metadata, pricing, probability scoring, and condition
- Expand "Market Stats" to see eBay data, BooksRun offers, and series information
- The detail pane is optimized for compact viewing with all essential info visible without scrolling

### Searching

- Use the search bar to filter books by ISBN, title, or author
- Search updates as you type (with a small delay)

### Keyboard Shortcuts

- **Enter** in ISBN field: Scan the book
- **Ctrl/Cmd + K**: Focus search
- **Ctrl/Cmd + I**: Focus ISBN input

## API Documentation

FastAPI provides automatic interactive API documentation:

- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

### Available Endpoints

#### Books
- `POST /api/books/scan` - Scan a single ISBN
- `GET /api/books` - List all books (supports `?search=` parameter)
- `GET /api/books/{isbn}` - Get book details

#### Pages
- `GET /` - Main dashboard

## Configuration

The web app uses the same `.env` configuration as the desktop app:

```bash
# eBay APIs
EBAY_APP_ID=your-finding-app-id
EBAY_CLIENT_ID=your-browse-client-id
EBAY_CLIENT_SECRET=your-browse-client-secret
EBAY_MARKETPLACE=EBAY_US

# BooksRun
BOOKSRUN_KEY=your-booksrun-api-key
BOOKSRUN_AFFILIATE_ID=your-affiliate-id

# Hardcover
HARDCOVER_API_TOKEN=Bearer your-token

# Web Server (optional)
HOST=127.0.0.1
PORT=8000
DEBUG=false
```

## Production Deployment

### Running as a Background Service (macOS)

Create a launchd plist file at `~/Library/LaunchAgents/com.isbn.web.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.isbn.web</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/nickcuskey/ISBN/.venv/bin/uvicorn</string>
        <string>isbn_web.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/nickcuskey/ISBN</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/nickcuskey/ISBN/logs/web.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/nickcuskey/ISBN/logs/web_error.log</string>
</dict>
</plist>
```

Load the service:

```bash
# Create logs directory
mkdir -p /Users/nickcuskey/ISBN/logs

# Load the service
launchctl load ~/Library/LaunchAgents/com.isbn.web.plist

# Check status
launchctl list | grep isbn

# Restart
launchctl unload ~/Library/LaunchAgents/com.isbn.web.plist
launchctl load ~/Library/LaunchAgents/com.isbn.web.plist
```

### Access from Other Devices

If you want to access the web app from other devices on your network:

1. Start the server with `--host 0.0.0.0`:
   ```bash
   uvicorn isbn_web.main:app --host 0.0.0.0 --port 8000
   ```

2. Find your Mac Mini's IP address:
   ```bash
   ifconfig | grep "inet " | grep -v 127.0.0.1
   ```

3. Access from other devices using: `http://YOUR_MAC_IP:8000`

## Architecture

### Tech Stack

- **Backend**: FastAPI (Python async web framework)
- **Frontend**: HTMX (dynamic HTML) + Alpine.js (reactivity) + Tailwind CSS (styling)
- **Database**: SQLite (shared with desktop app)
- **Templates**: Jinja2

### Design Philosophy

- **Minimal JavaScript**: Uses HTMX for dynamic updates, keeping client-side code simple
- **Compact Layout**: Optimized for information density without feeling cluttered
- **Viewport-Aware**: Tables and detail panes size dynamically to fit window height
- **Status Bar Integration**: Single bottom status bar shows book/lot counts and system status

### Directory Structure

```
isbn_web/
├── main.py                    # FastAPI app entry point
├── config.py                  # Settings and environment variables
├── api/
│   ├── dependencies.py        # Dependency injection
│   └── routes/
│       └── books.py          # Book API endpoints
├── templates/
│   ├── base.html             # Base layout
│   ├── index.html            # Dashboard page
│   └── components/
│       ├── book_table.html   # Book list table
│       └── book_detail.html  # Book detail panel
└── static/
    ├── css/custom.css        # Custom styles
    └── js/app.js             # Client-side JavaScript
```

## Development

### Hot Reload

The `--reload` flag enables automatic reloading when code changes:

```bash
uvicorn isbn_web.main:app --reload
```

### Debugging

Check server logs:

```bash
# If running in foreground, logs appear in terminal

# If running as background service:
tail -f /Users/nickcuskey/ISBN/logs/web.log
```

### Adding New Features

1. **New API Endpoints**: Add to `isbn_web/api/routes/`
2. **New Templates**: Add to `isbn_web/templates/components/`
3. **New Styles**: Add to `isbn_web/static/css/custom.css`
4. **New Client Logic**: Add to `isbn_web/static/js/app.js`

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>
```

### Database Locked

The web app uses a thread-safe SQLite connection (`check_same_thread=False`). If you encounter database locks:

1. Ensure the desktop GUI is not running simultaneously
2. Check for stale connections in the database

### Static Files Not Loading

Ensure the `isbn_web/static/` directory exists and contains the CSS/JS files.

## Next Steps (Phase 2)

The current implementation is Phase 1 MVP. Upcoming features:

- [ ] CSV import with progress tracking
- [ ] Bulk operations (edit, delete multiple books)
- [ ] Lot generation and display
- [ ] Real-time progress via Server-Sent Events (SSE)
- [ ] Author cleanup interface
- [ ] Series enrichment controls
- [ ] Cover image display
- [ ] Market refresh operations
- [ ] BooksRun offer refresh

## Support

For issues or questions:

1. Check the FastAPI docs: http://127.0.0.1:8000/docs
2. Review server logs
3. Ensure all environment variables are set correctly

## License

Same license as the main ISBN Lot Optimizer project.
