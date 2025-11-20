import SwiftUI

struct ScannerDecisionCard: View {
    let eval: BookEvaluationRecord
    let profit: ProfitBreakdown
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Decision Factors")
                .font(.headline)
            
            VStack(spacing: 0) {
                factorRow(
                    label: "Profit Margin",
                    value: formatUSD(profit.bestProfit ?? 0),
                    status: profitStatus
                )
                
                Divider()
                
                factorRow(
                    label: "Confidence",
                    value: "\(Int(eval.probabilityScore ?? 0))%",
                    status: confidenceStatus
                )
                
                Divider()
                
                factorRow(
                    label: "Velocity",
                    value: velocityLabel,
                    status: velocityStatus
                )
                
                Divider()
                
                factorRow(
                    label: "Competition",
                    value: competitionLabel,
                    status: competitionStatus
                )
            }
            .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
            .overlay(
                RoundedRectangle(cornerRadius: DS.Radius.md)
                    .stroke(Color.gray.opacity(0.2), lineWidth: 1)
            )
        }
        .padding(.horizontal)
    }
    
    private func factorRow(label: String, value: String, status: FactorStatus) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .font(.subheadline)
                .bold()
                .foregroundColor(status.color)
            
            Image(systemName: status.icon)
                .font(.caption)
                .foregroundColor(status.color)
        }
        .padding()
    }
    
    // MARK: - Status Logic
    
    private enum FactorStatus {
        case good, neutral, bad, unknown
        
        var color: Color {
            switch self {
            case .good: return .green
            case .neutral: return .orange
            case .bad: return .red
            case .unknown: return .gray
            }
        }
        
        var icon: String {
            switch self {
            case .good: return "checkmark.circle.fill"
            case .neutral: return "minus.circle.fill"
            case .bad: return "xmark.circle.fill"
            case .unknown: return "questionmark.circle.fill"
            }
        }
    }
    
    private var profitStatus: FactorStatus {
        guard let p = profit.bestProfit else { return .unknown }
        if p >= 5.0 { return .good }
        if p > 0 { return .neutral }
        return .bad
    }
    
    private var confidenceStatus: FactorStatus {
        guard let s = eval.probabilityScore else { return .unknown }
        if s >= 70 { return .good }
        if s >= 40 { return .neutral }
        return .bad
    }
    
    private var velocityLabel: String {
        if let days = eval.timeToSellDays {
            return "\(days) days"
        }
        return "Unknown"
    }
    
    private var velocityStatus: FactorStatus {
        guard let days = eval.timeToSellDays else { return .unknown }
        if days <= 30 { return .good }
        if days <= 90 { return .neutral }
        return .bad
    }
    
    private var competitionLabel: String {
        if let active = eval.market?.activeCount {
            return "\(active) active"
        }
        return "Unknown"
    }
    
    private var competitionStatus: FactorStatus {
        guard let active = eval.market?.activeCount else { return .unknown }
        if active < 5 { return .good }
        if active < 20 { return .neutral }
        return .bad
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
