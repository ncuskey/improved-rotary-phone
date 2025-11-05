import SwiftUI

struct BookCardView: View {
    struct Book {
        let title: String
        let author: String?
        let series: String?
        let thumbnail: String
        let score: String?
        let profitPotential: String?
        let estimatedPrice: Double?
        let soldCompsMedian: Double?
        let bestVendorPrice: Double?
        let amazonLowestPrice: Double?
        let timeToSellDays: Int?
        let soldCount: Int?

        // NEW: Routing info and channel recommendation
        let routingInfo: MLRoutingInfo?
        let channelRecommendation: ChannelRecommendation?

        var coverURL: URL? { URL(string: thumbnail) }
        var coverRequest: URLRequest? {
            guard let url = coverURL else { return nil }
            var request = URLRequest(url: url)
            request.cachePolicy = .returnCacheDataElseLoad
            return request
        }

        var profitMargin: Double? {
            guard let median = soldCompsMedian, let vendor = bestVendorPrice, vendor > 0 else { return nil }
            return median - vendor
        }

        var profitMarginPercentage: Double? {
            guard let margin = profitMargin, let vendor = bestVendorPrice, vendor > 0 else { return nil }
            return (margin / vendor) * 100
        }

        var ttsCategory: String? {
            guard let days = timeToSellDays else { return nil }
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

        static let placeholder = Book(title: "Loading", author: nil, series: nil, thumbnail: "", score: nil, profitPotential: nil, estimatedPrice: nil, soldCompsMedian: nil, bestVendorPrice: nil, amazonLowestPrice: nil, timeToSellDays: nil, soldCount: nil, routingInfo: nil, channelRecommendation: nil)
    }

    let book: Book
    var onViewDetails: () -> Void = {}
    var onAddToLot: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            // HERO METRICS SECTION - Most important info at top
            if let recommendation = book.channelRecommendation {
                HStack(alignment: .center, spacing: 12) {
                    // Expected profit - largest, most prominent
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Expected Profit")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text("$\(String(format: "%.2f", recommendation.expectedProfit))")
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundStyle(.green)
                    }

                    Divider()
                        .frame(height: 30)

                    // Channel recommendation
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Sell via")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        ChannelRecommendationPill(recommendation: recommendation)
                    }

                    Spacer()
                }
                .padding(.bottom, 4)
            } else if let estimated = book.estimatedPrice, estimated > 0 {
                // Fallback: just show estimated price if no recommendation
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Estimated Value")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text("$\(String(format: "%.2f", estimated))")
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundStyle(.blue)
                    }
                    Spacer()
                }
                .padding(.bottom, 4)
            }

            Divider()

            // BOOK INFO & DETAILS SECTION
            HStack(spacing: DS.Spacing.md) {
                // Cover image
                AsyncImage(url: book.coverURL) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .interpolation(.high)
                            .scaledToFill()
                    case .failure:
                        Rectangle().fill(DS.Color.cardBg)
                            .overlay(Image(systemName: "book.closed").foregroundStyle(DS.Color.textSecondary))
                    default:
                        Rectangle().fill(DS.Color.cardBg)
                            .overlay(ProgressView())
                    }
                }
                .frame(width: 50, height: 75)
                .clipShape(RoundedRectangle(cornerRadius: DS.Radius.sm))
                .accessibilityLabel(Text("Cover of \(book.title)"))

                // Book metadata
                VStack(alignment: .leading, spacing: 3) {
                    Text(book.title)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .lineLimit(2)
                    if let author = book.author, !author.isEmpty {
                        Text(author)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    if let series = book.series, !series.isEmpty {
                        HStack(spacing: 3) {
                            Image(systemName: "books.vertical.fill")
                                .font(.caption2)
                            Text(series)
                                .font(.caption2)
                        }
                        .foregroundStyle(DS.Color.textSecondary)
                        .lineLimit(1)
                    }
                }

                Spacer(minLength: DS.Spacing.sm)

                // ML model badge (compact, right side)
                if let routing = book.routingInfo {
                    VStack(alignment: .trailing, spacing: 4) {
                        MLModelBadge(routing: routing)
                        if let score = book.score {
                            Label(score, systemImage: "chart.line.uptrend.xyaxis")
                                .font(.caption2)
                                .foregroundStyle(DS.Color.textSecondary)
                                .labelStyle(.titleAndIcon)
                        }
                    }
                }
            }

            // QUICK METRICS ROW
            HStack(spacing: 12) {
                // Time to sell
                if let tts = book.ttsCategory {
                    HStack(spacing: 3) {
                        Image(systemName: ttsIcon(for: tts))
                            .font(.caption2)
                        Text(tts)
                            .font(.caption2)
                            .fontWeight(.medium)
                    }
                    .foregroundStyle(ttsColor(for: tts))
                }

                // Sold count
                if let count = book.soldCount, count > 0 {
                    HStack(spacing: 3) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.caption2)
                        Text("\(count) sold")
                            .font(.caption2)
                            .fontWeight(.medium)
                    }
                    .foregroundStyle(.blue)
                }

                Spacer()

                // Platform prices (compact)
                HStack(spacing: 8) {
                    if let median = book.soldCompsMedian {
                        VStack(alignment: .trailing, spacing: 1) {
                            Text("eBay")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text("$\(String(format: "%.0f", median))")
                                .font(.caption)
                                .fontWeight(.semibold)
                        }
                    }
                    if let vendor = book.bestVendorPrice, vendor > 0 {
                        VStack(alignment: .trailing, spacing: 1) {
                            Text("Cost")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text("$\(String(format: "%.0f", vendor))")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundStyle(.green)
                        }
                    }
                }
            }
            .font(.caption2)
        }
        .padding(DS.Spacing.md)
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
        .contentShape(Rectangle())
        .contextMenu {
            Button("View Details", systemImage: "info.circle", action: onViewDetails)
            Button("Add to Lot", systemImage: "shippingbox", action: onAddToLot)
        }
        .accessibilityElement(children: .combine)
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

    private func ttsIcon(for category: String) -> String {
        switch category.lowercased() {
        case "fast":
            return "hare.fill"
        case "medium":
            return "tortoise.fill"
        case "slow":
            return "clock.fill"
        case "very slow":
            return "hourglass.fill"
        default:
            return "questionmark.circle.fill"
        }
    }
}

#Preview(traits: .sizeThatFitsLayout) {
    BookCardView(book: .init(
        title: "Ship of Magic",
        author: "Robin Hobb",
        series: "Liveship Traders",
        thumbnail: "https://covers.openlibrary.org/b/isbn/9780670855032-L.jpg",
        score: "92",
        profitPotential: "High",
        estimatedPrice: 22.50,
        soldCompsMedian: 24.99,
        bestVendorPrice: 8.50,
        amazonLowestPrice: 28.99,
        timeToSellDays: 25,
        soldCount: 18,
        routingInfo: MLRoutingInfo(
            model: "ebay_specialist",
            modelDisplayName: "eBay Specialist",
            modelMae: 3.03,
            modelR2: 0.469,
            features: 20,
            confidence: "high",
            confidenceScore: 0.85,
            routingReason: "eBay market data available",
            coverage: "72% of catalog"
        ),
        channelRecommendation: ChannelRecommendation(
            channel: "ebay_individual",
            confidence: 0.85,
            reasoning: ["High eBay value", "Good sell-through rate"],
            expectedProfit: 16.49,
            expectedDaysToSale: 25
        )
    ))
    .padding()
    .background(DS.Color.background)
}

