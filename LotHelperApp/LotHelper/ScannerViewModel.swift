import SwiftUI
import SwiftData
import Combine
import CoreLocation

@MainActor
class ScannerViewModel: ObservableObject {
    // MARK: - Published State
    @Published var isScanning = true
    @Published var scannedCode: String?
    @Published var book: BookInfo?
    @Published var evaluation: BookEvaluationRecord?
    @Published var isLoading = false
    @Published var isLoadingEvaluation = false
    @Published var errorMessage: String?
    
    // Input State
    @Published var inputMode: ScannerInputMode = .camera
    @Published var textInput: String = ""
    @Published var useHiddenScanner = false
    @Published var isTextFieldFocused = false
    @Published var forceKeyboardVisible = false
    
    // Attributes State
    @Published var showAttributesSheet = false
    @Published var showPricePickerSheet = false
    @Published var bookAttributes = BookAttributes(defaultCondition: "Good")
    @Published var persistentPurchasePrice: Double = 0.0 {
        didSet {
            bookAttributes.purchasePrice = persistentPurchasePrice
        }
    }
    
    // Interactive Attributes
    @Published var selectedCondition: String = "Good"
    @Published var isHardcover: Bool = false
    @Published var isPaperback: Bool = false
    @Published var isMassMarket: Bool = false
    @Published var isSigned: Bool = false
    @Published var isFirstEdition: Bool = false
    @Published var dynamicEstimate: EstimatePriceResponse?
    @Published var isUpdatingPrice: Bool = false
    
    // Duplicate Detection
    @Published var isDuplicate = false
    @Published var existingBookDate: Date?
    
    // Settings
    @Published var thresholds = DecisionThresholds.load()
    @Published var showThresholdsSettings = false
    
    // Dependencies
    var modelContext: ModelContext?
    let locationManager: LocationManager
    let pricing: ScannerPricingVM
    
    init(locationManager: LocationManager? = nil, pricing: ScannerPricingVM? = nil) {
        if let existing = locationManager {
            self.locationManager = existing
        } else {
            self.locationManager = LocationManager()
        }
        
        if let pricing = pricing {
            self.pricing = pricing
        } else {
            // Default initialization using production URL
            let baseURL = URL(string: "https://lothelper.clevergirl.app")!
            let config = TokenBrokerConfig(baseURL: baseURL, prefix: "")
            let broker = EbayTokenBroker(config: config)
            let soldAPI = SoldAPI(config: config)
            self.pricing = ScannerPricingVM(broker: broker, soldAPI: soldAPI)
        }
        
        // Load persistent purchase price if needed (could be added to UserDefaults)
    }
    
    // MARK: - Actions
    
    func handleScan(_ code: String) {
        // Implicit reject logic for previous scan
        if let existingEval = evaluation, let isbn = scannedCode {
            Task {
                let decision = makeBuyDecision(existingEval, using: thresholds)
                let location = locationManager.locationData
                let wasRecommendedBuy = decision.shouldBuy
                
                try? await BookAPI.logScan(
                    isbn: isbn,
                    decision: "REJECT",
                    locationName: location.name,
                    locationLatitude: location.latitude,
                    locationLongitude: location.longitude,
                    locationAccuracy: location.accuracy,
                    deviceId: UIDevice.current.identifierForVendor?.uuidString,
                    appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String,
                    notes: wasRecommendedBuy
                        ? "Implicit reject (scanned next - system recommended BUY)"
                        : "Implicit reject (scanned next - system recommended DON'T BUY)"
                )
            }
        }
        
        // Reset state for new scan
        isScanning = false
        if inputMode == .text {
            isTextFieldFocused = false
            useHiddenScanner = true
        } else {
            useHiddenScanner = false
        }
        
        SoundFeedback.scanDetected()
        // Haptics should be handled by View or a helper, but we can leave it out or inject a handler
        // provideHaptic(.success) 
        
        let normalizedCode = normalizeToISBN13(code)
        scannedCode = normalizedCode
        errorMessage = nil
        book = nil
        evaluation = nil
        isDuplicate = false
        existingBookDate = nil
        
        bookAttributes.purchasePrice = persistentPurchasePrice
        
        // Start fetching
        fetchPreview(for: normalizedCode)
        pricing.load(for: normalizedCode)
        submitAndEvaluate(normalizedCode)
        
        // Check for duplicates locally
        checkForDuplicate(normalizedCode)
    }
    
