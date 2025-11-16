import SwiftUI

// MARK: - Redesigned Book Detail View
// This follows the same design philosophy as ScannerReviewView with card-based panels

struct BookDetailViewRedesigned: View {
    let record: BookEvaluationRecord
    @State private var lots: [LotSuggestionDTO] = []
    @State private var isLoadingLots = false
    @State private var showingEbayWizard = false
    @State private var priceVariants: PriceVariantsResponse?
    @State private var isLoadingVariants = false
    @State private var showVariantsExpanded = false
    @State private var soldStatistics: SoldStatistics?
    @State private var isLoadingSoldStats = false
    @Environment(\.dismiss) private var dismiss

    // Interactive attributes state
    // Initialize with record's condition, fallback to "Good" if not available
    @State private var selectedCondition: String
    @State private var isHardcover: Bool = false
    @State private var isPaperback: Bool = false
    @State private var isMassMarket: Bool = false
    @State private var isSigned: Bool = false
    @State private var isFirstEdition: Bool = false

    // Custom initializer to set selectedCondition and attributes from record
    init(record: BookEvaluationRecord, lots: [LotSuggestionDTO] = []) {
        self.record = record
        _lots = State(initialValue: lots)

        // Initialize selectedCondition with record's condition or default to "Good"
        let condition = record.condition ?? "Good"
        print("💰 Initializing BookDetailView for ISBN: \(record.isbn)")
        print("💰 Condition: \(condition), estimatedPrice: \(record.estimatedPrice ?? 0)")
        print("💰 Has metadata: \(record.metadata != nil)")
        _selectedCondition = State(initialValue: condition)

        // Initialize book attributes from saved metadata
        if let metadata = record.metadata {
            print("📋 Raw metadata attributes:")
            print("  - coverType: \(String(describing: metadata.coverType))")
            print("  - signed: \(String(describing: metadata.signed))")
            print("  - firstEdition: \(String(describing: metadata.firstEdition))")
            print("  - printing: \(String(describing: metadata.printing))")

            // Set format based on cover_type
            if let coverType = metadata.coverType {
                let coverLower = coverType.lowercased()
                if coverLower.contains("hardcover") || coverLower.contains("hardback") {
                    print("✅ Setting isHardcover = true")
                    _isHardcover = State(initialValue: true)
                } else if coverLower.contains("mass market") {
                    print("✅ Setting isMassMarket = true")
                    _isMassMarket = State(initialValue: true)
                } else if coverLower.contains("paperback") {
                    print("✅ Setting isPaperback = true")
                    _isPaperback = State(initialValue: true)
                }
            }

            // Set signed status
            if let signed = metadata.signed {
                print("✅ Setting isSigned = \(signed)")
                _isSigned = State(initialValue: signed)
            }

            // Set first edition status
            if let firstEdition = metadata.firstEdition {
                print("✅ Setting isFirstEdition = \(firstEdition)")
                _isFirstEdition = State(initialValue: firstEdition)
            }
        } else {
            print("⚠️ No metadata found in record")
        }
    }
    @State private var dynamicEstimate: Double? = nil
    @State private var attributeDeltas: [AttributeDelta] = []
    @State private var isUpdatingPrice: Bool = false
    @State private var dynamicProfitScenarios: [ProfitScenario]? = nil
    @State private var priceLower: Double? = nil
    @State private var priceUpper: Double? = nil
    @State private var confidencePercent: Double? = nil

    // Dynamic routing info (fetched from API if missing)
    @State private var dynamicRoutingInfo: MLRoutingInfo? = nil
    @State private var dynamicChannelRecommendation: ChannelRecommendation? = nil
    @State private var isLoadingRoutingInfo = false

    var lotsContainingBook: [LotSuggestionDTO] {
        lots.filter { lot in
            lot.bookIsbns.contains(record.isbn)
        }
    }

    // Use dynamic routing info if available, otherwise from record
    var effectiveRoutingInfo: MLRoutingInfo? {
        dynamicRoutingInfo ?? record.routingInfo
    }

