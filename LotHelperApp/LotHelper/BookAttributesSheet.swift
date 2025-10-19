import SwiftUI

/// Book attributes that can be selected during scanning
struct BookAttributes {
    var condition: String = "Good"
    var coverType: String = "Unknown"
    var signed: Bool = false
    var firstEdition: Bool = false
    var printing: String = ""
    var purchasePrice: Double = 0.0

    /// Build edition notes string from attributes
    var editionNotes: String? {
        var notes: [String] = []

        if firstEdition {
            notes.append("First Edition")
        }
        if !printing.isEmpty {
            notes.append(printing)
        }
        if signed {
            notes.append("Signed")
        }

        return notes.isEmpty ? nil : notes.joined(separator: ", ")
    }
}

struct BookAttributesSheet: View {
    @Binding var attributes: BookAttributes
    @Environment(\.dismiss) private var dismiss

    private let conditions = ["Acceptable", "Good", "Very Good", "Like New", "New"]
    private let coverTypes = ["Hardcover", "Paperback", "Trade Paperback", "Mass Market", "Unknown"]
    private let printings = ["First Printing", "Second Printing", "Later Printing", "Book Club Edition"]

    var body: some View {
        NavigationView {
            Form {
                Section("Condition") {
                    Picker("Condition", selection: $attributes.condition) {
                        ForEach(conditions, id: \.self) { condition in
                            Text(condition).tag(condition)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                Section("Format") {
                    Picker("Cover Type", selection: $attributes.coverType) {
                        ForEach(coverTypes, id: \.self) { type in
                            Text(type).tag(type)
                        }
                    }
                }

                Section("Edition Details") {
                    Toggle("First Edition", isOn: $attributes.firstEdition)

                    Picker("Printing", selection: $attributes.printing) {
                        Text("Not specified").tag("")
                        ForEach(printings, id: \.self) { printing in
                            Text(printing).tag(printing)
                        }
                    }
                }

                Section("Special Attributes") {
                    Toggle("Signed / Autographed", isOn: $attributes.signed)
                }

                Section("Purchase Details") {
                    HStack {
                        Text("Purchase Price")
                        Spacer()
                        TextField("$0.00", value: $attributes.purchasePrice, format: .currency(code: "USD"))
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                            .frame(width: 100)
                    }
                }

                if let notes = attributes.editionNotes {
                    Section("Summary") {
                        Text(notes)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Book Attributes")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
        }
    }
}

#Preview {
    @Previewable @State var attributes = BookAttributes()
    BookAttributesSheet(attributes: $attributes)
}
