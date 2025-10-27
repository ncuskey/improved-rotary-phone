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

        static let placeholder = Book(title: "Loading", author: nil, series: nil, thumbnail: "", score: nil, profitPotential: nil, estimatedPrice: nil, soldCompsMedian: nil, bestVendorPrice: nil, amazonLowestPrice: nil, timeToSellDays: nil)
    }

    let book: Book
    var onViewDetails: () -> Void = {}
    var onAddToLot: () -> Void = {}

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
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
            .frame(width: 60, height: 90)
            .clipShape(RoundedRectangle(cornerRadius: DS.Radius.sm))
            .accessibilityLabel(Text("Cover of \(book.title)"))

            VStack(alignment: .leading, spacing: 4) {
                Text(book.title)
                    .titleStyle()
                    .lineLimit(2)
                if let author = book.author, !author.isEmpty {
                    Text(author)
                        .subtitleStyle()
                        .lineLimit(1)
                }
                if let series = book.series, !series.isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: "books.vertical.fill")
                            .font(.caption2)
                        Text(series)
                            .font(.caption)
                    }
                    .foregroundStyle(DS.Color.textSecondary)
                    .lineLimit(1)
                }
                if let tts = book.ttsCategory {
                    HStack(spacing: 4) {
                        Image(systemName: ttsIcon(for: tts))
                            .font(.caption2)
                        Text("TTS: \(tts)")
                            .font(.caption)
                    }
                    .foregroundStyle(ttsColor(for: tts))
                    .lineLimit(1)
                }
                if let margin = book.profitMargin, let percentage = book.profitMarginPercentage {
                    Text("$\(String(format: "%.2f", margin)) (\(String(format: "%.0f", percentage))%)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer(minLength: DS.Spacing.md)

            VStack(alignment: .trailing, spacing: 4) {
                if let score = book.score {
                    Label(score, systemImage: "chart.line.uptrend.xyaxis")
                        .font(.caption)
                        .foregroundStyle(DS.Color.textSecondary)
                        .labelStyle(.titleAndIcon)
                        .accessibilityLabel("Sales signal score \(score)")
                }
                if let median = book.soldCompsMedian {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("eBay")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text("$\(String(format: "%.2f", median))")
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundStyle(.primary)
                    }
                }
                if let vendor = book.bestVendorPrice, vendor > 0 {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("Vendor")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text("$\(String(format: "%.2f", vendor))")
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundStyle(.green)
                    }
                }
                if let amazonPrice = book.amazonLowestPrice, amazonPrice > 0 {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("Amazon")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text("$\(String(format: "%.2f", amazonPrice))")
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundStyle(.orange)
                    }
                }
                if let estimated = book.estimatedPrice, estimated > 0 {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("Estimate")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text("$\(String(format: "%.2f", estimated))")
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundStyle(.blue)
                    }
                }
            }
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
        timeToSellDays: 25
    ))
    .padding()
    .background(DS.Color.background)
}

