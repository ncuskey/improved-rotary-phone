import pytest  # type: ignore[import]

from isbn_lot_optimizer.author_match import author_key, similarity, probable_author_matches, cluster_authors


@pytest.mark.parametrize(
    "raw,expected_prefix",
    [
        ("Rowling, J. K.", "rowling"),  # drops initials
        ("J. K. Rowling", "rowling"),  # drops initials
        ("Rowling, Joanne K.", "joanne rowling"),  # keeps non-initial first
        ("Joanne K Rowling", "joanne rowling"),
        ("Stephen King", "stephen king"),
        ("King, Stephen", "stephen king"),
        ("Gabriel García Márquez", "gabriel garcia marquez"),  # accent stripping
        ("Arthur C. Clarke", "arthur clarke"),
        ("Clarke, Arthur C.", "arthur clarke"),
        ("Doe Jr., John A.", "john doe"),  # suffix removed, initial removed
        ("doe, john", "john doe"),  # case-insensitive
    ],
)
def test_author_key_normalization(raw: str, expected_prefix: str) -> None:
    key = author_key(raw)
    # Expect exact equality in these fixtures
    assert key == expected_prefix


def test_similarity_handles_last_name_match_boost() -> None:
    # Base canonical keys would be 'rowling' vs 'joanne rowling', ratio is low,
    # but heuristic should boost because last names match.
    a = "J. K. Rowling"
    b = "Joanne Rowling"
    s = similarity(a, b)
    assert s >= 0.85


def test_probable_author_matches_threshold_and_sorting() -> None:
    candidates = [
        "J K Rowling",
        "Joanne K Rowling",
        "Stephen King",
        "Rowling, J. K.",
        "King, Stephen",
        "Jane Austen",
    ]
    matches = probable_author_matches("Rowling, Joanne", candidates, threshold=0.8)
    # Ensure only Rowling variants are included
    assert all("rowling" in author_key(name) for name, _ in matches)
    # Ensure sorted by score desc
    scores = [s for _, s in matches]
    assert scores == sorted(scores, reverse=True)


def test_cluster_authors_groups_variants() -> None:
    names = ["Rowling, J. K.", "J K Rowling", "Joanne K Rowling", "Stephen King", "King, Stephen"]
    clusters = cluster_authors(names)
    # Expect at least two clusters: one for Rowling variants, one for King variants
    # Determine by checking unique canonical keys present
    keys = {author_key(n) for n in names}
    keys.discard("")  # remove any empties
    assert len(clusters) >= 2
    # Rowling forms map to a cluster key containing 'rowling' as last token
    rowling_keys = [k for k in clusters.keys() if k.split() and k.split()[-1] == "rowling"]
    assert rowling_keys, "Expected a cluster for Rowling variants"
    for k in rowling_keys:
        # members should be drawn from provided names and include at least 2 variants
        assert len(clusters[k]) >= 2
