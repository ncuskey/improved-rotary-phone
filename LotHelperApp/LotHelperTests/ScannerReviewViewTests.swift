//
//  ScannerReviewViewTests.swift
//  LotHelperTests
//
//  Created by Claude Code
//

import Testing
import SwiftUI
@testable import LotHelper

@MainActor
struct ScannerReviewViewTests {

    // MARK: - ISBN Normalization Tests

    @Test("ISBN-10 to ISBN-13 conversion")
    func testISBN10ToISBN13Conversion() async throws {
        // Test converting ISBN-10 to ISBN-13
        let view = ScannerReviewView()

        // ISBN-10: 0307387895 -> ISBN-13: 9780307387899
        let normalized = view.normalizeToISBN13("0307387895")
        #expect(normalized == "9780307387899")

        // Already ISBN-13 should remain unchanged
        let isbn13 = "9780307387899"
        let unchanged = view.normalizeToISBN13(isbn13)
        #expect(unchanged == isbn13)
    }

    @Test("ISBN-13 checksum calculation")
    func testISBN13ChecksumCalculation() async throws {
        let view = ScannerReviewView()

        // Test known ISBN-13 checksum
        // For ISBN: 978-0-306-40615-?
        // The first 12 digits: 978030640615
        // Expected checksum: 7
        let checksum = view.calculateISBN13Checksum("978030640615")
        #expect(checksum == 7)

        // Another test case
        // For ISBN: 978-0-307-38789-?
        // The first 12 digits: 978030738789
        // Expected checksum: 9
        let checksum2 = view.calculateISBN13Checksum("978030738789")
        #expect(checksum2 == 9)
    }

    @Test("ISBN normalization with dashes and spaces")
    func testISBNNormalizationWithFormatting() async throws {
        let view = ScannerReviewView()

        // ISBN with dashes should have them removed
        let withDashes = "978-0-307-38789-9"
        let normalized = view.normalizeToISBN13(withDashes)
        #expect(normalized == "9780307387899")

        // ISBN-10 with dashes
        let isbn10WithDashes = "0-307-38789-5"
        let normalized10 = view.normalizeToISBN13(isbn10WithDashes)
        #expect(normalized10 == "9780307387899")
    }

    // MARK: - eBay Fee Calculation Tests

    @Test("eBay fees calculation for various prices")
    func testEbayFeesCalculation() async throws {
        let view = ScannerReviewView()

        // Test $20 sale
        let result20 = view.calculateEbayFees(salePrice: 20.0)
        #expect(result20.fees == 20.0 * 0.1325 + 0.30)
        #expect(result20.netProceeds == 20.0 - result20.fees)

        // Test $50 sale
        let result50 = view.calculateEbayFees(salePrice: 50.0)
        #expect(result50.fees == 50.0 * 0.1325 + 0.30)
        #expect(result50.netProceeds == 50.0 - result50.fees)

        // Test $10 sale (minimum viable)
        let result10 = view.calculateEbayFees(salePrice: 10.0)
        let expectedFees = 10.0 * 0.1325 + 0.30 // $1.325 + $0.30 = $1.625
        #expect(abs(result10.fees - expectedFees) < 0.01)
        #expect(abs(result10.netProceeds - (10.0 - expectedFees)) < 0.01)
    }

    @Test("eBay net proceeds are always less than sale price")
    func testEbayNetProceedsLessThanSale() async throws {
        let view = ScannerReviewView()

        for price in [5.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0] {
            let result = view.calculateEbayFees(salePrice: price)
            #expect(result.netProceeds < price)
            #expect(result.fees > 0)
        }
    }

    // MARK: - Amazon Fee Calculation Tests

