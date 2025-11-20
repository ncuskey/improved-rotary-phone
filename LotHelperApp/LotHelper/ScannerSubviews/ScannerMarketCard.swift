import SwiftUI

struct ScannerMarketCard: View {
    let eval: BookEvaluationRecord
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Market Intelligence")
                .font(.headline)
            
            if let market = eval.market {
                VStack(spacing: 12) {
                    // Price Distribution
                    if let min = market.soldCompsMin, let max = market.soldCompsMax, let median = market.soldCompsMedian {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Price Range")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            
                            GeometryReader { geo in
                                ZStack(alignment: .leading) {
                                    RoundedRectangle(cornerRadius: 4)
                                        .fill(Color.gray.opacity(0.2))
                                        .frame(height: 8)
                                    
                                    // Range bar
                                    let range = max - min
                                    let width = range > 0 ? CGFloat((max - min) / max) * geo.size.width : 0
                                    let offset = range > 0 ? CGFloat((min) / max) * geo.size.width : 0
                                    
                                    RoundedRectangle(cornerRadius: 4)
                                        .fill(Color.blue.opacity(0.3))
                                        .frame(width: width, height: 8)
                                        .offset(x: offset)
                                    
                                    // Median marker
                                    let medianPos = range > 0 ? CGFloat(median / max) * geo.size.width : 0
                                    Circle()
                                        .fill(Color.blue)
                                        .frame(width: 12, height: 12)
                                        .offset(x: medianPos - 6)
                                }
                            }
                            .frame(height: 12)
                            
                            HStack {
                                Text(formatUSD(min))
                                Spacer()
                                Text(formatUSD(median)).bold()
                                Spacer()
                                Text(formatUSD(max))
                            }
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        }
                    }
                    
                    Divider()
                    
                    // Additional Stats
                    HStack {
                        VStack(alignment: .leading) {
                            Text("Signed Copies")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("\(market.signedListingsDetected ?? 0)")
                                .font(.subheadline)
                                .bold()
                        }
                        Spacer()
                        VStack(alignment: .leading) {
                            Text("Lot Listings")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("\(market.lotListingsDetected ?? 0)")
                                .font(.subheadline)
                                .bold()
                        }
                        Spacer()
                        VStack(alignment: .leading) {
                            Text("Total Listings")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("\(market.totalListings ?? 0)")
                                .font(.subheadline)
                                .bold()
                        }
                    }
                }
                .padding()
                .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
                .overlay(
                    RoundedRectangle(cornerRadius: DS.Radius.md)
                        .stroke(Color.gray.opacity(0.2), lineWidth: 1)
                )
            } else {
                Text("No detailed market data available")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .center)
                    .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
            }
        }
        .padding(.horizontal)
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
}
