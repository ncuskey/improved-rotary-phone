import SwiftUI

struct ScannerReviewView: View {
    @AppStorage("scanner.hapticsEnabled") private var hapticsEnabled = true

    @State private var isScanning = true
    @State private var scannedCode: String?
    @State private var book: BookInfo?
    @State private var evaluation: BookEvaluationRecord?
    @State private var isLoading = false
    @State private var isLoadingEvaluation = false
    @State private var errorMessage: String?
    @State private var showAttributesSheet = false
    @State private var showPricePickerSheet = false
    @State private var bookAttributes = BookAttributes()
    @State private var persistentPurchasePrice: Double = 0.0

    // eBay pricing integration
    // Token broker accessible via Cloudflare tunnel for remote access
    @StateObject private var pricing: ScannerPricingVM = {
        let config = TokenBrokerConfig(
            baseURL: URL(string: "https://tokens.lothelper.clevergirl.app")!,
            prefix: ""
        )
        let broker = EbayTokenBroker(config: config)
        let soldAPI = SoldAPI(config: config)
        return ScannerPricingVM(broker: broker, soldAPI: soldAPI, zip: "60601")
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

                // Bottom two-thirds – preview + evaluation + actions
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

                        // Evaluation panel (probability, pricing, justification)
                        if isLoadingEvaluation {
                            evaluationLoadingPanel
                        } else if let evaluation {
                            evaluationPanel(evaluation)
                        }

                        if let errorMessage {
                            Text(errorMessage)
                                .font(.footnote)
                                .foregroundStyle(.red)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        // Show Accept/Reject after evaluation loads
                        if evaluation != nil {
                            HStack(spacing: DS.Spacing.md) {
                                Button(action: reject) {
                                    Label("Reject", systemImage: "xmark")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)
                                .tint(.red)
                                .frame(minHeight: 44)

                                Button(action: acceptAndContinue) {
                                    Label("Accept", systemImage: "checkmark")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.borderedProminent)
                                .frame(minHeight: 44)
                            }
                            .padding(.top, DS.Spacing.sm)
                        } else if scannedCode != nil && !isLoadingEvaluation {
                            // Show just Rescan if we have a scan but no evaluation yet
                            Button(action: rescan) {
                                Label("Rescan", systemImage: "arrow.clockwise")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.bordered)
                            .frame(minHeight: 44)
                            .padding(.top, DS.Spacing.sm)
                        }
                    }
                }
                .frame(height: geo.size.height * 2 / 3)
                .padding(.horizontal)
                .padding(.bottom, DS.Spacing.xl)
                .background(DS.Color.background.opacity(0.95))
            }
            .background(DS.Color.background.ignoresSafeArea())
            .navigationTitle("Scan")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { showPricePickerSheet = true }) {
                        HStack(spacing: 4) {
                            Text("Set Price")
                                .font(.subheadline)
                            if persistentPurchasePrice > 0 {
                                Text("(\(formatUSD(persistentPurchasePrice)))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            .sheet(isPresented: $showAttributesSheet) {
                BookAttributesSheet(attributes: $bookAttributes)
            }
            .sheet(isPresented: $showPricePickerSheet) {
                PricePickerSheet(selectedPrice: $persistentPurchasePrice)
            }
            .onChange(of: persistentPurchasePrice) { oldValue, newValue in
                bookAttributes.purchasePrice = newValue
            }
        }
    }

    // MARK: - UI builders

    @ViewBuilder
    private var pricingPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Mode toggle
            HStack {
                Text("eBay Comps")
                    .font(.headline)

                Spacer()

                Picker("", selection: $pricing.mode) {
                    Text("Active").tag(PricingMode.active)
                    Text(soldLabel).tag(PricingMode.sold)
                }
                .pickerStyle(.segmented)
                .frame(width: 180)
            }

            if pricing.isLoading {
                HStack(spacing: 8) {
                    ProgressView()
                    Text(pricing.mode == .active ? "Checking active listings…" : "Checking sold comps…")
                }
                .padding(.vertical, 4)
            } else if let s = pricing.currentSummary {
                // Stats row
                HStack(spacing: 16) {
                    statView("Count", "\(s.count)")
                    statView("$ Min", s.min, currency: "USD")
                    statView("$ Median", s.median, currency: "USD")
                    statView("$ Max", s.max, currency: "USD")
                }

                // Last sold date (if available)
                if pricing.mode == .sold, let lastSold = s.lastSoldDate {
                    HStack {
                        Text("Last sold:")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(formatDate(lastSold))
                            .font(.caption)
                            .bold()
                        Spacer()
                    }
                    .padding(.top, 4)
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
                                if pricing.mode == .active {
                                    Text("Item \(formatUSD(row.item))  ·  Ship \(formatUSD(row.ship))")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                        .padding(.vertical, 2)
                    }
                } else {
                    Text(pricing.mode == .active ? "No active listings for this GTIN." : "No sold history for this GTIN.")
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

    private var soldLabel: String {
        if let sold = pricing.soldSummary {
            return sold.isEstimate ? "Sold (est)" : "Sold"
        }
        return "Sold"
    }

    @ViewBuilder
    private var evaluationLoadingPanel: some View {
        VStack(spacing: 8) {
            HStack {
                ProgressView()
                Text("Analyzing book...")
                    .font(.subheadline)
            }
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

    @ViewBuilder
    private func evaluationPanel(_ eval: BookEvaluationRecord) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            // Buy/Don't Buy Recommendation
            buyRecommendation(for: eval)

            Divider()

            // Header with probability score
            HStack {
                Text("Triage Assessment")
                    .font(.headline)

                Spacer()

                if let score = eval.probabilityScore, let label = eval.probabilityLabel {
                    HStack(spacing: 6) {
                        Circle()
                            .fill(probabilityColor(for: label))
                            .frame(width: 8, height: 8)
                        Text(label)
                            .font(.subheadline)
                            .bold()
                            .foregroundStyle(probabilityColor(for: label))
                        Text("\(Int(score))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(probabilityColor(for: label).opacity(0.15), in: RoundedRectangle(cornerRadius: 12))
                }
            }

            Divider()

            // Pricing comparison
            HStack(spacing: 16) {
                if let estimated = eval.estimatedPrice {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Estimated Value")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(formatUSD(estimated))
                            .font(.title3)
                            .bold()
                    }
                }

                if let bookscouter = eval.bookscouter, bookscouter.bestPrice > 0 {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Buyback Floor")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(formatUSD(bookscouter.bestPrice))
                            .font(.title3)
                            .bold()
                            .foregroundStyle(.green)
                    }
                }
            }

            // Amazon rank and rarity badges
            HStack(spacing: 10) {
                if let rank = eval.bookscouter?.amazonSalesRank {
                    Label("\(formatRank(rank))", systemImage: "chart.line.uptrend.xyaxis")
                        .font(.caption)
                        .foregroundStyle(rankColor(for: rank))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(rankColor(for: rank).opacity(0.15), in: RoundedRectangle(cornerRadius: 6))
                }

                if let rarity = eval.rarity, rarity > 0.5 {
                    Label("Rare", systemImage: "star.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.orange.opacity(0.15), in: RoundedRectangle(cornerRadius: 6))
                }

                if let series = eval.metadata?.categories?.first, !series.isEmpty {
                    Label(series, systemImage: "books.vertical")
                        .font(.caption)
                        .foregroundStyle(.blue)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.blue.opacity(0.15), in: RoundedRectangle(cornerRadius: 6))
                        .lineLimit(1)
                }
            }

            // Justification (top 3 reasons)
            if let justification = eval.justification, !justification.isEmpty {
                Divider()
                VStack(alignment: .leading, spacing: 6) {
                    Text("Key Factors")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    ForEach(Array(justification.prefix(3)), id: \.self) { reason in
                        HStack(alignment: .top, spacing: 6) {
                            Text("•")
                                .foregroundStyle(.secondary)
                            Text(reason)
                                .font(.caption)
                                .foregroundStyle(.primary)
                        }
                    }
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

    // MARK: - Helpers

    @ViewBuilder
    private func buyRecommendation(for eval: BookEvaluationRecord) -> some View {
        let decision = makeBuyDecision(eval)
        let profit = calculateProfit(eval)

        VStack(spacing: 12) {
            HStack(spacing: 12) {
                // Icon
                Image(systemName: decision.shouldBuy ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .font(.system(size: 32))
                    .foregroundStyle(decision.shouldBuy ? .green : .red)

                VStack(alignment: .leading, spacing: 4) {
                    Text(decision.shouldBuy ? "BUY" : "DON'T BUY")
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundStyle(decision.shouldBuy ? .green : .red)

                    Text(decision.reason)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                Spacer()
            }

            // Profit display if purchase price is set
            if bookAttributes.purchasePrice > 0 {
                Divider()

                HStack(spacing: 16) {
                    profitMetric("Cost", bookAttributes.purchasePrice, color: .secondary)

                    if let estimated = eval.estimatedPrice {
                        profitMetric("Est. Sale", estimated, color: .blue)
                    }

                    if let buyback = eval.bookscouter?.bestPrice, buyback > 0 {
                        profitMetric("Buyback", buyback, color: .green)
                    }

                    Spacer()

                    // Net profit
                    if let netProfit = profit.estimatedProfit {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("Profit")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(formatUSD(netProfit))
                                .font(.title3)
                                .fontWeight(.bold)
                                .foregroundStyle(netProfit > 0 ? .green : .red)
                        }
                    }
                }
                .padding(.top, 4)
            }
        }
        .padding()
        .background(
            (decision.shouldBuy ? Color.green : Color.red)
                .opacity(0.1),
            in: RoundedRectangle(cornerRadius: 12)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(decision.shouldBuy ? Color.green : Color.red, lineWidth: 2)
        )
    }

    @ViewBuilder
    private func profitMetric(_ label: String, _ value: Double, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(formatUSD(value))
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(color)
        }
    }

    private func calculateProfit(_ eval: BookEvaluationRecord) -> (estimatedProfit: Double?, buybackProfit: Double?) {
        guard bookAttributes.purchasePrice > 0 else {
            return (nil, nil)
        }

        let estimatedProfit = (eval.estimatedPrice ?? 0) - bookAttributes.purchasePrice
        let buybackProfit = (eval.bookscouter?.bestPrice ?? 0) - bookAttributes.purchasePrice

        return (
            estimatedProfit: estimatedProfit,
            buybackProfit: buybackProfit > 0 ? buybackProfit : nil
        )
    }

    private func makeBuyDecision(_ eval: BookEvaluationRecord) -> (shouldBuy: Bool, reason: String) {
        let score = eval.probabilityScore ?? 0
        let label = eval.probabilityLabel?.lowercased() ?? ""
        let estimatedPrice = eval.estimatedPrice ?? 0
        let buybackPrice = eval.bookscouter?.bestPrice ?? 0
        let amazonRank = eval.bookscouter?.amazonSalesRank

        // Strong Buy - High confidence and good pricing
        if label.contains("strong") || (label.contains("high") && score >= 80) {
            if buybackPrice > 0 {
                return (true, "High confidence + $\(String(format: "%.2f", buybackPrice)) buyback floor")
            }
            return (true, "High probability of profitable sale")
        }

        // Conditional Buy - Worth considering
        if label.contains("worth") || (label.contains("high") && score >= 60) {
            if let rank = amazonRank, rank < 50000 {
                return (true, "Good demand (Amazon rank #\(formatRank(rank)))")
            }
            if buybackPrice > 0 {
                return (true, "Buyback option available as safety net")
            }
            if estimatedPrice >= 10 {
                return (true, "Decent estimated value (\(formatUSD(estimatedPrice)))")
            }
            return (true, "Worth buying with caution")
        }

        // Don't Buy - Risky or low confidence
        if label.contains("risky") || label.contains("pass") {
            if score < 40 {
                return (false, "Low probability score (\(Int(score)))")
            }
            if buybackPrice == 0 && estimatedPrice < 5 {
                return (false, "Low value, no buyback safety net")
            }
            return (false, "Risk outweighs potential reward")
        }

        // Default: Don't buy if we don't have clear signal
        return (false, "Insufficient confidence to recommend")
    }

    private func probabilityColor(for label: String) -> Color {
        switch label.lowercased() {
        case let s where s.contains("strong"):
            return .green
        case let s where s.contains("worth"):
            return .blue
        case let s where s.contains("risky"):
            return .orange
        default:
            return .red
        }
    }

    private func rankColor(for rank: Int) -> Color {
        if rank < 50_000 {
            return .green
        } else if rank < 100_000 {
            return .blue
        } else if rank < 300_000 {
            return .orange
        } else {
            return .secondary
        }
    }

    private func formatRank(_ rank: Int) -> String {
        if rank < 1000 {
            return "#\(rank)"
        } else if rank < 100_000 {
            return "#\(rank / 1000)k"
        } else {
            return "#\(rank / 1000)k"
        }
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

    private func formatDate(_ isoString: String) -> String {
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: isoString) else {
            return isoString  // Fallback to raw string if parsing fails
        }

        let displayFormatter = DateFormatter()
        displayFormatter.dateStyle = .medium
        displayFormatter.timeStyle = .none
        return displayFormatter.string(from: date)
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

        // Play scan detected sound
        SoundFeedback.scanDetected()
        provideHaptic(.success)

        // Normalize to ISBN-13 for eBay GTIN parameter
        let normalizedCode = normalizeToISBN13(code)
        scannedCode = normalizedCode
        errorMessage = nil
        book = nil
        evaluation = nil

        // Set purchase price from persistent value
        bookAttributes.purchasePrice = persistentPurchasePrice

        // Fetch preview and eBay comps immediately
        fetchPreview(for: normalizedCode)
        pricing.load(for: normalizedCode)

        // Submit book with attributes to backend and fetch full evaluation
        submitAndEvaluate(normalizedCode)
    }

    private func submitAndEvaluate(_ isbn: String) {
        // Submit book to backend with current attributes
        BookAPI.postISBNWithAttributes(
            isbn,
            condition: bookAttributes.condition,
            edition: bookAttributes.editionNotes,
            coverType: bookAttributes.coverType == "Unknown" ? nil : bookAttributes.coverType,
            printing: bookAttributes.printing.isEmpty ? nil : bookAttributes.printing,
            signed: bookAttributes.signed
        ) { bookInfo in
            // Use the ISBN returned by the backend (it's properly normalized)
            let finalIsbn = bookInfo?.isbn ?? isbn

            // Wait a moment for backend to complete scan processing
            // Backend needs time to fetch market data, calculate probability, etc.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                self.fetchEvaluation(for: finalIsbn)
            }
        }
    }

    /// Convert ISBN-10 to ISBN-13 if needed (eBay requires 13-digit GTIN)
    private func normalizeToISBN13(_ isbn: String) -> String {
        let digits = isbn.filter { $0.isNumber }

        // Already ISBN-13
        if digits.count == 13 {
            return digits
        }

        // Convert ISBN-10 to ISBN-13
        if digits.count == 10 {
            let base = "978" + digits.prefix(9)
            let checksum = calculateISBN13Checksum(base)
            return base + String(checksum)
        }

        // Invalid length - return as-is and let API handle error
        return digits
    }

    /// Calculate ISBN-13 check digit
    private func calculateISBN13Checksum(_ first12: String) -> Int {
        let weights = [1, 3, 1, 3, 1, 3, 1, 3, 1, 3, 1, 3]
        let sum = zip(first12, weights).reduce(0) { sum, pair in
            let digit = Int(String(pair.0)) ?? 0
            return sum + (digit * pair.1)
        }
        let remainder = sum % 10
        return remainder == 0 ? 0 : 10 - remainder
    }

    private func rescan() {
        errorMessage = nil
        scannedCode = nil
        book = nil
        evaluation = nil
        isLoading = false
        isLoadingEvaluation = false
        isScanning = true
    }

    private func acceptAndContinue() {
        // Book is already in database, just move to next scan
        SoundFeedback.success()
        provideHaptic(.success)

        // Reset attributes but keep the persistent purchase price
        bookAttributes = BookAttributes()
        bookAttributes.purchasePrice = persistentPurchasePrice

        rescan()
    }

    private func reject() {
        guard let isbn = scannedCode else { return }

        SoundFeedback.reject()

        // Delete the book from the database
        Task {
            do {
                try await BookAPI.deleteBook(isbn)
                await MainActor.run {
                    // Reset attributes but keep the persistent purchase price
                    bookAttributes = BookAttributes()
                    bookAttributes.purchasePrice = persistentPurchasePrice

                    rescan()
                    provideHaptic(.success)
                }
            } catch {
                await MainActor.run {
                    errorMessage = "Failed to reject book: \(error.localizedDescription)"
                    SoundFeedback.error()
                    provideHaptic(.error)
                }
            }
        }
    }

    private func fetchEvaluation(for isbn: String, retryCount: Int = 0) {
        isLoadingEvaluation = true
        Task {
            do {
                let eval = try await BookAPI.fetchBookEvaluation(isbn)
                await MainActor.run {
                    evaluation = eval
                    isLoadingEvaluation = false
                }
            } catch let error as BookAPIError {
                // Handle 404 - book might not be processed yet, retry
                if case .badStatus(let code, _) = error, code == 404, retryCount < 3 {
                    // Wait longer and retry (exponential backoff)
                    let delay = Double(retryCount + 1) * 1.0
                    await MainActor.run {
                        print("⏳ Book not ready yet, retrying in \(delay)s (attempt \(retryCount + 1)/3)...")
                    }
                    try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                    await MainActor.run {
                        self.fetchEvaluation(for: isbn, retryCount: retryCount + 1)
                    }
                } else {
                    await MainActor.run {
                        isLoadingEvaluation = false
                        errorMessage = "Evaluation failed: \(error.localizedDescription)"
                        print("❌ Evaluation fetch error: \(error)")
                    }
                }
            } catch {
                await MainActor.run {
                    isLoadingEvaluation = false
                    errorMessage = "Evaluation failed: \(error.localizedDescription)"
                    print("❌ Evaluation fetch error: \(error)")
                }
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
                    errorMessage = "Couldn't find details for \(isbn)."
                    isLoading = false
                    SoundFeedback.error()
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

