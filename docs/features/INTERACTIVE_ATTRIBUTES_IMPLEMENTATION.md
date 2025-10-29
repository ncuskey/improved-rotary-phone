# Interactive Book Attributes Feature - Implementation

**Date**: October 28, 2025
**Status**: Backend Complete ✅ | iOS Ready ✅

**Latest Update**: Fixed AttributeError in `/api/books/{isbn}/estimate_price` endpoint (October 28, 2025)

---

## Feature Overview

Allow users to toggle book attributes (Hardcover/Paperback/Mass Market, Signed, First Edition) on the book detail page and see real-time ML price estimates update with delta values showing how each attribute affects the price.

**User Requirements**:
- Start with blank toggles (unchecked)
- Persist selections to database
- Show price change amounts (+$X.XX for each attribute)
- Include condition picker in the same UI

---

## Backend Implementation ✅ COMPLETE

### Bug Fix (October 28, 2025)

**Issue**: `/api/books/{isbn}/estimate_price` endpoint returned 500 errors with AttributeError

**Root Cause**: Line 1042 called `service.db.get_book()` which doesn't exist (should be `service.get_book()`)

**Fix**: Changed to use `service.get_book()` which returns properly parsed `BookEvaluation` object with `metadata`, `market`, and `bookscouter` attributes

**Test Result**: Endpoint now returns price estimates correctly:
```json
{
  "estimated_price": 9.95,
  "baseline_price": 9.75,
  "confidence": 0.57,
  "deltas": [{"attribute": "is_hardcover", "label": "Hardcover", "delta": 0.2, "enabled": true}],
  "model_version": "v1"
}
```

### 1. API Endpoints (isbn_web/api/routes/books.py)

#### POST `/api/books/{isbn}/estimate_price`
Dynamic price estimation with attribute overrides.

**Request**:
```json
{
  "condition": "Good",
  "is_hardcover": true,
  "is_paperback": false,
  "is_mass_market": false,
  "is_signed": false,
  "is_first_edition": true
}
```

**Response**:
```json
{
  "estimated_price": 15.50,
  "baseline_price": 13.00,
  "confidence": 0.85,
  "deltas": [
    {
      "attribute": "is_hardcover",
      "label": "Hardcover",
      "delta": 2.50,
      "enabled": true
    },
    {
      "attribute": "is_first_edition",
      "label": "First Edition",
      "delta": 0.75,
      "enabled": true
    }
  ],
  "model_version": "v1"
}
```

**How it works**:
1. Calculate baseline price (no attributes)
2. Calculate final price with user-selected attributes
3. For each enabled attribute, calculate delta by estimating price without that attribute
4. Return final price + deltas for UI display

#### PUT `/api/books/{isbn}/attributes`
Save user-selected attributes to database.

**Request**:
```json
{
  "cover_type": "Hardcover",
  "signed": false,
  "printing": "1st"
}
```

**Response**:
```json
{
  "success": true,
  "isbn": "9780123456789",
  "attributes": {
    "cover_type": "Hardcover",
    "signed": false,
    "printing": "1st"
  }
}
```

### 2. Database Method (shared/database.py)

**Added**: `update_book_attributes(isbn, cover_type, signed, printing)`

Updates the book's attribute fields and sets `updated_at` timestamp.

```python
def update_book_attributes(
    self,
    isbn: str,
    *,
    cover_type: Optional[str] = None,  # "Hardcover", "Paperback", "Mass Market"
    signed: bool = False,
    printing: Optional[str] = None      # "1st" for first edition
) -> None:
    """Update user-selected book attributes."""
```

---

## iOS Implementation 🚧 TODO

### Phase 1: Data Models

#### 1. Add to BookAPI.swift

