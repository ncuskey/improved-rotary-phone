import Foundation
import Combine

// MARK: - Token Broker Configuration

struct TokenBrokerConfig: Sendable {
    /// e.g. https://api.lothelper.app (no trailing slash)
    let baseURL: URL
    /// "", "/isbn", or "/isbn-web"
    let prefix: String
    /// Fully-resolved endpoint URL for the token broker
    let endpoint: URL

    init(baseURL: URL, prefix: String) {
        self.baseURL = baseURL
        self.prefix = prefix

        // Build URL without using main-actor isolated APIs
        var base = baseURL.absoluteString
        // Ensure no trailing slash on base
        if base.hasSuffix("/") { base.removeLast() }

        var pref = prefix
        if pref.hasPrefix("/") { pref.removeFirst() }
        if !pref.isEmpty { base += "/\(pref)" }
        base += "/token/ebay-browse"

        self.endpoint = URL(string: base) ?? baseURL
    }
}

// MARK: - Token Management

actor EbayTokenBroker {
    private let config: TokenBrokerConfig
    private var token: String?
    private var expiry: Date?

    init(config: TokenBrokerConfig) {
        self.config = config
    }

    func validToken() async throws -> String {
        // Return cached token if still valid (with 5-minute buffer)
        if let t = token, let e = expiry, Date() < e.addingTimeInterval(-300) {
            return t
        }

        var req = URLRequest(url: config.endpoint)
        req.httpMethod = "GET"

        let (data, resp) = try await URLSession.shared.data(for: req)

        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw NSError(
                domain: "TokenBroker",
                code: (resp as? HTTPURLResponse)?.statusCode ?? -1,
                userInfo: [NSLocalizedDescriptionKey: "Token broker failed: \(body)"]
            )
        }

        struct BrokerResponse: Decodable {
            let access_token: String
            let expires_in: Int?
        }

        let response = try JSONDecoder().decode(BrokerResponse.self, from: data)
        token = response.access_token
        expiry = Date().addingTimeInterval(TimeInterval(response.expires_in ?? 7200))

        return response.access_token
    }

    func invalidate() {
        token = nil
        expiry = nil
    }
}

// MARK: - Browse API Models

struct BrowseItemSummary: Decodable {
    struct Price: Decodable {
        let value: String
        let currency: String
    }

    struct ShipCost: Decodable {
        let value: String?
        let currency: String?
    }

    struct ShipOpt: Decodable {
        let shippingCostType: String?
        let shippingCost: ShipCost?
    }

    let itemId: String
    let legacyItemId: String?
    let title: String
    let condition: String?
    let price: Price
    let shippingOptions: [ShipOpt]?
}

struct BrowseSearchResponse: Decodable {
    let total: Int?
    let itemSummaries: [BrowseItemSummary]?
}

struct BrowseItemDetail: Decodable {
    struct Price: Decodable {
        let value: String
    }

    struct ShipCost: Decodable {
        let value: String?
    }

    struct ShipOpt: Decodable {
        let shippingCost: ShipCost?
    }

    let legacyItemId: String?
    let title: String
    let condition: String?
    let price: Price
    let shippingOptions: [ShipOpt]?
}

struct PriceSample {
    let id: String
    let title: String
    let condition: String
    let item: Double
    let ship: Double

    var delivered: Double { item + ship }
}

struct PriceSummary {
    let count: Int
    let min: Double
    let median: Double
    let max: Double
    let samples: [PriceSample]
    let isEstimate: Bool // Track B: true for estimated sold from active listings
}

// MARK: - Sold Comps Models (Track A - Marketplace Insights)

struct SoldSample: Sendable, Decodable {
    let title: String
    let price: Double
    let currency: String
    let quantitySold: Int?
    let lastSoldDate: String?
}

struct SoldSummary: Sendable, Decodable {
    let count: Int
    let min: Double
    let median: Double
    let max: Double
    let samples: [SoldSample]

    private enum CodingKeys: String, CodingKey {
        case count
        case min
        case median
        case max
        case samples
    }

