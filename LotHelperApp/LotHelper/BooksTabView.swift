import SwiftUI
import SwiftData

struct BooksTabView: View {
    @Environment(\.modelContext) private var modelContext
    @State private var books: [BookEvaluationRecord] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var searchText = ""
    @State private var sortOption: SortOption = .recencyDescending
    private var cacheManager: CacheManager { CacheManager(modelContext: modelContext) }

    enum SortOption: String, CaseIterable, Identifiable {
        case recencyDescending = "Newest First"
        case recencyAscending = "Oldest First"
        case titleAscending = "Title (A-Z)"
        case titleDescending = "Title (Z-A)"
        case profitDescending = "Highest Profit"
        case profitAscending = "Lowest Profit"
        case priceDescending = "Highest Price"
        case priceAscending = "Lowest Price"

        var id: String { rawValue }
    }

    var filteredAndSortedBooks: [BookEvaluationRecord] {
        var result = books

        // Apply search filter
        if !searchText.isEmpty {
            result = result.filter { book in
                let title = book.metadata?.title?.lowercased() ?? ""
                let author = book.metadata?.primaryAuthor?.lowercased() ?? ""
                let isbn = book.isbn.lowercased()
                let series = book.metadata?.seriesName?.lowercased() ?? ""
                let searchLower = searchText.lowercased()

                return title.contains(searchLower) ||
                       author.contains(searchLower) ||
                       isbn.contains(searchLower) ||
                       series.contains(searchLower)
            }
        }

        let originalOrder = Dictionary(uniqueKeysWithValues: result.enumerated().map { ($1.id, $0) })

        // Apply sorting
        result.sort { book1, book2 in
            let index1 = originalOrder[book1.id] ?? 0
            let index2 = originalOrder[book2.id] ?? 0
            switch sortOption {
            case .recencyDescending:
                let date1 = book1.recencyDate
                let date2 = book2.recencyDate
                if date1 != date2 { return date1 > date2 }
                return index1 < index2
            case .recencyAscending:
                let date1 = book1.recencyDate
                let date2 = book2.recencyDate
                if date1 != date2 { return date1 < date2 }
                return index1 < index2
            case .titleAscending:
                let title1 = book1.sortingTitle
                let title2 = book2.sortingTitle
                let comparison = title1.localizedCaseInsensitiveCompare(title2)
                if comparison != .orderedSame { return comparison == .orderedAscending }
                return index1 < index2
            case .titleDescending:
                let title1 = book1.sortingTitle
                let title2 = book2.sortingTitle
                let comparison = title1.localizedCaseInsensitiveCompare(title2)
                if comparison != .orderedSame { return comparison == .orderedDescending }
                return index1 < index2
            case .profitDescending:
                let profit1 = (book1.market?.soldCompsMedian ?? 0) - (book1.bookscouter?.bestPrice ?? 0)
                let profit2 = (book2.market?.soldCompsMedian ?? 0) - (book2.bookscouter?.bestPrice ?? 0)
                if profit1 != profit2 { return profit1 > profit2 }
                return index1 < index2
            case .profitAscending:
                let profit1 = (book1.market?.soldCompsMedian ?? 0) - (book1.bookscouter?.bestPrice ?? 0)
                let profit2 = (book2.market?.soldCompsMedian ?? 0) - (book2.bookscouter?.bestPrice ?? 0)
                if profit1 != profit2 { return profit1 < profit2 }
                return index1 < index2
            case .priceDescending:
                let price1 = book1.market?.soldCompsMedian ?? 0
                let price2 = book2.market?.soldCompsMedian ?? 0
                if price1 != price2 { return price1 > price2 }
                return index1 < index2
            case .priceAscending:
                let price1 = book1.market?.soldCompsMedian ?? 0
                let price2 = book2.market?.soldCompsMedian ?? 0
                if price1 != price2 { return price1 < price2 }
                return index1 < index2
            }
        }

        return result
    }

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    ScrollView {
                        LazyVStack(spacing: DS.Spacing.md) {
                            ForEach(0..<6, id: \.self) { _ in
                                BookCardView(book: .placeholder)
                                    .redacted(reason: .placeholder)
                            }
                        }
                        .padding(.vertical, DS.Spacing.md)
                        .padding(.horizontal, DS.Spacing.xl)
                    }
                    .scrollIndicators(.hidden)
                    .background(DS.Color.background)
                } else if let errorMessage {
                    EmptyStateView(
                        systemImage: "exclamationmark.triangle",
                        title: "Books Unavailable",
                        message: errorMessage,
                        actionTitle: "Try Again"
                    ) {
                        Task { await loadBooks() }
                    }
                } else if books.isEmpty {
                    EmptyStateView(
                        systemImage: "book.closed",
                        title: "No Books Yet",
                        message: "Import a catalog or run a scan to see books here.",
                        actionTitle: "Refresh"
                    ) {
                        Task { await loadBooks() }
                    }
                } else {
                    List {
                        ForEach(filteredAndSortedBooks) { book in
                            NavigationLink(value: book) {
                                BookCardView(book: book.cardModel)
                            }
                            .buttonStyle(.plain)
                            .listRowBackground(DS.Color.background)
                            .listRowInsets(EdgeInsets(top: DS.Spacing.md / 2, leading: DS.Spacing.xl, bottom: DS.Spacing.md / 2, trailing: DS.Spacing.xl))
                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                Button(role: .destructive) {
                                    Task {
                                        await deleteBook(book)
                                    }
                                } label: {
                                    Label("Delete", systemImage: "trash")
                                }
                            }
                        }
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                    .background(DS.Color.background)
                    .refreshable { await loadBooks() }
                    .navigationDestination(for: BookEvaluationRecord.self) { record in
                        BookDetailView(record: record)
                    }
                    .navigationDestination(for: LotSuggestionDTO.self) { lot in
                        LotDetailView(lot: lot)
                    }
                    .searchable(text: $searchText, placement: .navigationBarDrawer(displayMode: .always), prompt: "Search by title, author, ISBN, or series")
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: CacheManager.booksDidChange)) { _ in
                let cached = cacheManager.getCachedBooks()
                if !cached.isEmpty {
                    books = cached
                }
            }
            .navigationTitle("Books")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Menu {
                        Picker("Sort By", selection: $sortOption) {
                            ForEach(SortOption.allCases) { option in
                                Text(option.rawValue).tag(option)
                            }
                        }

                        Divider()

                        Button {
                            Task { await refreshAll() }
                        } label: {
                            Label("Refresh All Books", systemImage: "arrow.clockwise")
                        }
                    } label: {
                        Label("Sort", systemImage: "arrow.up.arrow.down")
                    }
                }
            }
            .task { await initialLoadIfNeeded() }
        }
        .background(DS.Color.background)
    }

    @MainActor
    private func initialLoadIfNeeded() async {
        if books.isEmpty && !isLoading {
            // Load from cache first
            let cachedBooks = cacheManager.getCachedBooks()
            if !cachedBooks.isEmpty {
                books = cachedBooks
            }

            // Fetch fresh data in background if cache is expired or empty
            if cacheManager.isBooksExpired() || cachedBooks.isEmpty {
                await loadBooks()
            }
        }
    }

    @MainActor
    private func loadBooks() async {
        isLoading = books.isEmpty // Only show loading if we have no data
        errorMessage = nil
        do {
            let freshBooks = try await BookAPI.fetchAllBooks()
            books = freshBooks
            cacheManager.saveBooks(freshBooks)
            isLoading = false
        } catch {
            isLoading = false
            // Only show error if we have no cached data to display
            if books.isEmpty {
                errorMessage = "Failed to load books: \(error.localizedDescription)"
            }
        }
    }

    @MainActor
    private func refreshAll() async {
        // Clear the cache first to force fresh data
        cacheManager.clearAllCaches()
        books = []

        // Reload all books from backend
        await loadBooks()
    }

    @MainActor
    private func deleteBook(_ book: BookEvaluationRecord) async {
        do {
            // Call API to delete book
            try await BookAPI.deleteBook(book.isbn)

            // Remove from local state
            books.removeAll { $0.id == book.id }

            // Update cache
            cacheManager.saveBooks(books)

            print("✅ Book deleted from local state: \(book.isbn)")
        } catch {
            print("❌ Failed to delete book: \(error.localizedDescription)")
            errorMessage = "Failed to delete book: \(error.localizedDescription)"
        }
    }
}

