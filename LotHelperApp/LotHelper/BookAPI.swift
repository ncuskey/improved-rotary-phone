import Foundation

enum BookAPIError: Error, LocalizedError {
    case badStatus(code: Int, body: String?)

    var errorDescription: String? {
        switch self {
        case .badStatus(let code, let body):
            if let body, !body.isEmpty {
                return "Server responded with status \(code): \(body)"
            } else {
                return "Server responded with status \(code)."
            }
        }
    }
}

struct ISBNLookupResponse: Codable {
    let isbn: String?
    let title: String?
    let subtitle: String?
    let author: String?
    let authors: [String]?
    let publishedYear: Int?
    let pageCount: Int?
    let description: String?
    let thumbnail: String?
    let infoLink: String?
    let categories: [String]?

    enum CodingKeys: String, CodingKey {
        case isbn
        case title
        case subtitle
        case author
        case authors
        case publishedYear = "published_year"
        case pageCount = "page_count"
        case description
        case thumbnail
        case infoLink = "info_link"
        case categories
    }
}

struct BookInfo {
    let isbn: String
    let title: String
    let author: String
    let authors: [String]
    let subtitle: String?
    let description: String?
    let publishedYear: Int?
    let thumbnail: String
    let categories: [String]

    init(
        isbn: String,
        title: String,
        author: String,
        authors: [String],
        subtitle: String? = nil,
        description: String? = nil,
        publishedYear: Int? = nil,
        thumbnail: String,
        categories: [String] = []
    ) {
        self.isbn = isbn
        self.title = title
        self.author = author
        self.authors = authors
        self.subtitle = subtitle
        self.description = description
        self.publishedYear = publishedYear
        self.thumbnail = thumbnail
        self.categories = categories
    }

    var additionalAuthors: [String] {
        authors.filter { $0.caseInsensitiveCompare(author) != .orderedSame }
    }
}

struct BookMetadataDetails: Codable, Hashable {
    let title: String?
    let subtitle: String?
    let authors: [String]?
    let creditedAuthors: [String]?
    let canonicalAuthor: String?
    let publisher: String?
    let publishedYear: Int?
    let description: String?
    let thumbnail: String?
    let categories: [String]?
    let seriesName: String?
    let seriesIndex: Int?

    enum CodingKeys: String, CodingKey {
        case title
        case subtitle
        case authors
        case creditedAuthors = "credited_authors"
        case canonicalAuthor = "canonical_author"
        case publisher
        case publishedYear = "published_year"
        case description
        case thumbnail
        case categories
        case seriesName = "series_name"
        case seriesIndex = "series_index"
    }

    var primaryAuthor: String? {
        creditedAuthors?.first ?? authors?.first ?? canonicalAuthor
    }
}

struct VendorOffer: Codable, Hashable {
    let vendorName: String
    let vendorId: String
    let price: Double
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case vendorName = "vendor_name"
        case vendorId = "vendor_id"
        case price
        case updatedAt = "updated_at"
    }
}

struct BooksRunOffer: Codable, Hashable {
    let condition: String?
    let cashPrice: Double?
    let storeCredit: Double?
    let currency: String?
    let url: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case condition
        case cashPrice = "cash_price"
        case storeCredit = "store_credit"
        case currency
        case url
        case updatedAt = "updated_at"
    }
}

struct BookScouterResult: Codable, Hashable {
    let isbn10: String?  // Can be null if BookScouter doesn't have ISBN-10
    let isbn13: String?  // Can be null if BookScouter doesn't have ISBN-13
    let offers: [VendorOffer]
    let bestPrice: Double
    let bestVendor: String?
    let totalVendors: Int
    let amazonSalesRank: Int?  // Lower rank = more popular/higher demand
    let amazonCount: Int?  // Number of sellers on Amazon
    let amazonLowestPrice: Double?  // Lowest price on Amazon
    let amazonTradeInPrice: Double?  // Amazon trade-in value

    enum CodingKeys: String, CodingKey {
        case isbn10 = "isbn_10"
        case isbn13 = "isbn_13"
        case offers
        case bestPrice = "best_price"
        case bestVendor = "best_vendor"
        case totalVendors = "total_vendors"
        case amazonSalesRank = "amazon_sales_rank"
        case amazonCount = "amazon_count"
        case amazonLowestPrice = "amazon_lowest_price"
        case amazonTradeInPrice = "amazon_trade_in_price"
    }

    var topOffers: [VendorOffer] {
        Array(offers.sorted { $0.price > $1.price }.prefix(3))
    }
}

struct EbayMarketData: Codable, Hashable {
    let activeCount: Int?
    let soldCount: Int?
    let sellThroughRate: Double?
    let currency: String?
    let soldCompsCount: Int?
    let soldCompsMin: Double?
    let soldCompsMedian: Double?
    let soldCompsMax: Double?
    let soldCompsIsEstimate: Bool?
    let soldCompsSource: String?
    let soldCompsLastSoldDate: String?
    // Smart filtering metadata
    let signedListingsDetected: Int?
    let lotListingsDetected: Int?
    let filteredCount: Int?
    let totalListings: Int?