    // Ensure Decodable conformance is not main-actor isolated in Swift 6
    nonisolated init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.count = try c.decode(Int.self, forKey: .count)
        self.min = try c.decode(Double.self, forKey: .min)
        self.median = try c.decode(Double.self, forKey: .median)
        self.max = try c.decode(Double.self, forKey: .max)
        self.samples = try c.decode([SoldSample].self, forKey: .samples)
    }
}

// MARK: - eBay Browse API

enum EbayBrowseAPI {
    static var marketplace = "EBAY_US"

    /// Search eBay by GTIN (ISBN) with automatic token refresh on 401
    static func searchByGTIN(_ gtin: String, zip: String?, broker: EbayTokenBroker) async throws -> BrowseSearchResponse {
        var comps = URLComponents(string: "https://api.ebay.com/buy/browse/v1/item_summary/search")!
        comps.queryItems = [
            .init(name: "gtin", value: gtin),
            .init(name: "limit", value: "50"),
            .init(name: "fieldgroups", value: "FULL")
        ]

        var req = URLRequest(url: comps.url!)
        req.setValue("Bearer \(try await broker.validToken())", forHTTPHeaderField: "Authorization")
        req.setValue(marketplace, forHTTPHeaderField: "X-EBAY-C-MARKETPLACE-ID")

        if let zip {
            req.setValue("contextualLocation=country=US,zip=\(zip)", forHTTPHeaderField: "X-EBAY-C-ENDUSERCTX")
        }

        let (data, resp) = try await URLSession.shared.data(for: req)

        guard let http = resp as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if http.statusCode == 401 {
            await broker.invalidate()
            return try await searchByGTIN(gtin, zip: zip, broker: broker)
        }

        guard (200..<300).contains(http.statusCode) else {
            throw NSError(
                domain: "Browse",
                code: http.statusCode,
                userInfo: [NSLocalizedDescriptionKey: String(data: data, encoding: .utf8) ?? ""]
            )
        }

        return try JSONDecoder().decode(BrowseSearchResponse.self, from: data)
    }

    /// Fetch detailed item information (resolves CALCULATED shipping costs)
    static func fetchItemDetail(_ itemId: String, zip: String?, broker: EbayTokenBroker) async throws -> BrowseItemDetail {
        let url = URL(string: "https://api.ebay.com/buy/browse/v1/item/\(itemId)")!

        var req = URLRequest(url: url)
        req.setValue("Bearer \(try await broker.validToken())", forHTTPHeaderField: "Authorization")
        req.setValue(marketplace, forHTTPHeaderField: "X-EBAY-C-MARKETPLACE-ID")

        if let zip {
            req.setValue("contextualLocation=country=US,zip=\(zip)", forHTTPHeaderField: "X-EBAY-C-ENDUSERCTX")
        }

        let (data, resp) = try await URLSession.shared.data(for: req)

        guard let http = resp as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if http.statusCode == 401 {
            await broker.invalidate()
            return try await fetchItemDetail(itemId, zip: zip, broker: broker)
        }

        guard (200..<300).contains(http.statusCode) else {
            throw NSError(
                domain: "Item",
                code: http.statusCode,
                userInfo: [NSLocalizedDescriptionKey: String(data: data, encoding: .utf8) ?? ""]
            )
        }

        return try JSONDecoder().decode(BrowseItemDetail.self, from: data)
    }

    /// Pulls summaries, resolves shipping (incl. CALCULATED), returns stats for the UI
    static func priceSummary(gtin: String, zip: String?, broker: EbayTokenBroker, maxItems: Int = 25) async throws -> PriceSummary {
        let search = try await searchByGTIN(gtin, zip: zip, broker: broker)
        let items = Array((search.itemSummaries ?? []).prefix(maxItems))

        // Resolve shipping using detail endpoint (adds costs for "CALCULATED")
        let details: [BrowseItemDetail] = try await withThrowingTaskGroup(of: BrowseItemDetail?.self) { group in
            for it in items {
                group.addTask {
                    try? await fetchItemDetail(it.itemId, zip: zip, broker: broker)
                }
            }

            var acc: [BrowseItemDetail] = []
            for try await d in group {
                if let d = d {
                    acc.append(d)
                }
            }
            return acc
        }

        func n(_ s: String?) -> Double {
            Double(s ?? "") ?? 0
        }

        let samples: [PriceSample] = details.map {
            let item = n($0.price.value)
            let ship = n($0.shippingOptions?.first?.shippingCost?.value)
            return PriceSample(
                id: $0.legacyItemId ?? "",
                title: $0.title,
                condition: $0.condition ?? "",
                item: item,
                ship: ship
            )
        }.sorted { $0.delivered < $1.delivered }

        let delivered = samples.map(\.delivered)
        let count = delivered.count
        let min = delivered.first ?? 0
        let median = count == 0 ? 0 : delivered[(count - 1) / 2]
        let max = delivered.last ?? 0

        return PriceSummary(
            count: count,
            min: min,
            median: median,
            max: max,
            samples: Array(samples.prefix(3)),
            isEstimate: false
        )
    }

