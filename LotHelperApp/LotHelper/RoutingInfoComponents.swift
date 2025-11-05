//
//  RoutingInfoComponents.swift
//  LotHelper
//
//  Reusable SwiftUI components for displaying ML model routing info and sales channel recommendations
//

import SwiftUI

// MARK: - ML Model Badge
struct MLModelBadge: View {
    let routing: MLRoutingInfo

    var body: some View {
        HStack(spacing: 4) {
            // Confidence dot indicator
            Circle()
                .fill(confidenceColor)
                .frame(width: 8, height: 8)

            Text(routing.modelDisplayName)
                .font(.caption)
                .fontWeight(.medium)
                .foregroundColor(.primary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(confidenceColor.opacity(0.15))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(confidenceColor.opacity(0.3), lineWidth: 1)
        )
    }

    private var confidenceColor: Color {
        if routing.confidenceScore >= 0.9 {
            return .green
        } else if routing.confidenceScore >= 0.75 {
            return .blue
        } else if routing.confidenceScore >= 0.6 {
            return .orange
        } else {
            return .gray
        }
    }
}

// MARK: - Confidence Score Meter
struct ConfidenceScoreMeter: View {
    let score: Double
    let label: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let label = label {
                Text(label)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    // Background track
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.gray.opacity(0.2))

                    // Filled portion
                    RoundedRectangle(cornerRadius: 2)
                        .fill(confidenceGradient)
                        .frame(width: geometry.size.width * score)
                }
            }
            .frame(height: 4)

            // Percentage label
            Text("\(Int(score * 100))%")
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundColor(confidenceColor)
        }
    }

    private var confidenceColor: Color {
        if score >= 0.9 {
            return .green
        } else if score >= 0.75 {
            return .blue
        } else if score >= 0.6 {
            return .orange
        } else {
            return .gray
        }
    }

    private var confidenceGradient: LinearGradient {
        LinearGradient(
            gradient: Gradient(colors: [confidenceColor.opacity(0.8), confidenceColor]),
            startPoint: .leading,
            endPoint: .trailing
        )
    }
}

// MARK: - Channel Recommendation Pill
struct ChannelRecommendationPill: View {
    let recommendation: ChannelRecommendation

    var body: some View {
        HStack(spacing: 6) {
            // Channel icon
            Image(systemName: channelIcon)
                .font(.caption)
                .foregroundColor(channelColor)

            // Channel label
            Text(channelDisplayName)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundColor(.primary)

            // Confidence badge
            if recommendation.confidence >= 0.8 {
                Text("\(Int(recommendation.confidence * 100))%")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .foregroundColor(channelColor)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 2)
                    .background(
                        Capsule()
                            .fill(channelColor.opacity(0.15))
                    )
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(
            Capsule()
                .fill(channelColor.opacity(0.1))
        )
        .overlay(
            Capsule()
                .strokeBorder(channelColor.opacity(0.3), lineWidth: 1)
        )
    }

    private var channelDisplayName: String {
        switch recommendation.channel {
        case "ebay_individual":
            return "eBay Individual"
        case "ebay_lot":
            return "eBay Lot"
        case "bulk_vendor":
            return "Bulk Vendor"
        case "hold":
            return "Hold"
        default:
            return recommendation.channel.capitalized
        }
    }

    private var channelIcon: String {
        switch recommendation.channel {
        case "ebay_individual":
            return "tag.fill"
        case "ebay_lot":
            return "square.stack.3d.up.fill"
        case "bulk_vendor":
            return "dollarsign.circle.fill"
        case "hold":
            return "pause.circle.fill"
        default:
            return "tag"
        }
    }

    private var channelColor: Color {
        switch recommendation.channel {
        case "ebay_individual":
            return .blue
        case "ebay_lot":
            return .purple
        case "bulk_vendor":
            return .green
        case "hold":
            return .orange
        default:
            return .gray
        }
    }
}

// MARK: - Routing Info Detail View
struct RoutingInfoDetailView: View {
    let routing: MLRoutingInfo

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Image(systemName: "cpu.fill")
                    .foregroundColor(.blue)
                Text("ML Model")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                MLModelBadge(routing: routing)
            }

