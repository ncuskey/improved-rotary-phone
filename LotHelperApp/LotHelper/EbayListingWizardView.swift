import SwiftUI

/// Main wizard container for creating eBay listings
struct EbayListingWizardView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var draft: EbayListingDraft
    @State private var currentStep: Int = 0
    @State private var isSubmitting: Bool = false
    @State private var showingError: Bool = false
    @State private var errorMessage: String = ""
    @State private var showingSuccess: Bool = false

    private let onComplete: (EbayListingResponse) -> Void

    init(book: CachedBook, onComplete: @escaping (EbayListingResponse) -> Void) {
        _draft = StateObject(wrappedValue: EbayListingDraft(book: book))
        self.onComplete = onComplete
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Progress indicator
                ProgressView(value: Double(currentStep + 1), total: Double(totalSteps))
                    .tint(.blue)
                    .padding()

                // Current step view
                TabView(selection: $currentStep) {
                    ForEach(0..<totalSteps, id: \.self) { step in
                        stepView(for: step)
                            .tag(step)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
                .disabled(isSubmitting)

                // Navigation buttons
                HStack(spacing: 16) {
                    if currentStep > 0 {
                        Button {
                            withAnimation {
                                currentStep -= 1
                            }
                        } label: {
                            Label("Back", systemImage: "chevron.left")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(isSubmitting)
                    }

                    if currentStep < totalSteps - 1 {
                        Button {
                            withAnimation {
                                currentStep += 1
                            }
                        } label: {
                            Label("Next", systemImage: "chevron.right")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!canProceed || isSubmitting)
                    } else {
                        Button {
                            Task {
                                await submitListing()
                            }
                        } label: {
                            if isSubmitting {
                                ProgressView()
                                    .frame(maxWidth: .infinity)
                            } else {
                                Label("Create Listing", systemImage: "checkmark.circle.fill")
                                    .frame(maxWidth: .infinity)
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!draft.isValid || isSubmitting)
                    }
                }
                .padding()
            }
            .navigationTitle("List to eBay")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                    .disabled(isSubmitting)
                }
            }
            .alert("Error", isPresented: $showingError) {
                Button("OK", role: .cancel) { }
            } message: {
                Text(errorMessage)
            }
            .sheet(isPresented: $showingSuccess) {
                ListingSuccessView(response: nil)
            }
        }
    }

    // MARK: - Step Views

    @ViewBuilder
    private func stepView(for step: Int) -> some View {
        switch step {
        case 0:
            ConditionFeaturesStepView(draft: draft)
        case 1:
            FormatLanguageStepView(draft: draft)
        case 2:
            PriceStepView(draft: draft)
        case 3:
            ReviewConfirmStepView(draft: draft)
        case 4:
            FinalReviewEditStepView(draft: draft, onNavigateToStep: { step in
                withAnimation {
                    currentStep = step
                }
            })
        default:
            Text("Unknown step")
        }
    }

    // MARK: - Computed Properties

    private var totalSteps: Int {
        5  // Condition/Features, Format/Language, Price, Preview, Final Review & Edit
    }

    private var canProceed: Bool {
        switch currentStep {
        case 0:
            return !draft.condition.isEmpty  // Condition is required
        case 1:
            return !draft.format.isEmpty && !draft.language.isEmpty
        case 2:
            return draft.price > 0  // Price must be set
        case 3:
            return true  // Review step, always can proceed
        case 4:
            return draft.isValid  // Final validation before submit
        default:
            return false
        }
    }

    // MARK: - Actions

    private func submitListing() async {
        isSubmitting = true
        errorMessage = ""

        do {
            let response = try await BookAPI.shared.createEbayListing(draft: draft)

            await MainActor.run {
                isSubmitting = false
                onComplete(response)
                dismiss()
            }
        } catch {
            await MainActor.run {
                isSubmitting = false
                errorMessage = error.localizedDescription
                showingError = true
            }
        }
    }
}

