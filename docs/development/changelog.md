# Changelog

All notable changes to this project will be documented in this file.

## [2025-10-24] - Performance & Caching Optimization

### Fixed
- **Amazon Pricing Display**: Fixed bug where Amazon lowest price, seller count, and trade-in price weren't being extracted from database and sent to iOS app, even though data was stored in bookscouter_json field

### Added
- **Books Tab Sorting Options**:
  - Added sort by vendor price (high/low)
  - Added sort by Amazon price (high/low)
  - Renamed existing eBay sort to "Highest/Lowest eBay Price" for clarity
  - Books without pricing data appear at end of sorted lists
  - Six new sort options total alongside existing title, recency, and profit sorts
- **Persistent Storage & Smart Caching**:
  - iOS app now uses persistent SwiftData storage (was in-memory)
  - Smart cache with 5-minute window to avoid unnecessary network calls
  - Proactive background refresh after accepting books
  - Books and Lots tabs load instantly from cache on subsequent launches
- **Incremental Sync Support**:
  - Backend API supports `?since=` query parameter for `/api/books/all`
  - Database layer: `fetch_books_updated_since()` method
  - Service layer: `get_books_updated_since()` method
  - Client-side: `BookAPI.fetchBooksUpdatedSince()` method
- **Extended Splash Screen**:
  - Increased from 0.2s to 2.0s to display branding
  - Performance improvements made app load so fast splash needed to be extended
- **Books Tab Price Display**:
  - Now shows Amazon lowest price from BookScouter API
  - Now shows calculated estimated price (using max() algorithm)
  - Now shows eBay median from Track B sold comps (active listings estimate)
  - Four prices displayed: eBay median, Vendor buyback, Amazon lowest, Estimate
  - Color-coded for clarity: primary, green, orange, blue respectively
- **eBay Track B Integration**:
  - Replaced deprecated Finding API with Browse API + sold comps
  - Track B uses 25th percentile for used books, median for new books
  - Automatically fetches during book scanning (include_market=True)
  - Provides conservative pricing estimates from active listings
  - Works without Marketplace Insights API approval
- **Redesigned Book Detail View**:
  - Complete visual redesign following scanner results design philosophy
  - Card-based panels with rounded corners and consistent shadows
  - ScrollView layout for better control and smoother scrolling
  - Hero section with large cover image and quick stats badges
  - Price comparison panel with 2x2 grid of all four price types
  - Profit analysis panel showing margin and percentage markup
  - Color-coded sections: blue for info, green for buyback, orange for eBay/Amazon
  - Market data panel with metric chips for active/sold counts and sell-through rate
  - Buyback offers panel showing top 5 vendor offers
  - Amazon data panel with sales rank, seller count, and trade-in value
  - Lots panel showing which lots contain this book
  - Book info panel with publisher, year, categories, and description
  - Justification panel with numbered evaluation factors
  - File: `BookDetailViewRedesigned.swift` (replaces old List-based BookDetailView)
- **Smart eBay Listing Filtering**:
  - Automatically filters out multi-book lots ("lot of", "set of", "bundle", "collection")
  - Filters out signed/autographed copies by default to avoid inflated pricing
  - Tracks detection of signed listings for future user prompting
  - Returns filtering metadata: total listings, filtered count, signed count, lot count
  - Optional `include_signed` parameter to include signed copies when user confirms
  - Applied to both active listings (Browse API) and sold comps (Track B estimates)
  - Prevents inaccurate pricing from special edition or multi-book listings
- **Signed Copy Detection Infrastructure**:
  - Backend: Updated `EbayMarketStats` model with filtering metadata fields
  - Backend: `browse_active_by_isbn()` now returns `signed_listings_detected`, `lot_listings_detected`, `filtered_count`, `total_listings`
  - Backend: Updated `fetch_market_stats_v2()` to pass filtering data through to API
  - iOS: Added filtering fields to `EbayMarketData` model in BookAPI.swift
  - iOS: Ready for signed copy prompt implementation when signed copies detected
  - iOS: Fixed compilation errors in `CachedBook.swift` and `BooksTabView.swift`
  - Files: `shared/models.py`, `isbn_lot_optimizer/service.py`, `LotHelperApp/LotHelper/BookAPI.swift`
