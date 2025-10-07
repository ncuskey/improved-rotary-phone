import SwiftUI

struct BooksTabView: View {
    @State private var books: [BookEvaluationRecord] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

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
                    ScrollView {
                        LazyVStack(spacing: DS.Spacing.md) {
                            ForEach(books) { book in
                                NavigationLink(value: book) {
                                    BookCardView(book: book.cardModel)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.vertical, DS.Spacing.md)
                        .padding(.horizontal, DS.Spacing.xl)
                    }
                    .scrollIndicators(.hidden)
                    .background(DS.Color.background)
                    .refreshable { await loadBooks() }
                    .navigationDestination(for: BookEvaluationRecord.self) { record in
                        BookDetailView(record: record)
                    }
                }
            }
            .navigationTitle("Books")
            .task { await initialLoadIfNeeded() }
        }
        .background(DS.Color.background)
    }

    @MainActor
    private func initialLoadIfNeeded() async {
        if books.isEmpty && !isLoading {
            await loadBooks()
        }
    }

    @MainActor
    private func loadBooks() async {
        isLoading = true
        errorMessage = nil
        do {
            books = try await BookAPI.fetchAllBooks()
            isLoading = false
        } catch {
            isLoading = false
            errorMessage = "Failed to load books: \(error.localizedDescription)"
        }
    }
}

private extension BookEvaluationRecord {
    var cardModel: BookCardView.Book {
        let resolvedTitle = metadata?.title?.trimmedNonEmpty ?? metadata?.subtitle?.trimmedNonEmpty ?? isbn
        let resolvedAuthor = metadata?.primaryAuthor?.trimmedNonEmpty
        let resolvedSeries = metadata?.subtitle?.trimmedNonEmpty ?? metadata?.categories?.first?.trimmedNonEmpty
        let resolvedScore = probabilityLabel?.trimmedNonEmpty

        let thumbnail = (metadata?.thumbnail?.trimmedNonEmpty ?? fallbackCoverURLString) ?? ""

        return BookCardView.Book(
            title: resolvedTitle,
            author: resolvedAuthor,
            series: resolvedSeries,
            thumbnail: thumbnail,
            score: resolvedScore
        )
    }

    private var fallbackCoverURLString: String? {
        guard !isbn.isEmpty else { return nil }
        return "https://covers.openlibrary.org/b/isbn/\(isbn)-M.jpg"
    }
}

private struct BookDetailView: View {
    let record: BookEvaluationRecord

    var body: some View {
        List {
            coverSection
            overviewSection
            metadataSection
            justificationSection
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(DS.Color.background)
        .navigationTitle(record.metadata?.title ?? record.isbn)
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
            return URL(string: "https://covers.openlibrary.org/b/isbn/\(record.isbn)-M.jpg")
        }
        return nil
    }

    private func formattedCurrency(_ value: Double) -> String {
        value.formatted(.currency(code: "USD"))
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
                    title: "Sample Book Title",
                    subtitle: "A Journey into Testing",
                    authors: ["Jane Doe", "Alex Roe"],
                    creditedAuthors: nil,
                    canonicalAuthor: "Jane Doe",
                    publisher: "Sample Publisher",
                    publishedYear: 2018,
                    description: "This is a sample description used for SwiftUI previews.",
                    thumbnail: "https://covers.openlibrary.org/b/isbn/9780670855032-M.jpg",
                    categories: ["Fiction", "Adventure"]
                ),
                booksrunValueLabel: nil,
                booksrunValueRatio: nil,
                rarity: nil
            )
        )
    }
}