// MARK: - Step 1: Condition & Features

struct ConditionFeaturesStepView: View {
    @ObservedObject var draft: EbayListingDraft

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Step 1 of 5")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Condition & Features")
                        .font(.title2)
                        .fontWeight(.bold)
                    Text("Describe your book's condition and special features")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                // Book preview
                HStack(spacing: 12) {
                    if let thumbnail = draft.thumbnail, let url = URL(string: thumbnail) {
                        AsyncImage(url: url) { image in
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                        } placeholder: {
                            Color.gray.opacity(0.2)
                        }
                        .frame(width: 60, height: 90)
                        .cornerRadius(4)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        Text(draft.title)
                            .font(.headline)
                            .lineLimit(2)
                        if let author = draft.author {
                            Text(author)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)

                Divider()

                // Condition
                VStack(alignment: .leading, spacing: 8) {
                    Text("Condition")
                        .font(.headline)
                    Picker("Condition", selection: $draft.condition) {
                        ForEach(EbayListingDraft.conditions, id: \.self) { condition in
                            Text(condition).tag(condition)
                        }
                    }
                    .pickerStyle(.segmented)

                    conditionDescription
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.top, 4)
                }

                Divider()

                // Edition Features
                VStack(alignment: .leading, spacing: 12) {
                    Text("Edition Features")
                        .font(.headline)

                    FeatureToggle(
                        title: "First Edition",
                        description: "First published version of the book",
                        icon: "1.circle.fill",
                        isOn: $draft.isFirstEdition
                    )

                    FeatureToggle(
                        title: "First Printing",
                        description: "First print run of this edition",
                        icon: "printer.fill",
                        isOn: $draft.isFirstPrinting
                    )

                    FeatureToggle(
                        title: "Limited Edition",
                        description: "Limited release or special edition",
                        icon: "star.circle.fill",
                        isOn: $draft.isLimitedEdition
                    )

                    FeatureToggle(
                        title: "Book Club Edition",
                        description: "Book club release",
                        icon: "person.3.fill",
                        isOn: $draft.isBookClubEdition
                    )
                }

                Divider()

                // Condition Features
                VStack(alignment: .leading, spacing: 12) {
                    Text("Condition Features")
                        .font(.headline)

                    FeatureToggle(
                        title: "Dust Jacket",
                        description: "Book has original dust jacket",
                        icon: "book.closed",
                        isOn: $draft.hasDustJacket
                    )

                    FeatureToggle(
                        title: "Signed",
                        description: "Signed or autographed by author",
                        icon: "signature",
                        isOn: $draft.isSigned
                    )

                    FeatureToggle(
                        title: "Ex-Library",
                        description: "Former library book",
                        icon: "building.columns",
                        isOn: $draft.isExLibrary
                    )
                }

                Divider()

                // Content Features
                VStack(alignment: .leading, spacing: 12) {
                    Text("Content Features")
                        .font(.headline)

                    FeatureToggle(
                        title: "Illustrated",
                        description: "Contains illustrations",
                        icon: "photo.fill",
                        isOn: $draft.isIllustrated
                    )

                    FeatureToggle(
                        title: "Large Print",
                        description: "Large print edition",
                        icon: "textformat.size",
                        isOn: $draft.isLargePrint
                    )
                }

                Divider()

                // Custom Features
                VStack(alignment: .leading, spacing: 12) {
                    Text("Custom Features (Optional)")
                        .font(.headline)
                    Text("Add details buyers search for to improve discoverability")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    TextField("e.g., 'Autographed by Stephen King'", text: $draft.customFeatures)
                        .textFieldStyle(.roundedBorder)

                    Text("💡 Tip: Include author name, inscriptions, or special features")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Divider()

                // Quantity
                VStack(alignment: .leading, spacing: 8) {
                    Text("Quantity")
                        .font(.headline)
                    Stepper("\(draft.quantity) \(draft.quantity == 1 ? "copy" : "copies")",
                           value: $draft.quantity,
                           in: 1...99)
                }
            }
            .padding()
        }
    }

    @ViewBuilder
    private var conditionDescription: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .top, spacing: 4) {
                Text("eBay:")
                    .fontWeight(.semibold)
                    .foregroundColor(.blue)

                switch draft.condition {
                case "Brand New":
                    Text("A new, unread, unused book in perfect condition with no missing or damaged pages.")
                case "Like New":
                    Text("A book that looks new but has been read. Cover has no visible wear. No missing or damaged pages, no creases, tears, underlining, or writing.")
                case "Very Good":
                    Text("A book that does not look new but is in excellent condition. No obvious damage to cover. No missing or damaged pages, no creases, tears, underlining, or writing.")
                case "Good":
                    Text("The book has been read but is in good condition. Very minimal damage to cover. Minimal pencil underlining OK, but no highlighting or writing in margins. No missing pages.")
                case "Acceptable":
                    Text("A book with obvious wear. May have damage to cover or binding. Possible writing, underlining, and highlighting, but no missing pages.")
                default:
                    Text("")
                }
            }
        }
        .padding(12)
        .background(Color.blue.opacity(0.05))
        .cornerRadius(8)
    }
}