- **eBay Lot Comp Pricing (Fully Integrated)**:
  - **Search & Analysis**: Search eBay for lot listings by series name or author
  - **Lot Size Detection**: Parse lot sizes from listing titles using regex patterns
  - **Per-Book Pricing**: Calculate per-book pricing by dividing total price by lot size
  - **Size Optimization**: Analyze pricing across different lot sizes (e.g., 3-book vs 7-book lots)
  - **Market Intelligence**: Identify optimal lot size with highest per-book price
  - **Integrated into Lot Generation**: Automatically fetches lot pricing during lot recalculation
  - **Smart Pricing Logic**: Compares lot market value vs individual book pricing
  - **Database Storage**: Stores lot pricing data (market value, optimal size, per-book price, comps count)
  - **Justification Updates**: Adds lot pricing details to lot justification when used
  - **Database Migration**: Created `scripts/migrate_lot_pricing_fields.py` for existing databases
  - **CLI Test Interface**: `python -m isbn_lot_optimizer.market "Alex Cross" "James Patterson"`
  - **Data Models**: Added 5 new fields to `LotSuggestion` and `LotCandidate` models
  - **Database Schema**: Added 5 new columns to lots table (lot_market_value, lot_optimal_size, lot_per_book_price, lot_comps_count, use_lot_pricing)
  - **Files Modified**:
    - `isbn_lot_optimizer/market.py` (search & analysis functions)
    - `isbn_lot_optimizer/lots.py` (_compose_lot() integration)
    - `isbn_lot_optimizer/service.py` (serialization & conversion)
    - `shared/models.py` (LotSuggestion & LotCandidate fields)
    - `shared/database.py` (schema & INSERT statement)
  - **Documentation**: `docs/LOT_PRICING_FEATURE.md` with complete API reference and examples

### Changed
- **Accept/Reject Workflow**:
  - Accept: Proactively refreshes Books and Lots caches in background
  - Reject: Logs to scan_history and refreshes Books cache to remove rejected books
  - Accept/reject updates visible immediately when switching to Books/Lots tabs
  - Rejected books kept in scan_history for lot building and series matching
- **Cache Strategy**:
  - < 5 minutes: Uses cached data (instant load)
  - > 5 minutes: Full sync from backend (removes rejected books from cache)
  - Background refresh after accept ensures tabs are always current
- **Database Access Pattern**:
  - Fixed ThreadSafeDatabaseManager usage in `accept_book()`
  - Now uses `update_book_record()` instead of direct connection access

### Fixed
- **AttributeError in accept_book()**: Fixed ThreadSafeDatabaseManager attribute error
- **Rejected Books in Books Tab**: Cache now properly filters status='REJECT' books
- **Performance Issues**: Eliminated 30-second black screen on launch
- **UI Blocking**: Accept/reject operations no longer block UI or tab switching

### Technical Improvements
- Persistent SwiftData storage eliminates full data download on every launch
- 5-minute cache window balances performance and data freshness
- Background refresh ensures tabs ready when user switches to them
- Proper ThreadSafeDatabaseManager method usage throughout codebase
- Incremental sync infrastructure (currently does full sync after 5min)

## [Unreleased] - 2025-10-18

### Added
- **Full-Screen Analysis View**:
  - Camera disappears after scan to maximize analysis space
  - Complete transparency into decision-making process
  - Four detailed sections: Confidence Score, Data Sources, Decision Factors, Market Intelligence
  - Shows ALL justification reasons with numbered explanations
  - Data source attribution (eBay, BookScouter, backend estimates)
  - Explains where each number comes from and why recommendations are made