    enum CodingKeys: String, CodingKey {
        case activeCount = "active_count"
        case soldCount = "sold_count"
        case sellThroughRate = "sell_through_rate"
        case currency = "currency"
        case soldCompsCount = "sold_comps_count"
        case soldCompsMin = "sold_comps_min"
        case soldCompsMedian = "sold_comps_median"
        case soldCompsMax = "sold_comps_max"
        case soldCompsIsEstimate = "sold_comps_is_estimate"
        case soldCompsSource = "sold_comps_source"
        case soldCompsLastSoldDate = "sold_comps_last_sold_date"
        case signedListingsDetected = "signed_listings_detected"
        case lotListingsDetected = "lot_listings_detected"
        case filteredCount = "filtered_count"
        case totalListings = "total_listings"
    }

    var profitPotential: String {
        guard let median = soldCompsMedian else { return "Unknown" }
        if median < 5 { return "Low" }
        if median < 15 { return "Medium" }
        return "High"
    }
}

// MARK: - Price Variants Response Types

struct PriceVariant: Codable, Identifiable, Hashable {
    let condition: String?
    let features: [String]?
    let description: String?
    let price: Double
    let priceDifference: Double
    let percentageChange: Double
    let sampleSize: Int
    let dataSource: String

    var id: String {
        if let features = features, !features.isEmpty {
            return features.joined(separator: ",")
        } else if let condition = condition {
            return condition
        } else {
            return description ?? UUID().uuidString
        }
    }

    enum CodingKeys: String, CodingKey {
        case condition
        case features
        case description
        case price
        case priceDifference = "price_difference"
        case percentageChange = "percentage_change"
        case sampleSize = "sample_size"
        case dataSource = "data_source"
    }
}

struct PriceVariantsResponse: Codable {
    let basePrice: Double
    let currentCondition: String
    let currentPrice: Double
    let conditionVariants: [PriceVariant]
    let featureVariants: [PriceVariant]

    enum CodingKeys: String, CodingKey {
        case basePrice = "base_price"
        case currentCondition = "current_condition"
        case currentPrice = "current_price"
        case conditionVariants = "condition_variants"
        case featureVariants = "feature_variants"
    }
}

struct BookEvaluationRecord: Codable, Identifiable, Hashable {
    let isbn: String
    let originalIsbn: String?
    let condition: String?
    let edition: String?
    let quantity: Int?
    let estimatedPrice: Double?
    let probabilityScore: Double?
    let probabilityLabel: String?
    let justification: [String]?
    let metadata: BookMetadataDetails?
    let market: EbayMarketData?
    let booksrun: BooksRunOffer?
    let booksrunValueLabel: String?
    let booksrunValueRatio: Double?
    let bookscouter: BookScouterResult?
    let bookscouterValueLabel: String?
    let bookscouterValueRatio: Double?
    let rarity: Double?
    let updatedAt: String?
    let createdAt: String?
    let timeToSellDays: Int?

    var id: String { isbn }

    enum CodingKeys: String, CodingKey {
        case isbn
        case originalIsbn = "original_isbn"
        case condition
        case edition
        case quantity
        case estimatedPrice = "estimated_price"
        case probabilityScore = "probability_score"
        case probabilityLabel = "probability_label"
        case justification
        case metadata
        case market
        case booksrun
        case booksrunValueLabel = "booksrun_value_label"
        case booksrunValueRatio = "booksrun_value_ratio"
        case bookscouter
        case bookscouterValueLabel = "bookscouter_value_label"
        case bookscouterValueRatio = "bookscouter_value_ratio"
        case rarity
        case updatedAt = "updated_at"
        case createdAt = "created_at"
        case timeToSellDays = "time_to_sell_days"
    }
}

struct LotSuggestionDTO: Codable, Identifiable, Hashable {
    let lotID: Int?
    let name: String
    let strategy: String
    let bookIsbns: [String]
    let estimatedValue: Double
    let probabilityScore: Double
    let probabilityLabel: String
    let sellThrough: Double?
    let justification: [String]?
    let displayAuthorLabel: String?
    let canonicalAuthor: String?
    let canonicalSeries: String?
    let seriesName: String?
    let books: [BookEvaluationRecord]?
    let marketJson: String?

    // Lot pricing fields from eBay lot comp data
    let lotMarketValue: Double?
    let lotOptimalSize: Int?
    let lotPerBookPrice: Double?
    let lotCompsCount: Int?
    let useLotPricing: Bool?
    let individualValue: Double?  // Sum of individual book prices (for comparison)

    // Generate unique ID from lotID or create one from name + strategy
    var id: String {
        if let lotID = lotID {
            return String(lotID)
        }
        // Fallback: combine name and strategy to ensure uniqueness
        return "\(name)|\(strategy)"
    }

