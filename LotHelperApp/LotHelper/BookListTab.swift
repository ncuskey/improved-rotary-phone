import SwiftUI

/// Legacy wrapper maintained for backwards compatibility with earlier navigation setups.
/// Internally it defers to the new books tab implementation.
struct BookListTab: View {
    var body: some View {
        BooksTabView()
    }
}

#Preview {
    BookListTab()
}
