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

struct BookScouterResult: Codable, Hashable {
    let isbn10: String
    let isbn13: String
    let offers: [VendorOffer]
    let bestPrice: Double
    let bestVendor: String?
    let totalVendors: Int
    let amazonSalesRank: Int?  // Lower rank = more popular/higher demand

    enum CodingKeys: String, CodingKey {
        case isbn10 = "isbn_10"
        case isbn13 = "isbn_13"
        case offers
        case bestPrice = "best_price"
        case bestVendor = "best_vendor"
        case totalVendors = "total_vendors"
        case amazonSalesRank = "amazon_sales_rank"
    }

    var topOffers: [VendorOffer] {
        Array(offers.sorted { $0.price > $1.price }.prefix(3))
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
    let booksrunValueLabel: String?
    let booksrunValueRatio: Double?
    let bookscouter: BookScouterResult?
    let bookscouterValueLabel: String?
    let bookscouterValueRatio: Double?
    let rarity: Double?

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
        case booksrunValueLabel = "booksrun_value_label"
        case booksrunValueRatio = "booksrun_value_ratio"
        case bookscouter
        case bookscouterValueLabel = "bookscouter_value_label"
        case bookscouterValueRatio = "bookscouter_value_ratio"
        case rarity
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

    var id: String { lotID.map(String.init) ?? name }

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
    }
}

enum BookAPI {
    static let baseURLString = "http://192.168.4.50:8000"

    private static let session: URLSession = {
        let configuration = URLSessionConfiguration.default
        configuration.waitsForConnectivity = true
        configuration.requestCachePolicy = .returnCacheDataElseLoad
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
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let payload = ["isbn": isbn]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)

        let (data, response) = try await session.data(for: request)

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
            : "https://covers.openlibrary.org/b/isbn/\(resolvedISBN)-M.jpg"

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
            } catch {
                print("POST/Decode error: \(error)")
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
                    : "https://covers.openlibrary.org/b/isbn/\(resolvedISBN)-M.jpg"

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

    /// Fetch all books from the /api/books/all endpoint
    static func fetchAllBooks() async throws -> [BookEvaluationRecord] {
        guard let url = URL(string: "\(baseURLString)/api/books/all") else {
            throw URLError(.badURL)
        }

        let (data, response) = try await session.data(from: url)

        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        if !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            print("❌ GET /api/books/all failed — status: \(http.statusCode)\nResponse body: \(body ?? "<no body>")")
            throw BookAPIError.badStatus(code: http.statusCode, body: body)
        }

        return try await decodeOnWorker([BookEvaluationRecord].self, from: data)
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
}