// MARK: - Step 2: Format & Language

struct FormatLanguageStepView: View {
    @ObservedObject var draft: EbayListingDraft

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Step 2 of 5")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Format & Language")
                        .font(.title2)
                        .fontWeight(.bold)
                }

                Divider()

                // Format
                VStack(alignment: .leading, spacing: 12) {
                    Text("Book Format")
                        .font(.headline)

                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 100))], spacing: 12) {
                        ForEach(EbayListingDraft.formats, id: \.self) { format in
                            Button {
                                draft.format = format
                            } label: {
                                Text(format)
                                    .font(.subheadline)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .frame(maxWidth: .infinity)
                                    .background(draft.format == format ? Color.blue : Color(.systemGray6))
                                    .foregroundColor(draft.format == format ? .white : .primary)
                                    .cornerRadius(8)
                            }
                        }
                    }
                }

                Divider()

                // Language
                VStack(alignment: .leading, spacing: 12) {
                    Text("Language")
                        .font(.headline)

                    Picker("Language", selection: $draft.language) {
                        ForEach(EbayListingDraft.languages, id: \.self) { language in
                            Text(language).tag(language)
                        }
                    }
                    .pickerStyle(.wheel)
                    .frame(height: 120)
                }
            }
            .padding()
        }
    }
}

// MARK: - Step 3: Price