```swift
struct EstimatePriceRequest: Codable {
    let condition: String
    let isHardcover: Bool?
    let isPaperback: Bool?
    let isMassMarket: Bool?
    let isSigned: Bool?
    let isFirstEdition: Bool?

    enum CodingKeys: String, CodingKey {
        case condition
        case isHardcover = "is_hardcover"
        case isPaperback = "is_paperback"
        case isMassMarket = "is_mass_market"
        case isSigned = "is_signed"
        case isFirstEdition = "is_first_edition"
    }
}

struct AttributeDelta: Codable, Identifiable {
    var id: String { attribute }
    let attribute: String
    let label: String
    let delta: Double
    let enabled: Bool
}

struct EstimatePriceResponse: Codable {
    let estimatedPrice: Double
    let baselinePrice: Double
    let confidence: Double
    let deltas: [AttributeDelta]
    let modelVersion: String

    enum CodingKeys: String, CodingKey {
        case estimatedPrice = "estimated_price"
        case baselinePrice = "baseline_price"
        case confidence
        case deltas
        case modelVersion = "model_version"
    }
}

struct UpdateAttributesRequest: Codable {
    let coverType: String?
    let signed: Bool
    let printing: String?

    enum CodingKeys: String, CodingKey {
        case coverType = "cover_type"
        case signed
        case printing
    }
}
```

#### 2. Add API Methods

```swift
// In BookAPI or new AttributesAPI class
func estimatePrice(
    isbn: String,
    condition: String,
    isHardcover: Bool?,
    isPaperback: Bool?,
    isMassMarket: Bool?,
    isSigned: Bool?,
    isFirstEdition: Bool?
) async throws -> EstimatePriceResponse {
    let request = EstimatePriceRequest(
        condition: condition,
        isHardcover: isHardcover,
        isPaperback: isPaperback,
        isMassMarket: isMassMarket,
        isSigned: isSigned,
        isFirstEdition: isFirstEdition
    )

    let url = URL(string: "\(baseURL)/api/books/\(isbn)/estimate_price")!
    var urlRequest = URLRequest(url: url)
    urlRequest.httpMethod = "POST"
    urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
    urlRequest.httpBody = try JSONEncoder().encode(request)

    let (data, _) = try await URLSession.shared.data(for: urlRequest)
    return try JSONDecoder().decode(EstimatePriceResponse.self, from: data)
}

func updateAttributes(
    isbn: String,
    coverType: String?,
    signed: Bool,
    printing: String?
) async throws {
    let request = UpdateAttributesRequest(
        coverType: coverType,
        signed: signed,
        printing: printing
    )

    let url = URL(string: "\(baseURL)/api/books/\(isbn)/attributes")!
    var urlRequest = URLRequest(url: url)
    urlRequest.httpMethod = "PUT"
    urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
    urlRequest.httpBody = try JSONEncoder().encode(request)

    let (_, _) = try await URLSession.shared.data(for: urlRequest)
}
```

### Phase 2: UI Components

#### 1. Add AttributesView to BookDetailViewRedesigned.swift

