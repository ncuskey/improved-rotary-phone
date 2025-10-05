import Foundation

/// Convenience wrapper retained for legacy call sites.
func postISBNToBackend(_ isbn: String, completion: @escaping (BookInfo?) -> Void) {
    BookAPI.postISBNToBackend(isbn, completion: completion)
}
