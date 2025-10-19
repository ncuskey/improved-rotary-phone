# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2025-01-18

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
  - Mode preference persists across app sessions
  - Manual entry option with submit button
- **Splash Screen with Loading Status**:
  - Professional branded launch screen with app icon
  - Real-time loading status updates
  - Smooth fade-in animation to main app
  - Shows: "Initializing...", "Setting up database...", "Loading cached data...", "Ready!"
- **eBay Fee-Based Profit Analysis**:
  - Accurate net profit calculation including eBay fees (13.25% + $0.30)
  - Estimated shipping costs ($5.00 Media Mail)
  - Two-path profit display: eBay Route vs Buyback Route
  - Shows complete breakdown: Sale → Fees → Ship → Cost → Net
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
  - Profit metrics always shown when available
  - Two-route comparison: eBay vs Buyback side-by-side
  - Color-coded indicators (green/red) for profit/loss
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
  - Now includes eBay fees, transaction fees, and shipping
  - Returns salePrice used for transparency
  - Supports $0 purchase price
  - Always calculates buyback profit when offer exists

### Technical Improvements
- Live eBay median integrated into profit calculations
- Buyback profit calculated independently and checked first
- Purchase price defaults to $0 for free books
- Text field auto-focus management with FocusState
- Splash screen with async startup workflow
- Full-screen layout switching based on scan state
- Enhanced data source transparency in analysis view
- Vendor name integration from BookScouter API

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