    var effectiveChannelRecommendation: ChannelRecommendation? {
        dynamicChannelRecommendation ?? record.channelRecommendation
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Hero section with cover and title
                heroSection

                // PRIORITY 1: Price comparison panel (MOVED UP)
                priceComparisonPanel

                // PRIORITY 2: Profit analysis (MOVED UP - if available)
                if shouldShowProfitAnalysis {
                    profitAnalysisPanel
                }

                // Value Enhancement Checks (NEW)
                if let checks = record.checksNeeded, !checks.isEmpty {
                    valueEnhancementPanel
                }

                // List to eBay button
                ebayListingButton

                // ML Model Routing Info (NEW)
                if let routing = effectiveRoutingInfo {
                    RoutingInfoDetailView(routing: routing)
                } else if isLoadingRoutingInfo {
                    ProgressView("Loading ML insights...")
                        .padding()
                }

                // Channel Recommendation (NEW)
                if let recommendation = effectiveChannelRecommendation {
                    ChannelRecommendationDetailView(recommendation: recommendation)
                }

                // Price variants panel (condition and feature adjustments)
                if let variants = priceVariants {
                    priceVariantsPanel(variants)
                } else if isLoadingVariants {
                    loadingVariantsPanel
                }

                // Interactive attributes panel
                AttributesView(
                    condition: $selectedCondition,
                    isHardcover: $isHardcover,
                    isPaperback: $isPaperback,
                    isMassMarket: $isMassMarket,
                    isSigned: $isSigned,
                    isFirstEdition: $isFirstEdition,
                    priceEstimate: dynamicEstimate ?? record.estimatedPrice ?? 0.0,
                    priceLower: priceLower,
                    priceUpper: priceUpper,
                    confidencePercent: confidencePercent,
                    deltas: attributeDeltas,
                    onAttributeChanged: {
                        Task {
                            await updatePriceEstimate()
                            await saveAttributes()
                        }
                    }
                )

                // Market data
                if record.market != nil {
                    marketDataPanel
                }

                // Sold listings statistics
                if let stats = soldStatistics {
                    soldListingsPanel(stats)
                }

                // Buyback offers
                if let bookscouter = record.bookscouter, bookscouter.totalVendors > 0 {
                    buybackOffersPanel(bookscouter)
                }

                // Amazon data
                if shouldShowAmazonData {
                    amazonDataPanel
                }

                // Lots
                if !lotsContainingBook.isEmpty {
                    lotsPanel
                }

                // Book info
                bookInfoPanel

                // Justification
                if let reasons = record.justification, !reasons.isEmpty {
                    justificationPanel(reasons)
                }
            }
            .padding()
        }
        .background(DS.Color.background)
        .navigationTitle(record.metadata?.title ?? "Book Details")
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadLots() }
        .task { await loadPriceVariants() }
        .task { await loadSoldStatistics() }
        .task { await fetchRoutingInfoIfNeeded() }
        // Don't automatically update price estimate on load - only when user changes attributes
        // This preserves the original estimate from the record
        .sheet(isPresented: $showingEbayWizard) {
            let book = CachedBook(from: record)
            EbayListingWizardView(book: book) { response in
                print("✓ Listing created: \(response.title)")
            }
        }
    }

    // MARK: - Hero Section
    @ViewBuilder
    private var heroSection: some View {
        VStack(spacing: 12) {
            // Book cover
            if let url = coverURL {
                AsyncImage(url: url) { image in
                    image
                        .resizable()
                        .interpolation(.high)
                        .scaledToFit()
                } placeholder: {
                    ProgressView()
                }
                .frame(width: 140, height: 200)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .shadow(color: .black.opacity(0.2), radius: 8, x: 0, y: 4)
            }

            // Title and author
            VStack(spacing: 4) {
                if let title = record.metadata?.title {
                    Text(title)
                        .font(.title3)
                        .fontWeight(.bold)
                        .multilineTextAlignment(.center)
                }

                if let author = record.metadata?.primaryAuthor {
                    Text(author)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                // Only show series if it's different from the title (prevents bug where title = series)
                if let series = record.metadata?.seriesName,
                   let title = record.metadata?.title,
                   series.lowercased() != title.lowercased() {
                    HStack(spacing: 4) {
                        Image(systemName: "books.vertical.fill")
                            .font(.caption)
                        if let index = record.metadata?.seriesIndex {
                            Text("\(series) #\(index)")
                                .font(.caption)
                        } else {
                            Text(series)
                                .font(.caption)
                        }
                    }
                    .foregroundStyle(.purple)
                }
            }

            // Quick stats
            HStack(spacing: 20) {
                if let tts = ttsCategory(from: record.timeToSellDays) {
                    statBadge(tts.uppercased(), color: ttsColor(for: tts))
                }
                if let condition = record.condition {
                    statBadge(condition, color: .blue)
                }
                if let rarity = record.rarity, rarity > 0 {
                    statBadge(rarityLabel(for: rarity), color: rarityColor(for: rarity))
                }
                if let quantity = record.quantity, quantity > 1 {
                    statBadge("Qty: \(quantity)", color: .orange)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
    }

    // MARK: - eBay Listing Button
    @ViewBuilder
    private var ebayListingButton: some View {
        Button {
            showingEbayWizard = true
        } label: {
            HStack {
                Image(systemName: "tag.fill")
                    .font(.headline)
                Text("List to eBay")
                    .font(.headline)
                    .fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(
                LinearGradient(
                    colors: [.blue, .blue.opacity(0.8)],
                    startPoint: .leading,
                    endPoint: .trailing
                )
            )
            .foregroundColor(.white)
            .cornerRadius(12)
            .shadow(color: .blue.opacity(0.3), radius: 8, x: 0, y: 4)
        }
        .padding(.horizontal)
    }

    // MARK: - Price Comparison Panel
    @ViewBuilder
    private var priceComparisonPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "dollarsign.circle.fill")
                    .foregroundStyle(.blue)
                Text("Pricing")
                    .font(.headline)
            }

            // Price list sorted by price (highest to lowest)
            VStack(spacing: 8) {
                ForEach(sortedPrices, id: \.label) { priceItem in
                    priceListRow(priceItem)
                }
            }

            // ISBN
            HStack {
                Text("ISBN")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text(record.isbn)
                    .font(.caption)
                    .fontWeight(.medium)
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

    private struct PriceItem {
        let label: String
        let price: Double?
        let icon: String
        let color: Color
        let valueLabel: String?  // Optional value assessment (e.g., "Good Value", "Fair")
    }

    private var sortedPrices: [PriceItem] {
        let items = [
            PriceItem(
                label: "eBay Median",
                price: record.market?.soldCompsMedian,
                icon: "bag.fill",
                color: .primary,
                valueLabel: nil
            ),
            PriceItem(
                label: "Vendor Best",
                price: record.bookscouter?.bestPrice,
                icon: "arrow.2.circlepath",
                color: .green,
                valueLabel: record.bookscouterValueLabel
            ),
            PriceItem(
                label: "Amazon Low",
                price: record.bookscouter?.amazonLowestPrice,
                icon: "cart.fill",
                color: .orange,
                valueLabel: nil
            ),
            PriceItem(
                label: "Estimated",
                price: dynamicEstimate ?? record.estimatedPrice,  // Use dynamic estimate if available
                icon: "chart.bar.fill",
                color: .blue,
                valueLabel: nil
            )
        ]

        // Sort by price descending, nil values at the end
        return items.sorted { a, b in
            switch (a.price, b.price) {
            case (nil, nil): return false
            case (nil, _): return false
            case (_, nil): return true
            case (let priceA?, let priceB?): return priceA > priceB
            }
        }
    }

    @ViewBuilder
    private func priceListRow(_ item: PriceItem) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 12) {
                Image(systemName: item.icon)
                    .font(.body)
                    .foregroundStyle(item.color)
                    .frame(width: 24)

                VStack(alignment: .leading, spacing: 2) {
                    Text(item.label)
                        .font(.subheadline)
                        .foregroundStyle(.primary)

                    // Show value label badge if available
                    if let valueLabel = item.valueLabel {
                        Text(valueLabel)
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(valueLabelColor(for: valueLabel))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(valueLabelColor(for: valueLabel).opacity(0.15))
                            .cornerRadius(4)
                    }
                }

                Spacer()

                if let price = item.price {
                    Text(formattedCurrency(price))
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(item.color)
                } else {
                    Text("N/A")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            // Show prediction range for Estimated price if available
            if item.label == "Estimated", let lower = priceLower, let upper = priceUpper, let confidence = confidencePercent {
                HStack(spacing: 4) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                    Text("\(String(format: "%.0f%%", confidence)) range:")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("\(formattedCurrency(lower)) – \(formattedCurrency(upper))")
                        .font(.caption2)
                        .fontWeight(.medium)
                        .foregroundStyle(.orange)
                }
                .padding(.leading, 36)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(item.color.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Profit Analysis Panel
    private var shouldShowProfitAnalysis: Bool {
        // Show if we have dynamic profit scenarios OR old static data
        if dynamicProfitScenarios != nil && !dynamicProfitScenarios!.isEmpty {
            return true
        }

        guard let market = record.market,
              market.soldCompsMedian != nil,
              let bookscouter = record.bookscouter,
              bookscouter.bestPrice > 0 else {
            return false
        }
        return true
    }

    @ViewBuilder
    private var profitAnalysisPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .foregroundStyle(.green)
                Text("Multi-Scenario Profit Analysis")
                    .font(.headline)
            }

            // Use dynamic profit scenarios if available
            if let scenarios = dynamicProfitScenarios, !scenarios.isEmpty {
                ForEach(scenarios) { scenario in
                    dynamicProfitScenarioCard(scenario: scenario)
                }

                // Show best scenario indicator
                if let bestScenario = scenarios.max(by: { $0.marginPercent < $1.marginPercent }) {
                    Divider()
                    HStack(spacing: 4) {
                        Image(systemName: "lightbulb.fill")
                            .font(.caption)
                            .foregroundStyle(.yellow)
                        Text("Best margin: \(bestScenario.name) (\(String(format: "%.0f%%", bestScenario.marginPercent)))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            } else if let soldMedian = record.market?.soldCompsMedian {
                // Fallback to static calculations if no dynamic data
                // Best Case: Vendor acquisition
                if let vendorPrice = record.bookscouter?.bestPrice, vendorPrice > 0 {
                    profitScenarioCard(
                        title: "Best Case (Vendor)",
                        salePrice: soldMedian,
                        cost: vendorPrice,
                        badge: "Optimal",
                        badgeColor: .green
                    )
                }

                // Alternative: Amazon acquisition
                if let amazonPrice = record.bookscouter?.amazonLowestPrice, amazonPrice > 0 {
                    profitScenarioCard(
                        title: "Amazon Sourcing",
                        salePrice: soldMedian,
                        cost: amazonPrice,
                        badge: "Alternative",
                        badgeColor: .orange
                    )
                }

                // NOTE: estimatedPrice is ML-predicted SALE price, not acquisition cost
                // It should be compared to soldMedian, not used as a cost for profit calc

                // Summary comparison
                if let vendorPrice = record.bookscouter?.bestPrice,
                   let amazonPrice = record.bookscouter?.amazonLowestPrice,
                   vendorPrice > 0, amazonPrice > 0 {
                    Divider()
                    HStack(spacing: 4) {
                        Image(systemName: "lightbulb.fill")
                            .font(.caption)
                            .foregroundStyle(.yellow)
                        Text("Best margin: \(bestScenarioName(soldMedian: soldMedian))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

    // MARK: - Value Enhancement Panel
    @ViewBuilder
    private var valueEnhancementPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "sparkles")
                    .foregroundStyle(.orange)
                Text("Value Enhancement Opportunities")
                    .font(.headline)

                Spacer()

                if let totalPotential = record.potentialValueUplift, totalPotential > 0 {
                    Text("+\(formattedCurrency(totalPotential))")
                        .font(.headline)
                        .foregroundStyle(.green)
                }
            }

            if let checks = record.checksNeeded {
                ForEach(checks, id: \.attribute) { check in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(check.icon)
                                .font(.title3)
                            Text(check.attribute)
                                .font(.subheadline)
                                .fontWeight(.semibold)
                            Spacer()
                            Text("+\(formattedCurrency(check.potentialValue))")
                                .font(.subheadline)
                                .fontWeight(.bold)
                                .foregroundStyle(.green)
                        }

                        Text(check.prompt)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.vertical, 4)

                    if check.attribute != checks.last?.attribute {
                        Divider()
                    }
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

    // MARK: - Market Data Panel
    @ViewBuilder
    private var marketDataPanel: some View {
        if let market = record.market {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: "chart.bar.xaxis")
                        .foregroundStyle(.orange)
                    Text("eBay Market Data")
                        .font(.headline)
                    Spacer()
                    if let source = market.soldCompsSource {
                        Text(source == "marketplace_insights" ? "Real" : "Est")
                            .font(.caption2)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(
                                RoundedRectangle(cornerRadius: 10)
                                    .fill((source == "marketplace_insights" ? Color.green : Color.orange).opacity(0.2))
                            )
                    }
                }

                // Metrics
                HStack(spacing: 12) {
                    if let active = market.activeCount {
                        metricChip("Active", "\(active)", color: .blue)
                    }
                    if let sold = market.soldCount {
                        metricChip("Sold", "\(sold)", color: .green)
                    }
                    if let rate = market.sellThroughRate {
                        metricChip("Rate", "\(Int(rate * 100))%", color: rate > 0.5 ? .green : .orange)
                    }
                }

                // Price range
                if market.soldCompsMin != nil || market.soldCompsMax != nil {
                    Divider()
                    VStack(spacing: 6) {
                        if let min = market.soldCompsMin {
                            HStack {
                                Text("Min Price")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Text(formattedCurrency(min))
                                    .font(.caption)
                                    .fontWeight(.medium)
                            }
                        }
                        if let max = market.soldCompsMax {
                            HStack {
                                Text("Max Price")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Text(formattedCurrency(max))
                                    .font(.caption)
                                    .fontWeight(.medium)
                            }
                        }
                    }
                }
            }
            .padding()
            .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
            .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
        }
    }

    // MARK: - Sold Listings Panel
    @ViewBuilder
    private func soldListingsPanel(_ stats: SoldStatistics) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.blue)
                Text("Sold Listings Analysis")
                    .font(.headline)
                Spacer()
                if stats.hasSufficientData {
                    Text(stats.dataQuality.qualityLabel)
                        .font(.caption2)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(Color.green.opacity(0.2))
                        )
                }
            }

            // Demand Signal
            if let demand = stats.demandSignal {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Market Demand")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(stats.demandLabel)
                            .font(.title3)
                            .fontWeight(.semibold)
                            .foregroundStyle(demandColor(for: stats.demandLabel))
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 4) {
                        Text("Signal Score")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(String(format: "%.0f", demand))
                            .font(.title3)
                            .fontWeight(.semibold)
                    }
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 12)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(demandColor(for: stats.demandLabel).opacity(0.1))
                )
            }

            // Platform Breakdown
            if stats.platformBreakdown.sortedPlatforms.first(where: { $0.percentage > 0 }) != nil {
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    Text("Platform Distribution")
                        .font(.subheadline)
                        .fontWeight(.medium)

                    ForEach(stats.platformBreakdown.sortedPlatforms, id: \.name) { platform in
                        if platform.percentage > 0 {
                            HStack(spacing: 8) {
                                Text(platform.name)
                                    .font(.caption)
                                    .frame(width: 60, alignment: .leading)

                                GeometryReader { geometry in
                                    ZStack(alignment: .leading) {
                                        Rectangle()
                                            .fill(Color.gray.opacity(0.2))
                                            .frame(height: 8)
                                            .cornerRadius(4)

                                        Rectangle()
                                            .fill(platformColor(for: platform.name))
                                            .frame(width: geometry.size.width * (platform.percentage / 100), height: 8)
                                            .cornerRadius(4)
                                    }
                                }
                                .frame(height: 8)

                                Text(String(format: "%.0f%%", platform.percentage))
                                    .font(.caption)
                                    .fontWeight(.medium)
                                    .frame(width: 40, alignment: .trailing)
                            }
                        }
                    }
                }
            }

            // Price & Features
            if let avgPrice = stats.features.avgPrice, let range = stats.features.priceRange {
                Divider()
                HStack(spacing: 16) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Avg Price")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(formattedCurrency(avgPrice))
                            .font(.caption)
                            .fontWeight(.medium)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Range")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(formattedCurrency(range))
                            .font(.caption)
                            .fontWeight(.medium)
                    }
                    if let signedPct = stats.features.signedPct, signedPct > 0 {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Signed")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(String(format: "%.0f%%", signedPct * 100))
                                .font(.caption)
                                .fontWeight(.medium)
                                .foregroundStyle(.orange)
                        }
                    }
                }
            }

            // Data Quality
            HStack(spacing: 12) {
                metricChip("Total", "\(stats.dataQuality.totalCount)", color: .blue)
                if stats.dataQuality.singleSalesCount > 0 {
                    metricChip("Single", "\(stats.dataQuality.singleSalesCount)", color: .green)
                }
                if stats.dataQuality.lotSalesCount > 0 {
                    metricChip("Lots", "\(stats.dataQuality.lotSalesCount)", color: .orange)
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }

    // MARK: - Buyback Offers Panel
    @ViewBuilder
    private func buybackOffersPanel(_ bookscouter: BookScouterResult) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "arrow.2.circlepath.circle.fill")
                    .foregroundStyle(.green)
                Text("Buyback Offers")
                    .font(.headline)
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(formattedCurrency(bookscouter.bestPrice))
                        .font(.title3)
                        .bold()
                        .foregroundStyle(.green)
                    if let vendor = bookscouter.bestVendor {
                        Text(vendor)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if !bookscouter.topOffers.isEmpty {
                Divider()
                VStack(spacing: 8) {
                    ForEach(bookscouter.topOffers.prefix(5), id: \.vendorId) { offer in
                        HStack {
                            Text(offer.vendorName)
                                .font(.caption)
                                .lineLimit(1)
                            Spacer()
                            Text(formattedCurrency(offer.price))
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundStyle(.green)
                        }
                    }
                }
            } else {
                Text("\(bookscouter.totalVendors) vendor(s) - Best offer: \(formattedCurrency(bookscouter.bestPrice))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }

    // MARK: - Amazon Data Panel
    private var shouldShowAmazonData: Bool {
        guard let bookscouter = record.bookscouter else { return false }
        return bookscouter.amazonSalesRank != nil ||
               bookscouter.amazonCount != nil ||
               bookscouter.amazonLowestPrice != nil ||
               bookscouter.amazonTradeInPrice != nil
    }

    @ViewBuilder
    private var amazonDataPanel: some View {
        if let bookscouter = record.bookscouter {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: "cart.fill")
                        .foregroundStyle(.orange)
                    Text("Amazon Data")
                        .font(.headline)
                }

                VStack(spacing: 8) {
                    if let rank = bookscouter.amazonSalesRank {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Sales Rank")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text("Lower = more popular")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                            Spacer()
                            Text("#\(rank.formatted())")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                        }
                    }

                    if let count = bookscouter.amazonCount {
                        Divider()
                        HStack {
                            Text("Sellers")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text("\(count)")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                        }
                    }

                    if let tradeIn = bookscouter.amazonTradeInPrice, tradeIn > 0 {
                        Divider()
                        HStack {
                            Text("Trade-In Value")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(formattedCurrency(tradeIn))
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .foregroundStyle(.orange)
                        }
                    }
                }
            }
            .padding()
            .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
            .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
        }
    }

    // MARK: - Lots Panel
    @ViewBuilder
    private var lotsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "shippingbox.fill")
                    .foregroundStyle(.purple)
                Text("Included in Lots")
                    .font(.headline)
                Spacer()
                Text("\(lotsContainingBook.count)")
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.purple.opacity(0.2), in: RoundedRectangle(cornerRadius: 8))
            }

            ForEach(lotsContainingBook) { lot in
                NavigationLink(value: lot) {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(lot.name)
                                .font(.subheadline)
                                .fontWeight(.semibold)
                            HStack(spacing: 8) {
                                Text("\(lot.bookIsbns.count) books")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text("•")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(lot.estimatedValue.formatted(.currency(code: "USD")))
                                    .font(.caption)
                                    .foregroundStyle(.green)
                            }
                        }
                        Spacer()
                        if !lot.probabilityLabel.isEmpty {
                            Text(lot.probabilityLabel)
                                .font(.caption2)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(
                                    probabilityColor(for: lot.probabilityLabel).opacity(0.2),
                                    in: RoundedRectangle(cornerRadius: 8)
                                )
                        }
                    }
                    .padding(12)
                    .background(Color.purple.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }

    // MARK: - Book Info Panel
    @ViewBuilder
    private var bookInfoPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "info.circle.fill")
                    .foregroundStyle(.blue)
                Text("Book Information")
                    .font(.headline)
            }

            VStack(spacing: 8) {
                if let publisher = record.metadata?.publisher, !publisher.isEmpty {
                    infoRow("Publisher", publisher)
                }
                if let year = record.metadata?.publishedYear {
                    infoRow("Published", "\(year)")
                }
                if let categories = record.metadata?.categories, !categories.isEmpty {
                    infoRow("Categories", categories.prefix(3).joined(separator: ", "))
                }
                if let description = record.metadata?.description, !description.isEmpty {
                    Divider()
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Description")
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundStyle(.secondary)
                        Text(description)
                            .font(.caption)
                            .foregroundStyle(.primary)
                            .lineLimit(6)
                    }
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }

    // MARK: - Justification Panel
    @ViewBuilder
    private func justificationPanel(_ reasons: [String]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "brain.head.profile")
                    .foregroundStyle(.blue)
                Text("ML Model Reasoning")
                    .font(.headline)
            }

            // Explanatory subtitle
            Text("Our machine learning model analyzed these factors to estimate this book's value:")
                .font(.caption)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(reasons.enumerated()), id: \.offset) { index, reason in
                    HStack(alignment: .top, spacing: 10) {
                        // Icon based on reason content
                        Image(systemName: reasonIcon(for: reason))
                            .font(.caption)
                            .foregroundStyle(reasonColor(for: reason))
                            .frame(width: 20)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(reason)
                                .font(.subheadline)
                                .fixedSize(horizontal: false, vertical: true)

                            // Add contextual explanation for certain factors
                            if let context = reasonContext(for: reason) {
                                Text(context)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .italic()
                            }
                        }
                    }

                    if index < reasons.count - 1 {
                        Divider()
                            .padding(.leading, 30)
                    }
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }

    // MARK: - Helper Components
    @ViewBuilder
    private func statBadge(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.caption)
            .fontWeight(.semibold)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(color.opacity(0.15), in: RoundedRectangle(cornerRadius: 12))
            .foregroundStyle(color)
    }

    @ViewBuilder
    private func metricChip(_ label: String, _ value: String, color: Color = .primary) -> some View {
        VStack(spacing: 4) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(color)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private func infoRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .leading)
            Text(value)
                .font(.caption)
                .fontWeight(.medium)
            Spacer()
        }
    }

    // MARK: - Helpers
    private var coverURL: URL? {
        // Priority 1: Upgrade thumbnail if available
        if let thumbnail = record.metadata?.thumbnail, !thumbnail.isEmpty {
            var urlString = thumbnail
            print("📷 Original thumbnail URL: \(thumbnail)")

            // Upgrade Google Books thumbnail quality
            if urlString.contains("books.google.com") {
                // Remove zoom parameter if present and add high-res version
                if let range = urlString.range(of: "&zoom=") {
                    urlString = String(urlString[..<range.lowerBound])
                }
                urlString += "&zoom=1"  // Larger images

                // Prefer higher resolution if edge/printsec parameters exist
                if !urlString.contains("&imgmax=") {
                    urlString += "&imgmax=800"  // Request 800px max dimension
                }
                print("📷 Upgraded Google Books URL: \(urlString)")
            }
            // Upgrade Amazon image quality
            else if urlString.contains("amazon.com/images") || urlString.contains("media-amazon.com/images") {
                // Replace _SL75_ (75px), _SX75_ (75px width), etc. with larger sizes
                // Amazon supports: _SL500_, _SX500_, etc.
                urlString = urlString.replacingOccurrences(of: "_SL75_", with: "_SL500_")
                urlString = urlString.replacingOccurrences(of: "_SX75_", with: "_SX500_")
                urlString = urlString.replacingOccurrences(of: "_SY75_", with: "_SY500_")
                urlString = urlString.replacingOccurrences(of: "_SL100_", with: "_SL500_")
                urlString = urlString.replacingOccurrences(of: "_SX100_", with: "_SX500_")
                urlString = urlString.replacingOccurrences(of: "_SY100_", with: "_SY500_")
                urlString = urlString.replacingOccurrences(of: "_SL150_", with: "_SL500_")
                urlString = urlString.replacingOccurrences(of: "_SX150_", with: "_SX500_")
                urlString = urlString.replacingOccurrences(of: "_SY150_", with: "_SY500_")
                urlString = urlString.replacingOccurrences(of: "_SL200_", with: "_SL500_")
                urlString = urlString.replacingOccurrences(of: "_SX200_", with: "_SX500_")
                urlString = urlString.replacingOccurrences(of: "_SY200_", with: "_SY500_")
                print("📷 Upgraded Amazon URL: \(urlString)")
            }

            if let url = URL(string: urlString) {
                return url
            }
        }

        // Priority 2: Open Library with highest quality
        if !record.isbn.isEmpty {
            // Try largest size (-L), which is typically 400px+
            let fallbackURL = "https://covers.openlibrary.org/b/isbn/\(record.isbn)-L.jpg"
            print("📷 Using Open Library fallback: \(fallbackURL)")
            return URL(string: fallbackURL)
        }

        return nil
    }

    private func formattedCurrency(_ value: Double) -> String {
        value.formatted(.currency(code: "USD"))
    }

    private func probabilityColor(for label: String) -> Color {
        switch label.lowercased() {
        case "high", "strong":
            return .green
        case "medium", "worth":
            return .orange
        case "low", "risky":
            return .red
        default:
            return .gray
        }
    }

    private func demandColor(for label: String) -> Color {
        switch label.lowercased() {
        case "very high":
            return .green
        case "high":
            return .blue
        case "moderate":
            return .orange
        case "low":
            return .red
        default:
            return .gray
        }
    }

    private func platformColor(for platform: String) -> Color {
        switch platform.lowercased() {
        case "ebay":
            return .blue
        case "amazon":
            return .orange
        case "mercari":
            return .purple
        default:
            return .gray
        }
    }

    private func ttsCategory(from days: Int?) -> String? {
        guard let days = days else { return nil }
        if days <= 30 {
            return "Fast"
        } else if days <= 90 {
            return "Medium"
        } else if days <= 180 {
            return "Slow"
        } else {
            return "Very Slow"
        }
    }

    private func ttsColor(for category: String) -> Color {
        switch category.lowercased() {
        case "fast":
            return .green
        case "medium":
            return .blue
        case "slow":
            return .orange
        case "very slow":
            return .red
        default:
            return .gray
        }
    }

    private func rarityLabel(for score: Double) -> String {
        if score >= 0.9 {
            return "RARE"
        } else if score >= 0.7 {
            return "UNCOMMON"
        } else if score >= 0.3 {
            return "COMMON"
        } else {
            return "ABUNDANT"
        }
    }

    private func rarityColor(for score: Double) -> Color {
        if score >= 0.9 {
            return .purple
        } else if score >= 0.7 {
            return .indigo
        } else if score >= 0.3 {
            return .gray
        } else {
            return .gray.opacity(0.6)
        }
    }

    private func valueLabelColor(for label: String) -> Color {
        let lowercased = label.lowercased()
        if lowercased.contains("good") || lowercased.contains("great") || lowercased.contains("excellent") {
            return .green
        } else if lowercased.contains("fair") || lowercased.contains("okay") || lowercased.contains("moderate") {
            return .orange
        } else if lowercased.contains("poor") || lowercased.contains("bad") || lowercased.contains("low") {
            return .red
        } else {
            return .gray
        }
    }

    // MARK: - ML Justification Helpers

    private func reasonIcon(for reason: String) -> String {
        let lowercased = reason.lowercased()
        if lowercased.contains("market") || lowercased.contains("demand") || lowercased.contains("sell") {
            return "chart.line.uptrend.xyaxis"
        } else if lowercased.contains("rarity") || lowercased.contains("rare") || lowercased.contains("uncommon") {
            return "star.fill"
        } else if lowercased.contains("author") || lowercased.contains("writer") {
            return "person.fill"
        } else if lowercased.contains("series") || lowercased.contains("collection") {
            return "books.vertical.fill"
        } else if lowercased.contains("condition") || lowercased.contains("quality") {
            return "sparkles"
        } else if lowercased.contains("price") || lowercased.contains("value") || lowercased.contains("cost") {
            return "dollarsign.circle.fill"
        } else if lowercased.contains("category") || lowercased.contains("genre") {
            return "tag.fill"
        } else if lowercased.contains("year") || lowercased.contains("published") || lowercased.contains("edition") {
            return "calendar"
        } else {
            return "checkmark.circle.fill"
        }
    }

    private func reasonColor(for reason: String) -> Color {
        let lowercased = reason.lowercased()
        if lowercased.contains("strong") || lowercased.contains("high") || lowercased.contains("excellent") {
            return .green
        } else if lowercased.contains("moderate") || lowercased.contains("average") || lowercased.contains("fair") {
            return .orange
        } else if lowercased.contains("weak") || lowercased.contains("low") || lowercased.contains("poor") {
            return .red
        } else {
            return .blue
        }
    }

    private func reasonContext(for reason: String) -> String? {
        let lowercased = reason.lowercased()

        if lowercased.contains("sell through") || lowercased.contains("sell-through") {
            return "This measures how quickly books sell relative to available inventory"
        } else if lowercased.contains("rarity score") {
            return "Higher rarity scores indicate fewer copies available in the market"
        } else if lowercased.contains("amazon sales rank") {
            return "Lower ranks indicate stronger sales performance on Amazon"
        } else if lowercased.contains("vendor offers") {
            return "Number of buyback vendors interested in purchasing this book"
        } else if lowercased.contains("signed listings") {
            return "Presence of signed copies can indicate collectible demand"
        } else if lowercased.contains("lot listings") {
            return "Books frequently sold in lots may have different pricing dynamics"
        }

        return nil
    }

    @ViewBuilder
    private func dynamicProfitScenarioCard(scenario: ProfitScenario) -> some View {
        let badgeColor: Color = {
            switch scenario.name {
            case "Best Case": return .green
            case "Amazon": return .orange
            case "ML Estimate": return .blue
            default: return .gray
            }
        }()

        VStack(alignment: .leading, spacing: 8) {
            // Header with badge
            HStack {
                Text(scenario.name)
                    .font(.subheadline)
                    .fontWeight(.medium)
                Spacer()
                Text(String(format: "%.0f%% margin", scenario.marginPercent))
                    .font(.caption2)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(badgeColor.opacity(0.2))
                    )
                    .foregroundStyle(badgeColor)
            }

            // Price breakdown
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Revenue")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(formattedCurrency(scenario.revenue))
                        .font(.caption)
                        .fontWeight(.semibold)
                }

                Image(systemName: "minus")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Fees")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(formattedCurrency(scenario.fees))
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(.orange)
                }

                Image(systemName: "minus")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Cost")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(formattedCurrency(scenario.cost))
                        .font(.caption)
                        .fontWeight(.semibold)
                }

                Image(systemName: "equal")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Profit")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(formattedCurrency(scenario.profit))
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundStyle(scenario.profit > 0 ? .green : .red)
                }
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(uiColor: .secondarySystemBackground))
        )
    }

    @ViewBuilder
    private func profitScenarioCard(
        title: String,
        salePrice: Double,
        cost: Double,
        badge: String,
        badgeColor: Color
    ) -> some View {
        let margin = salePrice - cost
        let marginPct = (margin / cost) * 100

        VStack(alignment: .leading, spacing: 8) {
            // Header with badge
            HStack {
                Text(title)
                    .font(.subheadline)
                    .fontWeight(.medium)
                Spacer()
                Text(badge)
                    .font(.caption2)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(badgeColor.opacity(0.2))
                    )
                    .foregroundStyle(badgeColor)
            }

            // Price breakdown
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Sale Price")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(formattedCurrency(salePrice))
                        .font(.caption)
                        .fontWeight(.semibold)
                }

                Image(systemName: "minus")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Cost")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(formattedCurrency(cost))
                        .font(.caption)
                        .fontWeight(.semibold)
                }

                Image(systemName: "equal")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Profit")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(formattedCurrency(margin))
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(margin > 0 ? .green : .red)
                }

                Spacer()

                // Margin percentage
                Text(String(format: "%.0f%%", marginPct))
                    .font(.title3)
                    .fontWeight(.bold)
                    .foregroundStyle(margin > 0 ? .green : .red)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(uiColor: .secondarySystemBackground))
        )
    }

    private func bestScenarioName(soldMedian: Double) -> String {
        var scenarios: [(name: String, margin: Double)] = []

        if let vendorPrice = record.bookscouter?.bestPrice, vendorPrice > 0 {
            scenarios.append(("Vendor", soldMedian - vendorPrice))
        }

        if let amazonPrice = record.bookscouter?.amazonLowestPrice, amazonPrice > 0 {
            scenarios.append(("Amazon", soldMedian - amazonPrice))
        }

        // NOTE: Removed ML Estimate - it's a sale price prediction, not acquisition cost

        return scenarios.max(by: { $0.margin < $1.margin })?.name ?? "Unknown"
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

    @MainActor
    private func loadPriceVariants() async {
        isLoadingVariants = true
        defer { isLoadingVariants = false }

        do {
            let condition = record.condition ?? "Good"
            priceVariants = try await BookAPI.fetchPriceVariants(record.isbn, condition: condition)
        } catch {
            print("Failed to load price variants: \(error.localizedDescription)")
            priceVariants = nil
        }
    }

    private func loadSoldStatistics() async {
        isLoadingSoldStats = true
        defer { isLoadingSoldStats = false }

        do {
            soldStatistics = try await BookAPI.fetchSoldStatistics(record.isbn)
        } catch {
            print("Failed to load sold statistics: \(error.localizedDescription)")
            soldStatistics = nil
        }
    }

    // Fetch routing info from API if not already present
    private func fetchRoutingInfoIfNeeded() async {
        // Skip if already have data
        if record.routingInfo != nil && record.channelRecommendation != nil {
            return
        }

        isLoadingRoutingInfo = true
        defer { isLoadingRoutingInfo = false }

        do {
            // Call the evaluate endpoint to get fresh routing data
            let evaluation = try await BookAPI.fetchBookEvaluation(record.isbn)

            // Update state with dynamic data
            await MainActor.run {
                if evaluation.routingInfo != nil {
                    dynamicRoutingInfo = evaluation.routingInfo
                }
                if evaluation.channelRecommendation != nil {
                    dynamicChannelRecommendation = evaluation.channelRecommendation
                }
            }
        } catch {
            print("Failed to fetch routing info: \(error.localizedDescription)")
        }
    }

    @MainActor
    private func updatePriceEstimate() async {
        isUpdatingPrice = true
        defer { isUpdatingPrice = false }

        print("📡 Calling estimate_price with:")
        print("  condition: \(selectedCondition)")
        print("  hardcover: \(isHardcover), paperback: \(isPaperback), mass market: \(isMassMarket)")
        print("  signed: \(isSigned), first edition: \(isFirstEdition)")

        do {
            let response = try await BookAPI.estimatePrice(
                isbn: record.isbn,
                condition: selectedCondition,
                isHardcover: isHardcover ? true : nil,
                isPaperback: isPaperback ? true : nil,
                isMassMarket: isMassMarket ? true : nil,
                isSigned: isSigned ? true : nil,
                isFirstEdition: isFirstEdition ? true : nil
            )

            dynamicEstimate = response.estimatedPrice
            attributeDeltas = response.deltas
            dynamicProfitScenarios = response.profitScenarios
            priceLower = response.priceLower
            priceUpper = response.priceUpper
            confidencePercent = response.confidencePercent

            print("✅ Price estimate updated: $\(String(format: "%.2f", response.estimatedPrice))")
            print("  Deltas received: \(response.deltas.count) attributes")
        } catch {
            print("❌ Failed to update price estimate: \(error.localizedDescription)")
        }
    }

    @MainActor
    private func saveAttributes() async {
        do {
            var coverType: String? = nil
            if isHardcover {
                coverType = "Hardcover"
            } else if isPaperback {
                coverType = "Paperback"
            } else if isMassMarket {
                coverType = "Mass Market"
            }

            let printing = isFirstEdition ? "1st" : nil

            try await BookAPI.updateAttributes(
                isbn: record.isbn,
                condition: selectedCondition,
                coverType: coverType,
                signed: isSigned,
                firstEdition: isFirstEdition,
                printing: printing,
                estimatedPrice: dynamicEstimate  // Pass the updated price estimate
            )

            print("✓ Attributes saved successfully with new price: $\(String(format: "%.2f", dynamicEstimate ?? 0))")
            print("📋 Saved attributes: condition=\(selectedCondition), coverType=\(coverType ?? "nil"), signed=\(isSigned), firstEdition=\(isFirstEdition)")
        } catch {
            print("Failed to save attributes: \(error.localizedDescription)")
            // TODO: Show error alert to user
        }
    }

    // MARK: - Price Variants Panel

    @ViewBuilder
    private var loadingVariantsPanel: some View {
        VStack(spacing: 16) {
            HStack {
                Image(systemName: "slider.horizontal.3")
                    .foregroundStyle(.purple)
                Text("Price Adjustments")
                    .font(.headline)
                Spacer()
            }

            ProgressView()
                .frame(maxWidth: .infinity)
                .padding()
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

    @ViewBuilder
    private func priceVariantsPanel(_ variants: PriceVariantsResponse) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header with toggle
            Button {
                withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                    showVariantsExpanded.toggle()
                }
            } label: {
                HStack {
                    Image(systemName: "slider.horizontal.3")
                        .foregroundStyle(.purple)
                    Text("Price Adjustments")
                        .font(.headline)
                        .foregroundStyle(.primary)
                    Spacer()
                    Image(systemName: showVariantsExpanded ? "chevron.up" : "chevron.down")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            // Summary (always visible)
            HStack {
                Text("Current")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Spacer()
                Text("$\(String(format: "%.2f", variants.currentPrice))")
                    .font(.headline)
                    .foregroundStyle(.primary)
                Text("(\(variants.currentCondition))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)

            if showVariantsExpanded {
                Divider()

                // Condition Variants Section
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Image(systemName: "sparkles")
                            .font(.caption)
                            .foregroundStyle(.orange)
                        Text("By Condition")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                    }

                    VStack(spacing: 6) {
                        ForEach(variants.conditionVariants.prefix(5)) { variant in
                            if let condition = variant.condition {
                                priceVariantRow(
                                    label: condition,
                                    price: variant.price,
                                    difference: variant.priceDifference,
                                    percentage: variant.percentageChange,
                                    sampleSize: variant.sampleSize,
                                    dataSource: variant.dataSource,
                                    isCurrent: condition == variants.currentCondition
                                )
                            }
                        }
                    }
                }

                Divider()

                // Feature Variants Section
                if !variants.featureVariants.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Image(systemName: "star.fill")
                                .font(.caption)
                                .foregroundStyle(.yellow)
                            Text("With Special Features")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                        }

                        VStack(spacing: 6) {
                            ForEach(variants.featureVariants.prefix(6)) { variant in
                                if let description = variant.description {
                                    priceVariantRow(
                                        label: description,
                                        price: variant.price,
                                        difference: variant.priceDifference,
                                        percentage: variant.percentageChange,
                                        sampleSize: variant.sampleSize,
                                        dataSource: variant.dataSource,
                                        isCurrent: false
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

    @ViewBuilder
    private func priceVariantRow(
        label: String,
        price: Double,
        difference: Double,
        percentage: Double,
        sampleSize: Int,
        dataSource: String,
        isCurrent: Bool
    ) -> some View {
        HStack(alignment: .center, spacing: 8) {
            // Label
            HStack(spacing: 4) {
                Text(label)
                    .font(.caption)
                    .foregroundStyle(isCurrent ? .primary : .secondary)
                    .lineLimit(1)

                // Data source badge
                if dataSource == "comps" && sampleSize > 0 {
                    HStack(spacing: 2) {
                        Image(systemName: "chart.bar.fill")
                            .font(.system(size: 8))
                        Text("\(sampleSize)")
                            .font(.system(size: 9))
                    }
                    .foregroundStyle(.blue)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 2)
                    .background(Color.blue.opacity(0.1), in: Capsule())
                } else if dataSource == "estimated" {
                    Image(systemName: "wand.and.stars")
                        .font(.system(size: 9))
                        .foregroundStyle(.purple.opacity(0.6))
                }
            }

            Spacer()

            // Price
            Text("$\(String(format: "%.2f", price))")
                .font(.caption)
                .fontWeight(isCurrent ? .semibold : .regular)
                .foregroundStyle(.primary)

            // Change indicator
            if !isCurrent {
                HStack(spacing: 2) {
                    Image(systemName: difference > 0 ? "arrow.up" : "arrow.down")
                        .font(.system(size: 8))
                    Text(String(format: "%+.0f%%", percentage))
                        .font(.system(size: 10))
                }
                .foregroundStyle(difference > 0 ? .green : .red)
                .padding(.horizontal, 4)
                .padding(.vertical, 2)
                .background(
                    (difference > 0 ? Color.green : Color.red).opacity(0.1),
                    in: Capsule()
                )
            } else {
                Text("Current")
                    .font(.system(size: 9))
                    .foregroundStyle(.blue)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 2)
                    .background(Color.blue.opacity(0.1), in: Capsule())
            }
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 8)
        .background(
            isCurrent ? Color.blue.opacity(0.05) : Color.clear,
            in: RoundedRectangle(cornerRadius: 6)
        )
    }
}

// MARK: - Interactive Attributes View

struct AttributesView: View {
    @Binding var condition: String
    @Binding var isHardcover: Bool
    @Binding var isPaperback: Bool
    @Binding var isMassMarket: Bool
    @Binding var isSigned: Bool
    @Binding var isFirstEdition: Bool
    let priceEstimate: Double
    let priceLower: Double?
    let priceUpper: Double?
    let confidencePercent: Double?

    let deltas: [AttributeDelta]
    let onAttributeChanged: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Book Attributes")
                .font(.headline)

            // Condition Picker
            VStack(alignment: .leading, spacing: 8) {
                Text("Condition")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                Picker("Condition", selection: $condition) {
                    Text("New").tag("New")
                    Text("Like New").tag("Like New")
                    Text("Very Good").tag("Very Good")
                    Text("Good").tag("Good")
                    Text("Acceptable").tag("Acceptable")
                    Text("Poor").tag("Poor")
                }
                .pickerStyle(.segmented)
                .onChange(of: condition) { oldValue, newValue in
                    print("📝 Condition changed to: \(newValue)")
                    onAttributeChanged()
                }
            }

            // Format (mutually exclusive)
            VStack(alignment: .leading, spacing: 8) {
                Text("Format")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                HStack(spacing: 8) {
                    FormatToggle(
                        label: "Hardcover",
                        isSelected: $isHardcover,
                        delta: deltas.first { $0.attribute == "is_hardcover" }?.delta,
                        onToggle: {
                            if isHardcover {
                                isPaperback = false
                                isMassMarket = false
                            }
                            onAttributeChanged()
                        }
                    )

                    FormatToggle(
                        label: "Paperback",
                        isSelected: $isPaperback,
                        delta: deltas.first { $0.attribute == "is_paperback" }?.delta,
                        onToggle: {
                            if isPaperback {
                                isHardcover = false
                                isMassMarket = false
                            }
                            onAttributeChanged()
                        }
                    )

                    FormatToggle(
                        label: "Mass Market",
                        isSelected: $isMassMarket,
                        delta: deltas.first { $0.attribute == "is_mass_market" }?.delta,
                        onToggle: {
                            if isMassMarket {
                                isHardcover = false
                                isPaperback = false
                            }
                            onAttributeChanged()
                        }
                    )
                }
            }

            // Special Attributes
            VStack(alignment: .leading, spacing: 8) {
                Text("Special Attributes")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                AttributeToggle(
                    label: "Signed/Autographed",
                    isOn: $isSigned,
                    delta: deltas.first { $0.attribute == "is_signed" }?.delta,
                    onToggle: onAttributeChanged
                )

                AttributeToggle(
                    label: "First Edition",
                    isOn: $isFirstEdition,
                    delta: deltas.first { $0.attribute == "is_first_edition" }?.delta,
                    onToggle: onAttributeChanged
                )
            }

            // Price Display with Prediction Range
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Estimated Price:")
                        .font(.headline)
                    Spacer()
                    Text("$\(String(format: "%.2f", priceEstimate))")
                        .font(.title2)
                        .bold()
                        .foregroundColor(.green)
                }

                // Show prediction interval if available
                if let lower = priceLower, let upper = priceUpper, let confidence = confidencePercent {
                    Divider()

                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Image(systemName: "chart.line.uptrend.xyaxis")
                                .font(.caption)
                                .foregroundStyle(.blue)
                            Text("\(String(format: "%.0f%%", confidence)) Confidence Range")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundStyle(.secondary)
                        }

                        HStack(spacing: 4) {
                            Text("$\(String(format: "%.2f", lower))")
                                .font(.caption)
                                .foregroundStyle(.orange)
                            Text("–")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text("$\(String(format: "%.2f", upper))")
                                .font(.caption)
                                .foregroundStyle(.orange)
                        }
                        .padding(.leading, 20)
                    }
                }
            }
            .padding(.vertical, 8)
            .padding(.horizontal)
            .background(Color.green.opacity(0.1))
            .cornerRadius(8)
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(radius: 2)
    }
}

