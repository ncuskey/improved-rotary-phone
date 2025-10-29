import SwiftUI

struct DecisionThresholdsSettingsView: View {
    @Binding var thresholds: DecisionThresholds
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationView {
            Form {
                // Preset Selection
                Section("Quick Presets") {
                    Button("Conservative (High Profit, Low Risk)") {
                        thresholds = .conservative
                        thresholds.save()
                    }
                    .foregroundStyle(.blue)

                    Button("Balanced (Recommended)") {
                        thresholds = .balanced
                        thresholds.save()
                    }
                    .foregroundStyle(.green)

                    Button("Aggressive (Low Profit, High Volume)") {
                        thresholds = .aggressive
                        thresholds.save()
                    }
                    .foregroundStyle(.orange)
                }

                // Profit Thresholds
                Section("Profit Thresholds") {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Minimum Auto-Buy Profit")
                            Spacer()
                            Text("$\(String(format: "%.2f", thresholds.minProfitAutoBuy))")
                                .foregroundStyle(.secondary)
                        }
                        Slider(value: $thresholds.minProfitAutoBuy, in: 1...15, step: 0.5)
                            .onChange(of: thresholds.minProfitAutoBuy) { _, _ in
                                thresholds.save()
                            }
                        Text("Minimum profit to automatically buy a book")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Slow-Moving Threshold")
                            Spacer()
                            Text("$\(String(format: "%.2f", thresholds.minProfitSlowMoving))")
                                .foregroundStyle(.secondary)
                        }
                        Slider(value: $thresholds.minProfitSlowMoving, in: 3...20, step: 1)
                            .onChange(of: thresholds.minProfitSlowMoving) { _, _ in
                                thresholds.save()
                            }
                        Text("Minimum profit for slow-moving books (high TTS)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Uncertainty Threshold")
                            Spacer()
                            Text("$\(String(format: "%.2f", thresholds.minProfitUncertainty))")
                                .foregroundStyle(.secondary)
                        }
                        Slider(value: $thresholds.minProfitUncertainty, in: 1...10, step: 0.5)
                            .onChange(of: thresholds.minProfitUncertainty) { _, _ in
                                thresholds.save()
                            }
                        Text("Minimum profit when confidence is low")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                // Confidence Thresholds
                Section("Confidence Thresholds") {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Minimum Confidence Score")
                            Spacer()
                            Text("\(Int(thresholds.minConfidenceAutoBuy))%")
                                .foregroundStyle(.secondary)
                        }
                        Slider(value: $thresholds.minConfidenceAutoBuy, in: 30...80, step: 5)
                            .onChange(of: thresholds.minConfidenceAutoBuy) { _, _ in
                                thresholds.save()
                            }
                        Text("Minimum probability score to auto-buy")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Low Confidence Threshold")
                            Spacer()
                            Text("\(Int(thresholds.lowConfidenceThreshold))%")
                                .foregroundStyle(.secondary)
                        }
                        Slider(value: $thresholds.lowConfidenceThreshold, in: 10...50, step: 5)
                            .onChange(of: thresholds.lowConfidenceThreshold) { _, _ in
                                thresholds.save()
                            }
                        Text("Score below this triggers uncertainty review")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                // Market Data Thresholds
                Section("Market Data Thresholds") {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Minimum Comps Required")
                            Spacer()
                            Text("\(thresholds.minCompsRequired)")
                                .foregroundStyle(.secondary)
                        }
                        Slider(value: Binding(
                            get: { Double(thresholds.minCompsRequired) },
                            set: { thresholds.minCompsRequired = Int($0) }
                        ), in: 1...10, step: 1)
                            .onChange(of: thresholds.minCompsRequired) { _, _ in
                                thresholds.save()
                            }
                        Text("Minimum total comparables (active + sold)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Max Slow-Moving TTS")
                            Spacer()
                            Text("\(thresholds.maxSlowMovingTTS) days")
                                .foregroundStyle(.secondary)
                        }
                        Slider(value: Binding(
                            get: { Double(thresholds.maxSlowMovingTTS) },
                            set: { thresholds.maxSlowMovingTTS = Int($0) }
                        ), in: 60...365, step: 30)
                            .onChange(of: thresholds.maxSlowMovingTTS) { _, _ in
                                thresholds.save()
                            }
                        Text("Days before flagging as slow-moving")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                // Risk Tolerance
                Section("Risk Tolerance") {
                    Toggle("Require Profit Data", isOn: $thresholds.requireProfitData)
                        .onChange(of: thresholds.requireProfitData) { _, _ in
                            thresholds.save()
                        }
                    Text("Flag books for review if no pricing data exists")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                // Reset Section
                Section {
                    Button("Reset to Balanced (Default)") {
                        thresholds = .balanced
                        thresholds.save()
                    }
                    .foregroundStyle(.blue)
                }
            }
            .navigationTitle("Decision Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
    }
}

#Preview {
    @Previewable @State var thresholds = DecisionThresholds.balanced
    DecisionThresholdsSettingsView(thresholds: $thresholds)
}
