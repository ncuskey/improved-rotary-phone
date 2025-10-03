# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2024-12-19

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
