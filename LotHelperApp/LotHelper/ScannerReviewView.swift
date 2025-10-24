import SwiftUI
import SwiftData
import UIKit

enum ScannerInputMode: String, CaseIterable {
    case camera = "Camera"
    case text = "Text Entry"
}

struct ScannerReviewView: View {
    @AppStorage("scanner.hapticsEnabled") private var hapticsEnabled = true
    @AppStorage("scanner.inputMode") private var inputMode: ScannerInputMode = .camera

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
    @State private var textInput: String = ""
    @State private var useHiddenScanner = false
    @FocusState private var isTextFieldFocused: Bool

    // eBay pricing integration
    // Token broker accessible via Cloudflare tunnel for remote access
    @Environment(\.modelContext) private var modelContext

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
                HiddenScannerInput(
                    isActive: useHiddenScanner && inputMode == .text,
                    onSubmit: handleScan
                )
                .frame(width: 0, height: 0)

                // Show input area only while actively scanning
                if isScanning {
                    if inputMode == .camera {
                        // Camera mode - top third
                        BarcodeScannerView(isActive: $isScanning) { code in
                            handleScan(code)
                        }
                        .frame(height: geo.size.height / 3)
                        .background(Color.black)
                        .overlay(
                            ReticleView()
                                .padding(.horizontal, 28)
                        )
                    } else if inputMode == .text {
                        // Text entry mode - compact input area
                        textInputArea
                            .frame(height: 120)
                            .background(DS.Color.cardBg)
                    }
                }

                // Analysis area - uses full screen when evaluation is ready
                VStack(spacing: 0) {
                    // Top section: Accept/Reject buttons + Buy Recommendation (no scroll needed)
                    if let evaluation {
                        VStack(spacing: DS.Spacing.md) {
                            // Accept/Reject buttons at very top
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

                            // Buy recommendation immediately below buttons
                            buyRecommendation(for: evaluation)
                        }
                        .padding(.horizontal)
                        .padding(.top, DS.Spacing.md)
                        .background(DS.Color.background)
                    }

                    // Bottom section: Scrollable detailed analysis
                    ScrollView {
                        VStack(spacing: DS.Spacing.md) {
                            if inputMode == .text && !isScanning {
                                showTextFieldButton
                            }

                            if scannedCode != nil {
                                Button {
                                    refreshData()
                                } label: {
                                    Label("Refresh market data", systemImage: "arrow.clockwise")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)
                                .tint(.blue)
                            }

                            if isLoading {
                                ProgressView("Looking up \(scannedCode ?? "")…")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, DS.Spacing.sm)
                            } else if let book {
                                BookCardView(book: book.cardModel)
                            } else if let code = scannedCode {
                                fallbackCard(for: code)
                            } else if inputMode == .camera {
                                idleCard
                            }

                            // eBay pricing panel
                            if scannedCode != nil {
                                pricingPanel
                            }

                            // Evaluation panel (detailed analysis sections)
                            if isLoadingEvaluation {
                                evaluationLoadingPanel
                            } else if let evaluation {
                                detailedAnalysisPanel(evaluation)
                            }

                            if let errorMessage {
                                Text(errorMessage)
                                    .font(.footnote)
                                    .foregroundStyle(.red)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }

                            // Show Rescan if we have a scan but no evaluation yet
                            if scannedCode != nil && !isLoadingEvaluation && evaluation == nil {
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
                }
                .frame(height: isScanning ? geo.size.height * 2 / 3 : geo.size.height)
                .padding(.horizontal)
                .padding(.bottom, DS.Spacing.xl)
                .background(DS.Color.background.opacity(0.95))
            }
            .background(DS.Color.background.ignoresSafeArea())
            .navigationTitle("Scan")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Menu {
                        Picker("Input Mode", selection: $inputMode) {
                            ForEach(ScannerInputMode.allCases, id: \.self) { mode in
                                Label(
                                    mode.rawValue,
                                    systemImage: mode == .camera ? "camera.fill" : "keyboard.fill"
                                )
                                .tag(mode)
                            }
                        }
                    } label: {
                        Image(systemName: inputMode == .camera ? "camera.fill" : "keyboard.fill")
                    }
                }

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
            .onChange(of: inputMode) { oldValue, newValue in
                if newValue == .text {
                    activateTextEntry()
                } else {
                    isTextFieldFocused = false
                    useHiddenScanner = false
                }
            }
            .task {
                if inputMode == .text {
                    activateTextEntry()
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
    private var textInputArea: some View {
        VStack(spacing: 16) {
            VStack(spacing: 8) {
                HStack {
                    Image(systemName: "keyboard")
                        .foregroundStyle(.blue)
                    Text("Enter ISBN")
                        .font(.headline)
                    Spacer()
                }

                HStack(spacing: 12) {
                    TextField("Type or scan ISBN...", text: $textInput)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.numberPad)
                        .focused($isTextFieldFocused)
                        .onSubmit {
                            submitTextInput()
                        }

                    Button(action: submitTextInput) {
                        Image(systemName: "arrow.right.circle.fill")
                            .font(.title2)
                            .foregroundStyle(textInput.isEmpty ? .gray : .blue)
                    }
                    .disabled(textInput.isEmpty)
                }

                Text("Bluetooth scanner will auto-submit")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
        }
    }

    @ViewBuilder
    private var showTextFieldButton: some View {
        Button {
            activateTextEntry()
        } label: {
            Label("Show Keypad", systemImage: "keyboard")
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.bordered)
        .frame(minHeight: 44)
    }

    private func submitTextInput() {
        let trimmed = textInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        handleScan(trimmed)
        textInput = ""
    }

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
    private func detailedAnalysisPanel(_ eval: BookEvaluationRecord) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            // Confidence Score Breakdown
            scoreBreakdownSection(eval)

            // Data Sources & Pricing
            dataSourcesSection(eval)

            // Decision Factors
            decisionFactorsSection(eval)

            // Market Intelligence
            marketIntelligenceSection(eval)
        }
        .padding(.top, 8)
    }