    enum CodingKeys: String, CodingKey {
        case lotID = "id"
        case name
        case strategy
        case bookIsbns = "book_isbns"
        case estimatedValue = "estimated_value"
        case probabilityScore = "probability_score"
        case probabilityLabel = "probability_label"
        case sellThrough = "sell_through"
        case justification
        case displayAuthorLabel = "display_author_label"
        case canonicalAuthor = "canonical_author"
        case canonicalSeries = "canonical_series"
        case seriesName = "series_name"
        case books
        case marketJson = "market_json"
        case lotMarketValue = "lot_market_value"
        case lotOptimalSize = "lot_optimal_size"
        case lotPerBookPrice = "lot_per_book_price"
        case lotCompsCount = "lot_comps_count"
        case useLotPricing = "use_lot_pricing"
        case individualValue = "individual_value"
    }
}

enum BookAPI {
    static let baseURLString = "https://lothelper.clevergirl.app"

    private static let session: URLSession = {
        let configuration = URLSessionConfiguration.default
        configuration.waitsForConnectivity = true
        configuration.timeoutIntervalForRequest = 30.0  // 30 second request timeout
        configuration.timeoutIntervalForResource = 60.0 // 60 second resource timeout
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData  // Don't use stale cache
        configuration.urlCache = URLCache.shared
        return URLSession(configuration: configuration)
    }()

    // Long-running session for expensive operations like lot recalculation
    private static let longRunningSession: URLSession = {
        let configuration = URLSessionConfiguration.default
        configuration.waitsForConnectivity = true
        configuration.timeoutIntervalForRequest = 300.0  // 5 minute request timeout
        configuration.timeoutIntervalForResource = 600.0 // 10 minute resource timeout
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.urlCache = URLCache.shared
        return URLSession(configuration: configuration)
    }()

    private static func decodeOnWorker<T: Decodable>(_ type: T.Type, from data: Data) async throws -> T {
        try await Task.detached(priority: .utility) {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .useDefaultKeys
            return try decoder.decode(type, from: data)
        }.value
    }

    /// Async/await variant for ISBN lookup.
    static func lookupISBN(_ isbn: String) async throws -> ISBNLookupResponse {
        guard let url = URL(string: "\(baseURLString)/isbn") else {
            print("❌ Bad URL: \(baseURLString)/isbn")
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let payload = ["isbn": isbn]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)

        print("📡 Fetching ISBN \(isbn) from \(url.absoluteString)")
        let (data, response) = try await session.data(for: request)
        print("✅ Received response (\(data.count) bytes)")

        if let json = String(data: data, encoding: .utf8) {
            print("🔎 Raw response JSON:\n\(json)")
        }

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            throw BookAPIError.badStatus(code: http.statusCode, body: String(data: data, encoding: .utf8))
        }