- **Text Entry Mode for Bluetooth Scanners**:
  - Toggle between Camera and Text Entry modes via toolbar icon
  - Compact text input area with auto-focus and auto-clear
  - Perfect for Bluetooth barcode scanners
  - Auto-refocuses after Accept/Reject for continuous scanning
  - Auto-refocuses after evaluation completes (success or error)
  - Mode preference persists across app sessions
  - Manual entry option with submit button
  - Enables completely hands-free Bluetooth scanner workflow
- **Splash Screen with Loading Status**:
  - Professional branded launch screen with app icon
  - Real-time loading status updates
  - Smooth fade-in animation to main app
  - Shows: "Initializing...", "Setting up database...", "Loading cached data...", "Ready!"
- **eBay Fee-Based Profit Analysis**:
  - Accurate net profit calculation including eBay fees (13.25% + $0.30)
  - Shipping not deducted (buyer pays shipping in our store)
  - Two-path profit display: eBay Route vs Buyback Route
  - Shows complete breakdown: Sale → Fees → Cost → Net
  - Buy recommendation now requires $10+ NET profit (not just sale price)
- **Live eBay Pricing Integration**:
  - Uses real-time eBay median from pricing panel (not just backend estimate)
  - Shows "(Live)" or "(Est.)" indicator for price source transparency
  - More accurate profit calculations based on current market
- **Free Book Support ($0 Purchase Price)**:
  - Works without setting a purchase price (assumes $0 for free books)
  - Shows "Cost (Free)" in profit breakdown
  - Perfect for estate sales, donations, library discards
  - Any positive buyback offer = instant BUY recommendation
- **Buyback-First Priority Logic**:
  - Buyback profit > $0 = instant BUY (highest priority)
  - Works regardless of eBay data, confidence score, or Amazon rank
  - Shows vendor name in recommendation: "Guaranteed $X.XX profit via VendorName"
  - Vendor name displayed in buyback route breakdown
- **Enhanced Buy Recommendation Panel**:
  - Moved to top of analysis screen for immediate visibility
  - Accept/Reject buttons at very top (no scrolling needed)
  - Buy/Don't Buy advice immediately below buttons
  - Profit metrics always shown when available
  - Two-route comparison: eBay vs Buyback side-by-side
  - Color-coded indicators (green/red) for profit/loss
- **Custom Cash Register Sound**:
  - Custom MP3 audio file for BUY recommendations
  - Uses AVAudioPlayer for high-quality playback
  - Falls back to system sound if file unavailable
  - Cha-Ching.mp3 bundled with app
- **Always-Ready Scanning Workflow**:
  - Scanner automatically ready for next scan after evaluation
  - Auto-accepts BUY books when new scan arrives
  - Auto-rejects DON'T BUY books when new scan arrives
  - Enables continuous rapid scanning without button taps
  - Perfect for high-volume scanning sessions
- **New Swift Files**:
  - `LotHelperApp/LotHelper/PricePickerSheet.swift` - Purchase price picker component
  - `LotHelperApp/LotHelper/SplashScreenView.swift` - Branded splash screen
  - `LotHelperApp/LotHelper/SoundFeedback.swift` - Sound utilities (from previous session)
  - `LotHelperApp/LotHelper/SoundPreviewView.swift` - Sound testing interface (from previous session)

### Changed
- **Buy/Don't Buy Logic Completely Revised**:
  - RULE 1: Buyback profit > $0 → BUY (guaranteed, zero risk)
  - RULE 2: eBay net profit ≥ $10 → BUY (strong)
  - RULE 3: eBay net profit $5-10 → Conditional (needs high confidence or fast Amazon rank)
  - RULE 4: eBay net profit $1-5 → Usually DON'T BUY (too thin)
  - RULE 5: eBay net profit ≤ $0 → DON'T BUY (loss)
- **Scanner Input Modes**:
  - ScannerInputMode enum: .camera or .text
  - Saved to AppStorage for persistence
  - Keyboard icon toggles between modes
