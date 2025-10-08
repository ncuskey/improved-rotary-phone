# LotHelper iOS App

Native iOS application for ISBN scanning and book cataloging with real-time eBay market pricing.

## Features

### 📸 Barcode Scanner
- **Native camera integration** using AVFoundation
- Supports ISBN-13, ISBN-10, EAN-13, EAN-8, UPC-E, Code 128, and QR codes
- **Tap-to-focus** for improved scanning accuracy
- Haptic feedback on successful scan
- Freeze-frame review with book preview

### 📊 Real-Time eBay Pricing
- **Dual pricing modes**: Active listings + Sold comps
- **Active listings** (Browse API):
  - Current market comparables
  - Resolved CALCULATED shipping
  - 3 cheapest samples with item/ship breakdown
- **Sold comps** (Track A/B):
  - Track B: Conservative estimate from active (25th percentile for used, median for new)
  - Track A: Real sold history from Marketplace Insights API (when approved)
  - Label shows "Sold (est)" or "Sold" based on data source
- Displays count, min, median, and max prices
- Contextual pricing based on US zip code
- Segmented control for easy switching between modes
- See [SOLD_COMPS.md](SOLD_COMPS.md) for detailed implementation guide

### 🔒 Secure Token Management
- OAuth tokens obtained via server-side token broker
- eBay Production credentials never stored on device
- Automatic token refresh with 5-minute buffer
- Retry-on-401 handling for expired tokens

### 📱 Modern SwiftUI Interface
- Clean, accessible design following iOS Human Interface Guidelines
- Haptic feedback for user actions (configurable)
- Empty states and error handling
- Tab-based navigation: Books, Lots, Scanner, Settings

### 🔄 Backend Integration
- REST API integration with Python backend
- Real-time book metadata lookup
- Catalog synchronization
- Lot recommendations
- **BookScouter multi-vendor buyback data**
  - Best offer from 14+ vendors
  - Top 3 offers per book
  - Vendor names and pricing

## Architecture

### Token Broker
The token broker is a lightweight Node.js Express server that handles eBay OAuth:

**Location**: `token-broker/`
**Port**: 8787
**Endpoint**: `GET /token/ebay-browse`

**Response**:
```json
{
  "access_token": "v^1.1#i^1#...",
  "expires_in": 7200,
  "token_type": "Application Access Token"
}
```

**Auto-start**: Launched automatically by `isbn` or `isbn-web` commands via `token-broker/start-broker.sh`

### Swift Integration

#### EbayAPI.swift
Comprehensive eBay Browse API client with:
- `TokenBrokerConfig`: Configurable endpoint (supports `/isbn`, `/isbn-web`, or root)
- `EbayTokenBroker`: Thread-safe actor for token caching
- `EbayBrowseAPI`: Browse API wrapper with zip-contextual pricing
- `PriceSummary`: Statistical analysis (count/min/median/max)
- `ScannerPricingVM`: SwiftUI view model for scanner integration

**Key Types**:
```swift
struct TokenBrokerConfig {
    let baseURL: URL     // e.g., http://192.168.4.50:8787
    let prefix: String   // "", "/isbn", or "/isbn-web"
}

actor EbayTokenBroker {
    func validToken() async throws -> String
    func invalidate()
}

struct PriceSummary {
    let count: Int
    let min: Double
    let median: Double
    let max: Double
    let samples: [PriceSample]
}
```

#### ScannerReviewView.swift
Scanner UI with integrated pricing panel:
- Top third: Live camera feed with reticle overlay
- Middle third: Scrollable space for content
- Bottom third: Book preview + eBay comps + action buttons

**Pricing Panel**:
- Loading state with progress indicator
- Stats row (count/min/median/max)
- 3 cheapest samples with item/ship breakdown
- Error handling with fallback messages

## Setup

### Prerequisites
1. **eBay Developer Account** with Production credentials
2. **Backend server** running on local network
3. **Xcode 14+** with iOS 15+ target

### Configuration

1. **Set eBay credentials** in `ISBN/.env`:
   ```bash
   EBAY_CLIENT_ID=your-production-client-id
   EBAY_CLIENT_SECRET=your-production-secret
   EBAY_MARKETPLACE=EBAY_US
   ```

2. **Update backend URL** in `LotHelperApp/LotHelper/BookAPI.swift`:
   ```swift
   static let baseURLString = "http://YOUR_LOCAL_IP:8000"
   ```

3. **Update token broker URL** in `LotHelperApp/LotHelper/ScannerReviewView.swift`:
   ```swift
   let broker = EbayTokenBroker(config: TokenBrokerConfig(
       baseURL: URL(string: "http://YOUR_LOCAL_IP:8787")!,
       prefix: ""
   ))
   ```

### Building & Running

1. **Start backend services**:
   ```bash
   isbn-web  # Starts web server (port 8000) + token broker (port 8787)
   ```