        return try await decodeOnWorker(ISBNLookupResponse.self, from: data)
    }

    static func fetchBookInfo(_ isbn: String) async throws -> BookInfo {
        let lookup = try await lookupISBN(isbn)
        let resolvedISBN = lookup.isbn ?? isbn
        let authors = lookup.authors ?? (lookup.author.map { [$0] } ?? [])
        let primaryAuthor = lookup.author ?? authors.first ?? "Unknown Author"
        let title = lookup.title ?? "Untitled"
        let thumbnail = (lookup.thumbnail?.isEmpty == false)
            ? lookup.thumbnail!
            : "https://covers.openlibrary.org/b/isbn/\(resolvedISBN)-L.jpg"

        return BookInfo(
            isbn: resolvedISBN,
            title: title,
            author: primaryAuthor,
            authors: authors,
            subtitle: lookup.subtitle,
            description: lookup.description,
            publishedYear: lookup.publishedYear,
            thumbnail: thumbnail,
            categories: lookup.categories ?? []
        )
    }

    /// Completion-based wrapper for fetchBookInfo
    static func fetchBookInfo(_ isbn: String, completion: @escaping (BookInfo?) -> Void) {
        Task {
            do {
                let info = try await fetchBookInfo(isbn)
                await MainActor.run { completion(info) }
            } catch let error as URLError {
                print("❌ Network error for ISBN \(isbn): \(error.localizedDescription)")
                print("   Code: \(error.code.rawValue)")
                if let url = error.failingURL {
                    print("   URL: \(url.absoluteString)")
                }
                await MainActor.run { completion(nil) }
            } catch {
                print("❌ POST/Decode error for ISBN \(isbn): \(error)")
                await MainActor.run { completion(nil) }
            }
        }
    }

    /// Completion-based convenience wrapper matching the original API
    static func postISBNToBackend(_ isbn: String, completion: @escaping (BookInfo?) -> Void) {
        fetchBookInfo(isbn, completion: completion)
    }

    /// Post ISBN with book attributes
    static func postISBNWithAttributes(
        _ isbn: String,
        condition: String?,
        edition: String?,
        coverType: String?,
        printing: String?,
        signed: Bool?,
        completion: @escaping (BookInfo?) -> Void
    ) {
        Task {
            do {
                guard let url = URL(string: "\(baseURLString)/isbn") else {
                    throw URLError(.badURL)
                }

                var payload: [String: Any] = ["isbn": isbn]
                if let condition = condition { payload["condition"] = condition }
                if let edition = edition { payload["edition"] = edition }
                if let coverType = coverType { payload["cover_type"] = coverType }
                if let printing = printing { payload["printing"] = printing }
                if let signed = signed { payload["signed"] = signed }

                let jsonData = try JSONSerialization.data(withJSONObject: payload)
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = jsonData

                let (data, response) = try await session.data(for: request)

                guard let http = response as? HTTPURLResponse else {
                    throw URLError(.badServerResponse)
                }

                if !(200...299).contains(http.statusCode) {
                    let body = String(data: data, encoding: .utf8)
                    print("❌ POST /isbn failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
                    throw BookAPIError.badStatus(code: http.statusCode, body: body)
                }

                let lookup = try await decodeOnWorker(ISBNLookupResponse.self, from: data)
                let resolvedISBN = lookup.isbn ?? isbn
                let authors = lookup.authors ?? (lookup.author.map { [$0] } ?? [])
                let primaryAuthor = lookup.author ?? authors.first ?? "Unknown Author"
                let title = lookup.title ?? "Untitled"
                let thumbnail = (lookup.thumbnail?.isEmpty == false)
                    ? lookup.thumbnail!
                    : "https://covers.openlibrary.org/b/isbn/\(resolvedISBN)-L.jpg"

                let info = BookInfo(
                    isbn: resolvedISBN,
                    title: title,
                    author: primaryAuthor,
                    authors: authors,
                    subtitle: lookup.subtitle,
                    description: lookup.description,
                    publishedYear: lookup.publishedYear,
                    thumbnail: thumbnail,
                    categories: lookup.categories ?? []
                )

                await MainActor.run { completion(info) }
            } catch {
                print("POST /isbn with attributes error: \(error)")
                await MainActor.run { completion(nil) }
            }
        }
    }

    /// Fetch full evaluation for a single book (for triage)
    static func fetchBookEvaluation(_ isbn: String) async throws -> BookEvaluationRecord {
        guard let url = URL(string: "\(baseURLString)/api/books/\(isbn)/evaluate") else {
            throw URLError(.badURL)
        }

        let (data, response) = try await session.data(from: url)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ GET /api/books/\(isbn)/evaluate failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        return try await decodeOnWorker(BookEvaluationRecord.self, from: data)
    }

    /// Completion-based wrapper for fetchBookEvaluation
    static func fetchBookEvaluation(_ isbn: String, completion: @escaping (BookEvaluationRecord?) -> Void) {
        Task {
            do {
                let evaluation = try await fetchBookEvaluation(isbn)
                await MainActor.run { completion(evaluation) }
            } catch {
                print("Fetch evaluation error: \(error)")
                await MainActor.run { completion(nil) }
            }
        }
    }

    /// Fetch price variants for a book showing how price changes with different conditions and features
    static func fetchPriceVariants(_ isbn: String, condition: String? = nil) async throws -> PriceVariantsResponse {
        var urlComponents = URLComponents(string: "\(baseURLString)/api/books/\(isbn)/price-variants")!

        if let condition = condition {
            urlComponents.queryItems = [URLQueryItem(name: "condition", value: condition)]
        }

        guard let url = urlComponents.url else {
            throw URLError(.badURL)
        }

        let (data, response) = try await session.data(from: url)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ GET /api/books/\(isbn)/price-variants failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        return try await decodeOnWorker(PriceVariantsResponse.self, from: data)
    }

    /// Completion-based wrapper for fetchPriceVariants
    static func fetchPriceVariants(_ isbn: String, condition: String? = nil, completion: @escaping (PriceVariantsResponse?) -> Void) {
        Task {
            do {
                let variants = try await fetchPriceVariants(isbn, condition: condition)
                await MainActor.run { completion(variants) }
            } catch {
                print("Fetch price variants error: \(error)")
                await MainActor.run { completion(nil) }
            }
        }
    }

    /// Delete a book from the database
    static func deleteBook(_ isbn: String) async throws {
        guard let url = URL(string: "\(baseURLString)/api/books/\(isbn)/json") else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"

        let (data, response) = try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ DELETE /api/books/\(isbn)/json failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }
    }

    /// Fetch all books from the /api/books/all endpoint
    static func fetchAllBooks() async throws -> [BookEvaluationRecord] {
        guard let url = URL(string: "\(baseURLString)/api/books/all") else {
            print("❌ Bad URL for /api/books/all")
            throw URLError(.badURL)
        }

        print("📡 Fetching all books from \(url.absoluteString)")
        let (data, response) = try await session.data(from: url)
        print("✅ Received \(data.count) bytes")

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ GET /api/books/all failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        do {
            let books = try await decodeOnWorker([BookEvaluationRecord].self, from: data)
            print("✅ Decoded \(books.count) books successfully")
            return books
        } catch {
            print("❌ Failed to decode books: \(error)")
            if let jsonString = String(data: data, encoding: .utf8) {
                print("📄 Response preview: \(String(jsonString.prefix(500)))")
            }
            throw error
        }
    }

    /// Completion-based wrapper for fetchAllBooks
    static func fetchAllBooks(completion: @escaping ([BookEvaluationRecord]?) -> Void) {
        Task {
            do {
                let books = try await fetchAllBooks()
                await MainActor.run { completion(books) }
            } catch {
                print("Fetch all books error: \(error)")
                await MainActor.run { completion(nil) }
            }
        }
    }

    /// Fetch books updated since a given timestamp (incremental sync)
    static func fetchBooksUpdatedSince(_ timestamp: Date) async throws -> [BookEvaluationRecord] {
        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let sinceParam = isoFormatter.string(from: timestamp)

        guard var urlComponents = URLComponents(string: "\(baseURLString)/api/books/all") else {
            throw URLError(.badURL)
        }
        urlComponents.queryItems = [URLQueryItem(name: "since", value: sinceParam)]

        guard let url = urlComponents.url else {
            throw URLError(.badURL)
        }

        print("📡 Fetching books updated since \(sinceParam)")
        let (data, response) = try await session.data(from: url)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ GET /api/books/all?since=... failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        let books = try await decodeOnWorker([BookEvaluationRecord].self, from: data)
        print("✅ Fetched \(books.count) updated books")
        return books
    }

    /// Fetch all lot suggestions from the /api/lots/list.json endpoint
    static func fetchAllLots() async throws -> [LotSuggestionDTO] {
        guard let url = URL(string: "\(baseURLString)/api/lots/list.json") else {
            throw URLError(.badURL)
        }

        let (data, response) = try await session.data(from: url)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ GET /api/lots/list.json failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        return try await decodeOnWorker([LotSuggestionDTO].self, from: data)
    }

    /// Completion-based wrapper for fetchAllLots
    static func fetchAllLots(completion: @escaping ([LotSuggestionDTO]?) -> Void) {
        Task {
            do {
                let lots = try await fetchAllLots()
                await MainActor.run { completion(lots) }
            } catch {
                print("Fetch all lots error: \(error)")
                await MainActor.run { completion(nil) }
            }
        }
    }

    /// Trigger lot recalculation and return fresh lots
    /// This is a long-running operation that includes eBay lot comp searches
    /// Uses extended timeout (5 minutes) to allow for market data collection
    static func regenerateLots() async throws -> [LotSuggestionDTO] {
        guard let url = URL(string: "\(baseURLString)/api/lots/regenerate.json") else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // Use long-running session for this expensive operation
        let (data, response) = try await longRunningSession.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ POST /api/lots/regenerate.json failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        return try await decodeOnWorker([LotSuggestionDTO].self, from: data)
    }

    /// Search for book metadata by title and author
    static func searchMetadata(
        title: String,
        author: String? = nil,
        publicationYear: Int? = nil,
        edition: String? = nil
    ) async throws -> [MetadataSearchResult] {
        guard let url = URL(string: "\(baseURLString)/api/books/search-metadata") else {
            throw URLError(.badURL)
        }

        var payload: [String: Any] = ["title": title]
        if let author = author { payload["author"] = author }
        if let year = publicationYear { payload["publication_year"] = year }
        if let edition = edition { payload["edition"] = edition }

        let jsonData = try JSONSerialization.data(withJSONObject: payload)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = jsonData

        let (data, response) = try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ POST /api/books/search-metadata failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        struct SearchResponse: Codable {
            let results: [MetadataSearchResult]
            let total: Int
        }

        let searchResponse = try await decodeOnWorker(SearchResponse.self, from: data)
        return searchResponse.results
    }

    /// Log a scan decision with optional location data
    static func logScan(
        isbn: String,
        decision: String,
        locationName: String? = nil,
        locationAddress: String? = nil,
        locationLatitude: Double? = nil,
        locationLongitude: Double? = nil,
        locationAccuracy: Double? = nil,
        deviceId: String? = nil,
        appVersion: String? = nil,
        notes: String? = nil
    ) async throws {
        guard let url = URL(string: "\(baseURLString)/api/books/log-scan") else {
            throw URLError(.badURL)
        }

        var payload: [String: Any] = [
            "isbn": isbn,
            "decision": decision
        ]

        if let locationName = locationName { payload["location_name"] = locationName }
        if let locationAddress = locationAddress { payload["location_address"] = locationAddress }
        if let locationLatitude = locationLatitude { payload["location_latitude"] = locationLatitude }
        if let locationLongitude = locationLongitude { payload["location_longitude"] = locationLongitude }
        if let locationAccuracy = locationAccuracy { payload["location_accuracy"] = locationAccuracy }
        if let deviceId = deviceId { payload["device_id"] = deviceId }
        if let appVersion = appVersion { payload["app_version"] = appVersion }
        if let notes = notes { payload["notes"] = notes }

        let jsonData = try JSONSerialization.data(withJSONObject: payload)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = jsonData

        let (data, response) = try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ POST /api/books/log-scan failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        print("✓ Logged scan: \(isbn) - \(decision)")
    }

    /// Accept a book and add it to inventory
    static func acceptBook(
        isbn: String,
        condition: String = "Good",
        edition: String? = nil,
        locationName: String? = nil,
        locationLatitude: Double? = nil,
        locationLongitude: Double? = nil,
        locationAccuracy: Double? = nil,
        deviceId: String? = nil,
        appVersion: String? = nil
    ) async throws -> BookEvaluationRecord {
        guard let url = URL(string: "\(baseURLString)/api/books/\(isbn)/accept") else {
            throw URLError(.badURL)
        }

        var payload: [String: Any] = [
            "condition": condition
        ]

        if let edition = edition, !edition.isEmpty {
            payload["edition"] = edition
        }

        let jsonData = try JSONSerialization.data(withJSONObject: payload)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = jsonData

        print("📡 Accepting book: \(isbn)")
        let (data, response) = try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ POST /api/books/\(isbn)/accept failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        struct AcceptResponse: Codable {
            let success: Bool
            let book: BookEvaluationRecord
        }

        let acceptResponse = try await decodeOnWorker(AcceptResponse.self, from: data)

        // Also log the ACCEPT decision in scan history
        try await logScan(
            isbn: isbn,
            decision: "ACCEPT",
            locationName: locationName,
            locationLatitude: locationLatitude,
            locationLongitude: locationLongitude,
            locationAccuracy: locationAccuracy,
            deviceId: deviceId,
            appVersion: appVersion,
            notes: "User tapped Accept"
        )

        print("✓ Book accepted and added to inventory: \(isbn)")
        return acceptResponse.book
    }

    /// Reject a book and remove from inventory (set status to REJECT)
    static func rejectBook(isbn: String) async throws {
        guard let url = URL(string: "\(baseURLString)/api/books/\(isbn)/reject") else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        print("📡 Rejecting book: \(isbn)")
        let (data, response) = try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ POST /api/books/\(isbn)/reject failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        print("✓ Book rejected: \(isbn)")
    }

    /// Get scan history with optional filters
    static func getScanHistory(
        limit: Int = 100,
        isbn: String? = nil,
        locationName: String? = nil,
        decision: String? = nil
    ) async throws -> [ScanHistoryRecord] {
        var components = URLComponents(string: "\(baseURLString)/api/books/scan-history")!
        var queryItems: [URLQueryItem] = [URLQueryItem(name: "limit", value: String(limit))]

        if let isbn = isbn { queryItems.append(URLQueryItem(name: "isbn", value: isbn)) }
        if let locationName = locationName { queryItems.append(URLQueryItem(name: "location_name", value: locationName)) }
        if let decision = decision { queryItems.append(URLQueryItem(name: "decision", value: decision)) }

        components.queryItems = queryItems

        guard let url = components.url else {
            throw URLError(.badURL)
        }

        let (data, response) = try await session.data(from: url)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        struct HistoryResponse: Codable {
            let scans: [ScanHistoryRecord]
            let total: Int
        }

        let historyResponse = try await decodeOnWorker(HistoryResponse.self, from: data)
        return historyResponse.scans
    }

    /// Get scan location summaries
    static func getScanLocations() async throws -> [ScanLocationSummary] {
        guard let url = URL(string: "\(baseURLString)/api/books/scan-locations") else {
            throw URLError(.badURL)
        }

        let (data, response) = try await session.data(from: url)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        struct LocationsResponse: Codable {
            let locations: [ScanLocationSummary]
            let total: Int
        }

        let locationsResponse = try await decodeOnWorker(LocationsResponse.self, from: data)
        return locationsResponse.locations
    }

    /// Get scan statistics
    static func getScanStats() async throws -> ScanStatistics {
        guard let url = URL(string: "\(baseURLString)/api/books/scan-stats") else {
            throw URLError(.badURL)
        }

        let (data, response) = try await session.data(from: url)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        let stats = try await decodeOnWorker(ScanStatistics.self, from: data)
        return stats
    }
}

