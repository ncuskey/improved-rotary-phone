import SwiftUI

struct ScannerSeriesCard: View {
    let seriesCheck: (isPartOfSeries: Bool, seriesName: String?, booksInSeries: Int, previousScans: [PreviousSeriesScan], totalInSeries: Int?, missingCount: Int?)
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "books.vertical.fill")
                    .foregroundColor(.purple)
                Text("Series Context")
                    .font(.headline)
                Spacer()
                if let name = seriesCheck.seriesName {
                    Text(name)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
            }
            
            HStack(spacing: 16) {
                VStack(alignment: .leading) {
                    Text("Books Scanned")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("\(seriesCheck.booksInSeries)")
                        .font(.title2)
                        .bold()
                        .foregroundColor(.purple)
                }
                
                Divider()
                
                if !seriesCheck.previousScans.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Previously Found:")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        ForEach(seriesCheck.previousScans.prefix(3)) { scan in
                            HStack {
                                Text(scan.title ?? scan.isbn)
                                    .font(.caption2)
                                    .lineLimit(1)
                                Spacer()
                                if let decision = scan.decision {
                                    Image(systemName: decision == "ACCEPTED" ? "checkmark.circle.fill" : "xmark.circle.fill")
                                        .font(.caption2)
                                        .foregroundColor(decision == "ACCEPTED" ? .green : .red)
                                }
                            }
                        }
                        
                        if seriesCheck.previousScans.count > 3 {
                            Text("+ \(seriesCheck.previousScans.count - 3) more")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }
                } else {
                    Text("First book in this series found in this session.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding()
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .overlay(
            RoundedRectangle(cornerRadius: DS.Radius.md)
                .stroke(Color.purple.opacity(0.3), lineWidth: 1)
        )
        .padding(.horizontal)
    }
}
