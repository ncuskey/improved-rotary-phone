# iOS App Pre-Scanning Workflow Checklist

Complete this checklist before going to the book sale to ensure all features work correctly.

## 📱 App Tabs Overview

The app has 4 main tabs:
1. **Books** - View your accepted book collection
2. **Lots** - Browse lot recommendations
3. **Scan** - Scan and evaluate new books
4. **Settings** - Configure app settings

---

## ✅ TAB 1: SCAN (Primary Workflow)

### Initial Scan
- [ ] Open the Scan tab
- [ ] Tap the camera button to activate scanner
- [ ] Scan a book barcode (test with Jack Reacher book if available)
- [ ] **Expected**: Scanner beeps and shows book preview within 2 seconds
- [ ] **Expected**: Book title and author appear

### Book Evaluation
- [ ] Wait for full evaluation to load (10-30 seconds)
- [ ] **Expected**: See estimated price
- [ ] **Expected**: See probability label (High/Medium/Low)
- [ ] **Expected**: See justification bullets
- [ ] **Expected**: See Buy/Don't Buy recommendation

### Series Detection (Critical for book sales!)
- [ ] When scanning a series book (e.g., Jack Reacher #1)
- [ ] **Expected**: See "Series Collection" card
- [ ] **Expected**: Shows "You Have X Books" (NOT including current scan)
- [ ] **Expected**: If you have 0 other books in series, card should NOT appear
- [ ] **Expected**: If you have 1+ books, shows which books you have
- [ ] **Expected**: Shows series completion percentage

### Book Attributes
- [ ] Tap "Edit Attributes" or attribute fields
- [ ] **Expected**: Can mark as Signed
- [ ] **Expected**: Can select cover type (Hardcover/Paperback)
- [ ] **Expected**: Can set printing/edition
- [ ] Tap "Save" or "Done"
- [ ] **Expected**: Attributes are saved

### Accept/Reject Decision
- [ ] Tap "Accept" button on a recommended book
- [ ] **Expected**: Success sound plays (cha-ching)
- [ ] **Expected**: Book is added to collection
- [ ] **Expected**: Scanner resets for next scan
- [ ] Scan another book
- [ ] Tap "Reject" button
- [ ] **Expected**: Different sound plays
- [ ] **Expected**: Scanner resets for next scan

### Duplicate Detection
- [ ] Scan a book you've already accepted
- [ ] **Expected**: See "Duplicate Detected" warning
- [ ] **Expected**: Shows when you previously scanned it
- [ ] **Expected**: Shows previous location (if any)
- [ ] **Expected**: Option to still accept if you want multiple copies

### Last Scan Summary
- [ ] After accepting/rejecting a book
- [ ] **Expected**: See "Last Scan" card at top
- [ ] **Expected**: Shows ISBN, title, decision
- [ ] **Expected**: Can tap to see details
- [ ] Tap the card
- [ ] **Expected**: Opens detailed view of that book

---

## ✅ TAB 2: BOOKS (Collection Management)

### View Books List
- [ ] Switch to Books tab
- [ ] **Expected**: See list of all accepted books
- [ ] **Expected**: Shows book covers (if available)
- [ ] **Expected**: Shows title, author, estimated price
- [ ] Scroll through list
- [ ] **Expected**: Smooth scrolling, no lag

### Search Books
- [ ] Tap search bar at top
- [ ] Type a book title or author name
- [ ] **Expected**: List filters in real-time
- [ ] **Expected**: Finds books by title
- [ ] **Expected**: Finds books by author
- [ ] **Expected**: Finds books by ISBN
- [ ] Clear search
- [ ] **Expected**: Full list returns

### Sort Books
- [ ] Look for sort button/menu
- [ ] **Expected**: Can sort by Title (A-Z)
- [ ] **Expected**: Can sort by Author
- [ ] **Expected**: Can sort by Price (High to Low)
- [ ] **Expected**: Can sort by Date Added (Recent first)
- [ ] Test each sort option
- [ ] **Expected**: List reorders correctly

### View Book Details
- [ ] Tap on a book in the list
- [ ] **Expected**: Opens detailed view
- [ ] **Expected**: Shows cover image
- [ ] **Expected**: Shows all metadata (title, author, year, etc.)
- [ ] **Expected**: Shows pricing information
- [ ] **Expected**: Shows condition and attributes
- [ ] **Expected**: Can see which lot it's assigned to (if any)

### Edit Book
- [ ] From book detail view, look for edit option
- [ ] **Expected**: Can update condition
- [ ] **Expected**: Can update signed status
- [ ] **Expected**: Can update cover type
- [ ] Save changes
- [ ] **Expected**: Changes persist
- [ ] Go back and return
- [ ] **Expected**: Changes are still there

### Delete Book
- [ ] From book detail or list view
- [ ] Swipe left on book (or find delete button)
- [ ] **Expected**: Shows delete confirmation
- [ ] Confirm deletion
- [ ] **Expected**: Book is removed from list
- [ ] **Expected**: Book count decreases

### Filter Books
- [ ] Look for filter options
- [ ] **Expected**: Can filter by series
- [ ] **Expected**: Can filter by author
- [ ] **Expected**: Can filter by condition
- [ ] **Expected**: Can filter by probability (High/Medium/Low)
- [ ] Apply filter
- [ ] **Expected**: List updates correctly
- [ ] Clear filters
- [ ] **Expected**: Full list returns

---

## ✅ TAB 3: LOTS (Lot Recommendations)

### View Lots List
- [ ] Switch to Lots tab
- [ ] **Expected**: See list of lot suggestions
- [ ] **Expected**: Shows lot name
- [ ] **Expected**: Shows strategy (Series/Author)
- [ ] **Expected**: Shows estimated value
- [ ] **Expected**: Shows probability score
- [ ] **Expected**: Shows book count in each lot
- [ ] Scroll through list
- [ ] **Expected**: Smooth scrolling

### Sort Lots
- [ ] Look for sort/filter options
- [ ] **Expected**: Can sort by value (high to low)
- [ ] **Expected**: Can sort by probability
- [ ] **Expected**: Can filter by strategy type
- [ ] Test sorting options
- [ ] **Expected**: List reorders correctly

### View Lot Details
- [ ] Tap on a lot
- [ ] **Expected**: Opens lot detail view
- [ ] **Expected**: Shows all books in the lot
- [ ] **Expected**: Shows total estimated value
- [ ] **Expected**: Shows justification
- [ ] **Expected**: Shows series completion (if series lot)
- [ ] **Expected**: Shows market data (if available)

### View Books in Lot
- [ ] From lot detail view
- [ ] **Expected**: See carousel or list of books
- [ ] **Expected**: Can swipe through books
- [ ] **Expected**: Each book shows cover and price
- [ ] Tap on a book in the lot
- [ ] **Expected**: Opens that book's detail view
- [ ] Go back to lot
- [ ] **Expected**: Returns to lot view

### Lot Actions
- [ ] Look for action buttons on lot
- [ ] **Expected**: Can mark lot as "Ready to List"
- [ ] **Expected**: Can export lot data
- [ ] **Expected**: Can see eBay pricing estimates
- [ ] **Expected**: Can see comparable sold listings

### Refresh Lots
- [ ] Pull to refresh (swipe down)
- [ ] **Expected**: Shows loading indicator
- [ ] **Expected**: Lots regenerate with latest data
- [ ] **Expected**: Book counts update
- [ ] **Expected**: Pricing updates

---

## ✅ TAB 4: SETTINGS

### View Settings
- [ ] Switch to Settings tab
- [ ] **Expected**: See all configuration options
- [ ] **Expected**: Shows current backend URL
- [ ] **Expected**: Shows sync status

### Backend Connection
- [ ] Check backend URL setting
- [ ] **Expected**: Shows http://localhost:8000 (or your server)
- [ ] **Expected**: Shows connection status (green = connected)
- [ ] Tap "Test Connection"
- [ ] **Expected**: Shows success message
- [ ] **Expected**: Shows server version/info

### Scanning Preferences
- [ ] Look for scanning settings
- [ ] **Expected**: Can enable/disable sounds
- [ ] **Expected**: Can enable/disable haptic feedback
- [ ] **Expected**: Can adjust auto-accept threshold
- [ ] **Expected**: Can enable/disable duplicate warnings
- [ ] Test each toggle
- [ ] **Expected**: Changes take effect immediately

### Data Management
- [ ] Look for data management options
- [ ] **Expected**: Can see total books count
- [ ] **Expected**: Can see total lots count
- [ ] **Expected**: Can see database size
- [ ] **Expected**: Can export data
- [ ] **Expected**: Can sync with backend

### Sync Status
- [ ] Check sync indicators
- [ ] **Expected**: Shows last sync time
- [ ] **Expected**: Shows sync status
- [ ] Tap "Sync Now" (if available)
- [ ] **Expected**: Syncs with backend
- [ ] **Expected**: Shows progress
- [ ] **Expected**: Shows success/error

### Clear Cache
- [ ] Look for "Clear Cache" option
- [ ] Tap it
- [ ] **Expected**: Confirmation dialog
- [ ] Confirm
- [ ] **Expected**: Cache clears
- [ ] **Expected**: App still works
- [ ] Go to Books tab
- [ ] **Expected**: Books reload from backend

---

## 🔄 CRITICAL WORKFLOWS (Test These!)

### Workflow 1: Scan → Accept → Verify in Books
1. [ ] Go to Scan tab
2. [ ] Scan a new book
3. [ ] Wait for evaluation
4. [ ] Tap "Accept"
5. [ ] Go to Books tab
6. [ ] **Expected**: New book appears in list
7. [ ] **Expected**: Book count increases

### Workflow 2: Scan Series Book → Check Lot
1. [ ] Go to Scan tab
2. [ ] Scan a book from a series you have (e.g., Jack Reacher)
3. [ ] **Expected**: Series card shows existing books
4. [ ] Tap "Accept"
5. [ ] Go to Lots tab
6. [ ] Find the series lot
7. [ ] **Expected**: Lot now includes the new book
8. [ ] **Expected**: Book count increased
9. [ ] **Expected**: Estimated value increased

### Workflow 3: Duplicate Scan
1. [ ] Go to Scan tab
2. [ ] Scan a book you already have
3. [ ] **Expected**: Duplicate warning appears immediately
4. [ ] **Expected**: Shows when you last scanned it
5. [ ] Can still accept if needed
6. [ ] Reject instead
7. [ ] **Expected**: Scanner resets

### Workflow 4: Edit Book → Refresh Lots
1. [ ] Go to Books tab
2. [ ] Tap on a book
3. [ ] Edit its condition (e.g., change to "Like New")
4. [ ] Save changes
5. [ ] Go to Lots tab
6. [ ] Pull to refresh
7. [ ] **Expected**: Lot values update
8. [ ] **Expected**: Book's estimated price changes

### Workflow 5: Offline/Connection Loss
1. [ ] Turn on airplane mode
2. [ ] Try to scan a new book
3. [ ] **Expected**: Error message about connection
4. [ ] **Expected**: Can still view Books tab (cached data)
5. [ ] **Expected**: Can still view Lots tab (cached data)
6. [ ] Turn off airplane mode
7. [ ] Try scanning again
8. [ ] **Expected**: Works normally

### Workflow 6: Rapid Scanning (Speed Test)
1. [ ] Go to Scan tab
2. [ ] Scan book 1 → Accept → Immediately scan book 2
3. [ ] **Expected**: No crashes
4. [ ] **Expected**: Books don't get mixed up
5. [ ] Scan book 3 → Reject → Immediately scan book 4
6. [ ] **Expected**: Decisions recorded correctly
7. [ ] Go to Books tab
8. [ ] **Expected**: Only accepted books appear

---

## 🚨 CRITICAL CHECKS BEFORE BOOK SALE

### Must-Pass Tests:
- [ ] ✅ Scanner activates and reads barcodes
- [ ] ✅ Book evaluations load (even if slow)
- [ ] ✅ Series detection works correctly
- [ ] ✅ Accept button adds books to collection
- [ ] ✅ Duplicate detection warns about existing books
- [ ] ✅ Backend connection is stable
- [ ] ✅ Books tab shows accepted books
- [ ] ✅ Lots tab shows recommendations

### Performance Checks:
- [ ] ✅ Scanner responds within 2 seconds
- [ ] ✅ Evaluation loads within 30 seconds
- [ ] ✅ Books list loads within 3 seconds
- [ ] ✅ Lots list loads within 3 seconds
- [ ] ✅ No crashes during rapid scanning

### Data Integrity:
- [ ] ✅ Book count is accurate
- [ ] ✅ Lot assignments are correct
- [ ] ✅ Series groupings are accurate
- [ ] ✅ Prices display correctly
- [ ] ✅ Changes persist after app restart

---

## 📊 API Endpoints Used by Each Tab

### Scan Tab:
- `POST /isbn` - Initial book lookup
- `GET /api/books/{isbn}/evaluate` - Full evaluation
- `POST /api/books/{isbn}/accept` - Accept book
- `POST /api/books/log-scan` - Log scan history
- `GET /api/books/scan-history` - Check for duplicates

### Books Tab:
- `GET /api/books/all` - Fetch all books
- `GET /api/books/{isbn}/evaluate` - Book details
- `DELETE /api/books/{isbn}` - Delete book
- `POST /api/books/{isbn}/update` - Update book fields

### Lots Tab:
- `GET /api/lots/all.json` - Fetch all lots
- `GET /api/lots/{id}` - Lot details
- `POST /api/lots/regenerate.json` - Refresh lots

### Settings Tab:
- `GET /health` - Backend health check
- `GET /api/books/stats` - Database statistics

---

## ✅ FINAL CHECKLIST

Before going to the book sale:
- [ ] Run `python3 tests/pre_scan_validation.py` (should show 15/16 pass)
- [ ] Backend server is running (`lsof -ti:8000` shows process)
- [ ] iOS app connects to backend (Settings tab shows green)
- [ ] Can scan at least one test book successfully
- [ ] Series detection works for a known series
- [ ] Lots tab shows your current recommendations
- [ ] Battery is charged (>50%)
- [ ] Have stable internet connection (or mobile hotspot ready)

## 🎯 Quick Pre-Sale Test (5 minutes)

1. [ ] Open app → Should connect to backend
2. [ ] Scan a test book → Should evaluate
3. [ ] Accept the book → Should appear in Books tab
4. [ ] Check Lots tab → Should show updated recommendations
5. [ ] Scan the same book again → Should warn duplicate
6. [ ] All 4 tabs load without errors

**If all checks pass: YOU'RE READY TO SCAN! 📚**

---

## 🆘 Troubleshooting

### Scanner won't activate:
- Check camera permissions in iOS Settings
- Restart the app
- Restart iPhone

### Books won't load:
- Check Settings tab → Backend connection
- Check WiFi/cellular connection
- Run backend validation test

### Evaluations timing out:
- Check backend logs: `tail -f ~/.isbn_lot_optimizer/activity.log`
- Verify APIs are responding: `curl http://localhost:8000/health`
- Restart backend: `pkill uvicorn && python3 -m uvicorn isbn_web.main:app --host 0.0.0.0 --port 8000 --reload &`

### Series not detecting:
- Check that books have series metadata
- Regenerate lots: Pull to refresh in Lots tab
- Check series catalog: `ls -lh ~/.isbn_lot_optimizer/series_*.json`

### App crashes:
- Check Xcode console for errors
- Clear app data and resync
- Rebuild app if needed
