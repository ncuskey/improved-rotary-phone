import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            BooksTabView()
                .tabItem { Label("Books", systemImage: "book.closed") }

            LotRecommendationsView()
                .tabItem { Label("Lots", systemImage: "square.grid.2x2") }

            ScanTabView()
                .tabItem { Label("Scan", systemImage: "barcode.viewfinder") }

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
        .background(DS.Color.background.ignoresSafeArea())
    }
}

struct ScanTabView: View {
    var body: some View {
        NavigationStack {
            StartScreenView()
                .navigationTitle("Scan")
                .navigationBarTitleDisplayMode(.inline)
        }
    }
}

#Preview {
    ContentView()
}