struct MetadataSearchResult: Codable, Identifiable, Hashable {
    let isbn13: String?
    let isbn10: String?
    let title: String
    let subtitle: String?
    let authors: [String]
    let publisher: String?
    let publicationYear: Int?
    let coverUrl: String?
    let description: String?
    let categories: [String]
    let seriesName: String?
    let seriesIndex: Int?
    let source: String
    let ebaySearchUrl: String
    let googleSearchUrl: String

    var id: String {
        isbn13 ?? isbn10 ?? title
    }

    var preferredIsbn: String? {
        isbn13 ?? isbn10
    }

    enum CodingKeys: String, CodingKey {
        case isbn13 = "isbn_13"
        case isbn10 = "isbn_10"
        case title
        case subtitle
        case authors
        case publisher
        case publicationYear = "publication_year"
        case coverUrl = "cover_url"
        case description
        case categories
        case seriesName = "series_name"
        case seriesIndex = "series_index"
        case source
        case ebaySearchUrl = "ebay_search_url"
        case googleSearchUrl = "google_search_url"
    }
}

struct ScanHistoryRecord: Codable, Identifiable, Hashable {
    let id: Int
    let isbn: String
    let scannedAt: String
    let decision: String
    let title: String?
    let authors: String?
    let estimatedPrice: Double?
    let probabilityLabel: String?
    let probabilityScore: Double?
    let locationName: String?
    let locationAddress: String?
    let locationLatitude: Double?
    let locationLongitude: Double?
    let locationAccuracy: Double?
    let deviceId: String?
    let appVersion: String?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case id
        case isbn
        case scannedAt = "scanned_at"
        case decision
        case title
        case authors
        case estimatedPrice = "estimated_price"
        case probabilityLabel = "probability_label"
        case probabilityScore = "probability_score"
        case locationName = "location_name"
        case locationAddress = "location_address"
        case locationLatitude = "location_latitude"
        case locationLongitude = "location_longitude"
        case locationAccuracy = "location_accuracy"
        case deviceId = "device_id"
        case appVersion = "app_version"
        case notes
    }
}