            Divider()

            // Metrics
            VStack(alignment: .leading, spacing: 8) {
                MetricRow(label: "Accuracy", value: "±$\(String(format: "%.2f", routing.modelMae))")
                MetricRow(label: "R²", value: String(format: "%.3f", routing.modelR2))
                MetricRow(label: "Features", value: "\(routing.features)")
                MetricRow(label: "Coverage", value: routing.coverage)
            }

            // Confidence meter
            ConfidenceScoreMeter(score: routing.confidenceScore, label: "Confidence")

            // Routing reason
            Text(routing.routingReason)
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.top, 4)
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.secondarySystemGroupedBackground))
        )
    }
}

// MARK: - Channel Recommendation Detail View
struct ChannelRecommendationDetailView: View {
    let recommendation: ChannelRecommendation

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Image(systemName: "arrow.triangle.branch")
                    .foregroundColor(.purple)
                Text("Recommended Channel")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                ChannelRecommendationPill(recommendation: recommendation)
            }

            Divider()

            // Metrics
            VStack(alignment: .leading, spacing: 8) {
                MetricRow(
                    label: "Expected Profit",
                    value: "$\(String(format: "%.2f", recommendation.expectedProfit))",
                    valueColor: .green
                )
                if let days = recommendation.expectedDaysToSale {
                    MetricRow(label: "Est. Time to Sale", value: "\(days) days")
                }
            }

            // Confidence meter
            ConfidenceScoreMeter(score: recommendation.confidence, label: "Confidence")

            // Reasoning
            VStack(alignment: .leading, spacing: 4) {
                Text("Reasoning:")
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundColor(.secondary)

                ForEach(recommendation.reasoning, id: \.self) { reason in
                    HStack(alignment: .top, spacing: 4) {
                        Text("•")
                            .foregroundColor(.secondary)
                        Text(reason)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding(.top, 4)
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.secondarySystemGroupedBackground))
        )
    }
}

// MARK: - Helper Views
private struct MetricRow: View {
    let label: String
    let value: String
    var valueColor: Color = .primary

    var body: some View {
        HStack {
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .font(.caption)
                .fontWeight(.medium)
                .foregroundColor(valueColor)
        }
    }
}

// MARK: - Preview
#if DEBUG
struct RoutingInfoComponents_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: 20) {
            // ML Model Badge Preview
            MLModelBadge(routing: MLRoutingInfo(
                model: "ebay_specialist",
                modelDisplayName: "eBay Specialist",
                modelMae: 3.03,
                modelR2: 0.469,
                features: 20,
                confidence: "high",
                confidenceScore: 0.85,
                routingReason: "eBay market data available",
                coverage: "72% of catalog"
            ))

            // Channel Recommendation Pill Preview
            ChannelRecommendationPill(recommendation: ChannelRecommendation(
                channel: "ebay_individual",
                confidence: 0.85,
                reasoning: ["High eBay value", "Good sell-through rate"],
                expectedProfit: 28.50,
                expectedDaysToSale: 21
            ))

            // Full Detail Views
            ScrollView {
                VStack(spacing: 16) {
                    RoutingInfoDetailView(routing: MLRoutingInfo(
                        model: "ebay_specialist",
                        modelDisplayName: "eBay Specialist",
                        modelMae: 3.03,
                        modelR2: 0.469,
                        features: 20,
                        confidence: "high",
                        confidenceScore: 0.85,
                        routingReason: "eBay market data available",
                        coverage: "72% of catalog"
                    ))

                    ChannelRecommendationDetailView(recommendation: ChannelRecommendation(
                        channel: "ebay_individual",
                        confidence: 0.85,
                        reasoning: [
                            "High eBay value ($33.50)",
                            "Good sell-through rate (60%)",
                            "Recent sales activity"
                        ],
                        expectedProfit: 28.50,
                        expectedDaysToSale: 21
                    ))
                }
                .padding()
            }
        }
        .padding()
        .background(Color(.systemGroupedBackground))
    }
}
#endif