struct PriceStepView: View {
    @ObservedObject var draft: EbayListingDraft
    @State private var isLoadingPrice = false
    @State private var priceRecommendation: PriceRecommendationResponse?
    @State private var showPriceInfo = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Step 3 of 5")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Set Your Price")
                        .font(.title2)
                        .fontWeight(.bold)
                    Text("Based on your book's condition and features")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Divider()

                // Price Recommendation Card (if loaded)
                if let recommendation = priceRecommendation {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Image(systemName: "chart.line.uptrend.xyaxis")
                                .foregroundColor(.blue)
                            Text("Price Recommendation")
                                .font(.headline)
                        }

                        Text("$\(String(format: "%.2f", recommendation.recommendedPrice))")
                            .font(.system(size: 36, weight: .bold, design: .rounded))
                            .foregroundColor(.blue)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("\(recommendation.source)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text("Based on \(recommendation.compsCount) comparable listings")
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            if !recommendation.featuresMatched.isEmpty {
                                Text("Features: \(recommendation.featuresMatched.joined(separator: ", "))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }

                            HStack(spacing: 4) {
                                Text("Range: $\(String(format: "%.2f", recommendation.priceRangeMin)) - $\(String(format: "%.2f", recommendation.priceRangeMax))")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding()
                    .background(Color.blue.opacity(0.05))
                    .cornerRadius(12)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.blue.opacity(0.3), lineWidth: 1)
                    )
                }

                // Price Input
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("Listing Price")
                            .font(.headline)
                        Spacer()
                        if isLoadingPrice {
                            ProgressView()
                                .progressViewStyle(.circular)
                                .scaleEffect(0.8)
                        }
                    }

                    TextField("Enter price", value: $draft.price, format: .currency(code: "USD"))
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.decimalPad)
                        .font(.system(size: 24, weight: .medium, design: .rounded))
                        .padding()
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.blue.opacity(0.5), lineWidth: 2)
                        )

                    Button {
                        Task {
                            await loadPriceRecommendation()
                        }
                    } label: {
                        HStack {
                            Image(systemName: "arrow.clockwise")
                            Text("Get Price Recommendation")
                        }
                        .font(.subheadline)
                        .foregroundColor(.blue)
                    }
                    .disabled(isLoadingPrice)
                }

                Divider()

                // SEO Optimization toggle
                Toggle(isOn: $draft.useSEOOptimization) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("SEO-Optimized Title")
                            .font(.headline)
                        Text("Use keyword-ranked title for better search visibility")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)
            }
            .padding()
        }
        .onAppear {
            // Load price recommendation when view appears
            if draft.price == 0 && priceRecommendation == nil {
                Task {
                    await loadPriceRecommendation()
                }
            }
        }
    }

    private func loadPriceRecommendation() async {
        isLoadingPrice = true

        do {
            priceRecommendation = try await BookAPI.recommendPrice(draft: draft)

            // Auto-populate price with recommendation
            await MainActor.run {
                if draft.price == 0, let rec = priceRecommendation {
                    draft.price = Double(rec.recommendedPrice)
                }
            }
        } catch {
            print("❌ Failed to load price recommendation: \(error)")
        }

        isLoadingPrice = false
    }
}

struct FeatureToggle: View {
    let title: String
    let description: String
    let icon: String
    @Binding var isOn: Bool

    var body: some View {
        Button {
            withAnimation {
                isOn.toggle()
            }
        } label: {
            HStack(spacing: 16) {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundColor(isOn ? .blue : .secondary)
                    .frame(width: 32)

                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.headline)
                        .foregroundColor(.primary)
                    Text(description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Image(systemName: isOn ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(isOn ? .blue : .secondary)
                    .font(.title2)
            }
            .padding()
            .background(isOn ? Color.blue.opacity(0.1) : Color(.systemGray6))
            .cornerRadius(12)
        }
    }
}

// MARK: - Step 4: Review & Confirm

struct ReviewConfirmStepView: View {
    @ObservedObject var draft: EbayListingDraft
    @State private var titlePreview: TitlePreviewResponse?
    @State private var isLoadingPreview = false
    @State private var previewError: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Step 4 of 5")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Preview")
                        .font(.title2)
                        .fontWeight(.bold)
                    Text("Review the generated title and summary")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Divider()

                // Title Preview Card (if SEO enabled)
                if draft.useSEOOptimization {
                    TitlePreviewCard(
                        titlePreview: titlePreview,
                        isLoading: isLoadingPreview,
                        error: previewError,
                        onRegenerate: {
                            Task {
                                await loadTitlePreview()
                            }
                        }
                    )
                }