struct ScanLocationSummary: Codable, Identifiable, Hashable {
    let locationName: String
    let scanCount: Int
    let acceptedCount: Int
    let rejectedCount: Int
    let lastScan: String

    var id: String { locationName }

    var acceptanceRate: Double {
        guard scanCount > 0 else { return 0 }
        return Double(acceptedCount) / Double(scanCount) * 100
    }

    enum CodingKeys: String, CodingKey {
        case locationName = "location_name"
        case scanCount = "scan_count"
        case acceptedCount = "accepted_count"
        case rejectedCount = "rejected_count"
        case lastScan = "last_scan"
    }
}

struct ScanStatistics: Codable {
    let totalScans: Int
    let uniqueBooks: Int
    let accepted: Int
    let rejected: Int
    let skipped: Int
    let firstScan: String?
    let lastScan: String?
    let uniqueLocations: Int

    enum CodingKeys: String, CodingKey {
        case totalScans = "total_scans"
        case uniqueBooks = "unique_books"
        case accepted
        case rejected
        case skipped
        case firstScan = "first_scan"
        case lastScan = "last_scan"
        case uniqueLocations = "unique_locations"
    }
}

// MARK: - eBay Listing Response Types

struct TitlePreviewResponse: Codable {
    let title: String
    let titleScore: Float
    let maxScore: Float
    let scorePercentage: Float