- **Profit Calculation**:
  - Now includes eBay fees and transaction fees (13.25% + $0.30)
  - Shipping NOT deducted (buyer pays)
  - Returns salePrice used for transparency
  - Supports $0 purchase price
  - Always calculates buyback profit when offer exists
- **Sound Feedback System**:
  - Scan detected: System tink sound (1057)
  - BUY recommendation: Custom cash register MP3
  - DON'T BUY recommendation: System rejection sound (1053)
  - Success/Error: System sounds with haptic feedback
- **Scanner Workflow**:
  - Auto-accepts previous BUY when new scan arrives
  - Auto-rejects previous DON'T BUY when new scan arrives
  - Text field auto-refocuses after every evaluation
  - Always ready for next scan without manual interaction

### Technical Improvements
- Live eBay median integrated into profit calculations
- Buyback profit calculated independently and checked first
- Purchase price defaults to $0 for free books
- Text field auto-focus management with FocusState
- Auto-focus restoration after evaluation (success and error paths)
- Splash screen with async startup workflow
- Full-screen layout switching based on scan state
- Enhanced data source transparency in analysis view
- Vendor name integration from BookScouter API
- AVAudioPlayer for custom sound playback with fallback
- Auto-accept/auto-reject on new scan for continuous workflow

## [Previous] - 2025-01-09

### Added
- **iOS Scanner Triage Workflow**: Complete book profitability evaluation during scanning
  - Real-time evaluation panel showing probability score, pricing, Amazon rank, and justification
  - Accept/Reject buttons for immediate keep/discard decisions
  - Scan → Evaluate → Accept/Reject workflow eliminates need to review books later
  - Color-coded probability badges (Green/Blue/Orange/Red for Strong/Worth/Risky/Pass)
  - Estimated resale price vs BookScouter buyback floor comparison
  - Amazon sales rank badges with demand tier color coding
  - Top 3 justification reasons explaining probability score
  - Rarity and series badges for collectible books
- **Mobile API Endpoints**:
  - `GET /api/books/{isbn}/evaluate` - Complete evaluation data for triage
  - `DELETE /api/books/{isbn}/json` - Book deletion for reject workflow
  - `GET /api/books/stats` - Database statistics for mobile access
- **Scanner Layout Optimization**:
  - Expanded evaluation panel to use bottom 2/3 of screen (up from 1/3)
  - Top 1/3: Camera scanner with barcode reticle
  - Bottom 2/3: Scrollable book preview, eBay comps, evaluation panel, and action buttons

### Technical Improvements
- **ISBN Normalization**: Fixed ISBN-10 to ISBN-13 conversion (handles X check digits correctly)
- **Market Data Integration**: Changed mobile scan endpoint to include_market=True for complete data
- **Retry Logic**: Added exponential backoff (1s, 2s, 3s delays) for evaluation fetch race conditions
- **Error Handling**: Improved error messages and console logging for debugging
- **Backend ISBN Resolution**: Use server-normalized ISBN for evaluation endpoint calls

### Fixed
- eBay Browse API error 12001 by normalizing all ISBNs to 13-digit format before API calls
- 404 errors on evaluation endpoint due to race condition between scan submission and data processing
- ISBN-10 with X check digit not being properly converted (e.g., 034529906X → 9780345299062)
- Evaluation panel not displaying due to missing market data in database

## [Previous] - 2025-01-08

### Added
- **Database Statistics Feature**:
  - Comprehensive `--stats` CLI command showing storage usage, coverage, and efficiency
  - GUI menu option: Tools → Database Statistics...
  - Displays: file size, book counts, API response sizes, probability distribution, price stats, data freshness
  - Scrollable modal dialog with monospace formatting
- **Smart Series Refresh**:
  - Hardcover API integration for series metadata detection
  - Intelligent 7-day caching to minimize API calls
  - Batch processing with rate limiting (60 req/min)
  - Skip recently checked books option
  - GUI button: "Refresh Series (All)" in toolbar and Tools menu
  - CLI: `--refresh-series` with limit and force options
  - Shows cache efficiency statistics