                // Summary
                VStack(alignment: .leading, spacing: 16) {
                    Text(draft.summary())
                        .font(.system(.body, design: .monospaced))
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(.systemGray6))
                        .cornerRadius(12)
                }

                // What happens next
                VStack(alignment: .leading, spacing: 12) {
                    Text("What happens next:")
                        .font(.headline)

                    VStack(alignment: .leading, spacing: 8) {
                        BulletPoint(text: "AI will generate an optimized title and description")
                        BulletPoint(text: "Listing will be created on eBay")
                        BulletPoint(text: "You'll receive confirmation with listing details")
                    }
                }
                .padding()
                .background(Color.blue.opacity(0.1))
                .cornerRadius(12)
            }
            .padding()
        }
        .onAppear {
            // Load title preview when view appears (if SEO enabled)
            if draft.useSEOOptimization && titlePreview == nil {
                Task {
                    await loadTitlePreview()
                }
            }
        }
    }

    private func loadTitlePreview() async {
        isLoadingPreview = true
        previewError = nil

        do {
            titlePreview = try await BookAPI.previewTitle(draft: draft)
        } catch {
            previewError = "Failed to generate title preview: \(error.localizedDescription)"
            print("❌ Title preview error: \(error)")
        }

        isLoadingPreview = false
    }
}

// MARK: - Title Preview Card

struct TitlePreviewCard: View {
    let titlePreview: TitlePreviewResponse?
    let isLoading: Bool
    let error: String?
    let onRegenerate: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack {
                Image(systemName: "doc.text.fill")
                    .foregroundColor(.blue)
                Text("Generated Title")
                    .font(.headline)
                Spacer()
            }

            if isLoading {
                // Loading state
                HStack {
                    ProgressView()
                        .progressViewStyle(.circular)
                    Text("Generating optimized title...")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.vertical, 24)
            } else if let error = error {
                // Error state
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)
                        Text("Could not generate preview")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                    }
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Button(action: onRegenerate) {
                        HStack {
                            Image(systemName: "arrow.clockwise")
                            Text("Try Again")
                        }
                        .font(.subheadline)
                        .padding(.vertical, 8)
                        .padding(.horizontal, 16)
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                    }
                    .padding(.top, 4)
                }
            } else if let preview = titlePreview {
                // Success state - show title and score
                VStack(alignment: .leading, spacing: 12) {
                    // Title display
                    Text(preview.title)
                        .font(.body)
                        .fontWeight(.medium)
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(.systemGray5))
                        .cornerRadius(8)

                    Divider()

                    // Keyword Score
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Image(systemName: "target")
                                .foregroundColor(.blue)
                            Text("Keyword Score: \(String(format: "%.1f", preview.titleScore)) / \(String(format: "%.0f", preview.maxScore))")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                            Spacer()
                            Text("\(String(format: "%.0f", preview.scorePercentage))%")
                                .font(.subheadline)
                                .fontWeight(.bold)
                                .foregroundColor(scoreColor(preview.scorePercentage))
                        }

                        // Progress bar
                        GeometryReader { geometry in
                            ZStack(alignment: .leading) {
                                // Background
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(Color(.systemGray5))
                                    .frame(height: 8)

                                // Filled portion
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(scoreColor(preview.scorePercentage))
                                    .frame(width: geometry.size.width * CGFloat(preview.scorePercentage / 100), height: 8)
                            }
                        }
                        .frame(height: 8)

                        Text("Based on 90-day sold listings")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    // Regenerate button
                    Button(action: onRegenerate) {
                        HStack {
                            Image(systemName: "arrow.clockwise")
                            Text("Regenerate Title")
                        }
                        .font(.subheadline)
                        .foregroundColor(.blue)
                    }
                }
            }
        }
        .padding()
        .background(Color.blue.opacity(0.05))
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.blue.opacity(0.3), lineWidth: 1)
        )
    }

    private func scoreColor(_ percentage: Float) -> Color {
        switch percentage {
        case 0..<50: return .red
        case 50..<70: return .orange
        case 70..<85: return .yellow
        default: return .green
        }
    }
}

struct BulletPoint: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text("•")
                .font(.headline)
            Text(text)
                .font(.subheadline)
        }
    }
}

// MARK: - Success View