```swift
struct AttributesView: View {
    @Binding var condition: String
    @Binding var isHardcover: Bool
    @Binding var isPaperback: Bool
    @Binding var isMassMarket: Bool
    @Binding var isSigned: Bool
    @Binding var isFirstEdition: Bool
    @Binding var priceEstimate: Double

    let deltas: [AttributeDelta]
    let onAttributeChanged: () -> Void
    let onSave: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Book Attributes")
                .font(.headline)

            // Condition Picker
            VStack(alignment: .leading) {
                Text("Condition")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                Picker("Condition", selection: $condition) {
                    Text("New").tag("New")
                    Text("Like New").tag("Like New")
                    Text("Very Good").tag("Very Good")
                    Text("Good").tag("Good")
                    Text("Acceptable").tag("Acceptable")
                    Text("Poor").tag("Poor")
                }
                .pickerStyle(.segmented)
                .onChange(of: condition) { _ in onAttributeChanged() }
            }

            // Format (mutually exclusive)
            VStack(alignment: .leading) {
                Text("Format")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                HStack {
                    FormatToggle(
                        label: "Hardcover",
                        isSelected: $isHardcover,
                        delta: deltas.first { $0.attribute == "is_hardcover" }?.delta,
                        onToggle: {
                            if isHardcover {
                                isPaperback = false
                                isMassMarket = false
                            }
                            onAttributeChanged()
                        }
                    )

                    FormatToggle(
                        label: "Paperback",
                        isSelected: $isPaperback,
                        delta: deltas.first { $0.attribute == "is_paperback" }?.delta,
                        onToggle: {
                            if isPaperback {
                                isHardcover = false
                                isMassMarket = false
                            }
                            onAttributeChanged()
                        }
                    )

                    FormatToggle(
                        label: "Mass Market",
                        isSelected: $isMassMarket,
                        delta: deltas.first { $0.attribute == "is_mass_market" }?.delta,
                        onToggle: {
                            if isMassMarket {
                                isHardcover = false
                                isPaperback = false
                            }
                            onAttributeChanged()
                        }
                    )
                }
            }

            // Special Attributes
            VStack(alignment: .leading) {
                Text("Special Attributes")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                AttributeToggle(
                    label: "Signed/Autographed",
                    isOn: $isSigned,
                    delta: deltas.first { $0.attribute == "is_signed" }?.delta,
                    onToggle: onAttributeChanged
                )

                AttributeToggle(
                    label: "First Edition",
                    isOn: $isFirstEdition,
                    delta: deltas.first { $0.attribute == "is_first_edition" }?.delta,
                    onToggle: onAttributeChanged
                )
            }

            // Price Display
            HStack {
                Text("Estimated Price:")
                    .font(.headline)
                Spacer()
                Text("$\(String(format: "%.2f", priceEstimate))")
                    .font(.title2)
                    .bold()
                    .foregroundColor(.green)
            }
            .padding(.vertical, 8)
            .padding(.horizontal)
            .background(Color.green.opacity(0.1))
            .cornerRadius(8)

            // Save Button
            Button(action: onSave) {
                Text("Save Attributes")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(radius: 2)
    }
}

struct AttributeToggle: View {
    let label: String
    @Binding var isOn: Bool
    let delta: Double?
    let onToggle: () -> Void

    var body: some View {
        HStack {
            Toggle(label, isOn: $isOn)
                .onChange(of: isOn) { _ in onToggle() }

            if let delta = delta, delta != 0 {
                Text(delta > 0 ? "+$\(String(format: "%.2f", delta))" : "$\(String(format: "%.2f", delta))")
                    .font(.caption)
                    .foregroundColor(delta > 0 ? .green : .red)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(delta > 0 ? Color.green.opacity(0.1) : Color.red.opacity(0.1))
                    .cornerRadius(4)
            }
        }
    }
}

struct FormatToggle: View {
    let label: String
    @Binding var isSelected: Bool
    let delta: Double?
    let onToggle: () -> Void

    var body: some View {
        VStack {
            Button(action: {
                isSelected.toggle()
                onToggle()
            }) {
                Text(label)
                    .font(.caption)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 12)
                    .background(isSelected ? Color.blue : Color.gray.opacity(0.2))
                    .foregroundColor(isSelected ? .white : .primary)
                    .cornerRadius(8)
            }

            if let delta = delta, delta != 0 {
                Text(delta > 0 ? "+$\(String(format: "%.2f", delta))" : "$\(String(format: "%.2f", delta))")
                    .font(.caption2)
                    .foregroundColor(delta > 0 ? .green : .red)
            }
        }
    }
}
```

### Phase 3: Integration into BookDetailViewRedesigned

