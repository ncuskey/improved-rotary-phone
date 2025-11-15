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
    @State private var searchText = ""
    @State private var selectedStrategies: Set<LotStrategy> = Set(LotStrategy.allCases)
    @State private var sortOption: SortOption = .value
    @State private var showingFilterPopover = false
    private var cacheManager: CacheManager { CacheManager(modelContext: modelContext) }

    enum SortOption: String, CaseIterable, Identifiable {
        case name = "Name (A-Z)"
        case author = "Author (A-Z)"
        case value = "Value (High-Low)"
        case valuePerBook = "Value/Book (High-Low)"
        case probability = "Probability (High-Low)"
        case books = "Books (Most-Least)"
        case completion = "Completion % (High-Low)"

        var id: String { rawValue }
    }

    enum LotStrategy: String, CaseIterable, Identifiable {
        case author = "Author"
        case seriesComplete = "Series (Complete)"
        case seriesIncomplete = "Series (Incomplete)"
        case value = "Value Bundle"

        var id: String { rawValue }

        func matches(_ strategy: String) -> Bool {
            switch self {
            case .author:
                return strategy.contains("author")
            case .seriesComplete:
                return strategy.contains("series_complete")
            case .seriesIncomplete:
                return strategy.contains("series_incomplete")
            case .value:
                return strategy.contains("value")
            }
        }
    }

    var filteredLots: [LotSuggestionDTO] {
        var result = lots

        // Apply search filter
        if !searchText.isEmpty {
            result = result.filter { lot in
                let name = lot.name.lowercased()
                let author = lot.canonicalAuthor?.lowercased() ?? ""
                let displayAuthor = lot.displayAuthorLabel?.lowercased() ?? ""
                let series = lot.seriesName?.lowercased() ?? ""
                let canonicalSeries = lot.canonicalSeries?.lowercased() ?? ""
                let searchLower = searchText.lowercased()

                return name.contains(searchLower) ||
                       author.contains(searchLower) ||
                       displayAuthor.contains(searchLower) ||
                       series.contains(searchLower) ||
                       canonicalSeries.contains(searchLower)
            }
        }

        // Apply strategy filter
        let filtered = result.filter { lot in
            // A lot should be shown if ANY of the selected strategies matches it
            let isMatched = selectedStrategies.contains { strategy in
                strategy.matches(lot.strategy)
            }

            // Debug individual lot
            if !isMatched {
                print("❌ Filtered out: '\(lot.name)' (strategy: '\(lot.strategy)')")
            }

            return isMatched
        }

        // Apply sorting
        let sorted: [LotSuggestionDTO]
        switch sortOption {
        case .name:
            sorted = filtered.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        case .author:
            sorted = filtered.sorted { lot1, lot2 in
                let author1 = lot1.displayAuthorLabel ?? lot1.canonicalAuthor ?? ""
                let author2 = lot2.displayAuthorLabel ?? lot2.canonicalAuthor ?? ""
                return author1.localizedCaseInsensitiveCompare(author2) == .orderedAscending
            }
        case .value:
            sorted = filtered.sorted { $0.estimatedValue > $1.estimatedValue }
        case .valuePerBook:
            sorted = filtered.sorted { lot1, lot2 in
                let perBook1 = lot1.bookIsbns.isEmpty ? 0 : lot1.estimatedValue / Double(lot1.bookIsbns.count)
                let perBook2 = lot2.bookIsbns.isEmpty ? 0 : lot2.estimatedValue / Double(lot2.bookIsbns.count)
                return perBook1 > perBook2
            }
        case .probability:
            sorted = filtered.sorted { $0.probabilityScore > $1.probabilityScore }
        case .books:
            sorted = filtered.sorted { $0.bookIsbns.count > $1.bookIsbns.count }
        case .completion:
            sorted = filtered.sorted { lot1, lot2 in
                let completion1 = extractCompletionPercentage(from: lot1)
                let completion2 = extractCompletionPercentage(from: lot2)
                return completion1 > completion2
            }
        }

        // Debug logging
        print("\n📊 LOTS FILTERING DEBUG")
        print("📊 Total lots loaded: \(lots.count)")
        print("📊 Selected filter strategies: \(selectedStrategies.map { $0.rawValue })")
        print("📊 Filtered result count: \(filtered.count)")
        print("📊 Sort option: \(sortOption.rawValue)")

        // Log strategy distribution
        let strategyCounts = lots.reduce(into: [String: Int]()) { counts, lot in
            counts[lot.strategy, default: 0] += 1
        }
        print("\n📊 Strategy distribution in data:")
        for (strategy, count) in strategyCounts.sorted(by: { $0.key < $1.key }) {
            let matchingFilter = selectedStrategies.first { $0.matches(strategy) }
            let isFiltered = matchingFilter != nil
            print("   - '\(strategy)': \(count) lots \(isFiltered ? "✅ SHOWN (matches \(matchingFilter!.rawValue))" : "❌ HIDDEN (no match)")")
        }
        print("")

        return sorted
    }

    /// Extract completion percentage from a series lot name
    /// Format: "Series Name (X/Y Books)" -> returns (X/Y * 100)
    /// Returns 0 for non-series lots
    private func extractCompletionPercentage(from lot: LotSuggestionDTO) -> Double {
        // Only relevant for series lots
        guard lot.strategy.contains("series") else { return 0 }

        // Parse from name format: "Series Name (X/Y Books)"
        let name = lot.name
        guard let openParen = name.lastIndex(of: "("),
              let closeParen = name.lastIndex(of: ")") else {
            return 0
        }

        let content = name[name.index(after: openParen)..<closeParen]
        let parts = content.split(separator: "/")

        guard parts.count == 2,
              let currentStr = parts[0].split(separator: " ").first,
              let totalStr = parts[1].split(separator: " ").first,
              let current = Double(currentStr),
              let total = Double(totalStr),
              total > 0 else {
            return 0
        }

        return (current / total) * 100.0
    }

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    List(Array(0..<5).map { index in
                        LotSuggestionDTO.placeholder(id: index)
                    }, id: \.id) { lot in
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
                    List(filteredLots) { lot in
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
                    .navigationDestination(for: BookEvaluationRecord.self) { record in
                        BookDetailView(record: record)
                    }
                    .searchable(text: $searchText, placement: .navigationBarDrawer(displayMode: .always), prompt: "Search by name, author, or series")
                }
            }
            .navigationTitle("Lots")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    HStack(spacing: 8) {
                        // Recalculate button
                        Button {
                            Task { await recalculateLots() }
                        } label: {
                            Label("Recalculate", systemImage: "arrow.triangle.2.circlepath")
                        }
                        .disabled(isLoading)

                        // Sort menu
                        Menu {
                            ForEach(SortOption.allCases) { option in
                                Button {
                                    sortOption = option
                                } label: {
                                    Label(
                                        option.rawValue,
                                        systemImage: sortOption == option ? "checkmark.circle.fill" : "circle"
                                    )
                                }
                            }
                        } label: {
                            Label("Sort", systemImage: "arrow.up.arrow.down.circle")
                        }

                        // Filter button with popover
                        Button {
                            showingFilterPopover = true
                        } label: {
                            Label("Filter", systemImage: "line.3.horizontal.decrease.circle")
                        }
                        .popover(isPresented: $showingFilterPopover) {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Filter Lots")
                                    .font(.headline)
                                    .padding(.bottom, 4)

                                ForEach(LotStrategy.allCases) { strategy in
                                    Button {
                                        toggleStrategy(strategy)
                                    } label: {
                                        HStack {
                                            Image(systemName: selectedStrategies.contains(strategy) ? "checkmark.circle.fill" : "circle")
                                                .foregroundStyle(selectedStrategies.contains(strategy) ? .blue : .gray)
                                            Text(strategy.rawValue)
                                                .foregroundStyle(DS.Color.textPrimary)
                                            Spacer()
                                        }
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                            .padding()
                            .frame(minWidth: 220)
                            .presentationCompactAdaptation(.popover)
                        }
                    }
                }
            }
            .task { await initialLoadIfNeeded() }
        }
        .background(DS.Color.background)
    }

    private func toggleStrategy(_ strategy: LotStrategy) {
        if selectedStrategies.contains(strategy) {
            selectedStrategies.remove(strategy)
        } else {
            selectedStrategies.insert(strategy)
        }
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
            // Fetch existing lots (fast - no recalculation)
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

    @MainActor
    private func recalculateLots() async {
        print("🔄 Starting lot recalculation...")
        isLoading = true
        errorMessage = nil
        let startTime = Date()

        do {
            print("📡 Requesting lot recalculation from server...")
            // Trigger full lot recalculation (slow - includes eBay searches)
            let freshLots = try await BookAPI.regenerateLots()

            let duration = Date().timeIntervalSince(startTime)
            print("✅ Recalculation complete! Received \(freshLots.count) lots in \(String(format: "%.1f", duration))s")

            // Count lots with lot pricing
            let lotsWithPricing = freshLots.filter { $0.useLotPricing == true }.count
            if lotsWithPricing > 0 {
                print("💰 \(lotsWithPricing) lots have eBay lot comp pricing")
            } else {
                print("ℹ️ No lots found with eBay lot comp pricing (series may not have active lot markets)")
            }

            lots = freshLots
            cacheManager.saveLots(freshLots)
            isLoading = false
        } catch {
            let duration = Date().timeIntervalSince(startTime)
            print("❌ Recalculation failed after \(String(format: "%.1f", duration))s: \(error.localizedDescription)")
            isLoading = false
            errorMessage = "Failed to recalculate lots: \(error.localizedDescription)"
        }
    }
}

