import SwiftUI
import SwiftData

struct LotRecommendationsView: View {
    // Optional BookScouter integration inputs
    var bookscouter: Bool = false
    var bookscouterValueLabel: String = ""
    var bookscouterValueRatio: Double = 0.0

    @Environment(\.modelContext) private var modelContext
    @State private var lots: [LotSuggestionDTO] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    private var cacheManager: CacheManager { CacheManager(modelContext: modelContext) }

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    List(Array(repeating: LotSuggestionDTO.placeholder, count: 5), id: \.name) { lot in
                        LotSummaryRow(lot: lot)
                    }
                    .listStyle(.plain)
                    .scrollDisabled(true)
                    .redacted(reason: .placeholder)
                    .background(DS.Color.background)
                } else if let errorMessage {
                    EmptyStateView(
                        systemImage: "exclamationmark.triangle",
                        title: "Lots Unavailable",
                        message: errorMessage,
                        actionTitle: "Try Again"
                    ) {
                        Task { await loadLots() }
                    }
                } else if lots.isEmpty {
                    EmptyStateView(
                        systemImage: "shippingbox",
                        title: "No Lots Yet",
                        message: "Generate a fresh batch of recommendations to see them here.",
                        actionTitle: "Refresh"
                    ) {
                        Task { await loadLots() }
                    }
                } else {
                    List(lots) { lot in
                        NavigationLink(value: lot) {
                            LotSummaryRow(lot: lot)
                        }
                        .listRowBackground(DS.Color.cardBg)
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                    .background(DS.Color.background)
                    .refreshable { await loadLots() }
                    .navigationDestination(for: LotSuggestionDTO.self) { lot in
                        LotDetailView(lot: lot)
                    }
                }
            }
            .navigationTitle("Lots")
            .task { await initialLoadIfNeeded() }
        }
        .background(DS.Color.background)
    }

    @MainActor
    private func initialLoadIfNeeded() async {
        if lots.isEmpty && !isLoading {
            // Load from cache first
            let cachedLots = cacheManager.getCachedLots()
            if !cachedLots.isEmpty {
                lots = cachedLots
            }

            // Fetch fresh data in background if cache is expired or empty
            if cacheManager.isLotsExpired() || cachedLots.isEmpty {
                await loadLots()
            }
        }
    }

    @MainActor
    private func loadLots() async {
        isLoading = lots.isEmpty // Only show loading if we have no data
        errorMessage = nil
        do {
            let freshLots = try await BookAPI.fetchAllLots()
            lots = freshLots
            cacheManager.saveLots(freshLots)
            isLoading = false
        } catch {
            isLoading = false
            // Only show error if we have no cached data to display
            if lots.isEmpty {
                errorMessage = "Failed to load lots: \(error.localizedDescription)"
            }
        }
    }
}

private extension LotSuggestionDTO {
    static var placeholder: LotSuggestionDTO {
        LotSuggestionDTO(
            lotID: nil,
            name: "Sample Lot",
            strategy: "placeholder.strategy",
            bookIsbns: Array(repeating: "0000000000", count: 3),
            estimatedValue: 0,
            probabilityScore: 0,
            probabilityLabel: "",
            sellThrough: nil,
            justification: nil,
            displayAuthorLabel: "",
            canonicalAuthor: nil,
            canonicalSeries: nil,
            seriesName: nil,
            books: nil,
            marketJson: nil
        )
    }
}

private struct LotSummaryRow: View {
    let lot: LotSuggestionDTO

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(lot.name)
                .bodyStyle().fontWeight(.semibold)
            if let authorLabel = lot.displayAuthorLabel, !authorLabel.isEmpty {
                Text(authorLabel)
                    .subtitleStyle()
            }
            HStack(spacing: 12) {
                Text("Books: \(lot.bookIsbns.count)")
                    .font(.caption)
                    .foregroundStyle(DS.Color.textSecondary)
                Text("Value: \(lot.estimatedValue.formatted(.currency(code: "USD")))")
                    .font(.caption)
                    .foregroundStyle(DS.Color.textSecondary)
                if !lot.probabilityLabel.isEmpty {
                    Text(lot.probabilityLabel)
                        .font(.caption)
                        .foregroundStyle(DS.Color.textSecondary)
                }
            }
        }
        .padding(.vertical, DS.Spacing.sm)
        .contentShape(Rectangle())
    }
}