```swift
// Add state variables at top of BookDetailViewRedesigned
@State private var selectedCondition: String = "Good"
@State private var isHardcover: Bool = false
@State private var isPaperback: Bool = false
@State private var isMassMarket: Bool = false
@State private var isSigned: Bool = false
@State private var isFirstEdition: Bool = false
@State private var dynamicEstimate: Double? = nil
@State private var attributeDeltas: [AttributeDelta] = []
@State private var isUpdatingPrice: Bool = false

// Add this in the main body VStack, after existing sections:
if let isbn = book.isbn {
    AttributesView(
        condition: $selectedCondition,
        isHardcover: $isHardcover,
        isPaperback: $isPaperback,
        isMassMarket: $isMassMarket,
        isSigned: $isSigned,
        isFirstEdition: $isFirstEdition,
        priceEstimate: dynamicEstimate ?? book.estimatedPrice ?? 0.0,
        deltas: attributeDeltas,
        onAttributeChanged: {
            Task {
                await updatePriceEstimate(isbn: isbn)
            }
        },
        onSave: {
            Task {
                await saveAttributes(isbn: isbn)
            }
        }
    )
    .padding()
}

// Add these methods to BookDetailViewRedesigned:
private func updatePriceEstimate(isbn: String) async {
    isUpdatingPrice = true
    defer { isUpdatingPrice = false }

    do {
        let response = try await BookAPI.shared.estimatePrice(
            isbn: isbn,
            condition: selectedCondition,
            isHardcover: isHardcover ? true : nil,
            isPaperback: isPaperback ? true : nil,
            isMassMarket: isMassMarket ? true : nil,
            isSigned: isSigned ? true : nil,
            isFirstEdition: isFirstEdition ? true : nil
        )

        await MainActor.run {
            dynamicEstimate = response.estimatedPrice
            attributeDeltas = response.deltas
        }
    } catch {
        print("Failed to update price estimate: \(error)")
    }
}

private func saveAttributes(isbn: String) async {
    do {
        var coverType: String? = nil
        if isHardcover {
            coverType = "Hardcover"
        } else if isPaperback {
            coverType = "Paperback"
        } else if isMassMarket {
            coverType = "Mass Market"
        }

        let printing = isFirstEdition ? "1st" : nil

        try await BookAPI.shared.updateAttributes(
            isbn: isbn,
            coverType: coverType,
            signed: isSigned,
            printing: printing
        )

        // Success feedback
        await MainActor.run {
            // Show success message or haptic feedback
        }
    } catch {
        print("Failed to save attributes: \(error)")
        // Show error alert
    }
}
```

---

## Testing Plan

### Backend Tests

```bash
# Test estimate_price endpoint
curl -X POST http://localhost:8000/api/books/9780123456789/estimate_price \
  -H "Content-Type: application/json" \
  -d '{
    "condition": "Good",
    "is_hardcover": true,
    "is_first_edition": true
  }'

# Test update_attributes endpoint
curl -X PUT http://localhost:8000/api/books/9780123456789/attributes \
  -H "Content-Type: application/json" \
  -d '{
    "cover_type": "Hardcover",
    "signed": false,
    "printing": "1st"
  }'

# Verify in database
sqlite3 ~/.isbn_lot_optimizer/catalog.db \
  "SELECT isbn, cover_type, signed, printing FROM books WHERE isbn = '9780123456789'"
```

### iOS Tests

1. **Basic Toggle**: Toggle hardcover → see price update + delta display
2. **Multiple Attributes**: Enable hardcover + first edition → see cumulative effect
3. **Save & Reload**: Save attributes → close detail view → reopen → attributes still set
4. **Condition Change**: Change condition → price updates instantly
5. **Format Exclusivity**: Toggle hardcover → paperback/mass market auto-untoggle

---

## Current Status

✅ **Backend Complete**:
- API endpoints functional
- Database method implemented
- Delta calculation working
- Error handling in place

🚧 **iOS In Progress**:
- Data models: TODO
- API client methods: TODO
- UI components: TODO
- Integration: TODO

**Next Steps**:
1. Add data models to BookAPI.swift
2. Implement API client methods
3. Create AttributesView components
4. Integrate into BookDetailViewRedesigned
5. Test end-to-end flow
6. Add error handling and loading states

---

## Technical Notes

### Price Delta Calculation

The backend calculates deltas by:
1. Estimating price with ALL user-selected attributes → `final_price`
2. For each enabled attribute:
   - Create copy of metadata without that attribute
   - Estimate price → `no_attr_price`
   - Delta = `final_price - no_attr_price`

This shows the marginal contribution of each attribute to the final price.

### ML Model Integration

The feature uses the existing `MLPriceEstimator` with dynamically modified metadata:
- Creates deep copies of metadata objects
- Modifies `cover_type`, `signed`, `printing` fields
- Passes to `estimator.estimate_price()`
- No model retraining required - uses feature importance learned during training

### Performance

- Each attribute toggle triggers 1-2 API calls (~100-200ms each)
- Debouncing may be needed if users toggle rapidly
- Consider caching baseline price to avoid recalculation

---

## Future Enhancements

1. **Batch Attribute Updates**: Update multiple books at once
2. **Attribute Detection Confidence**: Show confidence scores for auto-detected attributes
3. **What-If Scenarios**: Show price for all attribute combinations in a table
4. **Historical Deltas**: Track how deltas change over time as model retrains
5. **Attribute Suggestions**: ML suggests likely attributes based on title/ISBN patterns
