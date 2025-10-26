# Incremental Lot Update Optimization Plan

## Executive Summary

**Goal**: Reduce lot regeneration time from ~77 seconds to ~2-4 seconds by only fetching eBay pricing for affected lots.

**Current State**: Accept operation triggers 122 eBay API calls (~0.6s each = ~77s total)

**Target State**: Accept operation triggers 1-3 eBay API calls (~0.6-2s total)

**Impact**: 40-120x speedup for lot regeneration after accepting a book

---

## Current Architecture Analysis

### Call Flow

```
User accepts book
  ↓
POST /api/books/{isbn}/accept (books.py:334)
  ↓
service.accept_book(..., recalc_lots=False)
  ↓
background_tasks.add_task(service.update_lots_for_isbn, isbn)
  ↓
service.update_lots_for_isbn(isbn) [RUNS IN BACKGROUND]
  ↓
service.build_lot_candidates() ← PROBLEM: Generates ALL lots
  ↓
generate_lot_suggestions(books) or build_lots_with_strategies(books)
  ↓
_compose_lot() called for EACH lot (122 times)
  ↓
search_ebay_lot_comps() called INSIDE _compose_lot (lines 254-306)
  ↓
122 eBay API calls × ~0.6s = ~77 seconds
  ↓
Filter to affected lots (only saves 1-3 to database)
```

### Key Coupling Point

**File**: `isbn_lot_optimizer/lots.py`
**Function**: `_compose_lot()` (lines 218-323)
**Lines 254-306**: eBay pricing fetch is embedded INSIDE lot structure creation

```python
def _compose_lot(name, strategy, books, justification, ...):
    # Calculate individual book pricing
    individual_value = _sum_price(books)

    # ⚠️ COUPLING: Fetch lot market pricing DURING structure building
    if LOT_PRICING_AVAILABLE and strategy in ("series", "author"):
        lot_pricing = search_ebay_lot_comps(f"{search_author} lot", limit=50)
        # ... use pricing to calculate final_value

    return LotSuggestion(...)  # Returns complete lot with pricing
```

### Why This Is Slow

1. `build_lot_candidates()` generates ALL lot structures
2. Each structure generation calls `_compose_lot()`
3. `_compose_lot()` fetches eBay pricing inline
4. Result: 122 eBay API calls happen before we can filter

---

## Proposed Architecture

### Separation of Concerns

**Phase 1: Structure Generation** (fast, no API calls)
- Group books into logical lots (author, series, etc.)
- Calculate individual book pricing (already in database)
- Generate lot metadata (name, strategy, book ISBNs)
- **Result**: "Skeleton" lot structure without market pricing

**Phase 2: Pricing Enrichment** (slow, API calls)
- Take skeleton lots that need pricing
- Fetch eBay comps for each
- Merge pricing data into lot structures
- **Result**: Complete lots with market pricing

### New Call Flow

```
User accepts book
  ↓
service.update_lots_for_isbn(isbn)
  ↓
Phase 1: Generate ALL skeleton lots (NO eBay calls, fast)
  build_lot_skeletons() → List[LotSkeleton]
  ↓
Phase 2: Filter to affected lots (fast)
  [lot for lot in skeletons if isbn in lot.book_isbns]
  ↓
Phase 3: Enrich ONLY affected lots with pricing (1-3 eBay calls)
  for lot in affected_lots:
      enrich_lot_with_pricing(lot)
  ↓
Phase 4: Save enriched lots to database
  save_lots(enriched_lots)
```

### Data Structures

```python
@dataclass
class LotSkeleton:
    """Lot structure without market pricing."""
    name: str
    strategy: str
    book_isbns: List[str]
    books: List[BookEvaluation]
    individual_value: float  # Sum of book prices
    avg_probability: float
    justification: List[str]

    # Metadata for pricing enrichment
    search_term: Optional[str] = None  # e.g., "stephen king lot"
    series_name: Optional[str] = None
    author_name: Optional[str] = None

@dataclass
class EnrichedLot(LotSkeleton):
    """Lot with market pricing added."""
    lot_market_value: Optional[float] = None
    lot_optimal_size: Optional[int] = None
    lot_per_book_price: Optional[float] = None
    lot_comps_count: Optional[int] = None
    use_lot_pricing: bool = False
    estimated_value: float  # Final value (market or individual)
```

---

## Implementation Plan

### Step 1: Create Skeleton Generation

**New Function**: `_compose_lot_skeleton()` in `lots.py`