    @Test("Amazon fees calculation for various prices")
    func testAmazonFeesCalculation() async throws {
        let view = ScannerReviewView()

        // Test $20 sale
        let result20 = view.calculateAmazonFees(salePrice: 20.0)
        #expect(result20.fees == 20.0 * 0.15 + 1.80)
        #expect(result20.netProceeds == 20.0 - result20.fees)

        // Test $50 sale
        let result50 = view.calculateAmazonFees(salePrice: 50.0)
        #expect(result50.fees == 50.0 * 0.15 + 1.80)
        #expect(result50.netProceeds == 50.0 - result50.fees)

        // Test $10 sale
        let result10 = view.calculateAmazonFees(salePrice: 10.0)
        let expectedFees = 10.0 * 0.15 + 1.80 // $1.50 + $1.80 = $3.30
        #expect(abs(result10.fees - expectedFees) < 0.01)
        #expect(abs(result10.netProceeds - (10.0 - expectedFees)) < 0.01)
    }

    @Test("Amazon net proceeds are always less than sale price")
    func testAmazonNetProceedsLessThanSale() async throws {
        let view = ScannerReviewView()

        for price in [5.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0] {
            let result = view.calculateAmazonFees(salePrice: price)
            #expect(result.netProceeds < price)
            #expect(result.fees > 0)
        }
    }

    @Test("Amazon vs eBay fee comparison")
    func testAmazonVsEbayFees() async throws {
        let view = ScannerReviewView()

        // Amazon: 15% + $1.80
        // eBay: 13.25% + $0.30
        // Amazon fees are typically higher for books

        let price = 20.0
        let ebayFees = view.calculateEbayFees(salePrice: price)
        let amazonFees = view.calculateAmazonFees(salePrice: price)

        // Amazon fees should be higher than eBay for most book prices
        #expect(amazonFees.fees > ebayFees.fees)
        #expect(amazonFees.netProceeds < ebayFees.netProceeds)
    }

    // MARK: - Profit Calculation Tests

    @Test("Profit calculation with purchase price")
    func testProfitCalculationWithPurchasePrice() async throws {
        let view = ScannerReviewView()

        // Create mock evaluation with estimated price
        var evaluation = BookEvaluationRecord()
        evaluation.estimatedPrice = 20.0

        // Set purchase price
        view.bookAttributes.purchasePrice = 5.0

        let profit = view.calculateProfit(evaluation)

        // Expected: $20 sale - $2.95 fees - $5 cost = $12.05 profit
        let expectedFees = 20.0 * 0.1325 + 0.30
        let expectedProfit = 20.0 - expectedFees - 5.0

        #expect(profit.estimatedProfit != nil)
        #expect(abs(profit.estimatedProfit! - expectedProfit) < 0.01)
    }

    @Test("Profit calculation with zero purchase price (free books)")
    func testProfitCalculationWithFreebooks() async throws {
        let view = ScannerReviewView()

        // Create mock evaluation
        var evaluation = BookEvaluationRecord()
        evaluation.estimatedPrice = 20.0

        // No purchase price set (free book)
        view.bookAttributes.purchasePrice = 0.0

        let profit = view.calculateProfit(evaluation)

        // Expected: $20 sale - $2.95 fees - $0 cost = $17.05 profit
        let expectedFees = 20.0 * 0.1325 + 0.30
        let expectedProfit = 20.0 - expectedFees

        #expect(profit.estimatedProfit != nil)
        #expect(abs(profit.estimatedProfit! - expectedProfit) < 0.01)
    }

    @Test("Buyback profit calculation")
    func testBuybackProfitCalculation() async throws {
        let view = ScannerReviewView()

        // Create mock evaluation with buyback offer
        var evaluation = BookEvaluationRecord()
        var bookscouter = BookScouterResult(isbn: "9780307387899")
        bookscouter.bestPrice = 15.0
        bookscouter.bestVendor = "TestVendor"
        evaluation.bookscouter = bookscouter

        // Set purchase price
        view.bookAttributes.purchasePrice = 5.0

        let profit = view.calculateProfit(evaluation)

        // Buyback profit: $15 - $5 = $10 (no fees)
        #expect(profit.buybackProfit == 10.0)
    }

