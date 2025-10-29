# eBay Listing Wizard - Testing Checklist

## Test Date: _____________
## Tester: _____________

---

## Pre-Test Setup

- [ ] Backend API server is running (`http://localhost:8000`)
- [ ] iOS app is built and running in simulator or device
- [ ] Have at least one scanned book in the Books tab

---

## Step 1: Price & Condition Testing

### Price Field Improvements
- [ ] **Price field visibility**: Confirm the price field has a blue border making it more prominent
- [ ] **Placeholder text**: Verify placeholder says "Tap to edit price"
- [ ] **Price source label**: Check that you see "From: eBay Sold Comps (90 days)" with chart icon
- [ ] **Info icon**: Confirm there's an info icon next to "Listing Price" header
- [ ] **Price is pre-filled**: Verify estimated price from book scan is populated

### Condition Descriptions
- [ ] **"Brand New" selected**:
  - Blue info panel appears below condition picker
  - Shows "eBay:" in blue bold text
  - Description: "A new, unread, unused book in perfect condition with no missing or damaged pages."

- [ ] **"Like New" selected**:
  - Description updates to: "A book that looks new but has been read. Cover has no visible wear. No missing or damaged pages, no creases, tears, underlining, or writing."

- [ ] **"Very Good" selected**:
  - Description updates to: "A book that does not look new but is in excellent condition. No obvious damage to cover. No missing or damaged pages, no creases, tears, underlining, or writing."

- [ ] **"Good" selected**:
  - Description updates to: "The book has been read but is in good condition. Very minimal damage to cover. Minimal pencil underlining OK, but no highlighting or writing in margins. No missing pages."

- [ ] **"Acceptable" selected**:
  - Description updates to: "A book with obvious wear. May have damage to cover or binding. Possible writing, underlining, and highlighting, but no missing pages."

### Quantity
- [ ] Quantity stepper works (can increment/decrement)
- [ ] Display shows "1 copy" (singular) when quantity is 1
- [ ] Display shows "X copies" (plural) when quantity > 1

### Navigation
- [ ] "Next" button is enabled when price > 0
- [ ] Tapping "Next" advances to Step 2

**Notes:**
```


```

---

## Step 2: Format & Language Testing

### Format Selection
- [ ] All format options are displayed in grid:
  - Hardcover
  - Paperback
  - Mass Market Paperback
  - Trade Paperback
  - Board Book
  - Leather Bound
  - Spiral Bound

- [ ] Selected format is highlighted in blue with white text
- [ ] Unselected formats have gray background
- [ ] Tapping a format immediately selects it

### Language Selection
- [ ] Language picker appears as a wheel
- [ ] Default language is "English"
- [ ] Can scroll through all language options:
  - English, Spanish, French, German, Italian, Portuguese, Chinese, Japanese, Korean, Other

### Navigation
- [ ] "Back" button returns to Step 1 with all selections preserved
- [ ] "Next" button advances to Step 3

**Notes:**
```


```

---

## Step 3: Special Features Testing

### Edition Features Section
- [ ] Section header: "Edition Features" is displayed

- [ ] **First Edition toggle**:
  - Icon: "1.circle.fill"
  - Title: "First Edition"
  - Description: "First published version of the book"
  - Can toggle on/off

- [ ] **First Printing toggle**:
  - Icon: "printer.fill"
  - Title: "First Printing"
  - Description: "First print run of this edition"
  - Can toggle on/off
  - **NOTE**: This is separate from First Edition ✓

- [ ] **Limited Edition toggle**:
  - Icon: "star.circle.fill"
  - Title: "Limited Edition"
  - Description: "Limited release or special edition"

- [ ] **Book Club Edition toggle**:
  - Icon: "person.3.fill"
  - Title: "Book Club Edition"
  - Description: "Book club release"

### Condition Features Section
- [ ] Section header: "Condition Features" is displayed
- [ ] Divider separates from Edition Features

- [ ] **Dust Jacket toggle**:
  - Icon: "book.closed"
  - Title: "Dust Jacket"
  - Description: "Book has original dust jacket"

- [ ] **Signed toggle**:
  - Icon: "signature"
  - Title: "Signed"
  - Description: "Signed or autographed by author"

- [ ] **Ex-Library toggle**:
  - Icon: "building.columns"
  - Title: "Ex-Library"
  - Description: "Former library book"

### Content Features Section
- [ ] Section header: "Content Features" is displayed
- [ ] Divider separates from Condition Features