    enum CodingKeys: String, CodingKey {
        case title
        case titleScore = "title_score"
        case maxScore = "max_score"
        case scorePercentage = "score_percentage"
    }
}

struct PriceRecommendationResponse: Codable {
    let recommendedPrice: Float
    let source: String
    let compsCount: Int
    let priceRangeMin: Float
    let priceRangeMax: Float
    let featuresMatched: [String]

    enum CodingKeys: String, CodingKey {
        case recommendedPrice = "recommended_price"
        case source
        case compsCount = "comps_count"
        case priceRangeMin = "price_range_min"
        case priceRangeMax = "price_range_max"
        case featuresMatched = "features_matched"
    }
}

// MARK: - Interactive Attributes Response Types

struct EstimatePriceRequest: Codable {
    let condition: String
    let isHardcover: Bool?
    let isPaperback: Bool?
    let isMassMarket: Bool?
    let isSigned: Bool?
    let isFirstEdition: Bool?

    enum CodingKeys: String, CodingKey {
        case condition
        case isHardcover = "is_hardcover"
        case isPaperback = "is_paperback"
        case isMassMarket = "is_mass_market"
        case isSigned = "is_signed"
        case isFirstEdition = "is_first_edition"
    }
}

struct AttributeDelta: Codable, Identifiable {
    var id: String { attribute }
    let attribute: String
    let label: String
    let delta: Double
    let enabled: Bool
}

struct EstimatePriceResponse: Codable {
    let estimatedPrice: Double
    let baselinePrice: Double
    let confidence: Double
    let deltas: [AttributeDelta]
    let modelVersion: String

    enum CodingKeys: String, CodingKey {
        case estimatedPrice = "estimated_price"
        case baselinePrice = "baseline_price"
        case confidence
        case deltas
        case modelVersion = "model_version"
    }
}