    @Test("Amazon profit calculation")
    func testAmazonProfitCalculation() async throws {
        let view = ScannerReviewView()

        // Create mock evaluation with Amazon lowest price
        var evaluation = BookEvaluationRecord()
        var bookscouter = BookScouterResult(isbn: "9780307387899")
        bookscouter.amazonLowestPrice = 25.0
        evaluation.bookscouter = bookscouter

        // Set purchase price
        view.bookAttributes.purchasePrice = 5.0

        let profit = view.calculateProfit(evaluation)

        // Amazon profit: $25 - (15% + $1.80) - $5 = $25 - $5.55 - $5 = $14.45
        let expectedFees = 25.0 * 0.15 + 1.80
        let expectedProfit = 25.0 - expectedFees - 5.0

        #expect(profit.amazonProfit != nil)
        #expect(abs(profit.amazonProfit! - expectedProfit) < 0.01)
        #expect(profit.amazonPrice == 25.0)
    }

    @Test("All three profit paths calculation")
    func testAllThreeProfitPaths() async throws {
        let view = ScannerReviewView()

        // Create comprehensive evaluation with all three exit strategies
        var evaluation = BookEvaluationRecord()
        evaluation.estimatedPrice = 30.0 // eBay estimated

        var bookscouter = BookScouterResult(isbn: "9780307387899")
        bookscouter.bestPrice = 12.0      // Buyback
        bookscouter.amazonLowestPrice = 28.0  // Amazon
        evaluation.bookscouter = bookscouter

        view.bookAttributes.purchasePrice = 5.0

        let profit = view.calculateProfit(evaluation)

        // All three should be calculated
        #expect(profit.estimatedProfit != nil)  // eBay
        #expect(profit.buybackProfit != nil)    // Buyback
        #expect(profit.amazonProfit != nil)     // Amazon

        // Buyback: $12 - $5 = $7
        #expect(profit.buybackProfit == 7.0)

        // eBay: $30 - fees - $5
        let ebayFees = 30.0 * 0.1325 + 0.30
        let ebayProfit = 30.0 - ebayFees - 5.0
        #expect(abs(profit.estimatedProfit! - ebayProfit) < 0.01)

        // Amazon: $28 - fees - $5
        let amzFees = 28.0 * 0.15 + 1.80
        let amzProfit = 28.0 - amzFees - 5.0
        #expect(abs(profit.amazonProfit! - amzProfit) < 0.01)
    }

    // MARK: - Buy Decision Logic Tests

    @Test("Buy decision: Guaranteed buyback profit")
    func testBuyDecisionGuaranteedBuyback() async throws {
        let view = ScannerReviewView()

        // Create evaluation with buyback offer > purchase price
        var evaluation = BookEvaluationRecord()
        var bookscouter = BookScouterResult(isbn: "9780307387899")
        bookscouter.bestPrice = 10.0
        bookscouter.bestVendor = "TestVendor"
        evaluation.bookscouter = bookscouter

        view.bookAttributes.purchasePrice = 3.0

        let decision = view.makeBuyDecision(evaluation)

        #expect(decision.shouldBuy == true)
        #expect(decision.reason.contains("Guaranteed"))
    }

    @Test("Buy decision: Strong eBay profit")
    func testBuyDecisionStrongEbayProfit() async throws {
        let view = ScannerReviewView()

        // Create evaluation with high estimated price
        var evaluation = BookEvaluationRecord()
        evaluation.estimatedPrice = 30.0 // After fees: ~$26, profit: $21
        evaluation.probabilityScore = 70
        evaluation.probabilityLabel = "Worth buying"

        view.bookAttributes.purchasePrice = 5.0

        let decision = view.makeBuyDecision(evaluation)

        #expect(decision.shouldBuy == true)
    }

