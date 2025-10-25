import Foundation
import SwiftData

@MainActor
class CacheManager {
    static let booksDidChange = Notification.Name("CacheManager.booksDidChange")

    private let modelContext: ModelContext

    // Staleness thresholds (in seconds)
    private let marketDataMaxAge: TimeInterval = 7 * 24 * 3600   // 7 days
    private let vendorDataMaxAge: TimeInterval = 14 * 24 * 3600  // 14 days
    private let metadataMaxAge: TimeInterval = 90 * 24 * 3600    // 90 days
    private let generalCacheMaxAge: TimeInterval = 24 * 3600     // 24 hours for list view

    init(modelContext: ModelContext) {
        self.modelContext = modelContext
    }

    // MARK: - Staleness Checking

    enum DataType {
        case market      // eBay pricing data
        case vendor      // BookScouter buyback data
        case metadata    // Book info (title, author, etc.)
        case general     // Overall cache freshness
    }

    func isStale(_ book: CachedBook, dataType: DataType) -> Bool {
        let age = Date().timeIntervalSince(book.lastUpdated)
        let threshold: TimeInterval

        switch dataType {
        case .market:
            threshold = marketDataMaxAge
        case .vendor:
            threshold = vendorDataMaxAge
        case .metadata:
            threshold = metadataMaxAge
        case .general:
            threshold = generalCacheMaxAge
        }

        return age > threshold
    }

    func isStale(_ record: BookEvaluationRecord, dataType: DataType) -> Bool {
        // Check if any data is missing (always stale if missing)
        switch dataType {
        case .market:
            return record.market == nil
        case .vendor:
            return record.bookscouter == nil
        case .metadata:
            return record.metadata == nil
        case .general:
            // For general staleness, we rely on the cache timestamp
            return true
        }
    }

    // MARK: - Books Cache

    func getCachedBooks() -> [BookEvaluationRecord] {
        let descriptor = FetchDescriptor<CachedBook>(sortBy: [SortDescriptor(\.lastUpdated, order: .reverse)])
        guard let cachedBooks = try? modelContext.fetch(descriptor) else {
            return []
        }
        return cachedBooks.map { $0.toBookEvaluationRecord() }
    }

    func saveBooks(_ books: [BookEvaluationRecord]) {
        // Delete old cached books
        do {
            try modelContext.delete(model: CachedBook.self)
        } catch {
            print("Failed to delete old cached books: \(error)")
        }

        // Insert new cached books
        for book in books {
            let cachedBook = CachedBook(from: book)
            modelContext.insert(cachedBook)
        }

        do {
            try modelContext.save()
            notifyBooksChanged()
        } catch {
            print("Failed to save books to cache: \(error)")
        }
    }

