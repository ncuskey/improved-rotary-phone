from __future__ import annotations

# Load .env from project root so env vars are available everywhere
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import os
missing = [k for k in ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET") if not os.getenv(k)]
if missing:
    print(f"Warning: missing {', '.join(missing)}; Browse API will be unavailable.")

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .models import BookEvaluation
from .service import BookService
from .utils import normalise_isbn

DEFAULT_DB_PATH = Path.home() / ".isbn_lot_optimizer" / "catalog.db"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate and lot ISBNs for eBay resale using metadata and market signals.",
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DB_PATH, help="Path to the SQLite database (default: ~/.isbn_lot_optimizer/catalog.db).")
    parser.add_argument("--gui", dest="gui", action="store_true", help="Launch the Tkinter GUI (default behavior).")
    parser.add_argument("--no-gui", dest="gui", action="store_false", help="Disable the GUI and use CLI operations only.")
    parser.set_defaults(gui=True)

    parser.add_argument("--scan", metavar="ISBN", help="Scan a single ISBN via CLI mode.")
    parser.add_argument("--import", dest="import_path", type=Path, help="Import ISBNs from a CSV file.")
    parser.add_argument("--condition", default="Good", help="Condition to apply when scanning (default: Good).")
    parser.add_argument("--edition", help="Edition notes to record when scanning.")
    parser.add_argument("--skip-market", action="store_true", help="Skip eBay market lookups.")

    parser.add_argument("--ebay-app-id", help="eBay developer AppID for sell-through data.")
    parser.add_argument("--ebay-global-id", default="EBAY-US", help="eBay Global ID (default: EBAY-US).")
    parser.add_argument("--ebay-delay", type=float, default=1.0, help="Delay between market requests in seconds (default: 1.0).")
    parser.add_argument("--ebay-entries", type=int, default=20, help="Max results per market query (default: 20, max 100).")
    parser.add_argument("--metadata-delay", type=float, default=0.0, help="Delay between metadata lookups in seconds.")
    parser.add_argument("--refresh-metadata", action="store_true",
        help="Refresh Google/OpenLibrary metadata for all books and exit")
    parser.add_argument("--refresh-metadata-missing", action="store_true",
        help="Refresh metadata only for rows missing title/authors/publication_year/metadata_json")
    parser.add_argument("--refresh-lot-signals", action="store_true",
        help="Fetch eBay actives+sold comps for candidate lots, score them, persist to market_json")
    parser.add_argument("--limit", type=int, default=None,
        help="Optional limit for number of rows to process during refresh")

    args = parser.parse_args(argv)

    if args.ebay_entries <= 0 or args.ebay_entries > 100:
        parser.error("--ebay-entries must be between 1 and 100")
    if args.ebay_delay < 0:
        parser.error("--ebay-delay must be non-negative")
    if args.metadata_delay < 0:
        parser.error("--metadata-delay must be non-negative")

    return args


def summarise_book(evaluation: BookEvaluation) -> str:
    parts = [
        f"Title: {evaluation.metadata.title or '(untitled)'}",
        f"ISBN: {evaluation.isbn}",
        f"Probability: {evaluation.probability_label} ({evaluation.probability_score:.1f})",
        f"Estimated price: ${evaluation.estimated_price:.2f}",
        f"Condition: {evaluation.condition}",
    ]
    if evaluation.market and evaluation.market.sell_through_rate is not None:
        parts.append(f"Sell-through: {evaluation.market.sell_through_rate:.0%}")
    if evaluation.market and evaluation.market.sold_avg_price:
        parts.append(f"Avg sold price: ${evaluation.market.sold_avg_price:.2f}")
    if evaluation.justification:
        parts.append("Reasons:")
        parts.extend(f" - {reason}" for reason in evaluation.justification)
    return "\n".join(parts)