    func rescan() {
        scannedCode = nil
        book = nil
        evaluation = nil
        errorMessage = nil
        isScanning = true
        isDuplicate = false
        existingBookDate = nil
        
        if inputMode == .text {
            activateTextEntry()
        }
    }
    
    func refreshData() {
        guard let isbn = scannedCode else { return }
        fetchPreview(for: isbn)
        pricing.load(for: isbn)
        fetchEvaluation(for: isbn)
    }
    
    func activateTextEntry() {
        guard inputMode == .text else { return }
        useHiddenScanner = true
        textInput = ""
        isScanning = true
        // Focus handling is done in View via @FocusState binding
    }
    
    func submitTextInput() {
        let trimmed = textInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isTextFieldFocused = false
        handleScan(trimmed)
        textInput = ""
    }
    
    // MARK: - Business Logic
    
    private func normalizeToISBN13(_ isbn: String) -> String {
        let digits = isbn.filter { $0.isNumber }
        if digits.count == 13 { return digits }
        if digits.count == 10 {
            let base = "978" + digits.prefix(9)
            // Simple checksum calculation or just return as is if complex logic needed
            // For now, assuming the original view's logic is sufficient or we can copy the helper
            // Copying helper logic:
            let checksum = calculateISBN13Checksum(base)
            return base + String(checksum)
        }
        return digits
    }
    
    private func calculateISBN13Checksum(_ partial: String) -> Int {
        let digits = partial.compactMap { Int(String($0)) }
        guard digits.count == 12 else { return 0 }
        
        var sum = 0
        for (index, digit) in digits.enumerated() {
            sum += digit * (index % 2 == 0 ? 1 : 3)
        }
        
        let remainder = sum % 10
        return remainder == 0 ? 0 : 10 - remainder
    }
    
    @discardableResult
    func checkForDuplicate(_ isbn: String) -> Bool {
        guard let modelContext = modelContext else { return false }
        let descriptor = FetchDescriptor<CachedBook>(
            predicate: #Predicate { $0.isbn == isbn }
        )
        if let existing = try? modelContext.fetch(descriptor).first {
            isDuplicate = true
            existingBookDate = existing.lastUpdated
            return true
        }
        return false
    }
    
    // MARK: - API Calls
    
    private func fetchPreview(for isbn: String) {
        isLoading = true
        BookAPI.fetchBookInfo(isbn) { [weak self] info in
            guard let self = self, self.scannedCode == isbn else { return }
            self.isLoading = false
            if let info = info {
                self.book = info
            } else {
                // Don't show error yet, wait for evaluation
            }
        }
    }
    
