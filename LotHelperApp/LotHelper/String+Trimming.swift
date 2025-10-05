import Foundation

public extension String {
    /// Returns the string trimmed of whitespace and newlines.
    var trimmed: String {
        trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Returns the string trimmed of whitespace/newlines if non-empty; otherwise returns nil.
    var trimmedNonEmpty: String? {
        let t = trimmed
        return t.isEmpty ? nil : t
    }
}

public extension Optional where Wrapped == String {
    /// Returns the optional string trimmed of whitespace/newlines if non-empty; otherwise returns nil.
    var trimmedNonEmpty: String? {
        guard let raw = self?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
        return raw
    }
}