    /// Track B: Estimate sold prices from active listings using conservative heuristic
    /// Uses 25th percentile for Used condition, median for New
    static func estimatedSoldSummary(gtin: String, zip: String?, broker: EbayTokenBroker, maxItems: Int = 25) async throws -> PriceSummary {
        let search = try await searchByGTIN(gtin, zip: zip, broker: broker)
        let items = Array((search.itemSummaries ?? []).prefix(maxItems))

        // Resolve shipping using detail endpoint
        let details: [BrowseItemDetail] = try await withThrowingTaskGroup(of: BrowseItemDetail?.self) { group in
            for it in items {
                group.addTask {
                    try? await fetchItemDetail(it.itemId, zip: zip, broker: broker)
                }
            }

            var acc: [BrowseItemDetail] = []
            for try await d in group {
                if let d = d {
                    acc.append(d)
                }
            }
            return acc
        }

        func n(_ s: String?) -> Double {
            Double(s ?? "") ?? 0
        }

        // Separate by condition
        var usedPrices: [Double] = []
        var newPrices: [Double] = []
        var allSamples: [PriceSample] = []

        for detail in details {
            let item = n(detail.price.value)
            let ship = n(detail.shippingOptions?.first?.shippingCost?.value)
            let delivered = item + ship
            let condition = detail.condition?.uppercased() ?? ""

            allSamples.append(PriceSample(
                id: detail.legacyItemId ?? "",
                title: detail.title,
                condition: detail.condition ?? "",
                item: item,
                ship: ship
            ))

            if condition.contains("NEW") {
                newPrices.append(delivered)
            } else {
                usedPrices.append(delivered)
            }
        }

        // Sort prices
        usedPrices.sort()
        newPrices.sort()
        allSamples.sort { $0.delivered < $1.delivered }

        // Conservative estimate: 25th percentile for used, median for new
        var estimatedPrices: [Double] = []
        if !usedPrices.isEmpty {
            let p25Index = max(0, usedPrices.count / 4)
            estimatedPrices.append(contentsOf: usedPrices.prefix(through: p25Index))
        }
        if !newPrices.isEmpty {
            let medianIndex = (newPrices.count - 1) / 2
            estimatedPrices.append(newPrices[medianIndex])
        }

        // Fallback: if no condition filtering worked, use 25th percentile of all
        if estimatedPrices.isEmpty && !allSamples.isEmpty {
            let allDelivered = allSamples.map(\.delivered).sorted()
            let p25Index = max(0, allDelivered.count / 4)
            estimatedPrices = Array(allDelivered.prefix(through: p25Index))
        }

        let count = estimatedPrices.count
        let min = estimatedPrices.first ?? 0
        let median = count == 0 ? 0 : estimatedPrices[(count - 1) / 2]
        let max = estimatedPrices.last ?? 0

        return PriceSummary(
            count: count,
            min: min,
            median: median,
            max: max,
            samples: Array(allSamples.prefix(3)),
            isEstimate: true
        )
    }
}

// MARK: - Sold Comps API (Track A - Marketplace Insights)