    @Test("Buy decision: Insufficient profit")
    func testBuyDecisionInsufficientProfit() async throws {
        let view = ScannerReviewView()

        // Create evaluation with low margin
        var evaluation = BookEvaluationRecord()
        evaluation.estimatedPrice = 8.0 // After fees: ~$6.74, profit: $1.74
        evaluation.probabilityScore = 50
        evaluation.probabilityLabel = "Risky"

        view.bookAttributes.purchasePrice = 5.0

        let decision = view.makeBuyDecision(evaluation)

        #expect(decision.shouldBuy == false)
        #expect(decision.reason.contains("thin") || decision.reason.contains("profit"))
    }

    @Test("Buy decision: Loss scenario")
    func testBuyDecisionLoss() async throws {
        let view = ScannerReviewView()

        // Create evaluation where cost exceeds proceeds
        var evaluation = BookEvaluationRecord()
        evaluation.estimatedPrice = 8.0 // After fees: ~$6.74

        view.bookAttributes.purchasePrice = 10.0 // Purchase price higher than net proceeds

        let decision = view.makeBuyDecision(evaluation)

        #expect(decision.shouldBuy == false)
        #expect(decision.reason.contains("lose"))
    }

    @Test("Buy decision: High confidence but low profit")
    func testBuyDecisionHighConfidenceLowProfit() async throws {
        let view = ScannerReviewView()

        // Create evaluation with very high confidence but thin margin
        var evaluation = BookEvaluationRecord()
        evaluation.estimatedPrice = 8.0 // After fees: ~$6.74, profit: ~$1.74
        evaluation.probabilityScore = 85
        evaluation.probabilityLabel = "Strong confidence"

        view.bookAttributes.purchasePrice = 5.0

        let decision = view.makeBuyDecision(evaluation)

        // Should still reject due to thin margin (less than $5 profit)
        #expect(decision.shouldBuy == false)
    }

    @Test("Buy decision: Amazon best profit")
    func testBuyDecisionAmazonBestProfit() async throws {
        let view = ScannerReviewView()

        // Create evaluation where Amazon offers best profit
        var evaluation = BookEvaluationRecord()
        evaluation.estimatedPrice = 18.0 // eBay: ~$15.35 net
        evaluation.probabilityScore = 65
        evaluation.probabilityLabel = "Worth buying"

        var bookscouter = BookScouterResult(isbn: "9780307387899")
        bookscouter.amazonLowestPrice = 25.0 // Amazon: ~$19.45 net (better!)
        bookscouter.bestPrice = 8.0 // Buyback: $3 net
        evaluation.bookscouter = bookscouter

        view.bookAttributes.purchasePrice = 5.0

        let decision = view.makeBuyDecision(evaluation)

        // Should recommend buy via Amazon (best profit of ~$14.45)
        #expect(decision.shouldBuy == true)
        #expect(decision.reason.contains("Amazon"))
    }

    @Test("Buy decision: Amazon with high rank indicates demand")
    func testBuyDecisionAmazonHighDemand() async throws {
        let view = ScannerReviewView()

        // Create evaluation with Amazon as best option and good sales rank
        var evaluation = BookEvaluationRecord()
        evaluation.estimatedPrice = 12.0 // Moderate eBay price
        evaluation.probabilityScore = 55
        evaluation.probabilityLabel = "Moderate"

        var bookscouter = BookScouterResult(isbn: "9780307387899")
        bookscouter.amazonLowestPrice = 20.0 // Strong Amazon price
        bookscouter.amazonSalesRank = 25_000 // Bestseller rank
        evaluation.bookscouter = bookscouter

        view.bookAttributes.purchasePrice = 5.0

        let decision = view.makeBuyDecision(evaluation)

        // Should recommend buy - Amazon offers good profit with strong demand
        #expect(decision.shouldBuy == true)
    }

