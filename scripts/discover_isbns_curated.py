"""
ISBN Discovery - Curated Lists for Training Data Collection

Generates curated lists of ISBNs for Priority 1 categories by leveraging
known popular books, series, authors, and award winners that are likely to have:
- First editions
- Signed copies
- Good sold comp data (10+ listings)

This is faster than eBay search integration for POC scaling.
"""

import argparse
import random
from pathlib import Path
from typing import Dict, List

# ===================================================================
# CURATED ISBN LISTS FOR PRIORITY 1 CATEGORIES
# ===================================================================

# Popular first edition hardcovers (literary fiction, bestsellers, award winners)
FIRST_EDITION_HARDCOVERS = [
    # Literary Fiction & Award Winners
    "9780060850524",  # To Kill a Mockingbird - Harper Lee
    "9780061120084",  # 1984 - George Orwell
    "9780141439518",  # Pride and Prejudice - Jane Austen
    "9780316769174",  # The Catcher in the Rye - J.D. Salinger
    "9780060256678",  # Where the Wild Things Are - Maurice Sendak
    "9780064404990",  # Charlotte's Web - E.B. White
    "9780061122415",  # The Alchemist - Paulo Coelho
    "9780061122419",  # The Book Thief - Markus Zusak
    "9780385720953",  # Extremely Loud & Incredibly Close - Jonathan Safran Foer
    "9780316034029",  # Freedom - Jonathan Franzen

    # Contemporary Bestsellers (likely first editions)
    "9780385537858",  # The Fault in Our Stars - John Green
    "9780316015844",  # Twilight - Stephenie Meyer
    "9780316055437",  # The Lost Symbol - Dan Brown
    "9780316228534",  # Gone Girl - Gillian Flynn
    "9780374292799",  # Life of Pi - Yann Martel
    "9780385537933",  # The Goldfinch - Donna Tartt
    "9780316246279",  # All the Light We Cannot See - Anthony Doerr
    "9780385538411",  # Cloud Atlas - David Mitchell
    "9780316017923",  # The Brief Wondrous Life of Oscar Wao - Junot Díaz
    "9780670921041",  # The Corrections - Jonathan Franzen

    # Fantasy & SciFi (collectible first editions)
    "9780439708180",  # Harry Potter and the Sorcerer's Stone - J.K. Rowling
    "9780439064873",  # Harry Potter and the Chamber of Secrets
    "9780439136365",  # Harry Potter and the Prisoner of Azkaban
    "9780439139601",  # Harry Potter and the Goblet of Fire
    "9780547928227",  # The Hobbit - J.R.R. Tolkien
    "9780547928210",  # The Lord of the Rings - J.R.R. Tolkien
    "9780765311788",  # Mistborn - Brandon Sanderson
    "9780765326355",  # The Way of Kings - Brandon Sanderson
    "9780316129084",  # The Lightning Thief - Rick Riordan
    "9780765326386",  # Steelheart - Brandon Sanderson

    # Mystery/Thriller (popular first editions)
    "9780307743657",  # Gone Girl - Gillian Flynn
    "9780307887894",  # The Girl with the Dragon Tattoo - Stieg Larsson
    "9780307454546",  # The Girl Who Played with Fire - Stieg Larsson
    "9780307269751",  # The Da Vinci Code - Dan Brown
    "9780307887900",  # Angels & Demons - Dan Brown
    "9780312427726",  # Still Life - Louise Penny
    "9781455586059",  # All the Light We Cannot See - Anthony Doerr
    "9780062073556",  # The Goldfinch - Donna Tartt
    "9780062315007",  # The Book Thief - Markus Zusak
    "9780385344227",  # The Girl on the Train - Paula Hawkins
]