- **Amazon Sales Rank Integration**:
  - BookScouter API batch refresh for Amazon sales ranks
  - Incorporated into probability scoring (0-15 points based on rank tiers)
  - Fallback probability calculation when eBay data unavailable
  - Batch refresh: `--refresh-amazon-ranks` with configurable batch sizes
  - Smart rate limiting and progress tracking
- **API Optimization**:
  - Reduced API calls by 33% per book (3→2 calls)
  - BookScouter now primary metadata source (includes Amazon rank)
  - Google Books used as fallback only
  - Improved .env file loading from multiple locations

### Technical Improvements
- Fixed Hardcover API integration for new Typesense search schema
- Updated GraphQL queries for current API structure
- Added "Bearer" prefix to Hardcover authorization header
- Improved error handling and user feedback for all refresh operations
- Enhanced probability scoring with Amazon rank factor

### Fixed
- Resolved Hardcover API authentication issues (401 errors)
- Fixed GraphQL query structure for Typesense results format
- Corrected authorization header format for Hardcover API
- Fixed .env loading to search multiple potential file locations

## [Previous] - 2024-12-19

### Added
- **3D Book Carousel**: Stunning interactive carousel for lot details page
  - Real book cover thumbnails from Open Library
  - 3D perspective transforms with smooth animations
  - Mouse wheel navigation and click interactions
  - Arrow buttons and progress dots
  - Smart fallback system for missing covers
  - Color-coded condition badges
- **Web Interface Enhancements**:
  - FastAPI backend with Jinja2 templates
  - HTMX for dynamic updates without page refreshes
  - Alpine.js for reactive UI components
  - Modern Tailwind CSS styling
  - Responsive design for desktop and mobile
- **Lot Details Page**: Comprehensive lot information display
  - Split-screen layout with carousel and details
  - Financial summary cards
  - Selected book details panel
  - HTMX-powered book removal and lot editing
- **Book Cover Integration**: 
  - Automatic thumbnail loading from Open Library
  - Graceful fallbacks for missing covers
  - Error handling and loading states

### Technical Improvements
- Fixed JSON serialization issues for Alpine.js data binding
- Improved template structure with proper separation of concerns
- Enhanced error handling and user feedback
- Optimized carousel performance with efficient DOM updates

### Fixed
- Resolved Alpine.js syntax errors caused by large inline JSON objects
- Fixed template data type issues with lot justification and book ISBNs
- Corrected server-side JSON serialization for complex dataclass objects
- **Fixed "Lot not found" error**: Corrected lots table template to use actual lot IDs instead of array indices
- Fixed 3D carousel navigation links in lots table
- **Fixed mobile carousel positioning**: Resolved cards appearing "half off the top of the screen" on mobile devices
- **Fixed mobile swipe functionality**: Added proper touch gesture support for carousel navigation
- **Fixed mobile viewport handling**: Improved responsive design for mobile browsers

### Changed
- Updated README.md to document web interface and 3D carousel features
- Enhanced lot detail templates with improved styling and functionality
- Refactored Alpine.js component structure for better maintainability
- **Mobile-optimized 3D carousel**: Reduced transform complexity and improved positioning for mobile devices
- **Enhanced touch interactions**: Added swipe gestures and touch-friendly navigation elements
- **Responsive design improvements**: Better mobile layout with flexible viewport handling

### Deployment Notes
- **isbn-web Shortcut**: The `isbn-web` command uses a separate directory (`/Users/nickcuskey/ISBN`) 
  - Changes must be synchronized manually between development and deployment directories
  - Updated files: `base.html`, `lot_details.html`, `lot_detail.html`, `lots.py`, `service.py`, `lots_table.html`
  - Added new components: `carousel.html`, `lot_edit_form.html`
  - **Mobile optimizations**: Touch gestures, responsive design, and mobile-specific 3D transforms
