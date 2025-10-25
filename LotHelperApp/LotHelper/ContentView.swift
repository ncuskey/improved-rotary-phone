import SwiftUI
import SwiftData

struct ContentView: View {
    var body: some View {
        TabView {
            BooksTabView()
                .tabItem { Label("Books", systemImage: "book.closed") }

            LotRecommendationsView(
                bookscouter: false,
                bookscouterValueLabel: "",
                bookscouterValueRatio: 0.0
            )
                .tabItem { Label("Lots", systemImage: "square.grid.2x2") }

            NavigationStack {
                ScannerReviewView()
            }
            .tabItem { Label("Scan", systemImage: "barcode.viewfinder") }

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
        .background(DS.Color.background.ignoresSafeArea())
        .modelContainer(for: [CachedBook.self, CachedLot.self], inMemory: true)
    }
}

// NOTE: This preview referenced `LotDetailView`, which isn't currently in scope.
// To restore it later, re-enable this preview once `LotDetailView` exists in the project.
#if canImport(Foundation) // placeholder guard to keep file compiling; replace with actual type when available
// #Preview("Sample Lot Detail") {
//     NavigationStack {
//         LotDetailView(
//             lot: LotSuggestionDTO(
//                 lotID: 1,
//                 name: "Sample Fantasy Bundle",
//                 strategy: "author.series",
//                 bookIsbns: ["9780670855032", "9780670855049"],
//                 estimatedValue: 42.5,
//                 probabilityScore: 0.78,
//                 probabilityLabel: "High",
//                 sellThrough: 0.65,
//                 justification: ["Matching author branding", "Includes reader favorites"],
//                 displayAuthorLabel: "Robin Hobb collection",
//                 canonicalAuthor: "Robin Hobb",
//                 canonicalSeries: "Realm of the Elderlings",
//                 seriesName: "Liveship Traders",
//                 books: [
//                     BookEvaluationRecord(
//                         isbn: "9780670855032",
//                         originalIsbn: "9780670855032",
//                         condition: "Good",
//                         edition: nil,
//                         quantity: 1,
//                         estimatedPrice: 18.0,
//                         probabilityScore: 0.82,
//                         probabilityLabel: "High",
//                         justification: ["First edition", "Recent sales trending upward"],
//                         metadata: BookMetadataDetails(
//                             title: "Ship of Magic",
//                             subtitle: "(Liveship Traders #1)",
//                             authors: ["Robin Hobb"],
//                             creditedAuthors: nil,
//                             canonicalAuthor: "Robin Hobb",
//                             publisher: "Spectra",
//                             publishedYear: 1998,
//                             description: nil,
//                             thumbnail: "https://covers.openlibrary.org/b/isbn/9780670855032-L.jpg",
//                             categories: ["Fantasy"]
//                         ),
//                         booksrunValueLabel: nil,
//                         booksrunValueRatio: nil,
//                         rarity: nil
//                     )
//                 ],
//                 marketJson: nil
//             )
//         )
//     }
// }
#endif