    func upsertBook(_ book: BookEvaluationRecord) {
        let descriptor = FetchDescriptor<CachedBook>(predicate: #Predicate { $0.isbn == book.isbn })
        if let existing = try? modelContext.fetch(descriptor), let cached = existing.first {
            modelContext.delete(cached)
        }

        let cachedBook = CachedBook(from: book)
        modelContext.insert(cachedBook)

        do {
            try modelContext.save()
            notifyBooksChanged()
        } catch {
            print("Failed to upsert book in cache: \(error)")
        }
    }

    func isBooksExpired() -> Bool {
        let descriptor = FetchDescriptor<CachedBook>(sortBy: [SortDescriptor(\.lastUpdated, order: .reverse)])
        guard let cachedBooks = try? modelContext.fetch(descriptor),
              let mostRecent = cachedBooks.first else {
            return true
        }
        return Date().timeIntervalSince(mostRecent.lastUpdated) > generalCacheMaxAge
    }

    func getStaleBooks(dataType: DataType = .market) -> [BookEvaluationRecord] {
        let descriptor = FetchDescriptor<CachedBook>(sortBy: [SortDescriptor(\.lastUpdated, order: .forward)])
        guard let cachedBooks = try? modelContext.fetch(descriptor) else {
            return []
        }

        return cachedBooks
            .filter { isStale($0, dataType: dataType) }
            .map { $0.toBookEvaluationRecord() }
    }

    func needsRefresh(_ isbn: String, dataType: DataType = .market) -> Bool {
        let descriptor = FetchDescriptor<CachedBook>(
            predicate: #Predicate { $0.isbn == isbn }
        )
        guard let cachedBooks = try? modelContext.fetch(descriptor),
              let book = cachedBooks.first else {
            return true  // Not in cache = needs refresh
        }
        return isStale(book, dataType: dataType)
    }

    // MARK: - Lots Cache

    func getCachedLots() -> [LotSuggestionDTO] {
        let descriptor = FetchDescriptor<CachedLot>(sortBy: [SortDescriptor(\.lastUpdated, order: .reverse)])
        guard let cachedLots = try? modelContext.fetch(descriptor) else {
            return []
        }
        return cachedLots.map { $0.toLotSuggestionDTO() }
    }

    func saveLots(_ lots: [LotSuggestionDTO]) {
        // Build a set of new lot IDs
        let newLotIDs = Set(lots.map { $0.id })

        // Fetch existing cached lots
        let descriptor = FetchDescriptor<CachedLot>()
        let existingLots = (try? modelContext.fetch(descriptor)) ?? []

        // Delete lots that are no longer in the new set
        for existing in existingLots {
            if !newLotIDs.contains(existing.lotID) {
                modelContext.delete(existing)
            }
        }

        // Upsert new lots (update existing, insert new)
        for lot in lots {
            let lotDescriptor = FetchDescriptor<CachedLot>(
                predicate: #Predicate { $0.lotID == lot.id }
            )

            if let existing = try? modelContext.fetch(lotDescriptor).first {
                // Update existing lot
                existing.name = lot.name
                existing.strategy = lot.strategy
                existing.bookIsbnsJSON = lot.bookIsbns.jsonEncoded
                existing.estimatedValue = lot.estimatedValue
                existing.probabilityScore = lot.probabilityScore
                existing.probabilityLabel = lot.probabilityLabel
                existing.sellThrough = lot.sellThrough
                existing.justificationJSON = lot.justification?.jsonEncoded
                existing.displayAuthorLabel = lot.displayAuthorLabel
                existing.canonicalAuthor = lot.canonicalAuthor
                existing.canonicalSeries = lot.canonicalSeries
                existing.seriesName = lot.seriesName
                existing.marketJson = lot.marketJson
                existing.lotMarketValue = lot.lotMarketValue
                existing.lotOptimalSize = lot.lotOptimalSize
                existing.lotPerBookPrice = lot.lotPerBookPrice
                existing.lotCompsCount = lot.lotCompsCount
                existing.useLotPricing = lot.useLotPricing
                existing.individualValue = lot.individualValue
                existing.lastUpdated = Date()

                // Update books JSON
                if let books = lot.books {
                    existing.booksJSON = try? JSONEncoder().encode(books).base64EncodedString()
                } else {
                    existing.booksJSON = nil
                }
            } else {
                // Insert new lot
                let cachedLot = CachedLot(from: lot)
                modelContext.insert(cachedLot)
            }
        }

        do {
            try modelContext.save()
        } catch {
            print("Failed to save lots to cache: \(error)")
        }
    }

    func isLotsExpired() -> Bool {
        let descriptor = FetchDescriptor<CachedLot>(sortBy: [SortDescriptor(\.lastUpdated, order: .reverse)])
        guard let cachedLots = try? modelContext.fetch(descriptor),
              let mostRecent = cachedLots.first else {
            return true
        }
        return Date().timeIntervalSince(mostRecent.lastUpdated) > generalCacheMaxAge
    }

    // MARK: - Cache Clearing

    func clearAllCaches() {
        do {
            try modelContext.delete(model: CachedBook.self)
            try modelContext.delete(model: CachedLot.self)
            try modelContext.save()
            notifyBooksChanged()
        } catch {
            print("Failed to clear caches: \(error)")
        }
    }

    private func notifyBooksChanged() {
        NotificationCenter.default.post(name: Self.booksDidChange, object: nil)
    }
}