    @ViewBuilder
    private func scoreBreakdownSection(_ eval: BookEvaluationRecord) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "chart.bar.fill")
                    .foregroundStyle(.blue)
                Text("Confidence Score")
                    .font(.headline)
                Spacer()
                if let score = eval.probabilityScore, let label = eval.probabilityLabel {
                    HStack(spacing: 6) {
                        Text("\(Int(score))")
                            .font(.title2)
                            .bold()
                            .foregroundStyle(probabilityColor(for: label))
                        Text("/ 100")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if let label = eval.probabilityLabel {
                HStack {
                    Circle()
                        .fill(probabilityColor(for: label))
                        .frame(width: 10, height: 10)
                    Text(label.uppercased() + " CONFIDENCE")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(probabilityColor(for: label))
                }
            }

            // Show how the score is calculated
            VStack(alignment: .leading, spacing: 8) {
                Text("How we calculated this:")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if let justification = eval.justification, !justification.isEmpty {
                    ForEach(Array(justification.enumerated()), id: \.offset) { index, reason in
                        HStack(alignment: .top, spacing: 8) {
                            Text("\(index + 1).")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .frame(width: 20, alignment: .leading)
                            Text(reason)
                                .font(.caption)
                                .foregroundStyle(.primary)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer()
                        }
                    }
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }

    @ViewBuilder
    private func dataSourcesSection(_ eval: BookEvaluationRecord) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "server.rack")
                    .foregroundStyle(.green)
                Text("Data Sources")
                    .font(.headline)
            }

            if let estimated = eval.estimatedPrice {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Image(systemName: "dollarsign.circle.fill")
                            .foregroundStyle(.blue)
                            .font(.caption)
                        Text("Estimated Value:")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                        Spacer()
                        Text(formatUSD(estimated))
                            .font(.title3)
                            .bold()
                    }
                    Text("Baseline from backend (eBay sold comps + condition/edition heuristics)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let market = eval.market {
                Divider()
                ebayMarketSection(market)
            }

            if let bookscouter = eval.bookscouter {
                Divider()
                bookscouterSection(
                    bookscouter,
                    valueLabel: eval.bookscouterValueLabel,
                    valueRatio: eval.bookscouterValueRatio
                )
            }

            if eval.booksrun != nil || eval.booksrunValueLabel != nil {
                Divider()
                booksRunSection(
                    eval.booksrun,
                    valueLabel: eval.booksrunValueLabel,
                    valueRatio: eval.booksrunValueRatio
                )
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }

    @ViewBuilder
    private func ebayMarketSection(_ market: EbayMarketData) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "shippingbox.fill")
                    .foregroundStyle(.orange)
                    .font(.caption)
                Text("eBay Market Snapshot")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                if let source = market.soldCompsSource {
                    Text(source == "marketplace_insights" ? "Marketplace Insights" : "Estimated")
                        .font(.caption2)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill((source == "marketplace_insights" ? Color.green : Color.orange).opacity(0.14))
                        )
                }
            }

            if market.activeCount != nil || market.soldCount != nil || market.sellThroughRate != nil {
                HStack(spacing: 12) {
                    if let active = market.activeCount {
                        metricChip("Active", "\(active)")
                    }
                    if let sold = market.soldCount {
                        metricChip("Sold (30d)", "\(sold)")
                    }
                    if let rate = market.sellThroughRate {
                        metricChip("Sell-through", rate.formatted(.percent.precision(.fractionLength(0))))
                    }
                }
            }

            if market.soldCompsMin != nil || market.soldCompsMedian != nil || market.soldCompsMax != nil {
                HStack(spacing: 12) {
                    if let min = market.soldCompsMin {
                        metricChip("Sold Min", formatUSD(min))
                    }
                    if let median = market.soldCompsMedian {
                        metricChip("Sold Median", formatUSD(median), emphasis: true)
                    }
                    if let max = market.soldCompsMax {
                        metricChip("Sold Max", formatUSD(max))
                    }
                }
            }

            if let date = market.soldCompsLastSoldDate {
                Text("Last sold on \(formatDate(date))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func bookscouterSection(
        _ bookscouter: BookScouterResult,
        valueLabel: String?,
        valueRatio: Double?
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "arrow.2.circlepath.circle.fill")
                    .foregroundStyle(.green)
                    .font(.caption)
                Text("BookScouter Buyback")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                if bookscouter.bestPrice > 0 {
                    Text(formatUSD(bookscouter.bestPrice))
                        .font(.title3)
                        .bold()
                        .foregroundStyle(.green)
                } else {
                    Text("No offers")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let label = valueLabel, let ratioText = formatRatio(valueRatio) {
                Text("Value vs. eBay: \(label) (\(ratioText))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let rank = bookscouter.amazonSalesRank {
                HStack(spacing: 6) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.caption2)
                    Text("Amazon Rank: \(formatRank(rank))")
                        .font(.caption)
                        .foregroundStyle(rankColor(for: rank))
                    if let count = bookscouter.amazonCount {
                        Text("(\(count) sellers)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            HStack(spacing: 12) {
                if let lowest = bookscouter.amazonLowestPrice, lowest > 0 {
                    metricChip("Amazon Low", formatUSD(lowest))
                }
                if let tradeIn = bookscouter.amazonTradeInPrice, tradeIn > 0 {
                    metricChip("Amazon Trade-in", formatUSD(tradeIn))
                }
            }

            if !bookscouter.offers.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Top Offers")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    ForEach(Array(bookscouter.offers.prefix(3)), id: \.vendorId) { offer in
                        HStack {
                            Text(offer.vendorName)
                                .font(.caption)
                                .fontWeight(.semibold)
                            Spacer()
                            Text(formatUSD(offer.price))
                                .font(.caption)
                                .bold()
                            if !offer.updatedAt.isEmpty {
                                Text(offer.updatedAt)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    if bookscouter.offers.count > 3 {
                        Text("+\(bookscouter.offers.count - 3) more vendors")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func booksRunSection(
        _ offer: BooksRunOffer?,
        valueLabel: String?,
        valueRatio: Double?
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "book.closed.fill")
                    .foregroundStyle(.purple)
                    .font(.caption)
                Text("BooksRun Offer")
                    .font(.subheadline)
                    .fontWeight(.semibold)
            }

            if let label = valueLabel, let ratioText = formatRatio(valueRatio) {
                Text("Value vs. eBay: \(label) (\(ratioText))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let offer {
                HStack(spacing: 12) {
                    if let cash = offer.cashPrice, cash > 0 {
                        metricChip("Cash", formatUSD(cash), emphasis: true)
                    }
                    if let credit = offer.storeCredit, credit > 0 {
                        metricChip("Store Credit", formatUSD(credit))
                    }
                }

                if let condition = offer.condition, !condition.isEmpty {
                    Text("Condition: \(condition.capitalized)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let urlString = offer.url, let url = URL(string: urlString) {
                    Link("Open BooksRun offer", destination: url)
                        .font(.caption)
                }

                if let updated = offer.updatedAt, !updated.isEmpty {
                    Text("Last updated \(updated)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("No BooksRun offer retrieved for this ISBN.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func decisionFactorsSection(_ eval: BookEvaluationRecord) -> some View {
        let decision = makeBuyDecision(eval)

        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "brain.fill")
                    .foregroundStyle(.purple)
                Text("Why \(decision.shouldBuy ? "BUY" : "DON'T BUY")?")
                    .font(.headline)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text(decision.reason)
                    .font(.subheadline)
                    .foregroundStyle(.primary)

                Divider()

                Text("Factors considered:")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                // Show key decision inputs
                VStack(alignment: .leading, spacing: 6) {
                    if let score = eval.probabilityScore {
                        decisionFactorRow("Confidence Score", "\(Int(score))/100", score >= 60 ? .green : .orange)
                    }

                    if let estimated = eval.estimatedPrice {
                        decisionFactorRow("Est. Sale Price", formatUSD(estimated), estimated >= 10 ? .blue : .secondary)
                    }

                    if let buyback = eval.bookscouter?.bestPrice {
                        decisionFactorRow("Buyback Floor", formatUSD(buyback), buyback > 0 ? .green : .secondary)
                    }

                    if let rank = eval.bookscouter?.amazonSalesRank {
                        decisionFactorRow("Amazon Demand", formatRank(rank), rankColor(for: rank))
                    }

                    if bookAttributes.purchasePrice > 0 {
                        let profit = calculateProfit(eval)
                        if let netProfit = profit.estimatedProfit {
                            decisionFactorRow("Expected Profit", formatUSD(netProfit), netProfit > 0 ? .green : .red)
                        }
                    }
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }

    @ViewBuilder
    private func decisionFactorRow(_ label: String, _ value: String, _ color: Color) -> some View {
        HStack {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(color)
        }
    }

    private func metricChip(_ title: String, _ value: String, emphasis: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.bold())
                .foregroundStyle(emphasis ? Color.blue : Color.primary)
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(emphasis ? Color.blue.opacity(0.12) : DS.Color.cardBg.opacity(0.9))
        )
    }

    private func formatRatio(_ ratio: Double?) -> String? {
        guard let ratio else { return nil }
        return ratio.formatted(.percent.precision(.fractionLength(0)))
    }

    @ViewBuilder
    private func marketIntelligenceSection(_ eval: BookEvaluationRecord) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "chart.xyaxis.line")
                    .foregroundStyle(.orange)
                Text("Market Intelligence")
                    .font(.headline)
            }

            // Rarity indicator
            if let rarity = eval.rarity {
                HStack {
                    Image(systemName: rarity > 0.5 ? "star.fill" : "star")
                        .foregroundStyle(rarity > 0.5 ? .orange : .secondary)
                    Text("Rarity Score:")
                        .font(.subheadline)
                    Spacer()
                    Text(String(format: "%.0f%%", rarity * 100))
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(rarity > 0.5 ? .orange : .secondary)
                }
                Text(rarity > 0.7 ? "Very rare - limited market activity" : rarity > 0.5 ? "Somewhat rare - niche market" : "Common availability")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.bottom, 4)
            }

            // Series/Category info
            if let categories = eval.metadata?.categories, !categories.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Image(systemName: "books.vertical.fill")
                            .foregroundStyle(.blue)
                        Text("Categories:")
                            .font(.subheadline)
                    }
                    ForEach(categories.prefix(3), id: \.self) { category in
                        Text("• \(category)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            // Author info
            if let authors = eval.metadata?.authors, !authors.isEmpty {
                HStack {
                    Image(systemName: "person.fill")
                        .foregroundStyle(.purple)
                    Text("By \(authors.joined(separator: ", "))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            // Publisher info
            if let publisher = eval.metadata?.publisher, let year = eval.metadata?.publishedYear {
                HStack {
                    Image(systemName: "building.2.fill")
                        .foregroundStyle(.gray)
                    Text("\(publisher) (\(year))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }

    private func rankDescription(for rank: Int) -> String {
        if rank < 50_000 {
            return "Bestseller"
        } else if rank < 100_000 {
            return "High demand"
        } else if rank < 300_000 {
            return "Solid demand"
        } else if rank < 500_000 {
            return "Moderate"
        } else if rank < 1_000_000 {
            return "Average"
        } else {
            return "Slow moving"
        }
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

            // Profit display (always show if we have profit data)
            if profit.estimatedProfit != nil || profit.buybackProfit != nil {
                Divider()

                VStack(spacing: 8) {
                    // eBay Path
                    if let salePrice = profit.salePrice, let netProfit = profit.estimatedProfit {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Image(systemName: "cart.fill")
                                    .font(.caption2)
                                    .foregroundStyle(.orange)
                                Text("eBay Route:")
                                    .font(.caption)
                                    .fontWeight(.semibold)

                                // Show source of price
                                if let liveMedian = pricing.currentSummary?.median, liveMedian > 0, abs(salePrice - liveMedian) < 0.01 {
                                    Text("(Live)")
                                        .font(.caption2)
                                        .foregroundStyle(.green)
                                } else {
                                    Text("(Est.)")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }

                            HStack(spacing: 12) {
                                profitMetric("Sale", salePrice, color: .blue)

                                if let fees = profit.ebayBreakdown {
                                    profitMetric("Fees", fees, color: .red, negative: true)
                                }

                                let costLabel = bookAttributes.purchasePrice > 0 ? "Cost" : "Cost (Free)"
                                profitMetric(costLabel, bookAttributes.purchasePrice, color: .secondary, negative: true)

                                Spacer()

                                VStack(alignment: .trailing, spacing: 2) {
                                    Text("Net")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text(formatUSD(netProfit))
                                        .font(.title3)
                                        .fontWeight(.bold)
                                        .foregroundStyle(netProfit > 0 ? .green : .red)
                                }
                            }
                        }
                    }

                    // Buyback Path
                    if let buyback = eval.bookscouter?.bestPrice, buyback > 0, let buybackNet = profit.buybackProfit {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Image(systemName: "arrow.2.circlepath")
                                    .font(.caption2)
                                    .foregroundStyle(.green)
                                Text("Buyback Route:")
                                    .font(.caption)
                                    .fontWeight(.semibold)

                                // Show vendor name if available
                                if let vendor = eval.bookscouter?.bestVendor {
                                    Text("(\(vendor))")
                                        .font(.caption2)
                                        .foregroundStyle(.green)
                                }
                            }

                            HStack(spacing: 12) {
                                profitMetric("Offer", buyback, color: .green)
                                let costLabel = bookAttributes.purchasePrice > 0 ? "Cost" : "Cost (Free)"
                                profitMetric(costLabel, bookAttributes.purchasePrice, color: .secondary, negative: true)

                                Spacer()

                                VStack(alignment: .trailing, spacing: 2) {
                                    Text("Net")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text(formatUSD(buybackNet))
                                        .font(.title3)
                                        .fontWeight(.bold)
                                        .foregroundStyle(buybackNet > 0 ? .green : .red)
                                }
                            }
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
    private func profitMetric(_ label: String, _ value: Double, color: Color, negative: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text((negative ? "-" : "") + formatUSD(value))
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(color)
        }
    }

    /// Calculate eBay fees for a given sale price
    /// eBay charges: 13.25% final value fee for books + $0.30 transaction fee
    /// Shipping is paid by buyer (not deducted from proceeds)
    private func calculateEbayFees(salePrice: Double) -> (fees: Double, netProceeds: Double) {
        let finalValueFeeRate = 0.1325 // 13.25% for books category
        let transactionFee = 0.30

        let finalValueFee = salePrice * finalValueFeeRate
        let totalFees = finalValueFee + transactionFee
        let netProceeds = salePrice - totalFees

        return (fees: totalFees, netProceeds: netProceeds)
    }

    private func calculateProfit(_ eval: BookEvaluationRecord) -> (estimatedProfit: Double?, buybackProfit: Double?, ebayBreakdown: Double?, salePrice: Double?) {
        // Allow $0 purchase price (free books)
        let purchasePrice = bookAttributes.purchasePrice

        // Prefer live eBay median over backend estimate
        var salePrice: Double?
        if let liveMedian = pricing.currentSummary?.median, liveMedian > 0 {
            salePrice = liveMedian
        } else if let backendEstimate = eval.estimatedPrice {
            salePrice = backendEstimate
        }

        // eBay net profit (after fees only, buyer pays shipping)
        var estimatedProfit: Double?
        var ebayBreakdown: Double?
        if let price = salePrice {
            let breakdown = calculateEbayFees(salePrice: price)
            estimatedProfit = breakdown.netProceeds - purchasePrice
            ebayBreakdown = breakdown.fees
        }

        // Buyback profit (no fees, vendor pays shipping)
        let buybackProfit = (eval.bookscouter?.bestPrice ?? 0) - purchasePrice

        return (
            estimatedProfit: estimatedProfit,
            buybackProfit: buybackProfit > 0 ? buybackProfit : nil,
            ebayBreakdown: ebayBreakdown,
            salePrice: salePrice
        )
    }

    private func refreshData() {
        guard let isbn = scannedCode else { return }
        fetchPreview(for: isbn)
        pricing.load(for: isbn)
        fetchEvaluation(for: isbn)
    }

    private func makeBuyDecision(_ eval: BookEvaluationRecord) -> (shouldBuy: Bool, reason: String) {
        let score = eval.probabilityScore ?? 0
        let label = eval.probabilityLabel?.lowercased() ?? ""
        let amazonRank = eval.bookscouter?.amazonSalesRank

        // Always calculate buyback profit if we have a buyback offer
        // If no purchase price is set, assume $0 (free book)
        var buybackNetProfit: Double?
        if let buybackOffer = eval.bookscouter?.bestPrice, buybackOffer > 0 {
            let purchasePrice = bookAttributes.purchasePrice // Use 0 if not set
            buybackNetProfit = buybackOffer - purchasePrice
        }

        // RULE 1: Buyback offer > purchase price = instant buy (guaranteed profit)
        // Check this FIRST before anything else
        if let buybackNet = buybackNetProfit, buybackNet > 0 {
            let vendorName = eval.bookscouter?.bestVendor ?? "vendor"
            return (true, "Guaranteed \(formatUSD(buybackNet)) profit via \(vendorName)")
        }

        // Calculate eBay net profit
        var ebayNetProfit: Double?
        if bookAttributes.purchasePrice > 0 {
            let profit = calculateProfit(eval)
            ebayNetProfit = profit.estimatedProfit
        } else {
            // If no purchase price set, calculate net proceeds only
            // Prefer live eBay median over backend estimate
            var salePrice: Double?
            if let liveMedian = pricing.currentSummary?.median, liveMedian > 0 {
                salePrice = liveMedian
            } else if let backendEstimate = eval.estimatedPrice {
                salePrice = backendEstimate
            }

            if let price = salePrice {
                let breakdown = calculateEbayFees(salePrice: price)
                ebayNetProfit = breakdown.netProceeds
            }
        }

        // RULE 2: Net profit $10+ on eBay = strong buy
        if let netProfit = ebayNetProfit, netProfit >= 10 {
            if label.contains("high") || score >= 60 {
                return (true, "Strong: \(formatUSD(netProfit)) net profit after fees")
            }
            return (true, "Net profit \(formatUSD(netProfit)) after eBay fees")
        }

        // RULE 3: Net profit $5-10 = conditional buy
        if let netProfit = ebayNetProfit, netProfit >= 5 {
            if label.contains("high") || score >= 70 {
                return (true, "Good confidence + \(formatUSD(netProfit)) net profit")
            }
            if let rank = amazonRank, rank < 100000 {
                return (true, "Fast-moving + \(formatUSD(netProfit)) net profit")
            }
            return (false, "Only \(formatUSD(netProfit)) profit - needs higher confidence")
        }

        // RULE 4: Positive but small profit ($1-5)
        if let netProfit = ebayNetProfit, netProfit > 0 {
            if label.contains("high") && score >= 80 {
                return (true, "Very high confidence offsets low margin")
            }
            return (false, "Net profit only \(formatUSD(netProfit)) - too thin")
        }

        // RULE 5: No profit or loss
        if let netProfit = ebayNetProfit, netProfit <= 0 {
            return (false, "Would lose \(formatUSD(abs(netProfit))) after eBay fees")
        }

        // RULE 6: No pricing data - use confidence only
        if label.contains("high") && score >= 80 {
            return (true, "Very high confidence but verify pricing")
        }

        return (false, "Insufficient profit margin or confidence")
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
        // If we have an existing evaluation (from a previous scan), handle it
        // For DON'T BUY: auto-reject and delete from database
        // For BUY: auto-accept and add to catalog
        if let existingEval = evaluation, let isbn = scannedCode {
            Task {
                let decision = makeBuyDecision(existingEval)
                if decision.shouldBuy {
                    // Auto-accept BUY books
                    print("✅ Auto-accepting previous BUY: \(isbn)")
                    // Book is already in database from scan, no action needed
                } else {
                    // Auto-reject DON'T BUY books
                    print("❌ Auto-rejecting previous DON'T BUY: \(isbn)")
                    try? await BookAPI.deleteBook(isbn)
                }
            }
        }

        // Always allow new scans (remove the isScanning guard)
        isScanning = false
        if inputMode == .text {
            isTextFieldFocused = false
            useHiddenScanner = true
        } else {
            useHiddenScanner = false
        }

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

    private func activateTextEntry() {
        guard inputMode == .text else { return }
        useHiddenScanner = false
        isScanning = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            isTextFieldFocused = true
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
        if inputMode == .text {
            activateTextEntry()
        } else {
            isScanning = true
        }
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
                    CacheManager(modelContext: modelContext).upsertBook(eval)
                    evaluation = eval
                    isLoadingEvaluation = false

                    // Play sound based on buy recommendation
                    let decision = makeBuyDecision(eval)
                    if decision.shouldBuy {
                        SoundFeedback.buyRecommendation() // Cha-ching!
                        provideHaptic(.success)
                    } else {
                        SoundFeedback.dontBuyRecommendation() // Rejection
                        provideHaptic(.warning)
                    }
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
            score: nil,
            profitPotential: nil,
            soldCompsMedian: nil,
            bestVendorPrice: nil
        )
    }
}

private struct HiddenScannerInput: UIViewRepresentable {
    var isActive: Bool
    var onSubmit: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onSubmit: onSubmit)
    }

    func makeUIView(context: Context) -> UITextField {
        let textField = UITextField(frame: .zero)
        textField.delegate = context.coordinator
        textField.autocorrectionType = .no
        textField.autocapitalizationType = .none
        textField.spellCheckingType = .no
        textField.returnKeyType = .done
        textField.enablesReturnKeyAutomatically = false
        textField.tintColor = .clear
        textField.textColor = .clear
        textField.backgroundColor = .clear

        // Prevent on-screen keyboard from appearing while still receiving hardware input.
        textField.inputView = UIView(frame: .zero)
        return textField
    }

    func updateUIView(_ textField: UITextField, context: Context) {
        if isActive {
            if !textField.isFirstResponder {
                DispatchQueue.main.async {
                    textField.becomeFirstResponder()
                }
            }
        } else {
            context.coordinator.reset()
            textField.text = ""
            if textField.isFirstResponder {
                DispatchQueue.main.async {
                    textField.resignFirstResponder()
                }
            }
        }
    }

    final class Coordinator: NSObject, UITextFieldDelegate {
        private var buffer = ""
        private let onSubmit: (String) -> Void

        init(onSubmit: @escaping (String) -> Void) {
            self.onSubmit = onSubmit
        }

        func textField(_ textField: UITextField, shouldChangeCharactersIn range: NSRange, replacementString string: String) -> Bool {
            if string.isEmpty {
                if !buffer.isEmpty {
                    buffer.removeLast()
                }
                return false
            }

            let newlineSet = CharacterSet.newlines
            let pieces = string.components(separatedBy: newlineSet)

            for (index, piece) in pieces.enumerated() {
                if !piece.isEmpty {
                    buffer.append(piece)
                }

                let isLastPiece = index == pieces.count - 1
                if !isLastPiece {
                    commitBuffer(textField)
                }
            }

            return false
        }

        func reset() {
            buffer = ""
        }

        private func commitBuffer(_ textField: UITextField) {
            let trimmed = buffer.trimmingCharacters(in: .whitespacesAndNewlines)
            buffer = ""
            textField.text = ""

            if !trimmed.isEmpty {
                onSubmit(trimmed)
            }
        }
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
