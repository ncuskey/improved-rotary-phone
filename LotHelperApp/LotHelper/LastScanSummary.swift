import SwiftUI

struct LastScanSummary: View {
    let book: BookInfo

    private var coverURL: URL? {
        guard !book.thumbnail.isEmpty else { return nil }
        return URL(string: book.thumbnail)
    }

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            if let url = coverURL {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                    case .failure:
                        placeholder
                    default:
                        placeholder.overlay(ProgressView())
                    }
                }
                .frame(width: 60, height: 90)
                .clipShape(RoundedRectangle(cornerRadius: DS.Radius.sm))
                .accessibilityHidden(true)
            } else {
                placeholder
                    .frame(width: 60, height: 90)
                    .clipShape(RoundedRectangle(cornerRadius: DS.Radius.sm))
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Last scan")
                    .font(.caption)
                    .foregroundStyle(DS.Color.textSecondary)
                Text(book.title)
                    .bodyStyle().fontWeight(.semibold)
                    .lineLimit(2)
                HStack(spacing: 6) {
                    Text(book.author)
                        .font(.caption)
                        .foregroundStyle(DS.Color.textSecondary)
                        .lineLimit(1)
                    if let year = book.publishedYear {
                        Text("•")
                            .font(.caption)
                            .foregroundStyle(DS.Color.textSecondary)
                        Text("\(year)")
                            .font(.caption)
                            .foregroundStyle(DS.Color.textSecondary)
                    }
                }
            }

            Spacer(minLength: DS.Spacing.md)
        }
        .padding(DS.Spacing.md)
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
        .accessibilityElement(children: .combine)
    }

    private var placeholder: some View {
        Rectangle().fill(DS.Color.cardBg)
            .overlay(Image(systemName: "book.closed").foregroundStyle(DS.Color.textSecondary))
    }
}

#Preview {
    LastScanSummary(
        book: BookInfo(
            isbn: "9780670855032",
            title: "Ship of Magic",
            author: "Robin Hobb",
            authors: ["Robin Hobb"],
            subtitle: "(Liveship Traders #1)",
            description: "A fantasy adventure.",
            publishedYear: 1998,
            thumbnail: "https://covers.openlibrary.org/b/isbn/9780670855032-L.jpg",
            categories: ["Fantasy"]
        )
    )
    .padding()
    .background(DS.Color.background)
}