- [ ] **Illustrated toggle**:
  - Icon: "photo.fill"
  - Title: "Illustrated"
  - Description: "Contains illustrations"

- [ ] **Large Print toggle**:
  - Icon: "textformat.size"
  - Title: "Large Print"
  - Description: "Large print edition"

### Custom Features Input
- [ ] Section header: "Custom Features (Optional)" is displayed
- [ ] Help text: "Add details buyers search for to improve discoverability"
- [ ] Text field with placeholder: "e.g., 'Autographed by Stephen King'"
- [ ] Tip text: "💡 Tip: Include author name, inscriptions, or special features"
- [ ] Can type custom text into field
- [ ] Text persists when navigating back and forth

### SEO Optimization Toggle
- [ ] Toggle appears after custom features
- [ ] Label: "SEO-Optimized Title"
- [ ] Description: "Use keyword-ranked title for better search visibility"
- [ ] Default state is ON (enabled)
- [ ] Can toggle off and on

### Visual Feedback
- [ ] When toggle is ON:
  - Background turns light blue (blue.opacity(0.1))
  - Checkmark icon is filled and blue
- [ ] When toggle is OFF:
  - Background is gray
  - Circle icon is empty

### Navigation
- [ ] "Back" button returns to Step 2 with all selections preserved
- [ ] "Next" button advances to Step 4

**Notes:**
```


```

---

## Step 4: Review & Confirm Testing

### Summary Display
- [ ] Book title is displayed with emoji "📚"
- [ ] Author name is displayed with emoji "✍️" (if available)
- [ ] Published year is displayed with emoji "📅" (if available)
- [ ] Price is formatted correctly: "$XX.XX"
- [ ] Quantity is shown: "📦 Quantity: X"
- [ ] Condition is shown: "✨ Condition: [Selected]"
- [ ] Format is shown: "📖 Format: [Selected]"
- [ ] Language is shown: "🌐 Language: [Selected]"

### Special Features Display
- [ ] If any features selected, "⭐️ Special Features:" header appears
- [ ] Each enabled feature is listed with bullet point
- [ ] Dust Jacket (if selected)
- [ ] First Edition (if selected)
- [ ] First Printing (if selected) ✓ **Check this is separate from First Edition**
- [ ] Signed (if selected)
- [ ] Ex-Library (if selected)
- [ ] Book Club Edition (if selected)
- [ ] Limited Edition (if selected)
- [ ] Custom features text (if provided)

### SEO Status
- [ ] If SEO enabled: "🚀 SEO-Optimized Title Enabled" is shown

### Navigation & Submission
- [ ] "Back" button returns to Step 3
- [ ] "Create Listing" button is enabled
- [ ] Tapping "Create Listing" shows loading state
- [ ] Button is disabled during submission

### Success Case
- [ ] After successful creation, wizard dismisses
- [ ] Returns to book detail view
- [ ] Console/debug output shows: "✓ Listing created: [Title]"

### Error Handling
- [ ] If error occurs, error alert is displayed
- [ ] Error message is readable
- [ ] Can dismiss error and try again

**Notes:**
```


```

---

## End-to-End Flow Testing

### Complete Flow Test
- [ ] Start from book detail page
- [ ] Tap "List to eBay" button
- [ ] Complete all 4 steps with various selections
- [ ] Successfully create listing
- [ ] Wizard dismisses properly

### Edge Cases
- [ ] Test with minimum fields (just price and condition)
- [ ] Test with all features enabled
- [ ] Test with custom features text containing special characters
- [ ] Test with very long custom features text
- [ ] Test back navigation preserves all selections
- [ ] Test that price field accepts decimal values

### Data Validation
- [ ] Cannot proceed from Step 1 if price is 0
- [ ] Cannot proceed from Step 1 if price is negative (should not be possible)
- [ ] Quantity cannot go below 1
- [ ] All user selections are reflected in final API payload

---

## Issues Found

### Critical Issues
```
Issue #:
Description:
Steps to Reproduce:
Expected Behavior:
Actual Behavior:
```

### Minor Issues
```
Issue #:
Description:
Steps to Reproduce:
Expected Behavior:
Actual Behavior:
```

### UI/UX Feedback
```
Suggestion:
Rationale:
```

---

## Summary

**Total Tests**: _____ / _____
**Pass Rate**: _____%

**Recommendation**:
- [ ] Ready to proceed with Priority 2 backend features
- [ ] Needs fixes before proceeding
- [ ] Requires additional testing

**Next Steps:**
```


```

---

## Tester Signature

_________________________________
Date: _____________