private extension BookEvaluationRecord {
    var cardModel: BookCardView.Book {
        let resolvedTitle = metadata?.title?.trimmedNonEmpty ?? metadata?.subtitle?.trimmedNonEmpty ?? isbn
        let resolvedAuthor = metadata?.primaryAuthor?.trimmedNonEmpty

        // Use series name from metadata if available, otherwise fall back to subtitle or categories
        let resolvedSeries: String? = {
            if let seriesName = metadata?.seriesName?.trimmedNonEmpty {
                // Include series index if available
                if let index = metadata?.seriesIndex {
                    return "\(seriesName) #\(index)"
                }
                return seriesName
            }
            return metadata?.subtitle?.trimmedNonEmpty ?? metadata?.categories?.first?.trimmedNonEmpty
        }()

        let resolvedScore = probabilityLabel?.trimmedNonEmpty

        let thumbnail = (metadata?.thumbnail?.trimmedNonEmpty ?? fallbackCoverURLString) ?? ""

        // Calculate profit potential based on eBay median price
        let profitPotential: String? = {
            guard let median = market?.soldCompsMedian else { return nil }
            if median < 5 { return "Low" }
            if median < 15 { return "Medium" }
            return "High"
        }()

        return BookCardView.Book(
            title: resolvedTitle,
            author: resolvedAuthor,
            series: resolvedSeries,
            thumbnail: thumbnail,
            score: resolvedScore,
            profitPotential: profitPotential,
            soldCompsMedian: market?.soldCompsMedian,
            bestVendorPrice: bookscouter?.bestPrice
        )
    }

