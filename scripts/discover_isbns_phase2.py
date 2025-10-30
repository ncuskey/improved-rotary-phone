"""
Phase 2 Strategic ISBN Discovery

Targets specific training data deficiencies:
1. Priority 1: High-value books ($15-35 range)
2. Priority 2: Format coverage (trade paperbacks, mass market)
3. Priority 3: Genre balance (non-fiction, textbooks, children's)

Usage:
    python3 scripts/discover_isbns_phase2.py --priority 1 --limit 50 --output /tmp/priority1_isbns.txt
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class Phase2ISBNDiscovery:
    """Strategic ISBN discovery for Phase 2 training data expansion."""

    def __init__(self):
        """Initialize ISBN discovery with curated high-value targets."""

        # Priority 1: High-value books ($15-35 range)
        # Focus on collectible, out-of-print, and special editions
        self.priority1_isbns = {
            # Collectible Signed First Editions (typically $20-50+)
            "signed_collectible": [
                # Neil Gaiman signed first editions
                "9780060558123",  # American Gods (signed editions available)
                "9780380789016",  # Neverwhere
                "9780060853983",  # Anansi Boys

                # Stephen King signed first editions
                "9781501143786",  # The Outsider (signed)
                "9781501156762",  # The Institute (signed)
                "9781501182099",  # If It Bleeds (signed)

                # Margaret Atwood signed
                "9780385490818",  # The Testaments (signed)
                "9780385543781",  # The Handmaid's Tale special edition

                # Colleen Hoover signed (very hot market)
                "9781501110368",  # It Ends with Us (signed)
                "9781791392796",  # Verity (signed)

                # Fantasy signed editions
                "9780765326362",  # The Way of Kings (Sanderson signed)
                "9780756404079",  # The Name of the Wind (Rothfuss signed)
                "9780553801477",  # A Game of Thrones (special edition)
            ],

            # Out-of-print hardcovers (typically $15-30)
            "out_of_print": [
                # Classic sci-fi hardcovers
                "9780441013593",  # Dune (early hardcover editions)
                "9780345391803",  # Ender's Game hardcover
                "9780441569595",  # Neuromancer hardcover

                # Literary fiction hardcovers
                "9780060838676",  # One Hundred Years of Solitude
                "9780679422846",  # Beloved
                "9780060920845",  # To Kill a Mockingbird hardcover

                # Mystery/Thriller out-of-print
                "9780394588148",  # The Silence of the Lambs hardcover
                "9780385319577",  # Gone Girl hardcover early printing
                "9780316666343",  # The Firm hardcover
            ],

            # Special/Illustrated editions (typically $20-40)
            "special_editions": [
                # Harry Potter illustrated editions
                "9780545790352",  # Illustrated Sorcerer's Stone
                "9780545791328",  # Illustrated Chamber of Secrets
                "9781338274028",  # Illustrated Prisoner of Azkaban

                # Deluxe/Anniversary editions
                "9780544273443",  # The Hobbit 75th Anniversary
                "9780544003415",  # Lord of the Rings 50th Anniversary
                "9780670026326",  # The Catcher in the Rye special edition
            ],
        }

        # Priority 2: Format Coverage (trade paperbacks, mass market)
        self.priority2_isbns = {
            # Trade Paperbacks (CRITICAL - currently 0!)
            "trade_paperback": [
                # Contemporary fiction trade paperbacks
                "9780316492546",  # Where the Crawdads Sing
                "9780062457714",  # The Handmaid's Tale
                "9780385721790",  # The Kite Runner
                "9780385537858",  # Life of Pi
                "9780385349741",  # The Book Thief
                "9780316769174",  # The Catcher in the Rye

                # Literary fiction trade paperbacks
                "9780143127550",  # Educated
                "9780525559474",  # Becoming
                "9780316478526",  # The Midnight Library
                "9780316492528",  # The Seven Husbands of Evelyn Hugo

                # Non-fiction trade paperbacks
                "9781501139154",  # The Subtle Art of Not Giving a F*ck
                "9780735211292",  # Atomic Habits
                "9781501156939",  # Educated
                "9780143110637",  # Born a Crime

                # Mystery/Thriller trade paperbacks
                "9780593296691",  # The Silent Patient
                "9780525536291",  # The Woman in the Window
                "9780804138321",  # Gone Girl
                "9780062073556",  # The Girl on the Train
            ],

            # More Mass Market Paperbacks (expand from 10 to 25+)
            "mass_market": [
                # James Patterson thrillers
                "9781455515820",  # Along Came a Spider
                "9780446602761",  # Kiss the Girls
                "9780446606325",  # Cross

                # Nora Roberts romance
                "9780515153651",  # Vision in White
                "9780515149913",  # The Next Always
                "9780515156447",  # The Perfect Hope

                # Lee Child Jack Reacher
                "9780515153651",  # Killing Floor
                "9780515153644",  # Die Trying
                "9780515140170",  # Tripwire

                # Mystery classics mass market
                "9780062073556",  # The Girl on the Train
                "9780062297358",  # And Then There Were None
                "9780062490339",  # Murder on the Orient Express
            ],

            # More Signed Books (expand from 12 to 22+)
            "signed_expansion": [
                # Contemporary authors who frequently sign
                "9780316492540",  # Colleen Hoover signed editions
                "9781501110368",  # It Ends with Us signed
                "9781982137274",  # Verity signed

                # Taylor Jenkins Reid signed
                "9781501161933",  # Daisy Jones & The Six
                "9781501161930",  # The Seven Husbands signed

                # Kristin Hannah signed
                "9780312577223",  # The Nightingale
                "9781250178602",  # The Great Alone
            ],
        }

        # Priority 3: Genre Balance (non-fiction, textbooks, children's)
        self.priority3_isbns = {
            # Non-fiction (currently underrepresented)
            "business_self_help": [
                "9780735211292",  # Atomic Habits
                "9781501139154",  # The Subtle Art of Not Giving a F*ck
                "9780743269513",  # The 7 Habits of Highly Effective People
                "9781451639619",  # The 7 Habits (updated)
                "9780307465351",  # Outliers
                "9780062315007",  # Sapiens
                "9780062316110",  # Homo Deus
                "9780307887894",  # Thinking, Fast and Slow
                "9781476753836",  # How to Win Friends and Influence People
                "9780062457714",  # Lean In
                "9780307463746",  # Freakonomics
                "9780735213517",  # Measure What Matters
            ],

            "biography_memoir": [
                "9780143110637",  # Born a Crime
                "9781501138232",  # Steve Jobs
                "9780525559474",  # Becoming
                "9780307951540",  # The Diary of a Young Girl
                "9780316346627",  # The Glass Castle
                "9780062225672",  # Unbroken
                "9780060920098",  # The Autobiography of Malcolm X
                "9780385537858",  # When Breath Becomes Air
            ],

            "history_science": [
                "9780062316110",  # Sapiens
                "9780812968255",  # Team of Rivals
                "9780307387899",  # 1776
                "9780307476463",  # The Immortal Life of Henrietta Lacks
                "9780385537859",  # The Devil in the White City
                "9780307388735",  # Guns, Germs, and Steel
            ],

            # Textbooks (if profitable - high prices!)
            "textbooks": [
                # Medical/Nursing (very high resale value)
                "9780323694766",  # Fundamentals of Nursing
                "9780323401678",  # Anatomy & Physiology (Patton)
                "9780323551496",  # Pharmacology textbook

                # Engineering/Computer Science
                "9780134685991",  # Computer Networking (Kurose)
                "9780133594140",  # Operating System Concepts
                "9780134997193",  # Introduction to Algorithms

                # Business textbooks
                "9780134472089",  # Principles of Economics (Mankiw)
                "9780133506693",  # Financial Accounting
                "9780134475059",  # Marketing Management (Kotler)
            ],

            # Children's Books (currently missing)
            "childrens": [
                # Picture books
                "9780394800165",  # The Cat in the Hat
                "9780394900155",  # Green Eggs and Ham
                "9780399257360",  # The Very Hungry Caterpillar
                "9780062467867",  # Where the Wild Things Are

                # Middle grade
                "9780786838653",  # The Lightning Thief
                "9780439554930",  # Harry Potter Sorcerer's Stone (children's edition)
                "9780141354934",  # Diary of a Wimpy Kid
                "9780439023511",  # The Hunger Games (YA edition)
            ],
        }

    def get_isbns_for_priority(self, priority: int, limit: int = 50) -> List[str]:
        """
        Get ISBNs for a specific priority level.

        Args:
            priority: Priority level (1, 2, or 3)
            limit: Maximum number of ISBNs to return

        Returns:
            List of ISBNs
        """
        if priority == 1:
            # Priority 1: High-value books
            all_isbns = []
            for category, isbns in self.priority1_isbns.items():
                all_isbns.extend(isbns)
            return all_isbns[:limit]

        elif priority == 2:
            # Priority 2: Format coverage
            all_isbns = []
            for category, isbns in self.priority2_isbns.items():
                all_isbns.extend(isbns)
            return all_isbns[:limit]

        elif priority == 3:
            # Priority 3: Genre balance
            all_isbns = []
            for category, isbns in self.priority3_isbns.items():
                all_isbns.extend(isbns)
            return all_isbns[:limit]

        else:
            raise ValueError(f"Invalid priority: {priority}. Must be 1, 2, or 3.")

    def get_isbns_by_category(self, priority: int, category: str, limit: int = 50) -> List[str]:
        """
        Get ISBNs for a specific category within a priority.

        Args:
            priority: Priority level (1, 2, or 3)
            category: Category name (e.g., 'signed_collectible', 'trade_paperback')
            limit: Maximum number of ISBNs to return

        Returns:
            List of ISBNs
        """
        if priority == 1:
            isbns = self.priority1_isbns.get(category, [])
        elif priority == 2:
            isbns = self.priority2_isbns.get(category, [])
        elif priority == 3:
            isbns = self.priority3_isbns.get(category, [])
        else:
            raise ValueError(f"Invalid priority: {priority}")

        return isbns[:limit]

    def list_categories(self, priority: int) -> List[str]:
        """
        List available categories for a priority level.

        Args:
            priority: Priority level (1, 2, or 3)

        Returns:
            List of category names
        """
        if priority == 1:
            return list(self.priority1_isbns.keys())
        elif priority == 2:
            return list(self.priority2_isbns.keys())
        elif priority == 3:
            return list(self.priority3_isbns.keys())
        else:
            raise ValueError(f"Invalid priority: {priority}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Phase 2 Strategic ISBN Discovery',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Priority Levels:
  1: High-value books ($15-35 range)
     - signed_collectible: Collectible signed first editions
     - out_of_print: Out-of-print hardcovers
     - special_editions: Special/illustrated editions

  2: Format coverage (trade paperbacks, mass market)
     - trade_paperback: Trade paperbacks (CRITICAL - currently 0!)
     - mass_market: Mass market paperbacks
     - signed_expansion: Additional signed books

  3: Genre balance (non-fiction, textbooks, children's)
     - business_self_help: Business and self-help books
     - biography_memoir: Biographies and memoirs
     - history_science: History and science books
     - textbooks: Academic textbooks (high value)
     - childrens: Children's and YA books

Examples:
  # Get all Priority 1 ISBNs (high-value books)
  python3 scripts/discover_isbns_phase2.py --priority 1 --limit 40 --output /tmp/priority1.txt

  # Get only trade paperbacks (Priority 2)
  python3 scripts/discover_isbns_phase2.py --priority 2 --category trade_paperback --limit 20 --output /tmp/trade_paperbacks.txt

  # Get all non-fiction ISBNs (Priority 3)
  python3 scripts/discover_isbns_phase2.py --priority 3 --limit 30 --output /tmp/priority3.txt

  # List available categories for Priority 2
  python3 scripts/discover_isbns_phase2.py --priority 2 --list-categories
        """
    )

    parser.add_argument(
        '--priority',
        type=int,
        required=True,
        choices=[1, 2, 3],
        help='Priority level (1=high-value, 2=format coverage, 3=genre balance)'
    )

    parser.add_argument(
        '--category',
        type=str,
        help='Specific category within priority (optional)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Maximum number of ISBNs to output (default: 50)'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output file path (one ISBN per line)'
    )

    parser.add_argument(
        '--list-categories',
        action='store_true',
        help='List available categories for the specified priority'
    )

    args = parser.parse_args()

    # Initialize discovery
    discovery = Phase2ISBNDiscovery()

    # List categories if requested
    if args.list_categories:
        categories = discovery.list_categories(args.priority)
        print(f"\nAvailable categories for Priority {args.priority}:")
        for cat in categories:
            print(f"  - {cat}")
        return

    # Get ISBNs
    if args.category:
        isbns = discovery.get_isbns_by_category(args.priority, args.category, args.limit)
        print(f"\nFound {len(isbns)} ISBNs for Priority {args.priority}, category '{args.category}'")
    else:
        isbns = discovery.get_isbns_for_priority(args.priority, args.limit)
        print(f"\nFound {len(isbns)} ISBNs for Priority {args.priority}")

    # Output to file or stdout
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            for isbn in isbns:
                f.write(f"{isbn}\n")
        print(f"Wrote {len(isbns)} ISBNs to {output_path}")
    else:
        print("\nISBNs:")
        for isbn in isbns:
            print(f"  {isbn}")


if __name__ == '__main__':
    main()
