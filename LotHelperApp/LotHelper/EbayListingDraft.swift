import Foundation
import Combine

/// Represents an in-progress eBay listing being created through the wizard.
/// This is a transient model (not persisted to SwiftData) that holds the user's
/// selections as they progress through the listing creation wizard.
class EbayListingDraft: ObservableObject {
    // MARK: - Book Information (from CachedBook)

    let isbn: String
    let title: String
    let author: String?
    let thumbnail: String?
    let publishedYear: Int?

    // MARK: - Listing Details (Step 1)

    @Published var price: Double = 0.0
    @Published var condition: String = "Good"
    @Published var quantity: Int = 1

    // MARK: - Format & Language (Step 2)

    @Published var format: String = "Hardcover"
    @Published var language: String = "English"

    // MARK: - Special Features (Step 3)

    @Published var hasDustJacket: Bool = false
    @Published var isFirstEdition: Bool = false
    @Published var isFirstPrinting: Bool = false
    @Published var isSigned: Bool = false
    @Published var isIllustrated: Bool = false
    @Published var isLargePrint: Bool = false
    @Published var isExLibrary: Bool = false
    @Published var isBookClubEdition: Bool = false
    @Published var isLimitedEdition: Bool = false
    @Published var customFeatures: String = ""

    // MARK: - Advanced Options (Step 4)

    @Published var useSEOOptimization: Bool = true
    @Published var customNotes: String = ""

    // MARK: - Generated Content (for final review/edit)

    @Published var generatedTitle: String = ""
    @Published var generatedDescription: String = ""

    // MARK: - Derived State

    /// Whether an ePID was found for this book (auto-populated Item Specifics)
    @Published var hasEPID: Bool = false
    @Published var epid: String? = nil

    /// Number of wizard steps (varies based on ePID availability)
    var totalSteps: Int {
        hasEPID ? 4 : 5  // Fewer steps if ePID auto-populates details
    }

    // MARK: - Validation

    var isValid: Bool {
        price > 0 && quantity > 0 && !condition.isEmpty
    }

    // MARK: - Initialization

    init(book: CachedBook) {
        self.isbn = book.isbn
        self.title = book.title ?? "Unknown Title"
        self.author = book.canonicalAuthor
        self.thumbnail = book.thumbnail
        self.publishedYear = book.publishedYear

        // Set default price from estimated price if available
        if let estimatedPrice = book.estimatedPrice {
            self.price = estimatedPrice
        }
    }

    // MARK: - API Payload

    /// Converts the draft to a payload for the API endpoint
    func toAPIPayload() -> [String: Any] {
        var payload: [String: Any] = [
            "isbn": isbn,
            "price": price,
            "condition": condition,
            "quantity": quantity,
            "use_seo_optimization": useSEOOptimization
        ]

        // Build Item Specifics
        var itemSpecifics: [String: [String]] = [:]

        // Format (always required)
        itemSpecifics["format"] = [format]

        // Language (default to English)
        itemSpecifics["language"] = [language]

        // Features (if any selected)
        var features: [String] = []
        if hasDustJacket {
            features.append("Dust Jacket")
        }
        if isFirstEdition {
            features.append("First Edition")
        }
        if isFirstPrinting {
            features.append("First Printing")
        }
        if isSigned {
            features.append("Signed")
        }
        if isExLibrary {
            features.append("Ex-Library")
        }
        if isBookClubEdition {
            features.append("Book Club Edition")
        }
        if isLimitedEdition {
            features.append("Limited Edition")
        }
        // Add custom features if provided
        if !customFeatures.isEmpty {
            features.append(customFeatures)
        }
        if features.count > 0 {
            itemSpecifics["features"] = features
        }

        // Special Attributes
        var specialAttributes: [String] = []
        if isIllustrated {
            specialAttributes.append("Illustrated")
        }
        if isLargePrint {
            specialAttributes.append("Large Print")
        }
        if specialAttributes.count > 0 {
            itemSpecifics["special_attributes"] = specialAttributes
        }

        if itemSpecifics.count > 0 {
            payload["item_specifics"] = itemSpecifics
        }

        return payload
    }

    // MARK: - Available Options

    static let conditions = [
        "Brand New",
        "Like New",
        "Very Good",
        "Good",
        "Acceptable"
    ]

    static let formats = [
        "Hardcover",
        "Paperback",
        "Mass Market Paperback",
        "Trade Paperback",
        "Board Book",
        "Leather Bound",
        "Spiral Bound"
    ]

    static let languages = [
        "English",
        "Spanish",
        "French",
        "German",
        "Italian",
        "Portuguese",
        "Chinese",
        "Japanese",
        "Korean",
        "Other"
    ]

    // MARK: - Summary

    /// Human-readable summary for confirmation step
    func summary() -> String {
        var lines: [String] = []

        lines.append("📚 \(title)")
        if let author = author {
            lines.append("✍️ \(author)")
        }
        if let year = publishedYear {
            lines.append("📅 \(year)")
        }
        lines.append("")
        lines.append("💵 Price: $\(String(format: "%.2f", price))")
        lines.append("📦 Quantity: \(quantity)")
        lines.append("✨ Condition: \(condition)")
        lines.append("📖 Format: \(format)")
        lines.append("🌐 Language: \(language)")

        if hasDustJacket || isFirstEdition || isSigned {
            lines.append("")
            lines.append("⭐️ Special Features:")
            if hasDustJacket {
                lines.append("  • Dust Jacket")
            }
            if isFirstEdition {
                lines.append("  • First Edition")
            }
            if isSigned {
                lines.append("  • Signed")
            }
        }

        if hasEPID, let epid = epid {
            lines.append("")
            lines.append("🎉 eBay Product ID: \(epid)")
            lines.append("   (Auto-populated Item Specifics)")
        }

        if useSEOOptimization {
            lines.append("")
            lines.append("🚀 SEO-Optimized Title Enabled")
        }

        return lines.joined(separator: "\n")
    }
}

/// Response from the create listing API
struct EbayListingResponse: Codable {
    let id: Int
    let sku: String
    let offerId: String?
    let ebayListingId: String?
    let epid: String?
    let title: String
    let titleScore: Double?
    let price: Double
    let status: String

    enum CodingKeys: String, CodingKey {
        case id, sku, epid, title, price, status
        case offerId = "offer_id"
        case ebayListingId = "ebay_listing_id"
        case titleScore = "title_score"
    }
}

/// Request payload for creating an eBay listing
struct CreateEbayListingRequest: Codable {
    let isbn: String
    let price: Double
    let condition: String
    let quantity: Int
    let itemSpecifics: [String: [String]]?
    let useSeoOptimization: Bool

    enum CodingKeys: String, CodingKey {
        case isbn, price, condition, quantity
        case itemSpecifics = "item_specifics"
        case useSeoOptimization = "use_seo_optimization"
    }
}
