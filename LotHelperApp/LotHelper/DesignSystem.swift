import SwiftUI

enum DS {
    enum Color {
        static let primary = SwiftUI.Color("AppPrimary")
        static let background = SwiftUI.Color("AppBackground")
        static let cardBg = SwiftUI.Color("CardBackground")
        static let textPrimary = SwiftUI.Color.primary
        static let textSecondary = SwiftUI.Color.secondary
    }

    enum Spacing {
        static let xs: CGFloat = 6
        static let sm: CGFloat = 10
        static let md: CGFloat = 14
        static let lg: CGFloat = 18
        static let xl: CGFloat = 24
    }

    enum Radius {
        static let sm: CGFloat = 10
        static let md: CGFloat = 16
        static let xl: CGFloat = 24
    }

    enum Shadow {
        static let card = SwiftUI.Color.black.opacity(0.08)
    }
}

struct BrandTheme: ViewModifier {
    func body(content: Content) -> some View {
        content
            .tint(DS.Color.primary)
    }
}

extension View {
    func brandTheme() -> some View { modifier(BrandTheme()) }
}

extension Text {
    func titleStyle() -> some View {
        font(.system(.title2, design: .rounded)).fontWeight(.semibold)
    }

    func subtitleStyle() -> some View {
        font(.system(.subheadline, design: .rounded)).foregroundStyle(DS.Color.textSecondary)
    }

    func bodyStyle() -> some View {
        font(.system(.body, design: .rounded))
    }
}
