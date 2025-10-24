# Documentation Index

Complete documentation for the ISBN Lot Optimizer (Improved Rotary Phone).

---

## Quick Links

- **[Main README](../README.md)** - Project overview and quick start
- **[Installation](setup/installation.md)** - Complete setup guide
- **[Configuration](setup/configuration.md)** - Environment variables and settings
- **[Deployment](deployment/overview.md)** - Cloud deployment guide

---

## Documentation Structure

### 📦 Setup
Installation, configuration, and local server setup.

- **[Installation Guide](setup/installation.md)**
  - Quick start
  - Local server setup (Mac Mini)
  - Database configuration
  - Network access
  - Troubleshooting

- **[Configuration](setup/configuration.md)**
  - Environment variables
  - API keys (eBay, BookScouter, Hardcover)
  - Database settings
  - Feature configuration

### 🚀 Deployment
Cloud platform deployment guides.

- **[Overview](deployment/overview.md)**
  - Platform comparison
  - Quick start
  - Database migration
  - Post-deployment

- **[Railway Guide](deployment/railway.md)**
  - Step-by-step Railway deployment
  - Recommended platform

- **[Render Guide](deployment/render.md)**
  - Step-by-step Render deployment
  - Free tier with generous limits

### 📱 Applications
Documentation for each application interface.

- **[Desktop GUI](apps/README.md)**
  - Tkinter desktop application
  - Book scanning and management
  - Lot generation
  - Author cleanup
  - BookScouter integration

- **[Web Interface](apps/web-temp.md)**
  - FastAPI web application
  - 3D book carousel
  - Mobile optimization
  - API endpoints
  - Metadata search endpoint (title/author → ISBN)
  - Camera scanner

- **[iOS App](apps/ios.md)**
  - Native iOS scanner
  - Barcode scanning with OCR
  - Real-time eBay pricing
  - Triage workflow
  - Books library with search and sorting
  - Lot filtering by strategy
  - Metadata search for books without barcodes
  - Token broker integration

- **[Camera Scanner](apps/camera-scanner.md)**
  - Web-based camera scanner
  - OCR text recognition
  - Known issues and roadmap

### ✨ Features
Detailed feature documentation.

- **[Series Integration](features/series-integration-temp.md)**
  - Hardcover API integration
  - BookSeries.org scraping
  - Series lot generation
  - Completion tracking

- **[Sold Comps](features/sold-comps.md)**
  - eBay sold comparables
  - Finding API integration
  - Browse API integration
  - Market intelligence

### 🔧 Development
Technical documentation for developers.

- **[Code Map](development/codemap.md)**
  - Project structure
  - Package layout
  - Module responsibilities
  - Data flow

- **[Refactoring 2025](development/refactoring-2025.md)**
  - Recent refactoring efforts
  - Performance improvements
  - Code consolidation
  - Deprecations

- **[Changelog](development/changelog.md)**
  - Version history
  - Feature additions
  - Bug fixes

### 📋 Todo
Planning and future work.

- **[Autostart](todo/autostart.md)**
  - macOS autostart configuration
  - System integration plans

- **[Camera Scanner](todo/camera-scanner.md)**
  - Known issues
  - Barcode scanning improvements
  - Future enhancements

---

## Documentation Status

### ✅ Complete
- Setup documentation
- Deployment guides
- Configuration reference

### ⏳ In Progress
- App documentation (some files need merging)
- Feature documentation (consolidation in progress)

### 📝 Notes
Files marked `-temp` are copies that need manual merging with other related docs. See [PHASE2_STATUS.md](../PHASE2_STATUS.md) for details.

---

## Contributing to Documentation

### Adding New Documentation

1. Choose appropriate directory:
   - `setup/` - Installation and configuration
   - `deployment/` - Platform deployment guides
   - `apps/` - Application-specific docs
   - `features/` - Feature documentation
   - `development/` - Technical/developer docs
   - `todo/` - Planning and roadmap

2. Create markdown file with clear headings

3. Update this README.md index

4. Link from main README.md if appropriate

### Documentation Style Guide

- Use clear, descriptive headings
- Include code examples where helpful
- Add troubleshooting sections
- Link to related documentation
- Keep language concise and actionable
- Use emoji sparingly for visual organization

---

## Getting Help

- **Issues:** Check [GitHub Issues](https://github.com/anthropics/claude-code/issues)
- **Setup Problems:** See [Installation Guide](setup/installation.md#troubleshooting)
- **Deployment Issues:** See [Deployment Guide](deployment/overview.md#troubleshooting)
- **Configuration:** See [Configuration Reference](setup/configuration.md)

---

**Last Updated:** 2025-10-20 (Phase 2 Documentation Consolidation)
