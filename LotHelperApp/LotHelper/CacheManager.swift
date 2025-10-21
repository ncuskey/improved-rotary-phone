import Foundation
import SwiftData

@MainActor
class CacheManager {
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
        } catch {
            print("Failed to save books to cache: \(error)")
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
        // Delete old cached lots
        do {
            try modelContext.delete(model: CachedLot.self)
        } catch {
            print("Failed to delete old cached lots: \(error)")
        }

        // Insert new cached lots
        for lot in lots {
            let cachedLot = CachedLot(from: lot)
            modelContext.insert(cachedLot)
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
        } catch {
            print("Failed to clear caches: \(error)")
        }
    }
}