# Books likely to have signed editions (popular contemporary authors)
SIGNED_HARDCOVER_CANDIDATES = [
    # Contemporary Authors (active signing)
    "9780385537858",  # The Fault in Our Stars - John Green (actively signs)
    "9780316246279",  # All the Light We Cannot See - Anthony Doerr
    "9780062073556",  # The Goldfinch - Donna Tartt
    "9780316228534",  # Gone Girl - Gillian Flynn
    "9781455586059",  # The Invention of Wings - Sue Monk Kidd
    "9780385537933",  # The Kitchen House - Kathleen Grissom
    "9780385344227",  # The Girl on the Train - Paula Hawkins
    "9780062315007",  # Ready Player One - Ernest Cline
    "9780316038379",  # The Martian - Andy Weir
    "9780316017923",  # The Brief Wondrous Life of Oscar Wao - Junot Díaz

    # Popular Series Authors (frequent signings)
    "9780765311788",  # Mistborn - Brandon Sanderson (prolific signer)
    "9780765326355",  # The Way of Kings - Brandon Sanderson
    "9780765326386",  # Steelheart - Brandon Sanderson
    "9780316129084",  # The Lightning Thief - Rick Riordan
    "9780316070638",  # The Son of Neptune - Rick Riordan
    "9781250010704",  # A Discovery of Witches - Deborah Harkness
    "9780307588364",  # 11/22/63 - Stephen King
    "9780307743657",  # Mr. Mercedes - Stephen King
    "9780062255655",  # American Gods - Neil Gaiman
    "9780062341518",  # The Ocean at the End of the Lane - Neil Gaiman

    # Award Winners (often signed at events)
    "9780374292799",  # Life of Pi - Yann Martel
    "9780385538411",  # Cloud Atlas - David Mitchell
    "9780670921041",  # The Corrections - Jonathan Franzen
    "9780316034029",  # Freedom - Jonathan Franzen
    "9780385537902",  # The Sympathizer - Viet Thanh Nguyen
    "9781455586066",  # Orphan Train - Christina Baker Kline
    "9780316245265",  # Little Fires Everywhere - Celeste Ng
    "9780385537858",  # Eleanor & Park - Rainbow Rowell
    "9780316217347",  # Daisy Jones & The Six - Taylor Jenkins Reid
    "9780385541213",  # Where the Crawdads Sing - Delia Owens
]

# Mass market paperbacks (underrepresented format)
MASS_MARKET_PAPERBACKS = [
    # Classic mass markets
    "9780345538376",  # Dune - Frank Herbert
    "9780345391803",  # The Hobbit - J.R.R. Tolkien
    "9780345339706",  # The Lord of the Rings (mass market)
    "9780553296983",  # Foundation - Isaac Asimov
    "9780553283686",  # I, Robot - Isaac Asimov
    "9780553213690",  # Fahrenheit 451 - Ray Bradbury
    "9780553272536",  # The Martian Chronicles - Ray Bradbury
    "9780441007462",  # Neuromancer - William Gibson
    "9780345333261",  # The Silmarillion - J.R.R. Tolkien
    "9780441172719",  # Dune Messiah - Frank Herbert

    # Mystery/Thriller mass markets
    "9780345466457",  # The Da Vinci Code (mass market)
    "9780345542983",  # Angels & Demons (mass market)
    "9780307454546",  # The Girl with the Dragon Tattoo (mass market)
    "9780307269751",  # Inferno - Dan Brown (mass market)
    "9781455566907",  # The Hunger Games (mass market)
    "9780439023527",  # Catching Fire (mass market)
    "9780439023511",  # Mockingjay (mass market)
    "9780425261712",  # Gone Girl (mass market)
    "9780425273982",  # The Girl on the Train (mass market)
    "9780451524935",  # 1984 (mass market)

    # Romance mass markets (popular format)
    "9780440245360",  # The Notebook - Nicholas Sparks
    "9780446676095",  # The Lucky One - Nicholas Sparks
    "9780451419408",  # Outlander - Diana Gabaldon
    "9780451465634",  # Dragonfly in Amber - Diana Gabaldon
    "9780440242840",  # A Walk to Remember - Nicholas Sparks
    "9780345535016",  # Fifty Shades of Grey (mass market)
    "9780345544476",  # Fifty Shades Darker (mass market)
    "9780345544995",  # Fifty Shades Freed (mass market)
    "9780515156447",  # The Time Traveler's Wife (mass market)
    "9780345528636",  # Me Before You - Jojo Moyes (mass market)
]

