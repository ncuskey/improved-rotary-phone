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
            PriceConditionStepView(draft: draft)
        case 1:
            FormatLanguageStepView(draft: draft)
        case 2:
            SpecialFeaturesStepView(draft: draft)
        case 3:
            ReviewConfirmStepView(draft: draft)
        default:
            Text("Unknown step")
        }
    }

    // MARK: - Computed Properties

    private var totalSteps: Int {
        4  // Price/Condition, Format/Language, Features, Review
    }

    private var canProceed: Bool {
        switch currentStep {
        case 0:
            return draft.price > 0 && !draft.condition.isEmpty
        case 1:
            return !draft.format.isEmpty && !draft.language.isEmpty
        case 2:
            return true  // Features are optional
        case 3:
            return draft.isValid
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

// MARK: - Step 1: Price & Condition

struct PriceConditionStepView: View {
    @ObservedObject var draft: EbayListingDraft

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Step 1 of 4")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Price & Condition")
                        .font(.title2)
                        .fontWeight(.bold)
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

                // Price
                VStack(alignment: .leading, spacing: 8) {
                    Text("Listing Price")
                        .font(.headline)
                    TextField("Price", value: $draft.price, format: .currency(code: "USD"))
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.decimalPad)
                    Text("Suggested: $\(String(format: "%.2f", draft.price))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

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
        switch draft.condition {
        case "New":
            Text("Brand new, unread, perfect condition")
        case "Like New":
            Text("Appears unread, no visible wear")
        case "Very Good":
            Text("Minimal wear, pages clean, binding tight")
        case "Good":
            Text("Some wear, all pages intact, readable")
        case "Acceptable":
            Text("Heavily worn but complete and usable")
        default:
            Text("")
        }
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
                    Text("Step 2 of 4")
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

// MARK: - Step 3: Special Features

struct SpecialFeaturesStepView: View {
    @ObservedObject var draft: EbayListingDraft

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Step 3 of 4")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Special Features")
                        .font(.title2)
                        .fontWeight(.bold)
                    Text("Select any special features that apply")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Divider()

                // Features
                VStack(spacing: 16) {
                    FeatureToggle(
                        title: "Dust Jacket",
                        description: "Book has original dust jacket",
                        icon: "book.closed",
                        isOn: $draft.hasDustJacket
                    )

                    FeatureToggle(
                        title: "First Edition",
                        description: "First printing of the book",
                        icon: "star.fill",
                        isOn: $draft.isFirstEdition
                    )

                    FeatureToggle(
                        title: "Signed",
                        description: "Signed by the author",
                        icon: "signature",
                        isOn: $draft.isSigned
                    )

                    FeatureToggle(
                        title: "Illustrated",
                        description: "Contains illustrations",
                        icon: "photo",
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

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Step 4 of 4")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Review & Confirm")
                        .font(.title2)
                        .fontWeight(.bold)
                    Text("Double-check your listing details before submitting")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Divider()

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

// MARK: - Preview

#Preview {
    let book = CachedBook(from: BookEvaluationRecord(
        isbn: "9780545349277",
        status: "ACCEPT",
        condition: "Good",
        metadata: BookMetadata(
            title: "The Brightest Night",
            authors: ["Tui T. Sutherland"],
            thumbnail: nil
        )
    ))

    EbayListingWizardView(book: book) { response in
        print("Created listing: \(response.title)")
    }
}