```python
def _compose_lot_skeleton(
    name: str,
    strategy: str,
    books: Sequence[BookEvaluation],
    justification: Sequence[str],
    series_name: Optional[str] = None,
    author_name: Optional[str] = None
) -> LotSkeleton | None:
    """Create lot structure WITHOUT fetching market pricing."""

    individual_value = _sum_price(books)
    if individual_value < 10:
        return None

    # Calculate probability without market data
    avg_probability = sum(b.probability_score for b in books) / len(books)
    probability_score = min(100.0, avg_probability + 8)

    # Determine search term for later pricing enrichment
    search_term = None
    if strategy in ("series", "author") and len(books) >= 2:
        if strategy == "series" and series_name:
            search_term = f"{series_name} series lot"
        elif strategy == "author" and author_name:
            search_term = f"{author_name} lot"

    return LotSkeleton(
        name=name,
        strategy=strategy,
        book_isbns=[b.isbn for b in books],
        books=list(books),
        individual_value=individual_value,
        avg_probability=probability_score,
        justification=list(justification),
        search_term=search_term,
        series_name=series_name,
        author_name=author_name,
    )
```

### Step 2: Create Pricing Enrichment

**New Function**: `enrich_lot_with_pricing()` in `lots.py`

```python
def enrich_lot_with_pricing(skeleton: LotSkeleton) -> EnrichedLot:
    """Fetch eBay pricing and merge into lot skeleton."""

    # Start with skeleton data
    enriched = EnrichedLot(**asdict(skeleton))
    enriched.estimated_value = skeleton.individual_value

    # Fetch pricing if applicable
    if skeleton.search_term:
        try:
            from isbn_lot_optimizer.market import search_ebay_lot_comps
            lot_pricing = search_ebay_lot_comps(skeleton.search_term, limit=50)

            if lot_pricing and lot_pricing.get("total_comps", 0) > 0:
                enriched.lot_comps_count = lot_pricing["total_comps"]
                enriched.lot_optimal_size = lot_pricing.get("optimal_lot_size")
                enriched.lot_per_book_price = lot_pricing.get("optimal_per_book_price")

                if enriched.lot_per_book_price:
                    lot_market_value = round(
                        enriched.lot_per_book_price * len(skeleton.books), 2
                    )
                    enriched.lot_market_value = lot_market_value
                    enriched.use_lot_pricing = True
                    enriched.estimated_value = lot_market_value

                    # Update justification with pricing
                    pricing_info = (
                        f"Market lot pricing: ${lot_market_value:.2f} "
                        f"(${enriched.lot_per_book_price:.2f}/book "
                        f"based on {enriched.lot_comps_count} eBay comps)"
                    )
                    enriched.justification.insert(0, pricing_info)
        except Exception as e:
            print(f"⚠️ Pricing enrichment failed: {e}")

    return enriched
```

### Step 3: Refactor Lot Generation

**Update**: `generate_lot_suggestions()` in `lots.py`

```python
def generate_lot_suggestions(
    books: Sequence[BookEvaluation],
    db_path: Optional[Path] = None,
    fetch_pricing: bool = True  # NEW PARAMETER
) -> List[LotSuggestion]:
    """Generate lot suggestions with optional pricing enrichment."""

    # Phase 1: Build skeletons (fast)
    skeletons = []
    for strategy in STRATEGIES:
        skeleton_results = _build_skeletons_for_strategy(strategy, books)
        skeletons.extend(skeleton_results)

    # Phase 2: Enrich with pricing (slow, optional)
    if fetch_pricing:
        suggestions = [enrich_lot_with_pricing(s) for s in skeletons]
    else:
        # Convert skeletons to suggestions without pricing
        suggestions = [skeleton_to_suggestion(s) for s in skeletons]

    return suggestions
```

### Step 4: Update Incremental Method

**Update**: `service.update_lots_for_isbn()` in `service.py`

```python
def update_lots_for_isbn(self, isbn: str) -> List[LotSuggestion]:
    """Incrementally update only affected lots."""

    normalized_isbn = normalise_isbn(isbn)
    if not normalized_isbn:
        return []

    # Phase 1: Build ALL skeletons WITHOUT pricing (fast, ~1s)
    all_skeletons = self.build_lot_skeletons()  # NEW METHOD

    # Phase 2: Filter to affected lots (fast)
    affected_skeletons = [
        s for s in all_skeletons
        if normalized_isbn in s.book_isbns
    ]

    if not affected_skeletons:
        return []

    print(f"  Found {len(affected_skeletons)} affected lots")

    # Phase 3: Enrich ONLY affected lots with pricing (1-3 eBay calls)
    enriched_lots = []
    for skeleton in affected_skeletons:
        enriched = enrich_lot_with_pricing(skeleton)
        enriched_lots.append(enriched)

    # Phase 4: Delete old lots and save new ones
    for lot in enriched_lots:
        self.db.delete_lot_by_name_and_strategy(lot.name, lot.strategy)

    self.save_lots(enriched_lots)

    return [lot_to_suggestion(lot) for lot in enriched_lots]
```