# Additional high-quality candidates
ADDITIONAL_CANDIDATES = [
    # YA with strong collector market
    "9780062024039",  # Divergent - Veronica Roth
    "9780062024046",  # Insurgent - Veronica Roth
    "9780062024077",  # Allegiant - Veronica Roth
    "9781423103349",  # The Sea of Monsters - Rick Riordan
    "9781423101482",  # The Titan's Curse - Rick Riordan
    "9781423101505",  # The Battle of the Labyrinth - Rick Riordan
    "9780316038379",  # The Martian - Andy Weir
    "9780062255655",  # American Gods - Neil Gaiman
    "9780062341518",  # The Ocean at the End of the Lane - Neil Gaiman
    "9780316217347",  # Daisy Jones & The Six - Taylor Jenkins Reid

    # Recent bestsellers
    "9780385541213",  # Where the Crawdads Sing - Delia Owens
    "9780593229385",  # The Midnight Library - Matt Haig
    "9780735219090",  # Where the Forest Meets the Stars - Glendy Vanderah
    "9780316454681",  # The Seven Husbands of Evelyn Hugo - Taylor Jenkins Reid
    "9780593133439",  # The Four Winds - Kristin Hannah
    "9780593243640",  # The Paris Apartment - Lucy Foley
    "9780593350256",  # The Last Thing He Told Me - Laura Dave
    "9780593156124",  # The Invisible Life of Addie LaRue - V.E. Schwab
    "9780593189641",  # Project Hail Mary - Andy Weir
    "9781250178602",  # The Guest List - Lucy Foley
]

# Round 2 Additions - Mystery/Thriller Series
MYSTERY_THRILLER_SERIES = [
    # Jack Reacher Series
    "9780515153651",  # Killing Floor - Lee Child
    "9780515140170",  # Die Trying - Lee Child
    "9780515140552",  # Tripwire - Lee Child

    # Alex Cross Series
    "9780446527880",  # Along Came a Spider - James Patterson
    "9780446364195",  # Kiss the Girls - James Patterson
    "9780446605601",  # Jack & Jill - James Patterson

    # Lincoln Rhyme Series
    "9780340767344",  # The Bone Collector - Jeffery Deaver
    "9780340767351",  # The Coffin Dancer - Jeffery Deaver

    # Millennium Series
    "9780307454546",  # The Girl with the Dragon Tattoo - Stieg Larsson
    "9780307269980",  # The Girl Who Played with Fire
    "9780307742537",  # The Girl Who Kicked the Hornet's Nest

    # Robert Langdon Series
    "9780307474278",  # The Da Vinci Code - Dan Brown
    "9780743275057",  # Angels & Demons - Dan Brown
    "9780307949486",  # The Lost Symbol - Dan Brown
    "9780385537858",  # Inferno - Dan Brown
]

# Round 2 - Contemporary Fiction Bestsellers
CONTEMPORARY_FICTION_ROUND2 = [
    # Colleen Hoover (highly collectible)
    "9781476753188",  # It Ends with Us
    "9781501193323",  # Verity
    "9781501110344",  # November 9
    "9781476786643",  # Ugly Love
    "9781476791531",  # Confess

    # Taylor Jenkins Reid
    "9781501161933",  # The Seven Husbands of Evelyn Hugo
    "9781524798628",  # Daisy Jones & The Six
    "9781524764746",  # Malibu Rising

    # Kristin Hannah
    "9780312577223",  # The Nightingale
    "9781250178602",  # The Four Winds
    "9780385721448",  # The Great Alone

    # Jodi Picoult
    "9780743496712",  # My Sister's Keeper
    "9780743454537",  # Nineteen Minutes
    "9781476776088",  # Small Great Things
]

