"""
Collectible Book Detection Module

Detects if a book is likely to be collectible based on:
1. Famous person signatures (authors, celebrities, directors, etc.)
2. Award winner first editions
3. Printing errors/variations
4. Famous series with collectible editions
"""

import json
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass

from shared.models import BookMetadata


@dataclass
class CollectibleInfo:
    """Information about why a book is collectible."""
    is_collectible: bool
    collectible_type: str  # "signed_famous", "award_winner", "printing_error", "famous_series", "none"
    fame_multiplier: float  # Multiplier based on fame tier
    famous_person: Optional[str] = None
    fame_tier: Optional[str] = None
    awards: Optional[List[str]] = None
    notes: Optional[str] = None


class CollectibleDetector:
    """Detects collectible books and calculates value multipliers."""

    def __init__(self, fame_db_path: Optional[Path] = None):
        """Initialize with path to fame database."""
        if fame_db_path is None:
            fame_db_path = Path(__file__).parent / "famous_people.json"

        self.fame_db = self._load_fame_database(fame_db_path)
        self.name_variations = self.fame_db.get("name_variations", {})

        # Build reverse lookup for name variations
        self.name_to_canonical = {}
        for canonical, variations in self.name_variations.items():
            self.name_to_canonical[canonical.lower()] = canonical
            for variant in variations:
                self.name_to_canonical[variant.lower()] = canonical

        # Build flat lookup for all famous people
        self.famous_people = {}
        for category in self.fame_db:
            if category in ["_metadata", "name_variations"]:
                continue
            for person_name, person_data in self.fame_db[category].items():
                self.famous_people[person_name.lower()] = person_data

    def _load_fame_database(self, path: Path) -> Dict:
        """Load the fame database from JSON."""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load fame database: {e}")
            return {}

    def detect(
        self,
        metadata: Optional[BookMetadata],
        signed: bool = False,
        first_edition: bool = False,
        abebooks_data: Optional[Dict] = None
    ) -> CollectibleInfo:
        """
        Detect if a book is collectible and return multiplier.

        Args:
            metadata: Book metadata with title, authors, etc.
            signed: Whether the book is signed
            first_edition: Whether it's a first edition
            abebooks_data: AbeBooks marketplace data (for collectible pricing signals)

        Returns:
            CollectibleInfo with detection results
        """
        # Check for signed books by famous people
        if signed and metadata and metadata.authors:
            signed_info = self._check_signed_famous(metadata.authors)
            if signed_info.is_collectible:
                return signed_info

        # Check for first editions by famous authors (unsigned but still valuable)
        if first_edition and metadata and metadata.authors:
            first_edition_info = self._check_first_edition_famous(metadata.authors)
            if first_edition_info.is_collectible:
                return first_edition_info

        # Check for award winners (even unsigned first editions can be collectible)
        if first_edition and metadata and metadata.title:
            award_info = self._check_award_winner(metadata.title, metadata.authors)
            if award_info.is_collectible:
                return award_info

        # Check for printing errors/variations
        if metadata and metadata.title:
            printing_info = self._check_printing_error(metadata.title, metadata.isbn)
            if printing_info.is_collectible:
                return printing_info

        # Check for famous series with collectible editions
        if metadata and metadata.title:
            series_info = self._check_famous_series(metadata.title, first_edition)
            if series_info.is_collectible:
                return series_info

        # Not collectible
        return CollectibleInfo(
            is_collectible=False,
            collectible_type="none",
            fame_multiplier=1.0
        )

    def _normalize_author_name(self, name: str) -> List[str]:
        """
        Generate name variations for lookup.

        Handles "Last,First" format by converting to "First Last".
        Strips punctuation from names to handle "CLANCY, Tom." format.
        Returns list of normalized variations to try.

        Examples:
            "Herbert,Frank" -> ["herbert,frank", "frank herbert"]
            "Frank Herbert" -> ["frank herbert"]
            "Goodwin, Doris Kearns" -> ["goodwin, doris kearns", "doris kearns goodwin"]
            "CLANCY, Tom." -> ["clancy, tom.", "tom clancy"]
        """
        import string

        # Remove periods and other punctuation (except commas for parsing)
        name_cleaned = name.translate(str.maketrans('', '', string.punctuation.replace(',', '')))
        name_lower = name_cleaned.lower().strip()
        variations = [name_lower]

        # Check if original name contains comma (Last,First format)
        if ',' in name:
            parts = name_lower.split(',', 1)
            if len(parts) == 2:
                last_name = parts[0].strip()
                first_name = parts[1].strip()
                # Add "First Last" variation
                normalized = f"{first_name} {last_name}"
                variations.append(normalized)

        return variations

    def _check_signed_famous(self, authors: Tuple[str, ...]) -> CollectibleInfo:
        """Check if book is signed by a famous person."""
        for author in authors:
            # Generate name variations (handles "Last,First" format)
            name_variations = self._normalize_author_name(author)

            # Try each variation
            for author_variant in name_variations:
                # Check direct match
                if author_variant in self.famous_people:
                    person_data = self.famous_people[author_variant]
                    return CollectibleInfo(
                        is_collectible=True,
                        collectible_type="signed_famous",
                        fame_multiplier=person_data.get("signed_multiplier", 5.0),
                        famous_person=author,
                        fame_tier=person_data.get("fame_tier"),
                        notes=person_data.get("notes")
                    )

                # Check name variations database
                canonical = self.name_to_canonical.get(author_variant)
                if canonical:
                    canonical_lower = canonical.lower()
                    if canonical_lower in self.famous_people:
                        person_data = self.famous_people[canonical_lower]
                        return CollectibleInfo(
                            is_collectible=True,
                            collectible_type="signed_famous",
                            fame_multiplier=person_data.get("signed_multiplier", 5.0),
                            famous_person=canonical,
                            fame_tier=person_data.get("fame_tier"),
                            notes=person_data.get("notes")
                        )

        return CollectibleInfo(
            is_collectible=False,
            collectible_type="none",
            fame_multiplier=1.0
        )

    def _check_first_edition_famous(self, authors: Tuple[str, ...]) -> CollectibleInfo:
        """
        Check if book is a first edition by a famous author.

        First editions by famous authors (even unsigned) have collectible value.
        Uses a fraction of the signed multiplier to reflect market reality.
        """
        if not authors:
            return CollectibleInfo(
                is_collectible=False,
                collectible_type="none",
                fame_multiplier=1.0
            )

        for author in authors:
            # Generate name variations (handles "Last,First" format)
            name_variations = self._normalize_author_name(author)

            # Try each variation
            for author_variant in name_variations:
                # Check direct match
                if author_variant in self.famous_people:
                    person_data = self.famous_people[author_variant]
                    signed_mult = person_data.get("signed_multiplier", 5.0)

                    # First edition unsigned typically worth 20-30% of signed value
                    # Use 25% as reasonable market estimate
                    first_edition_mult = signed_mult * 0.25

                    # Minimum 2x multiplier for any famous author first edition
                    first_edition_mult = max(first_edition_mult, 2.0)

                    return CollectibleInfo(
                        is_collectible=True,
                        collectible_type="first_edition_famous",
                        fame_multiplier=first_edition_mult,
                        famous_person=author,
                        fame_tier=person_data.get("fame_tier"),
                        notes=f"First edition by {person_data.get('fame_tier', 'famous author')}"
                    )

                # Check name variations database
                canonical = self.name_to_canonical.get(author_variant)
                if canonical:
                    canonical_lower = canonical.lower()
                    if canonical_lower in self.famous_people:
                        person_data = self.famous_people[canonical_lower]
                        signed_mult = person_data.get("signed_multiplier", 5.0)

                        # First edition unsigned = 25% of signed value
                        first_edition_mult = signed_mult * 0.25
                        first_edition_mult = max(first_edition_mult, 2.0)

                        return CollectibleInfo(
                            is_collectible=True,
                            collectible_type="first_edition_famous",
                            fame_multiplier=first_edition_mult,
                            famous_person=canonical,
                            fame_tier=person_data.get("fame_tier"),
                            notes=f"First edition by {person_data.get('fame_tier', 'famous author')}"
                        )

        return CollectibleInfo(
            is_collectible=False,
            collectible_type="none",
            fame_multiplier=1.0
        )

    def _check_award_winner(self, title: str, authors: Optional[Tuple[str, ...]]) -> CollectibleInfo:
        """Check if book won major literary awards."""
        title_lower = title.lower()

        # Major awards to check for in title or author metadata
        major_awards = {
            "pulitzer": 3.0,
            "nobel": 5.0,
            "national book award": 2.5,
            "man booker": 2.5,
            "newbery": 2.0,
            "caldecott": 2.0,
            "hugo": 2.0,
            "nebula": 2.0
        }

        # Check title for award mentions
        for award_name, multiplier in major_awards.items():
            if award_name in title_lower:
                return CollectibleInfo(
                    is_collectible=True,
                    collectible_type="award_winner",
                    fame_multiplier=multiplier,
                    awards=[award_name],
                    notes=f"First edition of {award_name} winner"
                )

        # Check if author is in award_winners category
        if authors:
            for author in authors:
                # Use name normalization to handle "Last,First" format
                name_variations = self._normalize_author_name(author)

                for author_variant in name_variations:
                    canonical = self.name_to_canonical.get(author_variant, author_variant)
                    canonical_lower = canonical.lower()

                    if canonical_lower in self.famous_people:
                        person_data = self.famous_people[canonical_lower]
                        if person_data.get("fame_tier") == "award_winner":
                            awards = person_data.get("awards", [])
                            return CollectibleInfo(
                                is_collectible=True,
                                collectible_type="award_winner",
                                fame_multiplier=person_data.get("signed_multiplier", 2.0) * 0.3,  # Unsigned = 30% of signed value
                                awards=awards,
                                notes=f"First edition by {', '.join(awards)} winner"
                            )

        return CollectibleInfo(
            is_collectible=False,
            collectible_type="none",
            fame_multiplier=1.0
        )

    def _check_printing_error(self, title: str, isbn: Optional[str]) -> CollectibleInfo:
        """Check for known printing errors/variations that make books collectible."""
        title_lower = title.lower()

        # Known printing points database
        printing_points = {
            # Harry Potter printing errors
            "harry potter philosopher's stone": {
                "patterns": ["1 wand", "wand", "philosopher's stone"],
                "multiplier": 20.0,
                "notes": "Rare printing error - '1 wand' instead of '2 wands' on page 53"
            },
            "harry potter and the philosopher's stone": {
                "patterns": ["1 wand", "wand"],
                "multiplier": 20.0,
                "notes": "Rare printing error - '1 wand' instead of '2 wands'"
            },
            "harry potter sorcerer's stone": {
                "patterns": ["number line", "first printing"],
                "multiplier": 15.0,
                "notes": "First American edition printing point"
            }
        }

        for key_title, data in printing_points.items():
            if key_title in title_lower:
                # TODO: Would need to check actual book contents for "1 wand" text
                # For now, assume if title matches and marked as collectible, it qualifies
                return CollectibleInfo(
                    is_collectible=True,
                    collectible_type="printing_error",
                    fame_multiplier=data["multiplier"],
                    notes=data["notes"]
                )

        return CollectibleInfo(
            is_collectible=False,
            collectible_type="none",
            fame_multiplier=1.0
        )

    def _check_famous_series(self, title: str, first_edition: bool) -> CollectibleInfo:
        """Check if book is part of a famous collectible series."""
        title_lower = title.lower()

        # Famous series where first editions are collectible
        collectible_series = {
            "harry potter": {
                "multiplier": 10.0 if first_edition else 2.0,
                "notes": "Highly collectible series, especially UK first editions"
            },
            "lord of the rings": {
                "multiplier": 8.0 if first_edition else 1.5,
                "notes": "Classic fantasy series, first editions highly sought"
            },
            "dune": {
                "multiplier": 15.0 if first_edition else 2.0,
                "notes": "Science fiction masterwork"
            },
            "foundation": {
                "multiplier": 12.0 if first_edition else 2.0,
                "notes": "Asimov's classic series"
            },
            "game of thrones": {
                "multiplier": 6.0 if first_edition else 1.5,
                "notes": "A Song of Ice and Fire series"
            }
        }

        for series_name, data in collectible_series.items():
            if series_name in title_lower:
                return CollectibleInfo(
                    is_collectible=True,
                    collectible_type="famous_series",
                    fame_multiplier=data["multiplier"],
                    notes=data["notes"]
                )

        return CollectibleInfo(
            is_collectible=False,
            collectible_type="none",
            fame_multiplier=1.0
        )

    def should_bypass_bundle_rule(self, collectible_info: CollectibleInfo, base_price: float) -> bool:
        """
        Determine if the "under $10 bundle" rule should be bypassed.

        Args:
            collectible_info: Result from detect()
            base_price: Base price estimate before collectible multiplier

        Returns:
            True if this book should bypass the bundle rule
        """
        if not collectible_info.is_collectible:
            return False

        # Bypass for any collectible with fame multiplier > 5x
        if collectible_info.fame_multiplier >= 5.0:
            return True

        # Bypass for signed books by moderately famous people if base > $5
        if collectible_info.collectible_type == "signed_famous" and base_price > 5.0:
            return True

        # Bypass for printing errors
        if collectible_info.collectible_type == "printing_error":
            return True

        return False


# Singleton instance
_detector_instance = None

def get_collectible_detector() -> CollectibleDetector:
    """Get or create the singleton collectible detector."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = CollectibleDetector()
    return _detector_instance


def detect_collectible(
    metadata: Optional[BookMetadata],
    signed: bool = False,
    first_edition: bool = False,
    abebooks_data: Optional[Dict] = None
) -> CollectibleInfo:
    """
    Convenience function to detect collectible books.

    Args:
        metadata: Book metadata
        signed: Whether book is signed
        first_edition: Whether it's a first edition
        abebooks_data: AbeBooks marketplace data

    Returns:
        CollectibleInfo with detection results
    """
    detector = get_collectible_detector()
    return detector.detect(metadata, signed, first_edition, abebooks_data)