### Step 5: Testing

**Performance Test**:
```python
def test_incremental_update_performance():
    # Accept a book
    isbn = "9780307743657"

    # Time full regeneration
    start = time.time()
    service.recalculate_lots()
    full_time = time.time() - start
    # Expected: ~77 seconds, 122 eBay calls

    # Time incremental update
    start = time.time()
    service.update_lots_for_isbn(isbn)
    incremental_time = time.time() - start
    # Expected: ~2 seconds, 1-3 eBay calls

    speedup = full_time / incremental_time
    print(f"Speedup: {speedup:.1f}x")

    assert speedup > 20, "Should be at least 20x faster"
```

---

## Benefits

### Performance
- **Accept operation**: 77s → 2-4s (20-40x faster)
- **eBay API calls**: 122 → 1-3 per accept
- **User experience**: No waiting for lot updates

### Architecture
- **Separation of concerns**: Structure vs pricing
- **Testability**: Can test lot logic without API calls
- **Flexibility**: Can regenerate pricing without rebuilding structures

### Maintainability
- **Clearer code flow**: Explicit phases
- **Easier debugging**: Can inspect skeletons before pricing
- **Caching opportunities**: Can cache skeletons

---

## Risks & Mitigation

### Risk 1: Skeleton Cache Invalidation
**Problem**: How do we know when to rebuild skeletons?

**Mitigation**:
- Rebuild skeletons on any book add/remove
- Cache is acceptable to be slightly stale (lots don't change composition often)
- Add a "last_skeleton_rebuild" timestamp

### Risk 2: Complexity Increase
**Problem**: More code, more moving parts

**Mitigation**:
- Keep both old and new code paths initially
- Feature flag: `USE_INCREMENTAL_UPDATES`
- Gradual rollout with monitoring

### Risk 3: Database Schema Changes
**Problem**: Need to store skeleton data somewhere?

**Mitigation**:
- No schema changes needed
- Skeletons only exist in memory during regeneration
- Enriched lots saved to existing `lots` table

---

## Rollout Plan

### Phase 1: Foundation (Week 1)
- [ ] Create `LotSkeleton` and `EnrichedLot` data classes
- [ ] Implement `_compose_lot_skeleton()`
- [ ] Implement `enrich_lot_with_pricing()`
- [ ] Unit tests for skeleton generation

### Phase 2: Integration (Week 2)
- [ ] Refactor `generate_lot_suggestions()` to use skeletons
- [ ] Update `build_lot_candidates()` to support skeleton mode
- [ ] Integration tests with real data

### Phase 3: Incremental Update (Week 3)
- [ ] Update `update_lots_for_isbn()` to use new architecture
- [ ] Performance benchmarking
- [ ] Fix any bugs found in testing

### Phase 4: Production (Week 4)
- [ ] Feature flag rollout
- [ ] Monitor performance metrics
- [ ] Remove old code path once stable

---

## Success Metrics

- ✅ Accept operation completes in < 5 seconds
- ✅ eBay API calls reduced from 122 to 1-3 per accept
- ✅ Lot accuracy maintained (prices within 5% of full regeneration)
- ✅ No regressions in full lot regeneration performance
- ✅ Test coverage > 80% for new code

---

## Questions to Resolve

1. **Caching Strategy**: Should we cache skeletons between requests?
   - Pro: Even faster subsequent updates
   - Con: Cache invalidation complexity

2. **Pricing Staleness**: How old can pricing data be?
   - Option: Add `last_priced_at` timestamp
   - Option: Re-price all lots nightly

3. **Backward Compatibility**: Do we need to support old lot format?
   - Option: Migration script for existing lots
   - Option: Lazy migration (rebuild on first access)

---

## Next Steps

1. **Review this plan** with team
2. **Prototype skeleton generation** with real data
3. **Benchmark** to validate performance assumptions
4. **Begin implementation** following rollout plan
