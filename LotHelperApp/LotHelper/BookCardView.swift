import SwiftUI

struct BookCardView: View {
    struct Book {
        let title: String
        let author: String?
        let series: String?
        let thumbnail: String
        let score: String?

        var coverURL: URL? { URL(string: thumbnail) }
        var coverRequest: URLRequest? {
            guard let url = coverURL else { return nil }
            var request = URLRequest(url: url)
            request.cachePolicy = .returnCacheDataElseLoad
            return request
        }

        static let placeholder = Book(title: "Loading", author: nil, series: nil, thumbnail: "", score: nil)
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
                    Text(series)
                        .font(.caption)
                        .foregroundStyle(DS.Color.textSecondary)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: DS.Spacing.md)

            if let score = book.score {
                Label(score, systemImage: "chart.line.uptrend.xyaxis")
                    .font(.caption)
                    .foregroundStyle(DS.Color.textSecondary)
                    .labelStyle(.titleAndIcon)
                    .accessibilityLabel("Sales signal score \(score)")
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
}

#Preview(traits: .sizeThatFitsLayout) {
    BookCardView(book: .init(
        title: "Ship of Magic",
        author: "Robin Hobb",
        series: "Liveship Traders",
        thumbnail: "https://covers.openlibrary.org/b/isbn/9780670855032-M.jpg",
        score: "92"
    ))
    .padding()
    .background(DS.Color.background)
}

