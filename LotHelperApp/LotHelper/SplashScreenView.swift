import SwiftUI

struct SplashScreenView: View {
    let loadingStatus: String

    var body: some View {
        ZStack {
            // Background
            DS.Color.background
                .ignoresSafeArea()

            VStack(spacing: 32) {
                Spacer()

                // App Icon
                if let appIcon = UIImage(named: "AppIcon") {
                    Image(uiImage: appIcon)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 120, height: 120)
                        .clipShape(RoundedRectangle(cornerRadius: 26.4, style: .continuous))
                        .shadow(color: .black.opacity(0.2), radius: 20, x: 0, y: 10)
                } else {
                    // Fallback icon if AppIcon not found
                    Image(systemName: "books.vertical.fill")
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 80, height: 80)
                        .foregroundStyle(.blue)
                }

                // App Name
                VStack(spacing: 8) {
                    Text("LotHelper")
                        .font(.system(size: 36, weight: .bold, design: .rounded))
                        .foregroundStyle(.primary)

                    Text("Book Scanner & Analyzer")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Loading Status
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.2)

                    Text(loadingStatus)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)
                }
                .padding(.bottom, 60)
            }
        }
    }
}

#Preview {
    SplashScreenView(loadingStatus: "Loading database...")
}