# Round 2 - Classic Literature
CLASSIC_LITERATURE = [
    # American Classics
    "9780743273565",  # The Great Gatsby - F. Scott Fitzgerald
    "9780061120084",  # To Kill a Mockingbird - Harper Lee
    "9780141439518",  # Of Mice and Men - John Steinbeck
    "9780142437230",  # The Grapes of Wrath - John Steinbeck

    # British Classics
    "9780141439679",  # Pride and Prejudice - Jane Austen
    "9780141439556",  # Jane Eyre - Charlotte Brontë
    "9780141439662",  # Wuthering Heights - Emily Brontë
    "9780141439600",  # Great Expectations - Charles Dickens

    # Modern Classics
    "9780316769174",  # The Catcher in the Rye - J.D. Salinger
    "9780452284234",  # Animal Farm - George Orwell
    "9780451524935",  # 1984 - George Orwell
    "9780060850524",  # Brave New World - Aldous Huxley
]

# Round 2 - Science Fiction & Fantasy
SCIFI_FANTASY_ROUND2 = [
    # Brandon Sanderson (active signer)
    "9780765377135",  # The Final Empire (Mistborn #1)
    "9780765316882",  # The Well of Ascension
    "9780765316899",  # The Hero of Ages
    "9780765365279",  # The Way of Kings
    "9780765365286",  # Words of Radiance

    # Patrick Rothfuss
    "9780756404741",  # The Name of the Wind
    "9780756407919",  # The Wise Man's Fear

    # N.K. Jemisin (Hugo Award winner)
    "9780316229296",  # The Fifth Season
    "9780316229265",  # The Obelisk Gate
    "9780316229241",  # The Stone Sky

    # Classic SciFi
    "9780441172719",  # Dune - Frank Herbert
    "9780553293357",  # Foundation - Isaac Asimov
    "9780441007462",  # Neuromancer - William Gibson
]

# Round 2 - Romance Bestsellers
ROMANCE_BESTSELLERS = [
    # Nicholas Sparks
    "9780446525190",  # The Notebook
    "9780446605621",  # Message in a Bottle
    "9780446676090",  # A Walk to Remember
    "9780446698429",  # The Lucky One

    # Nora Roberts
    "9780515120653",  # Born in Fire
    "9780515142082",  # Birthright
    "9780425247433",  # The Witness

    # Emily Henry
    "9780593334836",  # Beach Read
    "9781984806734",  # People We Meet on Vacation
    "9780593441275",  # Book Lovers

    # Historical Romance
    "9780062347657",  # Outlander - Diana Gabaldon
    "9780385343268",  # Dragonfly in Amber - Diana Gabaldon
]

# Round 2 - Historical Fiction
HISTORICAL_FICTION = [
    # Kristin Hannah
    "9780312577223",  # The Nightingale
    "9780385721448",  # The Great Alone

    # Anthony Doerr
    "9781476746586",  # All the Light We Cannot See

    # Ken Follett
    "9780451166890",  # The Pillars of the Earth
    "9780525951049",  # World Without End

    # Paula McLain
    "9780345521309",  # The Paris Wife
    "9780804172486",  # Circling the Sun

    # Others
    "9780062277022",  # The Book Thief - Markus Zusak
    "9780385503228",  # Memoirs of a Geisha - Arthur Golden
    "9780670021192",  # The Help - Kathryn Stockett
]

# Round 2 - Non-Fiction Bestsellers
NONFICTION_BESTSELLERS = [
    # Memoirs
    "9780316010665",  # Becoming - Michelle Obama
    "9781501171345",  # Educated - Tara Westover
    "9781451648539",  # Steve Jobs - Walter Isaacson
    "9780385353229",  # Unbroken - Laura Hillenbrand

    # Self-Help
    "9781501139154",  # The Subtle Art of Not Giving a F*ck - Mark Manson
    "9780593230572",  # Atomic Habits - James Clear
    "9780735211292",  # Sapiens - Yuval Noah Harari

    # True Crime
    "9781982128715",  # I'll Be Gone in the Dark - Michelle McNamara
    "9780385352192",  # In Cold Blood - Truman Capote
]


