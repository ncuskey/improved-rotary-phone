import SwiftUI

/// View that displays books grouped by vendor for quick review and fulfillment
struct VendorsTabView: View {
    @State private var vendorGroups: [VendorGroup] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            ZStack {
                if isLoading {
                    ProgressView("Loading vendors...")
                } else if let error = errorMessage {
                    ContentUnavailableView {
                        Label("Error Loading Vendors", systemImage: "exclamationmark.triangle")
                    } description: {
                        Text(error)
                    } actions: {
                        Button("Retry") {
                            Task { await loadVendors() }
                        }
                    }
                } else if vendorGroups.isEmpty {
                    ContentUnavailableView {
                        Label("No Vendor Deliveries", systemImage: "shippingbox")
                    } description: {
                        Text("Books grouped by vendor will appear here")
                    }
                } else {
                    ScrollView {
                        LazyVStack(spacing: 16) {
                            ForEach(vendorGroups) { group in
                                VendorGroupCard(group: group)
                            }
                        }
                        .padding()
                    }
                }
            }
            .navigationTitle("Vendors")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        Task { await loadVendors() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(isLoading)
                }
            }
            .task {
                await loadVendors()
            }
        }
    }

    private func loadVendors() async {
        isLoading = true
        errorMessage = nil

        do {
            vendorGroups = try await BookAPI.getVendorGroups()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}

/// Individual vendor group card
struct VendorGroupCard: View {
    let group: VendorGroup
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header with vendor name and summary
            Button {
                withAnimation {
                    isExpanded.toggle()
                }
            } label: {
                HStack(spacing: 12) {
                    // Vendor icon
                    Image(systemName: vendorIcon)
                        .font(.title2)
                        .foregroundStyle(vendorColor)
                        .frame(width: 40, height: 40)
                        .background(
                            Circle()
                                .fill(vendorColor.opacity(0.15))
                        )

                    VStack(alignment: .leading, spacing: 4) {
                        Text(group.vendor)
                            .font(.headline)
                            .foregroundStyle(.primary)

                        Text("\(group.bookCount) book\(group.bookCount == 1 ? "" : "s")")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    // Total value
                    if group.totalValue > 0 {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("Total Value")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text("$\(String(format: "%.2f", group.totalValue))")
                                .font(.title3)
                                .fontWeight(.semibold)
                                .foregroundStyle(.green)
                        }
                    }

                    // Expand/collapse chevron
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .buttonStyle(.plain)

            // Expanded content - show books
            if isExpanded {
                Divider()

                VStack(spacing: 8) {
                    ForEach(group.books, id: \.isbn) { book in
                        BookRowInVendorGroup(book: book)
                    }
                }
            }
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.secondarySystemGroupedBackground))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(vendorColor.opacity(0.3), lineWidth: 1)
        )
    }

    private var vendorIcon: String {
        switch group.vendor.lowercased() {
        case let v where v.contains("bookscouter") && v.contains("delivered"):
            return "checkmark.circle.fill"
        case let v where v.contains("bookscouter") && v.contains("expected"):
            return "clock.fill"
        case let v where v.contains("amazon"):
            return "cart.fill"
        case let v where v.contains("ebay"):
            return "tag.fill"
        default:
            return "shippingbox.fill"
        }
    }

    private var vendorColor: Color {
        switch group.vendor.lowercased() {
        case let v where v.contains("delivered"):
            return .green
        case let v where v.contains("expected"):
            return .orange
        case let v where v.contains("amazon"):
            return .blue
        case let v where v.contains("ebay"):
            return .purple
        default:
            return .gray
        }
    }
}

/// Individual book row within a vendor group
struct BookRowInVendorGroup: View {
    let book: VendorBook

    var body: some View {
        HStack(spacing: 12) {
            // Thumbnail
            if let thumbnail = book.thumbnail, let url = URL(string: thumbnail) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                    case .failure, .empty:
                        Image(systemName: "book.closed")
                            .foregroundStyle(.secondary)
                    @unknown default:
                        EmptyView()
                    }
                }
                .frame(width: 40, height: 60)
                .background(Color(.tertiarySystemGroupedBackground))
                .cornerRadius(4)
            } else {
                Image(systemName: "book.closed")
                    .foregroundStyle(.secondary)
                    .frame(width: 40, height: 60)
                    .background(Color(.tertiarySystemGroupedBackground))
                    .cornerRadius(4)
            }

            // Book info
            VStack(alignment: .leading, spacing: 4) {
                Text(book.title)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(2)

                if let authors = book.authors, !authors.isEmpty {
                    Text(authors.joined(separator: ", "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Text(book.isbn)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .monospaced()
            }

            Spacer()

            // Value
            if book.estimatedPrice > 0 {
                Text("$\(String(format: "%.2f", book.estimatedPrice))")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.green)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(.tertiarySystemGroupedBackground))
        )
    }
}

// MARK: - Data Models

struct VendorGroup: Identifiable, Codable {
    let vendor: String
    let bookCount: Int
    let totalValue: Double
    let books: [VendorBook]

    var id: String { vendor }

    enum CodingKeys: String, CodingKey {
        case vendor
        case bookCount = "book_count"
        case totalValue = "total_value"
        case books
    }
}

struct VendorBook: Codable {
    let isbn: String
    let title: String
    let authors: [String]?
    let thumbnail: String?
    let estimatedPrice: Double
    let condition: String

    enum CodingKeys: String, CodingKey {
        case isbn
        case title
        case authors
        case thumbnail
        case estimatedPrice = "estimated_price"
        case condition
    }
}

// MARK: - API Extension

extension BookAPI {
    static func getVendorGroups() async throws -> [VendorGroup] {
        let url = BookAPI.baseURL.appendingPathComponent("/api/books/grouped_by_vendor")

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }

        let decoder = JSONDecoder()
        let groups = try decoder.decode([VendorGroup].self, from: data)
        return groups
    }
}

// MARK: - Preview

#Preview {
    VendorsTabView()
}