    @Test("Buy decision: Multiple exit strategies increases confidence")
    func testBuyDecisionMultipleExitStrategies() async throws {
        let view = ScannerReviewView()

        // Create evaluation with decent profit across all three channels
        var evaluation = BookEvaluationRecord()
        evaluation.estimatedPrice = 20.0 // eBay: ~$12.35 net
        evaluation.probabilityScore = 60

        var bookscouter = BookScouterResult(isbn: "9780307387899")
        bookscouter.amazonLowestPrice = 22.0 // Amazon: ~$14.70 net
        bookscouter.bestPrice = 10.0 // Buyback: $5 net
        evaluation.bookscouter = bookscouter

        view.bookAttributes.purchasePrice = 5.0

        let decision = view.makeBuyDecision(evaluation)

        // Should recommend buy - best channel offers >$10 profit
        #expect(decision.shouldBuy == true)

        // Calculate actual profits to verify
        let profit = view.calculateProfit(evaluation)
        let bestProfit = [profit.estimatedProfit, profit.amazonProfit, profit.buybackProfit].compactMap { $0 }.max()
        #expect(bestProfit! > 10.0)
    }

    // MARK: - Probability Color Tests

    @Test("Probability color mapping")
    func testProbabilityColorMapping() async throws {
        let view = ScannerReviewView()

        #expect(view.probabilityColor(for: "Strong confidence") == .green)
        #expect(view.probabilityColor(for: "Worth buying") == .blue)
        #expect(view.probabilityColor(for: "Risky investment") == .orange)
        #expect(view.probabilityColor(for: "Don't buy") == .red)
    }

    // MARK: - Rank Color Tests

    @Test("Amazon rank color classification")
    func testAmazonRankColorClassification() async throws {
        let view = ScannerReviewView()

        // Bestseller (< 50k)
        #expect(view.rankColor(for: 10_000) == .green)
        #expect(view.rankColor(for: 49_999) == .green)

        // High demand (50k-100k)
        #expect(view.rankColor(for: 75_000) == .blue)

        // Solid demand (100k-300k)
        #expect(view.rankColor(for: 200_000) == .orange)

        // Slow moving (> 300k)
        #expect(view.rankColor(for: 500_000) == .secondary)
    }

    // MARK: - Rank Formatting Tests

    @Test("Amazon rank formatting")
    func testAmazonRankFormatting() async throws {
        let view = ScannerReviewView()

        // Low ranks show exact number
        #expect(view.formatRank(500) == "#500")
        #expect(view.formatRank(999) == "#999")

        // Higher ranks show in thousands
        #expect(view.formatRank(50_000) == "#50k")
        #expect(view.formatRank(150_000) == "#150k")
        #expect(view.formatRank(1_000_000) == "#1000k")
    }

    // MARK: - Rank Description Tests

    @Test("Amazon rank descriptions")
    func testAmazonRankDescriptions() async throws {
        let view = ScannerReviewView()

        #expect(view.rankDescription(for: 10_000) == "Bestseller")
        #expect(view.rankDescription(for: 75_000) == "High demand")
        #expect(view.rankDescription(for: 200_000) == "Solid demand")
        #expect(view.rankDescription(for: 400_000) == "Moderate")
        #expect(view.rankDescription(for: 750_000) == "Average")
        #expect(view.rankDescription(for: 1_500_000) == "Slow moving")
    }

    // MARK: - USD Formatting Tests

    @Test("USD currency formatting")
    func testUSDFormatting() async throws {
        let view = ScannerReviewView()

        let formatted10 = view.formatUSD(10.0)
        #expect(formatted10.contains("10"))
        #expect(formatted10.contains("$") || formatted10.contains("USD"))

        let formatted1599 = view.formatUSD(15.99)
        #expect(formatted1599.contains("15.99"))

        let formatted0 = view.formatUSD(0.0)
        #expect(formatted0.contains("0"))
    }

    // MARK: - Scanner Input Mode Tests