2. **Open Xcode project**:
   ```bash
   open LotHelperApp/LotHelper.xcodeproj
   ```

3. **Build and run** on device or simulator (Cmd+R)

### Network Configuration

For testing on physical devices:
- Backend must be accessible on local network
- Use your Mac's local IP (not localhost)
- Ensure firewall allows ports 8000 (backend) and 8787 (token broker)
- Token broker auto-starts with `isbn` or `isbn-web` commands

**Find your local IP**:
```bash
ipconfig getifaddr en0  # Wi-Fi
ipconfig getifaddr en1  # Ethernet
```

## API Endpoints Used

### Backend (Port 8000)
- `POST /isbn` - Book metadata lookup
- `GET /api/books/all` - Fetch all books (includes BookScouter data)
- `GET /api/lots/list.json` - Fetch lot recommendations

### Token Broker (Port 8787)
- `GET /token/ebay-browse` - Get eBay OAuth token

### eBay Browse API
- `GET /buy/browse/v1/item_summary/search` - Search by GTIN
- `GET /buy/browse/v1/item/{itemId}` - Get item details (resolves shipping)

## Pricing Flow

1. User scans barcode → ISBN captured
2. Book metadata fetched from backend (`POST /isbn`)
3. **eBay pricing triggered** (`pricing.load(for: isbn)`)
4. Token broker provides OAuth token (cached, 2hr TTL)
5. Browse API search by GTIN (up to 50 results)
6. Parallel detail fetches (up to 25 items) to resolve CALCULATED shipping
7. Sort by delivered price (item + ship)
8. Compute stats: count, min, median, max
9. Display summary + 3 cheapest samples

**Timeline**: ~2-3 seconds for full pricing fetch

## Troubleshooting

### "Token broker failed: Not Found"
- Check token broker is running: `lsof -i :8787`
- Start manually: `cd token-broker && PORT=8787 node server.js`
- Verify credentials in `.env`

### "No active listings for this GTIN"
- Normal for rare/obscure books
- eBay Browse API only shows active listings
- Check GTIN is correct (13-digit ISBN)

### Network errors
- Verify backend URL is correct (local IP, not localhost)
- Check firewall settings on Mac
- Ensure device is on same network

### Build errors
- Clean build folder: Product → Clean Build Folder
- Update Swift packages if needed
- Check Xcode version (14+ required)

## Files

### Swift Files
- `LotHelperApp/LotHelper/EbayAPI.swift` - eBay integration
- `LotHelperApp/LotHelper/ScannerReviewView.swift` - Scanner UI with pricing
- `LotHelperApp/LotHelper/BookAPI.swift` - Backend REST client, BookScouter models
- `LotHelperApp/LotHelper/BooksTabView.swift` - Books list and detail view with BookScouter UI
- `LotHelperApp/LotHelper/BarcodeScannerView.swift` - Camera scanner

### Token Broker
- `token-broker/server.js` - Express server
- `token-broker/start-broker.sh` - Startup script
- `token-broker/package.json` - Dependencies

### Launch Scripts
- `bin/isbn` - Desktop GUI launcher (auto-starts broker)
- `/usr/local/bin/isbn-web` - Web server launcher (auto-starts broker)

## Development

### Adding new eBay API calls
Extend `EbayBrowseAPI` in `EbayAPI.swift`:
```swift
static func newEndpoint(broker: EbayTokenBroker) async throws -> Data {
    var req = URLRequest(url: yourURL)
    req.setValue("Bearer \(try await broker.validToken())", forHTTPHeaderField: "Authorization")
    req.setValue(marketplace, forHTTPHeaderField: "X-EBAY-C-MARKETPLACE-ID")

    let (data, resp) = try await URLSession.shared.data(for: req)

    // Handle 401 retry
    guard let http = resp as? HTTPURLResponse else { throw URLError(.badServerResponse) }
    if http.statusCode == 401 {
        await broker.invalidate()
        return try await newEndpoint(broker: broker)
    }
    guard (200..<300).contains(http.statusCode) else { throw ... }
    return data
}
```

### Customizing pricing display
Modify `pricingPanel` in `ScannerReviewView.swift`:
- Adjust stats shown (add average, percentiles)
- Change sample count (currently 3)
- Add filtering by condition
- Show price history trends

## Future Enhancements

- [ ] Offline mode with local pricing cache
- [ ] Batch scanning with queue management
- [ ] Price alerts for valuable books
- [ ] Condition assessment guidance
- [ ] Integration with lot recommendations
- [ ] Export scans to CSV/JSON
- [ ] Multiple marketplace support (UK, DE, etc.)
- [ ] Shipping calculator for seller perspective

## Credits

Built with:
- **SwiftUI** - Modern iOS UI framework
- **AVFoundation** - Camera and barcode scanning
- **eBay Browse API** - Market pricing data
- **FastAPI** - Python backend
- **Express.js** - Token broker service