    private var fallbackCoverURLString: String? {
        guard !isbn.isEmpty else { return nil }
        return "https://covers.openlibrary.org/b/isbn/\(isbn)-L.jpg"
    }

    var sortingTitle: String {
        metadata?.title ?? isbn
    }

    var recencyDate: Date {
        // Try SQL format first (most common: "2025-10-24 01:43:00")
        if let updatedAt,
           let date = BookEvaluationRecord.sqlFormatter.date(from: updatedAt) {
            return date
        }
        if let createdAt,
           let date = BookEvaluationRecord.sqlFormatter.date(from: createdAt) {
            return date
        }

        // Try ISO8601 with fractional seconds
        if let updatedAt,
           let date = BookEvaluationRecord.isoFormatterWithFractional.date(from: updatedAt) {
            return date
        }
        if let createdAt,
           let date = BookEvaluationRecord.isoFormatterWithFractional.date(from: createdAt) {
            return date
        }

        // Try ISO8601 without fractional seconds
        if let updatedAt,
           let date = BookEvaluationRecord.isoFormatter.date(from: updatedAt) {
            return date
        }
        if let createdAt,
           let date = BookEvaluationRecord.isoFormatter.date(from: createdAt) {
            return date
        }

        return .distantPast
    }

    // Formatter for "2025-10-24 01:43:00" format (space-separated, no timezone)
    private static let sqlFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter
    }()

    private static let isoFormatterWithFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}

struct BookDetailView: View {
    let record: BookEvaluationRecord
    @State private var lots: [LotSuggestionDTO] = []
    @State private var isLoadingLots = false

    var lotsContainingBook: [LotSuggestionDTO] {
        lots.filter { lot in
            lot.bookIsbns.contains(record.isbn)
        }
    }

