import SwiftUI

struct SettingsView: View {
    @AppStorage("scanner.autoSubmit") private var autoSubmit = true
    @AppStorage("scanner.hapticsEnabled") private var hapticsEnabled = true
    @AppStorage("scanner.defaultCondition") private var defaultCondition = "Good"
    @AppStorage("data.useLocalServer") private var useLocalServer = true
    @AppStorage("data.useProductionAPI") private var useProductionAPI = false

    @Environment(\.openURL) private var openURL

    private let conditions = ["Acceptable", "Good", "Very Good", "Like New", "New"]

    private let privacyURL = URL(string: "https://clevergirl.ai/privacy")!
    private let licensesURL = URL(string: "https://clevergirl.ai/licenses")!
    private let feedbackURL = URL(string: "mailto:lothelper@clevergirl.ai?subject=LotHelper%20Feedback")!

    var body: some View {
        NavigationStack {
            List {
                scannerSection
                dataSourcesSection
                developerSection
                aboutSection
                linksSection
            }
            .tint(DS.Color.primary)
            .listStyle(.insetGrouped)
            .scrollContentBackground(.hidden)
            .background(DS.Color.background)
            .navigationTitle("Settings")
        }
    }

    private var developerSection: some View {
        Section("Developer") {
            NavigationLink(destination: SoundPreviewView()) {
                Label("Sound Preview", systemImage: "speaker.wave.2")
            }
        }
    }

    private var scannerSection: some View {
        Section("Scanner") {
            Toggle(isOn: $autoSubmit) {
                Label("Auto-submit after scan", systemImage: "bolt.badge.clock")
            }
            Toggle(isOn: $hapticsEnabled) {
                Label("Vibration feedback", systemImage: "waveform.path")
            }

            Picker(selection: $defaultCondition) {
                ForEach(conditions, id: \.self) { condition in
                    Text(condition).tag(condition)
                }
            } label: {
                Label("Default book condition", systemImage: "book.closed")
            }
        }
        .accessibilityElement(children: .contain)
    }

    private var dataSourcesSection: some View {
        Section("Data Sources") {
            Toggle(isOn: $useLocalServer) {
                Label("Use local server", systemImage: "server.rack")
            }
            Toggle(isOn: $useProductionAPI) {
                Label("Use production API", systemImage: "antenna.radiowaves.left.and.right")
            }
        }
        .accessibilityElement(children: .contain)
    }

    private var aboutSection: some View {
        Section("About") {
            HStack {
                Text("App Version")
                Spacer()
                Text(appVersion)
                    .font(.caption)
                    .foregroundStyle(DS.Color.textSecondary)
                    .accessibilityLabel("Version \(appVersion)")
            }
        }
    }

    private var linksSection: some View {
        Section("Links") {
            Button {
                openURL(privacyURL)
            } label: {
                Label("Privacy Policy", systemImage: "lock.shield")
            }

            Button {
                openURL(licensesURL)
            } label: {
                Label("Open Source Licenses", systemImage: "doc.text.magnifyingglass")
            }

            Button {
                openURL(feedbackURL)
            } label: {
                Label("Send Feedback", systemImage: "envelope")
            }
        }
    }

    private var appVersion: String {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0"
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "1"
        return "\(version) (\(build))"
    }
}

#Preview {
    SettingsView()
}
