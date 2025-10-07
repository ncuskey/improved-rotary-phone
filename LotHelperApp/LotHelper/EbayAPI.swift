import Foundation
import Combine

// MARK: - Token Broker Configuration

struct TokenBrokerConfig: Sendable {
    /// e.g. https://api.lothelper.app (no trailing slash)
    let baseURL: URL
    /// "", "/isbn", or "/isbn-web"
    let prefix: String

    var endpoint: URL {
        // Build URL without using main-actor isolated URL.append(path:)
        var base = baseURL.absoluteString
        // Ensure no trailing slash on base
        if base.hasSuffix("/") { base.removeLast() }

        var pref = prefix
        if pref.hasPrefix("/") { pref.removeFirst() }
        if !pref.isEmpty { base += "/\(pref)" }
        base += "/token/ebay-browse"

        // Force-unwrap is acceptable here because inputs are controlled and previously valid URLs
        return URL(string: base) ?? baseURL
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
            samples: Array(samples.prefix(3))
        )
    }
}

// MARK: - Scanner Pricing ViewModel

@MainActor
final class ScannerPricingVM: ObservableObject {
    @Published var isLoading = false
    @Published var summary: PriceSummary?
    @Published var error: String?

    private let broker: EbayTokenBroker
    private let zip: String

    init(broker: EbayTokenBroker, zip: String = "60601") {
        self.broker = broker
        self.zip = zip
    }

    func load(for gtin: String) {
        isLoading = true
        error = nil
        summary = nil

        Task {
            do {
                let s = try await EbayBrowseAPI.priceSummary(gtin: gtin, zip: zip, broker: broker)
                self.summary = s
            } catch {
                self.error = (error as NSError).localizedDescription
            }
            self.isLoading = false
        }
    }
}

