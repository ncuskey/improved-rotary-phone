import SwiftUI

struct ScannerReviewView: View {
    @AppStorage("scanner.hapticsEnabled") private var hapticsEnabled = true

    @State private var isScanning = true
    @State private var scannedCode: String?
    @State private var book: BookInfo?
    @State private var isLoading = false
    @State private var errorMessage: String?

    // eBay pricing integration
    @StateObject private var pricing: ScannerPricingVM = {
        let broker = EbayTokenBroker(config: TokenBrokerConfig(
            baseURL: URL(string: "http://192.168.4.50:8787")!,
            prefix: ""
        ))
        return ScannerPricingVM(broker: broker, zip: "60601")
    }()

    var body: some View {
        GeometryReader { geo in
            VStack(spacing: 0) {
                // Top third – live camera feed
                BarcodeScannerView(isActive: $isScanning) { code in
                    handleScan(code)
                }
                .frame(height: geo.size.height / 3)
                .background(Color.black)
                .overlay(
                    ReticleView()
                        .padding(.horizontal, 28)
                )

                Spacer(minLength: geo.size.height / 3)

                // Bottom third – preview + actions
                ScrollView {
                    VStack(spacing: DS.Spacing.md) {
                        if isLoading {
                            ProgressView("Looking up \(scannedCode ?? "")…")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, DS.Spacing.sm)
                        } else if let book {
                            BookCardView(book: book.cardModel)
                        } else if let code = scannedCode {
                            fallbackCard(for: code)
                        } else {
                            idleCard
                        }

                        // eBay pricing panel
                        if scannedCode != nil {
                            pricingPanel
                        }

                        if let errorMessage {
                            Text(errorMessage)
                                .font(.footnote)
                                .foregroundStyle(.red)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        HStack(spacing: DS.Spacing.md) {
                            Button(action: rescan) {
                                Label("Rescan", systemImage: "arrow.clockwise")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.bordered)
                            .frame(minHeight: 44)

                            Button(action: accept) {
                                Label("Accept", systemImage: "checkmark")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .frame(minHeight: 44)
                            .disabled(scannedCode == nil)
                        }
                        .padding(.top, DS.Spacing.sm)
                    }
                }
                .frame(height: geo.size.height / 3)
                .padding(.horizontal)
                .padding(.bottom, DS.Spacing.xl)
                .background(DS.Color.background.opacity(0.95))
            }
            .background(DS.Color.background.ignoresSafeArea())
            .navigationTitle("Scan")
        }
    }

    // MARK: - UI builders

    @ViewBuilder
    private var pricingPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("eBay Comps")
                .font(.headline)

            if pricing.isLoading {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("Checking active listings…")
                }
                .padding(.vertical, 4)
            } else if let s = pricing.summary {
                // Stats row
                HStack(spacing: 16) {
                    statView("Count", "\(s.count)")
                    statView("$ Min", s.min, currency: "USD")
                    statView("$ Median", s.median, currency: "USD")
                    statView("$ Max", s.max, currency: "USD")
                }

                // Samples (3 cheapest)
                if !s.samples.isEmpty {
                    Divider().padding(.vertical, 6)
                    ForEach(Array(s.samples.enumerated()), id: \.offset) { _, row in
                        HStack(alignment: .top, spacing: 10) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.title).lineLimit(2)
                                    .font(.subheadline)
                                Text(row.condition.isEmpty ? "—" : row.condition)
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(formatUSD(row.delivered)).bold()
                                Text("Item \(formatUSD(row.item))  ·  Ship \(formatUSD(row.ship))")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                } else {
                    Text("No active listings for this GTIN.")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
            } else if let err = pricing.error {
                Text(err).foregroundStyle(.red).font(.footnote)
            } else {
                Text("Scan a book to see comps.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

    @ViewBuilder
    private func statView(_ title: String, _ value: Double, currency: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(formatUSD(value)).font(.subheadline).bold()
        }
    }

    @ViewBuilder
    private func statView(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.subheadline).bold()
        }
    }

    private func formatUSD(_ x: Double) -> String {
        if #available(iOS 15.0, *) {
            return x.formatted(.currency(code: "USD"))
        } else {
            let f = NumberFormatter()
            f.numberStyle = .currency
            f.currencyCode = "USD"
            return f.string(from: x as NSNumber) ?? "$\(x)"
        }
    }

    private var idleCard: some View {
        VStack(spacing: DS.Spacing.sm) {
            Image(systemName: "barcode.viewfinder")
                .font(.largeTitle)
                .foregroundStyle(DS.Color.textSecondary)
                .accessibilityHidden(true)
            Text("Ready to Scan")
                .titleStyle()
            Text("Align the barcode within the frame.")
                .subtitleStyle()
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

    private func fallbackCard(for code: String) -> some View {
        VStack(alignment: .leading, spacing: DS.Spacing.xs) {
            Text("Scanned")
                .font(.footnote)
                .foregroundStyle(DS.Color.textSecondary)
            Text(code)
                .font(.title3.weight(.semibold))
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

    // MARK: - Actions

    private func handleScan(_ code: String) {
        guard isScanning else { return }
        isScanning = false
        scannedCode = code
        errorMessage = nil
        book = nil
        fetchPreview(for: code)
        pricing.load(for: code)
        provideHaptic(.success)
    }

    private func rescan() {
        errorMessage = nil
        scannedCode = nil
        book = nil
        isLoading = false
        isScanning = true
    }

    private func accept() {
        guard let code = scannedCode else { return }
        BookAPI.postISBNToBackend(code) { _ in
            DispatchQueue.main.async {
                rescan()
            }
        }
    }

    private func fetchPreview(for isbn: String) {
        isLoading = true
        Task {
            do {
                let info = try await BookAPI.fetchBookInfo(isbn)
                await MainActor.run {
                    book = info
                    isLoading = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = "Couldn’t find details for \(isbn)."
                    isLoading = false
                    provideHaptic(.error)
                }
            }
        }
    }

    // MARK: - Haptics

    private func provideHaptic(_ type: UINotificationFeedbackGenerator.FeedbackType) {
#if canImport(UIKit)
        guard hapticsEnabled else { return }
        let generator = UINotificationFeedbackGenerator()
        generator.notificationOccurred(type)
#endif
    }
}

private extension BookInfo {
    var cardModel: BookCardView.Book {
        BookCardView.Book(
            title: title,
            author: author,
            series: subtitle ?? categories.first,
            thumbnail: thumbnail,
            score: nil
        )
    }
}

private struct ReticleView: View {
    var body: some View {
        RoundedRectangle(cornerRadius: 14)
            .strokeBorder(style: StrokeStyle(lineWidth: 2, dash: [10, 8]))
            .foregroundStyle(DS.Color.textSecondary.opacity(0.6))
            .frame(maxWidth: .infinity)
            .frame(height: 140)
            .accessibilityHidden(true)
    }
}

#Preview {
    NavigationStack {
        ScannerReviewView()
    }
}
