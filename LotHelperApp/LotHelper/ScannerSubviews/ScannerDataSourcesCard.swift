import SwiftUI

struct ScannerDataSourcesCard: View {
    let eval: BookEvaluationRecord
    let profit: ProfitBreakdown
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Data Sources")
                .font(.headline)
                .padding(.horizontal)
            
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ebayMarketSection
                    bookscouterSection
                    booksRunSection
                }
                .padding(.horizontal)
            }
        }
    }
    
    private var ebayMarketSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "cart.fill")
                Text("eBay Market")
                    .font(.headline)
            }
            
            if let market = eval.market {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Sold Comps:")
                        Spacer()
                        Text("\(market.soldCompsCount ?? 0)")
                            .bold()
                    }
                    
                    HStack {
                        Text("Median Sold:")
                        Spacer()
                        Text(formatUSD(market.soldCompsMedian ?? 0))
                            .bold()
                            .foregroundColor(.green)
                    }
                    
                    HStack {
                        Text("Sell-Through:")
                        Spacer()
                        Text("\(Int((market.sellThroughRate ?? 0) * 100))%")
                            .bold()
                    }
                    
                    if let fees = profit.ebayBreakdown {
                        Divider()
                        HStack {
                            Text("Est. Fees:")
                            Spacer()
                            Text(formatUSD(fees))
                                .font(.caption)
                                .foregroundColor(.red)
                        }
                    }
                }
                .font(.caption)
            } else {
                Text("No market data")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .frame(width: 160)
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }
    
    private var bookscouterSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "book.closed.fill")
                Text("BookScouter")
                    .font(.headline)
            }
            
            if let bs = eval.bookscouter {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Best Offer:")
                        Spacer()
                        Text(formatUSD(bs.bestPrice))
                            .bold()
                            .foregroundColor(.green)
                    }
                    
                    if let vendor = bs.bestVendor {
                        Text(vendor)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                    
                    if let rank = bs.amazonSalesRank {
                        Divider()
                        HStack {
                            Text("Amz Rank:")
                            Spacer()
                            Text("#\(rank)")
                                .font(.caption)
                        }
                    }
                }
                .font(.caption)
            } else {
                Text("No offers found")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .frame(width: 160)
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
    }
    
    private var booksRunSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "arrow.triangle.2.circlepath")
                Text("BooksRun")
                    .font(.headline)
            }
            
            if let br = eval.booksrun {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Cash:")
                        Spacer()
                        Text(formatUSD(br.cashPrice ?? 0))
                            .bold()
                            .foregroundColor(.green)
                    }
                    
                    HStack {
                        Text("Credit:")
                        Spacer()
                        Text(formatUSD(br.storeCredit ?? 0))
                            .bold()
                            .foregroundColor(.blue)
                    }
                }
                .font(.caption)
            } else {
                Text("No offer")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .frame(width: 160)
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 4, x: 0, y: 2)
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
