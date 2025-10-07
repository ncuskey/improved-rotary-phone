import SwiftUI

struct EmptyStateView: View {
    let systemImage: String
    let title: String
    let message: String
    let actionTitle: String
    let action: () -> Void

    var body: some View {
        VStack(spacing: DS.Spacing.lg) {
            Image(systemName: systemImage)
                .font(.system(size: 48, weight: .light, design: .rounded))
                .foregroundStyle(DS.Color.textSecondary)
                .accessibilityHidden(true)

            VStack(spacing: DS.Spacing.sm) {
                Text(title)
                    .titleStyle()
                Text(message)
                    .bodyStyle()
                    .foregroundStyle(DS.Color.textSecondary)
                    .multilineTextAlignment(.center)
            }

            Button(actionTitle, action: action)
                .buttonStyle(.borderedProminent)
                .accessibilityLabel(actionTitle)
                .padding(.horizontal, DS.Spacing.lg)
                .padding(.vertical, 12)
        }
        .padding(DS.Spacing.xl)
        .frame(maxWidth: .infinity)
        .background(DS.Color.cardBg, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        .shadow(color: DS.Shadow.card, radius: 10, x: 0, y: 6)
        .padding(.horizontal, DS.Spacing.xl)
    }
}

#Preview {
    EmptyStateView(
        systemImage: "shippingbox",
        title: "No Lots Yet",
        message: "Generate a fresh batch of recommendations to see them here.",
        actionTitle: "Refresh",
        action: {}
    )
    .padding()
    .background(DS.Color.background)
}
