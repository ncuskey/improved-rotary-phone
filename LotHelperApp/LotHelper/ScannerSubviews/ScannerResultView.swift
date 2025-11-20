import SwiftUI

struct ScannerResultView: View {
    @ObservedObject var viewModel: ScannerViewModel
    let eval: BookEvaluationRecord
    
    var body: some View {
        VStack(spacing: 16) {
            // Duplicate Warning
            if viewModel.isDuplicate {
                duplicateWarningBanner
            }
            
            // Buy Recommendation
            buyRecommendation
            
            // Series Context
            let seriesCheck = viewModel.checkSeriesCompletion(eval)
            if seriesCheck.isPartOfSeries {
                ScannerSeriesCard(seriesCheck: seriesCheck)
            }
            
            // Detailed Analysis
            detailedAnalysisPanel
        }
    }
    
    private var duplicateWarningBanner: some View {
        HStack {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.white)
            VStack(alignment: .leading) {
                Text("Duplicate Scan")
                    .font(.headline)
                    .foregroundColor(.white)
                if let date = viewModel.existingBookDate {
                    Text("Scanned \(formatDate(date))")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.9))
                }
            }
            Spacer()
        }
        .padding()
        .background(Color.orange)
        .cornerRadius(DS.Radius.md)
        .padding(.horizontal)
    }
    
    private var buyRecommendation: some View {
        let decision = viewModel.makeBuyDecision(eval)
        
        return VStack(spacing: 12) {
            HStack {
                Image(systemName: decision.shouldBuy ? "cart.fill.badge.plus" : "hand.raised.fill")
                    .font(.title)
                    .foregroundColor(decision.shouldBuy ? .green : .red)
                
                Text(decision.shouldBuy ? "BUY THIS BOOK" : "PASS")
                    .font(.title2)
                    .bold()
                    .foregroundColor(decision.shouldBuy ? .green : .red)
            }
            
            Text(decision.reason)
                .font(.headline)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
            
            if case .needsReview(_, let concerns) = decision {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(concerns, id: \.self) { concern in
                        HStack(alignment: .top) {
                            Image(systemName: "exclamationmark.circle")
                                .foregroundColor(.orange)
                            Text(concern)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .padding()
                .background(Color.orange.opacity(0.1))
                .cornerRadius(8)
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .overlay(
            RoundedRectangle(cornerRadius: DS.Radius.md)
                .stroke(decision.shouldBuy ? Color.green : Color.red, lineWidth: 2)
        )
        .padding(.horizontal)
    }
    
    private var detailedAnalysisPanel: some View {
        VStack(spacing: 16) {
            // Score Breakdown
            ScannerScoreCard(
                score: eval.probabilityScore ?? 0,
                label: eval.probabilityLabel ?? "Unknown",
                justification: eval.justification ?? []
            )
            .padding(.horizontal)
            
            // Data Sources
            ScannerDataSourcesCard(
                eval: eval,
                profit: viewModel.calculateProfit(eval)
            )
            
            // Decision Factors
            ScannerDecisionCard(
                eval: eval,
                profit: viewModel.calculateProfit(eval)
            )
            
            // Market Intelligence
            ScannerMarketCard(eval: eval)
        }
    }
    
    private func formatDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}
