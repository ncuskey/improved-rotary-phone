import Foundation
import SwiftData

private let cachedBookISOFormatter: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
}()

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
    var seriesName: String?
    var seriesIndex: Int?

    // eBay Market data fields (flattened)
    var ebayActiveCount: Int?
    var ebaySoldCount: Int?
    var ebaySellThroughRate: Double?
    var ebayCurrency: String?
    var ebaySoldCompsCount: Int?
    var ebaySoldCompsMin: Double?
    var ebaySoldCompsMedian: Double?
    var ebaySoldCompsMax: Double?
    var ebaySoldCompsIsEstimate: Bool?
    var ebaySoldCompsSource: String?
    var ebaySoldCompsLastSoldDate: String?

    // BookScouter fields (flattened)
    var bookscouterIsbn10: String?
    var bookscouterIsbn13: String?
    var bookscouterBestPrice: Double?
    var bookscouterBestVendor: String?
    var bookscouterTotalVendors: Int?
    var bookscouterAmazonSalesRank: Int?
    var bookscouterAmazonCount: Int?
    var bookscouterAmazonLowestPrice: Double?
    var bookscouterAmazonTradeInPrice: Double?
    var bookscouterOffersJSON: String? // Store offers as JSON string

    // BooksRun fields
    var booksrunCondition: String?
    var booksrunCashPrice: Double?
    var booksrunStoreCredit: Double?
    var booksrunCurrency: String?
    var booksrunUrl: String?
    var booksrunUpdatedAt: String?

    var booksrunValueLabel: String?
    var booksrunValueRatio: Double?
    var bookscouterValueLabel: String?
    var bookscouterValueRatio: Double?
    var rarity: Double?
    var remoteUpdatedAt: String?
    var remoteCreatedAt: String?

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
        self.seriesName = record.metadata?.seriesName
        self.seriesIndex = record.metadata?.seriesIndex

        // Flatten eBay market data
        self.ebayActiveCount = record.market?.activeCount
        self.ebaySoldCount = record.market?.soldCount
        self.ebaySellThroughRate = record.market?.sellThroughRate
        self.ebayCurrency = record.market?.currency
        self.ebaySoldCompsCount = record.market?.soldCompsCount
        self.ebaySoldCompsMin = record.market?.soldCompsMin
        self.ebaySoldCompsMedian = record.market?.soldCompsMedian
        self.ebaySoldCompsMax = record.market?.soldCompsMax
        self.ebaySoldCompsIsEstimate = record.market?.soldCompsIsEstimate
        self.ebaySoldCompsSource = record.market?.soldCompsSource
        self.ebaySoldCompsLastSoldDate = record.market?.soldCompsLastSoldDate

        // Flatten BookScouter
        self.bookscouterIsbn10 = record.bookscouter?.isbn10
        self.bookscouterIsbn13 = record.bookscouter?.isbn13
        self.bookscouterBestPrice = record.bookscouter?.bestPrice
        self.bookscouterBestVendor = record.bookscouter?.bestVendor
        self.bookscouterTotalVendors = record.bookscouter?.totalVendors
        self.bookscouterAmazonSalesRank = record.bookscouter?.amazonSalesRank
        self.bookscouterAmazonCount = record.bookscouter?.amazonCount
        self.bookscouterAmazonLowestPrice = record.bookscouter?.amazonLowestPrice
        self.bookscouterAmazonTradeInPrice = record.bookscouter?.amazonTradeInPrice

        // Encode offers to JSON
        if let offers = record.bookscouter?.offers {
            self.bookscouterOffersJSON = try? JSONEncoder().encode(offers).base64EncodedString()
        }

        // BooksRun
        self.booksrunCondition = record.booksrun?.condition
        self.booksrunCashPrice = record.booksrun?.cashPrice
        self.booksrunStoreCredit = record.booksrun?.storeCredit
        self.booksrunCurrency = record.booksrun?.currency
        self.booksrunUrl = record.booksrun?.url
        self.booksrunUpdatedAt = record.booksrun?.updatedAt

        self.booksrunValueLabel = record.booksrunValueLabel
        self.booksrunValueRatio = record.booksrunValueRatio
        self.bookscouterValueLabel = record.bookscouterValueLabel
        self.bookscouterValueRatio = record.bookscouterValueRatio
        self.rarity = record.rarity
        let now = Date()
        if let updated = record.updatedAt {
            self.remoteUpdatedAt = updated
        } else {
            self.remoteUpdatedAt = cachedBookISOFormatter.string(from: now)
        }
        self.remoteCreatedAt = record.createdAt

        self.lastUpdated = now
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
            categories: categoriesJSON?.jsonDecoded(),
            seriesName: seriesName,
            seriesIndex: seriesIndex
        )

        let market = EbayMarketData(
            activeCount: ebayActiveCount,
            soldCount: ebaySoldCount,
            sellThroughRate: ebaySellThroughRate,
            currency: ebayCurrency,
            soldCompsCount: ebaySoldCompsCount,
            soldCompsMin: ebaySoldCompsMin,
            soldCompsMedian: ebaySoldCompsMedian,
            soldCompsMax: ebaySoldCompsMax,
            soldCompsIsEstimate: ebaySoldCompsIsEstimate,
            soldCompsSource: ebaySoldCompsSource,
            soldCompsLastSoldDate: ebaySoldCompsLastSoldDate,
            signedListingsDetected: nil,
            lotListingsDetected: nil,
            filteredCount: nil,
            totalListings: nil
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
                amazonSalesRank: bookscouterAmazonSalesRank,
                amazonCount: bookscouterAmazonCount,
                amazonLowestPrice: bookscouterAmazonLowestPrice,
                amazonTradeInPrice: bookscouterAmazonTradeInPrice
            )
        }

        var booksrunOffer: BooksRunOffer?
        if booksrunCondition != nil ||
            booksrunCashPrice != nil ||
            booksrunStoreCredit != nil ||
            booksrunCurrency != nil ||
            booksrunUrl != nil ||
            booksrunUpdatedAt != nil {
            booksrunOffer = BooksRunOffer(
                condition: booksrunCondition,
                cashPrice: booksrunCashPrice,
                storeCredit: booksrunStoreCredit,
                currency: booksrunCurrency,
                url: booksrunUrl,
                updatedAt: booksrunUpdatedAt
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
            market: market,
            booksrun: booksrunOffer,
            booksrunValueLabel: booksrunValueLabel,
            booksrunValueRatio: booksrunValueRatio,
            bookscouter: bookscouter,
            bookscouterValueLabel: bookscouterValueLabel,
            bookscouterValueRatio: bookscouterValueRatio,
            rarity: rarity,
            updatedAt: remoteUpdatedAt ?? cachedBookISOFormatter.string(from: lastUpdated),
            createdAt: remoteCreatedAt
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

    // Lot pricing fields
    var lotMarketValue: Double?
    var lotOptimalSize: Int?
    var lotPerBookPrice: Double?
    var lotCompsCount: Int?
    var useLotPricing: Bool?
    var individualValue: Double?

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

        // Store lot pricing fields
        self.lotMarketValue = lot.lotMarketValue
        self.lotOptimalSize = lot.lotOptimalSize
        self.lotPerBookPrice = lot.lotPerBookPrice
        self.lotCompsCount = lot.lotCompsCount
        self.useLotPricing = lot.useLotPricing
        self.individualValue = lot.individualValue

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
            marketJson: marketJson,
            lotMarketValue: lotMarketValue,
            lotOptimalSize: lotOptimalSize,
            lotPerBookPrice: lotPerBookPrice,
            lotCompsCount: lotCompsCount,
            useLotPricing: useLotPricing,
            individualValue: individualValue
        )
    }
}

// MARK: - JSON Encoding/Decoding Helpers

extension Array where Element == String {
    var jsonEncoded: String? {
        guard let data = try? JSONEncoder().encode(self) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

extension String {
    func jsonDecoded() -> [String]? {
        guard let data = self.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode([String].self, from: data)
    }
}
