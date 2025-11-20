import SwiftUI

struct ScannerScoreCard: View {
    let score: Double
    let label: String
    let justification: [String]
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 16) {
                // Score Circle
                ZStack {
                    Circle()
                        .stroke(lineWidth: 6)
                        .opacity(0.3)
                        .foregroundColor(scoreColor)
                    
                    Circle()
                        .trim(from: 0.0, to: CGFloat(min(score / 100.0, 1.0)))
                        .stroke(style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round))
                        .foregroundColor(scoreColor)
                        .rotationEffect(Angle(degrees: 270.0))
                    
                    Text("\(Int(score))")
                        .font(.system(.title, design: .rounded))
                        .bold()
                        .foregroundColor(scoreColor)
                }
                .frame(width: 60, height: 60)
                
                VStack(alignment: .leading, spacing: 4) {
                    Text(label)
                        .font(.headline)
                        .foregroundColor(scoreColor)
                    
                    if !justification.isEmpty {
                        Text(justification.first ?? "")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                    }
                }
            }
            
            if justification.count > 1 {
                Divider()
                ForEach(justification.dropFirst(), id: \.self) { reason in
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.caption)
                            .foregroundColor(.green)
                            .padding(.top, 2)
                        Text(reason)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }
    
    private var scoreColor: Color {
        if score >= 70 { return .green }
        if score >= 40 { return .orange }
        return .red
    }
}