struct ListingSuccessView: View {
    let response: EbayListingResponse?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 60))
                    .foregroundColor(.green)

                Text("Listing Created!")
                    .font(.title)
                    .fontWeight(.bold)

                if let response = response {
                    VStack(alignment: .leading, spacing: 12) {
                        DetailRow(label: "Title", value: response.title)
                        DetailRow(label: "Price", value: "$\(String(format: "%.2f", response.price))")
                        DetailRow(label: "Status", value: response.status.capitalized)
                        if let epid = response.epid {
                            DetailRow(label: "eBay Product ID", value: epid)
                        }
                    }
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(12)
                }

                Button("Done") {
                    dismiss()
                }
                .buttonStyle(.borderedProminent)
            }
            .padding()
            .navigationTitle("Success")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

struct DetailRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.subheadline)
                .fontWeight(.medium)
        }
    }
}

// MARK: - Step 5: Final Review & Edit

struct FinalReviewEditStepView: View {
    @ObservedObject var draft: EbayListingDraft
    let onNavigateToStep: (Int) -> Void

    @State private var isLoadingContent = false
    @State private var loadError: String?

    private let conditions = ["Brand New", "Like New", "Very Good", "Good", "Acceptable"]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Step 5 of 5")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Final Review & Edit")
                        .font(.title2)
                        .fontWeight(.bold)
                    Text("Review and edit all listing details before submission")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Divider()

                // Generated Title Section
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Label("eBay Title", systemImage: "textformat")
                            .font(.headline)
                        Spacer()
                        Button {
                            onNavigateToStep(2)
                        } label: {
                            Text("Edit Price")
                                .font(.caption)
                        }
                    }

                    if isLoadingContent {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                    } else if let error = loadError {
                        Text(error)
                            .foregroundStyle(.red)
                            .font(.caption)
                    } else {
                        TextField("Title", text: $draft.generatedTitle, axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                            .lineLimit(2...4)
                    }
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)

                // Description Section
                VStack(alignment: .leading, spacing: 12) {
                    Label("Description", systemImage: "text.alignleft")
                        .font(.headline)

                    TextEditor(text: $draft.generatedDescription)
                        .frame(minHeight: 150)
                        .padding(8)
                        .background(Color(.systemBackground))
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color(.systemGray4), lineWidth: 1)
                        )
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)

                // Price & Condition Section
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Label("Price & Condition", systemImage: "dollarsign.circle")
                            .font(.headline)
                        Spacer()
                        Button {
                            onNavigateToStep(0)
                        } label: {
                            Text("Edit Condition")
                                .font(.caption)
                        }
                    }

                    HStack(spacing: 16) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Price")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            TextField("Price", value: $draft.price, format: .currency(code: "USD"))
                                .textFieldStyle(.roundedBorder)
                                .keyboardType(.decimalPad)
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Condition")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Picker("Condition", selection: $draft.condition) {
                                ForEach(conditions, id: \.self) { condition in
                                    Text(condition).tag(condition)
                                }
                            }
                            .pickerStyle(.menu)
                            .tint(.primary)
                        }
                    }
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)

                // Item Specifics Section
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Label("Item Specifics", systemImage: "list.bullet.rectangle")
                            .font(.headline)
                        Spacer()
                        Button {
                            onNavigateToStep(1)
                        } label: {
                            Text("Edit Format")
                                .font(.caption)
                        }
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        itemSpecificRow("Format", value: draft.format)
                        itemSpecificRow("Language", value: draft.language)
                        itemSpecificRow("ISBN", value: draft.isbn)

                        if draft.isFirstEdition {
                            itemSpecificRow("Edition", value: "First Edition")
                        }
                        if draft.isSigned {
                            itemSpecificRow("Special Attributes", value: "Signed")
                        }
                        if draft.hasDustJacket {
                            itemSpecificRow("Features", value: "Dust Jacket")
                        }
                    }
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)

                // Photos Section
                if let thumbnail = draft.thumbnail, let url = URL(string: thumbnail) {
                    VStack(alignment: .leading, spacing: 12) {
                        Label("Photos", systemImage: "photo")
                            .font(.headline)

                        AsyncImage(url: url) { image in
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                        } placeholder: {
                            Color.gray.opacity(0.2)
                        }
                        .frame(maxWidth: 200, maxHeight: 300)
                        .cornerRadius(8)
                    }
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(12)
                }

                // Final notice
                VStack(alignment: .leading, spacing: 12) {
                    Text("Ready to submit?")
                        .font(.headline)

                    VStack(alignment: .leading, spacing: 8) {
                        BulletPoint(text: "Your listing will be created on eBay")
                        BulletPoint(text: "You'll receive confirmation with the listing URL")
                        BulletPoint(text: "The listing will be active immediately")
                    }
                }
                .padding()
                .background(Color.green.opacity(0.1))
                .cornerRadius(12)
            }
            .padding()
        }
        .onAppear {
            // Generate title and description if not already loaded
            if draft.generatedTitle.isEmpty {
                Task {
                    await loadGeneratedContent()
                }
            }
        }
    }

    @ViewBuilder
    private func itemSpecificRow(_ label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.caption)
                .fontWeight(.medium)
        }
    }

    private func loadGeneratedContent() async {
        isLoadingContent = true
        loadError = nil

        do {
            // Load title preview (this generates the title via AI)
            let titlePreview = try await BookAPI.previewTitle(draft: draft)

            await MainActor.run {
                draft.generatedTitle = titlePreview.title
                // Generate a basic description (you could call another API endpoint for this)
                draft.generatedDescription = generateBasicDescription()
                isLoadingContent = false
            }
        } catch {
            await MainActor.run {
                loadError = "Failed to generate content: \(error.localizedDescription)"
                // Fallback to basic title
                draft.generatedTitle = "\(draft.title) by \(draft.author ?? "Unknown")"
                draft.generatedDescription = generateBasicDescription()
                isLoadingContent = false
            }
        }
    }

    private func generateBasicDescription() -> String {
        var desc = ""
        desc += "\(draft.title)\n\n"
        if let author = draft.author {
            desc += "Author: \(author)\n"
        }
        desc += "Format: \(draft.format)\n"
        desc += "Condition: \(draft.condition)\n"
        desc += "Language: \(draft.language)\n\n"

        if draft.isFirstEdition {
            desc += "• First Edition\n"
        }
        if draft.isSigned {
            desc += "• Signed by Author\n"
        }
        if draft.hasDustJacket {
            desc += "• Includes Dust Jacket\n"
        }

        return desc
    }
}

