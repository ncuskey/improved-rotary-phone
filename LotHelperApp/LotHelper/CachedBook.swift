import Foundation
import SwiftData

@Model
final class CachedBook {
    @Attribute(.unique) var isbn: String
    var originalIsbn: String?
    var condition: String?
    var edition: String?
    var quantity: Int?
    var estimatedPrice: Double?
    var probabilityScore: Double?
    var probabilityLabel: String?
    var justificationJSON: String? // Store as JSON string

    // Metadata fields (flattened)
    var title: String?
    var subtitle: String?
    var authorsJSON: String? // Store as JSON string
    var creditedAuthorsJSON: String? // Store as JSON string
    var canonicalAuthor: String?
    var publisher: String?
    var publishedYear: Int?
    var bookDescription: String?
    var thumbnail: String?
    var categoriesJSON: String? // Store as JSON string

    // BookScouter fields (flattened)
    var bookscouterIsbn10: String?
    var bookscouterIsbn13: String?
    var bookscouterBestPrice: Double?
    var bookscouterBestVendor: String?
    var bookscouterTotalVendors: Int?
    var bookscouterAmazonSalesRank: Int?
    var bookscouterOffersJSON: String? // Store offers as JSON string

    var booksrunValueLabel: String?
    var booksrunValueRatio: Double?
    var bookscouterValueLabel: String?
    var bookscouterValueRatio: Double?
    var rarity: Double?

    var lastUpdated: Date

    init(from record: BookEvaluationRecord) {
        self.isbn = record.isbn
        self.originalIsbn = record.originalIsbn
        self.condition = record.condition
        self.edition = record.edition
        self.quantity = record.quantity
        self.estimatedPrice = record.estimatedPrice
        self.probabilityScore = record.probabilityScore
        self.probabilityLabel = record.probabilityLabel
        self.justificationJSON = record.justification?.jsonEncoded

        // Flatten metadata
        self.title = record.metadata?.title
        self.subtitle = record.metadata?.subtitle
        self.authorsJSON = record.metadata?.authors?.jsonEncoded
        self.creditedAuthorsJSON = record.metadata?.creditedAuthors?.jsonEncoded
        self.canonicalAuthor = record.metadata?.canonicalAuthor
        self.publisher = record.metadata?.publisher
        self.publishedYear = record.metadata?.publishedYear
        self.bookDescription = record.metadata?.description
        self.thumbnail = record.metadata?.thumbnail
        self.categoriesJSON = record.metadata?.categories?.jsonEncoded

        // Flatten BookScouter
        self.bookscouterIsbn10 = record.bookscouter?.isbn10
        self.bookscouterIsbn13 = record.bookscouter?.isbn13
        self.bookscouterBestPrice = record.bookscouter?.bestPrice
        self.bookscouterBestVendor = record.bookscouter?.bestVendor
        self.bookscouterTotalVendors = record.bookscouter?.totalVendors
        self.bookscouterAmazonSalesRank = record.bookscouter?.amazonSalesRank

        // Encode offers to JSON
        if let offers = record.bookscouter?.offers {
            self.bookscouterOffersJSON = try? JSONEncoder().encode(offers).base64EncodedString()
        }

        self.booksrunValueLabel = record.booksrunValueLabel
        self.booksrunValueRatio = record.booksrunValueRatio
        self.bookscouterValueLabel = record.bookscouterValueLabel
        self.bookscouterValueRatio = record.bookscouterValueRatio
        self.rarity = record.rarity

        self.lastUpdated = Date()
    }

