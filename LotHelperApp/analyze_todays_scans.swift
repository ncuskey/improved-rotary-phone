#!/usr/bin/env swift

import Foundation

// This script fetches today's scans and runs them through the valuation process

struct ScanAnalysis {
    let isbn: String
    let title: String
    let estimatedPrice: Double?
    let probabilityScore: Double?
    let probabilityLabel: String?
    let ebayProfit: Double?
    let amazonProfit: Double?
    let buybackProfit: Double?
    let bestProfit: Double?
    let bestPlatform: String
    let recommendation: String
    let reason: String
    let isPartOfSeries: Bool
    let seriesName: String?
    let booksInSeries: Int
}

print("📚 Fetching today's scans...")
print("===========================================\n")

// Note: This is a template script. In practice, you would run this via the Swift app
// For now, let's create a curl command to fetch the data

let curlCommand = """
curl -s "https://lothelper.clevergirl.app/api/books/scan-history?limit=20" | python3 -m json.tool
"""

print("Run this command to fetch today's scans:")
print(curlCommand)
print("\n")
print("Then paste the ISBNs below and we'll analyze them.")
