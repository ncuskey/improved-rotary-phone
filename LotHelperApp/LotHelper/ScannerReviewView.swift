import SwiftUI
import SwiftData
import UIKit
import CoreLocation

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
    @State private var forceKeyboardVisible = false

    // Duplicate detection
    @State private var isDuplicate = false
    @State private var existingBookDate: Date?

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

    @StateObject private var locationManager = LocationManager()

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

                            // Duplicate warning
                            if isDuplicate {
                                duplicateWarningBanner
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
                            // Series context (if applicable)
                            if let evaluation {
                                let seriesInfo = checkSeriesCompletion(evaluation)
                                if seriesInfo.isPartOfSeries {
                                    seriesContextCard(seriesInfo: seriesInfo)
                                }
                            }

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
            .overlay(alignment: .bottomTrailing) {
                // Floating action button for quick keypad access
                if scannedCode == nil || (inputMode == .text && !isScanning) {
                    Button {
                        if inputMode == .camera {
                            // Switch to text mode and show keypad
                            inputMode = .text
                        } else {
                            // Already in text mode, just activate keypad
                            activateTextEntry()
                        }
                    } label: {
                        Image(systemName: "keyboard.fill")
                            .font(.title2)
                            .foregroundStyle(.white)
                            .frame(width: 56, height: 56)
                            .background(Color.blue)
                            .clipShape(Circle())
                            .shadow(radius: 4)
                    }
                    .padding(.trailing, 20)
                    .padding(.bottom, 20)
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
            .onAppear {
                // Request location permission and start tracking
                print("📍 Location authorization status: \(locationManager.authorizationStatus.rawValue)")

                if locationManager.authorizationStatus == .notDetermined {
                    print("📍 Requesting location permission...")
                    locationManager.requestLocationPermission()
                } else if locationManager.authorizationStatus == .authorizedWhenInUse ||
                          locationManager.authorizationStatus == .authorizedAlways {
                    print("📍 Location authorized, requesting current location...")
                    locationManager.requestLocation()
                } else {
                    print("⚠️ Location denied or restricted")
                }
            }
        }
    }

    // MARK: - UI builders

    @ViewBuilder
    private func seriesContextCard(seriesInfo: (isPartOfSeries: Bool, seriesName: String?, booksInSeries: Int, previousScans: [PreviousSeriesScan], totalInSeries: Int?, missingCount: Int?)) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "books.vertical.fill")
                    .font(.title2)
                    .foregroundStyle(.purple)
                Text("Series Collection")
                    .font(.headline)
                Spacer()
            }

            if let seriesName = seriesInfo.seriesName {
                VStack(alignment: .leading, spacing: 8) {
                    Text(seriesName)
                        .font(.title3)
                        .fontWeight(.semibold)

                    HStack(spacing: 16) {
                        // Books we have
                        VStack(alignment: .leading, spacing: 4) {
                            Text("You Have")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            HStack(spacing: 4) {
                                Text("\(seriesInfo.booksInSeries)")
                                    .font(.title2)
                                    .fontWeight(.bold)
                                    .foregroundStyle(.purple)
                                Text("books")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        Divider()
                            .frame(height: 40)

                        // Strategic value indicator
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Collection Status")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(seriesInfo.booksInSeries >= 3 ? "Near Complete" : "Building")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .foregroundStyle(seriesInfo.booksInSeries >= 3 ? .green : .orange)
                        }
                    }

                    Divider()

                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            Image(systemName: "chart.line.uptrend.xyaxis")
                                .font(.caption)
                                .foregroundStyle(.green)
                            Text("Complete series sell for 2-3x individual book value")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        HStack(spacing: 6) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption)
                                .foregroundStyle(.purple)
                            Text("Lower profit margin acceptable for series completion")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    // Show previously scanned books with "go back" prompts
                    if !seriesInfo.previousScans.isEmpty {
                        Divider()

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Previously Scanned Books:")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundStyle(.secondary)

                            ForEach(seriesInfo.previousScans.prefix(5), id: \.isbn) { scan in
                                HStack(spacing: 8) {
                                    // Decision indicator
                                    Image(systemName: scan.decision == "ACCEPTED" ? "checkmark.circle.fill" : "xmark.circle")
                                        .font(.caption2)
                                        .foregroundStyle(scan.decision == "ACCEPTED" ? .green : .orange)

                                    VStack(alignment: .leading, spacing: 2) {
                                        if let title = scan.title {
                                            Text(title)
                                                .font(.caption2)
                                                .fontWeight(.medium)
                                                .lineLimit(1)
                                        }

                                        HStack(spacing: 4) {
                                            if let index = scan.seriesIndex {
                                                Text("#\(index)")
                                                    .font(.caption2)
                                                    .foregroundStyle(.purple)
                                            }

                                            Text(formatDate(scan.scannedAt))
                                                .font(.caption2)
                                                .foregroundStyle(.tertiary)

                                            if let location = scan.locationName {
                                                Text("•")
                                                    .font(.caption2)
                                                    .foregroundStyle(.tertiary)
                                                Text(location)
                                                    .font(.caption2)
                                                    .foregroundStyle(.blue)
                                            }
                                        }
                                    }

                                    Spacer()

                                    // "Go back" indicator for rejected books
                                    if scan.decision != "ACCEPTED" {
                                        Image(systemName: "arrow.uturn.backward")
                                            .font(.caption2)
                                            .foregroundStyle(.orange)
                                    }
                                }
                                .padding(.vertical, 4)
                                .padding(.horizontal, 8)
                                .background(
                                    RoundedRectangle(cornerRadius: 6)
                                        .fill(Color.secondary.opacity(0.1))
                                )
                            }

                            // Show prompt to go back for rejected books
                            let rejectedScans = seriesInfo.previousScans.filter { $0.decision != "ACCEPTED" }
                            if !rejectedScans.isEmpty {
                                HStack(spacing: 6) {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .font(.caption)
                                        .foregroundStyle(.orange)
                                    Text("Go back and get the rejected books to complete series!")
                                        .font(.caption)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(.orange)
                                }
                                .padding(.top, 4)
                            }
                        }
                    }
                }
            }
        }
        .padding()
        .background(
            LinearGradient(
                colors: [Color.purple.opacity(0.1), Color.purple.opacity(0.05)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: DS.Radius.md)
        )
        .overlay(
            RoundedRectangle(cornerRadius: DS.Radius.md)
                .stroke(Color.purple.opacity(0.3), lineWidth: 2)
        )
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }

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
                    ForceKeyboardTextField(
                        placeholder: "Type or scan ISBN...",
                        text: $textInput,
                        onSubmit: submitTextInput,
                        isFocused: $isTextFieldFocused,
                        forceKeyboard: $forceKeyboardVisible
                    )

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
        .onAppear {
            // Force keyboard to show when text input area appears
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                isTextFieldFocused = true
            }
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

        // Dismiss keyboard
        isTextFieldFocused = false

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

    private var duplicateWarningBanner: some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.title2)
                .foregroundStyle(.orange)

            VStack(alignment: .leading, spacing: 4) {
                Text("Already in Database")
                    .font(.headline)
                    .foregroundStyle(.primary)

                if let date = existingBookDate {
                    Text("Added \(formatDate(date))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Text("Consider rejecting to avoid duplicate purchase")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding()
        .background(Color.orange.opacity(0.1))
        .cornerRadius(12)
    }

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
            if profit.estimatedProfit != nil || profit.buybackProfit != nil || profit.amazonProfit != nil {
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

                    // Amazon Path
                    if let amazonPrice = profit.amazonPrice, let netProfit = profit.amazonProfit {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Image(systemName: "cart.badge.minus")
                                    .font(.caption2)
                                    .foregroundStyle(.blue)
                                Text("Amazon Route:")
                                    .font(.caption)
                                    .fontWeight(.semibold)

                                Text("(Lowest Price)")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)

                                // Show rank if available
                                if let rank = eval.bookscouter?.amazonSalesRank {
                                    Text("Rank: \(formatRank(rank))")
                                        .font(.caption2)
                                        .foregroundStyle(rankColor(for: rank))
                                }
                            }

                            HStack(spacing: 12) {
                                profitMetric("Sale", amazonPrice, color: .blue)

                                if let fees = profit.amazonBreakdown {
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

    /// Calculate Amazon fees for a given sale price
    /// Amazon charges: 15% referral fee + $1.80 closing fee for books
    /// Assumes seller-fulfilled shipping (buyer pays shipping separately)
    private func calculateAmazonFees(salePrice: Double) -> (fees: Double, netProceeds: Double) {
        let referralFeeRate = 0.15 // 15% for books category
        let closingFee = 1.80

        let referralFee = salePrice * referralFeeRate
        let totalFees = referralFee + closingFee
        let netProceeds = salePrice - totalFees

        return (fees: totalFees, netProceeds: netProceeds)
    }

    private func calculateProfit(_ eval: BookEvaluationRecord) -> (
        estimatedProfit: Double?,
        buybackProfit: Double?,
        amazonProfit: Double?,
        ebayBreakdown: Double?,
        amazonBreakdown: Double?,
        salePrice: Double?,
        amazonPrice: Double?
    ) {
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

        // Amazon net profit (after fees, seller-fulfilled)
        var amazonProfit: Double?
        var amazonBreakdown: Double?
        var amazonPrice: Double?
        if let amzPrice = eval.bookscouter?.amazonLowestPrice, amzPrice > 0 {
            amazonPrice = amzPrice
            let breakdown = calculateAmazonFees(salePrice: amzPrice)
            amazonProfit = breakdown.netProceeds - purchasePrice
            amazonBreakdown = breakdown.fees
        }

        // Buyback profit (no fees, vendor pays shipping)
        let buybackProfit = (eval.bookscouter?.bestPrice ?? 0) - purchasePrice

        return (
            estimatedProfit: estimatedProfit,
            buybackProfit: buybackProfit > 0 ? buybackProfit : nil,
            amazonProfit: amazonProfit,
            ebayBreakdown: ebayBreakdown,
            amazonBreakdown: amazonBreakdown,
            salePrice: salePrice,
            amazonPrice: amazonPrice
        )
    }

    private func refreshData() {
        guard let isbn = scannedCode else { return }
        fetchPreview(for: isbn)
        pricing.load(for: isbn)
        fetchEvaluation(for: isbn)
    }

    // MARK: - Series Completion Logic

    // MARK: - Series History Data Structure

    struct PreviousSeriesScan {
        let isbn: String
        let title: String?
        let seriesIndex: Int?
        let scannedAt: Date
        let locationName: String?
        let decision: String?
        let estimatedPrice: Double?
    }

    /// Check if this book is part of a series we've previously encountered
    /// This includes both accepted books AND rejected scans
    private func checkSeriesCompletion(_ eval: BookEvaluationRecord) -> (
        isPartOfSeries: Bool,
        seriesName: String?,
        booksInSeries: Int,
        previousScans: [PreviousSeriesScan],
        totalInSeries: Int?,
        missingCount: Int?
    ) {
        guard let seriesName = eval.metadata?.seriesName else {
            return (false, nil, 0, [], nil, nil)
        }

        var previousScans: [PreviousSeriesScan] = []

        // 1. Check accepted/saved books from database
        let descriptor = FetchDescriptor<CachedBook>(
            predicate: #Predicate { book in
                book.seriesName == seriesName
            },
            sortBy: [SortDescriptor(\.lastUpdated, order: .reverse)]
        )

        if let existingBooks = try? modelContext.fetch(descriptor) {
            for book in existingBooks {
                previousScans.append(PreviousSeriesScan(
                    isbn: book.isbn,
                    title: book.title,
                    seriesIndex: book.seriesIndex,
                    scannedAt: book.lastUpdated,
                    locationName: nil, // CachedBook doesn't store location
                    decision: "ACCEPTED",
                    estimatedPrice: book.estimatedPrice
                ))
            }
        }

        // 2. Check scan history via backend API (includes rejected scans)
        // This is an async call, so we'll do it in the background and update state
        Task {
            await checkScanHistoryForSeries(seriesName: seriesName, currentIsbn: eval.isbn)
        }

        // 3. Check active lots for this series
        let lotDescriptor = FetchDescriptor<CachedLot>(
            predicate: #Predicate { lot in
                lot.canonicalSeries == seriesName || lot.seriesName == seriesName
            }
        )

        if let lots = try? modelContext.fetch(lotDescriptor), !lots.isEmpty {
            // Series is in an active lot suggestion
            let lot = lots.first!
            var booksInLot = 0
            if let jsonString = lot.bookIsbnsJSON,
               let data = jsonString.data(using: .utf8),
               let isbns = try? JSONDecoder().decode([String].self, from: data) {
                booksInLot = isbns.count
            }

            let totalCount = max(previousScans.count, booksInLot)
            return (true, seriesName, totalCount, previousScans, nil, nil)
        }

        let isPartOfSeries = !previousScans.isEmpty
        return (isPartOfSeries, seriesName, previousScans.count, previousScans, nil, nil)
    }

    /// Check scan history for other books in this series (includes rejected scans)
    private func checkScanHistoryForSeries(seriesName: String, currentIsbn: String) async {
        // This would call the backend API to get scan history
        // For now, we'll rely on the local database check above
        // In the future, this could call:
        // BookAPI.getScanHistory() filtered by series_name
    }

    private func makeBuyDecision(_ eval: BookEvaluationRecord) -> (shouldBuy: Bool, reason: String) {
        let score = eval.probabilityScore ?? 0
        let label = eval.probabilityLabel?.lowercased() ?? ""
        let amazonRank = eval.bookscouter?.amazonSalesRank

        // Calculate all profit paths
        let profit = calculateProfit(eval)
        let buybackNetProfit = profit.buybackProfit
        let ebayNetProfit = profit.estimatedProfit
        let amazonNetProfit = profit.amazonProfit

        // Find the best profit among all exit strategies
        let bestProfit = [buybackNetProfit, ebayNetProfit, amazonNetProfit].compactMap { $0 }.max()

        // Check if this is part of an ongoing series
        let seriesCheck = checkSeriesCompletion(eval)

        // RULE 1: Buyback offer > purchase price = instant buy (guaranteed profit, no risk)
        // Check this FIRST before anything else
        if let buybackNet = buybackNetProfit, buybackNet > 0 {
            let vendorName = eval.bookscouter?.bestVendor ?? "vendor"

            // Add series context if applicable
            if seriesCheck.isPartOfSeries, let series = seriesCheck.seriesName {
                return (true, "Guaranteed \(formatUSD(buybackNet)) via \(vendorName) + Completes \(series) series")
            }

            return (true, "Guaranteed \(formatUSD(buybackNet)) profit via \(vendorName)")
        }

        // RULE 1.5: Series Completion - Buy if part of ongoing series AND profit is reasonable
        // This takes priority over general profit rules because completing series adds strategic value
        if seriesCheck.isPartOfSeries, let series = seriesCheck.seriesName {
            let booksWeHave = seriesCheck.booksInSeries

            // More lenient profit requirements for series completion
            // Accept profit as low as $3 if:
            // - Part of ongoing series (we have 1+ books)
            // - Not a loss (profit > 0)
            // - Confidence score is decent (≥50)
            if let netProfit = bestProfit, netProfit >= 3.0 && score >= 50 {
                return (true, "Series: \(series) (\(booksWeHave) books) + \(formatUSD(netProfit)) profit")
            }

            // Even more lenient: If we have 3+ books in the series and it's break-even or small profit
            if booksWeHave >= 3, let netProfit = bestProfit, netProfit >= 1.0 {
                return (true, "Near-complete series: \(series) (\(booksWeHave) books) + \(formatUSD(netProfit))")
            }

            // If series has high value, accept even small losses (up to $2) to complete
            if booksWeHave >= 3, let netProfit = bestProfit, netProfit >= -2.0 && score >= 60 {
                return (true, "Complete series: \(series) (\(booksWeHave) books) - strategic buy")
            }
        }

        // RULE 2: Net profit $10+ on any platform = strong buy
        if let maxProfit = bestProfit, maxProfit >= 10 {
            // Determine which platform offers best profit
            var platform = "eBay"
            if let amz = amazonNetProfit, amz == maxProfit {
                platform = "Amazon"
            } else if let ebay = ebayNetProfit, ebay == maxProfit {
                platform = "eBay"
            }

            if label.contains("high") || score >= 60 {
                return (true, "Strong: \(formatUSD(maxProfit)) net via \(platform)")
            }
            return (true, "Net profit \(formatUSD(maxProfit)) via \(platform)")
        }

        // RULE 3: Net profit $5-10 = conditional buy
        if let maxProfit = bestProfit, maxProfit >= 5 {
            var platform = "eBay"
            if let amz = amazonNetProfit, amz == maxProfit {
                platform = "Amazon"
            } else if let ebay = ebayNetProfit, ebay == maxProfit {
                platform = "eBay"
            }

            if label.contains("high") || score >= 70 {
                return (true, "Good confidence + \(formatUSD(maxProfit)) via \(platform)")
            }
            if let rank = amazonRank, rank < 100000 {
                return (true, "Fast-moving + \(formatUSD(maxProfit)) via \(platform)")
            }
            return (false, "Only \(formatUSD(maxProfit)) profit - needs higher confidence")
        }

        // RULE 4: Positive but small profit ($1-5)
        if let maxProfit = bestProfit, maxProfit > 0 {
            if label.contains("high") && score >= 80 {
                return (true, "Very high confidence offsets low margin")
            }
            return (false, "Net profit only \(formatUSD(maxProfit)) - too thin")
        }

        // RULE 5: No profit or loss on best channel
        if let maxProfit = bestProfit, maxProfit <= 0 {
            return (false, "Would lose \(formatUSD(abs(maxProfit))) after fees")
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

    private func formatDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
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
        // For BUY: auto-accept and add to catalog
        // For DON'T BUY: auto-reject and log
        if let existingEval = evaluation, let isbn = scannedCode {
            Task {
                let decision = makeBuyDecision(existingEval)
                let location = locationManager.locationData

                if decision.shouldBuy {
                    // Auto-accept BUY books
                    print("✅ Auto-accepting previous BUY: \(isbn)")
                    _ = try? await BookAPI.acceptBook(
                        isbn: isbn,
                        condition: bookAttributes.condition,
                        edition: bookAttributes.editionNotes,
                        locationName: location.name,
                        locationLatitude: location.latitude,
                        locationLongitude: location.longitude,
                        locationAccuracy: location.accuracy,
                        deviceId: UIDevice.current.identifierForVendor?.uuidString,
                        appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
                    )
                    // Proactively refresh Books and Lots tabs in background
                    let context = modelContext
                    Task.detached {
                        // Fetch fresh books list (includes the newly accepted book)
                        do {
                            let books = try await BookAPI.fetchAllBooks()
                            await MainActor.run {
                                CacheManager(modelContext: context).saveBooks(books)
                                UserDefaults.standard.set(Date(), forKey: "lastBooksSync")
                                print("✅ Refreshed books cache: \(books.count) books")
                            }
                        } catch {
                            print("⚠️ Failed to refresh books cache: \(error)")
                        }

                        // Fetch fresh lots list (includes updated lot compositions)
                        do {
                            let lots = try await BookAPI.fetchAllLots()
                            await MainActor.run {
                                CacheManager(modelContext: context).saveLots(lots)
                                UserDefaults.standard.set(Date(), forKey: "lastLotsSync")
                                print("✅ Refreshed lots cache: \(lots.count) lots")
                            }
                        } catch {
                            print("⚠️ Failed to refresh lots cache: \(error)")
                        }
                    }
                } else {
                    // Auto-reject DON'T BUY books
                    print("❌ Auto-rejecting previous DON'T BUY: \(isbn)")
                    try? await BookAPI.logScan(
                        isbn: isbn,
                        decision: "REJECT",
                        locationName: location.name,
                        locationLatitude: location.latitude,
                        locationLongitude: location.longitude,
                        locationAccuracy: location.accuracy,
                        deviceId: UIDevice.current.identifierForVendor?.uuidString,
                        appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String,
                        notes: "Auto-rejected (scanned next book)"
                    )
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
        isDuplicate = false
        existingBookDate = nil

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

        // Keep hidden scanner enabled for bluetooth input
        // Show visible text field for visual feedback
        useHiddenScanner = true

        // Clear any existing text
        textInput = ""

        // Show the text field
        isScanning = true

        // DON'T force focus - let hidden scanner keep focus for bluetooth
        // User can tap the text field manually if they want to type with on-screen keyboard
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
        guard let isbn = scannedCode else { return }

        SoundFeedback.success()
        provideHaptic(.success)

        // Accept the book and add to inventory
        Task {
            do {
                let location = locationManager.locationData
                _ = try await BookAPI.acceptBook(
                    isbn: isbn,
                    condition: bookAttributes.condition,
                    edition: bookAttributes.editionNotes,
                    locationName: location.name,
                    locationLatitude: location.latitude,
                    locationLongitude: location.longitude,
                    locationAccuracy: location.accuracy,
                    deviceId: UIDevice.current.identifierForVendor?.uuidString,
                    appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
                )

                // Proactively refresh both Books and Lots tabs in background
                // This ensures tabs show updated data immediately when user switches to them
                let context = modelContext
                Task.detached {
                    // Fetch fresh books list (includes the newly accepted book)
                    do {
                        let books = try await BookAPI.fetchAllBooks()
                        await MainActor.run {
                            CacheManager(modelContext: context).saveBooks(books)
                            UserDefaults.standard.set(Date(), forKey: "lastBooksSync")
                            print("✅ Refreshed books cache: \(books.count) books")
                        }
                    } catch {
                        print("⚠️ Failed to refresh books cache: \(error)")
                    }

                    // Fetch fresh lots list (includes updated lot compositions)
                    do {
                        let lots = try await BookAPI.fetchAllLots()
                        await MainActor.run {
                            CacheManager(modelContext: context).saveLots(lots)
                            UserDefaults.standard.set(Date(), forKey: "lastLotsSync")
                            print("✅ Refreshed lots cache: \(lots.count) lots")
                        }
                    } catch {
                        print("⚠️ Failed to refresh lots cache: \(error)")
                    }
                }

                await MainActor.run {
                    // Reset attributes but keep the persistent purchase price
                    bookAttributes = BookAttributes()
                    bookAttributes.purchasePrice = persistentPurchasePrice

                    rescan()
                }
            } catch {
                await MainActor.run {
                    errorMessage = "Failed to accept book: \(error.localizedDescription)"
                    SoundFeedback.error()
                    provideHaptic(.error)
                }
            }
        }
    }

    private func reject() {
        guard let isbn = scannedCode else { return }

        SoundFeedback.reject()

        // Dismiss keyboard first to allow tab switching
        isTextFieldFocused = false

        // Immediately reset UI to prepare for next scan - don't wait for API
        bookAttributes = BookAttributes()
        bookAttributes.purchasePrice = persistentPurchasePrice

        // Reset state but don't force keyboard focus
        errorMessage = nil
        scannedCode = nil
        book = nil
        evaluation = nil
        isLoading = false
        isLoadingEvaluation = false
        textInput = "" // Clear text input

        // Don't call rescan() which would re-focus keyboard
        // Just enable scanning mode without forcing focus
        if inputMode == .camera {
            isScanning = true
        }

        provideHaptic(.success)

        // Capture location data and device info before detached task
        let location = locationManager.locationData
        let deviceId = UIDevice.current.identifierForVendor?.uuidString
        let appVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String

        // Log the rejection in background - don't block UI
        // NOTE: We DON'T change the book's status in the database
        // This allows rejecting duplicate scans while keeping the original accepted book
        let context = modelContext
        Task.detached {
            do {
                try await BookAPI.logScan(
                    isbn: isbn,
                    decision: "REJECT",
                    locationName: location.name,
                    locationLatitude: location.latitude,
                    locationLongitude: location.longitude,
                    locationAccuracy: location.accuracy,
                    deviceId: deviceId,
                    appVersion: appVersion,
                    notes: "User tapped Don't Buy"
                )
                print("✅ Logged rejection for \(isbn)")

                // Refresh Books cache to remove any stale REJECT-status books
                // (When scanning new books via /isbn, they're created with status='REJECT'
                // and won't appear in Books tab query, but cache might be stale)
                do {
                    let books = try await BookAPI.fetchAllBooks()
                    await MainActor.run {
                        CacheManager(modelContext: context).saveBooks(books)
                        UserDefaults.standard.set(Date(), forKey: "lastBooksSync")
                        print("✅ Refreshed books cache after rejection: \(books.count) books")
                    }
                } catch {
                    print("⚠️ Failed to refresh books cache after rejection: \(error)")
                }
            } catch {
                print("⚠️ Failed to log rejection: \(error)")
                // Don't show error to user - logging is not critical
            }
        }
    }

    private func fetchEvaluation(for isbn: String, retryCount: Int = 0) {
        isLoadingEvaluation = true
        Task {
            do {
                // Check for duplicates BEFORE fetching evaluation
                await checkForDuplicate(isbn: isbn)

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

    private func checkForDuplicate(isbn: String) async {
        await MainActor.run {
            let descriptor = FetchDescriptor<CachedBook>(
                predicate: #Predicate { $0.isbn == isbn }
            )

            if let cachedBooks = try? modelContext.fetch(descriptor),
               let existingBook = cachedBooks.first {
                isDuplicate = true
                existingBookDate = existingBook.lastUpdated
                print("⚠️ Duplicate detected: \(isbn) (added \(existingBook.lastUpdated))")
            } else {
                isDuplicate = false
                existingBookDate = nil
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
            // Resign immediately (not async) to allow visible TextField to take focus faster
            if textField.isFirstResponder {
                textField.resignFirstResponder()
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

/// Custom UITextField that forces software keyboard even with bluetooth keyboard
class AlwaysShowKeyboardTextField: UITextField {
    // Override to force software keyboard
    override var inputAccessoryView: UIView? {
        get { super.inputAccessoryView }
        set { super.inputAccessoryView = newValue }
    }
}

/// Custom TextField that forces on-screen keyboard even when bluetooth keyboard connected
struct ForceKeyboardTextField: UIViewRepresentable {
    let placeholder: String
    @Binding var text: String
    var onSubmit: () -> Void
    var isFocused: FocusState<Bool>.Binding
    @Binding var forceKeyboard: Bool

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text, onSubmit: onSubmit, isFocused: isFocused)
    }

    func makeUIView(context: Context) -> AlwaysShowKeyboardTextField {
        let textField = AlwaysShowKeyboardTextField()
        textField.placeholder = placeholder
        textField.borderStyle = .roundedRect
        textField.keyboardType = .numberPad
        textField.autocorrectionType = .no
        textField.autocapitalizationType = .none
        textField.delegate = context.coordinator

        // This is the key: disable automatic keyboard suppression
        textField.inputAssistantItem.leadingBarButtonGroups = []
        textField.inputAssistantItem.trailingBarButtonGroups = []

        // Add toolbar with Done button above keyboard
        let toolbar = UIToolbar()
        toolbar.sizeToFit()
        let flexSpace = UIBarButtonItem(barButtonSystemItem: .flexibleSpace, target: nil, action: nil)
        let doneButton = UIBarButtonItem(title: "Done", style: .done, target: context.coordinator, action: #selector(Coordinator.doneButtonTapped))
        toolbar.items = [flexSpace, doneButton]
        textField.inputAccessoryView = toolbar

        return textField
    }

    func updateUIView(_ uiView: AlwaysShowKeyboardTextField, context: Context) {
        uiView.text = text

        // Check if we should force keyboard focus
        if forceKeyboard && !uiView.isFirstResponder {
            DispatchQueue.main.async {
                uiView.becomeFirstResponder()
                // Reload input views to ensure keyboard appears if possible
                uiView.reloadInputViews()
            }
            // Reset the trigger
            DispatchQueue.main.async {
                self.forceKeyboard = false
            }
        }

        // Handle normal focus state changes
        if isFocused.wrappedValue {
            if !uiView.isFirstResponder {
                DispatchQueue.main.async {
                    uiView.becomeFirstResponder()
                }
            }
        } else {
            if uiView.isFirstResponder {
                DispatchQueue.main.async {
                    uiView.resignFirstResponder()
                }
            }
        }
    }

    class Coordinator: NSObject, UITextFieldDelegate {
        @Binding var text: String
        var onSubmit: () -> Void
        var isFocused: FocusState<Bool>.Binding

        init(text: Binding<String>, onSubmit: @escaping () -> Void, isFocused: FocusState<Bool>.Binding) {
            _text = text
            self.onSubmit = onSubmit
            self.isFocused = isFocused
        }

        @objc func doneButtonTapped() {
            onSubmit()
        }

        func textFieldDidChangeSelection(_ textField: UITextField) {
            text = textField.text ?? ""
        }

        func textField(_ textField: UITextField, shouldChangeCharactersIn range: NSRange, replacementString string: String) -> Bool {
            // Update binding
            if let currentText = textField.text,
               let textRange = Range(range, in: currentText) {
                let updatedText = currentText.replacingCharacters(in: textRange, with: string)
                text = updatedText
            }
            return true
        }

        func textFieldShouldReturn(_ textField: UITextField) -> Bool {
            onSubmit()
            return true
        }

        func textFieldDidBeginEditing(_ textField: UITextField) {
            isFocused.wrappedValue = true
        }

        func textFieldDidEndEditing(_ textField: UITextField) {
            isFocused.wrappedValue = false
        }
    }
}

#Preview {
    NavigationStack {
        ScannerReviewView()
    }
}