private struct LotDetailView: View {
    let lot: LotSuggestionDTO

    var body: some View {
        List {
            Section("Overview") {
                Text(lot.name)
                    .bodyStyle().fontWeight(.semibold)
                if let strategy = lot.strategy.split(separator: ".").last {
                    Text("Strategy: \(strategy)")
                        .subtitleStyle()
                } else {
                    Text("Strategy: \(lot.strategy)")
                        .subtitleStyle()
                }
                Text("Estimated value: \(lot.estimatedValue.formatted(.currency(code: "USD")))")
                if let sellThrough = lot.sellThrough {
                    Text("Sell-through: \(sellThrough, format: .percent)")
                }
                Text("Probability: \(lot.probabilityLabel)")
                if let canonical = lot.canonicalAuthor {
                    Text("Canonical author: \(canonical)")
                }
                if let series = lot.seriesName, !series.isEmpty {
                    Text("Series: \(series)")
                }
            }

            if let justification = lot.justification, !justification.isEmpty {
                Section("Justification") {
                    ForEach(justification, id: \.self) { reason in
                        Text(reason)
                    }
                }
            }

            if let books = lot.books, !books.isEmpty {
                Section("Books in Lot") {
                    ForEach(books, id: \.isbn) { book in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(book.metadata?.title ?? book.isbn)
                                .bodyStyle().fontWeight(.semibold)
                                .lineLimit(2)
                            if let author = book.metadata?.primaryAuthor {
                                Text(author)
                                    .font(.caption)
                                    .foregroundStyle(DS.Color.textSecondary)
                            }
                            HStack(spacing: 8) {
                                if let price = book.estimatedPrice {
                                    Text(price, format: .currency(code: "USD"))
                                        .font(.caption)
                                        .foregroundStyle(DS.Color.textSecondary)
                                }
                                if let probability = book.probabilityLabel {
                                    Text(probability)
                                        .font(.caption)
                                        .foregroundStyle(DS.Color.textSecondary)
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(DS.Color.background)
        .navigationTitle(lot.name)
    }
}

#Preview {
    NavigationStack {
        LotDetailView(
            lot: LotSuggestionDTO(
                lotID: 1,
                name: "Sample Fantasy Bundle",
                strategy: "author.series",
                bookIsbns: ["9780670855032", "9780670855049"],
                estimatedValue: 42.5,
                probabilityScore: 0.78,
                probabilityLabel: "High",
                sellThrough: 0.65,
                justification: ["Matching author branding", "Includes reader favorites"],
                displayAuthorLabel: "Robin Hobb collection",
                canonicalAuthor: "Robin Hobb",
                canonicalSeries: "Realm of the Elderlings",
                seriesName: "Liveship Traders",
                books: [
                    BookEvaluationRecord(
                        isbn: "9780670855032",
                        originalIsbn: "9780670855032",
                        condition: "Good",
                        edition: nil,
                        quantity: 1,
                        estimatedPrice: 18.0,
                        probabilityScore: 0.82,
                        probabilityLabel: "High",
                        justification: ["First edition", "Recent sales trending upward"],
                        metadata: BookMetadataDetails(
                            title: "Ship of Magic",
                            subtitle: "(Liveship Traders #1)",
                            authors: ["Robin Hobb"],
                            creditedAuthors: nil,
                            canonicalAuthor: "Robin Hobb",
                            publisher: "Spectra",
                            publishedYear: 1998,
                            description: nil,
                            thumbnail: "https://covers.openlibrary.org/b/isbn/9780670855032-M.jpg",
                            categories: ["Fantasy"],
                            seriesName: "Liveship Traders",
                            seriesIndex: 1
                        ),
                        market: nil,
                        booksrunValueLabel: nil,
                        booksrunValueRatio: nil,
                        bookscouter: nil,
                        bookscouterValueLabel: nil,
                        bookscouterValueRatio: nil,
                        rarity: nil
                    )
                ],
                marketJson: nil
            )
        )
    }
}
