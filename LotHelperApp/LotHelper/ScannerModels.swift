import Foundation
import SwiftUI

// MARK: - Input Mode
enum ScannerInputMode {
    case camera
    case text
}

// MARK: - Purchase Decision
enum PurchaseDecision {
    case buy(reason: String)
    case skip(reason: String)
    case needsReview(reason: String, concerns: [String])
    
    var shouldBuy: Bool {
        switch self {
        case .buy: return true
        case .skip, .needsReview: return false
        }
    }
    
    var reason: String {
        switch self {
        case .buy(let r): return r
        case .skip(let r): return r
        case .needsReview(let r, _): return r
        }
    }
}

// MARK: - Decision Thresholds
struct DecisionThresholds: Codable, Equatable {
    var minProfitAutoBuy: Double
    var minProfitSlowMoving: Double
    var minProfitUncertainty: Double
    var minConfidenceAutoBuy: Double
    var lowConfidenceThreshold: Double
    var minCompsRequired: Int
    var maxSlowMovingTTS: Int
    var requireProfitData: Bool
    
    static let balanced = DecisionThresholds(
        minProfitAutoBuy: 5.0,
        minProfitSlowMoving: 10.0,
        minProfitUncertainty: 3.0,
        minConfidenceAutoBuy: 60.0,
        lowConfidenceThreshold: 40.0,
        minCompsRequired: 3,
        maxSlowMovingTTS: 180,
        requireProfitData: false
    )
    
    static let conservative = DecisionThresholds(
        minProfitAutoBuy: 8.0,
        minProfitSlowMoving: 15.0,
        minProfitUncertainty: 5.0,
        minConfidenceAutoBuy: 75.0,
        lowConfidenceThreshold: 50.0,
        minCompsRequired: 5,
        maxSlowMovingTTS: 90,
        requireProfitData: true
    )
    
    static let aggressive = DecisionThresholds(
        minProfitAutoBuy: 3.0,
        minProfitSlowMoving: 8.0,
        minProfitUncertainty: 1.0,
        minConfidenceAutoBuy: 50.0,
        lowConfidenceThreshold: 30.0,
        minCompsRequired: 1,
        maxSlowMovingTTS: 365,
        requireProfitData: false
    )
    
    static func load() -> DecisionThresholds {
        if let data = UserDefaults.standard.data(forKey: "DecisionThresholds"),
           let decoded = try? JSONDecoder().decode(DecisionThresholds.self, from: data) {
            return decoded
        }
        return .balanced
    }
    
    func save() {
        if let encoded = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(encoded, forKey: "DecisionThresholds")
        }
    }
}

// MARK: - Book Attributes
struct BookAttributes {
    var condition: String
    var purchasePrice: Double = 0.0
    var coverType: String = "Unknown"
    var printing: String = ""
    var signed: Bool = false
    var firstEdition: Bool = false
    
    init(defaultCondition: String = "Good") {
        self.condition = defaultCondition
    }
    
    /// Build edition notes string from attributes
    var editionNotes: String? {
        var notes: [String] = []

        if firstEdition {
            notes.append("First Edition")
        }
        if !printing.isEmpty {
            notes.append(printing)
        }
        if signed {
            notes.append("Signed")
        }

        return notes.isEmpty ? nil : notes.joined(separator: ", ")
    }
}

// MARK: - Profit Breakdown
struct ProfitBreakdown {
    let estimatedProfit: Double?
    let buybackProfit: Double?
    let amazonProfit: Double?
    let ebayBreakdown: Double?
    let amazonBreakdown: Double?
    let salePrice: Double?
    let amazonPrice: Double?
    
    var bestProfit: Double? {
        [estimatedProfit, buybackProfit, amazonProfit]
            .compactMap { $0 }
            .max()
    }
}

// MARK: - Series Scan Helper
struct PreviousSeriesScan: Identifiable {
    let id = UUID()
    let isbn: String
    let title: String?
    let seriesIndex: String?
    let scannedAt: Date
    let locationName: String?
    let decision: String?
    let estimatedPrice: Double?
}
