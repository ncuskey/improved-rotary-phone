import SwiftUI

struct PricePickerSheet: View {
    @Binding var selectedPrice: Double
    @Environment(\.dismiss) private var dismiss

    // Generate price options from $0.00 to $50.00 in $0.25 increments
    private let priceOptions: [Double] = {
        var options: [Double] = []
        var price: Double = 0.00
        while price <= 50.00 {
            options.append(price)
            price += 0.25
        }
        return options
    }()

    @State private var tempSelectedPrice: Double

    init(selectedPrice: Binding<Double>) {
        self._selectedPrice = selectedPrice
        self._tempSelectedPrice = State(initialValue: selectedPrice.wrappedValue)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Current selection display
                VStack(spacing: 8) {
                    Text("Purchase Price")
                        .font(.headline)
                        .foregroundStyle(.secondary)

                    Text(formatUSD(tempSelectedPrice))
                        .font(.system(size: 48, weight: .bold, design: .rounded))
                        .foregroundStyle(.primary)

                    if tempSelectedPrice > 0 {
                        Button(action: { tempSelectedPrice = 0.00 }) {
                            Text("Clear")
                                .font(.subheadline)
                                .foregroundStyle(.red)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 24)
                .background(Color(.systemGray6))

                // Scrollable price list
                ScrollViewReader { proxy in
                    List {
                        ForEach(priceOptions, id: \.self) { price in
                            Button(action: {
                                tempSelectedPrice = price
                                SoundFeedback.lightImpact()
                            }) {
                                HStack {
                                    Text(formatUSD(price))
                                        .font(.body)
                                        .foregroundStyle(tempSelectedPrice == price ? .white : .primary)

                                    Spacer()

                                    if tempSelectedPrice == price {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundStyle(.white)
                                    }
                                }
                                .padding(.vertical, 8)
                            }
                            .listRowBackground(tempSelectedPrice == price ? Color.accentColor : Color(.systemBackground))
                            .id(price)
                        }
                    }
                    .listStyle(.plain)
                    .onAppear {
                        // Scroll to current selection
                        if tempSelectedPrice > 0 {
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                                proxy.scrollTo(tempSelectedPrice, anchor: .center)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Set Price")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        selectedPrice = tempSelectedPrice
                        SoundFeedback.success()
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
        }
    }

    private func formatUSD(_ value: Double) -> String {
        if #available(iOS 15.0, *) {
            return value.formatted(.currency(code: "USD"))
        } else {
            let formatter = NumberFormatter()
            formatter.numberStyle = .currency
            formatter.currencyCode = "USD"
            return formatter.string(from: value as NSNumber) ?? "$\(value)"
        }
    }
}

#Preview {
    @Previewable @State var price: Double = 2.50

    return PricePickerSheet(selectedPrice: $price)
}