struct UpdateAttributesRequest: Codable {
    let coverType: String?
    let signed: Bool
    let printing: String?

    enum CodingKeys: String, CodingKey {
        case coverType = "cover_type"
        case signed
        case printing
    }
}

// MARK: - eBay Listing Extension

extension BookAPI {
    /// Preview the generated eBay listing title with keyword score
    static func previewTitle(draft: EbayListingDraft) async throws -> TitlePreviewResponse {
        guard let url = URL(string: "\(baseURLString)/api/ebay/preview-title") else {
            throw URLError(.badURL)
        }

        let payload = draft.toAPIPayload()
        let jsonData = try JSONSerialization.data(withJSONObject: payload)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = jsonData

        print("📡 Previewing title for ISBN: \(draft.isbn)")
        let (data, response) = try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ POST /api/ebay/preview-title failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        let titlePreview = try await decodeOnWorker(TitlePreviewResponse.self, from: data)
        print("✓ Title preview generated: \(titlePreview.title)")

        return titlePreview
    }

    /// Get price recommendation based on sold comps filtered by features
    static func recommendPrice(draft: EbayListingDraft) async throws -> PriceRecommendationResponse {
        guard let url = URL(string: "\(baseURLString)/api/ebay/recommend-price") else {
            throw URLError(.badURL)
        }

        let payload = draft.toAPIPayload()
        let jsonData = try JSONSerialization.data(withJSONObject: payload)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = jsonData

        print("📡 Requesting price recommendation for ISBN: \(draft.isbn)")
        let (data, response) = try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ POST /api/ebay/recommend-price failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        let priceRecommendation = try await decodeOnWorker(PriceRecommendationResponse.self, from: data)
        print("✓ Price recommendation: $\(priceRecommendation.recommendedPrice) from \(priceRecommendation.compsCount) comps")

        return priceRecommendation
    }

    /// Create an eBay listing from a draft
    static func createEbayListing(draft: EbayListingDraft) async throws -> EbayListingResponse {
        guard let url = URL(string: "\(baseURLString)/api/ebay/create-listing") else {
            throw URLError(.badURL)
        }

        let payload = draft.toAPIPayload()
        let jsonData = try JSONSerialization.data(withJSONObject: payload)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = jsonData

        print("📡 Creating eBay listing for ISBN: \(draft.isbn)")
        let (data, response) = try await session.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ POST /api/ebay/create-listing failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        let listingResponse = try await decodeOnWorker(EbayListingResponse.self, from: data)
        print("✓ eBay listing created: \(listingResponse.title)")

        return listingResponse
    }

    /// Estimate price with user-selected attributes
    static func estimatePrice(
        isbn: String,
        condition: String,
        isHardcover: Bool?,
        isPaperback: Bool?,
        isMassMarket: Bool?,
        isSigned: Bool?,
        isFirstEdition: Bool?
    ) async throws -> EstimatePriceResponse {
        guard let url = URL(string: "\(baseURLString)/api/books/\(isbn)/estimate_price") else {
            throw URLError(.badURL)
        }

        let request = EstimatePriceRequest(
            condition: condition,
            isHardcover: isHardcover,
            isPaperback: isPaperback,
            isMassMarket: isMassMarket,
            isSigned: isSigned,
            isFirstEdition: isFirstEdition
        )

        let jsonData = try JSONEncoder().encode(request)
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = jsonData

        print("📡 Estimating price for ISBN: \(isbn) with attributes")
        let (data, response) = try await session.data(for: urlRequest)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ POST /api/books/\(isbn)/estimate_price failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        let priceResponse = try await decodeOnWorker(EstimatePriceResponse.self, from: data)
        print("✓ Price estimate: $\(priceResponse.estimatedPrice) (baseline: $\(priceResponse.baselinePrice))")

        return priceResponse
    }

    /// Save user-selected book attributes to database
    static func updateAttributes(
        isbn: String,
        coverType: String?,
        signed: Bool,
        printing: String?
    ) async throws {
        guard let url = URL(string: "\(baseURLString)/api/books/\(isbn)/attributes") else {
            throw URLError(.badURL)
        }

        let request = UpdateAttributesRequest(
            coverType: coverType,
            signed: signed,
            printing: printing
        )

        let jsonData = try JSONEncoder().encode(request)
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "PUT"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = jsonData

        print("📡 Updating attributes for ISBN: \(isbn)")
        let (data, response) = try await session.data(for: urlRequest)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ PUT /api/books/\(isbn)/attributes failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        print("✓ Attributes updated for ISBN: \(isbn)")
    }

    /// Shared singleton for SwiftUI views
    static let shared = BookAPIShared()
}

/// Wrapper to provide instance-based access for SwiftUI views
class BookAPIShared {
    func createEbayListing(draft: EbayListingDraft) async throws -> EbayListingResponse {
        try await BookAPI.createEbayListing(draft: draft)
    }
}