    private func submitAndEvaluate(_ isbn: String) {
        BookAPI.postISBNWithAttributes(
            isbn,
            condition: bookAttributes.condition,
            edition: bookAttributes.editionNotes,
            coverType: bookAttributes.coverType == "Unknown" ? nil : bookAttributes.coverType,
            printing: bookAttributes.printing.isEmpty ? nil : bookAttributes.printing,
            signed: bookAttributes.signed,
            firstEdition: bookAttributes.firstEdition
        ) { [weak self] bookInfo in
            guard let self = self else { return }
            let finalIsbn = bookInfo?.isbn ?? isbn
            
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                self.fetchEvaluation(for: finalIsbn)
            }
        }
    }
    
    private func fetchEvaluation(for isbn: String) {
        isLoadingEvaluation = true
        BookAPI.fetchBookEvaluation(isbn) { [weak self] record in
            guard let self = self, self.scannedCode == isbn || (self.scannedCode != nil && record?.isbn == self.scannedCode) else { return }
            self.isLoadingEvaluation = false
            
            if let record = record {
                self.evaluation = record
                self.initializeAttributesFromMetadata(record)
                
                // Update book info if preview failed
                if self.book == nil, let metadata = record.metadata {
                    self.book = BookInfo(
                        isbn: record.isbn,
                        title: metadata.title ?? "Unknown Title",
                        author: metadata.authors?.first ?? "Unknown Author",
                        authors: metadata.authors ?? [],
                        thumbnail: metadata.thumbnail ?? ""
                    )
                }
            } else {
                self.errorMessage = "Could not evaluate book. Please try again."
            }
        }
    }
    
    // MARK: - Attribute Logic
    
    private func initializeAttributesFromMetadata(_ eval: BookEvaluationRecord) {
        selectedCondition = bookAttributes.condition
        
        let coverType = eval.metadata?.coverType?.lowercased() ?? ""
        if coverType.contains("hardcover") || coverType.contains("hardback") {
            isHardcover = true; isPaperback = false; isMassMarket = false
        } else if coverType.contains("mass market") {
            isHardcover = false; isPaperback = false; isMassMarket = true
        } else if coverType.contains("paperback") || coverType.contains("trade paperback") {
            isHardcover = false; isPaperback = true; isMassMarket = false
        } else {
            isHardcover = false; isPaperback = false; isMassMarket = false
        }
        
        isSigned = eval.metadata?.signed ?? false
        isFirstEdition = eval.metadata?.firstEdition ?? false
        
        updatePriceEstimate()
    }
    
    func updatePriceEstimate() {
        guard let isbn = scannedCode else { return }
        isUpdatingPrice = true
        
        Task {
            do {
                let response = try await BookAPI.estimatePrice(
                    isbn: isbn,
                    condition: selectedCondition,
                    isHardcover: isHardcover ? true : nil,
                    isPaperback: isPaperback ? true : nil,
                    isMassMarket: isMassMarket ? true : nil,
                    isSigned: isSigned ? true : nil,
                    isFirstEdition: isFirstEdition ? true : nil
                )
                
                await MainActor.run {
                    self.dynamicEstimate = response
                    self.isUpdatingPrice = false
                    
                    self.bookAttributes.coverType = self.isHardcover ? "Hardcover" : self.isPaperback ? "Paperback" : self.isMassMarket ? "Mass Market" : "Unknown"
                    self.bookAttributes.signed = self.isSigned
                    self.bookAttributes.firstEdition = self.isFirstEdition
                    self.bookAttributes.condition = self.selectedCondition
                }
            } catch {
                await MainActor.run {
                    self.isUpdatingPrice = false
                    // Error logging can be handled by a logger service
                }
            }
        }
    }
    
    // MARK: - Decision Logic
    
    func makeBuyDecision(_ eval: BookEvaluationRecord, using thresholds: DecisionThresholds? = nil) -> PurchaseDecision {
        let currentThresholds = thresholds ?? self.thresholds
        
        let score = eval.probabilityScore ?? 0
        let label = eval.probabilityLabel?.lowercased() ?? ""
        let amazonRank = eval.bookscouter?.amazonSalesRank
        
        let profit = calculateProfit(eval)
        let buybackNetProfit = profit.buybackProfit
        let ebayNetProfit = profit.estimatedProfit
        let amazonNetProfit = profit.amazonProfit
        
        let bestProfit = profit.bestProfit
        
        let seriesCheck = checkSeriesCompletion(eval)
        
        // Needs Review Checks
        var concerns: [String] = []
        let totalComps = (eval.market?.soldCount ?? 0) + (eval.market?.activeCount ?? 0)
        if totalComps < currentThresholds.minCompsRequired {
            if totalComps == 0 { concerns.append("No market data found") }
            else { concerns.append("Only \(totalComps) comparable listing\(totalComps == 1 ? "" : "s") found") }
        }
        
        if let buybackNet = buybackNetProfit, buybackNet > currentThresholds.minProfitAutoBuy,
           let ebayNet = ebayNetProfit, ebayNet < 0 {
            concerns.append("Conflicting: Buyback shows \(formatUSD(buybackNet)) profit but eBay predicts \(formatUSD(abs(ebayNet))) loss")
        }
        
        if let tts = eval.timeToSellDays, tts > currentThresholds.maxSlowMovingTTS,
           let netProfit = bestProfit, netProfit < currentThresholds.minProfitSlowMoving {
            concerns.append("Slow velocity (~\(tts) days) + thin margin (\(formatUSD(netProfit)))")
        }
        
        if score < currentThresholds.lowConfidenceThreshold, let netProfit = bestProfit, netProfit < currentThresholds.minProfitUncertainty {
            concerns.append("Low confidence (score \(Int(score))) + minimal profit (\(formatUSD(netProfit)))")
        }
        
        if currentThresholds.requireProfitData && bestProfit == nil && score < currentThresholds.minConfidenceAutoBuy {
            concerns.append("No pricing data + moderate confidence")
        }
        
        if !concerns.isEmpty {
            let summary = concerns.count == 1 ? concerns[0] : "\(concerns.count) concerns flagged for review"
            return .needsReview(reason: summary, concerns: concerns)
        }
        
        // Rule 1: Buyback
        if let buybackNet = buybackNetProfit, buybackNet > 0 {
            let vendorName = eval.bookscouter?.bestVendor ?? "vendor"
            if seriesCheck.isPartOfSeries, let series = seriesCheck.seriesName {
                return .buy(reason: "Guaranteed \(formatUSD(buybackNet)) via \(vendorName) + Completes \(series) series")
            }
            return .buy(reason: "Guaranteed \(formatUSD(buybackNet)) profit via \(vendorName)")
        }
        
        // Rule 1.5: Series
        if seriesCheck.isPartOfSeries, let series = seriesCheck.seriesName {
            let booksWeHave = seriesCheck.booksInSeries
            if let netProfit = bestProfit, netProfit >= 3.0 && score >= 50 {
                return .buy(reason: "Series: \(series) (\(booksWeHave) books) + \(formatUSD(netProfit)) profit")
            }
            if booksWeHave >= 3, let netProfit = bestProfit, netProfit >= 1.0 {
                return .buy(reason: "Near-complete series: \(series) (\(booksWeHave) books) + \(formatUSD(netProfit))")
            }
            if booksWeHave >= 3, let netProfit = bestProfit, netProfit >= -2.0 && score >= 60 {
                return .buy(reason: "Complete series: \(series) (\(booksWeHave) books) - strategic buy")
            }
        }
        
        // Rule 2: Strong Profit
        let strongProfitThreshold = currentThresholds.minProfitAutoBuy * 2
        if let maxProfit = bestProfit, maxProfit >= strongProfitThreshold {
            var platform = "eBay"
            if let amz = amazonNetProfit, amz == maxProfit { platform = "Amazon" }
            
            if label.contains("high") || score >= 60 {
                return .buy(reason: "Strong: \(formatUSD(maxProfit)) net via \(platform)")
            }
            return .buy(reason: "Net profit \(formatUSD(maxProfit)) via \(platform)")
        }
        
        // Rule 3: Minimum Profit
        if let maxProfit = bestProfit, maxProfit >= currentThresholds.minProfitAutoBuy {
            var platform = "eBay"
            if let amz = amazonNetProfit, amz == maxProfit { platform = "Amazon" }
            
            if label.contains("high") || score >= 70 {
                return .buy(reason: "Good confidence + \(formatUSD(maxProfit)) via \(platform)")
            }
            if let rank = amazonRank, rank < 100000 {
                return .buy(reason: "Fast-moving + \(formatUSD(maxProfit)) via \(platform)")
            }
            return .skip(reason: "Only \(formatUSD(maxProfit)) profit - needs higher confidence")
        }
        
        // Rule 4: Small Profit
        if let maxProfit = bestProfit, maxProfit > 0 {
            if label.contains("high") && score >= 80 {
                return .buy(reason: "Very high confidence offsets low margin")
            }
            return .skip(reason: "Net profit only \(formatUSD(maxProfit)) - too thin")
        }
        
        // Rule 5: Loss
        if let maxProfit = bestProfit, maxProfit <= 0 {
            return .skip(reason: "Would lose \(formatUSD(abs(maxProfit))) after fees")
        }
        
        // Rule 6: No Pricing
        let veryHighConfidenceThreshold = currentThresholds.minConfidenceAutoBuy + 30
        if label.contains("high") && score >= veryHighConfidenceThreshold {
            return .buy(reason: "Very high confidence but verify pricing")
        }
        
        return .skip(reason: "Insufficient profit margin or confidence")
    }
    
    func calculateProfit(_ eval: BookEvaluationRecord) -> ProfitBreakdown {
        let purchasePrice = bookAttributes.purchasePrice
        
        var salePrice: Double?
        if let liveMedian = pricing.currentSummary?.median, liveMedian > 0 {
            salePrice = liveMedian
        } else if let backendEstimate = eval.estimatedPrice {
            salePrice = backendEstimate
        }
        
        var estimatedProfit: Double?
        var ebayBreakdown: Double?
        if let price = salePrice {
            let fees = price * 0.1325 + 0.30
            estimatedProfit = price - fees - purchasePrice
            ebayBreakdown = fees
        }
        
        var amazonProfit: Double?
        var amazonBreakdown: Double?
        var amazonPrice: Double?
        if let amzPrice = eval.bookscouter?.amazonLowestPrice, amzPrice > 0 {
            amazonPrice = amzPrice
            let fees = amzPrice * 0.15 + 1.80
            amazonProfit = amzPrice - fees - purchasePrice
            amazonBreakdown = fees
        }
        
        let buybackProfit = (eval.bookscouter?.bestPrice ?? 0) - purchasePrice
        
        return ProfitBreakdown(
            estimatedProfit: estimatedProfit,
            buybackProfit: buybackProfit > 0 ? buybackProfit : nil,
            amazonProfit: amazonProfit,
            ebayBreakdown: ebayBreakdown,
            amazonBreakdown: amazonBreakdown,
            salePrice: salePrice,
            amazonPrice: amazonPrice
        )
    }
    
    // MARK: - Series Logic (Simplified for ViewModel)
    
    func checkSeriesCompletion(_ eval: BookEvaluationRecord) -> (
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
        
        if let modelContext = modelContext {
            let descriptor = FetchDescriptor<CachedBook>(
                predicate: #Predicate { book in
                    book.seriesName == seriesName && book.isbn != eval.isbn
                },
                sortBy: [SortDescriptor(\.lastUpdated, order: .reverse)]
            )
            
            if let existingBooks = try? modelContext.fetch(descriptor) {
                for book in existingBooks {
                    previousScans.append(PreviousSeriesScan(
                        isbn: book.isbn,
                        title: book.title,
                        seriesIndex: book.seriesIndex.map(String.init),
                        scannedAt: book.lastUpdated,
                        locationName: nil,
                        decision: "ACCEPTED",
                        estimatedPrice: book.estimatedPrice
                    ))
                }
            }
            
            // Check active lots
            let lotDescriptor = FetchDescriptor<CachedLot>(
                predicate: #Predicate { lot in
                    lot.canonicalSeries == seriesName || lot.seriesName == seriesName
                }
            )
            
            if let lots = try? modelContext.fetch(lotDescriptor), !lots.isEmpty {
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
        }
        
        let isPartOfSeries = !previousScans.isEmpty
        return (isPartOfSeries, seriesName, previousScans.count, previousScans, nil, nil)
    }
    
    // MARK: - Formatting Helpers
    
    func formatUSD(_ x: Double) -> String {
        if #available(iOS 15.0, *) {
            return x.formatted(.currency(code: "USD"))
        } else {
            let f = NumberFormatter()
            f.numberStyle = .currency
            f.currencyCode = "USD"
            return f.string(from: x as NSNumber) ?? "$\(x)"
        }
    }
    
    // MARK: - Accept/Reject
    
    func acceptAndContinue() {
        guard let eval = evaluation, let modelContext = modelContext else { return }
        
        Task {
            let location = locationManager.locationData
            
            // Log scan as ACCEPTED
            try? await BookAPI.logScan(
                isbn: eval.isbn,
                decision: "ACCEPTED",
                locationName: location.name,
                locationLatitude: location.latitude,
                locationLongitude: location.longitude,
                locationAccuracy: location.accuracy,
                deviceId: UIDevice.current.identifierForVendor?.uuidString,
                appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
            )
            
            // Save to local database
            let cachedBook = CachedBook(from: eval)
            modelContext.insert(cachedBook)
            
            // Play success sound
            SoundFeedback.success()
            
            // Reset for next scan
            await MainActor.run {
                rescan()
            }
        }
    }
    
    func reject() {
        guard let eval = evaluation else { return }
        
        Task {
            let location = locationManager.locationData
            
            // Log scan as REJECTED
            try? await BookAPI.logScan(
                isbn: eval.isbn,
                decision: "REJECT",
                locationName: location.name,
                locationLatitude: location.latitude,
                locationLongitude: location.longitude,
                locationAccuracy: location.accuracy,
                deviceId: UIDevice.current.identifierForVendor?.uuidString,
                appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
            )
            
            // Play error sound (or just neutral feedback)
            // SoundFeedback.error() 
            
            // Reset for next scan
            await MainActor.run {
                rescan()
            }
        }
    }
}
