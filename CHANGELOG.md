# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2025-01-08

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