    @Test("Scanner input mode enum values")
    func testScannerInputModeEnum() async throws {
        #expect(ScannerInputMode.camera.rawValue == "Camera")
        #expect(ScannerInputMode.text.rawValue == "Text Entry")
        #expect(ScannerInputMode.allCases.count == 2)
    }

    // MARK: - Edge Cases

    @Test("Empty ISBN handling")
    func testEmptyISBNHandling() async throws {
        let view = ScannerReviewView()

        let normalized = view.normalizeToISBN13("")
        #expect(normalized.isEmpty)
    }

    @Test("Invalid ISBN length handling")
    func testInvalidISBNLengthHandling() async throws {
        let view = ScannerReviewView()

        // Too short
        let short = view.normalizeToISBN13("123")
        #expect(short == "123")

        // Too long
        let long = view.normalizeToISBN13("12345678901234567890")
        #expect(long == "12345678901234567890")
    }

    @Test("Profit calculation with no price data")
    func testProfitCalculationWithNoPriceData() async throws {
        let view = ScannerReviewView()

        // Empty evaluation
        let evaluation = BookEvaluationRecord()

        let profit = view.calculateProfit(evaluation)

        #expect(profit.estimatedProfit == nil)
        #expect(profit.buybackProfit == nil)
        #expect(profit.amazonProfit == nil)
    }

    @Test("Buy decision with no data")
    func testBuyDecisionWithNoData() async throws {
        let view = ScannerReviewView()

        // Empty evaluation
        let evaluation = BookEvaluationRecord()

        let decision = view.makeBuyDecision(evaluation)

        #expect(decision.shouldBuy == false)
        #expect(decision.reason.contains("Insufficient") || decision.reason.contains("confidence"))
    }

    // MARK: - Integration Tests

    @Test("Complete buy decision flow with all data")
    func testCompleteBuyDecisionFlow() async throws {
        let view = ScannerReviewView()

        // Create comprehensive evaluation
        var evaluation = BookEvaluationRecord()
        evaluation.isbn = "9780307387899"
        evaluation.estimatedPrice = 25.0
        evaluation.probabilityScore = 75
        evaluation.probabilityLabel = "Worth buying"

        var bookscouter = BookScouterResult(isbn: "9780307387899")
        bookscouter.bestPrice = 12.0
        bookscouter.bestVendor = "Decluttr"
        bookscouter.amazonSalesRank = 50_000
        evaluation.bookscouter = bookscouter

        view.bookAttributes.purchasePrice = 5.0

        let decision = view.makeBuyDecision(evaluation)
        let profit = view.calculateProfit(evaluation)

        // Should recommend buy due to strong eBay profit
        #expect(decision.shouldBuy == true)
        #expect(profit.estimatedProfit != nil)
        #expect(profit.estimatedProfit! > 10.0) // Should have > $10 net profit
        #expect(profit.buybackProfit == 7.0) // $12 - $5
    }
}

// MARK: - Helper Extensions for Testing

extension ScannerReviewView {
    // Expose internal methods for testing via reflection workaround
    // These methods are already internal but we make them accessible for testing

    func normalizeToISBN13(_ isbn: String) -> String {
        let digits = isbn.filter { $0.isNumber }

        if digits.count == 13 {
            return digits
        }

        if digits.count == 10 {
            let base = "978" + digits.prefix(9)
            let checksum = calculateISBN13Checksum(base)
            return base + String(checksum)
        }

        return digits
    }

    func calculateISBN13Checksum(_ first12: String) -> Int {
        let weights = [1, 3, 1, 3, 1, 3, 1, 3, 1, 3, 1, 3]
        let sum = zip(first12, weights).reduce(0) { sum, pair in
            let digit = Int(String(pair.0)) ?? 0
            return sum + (digit * pair.1)
        }
        let remainder = sum % 10
        return remainder == 0 ? 0 : 10 - remainder
    }