// MARK: - Preview

#Preview {
    let metadata = BookMetadataDetails(
        title: "The Brightest Night",
        subtitle: nil,
        authors: ["Tui T. Sutherland"],
        creditedAuthors: nil,
        canonicalAuthor: "Tui T. Sutherland",
        publisher: "Scholastic",
        publishedYear: 2015,
        description: "The fifth book in the Wings of Fire series",
        thumbnail: nil,
        categories: ["Fantasy", "Children's Fiction"],
        seriesName: "Wings of Fire",
        seriesIndex: 5
    )

    let record = BookEvaluationRecord(
        isbn: "9780545349277",
        originalIsbn: nil,
        condition: "Good",
        edition: nil,
        quantity: 1,
        estimatedPrice: 12.99,
        estimatedSalePrice: 12.99,
        probabilityScore: 0.75,
        probabilityLabel: "PROFIT",
        justification: ["Popular series", "High demand"],
        metadata: metadata,
        market: nil,
        booksrun: nil,
        booksrunValueLabel: nil,
        booksrunValueRatio: nil,
        bookscouter: nil,
        bookscouterValueLabel: nil,
        bookscouterValueRatio: nil,
        rarity: nil,
        updatedAt: nil,
        createdAt: nil,
        timeToSellDays: nil,
        routingInfo: nil,
        channelRecommendation: nil
    )

    let book = CachedBook(from: record)

    EbayListingWizardView(book: book) { response in
        print("Created listing: \(response.title)")
    }
}
