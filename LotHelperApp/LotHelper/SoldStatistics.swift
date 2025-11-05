import Foundation

/// Model for sold listings statistics from the /api/books/{isbn}/sold-statistics endpoint
struct SoldStatistics: Codable, Hashable {
    let demandSignal: Double?
    let platformBreakdown: PlatformBreakdown
    let features: SoldFeatures
    let dataQuality: DataQuality

    enum CodingKeys: String, CodingKey {
        case demandSignal = "demand_signal"
        case platformBreakdown = "platform_breakdown"
        case features
        case dataQuality = "data_quality"
    }
}

struct PlatformBreakdown: Codable, Hashable {
    let ebayPct: Double
    let amazonPct: Double
    let mercariPct: Double

    enum CodingKeys: String, CodingKey {
        case ebayPct = "ebay_pct"
        case amazonPct = "amazon_pct"
        case mercariPct = "mercari_pct"
    }
}

struct SoldFeatures: Codable, Hashable {
    let signedPct: Double?
    let hardcoverPct: Double?
    let avgPrice: Double?
    let priceRange: Double?

    enum CodingKeys: String, CodingKey {
        case signedPct = "signed_pct"
        case hardcoverPct = "hardcover_pct"
        case avgPrice = "avg_price"
        case priceRange = "price_range"
    }
}

struct DataQuality: Codable, Hashable {
    let totalCount: Int
    let singleSalesCount: Int
    let lotSalesCount: Int
    let dataCompleteness: Double

    enum CodingKeys: String, CodingKey {
        case totalCount = "total_count"
        case singleSalesCount = "single_sales_count"
        case lotSalesCount = "lot_sales_count"
        case dataCompleteness = "data_completeness"
    }
}

// MARK: - Computed Properties for UI Display

extension SoldStatistics {
    /// Human-readable demand indicator
    var demandLabel: String {
        guard let signal = demandSignal else { return "Unknown" }

        switch signal {
        case 0..<50:
            return "Very Low"
        case 50..<200:
            return "Low"
        case 200..<500:
            return "Moderate"
        case 500..<1000:
            return "High"
        default:
            return "Very High"
        }
    }

    /// Primary platform (highest percentage)
    var primaryPlatform: String {
        let platforms = [
            ("eBay", platformBreakdown.ebayPct),
            ("Amazon", platformBreakdown.amazonPct),
            ("Mercari", platformBreakdown.mercariPct)
        ]
        return platforms.max(by: { $0.1 < $1.1 })?.0 ?? "Unknown"
    }

    /// Data quality indicator (0-100%)
    var qualityScore: Double {
        dataQuality.dataCompleteness * 100
    }

    /// Whether we have sufficient data for reliable analysis
    var hasSufficientData: Bool {
        dataQuality.totalCount >= 3 && dataQuality.dataCompleteness >= 0.7
    }
}

extension PlatformBreakdown {
    /// Array of (platform name, percentage) sorted by percentage descending
    var sortedPlatforms: [(name: String, percentage: Double)] {
        [
            ("eBay", ebayPct),
            ("Amazon", amazonPct),
            ("Mercari", mercariPct)
        ].sorted { $0.1 > $1.1 }
    }
}

extension DataQuality {
    /// Human-readable quality label
    var qualityLabel: String {
        switch dataCompleteness {
        case 0.9...1.0:
            return "Excellent"
        case 0.7..<0.9:
            return "Good"
        case 0.5..<0.7:
            return "Fair"
        default:
            return "Limited"
        }
    }

    /// Whether this book is primarily sold in lots
    var isPrimarilyLots: Bool {
        guard totalCount > 0 else { return false }
        let lotPct = Double(lotSalesCount) / Double(totalCount)
        return lotPct > 0.5
    }
}
