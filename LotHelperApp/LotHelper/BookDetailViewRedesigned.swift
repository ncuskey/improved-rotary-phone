import SwiftUI

// MARK: - Redesigned Book Detail View
// This follows the same design philosophy as ScannerReviewView with card-based panels

struct BookDetailViewRedesigned: View {
    let record: BookEvaluationRecord
    @State private var lots: [LotSuggestionDTO] = []
    @State private var isLoadingLots = false
    @Environment(\.dismiss) private var dismiss

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

                // Price comparison panel
                priceComparisonPanel

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
                if let label = record.probabilityLabel {
                    statBadge(label.uppercased(), color: probabilityColor(for: label))
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

            // Price grid
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                if let ebayPrice = record.market?.soldCompsMedian {
                    priceCard("eBay Median", ebayPrice, icon: "bag.fill", color: .primary)
                }

                if let vendorPrice = record.bookscouter?.bestPrice, vendorPrice > 0 {
                    priceCard("Vendor Best", vendorPrice, icon: "arrow.2.circlepath", color: .green)
                }

                if let amazonPrice = record.bookscouter?.amazonLowestPrice, amazonPrice > 0 {
                    priceCard("Amazon Low", amazonPrice, icon: "cart.fill", color: .orange)
                }

                if let estimated = record.estimatedPrice, estimated > 0 {
                    priceCard("Estimated", estimated, icon: "chart.bar.fill", color: .blue)
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

    // MARK: - Price Card Component
    @ViewBuilder
    private func priceCard(_ label: String, _ price: Double, icon: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.caption2)
                    .foregroundStyle(color)
                Text(label)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(formattedCurrency(price))
                .font(.title3)
                .fontWeight(.bold)
                .foregroundStyle(color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
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