private extension LotSuggestionDTO {
    static func placeholder(id: Int) -> LotSuggestionDTO {
        LotSuggestionDTO(
            lotID: -id - 1,  // Negative IDs for placeholders
            name: "Sample Lot \(id)",
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
            marketJson: nil,
            lotMarketValue: nil,
            lotOptimalSize: nil,
            lotPerBookPrice: nil,
            lotCompsCount: nil,
            useLotPricing: nil,
            individualValue: nil
        )
    }
}

private struct LotSummaryRow: View {
    let lot: LotSuggestionDTO

    var strategyBadge: (String, Color) {
        let strategy = lot.strategy
        if strategy.contains("series_complete") {
            return ("Complete", .green)
        } else if strategy.contains("series_incomplete") {
            return ("Incomplete", .orange)
        } else if strategy.contains("author") {
            return ("Author", .purple)
        } else if strategy.contains("value") {
            return ("Value", .gray)
        } else {
            return ("Other", .gray)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(lot.name)
                    .bodyStyle().fontWeight(.semibold)
                    .lineLimit(2)

                Spacer()

                Text(strategyBadge.0)
                    .font(.caption2)
                    .fontWeight(.semibold)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(strategyBadge.1.opacity(0.2))
                    .foregroundStyle(strategyBadge.1)
                    .clipShape(Capsule())
            }

            if let authorLabel = lot.displayAuthorLabel, !authorLabel.isEmpty {
                Text(authorLabel)
                    .subtitleStyle()
            }

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
        .padding(.vertical, DS.Spacing.sm)
        .contentShape(Rectangle())
    }
}