actor SoldAPI {
    let base: URL
    let prefix: String

    init(config: TokenBrokerConfig) {
        self.base = config.baseURL
        self.prefix = config.prefix
    }

    /// Fetch real sold comps from Marketplace Insights API (requires approval)
    func fetchSold(gtin: String) async throws -> SoldSummary {
        // Build URL: base + prefix + "/sold/ebay"
        var urlString = base.absoluteString
        if urlString.hasSuffix("/") { urlString.removeLast() }

        var pref = prefix
        if pref.hasPrefix("/") { pref.removeFirst() }
        if !pref.isEmpty { urlString += "/\(pref)" }
        urlString += "/sold/ebay"

        guard var comps = URLComponents(string: urlString) else {
            throw URLError(.badURL)
        }

        comps.queryItems = [.init(name: "gtin", value: gtin)]

        guard let url = comps.url else {
            throw URLError(.badURL)
        }

        let (data, resp) = try await URLSession.shared.data(from: url)
        let http = resp as! HTTPURLResponse

        // 501 = MI not enabled yet (waiting for eBay approval)
        if http.statusCode == 501 {
            throw NSError(
                domain: "MI",
                code: 501,
                userInfo: [NSLocalizedDescriptionKey: "eBay Marketplace Insights not enabled on this app."]
            )
        }

        guard (200..<300).contains(http.statusCode) else {
            throw NSError(
                domain: "MI",
                code: http.statusCode,
                userInfo: [NSLocalizedDescriptionKey: String(data: data, encoding: .utf8) ?? ""]
            )
        }

        return try JSONDecoder().decode(SoldSummary.self, from: data)
    }
}

// MARK: - Scanner Pricing ViewModel

enum PricingMode {
    case active      // Browse API - current active listings
    case sold        // Sold comps (real or estimated)
}

@MainActor
final class ScannerPricingVM: ObservableObject {
    @Published var isLoading = false
    @Published var activeSummary: PriceSummary?
    @Published var soldSummary: PriceSummary?
    @Published var error: String?
    @Published var mode: PricingMode = .active

    private let broker: EbayTokenBroker
    private let soldAPI: SoldAPI
    private let zip: String

    init(broker: EbayTokenBroker, soldAPI: SoldAPI, zip: String = "60601") {
        self.broker = broker
        self.soldAPI = soldAPI
        self.zip = zip
    }

    var currentSummary: PriceSummary? {
        mode == .active ? activeSummary : soldSummary
    }

    func load(for gtin: String) {
        isLoading = true
        error = nil
        activeSummary = nil
        soldSummary = nil

        Task {
            // Load both in parallel
            async let activeTask: Void = loadActive(gtin: gtin)
            async let soldTask: Void = loadSold(gtin: gtin)

            await activeTask
            await soldTask
            self.isLoading = false
        }
    }

    private func loadActive(gtin: String) async {
        do {
            let s = try await EbayBrowseAPI.priceSummary(gtin: gtin, zip: zip, broker: broker)
            await MainActor.run {
                self.activeSummary = s
            }
        } catch {
            await MainActor.run {
                self.error = (error as NSError).localizedDescription
            }
        }
    }

    private func loadSold(gtin: String) async {
        do {
            // Try Track A first (real sold data from MI)
            let sold = try await soldAPI.fetchSold(gtin: gtin)

            // Convert to PriceSummary format
            await MainActor.run {
                self.soldSummary = PriceSummary(
                    count: sold.count,
                    min: sold.min,
                    median: sold.median,
                    max: sold.max,
                    samples: sold.samples.map { sample in
                        PriceSample(
                            id: "",
                            title: sample.title,
                            condition: "",
                            item: sample.price,
                            ship: 0
                        )
                    },
                    isEstimate: false
                )
            }
        } catch let err as NSError where err.code == 501 {
            // Track B fallback: MI not available, use estimate
            do {
                let estimated = try await EbayBrowseAPI.estimatedSoldSummary(gtin: gtin, zip: zip, broker: broker)
                await MainActor.run {
                    self.soldSummary = estimated
                }
            } catch {
                // Don't overwrite error if active already failed
                if await MainActor.run(body: { self.error == nil }) {
                    await MainActor.run {
                        self.error = (error as NSError).localizedDescription
                    }
                }
            }
        } catch {
            // Don't overwrite error if active already failed
            if await MainActor.run(body: { self.error == nil }) {
                await MainActor.run {
                    self.error = (error as NSError).localizedDescription
                }
            }
        }
    }
}

