import SwiftUI

struct ScannerAttributesView: View {
    @ObservedObject var viewModel: ScannerViewModel
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "slider.horizontal.3")
                    .foregroundStyle(.purple)
                Text("Book Attributes")
                    .font(.headline)
                
                Spacer()
                
                if viewModel.isUpdatingPrice {
                    ProgressView()
                        .scaleEffect(0.8)
                }
            }
            
            // Condition Picker
            VStack(alignment: .leading, spacing: 8) {
                Text("Condition")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                Picker("Condition", selection: $viewModel.selectedCondition) {
                    Text("New").tag("New")
                    Text("Like New").tag("Like New")
                    Text("Very Good").tag("Very Good")
                    Text("Good").tag("Good")
                    Text("Acceptable").tag("Acceptable")
                    Text("Poor").tag("Poor")
                }
                .pickerStyle(.segmented)
                .onChange(of: viewModel.selectedCondition) { oldValue, newValue in
                    viewModel.updatePriceEstimate()
                }
            }
            
            // Format (mutually exclusive)
            VStack(alignment: .leading, spacing: 8) {
                Text("Format")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                HStack(spacing: 8) {
                    FormatToggle(
                        label: "Hardcover",
                        isSelected: $viewModel.isHardcover,
                        delta: viewModel.dynamicEstimate?.deltas.first { $0.attribute == "is_hardcover" }?.delta,
                        onToggle: {
                            if viewModel.isHardcover {
                                viewModel.isPaperback = false
                                viewModel.isMassMarket = false
                            }
                            viewModel.updatePriceEstimate()
                        }
                    )
                    
                    FormatToggle(
                        label: "Paperback",
                        isSelected: $viewModel.isPaperback,
                        delta: viewModel.dynamicEstimate?.deltas.first { $0.attribute == "is_paperback" }?.delta,
                        onToggle: {
                            if viewModel.isPaperback {
                                viewModel.isHardcover = false
                                viewModel.isMassMarket = false
                            }
                            viewModel.updatePriceEstimate()
                        }
                    )
                    
                    FormatToggle(
                        label: "Mass Market",
                        isSelected: $viewModel.isMassMarket,
                        delta: viewModel.dynamicEstimate?.deltas.first { $0.attribute == "is_mass_market" }?.delta,
                        onToggle: {
                            if viewModel.isMassMarket {
                                viewModel.isHardcover = false
                                viewModel.isPaperback = false
                            }
                            viewModel.updatePriceEstimate()
                        }
                    )
                }
            }
            
            // Special Attributes
            VStack(alignment: .leading, spacing: 8) {
                Text("Special Attributes")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                AttributeToggle(
                    label: "Signed/Autographed",
                    isOn: $viewModel.isSigned,
                    delta: viewModel.dynamicEstimate?.deltas.first { $0.attribute == "is_signed" }?.delta,
                    onToggle: { viewModel.updatePriceEstimate() }
                )
                
                AttributeToggle(
                    label: "First Edition",
                    isOn: $viewModel.isFirstEdition,
                    delta: viewModel.dynamicEstimate?.deltas.first { $0.attribute == "is_first_edition" }?.delta,
                    onToggle: { viewModel.updatePriceEstimate() }
                )
            }
            
            // Price Display with updated estimate
            if let estimate = viewModel.dynamicEstimate {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("Updated Price:")
                            .font(.headline)
                        Spacer()
                        Text("$\(String(format: "%.2f", estimate.estimatedPrice))")
                            .font(.title2)
                            .bold()
                            .foregroundColor(.green)
                    }
                    
                    // Show prediction interval
                    Divider()
                    
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Image(systemName: "chart.line.uptrend.xyaxis")
                                .font(.caption)
                                .foregroundStyle(.blue)
                            Text("\(String(format: "%.0f%%", estimate.confidencePercent)) Confidence Range")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundStyle(.secondary)
                        }
                        
                        HStack(spacing: 4) {
                            Text("$\(String(format: "%.2f", estimate.priceLower))")
                                .font(.caption)
                                .foregroundStyle(.orange)
                            Text("–")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text("$\(String(format: "%.2f", estimate.priceUpper))")
                                .font(.caption)
                                .foregroundStyle(.orange)
                        }
                        .padding(.leading, 20)
                    }
                }
                .padding(.vertical, 8)
                .padding(.horizontal)
                .background(Color.green.opacity(0.1))
                .cornerRadius(8)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: DS.Shadow.card, radius: 8, x: 0, y: 4)
    }
}

struct AttributeToggle: View {
    let label: String
    @Binding var isOn: Bool
    let delta: Double?
    let onToggle: () -> Void
    
    var body: some View {
        HStack {
            Toggle(label, isOn: $isOn)
                .onChange(of: isOn) { oldValue, newValue in
                    onToggle()
                }
            
            if let delta = delta, delta != 0 {
                Text(delta > 0 ? "+$\(String(format: "%.2f", delta))" : "$\(String(format: "%.2f", delta))")
                    .font(.caption)
                    .foregroundColor(delta > 0 ? .green : .red)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(delta > 0 ? Color.green.opacity(0.1) : Color.red.opacity(0.1))
                    .cornerRadius(4)
            }
        }
    }
}

struct FormatToggle: View {
    let label: String
    @Binding var isSelected: Bool
    let delta: Double?
    let onToggle: () -> Void
    
    var body: some View {
        VStack(spacing: 4) {
            Button(action: {
                isSelected.toggle()
                onToggle()
            }) {
                Text(label)
                    .font(.caption)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 12)
                    .background(isSelected ? Color.blue : Color.gray.opacity(0.2))
                    .foregroundColor(isSelected ? .white : .primary)
                    .cornerRadius(8)
            }
            
            if let delta = delta, delta != 0 {
                Text(delta > 0 ? "+$\(String(format: "%.2f", delta))" : "$\(String(format: "%.2f", delta))")
                    .font(.caption2)
                    .foregroundColor(delta > 0 ? .green : .red)
            }
        }
    }
}
