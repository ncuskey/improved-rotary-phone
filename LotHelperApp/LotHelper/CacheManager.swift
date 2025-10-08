import Foundation
import SwiftData

@MainActor
class CacheManager {
    private let modelContext: ModelContext
    private let cacheExpirationInterval: TimeInterval = 3600 // 1 hour

    init(modelContext: ModelContext) {
        self.modelContext = modelContext
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
        return Date().timeIntervalSince(mostRecent.lastUpdated) > cacheExpirationInterval
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
        return Date().timeIntervalSince(mostRecent.lastUpdated) > cacheExpirationInterval
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