struct LotDetailView: View {
    let lot: LotSuggestionDTO

    struct SeriesInfo {
        let completionText: String
        let haveIndices: [Int]
        let missingIndices: [Int]
    }

    var seriesInfo: SeriesInfo? {
        guard let justification = lot.justification,
              lot.strategy.contains("series") else {
            return nil
        }

        var completionText = ""
        var haveIndices: [Int] = []
        var missingIndices: [Int] = []

        for line in justification {
            if line.starts(with: "Have ") && line.contains("of") && line.contains("books") {
                completionText = line
            } else if line.starts(with: "Have: ") {
                let indices = line.replacingOccurrences(of: "Have: ", with: "")
                haveIndices = parseIndices(indices)
            } else if line.starts(with: "Missing: ") {
                let indices = line.replacingOccurrences(of: "Missing: ", with: "")
                missingIndices = parseIndices(indices)
            }
        }

        if !completionText.isEmpty {
            return SeriesInfo(
                completionText: completionText,
                haveIndices: haveIndices,
                missingIndices: missingIndices
            )
        }
        return nil
    }

    func parseIndices(_ text: String) -> [Int] {
        var indices: [Int] = []
        if text.contains("books") { return [] }

        let parts = text.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
        for part in parts {
            if part.contains("-") {
                let range = part.split(separator: "-")
                if range.count == 2,
                   let start = Int(range[0].replacingOccurrences(of: "#", with: "")),
                   let end = Int(range[1].replacingOccurrences(of: "#", with: "")) {
                    indices.append(contentsOf: start...end)
                }
            } else {
                if let num = Int(part.replacingOccurrences(of: "#", with: "")) {
                    indices.append(num)
                }
            }
        }
        return indices.sorted()
    }