    func toBookEvaluationRecord() -> BookEvaluationRecord {
        let metadata = BookMetadataDetails(
            title: title,
            subtitle: subtitle,
            authors: authorsJSON?.jsonDecoded(),
            creditedAuthors: creditedAuthorsJSON?.jsonDecoded(),
            canonicalAuthor: canonicalAuthor,
            publisher: publisher,
            publishedYear: publishedYear,
            description: bookDescription,
            thumbnail: thumbnail,
            categories: categoriesJSON?.jsonDecoded()
        )

        var bookscouter: BookScouterResult?
        if let isbn10 = bookscouterIsbn10,
           let isbn13 = bookscouterIsbn13,
           let bestPrice = bookscouterBestPrice,
           let totalVendors = bookscouterTotalVendors {

            // Decode offers from JSON
            var offers: [VendorOffer] = []
            if let offersJSON = bookscouterOffersJSON,
               let data = Data(base64Encoded: offersJSON) {
                offers = (try? JSONDecoder().decode([VendorOffer].self, from: data)) ?? []
            }

            bookscouter = BookScouterResult(
                isbn10: isbn10,
                isbn13: isbn13,
                offers: offers,
                bestPrice: bestPrice,
                bestVendor: bookscouterBestVendor,
                totalVendors: totalVendors,
                amazonSalesRank: bookscouterAmazonSalesRank
            )
        }

        return BookEvaluationRecord(
            isbn: isbn,
            originalIsbn: originalIsbn,
            condition: condition,
            edition: edition,
            quantity: quantity,
            estimatedPrice: estimatedPrice,
            probabilityScore: probabilityScore,
            probabilityLabel: probabilityLabel,
            justification: justificationJSON?.jsonDecoded(),
            metadata: metadata,
            booksrunValueLabel: booksrunValueLabel,
            booksrunValueRatio: booksrunValueRatio,
            bookscouter: bookscouter,
            bookscouterValueLabel: bookscouterValueLabel,
            bookscouterValueRatio: bookscouterValueRatio,
            rarity: rarity
        )
    }
}

@Model
final class CachedLot {
    @Attribute(.unique) var lotID: String
    var name: String
    var strategy: String
    var bookIsbnsJSON: String? // Store as JSON string
    var estimatedValue: Double
    var probabilityScore: Double
    var probabilityLabel: String
    var sellThrough: Double?
    var justificationJSON: String? // Store as JSON string
    var displayAuthorLabel: String?
    var canonicalAuthor: String?
    var canonicalSeries: String?
    var seriesName: String?
    var marketJson: String?
    var booksJSON: String? // Store books array as JSON string
    var lastUpdated: Date

    init(from lot: LotSuggestionDTO) {
        self.lotID = lot.id
        self.name = lot.name
        self.strategy = lot.strategy
        self.bookIsbnsJSON = lot.bookIsbns.jsonEncoded
        self.estimatedValue = lot.estimatedValue
        self.probabilityScore = lot.probabilityScore
        self.probabilityLabel = lot.probabilityLabel
        self.sellThrough = lot.sellThrough
        self.justificationJSON = lot.justification?.jsonEncoded
        self.displayAuthorLabel = lot.displayAuthorLabel
        self.canonicalAuthor = lot.canonicalAuthor
        self.canonicalSeries = lot.canonicalSeries
        self.seriesName = lot.seriesName
        self.marketJson = lot.marketJson

        // Encode books to JSON
        if let books = lot.books {
            self.booksJSON = try? JSONEncoder().encode(books).base64EncodedString()
        }

        self.lastUpdated = Date()
    }

    func toLotSuggestionDTO() -> LotSuggestionDTO {
        // Decode books from JSON
        var books: [BookEvaluationRecord]?
        if let booksJSON = booksJSON,
           let data = Data(base64Encoded: booksJSON) {
            books = try? JSONDecoder().decode([BookEvaluationRecord].self, from: data)
        }

        return LotSuggestionDTO(
            lotID: Int(lotID),
            name: name,
            strategy: strategy,
            bookIsbns: bookIsbnsJSON?.jsonDecoded() ?? [],
            estimatedValue: estimatedValue,
            probabilityScore: probabilityScore,
            probabilityLabel: probabilityLabel,
            sellThrough: sellThrough,
            justification: justificationJSON?.jsonDecoded(),
            displayAuthorLabel: displayAuthorLabel,
            canonicalAuthor: canonicalAuthor,
            canonicalSeries: canonicalSeries,
            seriesName: seriesName,
            books: books,
            marketJson: marketJson
        )
    }
}

// MARK: - JSON Encoding/Decoding Helpers

private extension Array where Element == String {
    var jsonEncoded: String? {
        guard let data = try? JSONEncoder().encode(self) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

private extension String {
    func jsonDecoded() -> [String]? {
        guard let data = self.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode([String].self, from: data)
    }
}