struct AttributeToggle: View {
    let label: String
    @Binding var isOn: Bool
    let delta: Double?
    let onToggle: () -> Void

    var body: some View {
        HStack {
            Toggle(label, isOn: $isOn)
                .onChange(of: isOn) { oldValue, newValue in
                    print("📝 AttributeToggle '\(label)' changed to: \(newValue)")
                    onToggle()
                }

            if let delta = delta, delta != 0 {
                Text(delta > 0 ? "+$\(String(format: "%.2f", delta))" : "$\(String(format: "%.2f", delta))")
                    .font(.caption)
                    .foregroundColor(delta > 0 ? .green : .red)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(delta > 0 ? Color.green.opacity(0.1) : Color.red.opacity(0.1))
                    .cornerRadius(4)
            }
        }
    }
}

struct FormatToggle: View {
    let label: String
    @Binding var isSelected: Bool
    let delta: Double?
    let onToggle: () -> Void

    var body: some View {
        VStack(spacing: 4) {
            Button(action: {
                print("📝 FormatToggle '\(label)' button pressed, current: \(isSelected)")
                isSelected.toggle()
                print("📝 FormatToggle '\(label)' now: \(isSelected)")
                onToggle()
            }) {
                Text(label)
                    .font(.caption)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 12)
                    .background(isSelected ? Color.blue : Color.gray.opacity(0.2))
                    .foregroundColor(isSelected ? .white : .primary)
                    .cornerRadius(8)
            }

            if let delta = delta, delta != 0 {
                Text(delta > 0 ? "+$\(String(format: "%.2f", delta))" : "$\(String(format: "%.2f", delta))")
                    .font(.caption2)
                    .foregroundColor(delta > 0 ? .green : .red)
            }
        }
    }
}