    var body: some View {
        List {
            coverSection
            overviewSection
            lotsSection
            profitAnalysisSection
            ebayMarketSection
            bookscouterSection
            amazonSection
            metadataSection
            justificationSection
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(DS.Color.background)
        .navigationTitle(record.metadata?.title ?? record.isbn)
        .task { await loadLots() }
    }

    @ViewBuilder
    private var coverSection: some View {
        if let url = coverURL {
            Section {
                HStack {
                    Spacer()
                    AsyncImage(url: url) { image in
                        image
                            .resizable()
                            .scaledToFit()
                    } placeholder: {
                        ProgressView()
                    }
                    .frame(width: 160, height: 220)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    Spacer()
                }
            }
        }
    }

    @ViewBuilder
    private var lotsSection: some View {
        let containingLots = lotsContainingBook
        if !containingLots.isEmpty {
            Section("Included in Lots (\(containingLots.count))") {
                ForEach(containingLots) { lot in
                    NavigationLink(value: lot) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(lot.name)
                                .bodyStyle()
                                .fontWeight(.semibold)

                            HStack(spacing: 12) {
                                Label("\(lot.bookIsbns.count)", systemImage: "book.closed")
                                    .font(.caption)
                                    .foregroundStyle(DS.Color.textSecondary)

                                Text(lot.estimatedValue.formatted(.currency(code: "USD")))
                                    .font(.caption)
                                    .foregroundStyle(.green)
                                    .fontWeight(.medium)

                                if !lot.probabilityLabel.isEmpty {
                                    Text(lot.probabilityLabel)
                                        .font(.caption)
                                        .fontWeight(.medium)
                                        .foregroundStyle(
                                            lot.probabilityLabel == "High" ? .green :
                                            lot.probabilityLabel == "Medium" ? .orange :
                                            .red
                                        )
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        } else if isLoadingLots {
            Section("Included in Lots") {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
            }
        }
    }

    @ViewBuilder
    private var overviewSection: some View {
        Section("Overview") {
            Text("ISBN: \(record.isbn)")
                .bodyStyle()
            if let quantity = record.quantity {
                Text("Quantity: \(quantity)")
                    .bodyStyle()
            }
            if let condition = record.condition, !condition.isEmpty {
                Text("Condition: \(condition)")
                    .bodyStyle()
            }
            if let price = record.estimatedPrice {
                Text("Estimated price: \(formattedCurrency(price))")
                    .bodyStyle()
            }
            if let probability = record.probabilityLabel, !probability.isEmpty {
                Text("Probability: \(probability)")
                    .bodyStyle()
            }
        }
    }

    @ViewBuilder
    private var profitAnalysisSection: some View {
        if let market = record.market,
           let soldMedian = market.soldCompsMedian,
           let vendorPrice = record.bookscouter?.bestPrice {
            Section("Profit Analysis") {
                HStack {
                    Text("eBay Sold Price (Median)")
                        .bodyStyle()
                    Spacer()
                    Text(formattedCurrency(soldMedian))
                        .bodyStyle()
                        .fontWeight(.semibold)
                }

                HStack {
                    Text("Best Vendor Buyback")
                        .bodyStyle()
                    Spacer()
                    Text(formattedCurrency(vendorPrice))
                        .bodyStyle()
                        .fontWeight(.semibold)
                        .foregroundStyle(.green)
                }

                let margin = soldMedian - vendorPrice
                let percentage = (margin / vendorPrice) * 100

                Divider()

                HStack {
                    Text("Profit Margin")
                        .bodyStyle()
                        .fontWeight(.semibold)
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(formattedCurrency(margin))
                            .bodyStyle()
                            .fontWeight(.bold)
                            .foregroundStyle(margin > 0 ? .green : .red)
                        Text("(\(String(format: "%.0f", percentage))%)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                if margin > 0 {
                    let potential: String = {
                        if soldMedian < 5 { return "Low" }
                        if soldMedian < 15 { return "Medium" }
                        return "High"
                    }()

                    HStack {
                        Text("Profit Potential")
                            .bodyStyle()
                        Spacer()
                        Text(potential)
                            .bodyStyle()
                            .fontWeight(.semibold)
                            .foregroundStyle(potential == "High" ? .green : potential == "Medium" ? .orange : .red)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var ebayMarketSection: some View {
        if let market = record.market {
            Section("eBay Market Data") {
                if let activeCount = market.activeCount {
                    HStack {
                        Text("Active Listings")
                            .bodyStyle()
                        Spacer()
                        Text("\(activeCount)")
                            .bodyStyle()
                            .fontWeight(.semibold)
                    }
                }

                if let soldCount = market.soldCount {
                    HStack {
                        Text("Sold Listings")
                            .bodyStyle()
                        Spacer()
                        Text("\(soldCount)")
                            .bodyStyle()
                            .fontWeight(.semibold)
                    }
                }

                if let sellThrough = market.sellThroughRate {
                    HStack {
                        Text("Sell Through Rate")
                            .bodyStyle()
                        Spacer()
                        Text("\(String(format: "%.1f", sellThrough * 100))%")
                            .bodyStyle()
                            .fontWeight(.semibold)
                            .foregroundStyle(sellThrough > 0.5 ? .green : .orange)
                    }
                }

                if let soldMedian = market.soldCompsMedian {
                    Divider()

                    HStack {
                        Text("Sold Price (Median)")
                            .bodyStyle()
                        Spacer()
                        Text(formattedCurrency(soldMedian))
                            .bodyStyle()
                            .fontWeight(.semibold)
                    }

                    if let soldMin = market.soldCompsMin {
                        HStack {
                            Text("Sold Price (Min)")
                                .bodyStyle()
                            Spacer()
                            Text(formattedCurrency(soldMin))
                                .bodyStyle()
                        }
                    }

                    if let soldMax = market.soldCompsMax {
                        HStack {
                            Text("Sold Price (Max)")
                                .bodyStyle()
                            Spacer()
                            Text(formattedCurrency(soldMax))
                                .bodyStyle()
                        }
                    }

                    if let isEstimate = market.soldCompsIsEstimate, isEstimate {
                        Text("Note: Sold prices are estimated from active listings")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var bookscouterSection: some View {
        if let bookscouter = record.bookscouter, bookscouter.totalVendors > 0 {
            Section("BookScouter Buyback Offers") {
                HStack {
                    Text("Best Offer")
                        .bodyStyle()
                    Spacer()
                    Text(formattedCurrency(bookscouter.bestPrice))
                        .bodyStyle()
                        .fontWeight(.semibold)
                        .foregroundStyle(.green)
                }

                if let vendor = bookscouter.bestVendor {
                    Text("from \(vendor)")
                        .font(.caption)
                        .foregroundStyle(DS.Color.textSecondary)
                }

                HStack {
                    Text("Total Vendors")
                        .bodyStyle()
                    Spacer()
                    Text("\(bookscouter.totalVendors)")
                        .bodyStyle()
                }

                if !bookscouter.topOffers.isEmpty {
                    VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                        Text("Top Offers")
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundStyle(DS.Color.textSecondary)

                        ForEach(bookscouter.topOffers, id: \.vendorId) { offer in
                            HStack {
                                Text(offer.vendorName)
                                    .font(.caption)
                                Spacer()
                                Text(formattedCurrency(offer.price))
                                    .font(.caption)
                                    .fontWeight(.medium)
                                    .foregroundStyle(.green)
                            }
                        }
                    }
                    .padding(.top, DS.Spacing.sm)
                }
            }
        }
    }

    @ViewBuilder
    private var amazonSection: some View {
        if let bookscouter = record.bookscouter,
           (bookscouter.amazonSalesRank != nil || bookscouter.amazonCount != nil || bookscouter.amazonLowestPrice != nil || bookscouter.amazonTradeInPrice != nil) {
            Section("Amazon Market Data") {
                if let rank = bookscouter.amazonSalesRank {
                    HStack {
                        Text("Sales Rank")
                            .bodyStyle()
                        Spacer()
                        Text("#\(rank.formatted())")
                            .bodyStyle()
                            .fontWeight(.semibold)
                    }
                    Text("Lower rank = higher demand")
                        .font(.caption)
                        .foregroundStyle(DS.Color.textSecondary)
                }

                if let count = bookscouter.amazonCount {
                    HStack {
                        Text("Sellers")
                            .bodyStyle()
                        Spacer()
                        Text("\(count)")
                            .bodyStyle()
                            .fontWeight(.semibold)
                    }
                }

                if let price = bookscouter.amazonLowestPrice {
                    HStack {
                        Text("Lowest Amazon Price")
                            .bodyStyle()
                        Spacer()
                        Text(formattedCurrency(price))
                            .bodyStyle()
                            .fontWeight(.semibold)
                            .foregroundStyle(.blue)
                    }
                }

                if let tradeIn = bookscouter.amazonTradeInPrice, tradeIn > 0 {
                    HStack {
                        Text("Amazon Trade-In")
                            .bodyStyle()
                        Spacer()
                        Text(formattedCurrency(tradeIn))
                            .bodyStyle()
                            .fontWeight(.semibold)
                            .foregroundStyle(.orange)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var metadataSection: some View {
        if let metadata = record.metadata {
            Section("Metadata") {
                if let title = metadata.title, !title.isEmpty {
                    Text(title)
                        .bodyStyle().fontWeight(.semibold)
                }
                if let subtitle = metadata.subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .subtitleStyle()
                }
                if let author = metadata.primaryAuthor {
                    Text("Author: \(author)")
                        .bodyStyle()
                }
                if let seriesName = metadata.seriesName, !seriesName.isEmpty {
                    HStack {
                        Image(systemName: "books.vertical.fill")
                            .foregroundStyle(DS.Color.textSecondary)
                        if let index = metadata.seriesIndex {
                            Text("Series: \(seriesName) #\(index)")
                                .bodyStyle()
                        } else {
                            Text("Series: \(seriesName)")
                                .bodyStyle()
                        }
                    }
                }
                if let publisher = metadata.publisher, !publisher.isEmpty {
                    Text("Publisher: \(publisher)")
                        .bodyStyle()
                }
                if let year = metadata.publishedYear {
                    Text("Published: \(year)")
                        .bodyStyle()
                }
                if let categories = metadata.categories, !categories.isEmpty {
                    Text("Categories: \(categories.joined(separator: ", "))")
                        .bodyStyle()
                }
                if let description = metadata.description, !description.isEmpty {
                    Text(description)
                        .font(.footnote)
                        .foregroundStyle(DS.Color.textSecondary)
                }
            }
        }
    }

    @ViewBuilder
    private var justificationSection: some View {
        if let reasons = record.justification, !reasons.isEmpty {
            Section("Justification") {
                ForEach(reasons, id: \.self) { reason in
                    Text(reason)
                        .bodyStyle()
                }
            }
        }
    }

    private var coverURL: URL? {
        if let thumbnail = record.metadata?.thumbnail, !thumbnail.isEmpty, let url = URL(string: thumbnail) {
            return url
        }
        if !record.isbn.isEmpty {
            return URL(string: "https://covers.openlibrary.org/b/isbn/\(record.isbn)-L.jpg")
        }
        return nil
    }

    private func formattedCurrency(_ value: Double) -> String {
        value.formatted(.currency(code: "USD"))
    }

    @MainActor
    private func loadLots() async {
        isLoadingLots = true
        do {
            lots = try await BookAPI.fetchAllLots()
        } catch {
            print("Failed to load lots: \(error.localizedDescription)")
            lots = []
        }
        isLoadingLots = false
    }
}

#Preview {
    NavigationStack {
        BookDetailView(
            record: BookEvaluationRecord(
                isbn: "9780670855032",
                originalIsbn: "9780670855032",
                condition: "Good",
                edition: nil,
                quantity: 2,
                estimatedPrice: 18.5,
                probabilityScore: 0.82,
                probabilityLabel: "High",
                justification: ["Strong demand in recent sales", "Complete series"],
                metadata: BookMetadataDetails(
                    title: "Ship of Magic",
                    subtitle: "A Journey into Testing",
                    authors: ["Robin Hobb"],
                    creditedAuthors: nil,
                    canonicalAuthor: "Robin Hobb",
                    publisher: "Sample Publisher",
                    publishedYear: 2018,
                    description: "This is a sample description used for SwiftUI previews.",
                    thumbnail: "https://covers.openlibrary.org/b/isbn/9780670855032-L.jpg",
                    categories: ["Fiction", "Adventure"],
                    seriesName: "Liveship Traders",
                    seriesIndex: 1
                ),
                market: EbayMarketData(
                    activeCount: 25,
                    soldCount: 18,
                    sellThroughRate: 0.72,
                    currency: "USD",
                    soldCompsCount: 12,
                    soldCompsMin: 15.99,
                    soldCompsMedian: 24.99,
                    soldCompsMax: 35.50,
                    soldCompsIsEstimate: false,
                    soldCompsSource: "marketplace_insights",
                    soldCompsLastSoldDate: "2025-01-10T00:00:00Z"
                ),
                booksrun: BooksRunOffer(
                    condition: "good",
                    cashPrice: 7.25,
                    storeCredit: 8.00,
                    currency: "USD",
                    url: "https://www.booksrun.com",
                    updatedAt: "2025-01-14"
                ),
                booksrunValueLabel: nil,
                booksrunValueRatio: nil,
                bookscouter: BookScouterResult(
                    isbn10: "0670855032",
                    isbn13: "9780670855032",
                    offers: [
                        VendorOffer(vendorName: "TextbookAgent", vendorId: "70", price: 8.50, updatedAt: "2025-01-15"),
                        VendorOffer(vendorName: "BooksRun", vendorId: "809", price: 7.44, updatedAt: "2025-01-15"),
                        VendorOffer(vendorName: "World of Books", vendorId: "836", price: 6.25, updatedAt: "2025-01-15")
                    ],
                    bestPrice: 8.50,
                    bestVendor: "TextbookAgent",
                    totalVendors: 3,
                    amazonSalesRank: 15432,
                    amazonCount: 69,
                    amazonLowestPrice: 18.99,
                    amazonTradeInPrice: 3.50
                ),
                bookscouterValueLabel: "High",
                bookscouterValueRatio: 0.93,
                rarity: nil,
                updatedAt: "2025-01-15T12:00:00Z",
                createdAt: "2025-01-10T12:00:00Z"
            )
        )
    }
}