def ensure_database_path(path: Path) -> Path:
    resolved = path.expanduser()
    if resolved.is_dir():
        resolved = resolved / "catalog.db"
    if not resolved.parent.exists():
        resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    database_path = ensure_database_path(args.database)

    if args.refresh_metadata or args.refresh_metadata_missing:
        from . import db, metadata
        import sqlite3
        import requests

        conn = db.connect(args.database)
        if args.refresh_metadata_missing:
            rows = conn.execute("""
                SELECT isbn FROM books
                WHERE (metadata_json IS NULL OR metadata_json = '')
                   OR title IS NULL OR title = ''
                   OR authors IS NULL OR authors = ''
                   OR publication_year IS NULL
            """).fetchall()
        else:
            rows = conn.execute("SELECT isbn FROM books ORDER BY updated_at DESC").fetchall()

        if args.limit is not None:
            rows = rows[:args.limit]

        c_gb, c_ol, c_cache, c_hint, c_err, c_nf = 0, 0, 0, 0, 0, 0

        sess = requests.Session()
        try:
            for (isbn,) in rows:
                print(f"Metadata: {isbn} …", end=" ")
                try:
                    meta = metadata.fetch_metadata(isbn, session=sess)
                    if not meta:
                        c_nf += 1
                        print("not found")
                        continue
                    source = meta.get("source") or "unknown"
                    if source == "google_books":
                        c_gb += 1
                    elif source in ("open_library", "open_library_deep"):
                        c_ol += 1
                    elif source == "isbn_hint":
                        c_hint += 1
                    elif source == "cache":
                        c_cache += 1
                    db.update_book_metadata(conn, isbn, meta)
                    print(f"ok ({source})")
                except Exception as exc:
                    c_err += 1
                    print(f"error: {exc}")
        finally:
            sess.close()

        conn.commit()
        print(f"✅ Metadata refresh complete  | GB:{c_gb}  OL:{c_ol}  Hint:{c_hint}  Cache:{c_cache}  NotFound:{c_nf}  Errors:{c_err}")
        raise SystemExit(0)

    service = BookService(
        database_path=database_path,
        ebay_app_id=args.ebay_app_id,
        ebay_global_id=args.ebay_global_id,
        ebay_delay=args.ebay_delay,
        ebay_entries=args.ebay_entries,
        metadata_delay=args.metadata_delay,
    )

    try:
        if args.refresh_lot_signals:
            lots = service.build_lot_candidates()
            if args.limit is not None:
                lots = lots[: args.limit]
            for lot in lots:
                try:
                    service.enrich_lot_with_market(lot)
                    label = lot.series_name or lot.author or lot.name
                    sell_through = lot.sell_through
                    if isinstance(sell_through, (int, float)):
                        st_display = f"{sell_through:.2f}"
                    else:
                        st_display = "n/a"
                    print(
                        f"[{lot.probability_label}] {label}  "
                        f"price≈{lot.estimated_price:.2f}  ST={st_display}"
                    )
                except Exception as exc:
                    print("lot refresh error:", exc)
            service.save_lots(lots)
            raise SystemExit(0)

        if args.import_path:
            import_path = args.import_path.expanduser()
            if not import_path.exists():
                raise FileNotFoundError(f"CSV file not found: {import_path}")
            evaluations = service.import_csv(
                import_path,
                condition=args.condition,
                edition=args.edition,
                include_market=not args.skip_market,
            )
            print(f"Imported {len(evaluations)} ISBNs from {import_path}")
            for evaluation in evaluations:
                print("\n" + summarise_book(evaluation))
            return

        if args.scan:
            evaluation = service.scan_isbn(
                args.scan,
                condition=args.condition,
                edition=args.edition,
                include_market=not args.skip_market,
            )
            print(summarise_book(evaluation))
            return

        if args.gui:
            try:
                from .gui import BookEvaluatorGUI
            except RuntimeError as exc:
                print(f"GUI unavailable: {exc}", file=sys.stderr)
                print("Falling back to CLI. Use --no-gui to suppress this message.")
            else:
                gui = BookEvaluatorGUI(service)
                gui.run()
                return

        # CLI fallback: list stored books and lots
        books = service.list_books()
        lots = service.list_lots()
        if not books:
            print("No books have been scanned yet. Use --scan or --import to add data.")
        else:
            print("Stored book evaluations:")
            for book in books:
                print("\n" + summarise_book(book))
        if lots:
            print("\nLot recommendations:")
            for lot in lots:
                justification = "\n".join(lot.justification) if lot.justification else "No justification available"
                print(
                    f"- {lot.name} [{lot.strategy}] value ${lot.estimated_value:.2f} -> {lot.probability_label} ({lot.probability_score:.1f})\n"
                    f"  {justification}"
                )
    finally:
        service.close()


if __name__ == "__main__":
    main()
