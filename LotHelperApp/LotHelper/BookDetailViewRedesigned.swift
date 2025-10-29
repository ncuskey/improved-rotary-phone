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
    @Environment(\.dismiss) private var dismiss

    // Interactive attributes state
    @State private var selectedCondition: String = "Good"
    @State private var isHardcover: Bool = false
    @State private var isPaperback: Bool = false
    @State private var isMassMarket: Bool = false
    @State private var isSigned: Bool = false
    @State private var isFirstEdition: Bool = false
    @State private var dynamicEstimate: Double? = nil
    @State private var attributeDeltas: [AttributeDelta] = []
    @State private var isUpdatingPrice: Bool = false

    var lotsContainingBook: [LotSuggestionDTO] {
        lots.filter { lot in
            lot.bookIsbns.contains(record.isbn)
        }
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Hero section with cover and title
                heroSection

                // List to eBay button
                ebayListingButton

                // Price comparison panel
                priceComparisonPanel

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
                    deltas: attributeDeltas,
                    onAttributeChanged: {
                        Task {
                            await updatePriceEstimate()
                        }
                    },
                    onSave: {
                        Task {
                            await saveAttributes()
                        }
                    }
                )

                // Profit analysis (if available)
                if shouldShowProfitAnalysis {
                    profitAnalysisPanel
                }

                // Market data
                if record.market != nil {
                    marketDataPanel
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

                if let series = record.metadata?.seriesName {
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
    }

    private var sortedPrices: [PriceItem] {
        let items = [
            PriceItem(
                label: "eBay Median",
                price: record.market?.soldCompsMedian,
                icon: "bag.fill",
                color: .primary
            ),
            PriceItem(
                label: "Vendor Best",
                price: record.bookscouter?.bestPrice,
                icon: "arrow.2.circlepath",
                color: .green
            ),
            PriceItem(
                label: "Amazon Low",
                price: record.bookscouter?.amazonLowestPrice,
                icon: "cart.fill",
                color: .orange
            ),
            PriceItem(
                label: "Estimated",
                price: record.estimatedPrice,
                icon: "chart.bar.fill",
                color: .blue
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
        HStack(spacing: 12) {
            Image(systemName: item.icon)
                .font(.body)
                .foregroundStyle(item.color)
                .frame(width: 24)

            Text(item.label)
                .font(.subheadline)
                .foregroundStyle(.primary)

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
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(item.color.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Profit Analysis Panel
    private var shouldShowProfitAnalysis: Bool {
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
        if let soldMedian = record.market?.soldCompsMedian,
           let vendorPrice = record.bookscouter?.bestPrice {

            let margin = soldMedian - vendorPrice
            let percentage = (margin / vendorPrice) * 100

            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .foregroundStyle(.green)
                    Text("Profit Analysis")
                        .font(.headline)
                }

                // Profit margin
                VStack(spacing: 8) {
                    HStack {
                        Text("Potential Margin")
                            .font(.subheadline)
                        Spacer()
                        VStack(alignment: .trailing, spacing: 2) {
                            Text(formattedCurrency(margin))
                                .font(.title2)
                                .bold()
                                .foregroundStyle(margin > 0 ? .green : .red)
                            Text("\(String(format: "%.0f", percentage))% markup")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    Divider()

                    // Calculation breakdown
                    HStack {
                        Text("eBay Sale")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(formattedCurrency(soldMedian))
                            .font(.caption)
                            .fontWeight(.medium)
                    }

                    HStack {
                        Text("Cost (Vendor)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(formattedCurrency(vendorPrice))
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundStyle(.green)
                    }
                }
                .padding(12)
                .background(Color.green.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
            }
            .padding()
            .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
            .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
        }
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
                Image(systemName: "list.bullet.clipboard.fill")
                    .foregroundStyle(.blue)
                Text("Evaluation Factors")
                    .font(.headline)
            }

            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(reasons.enumerated()), id: \.offset) { index, reason in
                    HStack(alignment: .top, spacing: 8) {
                        Text("\(index + 1).")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .frame(width: 20, alignment: .leading)
                        Text(reason)
                            .font(.caption)
                            .fixedSize(horizontal: false, vertical: true)
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

    @MainActor
    private func updatePriceEstimate() async {
        isUpdatingPrice = true
        defer { isUpdatingPrice = false }

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
        } catch {
            print("Failed to update price estimate: \(error.localizedDescription)")
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
                coverType: coverType,
                signed: isSigned,
                printing: printing
            )

            print("✓ Attributes saved successfully")
            // TODO: Show success feedback to user
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

    let deltas: [AttributeDelta]
    let onAttributeChanged: () -> Void
    let onSave: () -> Void

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
                .onChange(of: condition) { _ in onAttributeChanged() }
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

            // Price Display
            HStack {
                Text("Estimated Price:")
                    .font(.headline)
                Spacer()
                Text("$\(String(format: "%.2f", priceEstimate))")
                    .font(.title2)
                    .bold()
                    .foregroundColor(.green)
            }
            .padding(.vertical, 8)
            .padding(.horizontal)
            .background(Color.green.opacity(0.1))
            .cornerRadius(8)

            // Save Button
            Button(action: onSave) {
                Text("Save Attributes")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
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
                .onChange(of: isOn) { _ in onToggle() }

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
                isSelected.toggle()
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
