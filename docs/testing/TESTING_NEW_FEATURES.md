# Test Suite for New Features

This document describes the test suite for the newly implemented features in the LotHelper iOS app.

## Features Tested

### 1. TTS (Time-To-Sell) Display (Feature 3)
- ✅ TTS category calculation (Fast, Medium, Slow, Very Slow)
- ✅ Boundary condition testing (30d, 90d, 180d thresholds)
- ✅ Nil handling
- ✅ Extreme values (1 day, 365 days)
- ✅ Color mapping for categories

### 2. Default Book Condition (Feature 1)
- ✅ Custom default condition initialization
- ✅ Fallback to "Good" when not specified
- ✅ All valid condition values
- ✅ Edition notes formatting

### 3. Sorted Price List (Feature 4)
- ✅ Sorting order (highest to lowest)
- ✅ Nil value handling (placed at end)
- ✅ All-nil scenario
- ✅ Multi-source price sorting

### 4. eBay Listing Wizard (Feature 5)
- ✅ Draft initialization with book data
- ✅ Validation logic (price, condition, quantity)
- ✅ Editable title and description fields
- ✅ Item specifics persistence
- ✅ 5-step wizard structure

## Running iOS Tests

### Using Xcode
1. Open `LotHelper.xcodeproj` in Xcode
2. Press `Cmd+U` to run all tests
3. Or select specific test file:
   - **Product → Test** menu
   - Choose `LotHelperTests` scheme
   - Navigate to `NewFeaturesTests.swift`

### Using Command Line
```bash
cd /Users/nickcuskey/ISBN/LotHelperApp

# Run all tests
xcodebuild test \
  -scheme LotHelper \
  -destination 'platform=iOS Simulator,name=iPhone 15,OS=latest' \
  -only-testing:LotHelperTests/NewFeaturesTests

# Run specific test
xcodebuild test \
  -scheme LotHelper \
  -destination 'platform=iOS Simulator,name=iPhone 15,OS=latest' \
  -only-testing:LotHelperTests/NewFeaturesTests/testTTSCategoryFast
```

### Using Swift Testing in Terminal
```bash
cd /Users/nickcuskey/ISBN/LotHelperApp
swift test --filter NewFeaturesTests
```

## Test Coverage

### NewFeaturesTests.swift
Located at: `/Users/nickcuskey/ISBN/LotHelperApp/LotHelperTests/NewFeaturesTests.swift`

**Test Count:** 25+ tests

**Test Categories:**
- TTS Category Tests: 7 tests
- Default Condition Tests: 3 tests
- Price Sorting Tests: 3 tests
- eBay Listing Wizard Tests: 6 tests
- Integration Tests: 3 tests
- Edge Cases: 3 tests

## Test Results Interpretation

### Success Output
```
Test Suite 'NewFeaturesTests' passed
    ✓ TTS category for Fast books (≤30 days)
    ✓ TTS category for Medium books (31-90 days)
    ✓ TTS category for Slow books (91-180 days)
    ✓ TTS category for Very Slow books (>180 days)
    ... (remaining tests)

Executed 25 tests, with 0 failures in 0.234 seconds
```

### Failure Output
If a test fails, you'll see:
```
Test Case '-[LotHelperTests.NewFeaturesTests testTTSCategoryFast]' failed
Expected: "Fast"
Actual: "Medium"
```

## Manual Testing Checklist

After running automated tests, verify these manual scenarios:

### Feature 1: Default Condition
- [ ] Open Settings → Scanner
- [ ] Change default condition to "Very Good"
- [ ] Restart app
- [ ] Scan a book
- [ ] Verify condition defaults to "Very Good"

### Feature 3: TTS Display
- [ ] View Books tab
- [ ] Check book cards show TTS instead of probability
- [ ] Verify icons: 🐇 Fast, 🐢 Medium, 🕐 Slow, ⏳ Very Slow
- [ ] Verify colors: Green, Blue, Orange, Red
- [ ] Tap book to view details
- [ ] Verify TTS badge in header

### Feature 4: Sorted Price List
- [ ] Open book details
- [ ] Verify "Pricing" section shows vertical list
- [ ] Verify prices sorted high to low
- [ ] Verify "N/A" for missing prices
- [ ] Verify all 4 sources displayed

### Feature 5: Listing Preview
- [ ] Open book details → "List to eBay"
- [ ] Step through wizard (should be 5 steps now)
- [ ] Step 4: Verify preview shows summary
- [ ] Step 5: Verify "Final Review & Edit" screen
- [ ] Verify editable title field
- [ ] Verify editable description
- [ ] Verify inline price/condition editors
- [ ] Test "Edit Condition" button → jumps to Step 1
- [ ] Test "Edit Format" button → jumps to Step 2
- [ ] Test "Edit Price" button → jumps to Step 3
- [ ] Verify "Create Listing" button on Step 5 (not Step 4)

## Continuous Integration

To integrate with CI/CD:

### GitHub Actions Example
```yaml
name: iOS Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Tests
        run: |
          cd LotHelperApp
          xcodebuild test \
            -scheme LotHelper \
            -destination 'platform=iOS Simulator,name=iPhone 15' \
            -only-testing:LotHelperTests/NewFeaturesTests
```

## Debugging Failed Tests

### Common Issues

**1. Missing timeToSellDays data**
```
Error: TTS category is nil
Solution: Ensure backend is calculating and returning timeToSellDays in API responses
```

**2. Color comparison fails**
```
Note: Color objects can't be directly compared in unit tests
Solution: Tests use string representations of colors instead
```

**3. Draft validation fails unexpectedly**
```
Error: draft.isValid == false
Check: Ensure price > 0, quantity > 0, condition not empty
```

### Debug Tips

1. **Enable verbose test output:**
```bash
xcodebuild test -scheme LotHelper -verbose
```

2. **Run single test in isolation:**
```swift
@Test("TTS category for Fast books")
func testTTSCategoryFast() async throws {
    // Add print statements for debugging
    print("Testing TTS with 15 days")
    let book = makeBook(tts: 15)
    print("Result: \(book.ttsCategory ?? "nil")")
    #expect(book.ttsCategory == "Fast")
}
```

3. **Check test isolation:**
Ensure tests don't depend on execution order or shared state.

## Code Coverage

To generate code coverage report:

```bash
xcodebuild test \
  -scheme LotHelper \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  -enableCodeCoverage YES

# View coverage report
open ~/Library/Developer/Xcode/DerivedData/LotHelper-*/Logs/Test/*.xcresult
```

**Target Coverage:** >80% for new features

## Backend Tests

TTS calculation is tested in the Python backend:

```bash
cd /Users/nickcuskey/ISBN
python tests/test_tts_calculation.py
```

## Next Steps

1. **Run the test suite:**
   ```bash
   cd /Users/nickcuskey/ISBN/LotHelperApp
   xcodebuild test -scheme LotHelper -destination 'platform=iOS Simulator,name=iPhone 15'
   ```

2. **Review results:** Check for any failures

3. **Manual testing:** Follow the checklist above

4. **Report issues:** Document any bugs found during testing

## Test Maintenance

- **Add tests** when adding new features
- **Update tests** when changing behavior
- **Remove tests** when deprecating features
- **Keep tests fast** (<1 second per test)
- **Keep tests isolated** (no shared state)

## Support

If tests fail or you need help:
1. Check this document for debugging tips
2. Review test implementation in `NewFeaturesTests.swift`
3. Check related feature implementation
4. Verify data flow from backend to iOS

---

**Last Updated:** 2025-01-26
**Test Suite Version:** 1.0
**Compatible with:** iOS 17.0+, Swift 5.9+
