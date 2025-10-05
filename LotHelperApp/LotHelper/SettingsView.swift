import SwiftUI

struct SettingsView: View {
    var body: some View {
        NavigationStack {
            List {
                Section("Appearance") {
                    Label("Brand theme enabled", systemImage: "paintbrush.pointed")
                        .font(.system(.subheadline, design: .rounded)).foregroundStyle(DS.Color.textSecondary)
                }

                Section("About") {
                    VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                        Text("LotHelper")
                            .bodyStyle().fontWeight(.semibold)
                        Text(appVersion)
                            .font(.caption)
                            .foregroundStyle(DS.Color.textSecondary)
                    }
                    .padding(.vertical, DS.Spacing.xs)
                }
            }
            .listStyle(.insetGrouped)
            .scrollContentBackground(.hidden)
            .background(DS.Color.background)
            .navigationTitle("Settings")
        }
    }

    private var appVersion: String {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0"
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "1"
        return "Version \(version) (\(build))"
    }
}

#Preview {
    SettingsView()
}