def get_isbns_for_category(category: str, limit: int = 100) -> List[str]:
    """
    Get curated ISBNs for a specific category.

    Args:
        category: Collection category name
        limit: Maximum number of ISBNs to return

    Returns:
        List of ISBNs (deduplicated and shuffled)
    """
    if category == 'signed_hardcover':
        isbns = (
            SIGNED_HARDCOVER_CANDIDATES +
            CONTEMPORARY_FICTION_ROUND2 +
            SCIFI_FANTASY_ROUND2 +
            ROMANCE_BESTSELLERS +
            HISTORICAL_FICTION +
            NONFICTION_BESTSELLERS
        )
    elif category == 'first_edition_hardcover':
        isbns = (
            FIRST_EDITION_HARDCOVERS +
            CLASSIC_LITERATURE +
            MYSTERY_THRILLER_SERIES +
            SCIFI_FANTASY_ROUND2 +
            HISTORICAL_FICTION
        )
    elif category == 'mass_market_paperback':
        isbns = (
            MASS_MARKET_PAPERBACKS +
            MYSTERY_THRILLER_SERIES +
            ROMANCE_BESTSELLERS
        )
    else:
        # For other categories, combine all lists
        isbns = (
            FIRST_EDITION_HARDCOVERS +
            SIGNED_HARDCOVER_CANDIDATES +
            MASS_MARKET_PAPERBACKS +
            ADDITIONAL_CANDIDATES +
            MYSTERY_THRILLER_SERIES +
            CONTEMPORARY_FICTION_ROUND2 +
            CLASSIC_LITERATURE +
            SCIFI_FANTASY_ROUND2 +
            ROMANCE_BESTSELLERS +
            HISTORICAL_FICTION +
            NONFICTION_BESTSELLERS
        )

    # Deduplicate while preserving order
    seen = set()
    unique_isbns = []
    for isbn in isbns:
        if isbn not in seen:
            seen.add(isbn)
            unique_isbns.append(isbn)

    # Shuffle for variety
    random.shuffle(unique_isbns)

    # Return up to limit
    return unique_isbns[:limit]


def save_isbns_to_file(isbns: List[str], filepath: Path) -> None:
    """Save ISBNs to file (one per line)."""
    with open(filepath, 'w') as f:
        for isbn in isbns:
            f.write(f"{isbn}\n")
    print(f"Saved {len(isbns)} ISBNs to {filepath}")


def main():
    """Generate curated ISBN lists for training data collection."""
    parser = argparse.ArgumentParser(
        description='Generate curated ISBN lists for Priority 1 categories'
    )

    parser.add_argument(
        '--category',
        type=str,
        required=True,
        choices=['signed_hardcover', 'first_edition_hardcover', 'mass_market_paperback', 'all'],
        help='Category to generate ISBNs for'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Maximum number of ISBNs to generate (default: 100)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default='/tmp/training_isbns.txt',
        help='Output file path (default: /tmp/training_isbns.txt)'
    )

    args = parser.parse_args()

    # Generate ISBNs
    print(f"Generating {args.limit} ISBNs for category: {args.category}")
    isbns = get_isbns_for_category(args.category, args.limit)

    print(f"Generated {len(isbns)} unique ISBNs")

    # Save to file
    output_path = Path(args.output)
    save_isbns_to_file(isbns, output_path)

    print()
    print("=" * 70)
    print("ISBN list ready!")
    print("=" * 70)
    print(f"Category: {args.category}")
    print(f"Total ISBNs: {len(isbns)}")
    print(f"Output file: {output_path}")
    print()
    print("Next step: Run POC collector")
    print(f"  python3 scripts/collect_training_data_poc.py \\")
    print(f"    --category {args.category} \\")
    print(f"    --limit {args.limit} \\")
    print(f"    --isbn-file {output_path}")
    print()


if __name__ == '__main__':
    main()