    var body: some View {
        List {
            Section("Overview") {
                Text(lot.name)
                    .bodyStyle().fontWeight(.semibold)

                HStack {
                    Text("Strategy").foregroundStyle(DS.Color.textSecondary)
                    Spacer()
                    if lot.strategy.contains("series_complete") {
                        Text("Series (Complete)").fontWeight(.medium).foregroundStyle(.green)
                    } else if lot.strategy.contains("series_incomplete") {
                        Text("Series (Incomplete)").fontWeight(.medium).foregroundStyle(.orange)
                    } else if lot.strategy.contains("author") {
                        Text("Author").fontWeight(.medium).foregroundStyle(.purple)
                    } else if lot.strategy.contains("value") {
                        Text("Value Bundle").fontWeight(.medium).foregroundStyle(.gray)
                    } else {
                        Text(lot.strategy)
                    }
                }

                HStack {
                    Text("Estimated value").foregroundStyle(DS.Color.textSecondary)
                    Spacer()
                    Text(lot.estimatedValue.formatted(.currency(code: "USD"))).fontWeight(.medium).foregroundStyle(.green)
                }

                if let sellThrough = lot.sellThrough {
                    HStack {
                        Text("Sell-through").foregroundStyle(DS.Color.textSecondary)
                        Spacer()
                        Text(sellThrough, format: .percent).fontWeight(.medium)
                    }
                }

                HStack {
                    Text("Probability").foregroundStyle(DS.Color.textSecondary)
                    Spacer()
                    Text(lot.probabilityLabel).fontWeight(.medium).foregroundStyle(
                        lot.probabilityLabel == "High" ? .green : lot.probabilityLabel == "Medium" ? .orange : .red
                    )
                }

                if let canonical = lot.canonicalAuthor {
                    HStack {
                        Text("Author").foregroundStyle(DS.Color.textSecondary)
                        Spacer()
                        Text(canonical).fontWeight(.medium)
                    }
                }

                if let series = lot.seriesName, !series.isEmpty {
                    HStack {
                        Text("Series").foregroundStyle(DS.Color.textSecondary)
                        Spacer()
                        Text(series).fontWeight(.medium)
                    }
                }
            }

            // Lot Market Pricing Section - shown when lot comp data is available
            if lot.useLotPricing == true,
               let lotMarketValue = lot.lotMarketValue,
               let lotCompsCount = lot.lotCompsCount,
               lotCompsCount > 0 {
                Section {
                    VStack(alignment: .leading, spacing: 12) {
                        // Market-based pricing indicator
                        HStack {
                            Image(systemName: "chart.line.uptrend.xyaxis")
                                .foregroundStyle(.blue)
                            Text("Lot comp pricing")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .foregroundStyle(.blue)
                            Spacer()
                            Text("\(lotCompsCount) eBay comps")
                                .font(.caption)
                                .foregroundStyle(DS.Color.textSecondary)
                        }

                        Divider()

                        // Pricing display
                        VStack(spacing: 8) {
                            HStack {
                                Text("Lot market value")
                                    .foregroundStyle(DS.Color.textPrimary)
                                Spacer()
                                Text(lotMarketValue.formatted(.currency(code: "USD")))
                                    .fontWeight(.semibold)
                                    .foregroundStyle(.green)
                            }

                            if let perBookPrice = lot.lotPerBookPrice {
                                HStack {
                                    Text("Per-book price")
                                        .foregroundStyle(DS.Color.textSecondary)
                                    Spacer()
                                    Text(perBookPrice.formatted(.currency(code: "USD")))
                                        .font(.caption)
                                        .foregroundStyle(DS.Color.textSecondary)
                                }
                            }

                            // Show individual pricing comparison if available
                            if let individualValue = lot.individualValue {
                                Divider()
                                    .padding(.vertical, 4)

                                HStack {
                                    Text("Individual pricing")
                                        .foregroundStyle(DS.Color.textSecondary)
                                        .font(.caption)
                                    Spacer()
                                    Text(individualValue.formatted(.currency(code: "USD")))
                                        .font(.caption)
                                        .foregroundStyle(DS.Color.textSecondary)
                                }

                                // Pricing insight
                                let priceDiff = lotMarketValue - individualValue
                                let percentDiff = abs(priceDiff / individualValue) * 100

                                HStack(spacing: 6) {
                                    Image(systemName: priceDiff > 0 ? "arrow.up.circle.fill" : "arrow.down.circle.fill")
                                        .font(.caption)
                                        .foregroundStyle(priceDiff > 0 ? .green : .orange)
                                    Text(priceDiff > 0 ?
                                        "+\(abs(priceDiff).formatted(.currency(code: "USD"))) (\(percentDiff, specifier: "%.1f")%) vs individual sales" :
                                        "\(abs(priceDiff).formatted(.currency(code: "USD"))) (\(percentDiff, specifier: "%.1f")%) vs individual sales")
                                        .font(.caption2)
                                        .fontWeight(.medium)
                                        .foregroundStyle(priceDiff > 0 ? .green : .orange)
                                }
                                .padding(.vertical, 4)
                                .padding(.horizontal, 8)
                                .background(
                                    RoundedRectangle(cornerRadius: 4)
                                        .fill(priceDiff > 0 ? Color.green.opacity(0.1) : Color.orange.opacity(0.1))
                                )
                            }
                        }

                        Text("Using lot comps as more direct comparable")
                            .font(.caption2)
                            .foregroundStyle(DS.Color.textSecondary)
                            .italic()
                    }
                    .padding(.vertical, 8)
                } header: {
                    Text("Lot Market Pricing")
                }
            }

            // Optimal Lot Size Recommendation - shown when available
            if let optimalSize = lot.lotOptimalSize,
               optimalSize != lot.bookIsbns.count {
                Section {
                    HStack(spacing: 10) {
                        Image(systemName: "lightbulb.fill")
                            .foregroundStyle(.yellow)
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Optimal lot size: \(optimalSize) books")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                            Text("You have \(lot.bookIsbns.count) books. Market data suggests \(optimalSize)-book lots perform best for this series.")
                                .font(.caption)
                                .foregroundStyle(DS.Color.textSecondary)
                        }
                    }
                    .padding(.vertical, 6)
                } header: {
                    Text("Recommendation")
                }
            }

            if let seriesInfo = seriesInfo {
                Section {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(seriesInfo.completionText).font(.subheadline).fontWeight(.semibold)

                        if !seriesInfo.haveIndices.isEmpty {
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                                    Text("Books You Have").font(.caption).fontWeight(.semibold).foregroundStyle(.green)
                                }
                                Text(formatIndices(seriesInfo.haveIndices)).font(.caption).foregroundStyle(DS.Color.textSecondary)
                            }
                        }

                        if !seriesInfo.missingIndices.isEmpty {
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Image(systemName: "circle").foregroundStyle(.orange)
                                    Text("Books Still Needed").font(.caption).fontWeight(.semibold).foregroundStyle(.orange)
                                }
                                Text(formatIndices(seriesInfo.missingIndices)).font(.caption).foregroundStyle(DS.Color.textSecondary)
                            }
                        }
                    }
                    .padding(.vertical, 8)
                } header: {
                    Text("Series Completion")
                }
            }

            if let justification = lot.justification, !justification.isEmpty {
                Section("Justification") {
                    ForEach(justification.filter { line in
                        if seriesInfo != nil {
                            return !line.starts(with: "Have ") && !line.starts(with: "Missing: ")
                        }
                        return true
                    }, id: \.self) { reason in
                        Text(reason).font(.subheadline)
                    }
                }
            }

            if let books = lot.books, !books.isEmpty {
                Section("Books in Lot (\(books.count))") {
                    ForEach(books, id: \.isbn) { book in
                        NavigationLink(value: book) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(book.metadata?.title ?? book.isbn).bodyStyle().fontWeight(.semibold).lineLimit(2)
                                if let author = book.metadata?.primaryAuthor {
                                    Text(author).font(.caption).foregroundStyle(DS.Color.textSecondary)
                                }
                                if let seriesName = book.metadata?.seriesName, let seriesIndex = book.metadata?.seriesIndex {
                                    HStack(spacing: 4) {
                                        Image(systemName: "books.vertical.fill").font(.caption2)
                                        Text("\(seriesName) #\(seriesIndex)")
                                    }
                                    .font(.caption).foregroundStyle(.blue)
                                }
                                HStack(spacing: 8) {
                                    if let price = book.estimatedPrice {
                                        Text(price, format: .currency(code: "USD")).font(.caption).foregroundStyle(.green).fontWeight(.medium)
                                    }
                                    if let probability = book.probabilityLabel {
                                        Text(probability).font(.caption).fontWeight(.medium).foregroundStyle(
                                            probability == "High" ? .green : probability == "Medium" ? .orange : .red
                                        )
                                    }
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(DS.Color.background)
        .navigationTitle(lot.name)
        .navigationBarTitleDisplayMode(.inline)
    }

    func formatIndices(_ indices: [Int]) -> String {
        if indices.isEmpty { return "None" }
        var ranges: [(Int, Int)] = []
        var start = indices[0], end = indices[0]

        for i in 1..<indices.count {
            if indices[i] == end + 1 {
                end = indices[i]
            } else {
                ranges.append((start, end))
                start = indices[i]; end = indices[i]
            }
        }
        ranges.append((start, end))

        let formatted = ranges.map { range in
            if range.0 == range.1 { return "#\(range.0)" }
            else if range.1 == range.0 + 1 { return "#\(range.0), #\(range.1)" }
            else { return "#\(range.0)-#\(range.1)" }
        }
        return formatted.joined(separator: ", ")
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
                        estimatedSalePrice: 18.0,
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
                            thumbnail: "https://covers.openlibrary.org/b/isbn/9780670855032-L.jpg",
                            categories: ["Fantasy"],
                            seriesName: "Liveship Traders",
                            seriesIndex: 1
                        ),
                        market: nil,
                        booksrun: nil,
                        booksrunValueLabel: nil,
                        booksrunValueRatio: nil,
                        bookscouter: nil,
                        bookscouterValueLabel: nil,
                        bookscouterValueRatio: nil,
                        rarity: nil,
                        updatedAt: "2025-01-15T00:00:00Z",
                        createdAt: "2025-01-14T00:00:00Z",
                        timeToSellDays: nil,
                        routingInfo: nil,
                        channelRecommendation: nil
                    )
                ],
                marketJson: nil,
                lotMarketValue: 55.0,
                lotOptimalSize: 3,
                lotPerBookPrice: 18.33,
                lotCompsCount: 8,
                useLotPricing: true,
                individualValue: 60.0
            )
        )
    }
}