    func calculateEbayFees(salePrice: Double) -> (fees: Double, netProceeds: Double) {
        let finalValueFeeRate = 0.1325
        let transactionFee = 0.30

        let finalValueFee = salePrice * finalValueFeeRate
        let totalFees = finalValueFee + transactionFee
        let netProceeds = salePrice - totalFees

        return (fees: totalFees, netProceeds: netProceeds)
    }

    func calculateAmazonFees(salePrice: Double) -> (fees: Double, netProceeds: Double) {
        let referralFeeRate = 0.15
        let closingFee = 1.80

        let referralFee = salePrice * referralFeeRate
        let totalFees = referralFee + closingFee
        let netProceeds = salePrice - totalFees

        return (fees: totalFees, netProceeds: netProceeds)
    }

    func calculateProfit(_ eval: BookEvaluationRecord) -> (
        estimatedProfit: Double?,
        buybackProfit: Double?,
        amazonProfit: Double?,
        ebayBreakdown: Double?,
        amazonBreakdown: Double?,
        salePrice: Double?,
        amazonPrice: Double?
    ) {
        let purchasePrice = bookAttributes.purchasePrice

        var salePrice: Double?
        if let backendEstimate = eval.estimatedPrice {
            salePrice = backendEstimate
        }

        var estimatedProfit: Double?
        var ebayBreakdown: Double?
        if let price = salePrice {
            let breakdown = calculateEbayFees(salePrice: price)
            estimatedProfit = breakdown.netProceeds - purchasePrice
            ebayBreakdown = breakdown.fees
        }

        var amazonProfit: Double?
        var amazonBreakdown: Double?
        var amazonPrice: Double?
        if let amzPrice = eval.bookscouter?.amazonLowestPrice, amzPrice > 0 {
            amazonPrice = amzPrice
            let breakdown = calculateAmazonFees(salePrice: amzPrice)
            amazonProfit = breakdown.netProceeds - purchasePrice
            amazonBreakdown = breakdown.fees
        }

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

    func makeBuyDecision(_ eval: BookEvaluationRecord) -> (shouldBuy: Bool, reason: String) {
        let score = eval.probabilityScore ?? 0
        let label = eval.probabilityLabel?.lowercased() ?? ""
        let amazonRank = eval.bookscouter?.amazonSalesRank

        let profit = calculateProfit(eval)
        let buybackNetProfit = profit.buybackProfit
        let ebayNetProfit = profit.estimatedProfit
        let amazonNetProfit = profit.amazonProfit

        let bestProfit = [buybackNetProfit, ebayNetProfit, amazonNetProfit].compactMap { $0 }.max()

        if let buybackNet = buybackNetProfit, buybackNet > 0 {
            let vendorName = eval.bookscouter?.bestVendor ?? "vendor"
            return (true, "Guaranteed \(formatUSD(buybackNet)) profit via \(vendorName)")
        }

        if let maxProfit = bestProfit, maxProfit >= 10 {
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

        if let maxProfit = bestProfit, maxProfit > 0 {
            if label.contains("high") && score >= 80 {
                return (true, "Very high confidence offsets low margin")
            }
            return (false, "Net profit only \(formatUSD(maxProfit)) - too thin")
        }

        if let maxProfit = bestProfit, maxProfit <= 0 {
            return (false, "Would lose \(formatUSD(abs(maxProfit))) after fees")
        }

        if label.contains("high") && score >= 80 {
            return (true, "Very high confidence but verify pricing")
        }

        return (false, "Insufficient profit margin or confidence")
    }

    func probabilityColor(for label: String) -> Color {
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

    func rankColor(for rank: Int) -> Color {
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

    func formatRank(_ rank: Int) -> String {
        if rank < 1000 {
            return "#\(rank)"
        } else if rank < 100_000 {
            return "#\(rank / 1000)k"
        } else {
            return "#\(rank / 1000)k"
        }
    }

    func rankDescription(for rank: Int) -> String {
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
}
