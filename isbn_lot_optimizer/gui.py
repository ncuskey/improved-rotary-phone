from __future__ import annotations

import threading
import sys
import hashlib
import platform
from datetime import datetime
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional, Any, Iterable, Dict

import json


try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk, Toplevel
except Exception as exc:  # pragma: no cover - Tk not available
    raise RuntimeError("Tkinter is required for the GUI but is not available") from exc

try:  # pragma: no cover - winsound only exists on Windows
    import winsound  # type: ignore
except Exception:  # pragma: no cover - ignore import errors on non-Windows
    winsound = None  # type: ignore

try:  # pragma: no cover - chime optional dependency
    import chime  # type: ignore
except Exception:
    chime = None  # type: ignore

from .clipboard_import import ImportOptions, parse_prices_from_clipboard_text, parse_isbns_from_text
from .models import BookEvaluation, LotSuggestion
from .service import BookService
from .constants import COVER_CHOICES
from .utils import normalise_isbn, isbn10_to_isbn13, compute_isbn10_check_digit
from .author_match import cluster_authors

# Optional cover image support is imported lazily in _load_cover_image to avoid a hard dependency
# on PIL/requests at import time and to prevent static analysis errors when they aren't installed.

COVER_CACHE_DIR = Path.home() / ".isbn_lot_optimizer" / "covers"
IS_MAC = platform.system() == "Darwin"

# -----------------------------
# Sorting helpers for Treeview
# -----------------------------
def _tree_sortby(tree, col, descending=False, cast=None):
    """Sort a ttk.Treeview by a column. `cast` can convert values (e.g., to float)."""
    def _safe(s):
        s = "" if s is None else str(s)
        return s.strip()

    rows = []
    for iid in tree.get_children(""):
        val = tree.set(iid, col)
        val = _safe(val)
        if cast:
            try:
                val = cast(val)
            except Exception:
                # if cast fails, put non-numeric near the end
                val = (1, val.lower())
        rows.append((val, iid))

    rows.sort(reverse=descending, key=lambda x: x[0])

    # reinsert in sorted order
    for idx, (_, iid) in enumerate(rows):
        tree.move(iid, "", idx)

    # toggle sort direction on next click
    tree.heading(col, command=lambda: _tree_sortby(tree, col, not descending, cast=cast))


def _as_float(s):
    # e.g., "12", "12.34", "$12.34", "1,234.56"
    try:
        return float(s.replace("$", "").replace(",", ""))
    except Exception:
        return float("inf")  # push non-numeric to the end


def _as_int(s):
    try:
        return int(s.replace(",", ""))
    except Exception:
        return 10**18  # big number -> end


class BookEvaluatorGUI:
    def __init__(self, service: BookService) -> None:
        self.service = service
        self.root = tk.Tk()
        self.root.title("ISBN Resale Evaluator")
        self.root.geometry("1100x720")

        self._lot_by_iid = {}  # map Treeview row -> lot object
        self._book_by_iid = {}  # map Treeview row -> BookEvaluation

        self.isbn_var = tk.StringVar()
        self.condition_var = tk.StringVar(value="Good")
        self.edition_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.search_var = tk.StringVar()

        # cover image cache and handle to prevent GC
        self._image_cache: dict[str, Any] = {}
        self._cover_images: list[Any] = []
        self._warned_no_pil: bool = False
        self._clipboard_import_options = ImportOptions(
            exclude_large_print=False,
            last_n_days=180,
        )
        self._winsound_available = winsound is not None
        self._chime_available = chime is not None
        if chime is not None:
            try:
                chime.theme("pokemon")
            except Exception:
                try:
                    chime.theme("mario")
                except Exception:
                    pass
        self._sound_settings: dict[str, str] = {
            "start": "chime_info" if self._chime_available else "system",
            "complete": "chime_success" if self._chime_available else "winsound",
            "lot": "chime_warning" if self._chime_available else "winsound",
        }
        self._sound_pref_window: Optional[tk.Toplevel] = None
        self._sound_pref_vars: dict[str, tk.StringVar] = {}
        self._sound_option_labels: list[str] = []
        self._sound_label_to_value: dict[str, str] = {}

        self._settings_path = Path.home() / ".isbn_lot_optimizer" / "settings.json"
        self._load_sound_settings()

        self._cover_prefetch_thread: Optional[threading.Thread] = None
        self._refresh_thread: Optional[threading.Thread] = None
        self._progress_task: Optional[str] = None
        self._progress_total = 0
        self._progress_done = 0
        self._progress_label: str = ""
        self._progress_reset_job: Optional[str] = None

        self._build_layout()
        # Check image support once for user feedback
        self._image_supported = self._check_image_support()
        if not self._image_supported:
            self._set_status("Cover thumbnails disabled: install Pillow to enable covers.")
        self._populate_tables()
        self._trigger_cover_prefetch()

    # ------------------------------------------------------------------
    # UI construction

    def _build_layout(self) -> None:
        # Use grid on the root so the status bar stays visible at the bottom
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        # Central body container takes the expandable grid cell
        self.body = ttk.Frame(self.root)
        self.body.grid(row=0, column=0, sticky="nsew")

        input_frame = ttk.Frame(self.body, padding=10)
        input_frame.pack(fill="x")

        ttk.Label(input_frame, text="ISBN:").grid(row=0, column=0, sticky="w")
        isbn_entry = ttk.Entry(input_frame, textvariable=self.isbn_var, width=30)
        isbn_entry.grid(row=0, column=1, padx=5)
        isbn_entry.focus_set()
        # Trigger scan when pressing Enter (many barcode scanners send an Enter keystroke)
        isbn_entry.bind("<Return>", lambda e: self._on_scan())
        isbn_entry.bind("<KP_Enter>", lambda e: self._on_scan())

        ttk.Label(input_frame, text="Condition:").grid(row=0, column=2, sticky="w")
        condition_combo = ttk.Combobox(
            input_frame,
            textvariable=self.condition_var,
            values=["New", "Like New", "Very Good", "Good", "Acceptable", "Poor"],
            width=15,
            state="readonly",
        )
        condition_combo.grid(row=0, column=3, padx=5)

        ttk.Label(input_frame, text="Edition notes:").grid(row=0, column=4, sticky="w")
        edition_entry = ttk.Entry(input_frame, textvariable=self.edition_var, width=25)
        edition_entry.grid(row=0, column=5, padx=5)

        scan_button = ttk.Button(input_frame, text="Scan ISBN", command=self._on_scan)
        scan_button.grid(row=0, column=6, padx=5)

        import_button = ttk.Button(input_frame, text="Import CSV", command=self._on_import)
        import_button.grid(row=0, column=7, padx=5)

        refresh_button = ttk.Button(input_frame, text="Refresh Selected", command=self.refresh_selected)
        refresh_button.grid(row=0, column=8, padx=5)

        modify_button = ttk.Button(input_frame, text="Modify Books", command=self._on_modify_books)
        modify_button.grid(row=0, column=9, padx=5)

        clear_db_button = ttk.Button(input_frame, text="Clear Database", command=self._on_clear_database)
        clear_db_button.grid(row=0, column=10, padx=5)

        # Refresh all BooksRun offers (bulk)
        refresh_booksrun_all_button = ttk.Button(
            input_frame, text="Refresh BooksRun (All)", command=self.refresh_booksrun_all
        )
        refresh_booksrun_all_button.grid(row=0, column=11, padx=5)

        # Search row
        ttk.Label(input_frame, text="Search:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        search_entry = ttk.Entry(input_frame, textvariable=self.search_var, width=40)
        search_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=(8, 0))
        search_entry.bind("<Return>", lambda e: self._on_search())
        search_entry.bind("<KP_Enter>", lambda e: self._on_search())
        search_button = ttk.Button(input_frame, text="Search", command=self._on_search)
        search_button.grid(row=1, column=4, padx=5, pady=(8, 0))
        clear_button = ttk.Button(input_frame, text="Clear", command=self._on_clear_search)
        clear_button.grid(row=1, column=5, padx=5, pady=(8, 0))

        # Allow search entry to expand
        input_frame.columnconfigure(1, weight=1)
        input_frame.columnconfigure(5, weight=1)

        # --- Lot type toggle bar ---
        lotbar = ttk.Frame(self.body)
        lotbar.pack(side="top", fill="x", padx=8, pady=(8, 0))

        ttk.Label(lotbar, text="Form lots by:").pack(side="left", padx=(0, 6))

        self.var_lot_author = tk.BooleanVar(value=True)
        self.var_lot_series = tk.BooleanVar(value=True)
        self.var_lot_genre = tk.BooleanVar(value=False)

        ttk.Checkbutton(lotbar, text="Author", variable=self.var_lot_author,
                        command=self._on_lot_option_change).pack(side="left", padx=8)
        ttk.Checkbutton(lotbar, text="Series", variable=self.var_lot_series,
                        command=self._on_lot_option_change).pack(side="left", padx=8)
        ttk.Checkbutton(lotbar, text="Genre", variable=self.var_lot_genre,
                        command=self._on_lot_option_change).pack(side="left", padx=8)


        # Books table
        books_frame = ttk.LabelFrame(self.body, text="Evaluated Books", padding=10)
        books_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        book_columns = (
            "isbn",
            "title",
            "authors",
            "edition",
            "cover",
            "printing",
            "price",
            "probability",
            "quantity",
            "condition",
            "sell_through",
            "booksrun_cash",
            "booksrun_credit",
            "booksrun_value",
            "scanned",
        )
        self.books_tree = ttk.Treeview(
            books_frame,
            columns=book_columns,
            show="headings",
            height=12,
            selectmode="extended",
        )
        heading_overrides = {
            "booksrun_cash": "BooksRun Cash",
            "booksrun_credit": "BooksRun Credit",
            "booksrun_value": "BooksRun Value",
        }
        for col in book_columns:
            heading = heading_overrides.get(col, col.replace("_", " ").title())
            cast = _as_float if col in {"price", "booksrun_cash", "booksrun_credit"} else (_as_int if col in {"quantity"} else None)
            self.books_tree.heading(col, text=heading, command=lambda c=col, func=cast: _tree_sortby(self.books_tree, c, cast=func))
        self.books_tree.column("isbn", width=130, anchor="w")
        self.books_tree.column("title", width=260, anchor="w")
        self.books_tree.column("authors", width=200, anchor="w")
        self.books_tree.column("edition", width=120, anchor="w")
        self.books_tree.column("cover", width=140, anchor="w")
        self.books_tree.column("printing", width=120, anchor="w")
        self.books_tree.column("price", width=90, anchor="e")
        self.books_tree.column("probability", width=120, anchor="w")
        self.books_tree.column("quantity", width=70, anchor="center")
        self.books_tree.column("condition", width=100, anchor="w")
        self.books_tree.column("sell_through", width=110, anchor="w")
        self.books_tree.column("booksrun_cash", width=110, anchor="e")
        self.books_tree.column("booksrun_credit", width=110, anchor="e")
        self.books_tree.column("booksrun_value", width=120, anchor="w")
        self.books_tree.column("scanned", width=150, anchor="w")
        self.books_tree.bind("<<TreeviewSelect>>", self._on_book_select)
        self.books_tree.bind("<Double-1>", self._on_books_double_click)

        # Use grid geometry inside books_frame to support both scrollbars
        self.books_tree.grid(row=0, column=0, sticky="nsew")
        sb_books = ttk.Scrollbar(books_frame, orient="vertical", command=self.books_tree.yview)
        sb_books.grid(row=0, column=1, sticky="ns")
        sb_books_x = ttk.Scrollbar(books_frame, orient="horizontal", command=self.books_tree.xview)
        sb_books_x.grid(row=1, column=0, sticky="ew")
        self.books_tree.configure(yscrollcommand=sb_books.set, xscrollcommand=sb_books_x.set)
        # Make the tree expand to fill the frame
        books_frame.rowconfigure(0, weight=1)
        books_frame.columnconfigure(0, weight=1)

        self.books_menu = tk.Menu(self.root, tearoff=0)
        self.books_menu.add_command(label="Edit…", command=lambda: self._menu_edit_book())
        self.books_menu.add_command(label="Modify…", command=self._on_modify_books)
        self.books_menu.add_separator()
        self.books_menu.add_command(label="Delete", command=lambda: self._menu_delete_books())
        self.books_tree.bind("<Button-3>", self._popup_books_menu)
        if IS_MAC:
            self.books_tree.bind("<Control-Button-1>", self._popup_books_menu)

        # Lots table
        lots_frame = ttk.LabelFrame(self.body, text="Lot Recommendations", padding=10)
        lots_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        lot_columns = ("title", "author", "value", "probability", "justification")
        self.lots_tree = ttk.Treeview(
            lots_frame,
            columns=lot_columns,
            show="headings",
            height=8,
            selectmode="extended",
        )
        for col in lot_columns:
            heading = col.replace("_", " ").title()
            cast = _as_float if col == "value" else None
            self.lots_tree.heading(col, text=heading, command=lambda c=col, func=cast: _tree_sortby(self.lots_tree, c, cast=func))
        self.lots_tree.column("title", width=260)
        self.lots_tree.column("author", width=200)
        self.lots_tree.column("value", width=110, anchor="e")
        self.lots_tree.column("probability", width=110)
        self.lots_tree.column("justification", width=380)
        self.lots_tree.bind("<<TreeviewSelect>>", self._on_lot_select)
        self.lots_tree.bind("<Double-1>", self._on_lot_double_click)

        # Use grid geometry inside lots_frame to support both scrollbars
        self.lots_tree.grid(row=0, column=0, sticky="nsew")
        sb_lots = ttk.Scrollbar(lots_frame, orient="vertical", command=self.lots_tree.yview)
        sb_lots.grid(row=0, column=1, sticky="ns")
        sb_lots_x = ttk.Scrollbar(lots_frame, orient="horizontal", command=self.lots_tree.xview)
        sb_lots_x.grid(row=1, column=0, sticky="ew")
        self.lots_tree.configure(yscrollcommand=sb_lots.set, xscrollcommand=sb_lots_x.set)
        # Make the tree expand to fill the frame
        lots_frame.rowconfigure(0, weight=1)
        lots_frame.columnconfigure(0, weight=1)

        # initialize service strategies from defaults now that tables exist
        self._on_lot_option_change()

        # Detail panel
        detail_frame = ttk.LabelFrame(self.body, text="Details", padding=10)
        detail_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # cover thumbnails container with horizontal scrolling
        self.cover_wrap = ttk.Frame(detail_frame)
        self.cover_wrap.pack(fill="x", pady=(0, 6))
        self.cover_canvas = tk.Canvas(self.cover_wrap, height=200, highlightthickness=0)
        self.cover_canvas.grid(row=0, column=0, sticky="ew")
        self.cover_hbar = ttk.Scrollbar(self.cover_wrap, orient="horizontal", command=self.cover_canvas.xview)
        self.cover_hbar.grid(row=1, column=0, sticky="ew")
        self.cover_canvas.configure(xscrollcommand=self.cover_hbar.set)
        self.cover_inner = ttk.Frame(self.cover_canvas)
        self.cover_canvas.create_window((0, 0), window=self.cover_inner, anchor="nw")
        self.cover_wrap.columnconfigure(0, weight=1)
        # Update scrollregion when thumbnails change
        self.cover_inner.bind("<Configure>", lambda e: self.cover_canvas.configure(scrollregion=self.cover_canvas.bbox("all")))

        self.detail_text = tk.Text(detail_frame, height=8, wrap="word")
        self.detail_text.pack(fill="both", expand=True)
        self.detail_text.configure(state="disabled")

        # Menubar - Tools
        menubar = tk.Menu(self.root)

        research = tk.Menu(menubar, tearoff=0)
        research.add_command(label="Open Product Research…", command=self._open_research_for_current)
        research.add_command(label="Open Sold+Completed Search…", command=self._open_sold_search_for_current)
        research.add_separator()
        research.add_command(label="Import from Clipboard", command=self._import_product_research_clipboard)

        tools = tk.Menu(menubar, tearoff=0)
        tools.add_command(label="Refresh Selected Book(s)", command=self.refresh_selected)
        tools.add_command(label="Refresh BooksRun (All)", command=self.refresh_booksrun_all)
        tools.add_command(label="Author Cleanup…", command=self._open_author_cleanup)
        tools.add_command(label="Refresh Series Catalog", command=self._refresh_series_catalog)
        tools.add_command(label="Bulk Remove Sold (Paste…)", command=self._open_bulk_remove_paste)
        tools.add_separator()
        tools.add_command(label="Show Cover Cache Info", command=self._show_cover_cache_info)
        tools.add_command(label="Show Cover Sources", command=self._show_cover_sources)
        menubar.add_cascade(label="Research", menu=research)
        menubar.add_cascade(label="Tools", menu=tools)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Sound Preferences…", command=self._open_sound_preferences)
        menubar.add_cascade(label="Settings", menu=settings_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Copy Helper (Bookmarklet)", command=self._show_copy_helper)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

        status_frame = ttk.Frame(self.root)
        status_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

        status_bar = ttk.Label(status_frame, textvariable=self.status_var, anchor="w")
        status_bar.pack(side="left", fill="x", expand=True)

        self.preload_progress = ttk.Progressbar(status_frame, mode="determinate", length=140, maximum=1)
        self.preload_progress.pack(side="left", padx=8)
        self.preload_progress['value'] = 0
        self.preload_text = tk.StringVar(value="")
        preload_label = ttk.Label(status_frame, textvariable=self.preload_text, anchor="center", width=16)
        preload_label.pack(side="left", padx=4)

        self.count_var = tk.StringVar()
        count_label = ttk.Label(status_frame, textvariable=self.count_var, anchor="e")
        count_label.pack(side="right")

        accel = "<Command-a>" if IS_MAC else "<Control-a>"
        self.root.bind(accel, self._handle_select_all)
        self.root.bind("<Delete>", self._on_delete_key)
        if IS_MAC:
            self.root.bind("<BackSpace>", self._on_delete_key)

    # ------------------------------------------------------------------
    # Event handlers

    def _on_scan(self) -> None:
        raw_isbn = self.isbn_var.get().strip()
        if not raw_isbn:
            messagebox.showwarning("Missing ISBN", "Please enter an ISBN before scanning.")
            return

        normalized = normalise_isbn(raw_isbn)
        if not normalized:
            messagebox.showwarning("Invalid ISBN", "Could not recognise that ISBN. Please check the digits and try again.")
            return

        condition = self.condition_var.get() or "Good"
        edition = self.edition_var.get().strip() or None

        existing = self.service.get_book(normalized)
        if existing:
            current_qty = getattr(existing, "quantity", 1)
            title = existing.metadata.title or normalized
            message = (
                f"{title} is already in the list (count: {current_qty}).\n\n"
                "Increase the count by 1?"
            )
            if messagebox.askyesno("Duplicate ISBN", message):
                updated = self.service.increment_book_quantity(normalized, 1)
                if updated:
                    self._set_status(
                        f"Count for {updated.metadata.title or updated.isbn} increased to {updated.quantity}."
                    )
                    self._populate_books()
                    try:
                        self.books_tree.selection_set(updated.isbn)
                        self.books_tree.focus(updated.isbn)
                        self._show_book_details(updated)
                    except Exception:
                        pass
                else:
                    messagebox.showerror("Update failed", "Could not adjust the quantity for this book.")
            else:
                self._set_status("Duplicate ISBN ignored.")
            self.isbn_var.set("")
            self.edition_var.set("")
            return

        isbn = normalized
        self._play_scan_started()

        def task() -> None:
            try:
                evaluation = self.service.scan_isbn(isbn, condition=condition, edition=edition)
            except Exception as exc:
                self._set_status(f"Scan failed: {exc}")
                messagebox.showerror("Scan failed", str(exc))
                return
            self.root.after(0, self._handle_scan_result, evaluation)

        threading.Thread(target=task, daemon=True).start()
        self._set_status("Evaluating ISBN…")

    def _handle_scan_result(self, evaluation: BookEvaluation) -> None:
        self.isbn_var.set("")
        self.edition_var.set("")
        self._play_scan_complete()
        self._set_status(f"Recorded {evaluation.metadata.title or evaluation.isbn}")
        self._populate_tables(select_isbn=evaluation.isbn)
        try:
            self._enqueue_series_enrichment(evaluation.isbn)
        except Exception:
            pass
        if self._isbn_in_any_lot(evaluation.isbn):
            self._play_lot_match()
            self._focus_lot_for_isbn(evaluation.isbn)
        else:
            self._show_book_details(evaluation)

    def _on_import(self) -> None:
        path_str = filedialog.askopenfilename(
            title="Select ISBN CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path_str:
            return
        path = Path(path_str)

        def task() -> None:
            try:
                evaluations = self.service.import_csv(path)
            except Exception as exc:
                self._set_status(f"Import failed: {exc}")
                messagebox.showerror("Import failed", str(exc))
                return
            self.root.after(0, self._handle_import_result, len(evaluations), path)

        threading.Thread(target=task, daemon=True).start()
        self._set_status(f"Importing from {path.name}…")

    def _handle_import_result(self, count: int, path: Path) -> None:
        self._set_status(f"Imported {count} ISBNs from {path.name}")
        self.reload_tables()
        try:
            self._enqueue_series_backfill(limit=count or 200)
        except Exception:
            pass

    def _on_refresh_selected(self) -> None:
        self.refresh_selected()

    def refresh_booksrun_all(self, *_args) -> None:
        """
        Refresh BooksRun offers for all stored books with polite rate limiting.
        Uses the service.refresh_booksrun_all method and shows a determinate progress bar.
        """
        if self._refresh_thread and self._refresh_thread.is_alive():
            messagebox.showinfo("BooksRun Refresh", "A refresh is already in progress. Please wait for it to finish.")
            return

        confirm = messagebox.askyesno(
            "Refresh BooksRun (All)",
            "This will query BooksRun for all books in your catalog.\n\nProceed?",
        )
        if not confirm:
            self._set_status("BooksRun refresh cancelled.")
            return

        # Start progress; total will be updated by progress callback
        self._set_status("Refreshing BooksRun offers for all books…")
        self._start_progress("booksrun", "BooksRun", 1)

        def progress(done: int, total_count: int) -> None:
            # Update progress from worker thread safely
            self.root.after(0, self._update_progress, "booksrun", done, total_count)

        def handle_error(exc: Exception) -> None:
            self._refresh_thread = None
            self._reset_progress("booksrun")
            messagebox.showerror("BooksRun Refresh", f"Refresh failed:\n{exc}")
            self._set_status("BooksRun refresh failed.")

        def handle_success(count: int) -> None:
            self._refresh_thread = None
            self.reload_tables()
            self._finish_progress("booksrun", label="BooksRun", delay_ms=1200)
            self._set_status(f"Refreshed BooksRun offers for {count} book(s).")

        def worker() -> None:
            try:
                # Delay between calls defaults from env BOOKSRUN_DELAY or 0.2s inside service
                count = self.service.refresh_booksrun_all(progress_cb=progress)
            except Exception as exc:  # pragma: no cover - UI path
                self.root.after(0, lambda: handle_error(exc))
                return
            self.root.after(0, lambda: handle_success(count))

        self._refresh_thread = threading.Thread(target=worker, daemon=True)
        self._refresh_thread.start()

    def _open_author_cleanup(self) -> None:
        """
        Find probable author name variants and offer to normalize them.
        Strategy:
          - Pull distinct author names from the DB.
          - Cluster with author_match.cluster_authors.
          - For each cluster, choose a representative display form (prefer multi-token names).
          - Build a mapping old_name -> representative for all members where it differs.
          - Show a summary and prompt to apply.
        """
        if self._refresh_thread and self._refresh_thread.is_alive():
            messagebox.showinfo("Author Cleanup", "An operation is already in progress. Please wait for it to finish.")
            return

        # Gather names
        try:
            # Use DatabaseManager method directly
            names = self.service.db.list_distinct_author_names()
        except Exception:
            # Fall back to scanning in-memory books
            try:
                names = sorted({
                    (b.metadata.authors[0].strip() if b.metadata.authors else "")
                    for b in self.service.list_books()
                    if b and getattr(b, "metadata", None) and b.metadata.authors
                })
            except Exception:
                names = []

        names = [n for n in names if n]
        if not names:
            messagebox.showinfo("Author Cleanup", "No author names found to analyze.")
            return

        clusters = cluster_authors(names)
        # Open interactive review UI for case-by-case approval with thumbnails
        review_clusters = {k: v for k, v in clusters.items() if isinstance(v, (list, tuple)) and len(v) >= 2}
        if not review_clusters:
            messagebox.showinfo("Author Cleanup", "No normalization suggestions were generated.")
            return
        self._open_author_cleanup_reviewer(review_clusters)
        return

    def _open_bulk_remove_paste(self) -> None:
        """
        Paste text from World of Books / BooksRun confirmation pages, parse ISBNs, and bulk remove.
        """
        if self._refresh_thread and self._refresh_thread.is_alive():
            messagebox.showinfo("Bulk Remove", "An operation is already in progress. Please wait for it to finish.")
            return

        dialog = Toplevel(self.root)
        dialog.title("Bulk Remove Sold — Paste Confirmation Page")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("720x520")

        ttk.Label(
            dialog,
            text="Paste the confirmation page text below (World of Books or BooksRun). ISBNs will be detected."
        ).pack(anchor="w", padx=10, pady=(10, 6))

        txt_input = tk.Text(dialog, height=12, wrap="word")
        txt_input.pack(fill="both", expand=False, padx=10, pady=(0, 6))
        try:
            # Pre-fill from clipboard if available
            clip = self.root.clipboard_get()
            if clip and isinstance(clip, str):
                txt_input.insert("1.0", clip)
        except Exception:
            pass

        status_var = tk.StringVar(value="Found 0 ISBN(s)")
        ttk.Label(dialog, textvariable=status_var).pack(anchor="w", padx=10, pady=(4, 0))

        preview = tk.Text(dialog, height=10, wrap="word", state="disabled")
        preview.pack(fill="both", expand=True, padx=10, pady=(4, 8))

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        parsed_isbns: list[str] = []

        def show_preview(items: list[str]) -> None:
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            if items:
                sample = items[:200]
                preview.insert("1.0", "\n".join(sample))
                if len(items) > len(sample):
                    preview.insert("end", f"\n… and {len(items) - len(sample)} more")
            else:
                preview.insert("1.0", "No ISBNs detected yet.")
            preview.configure(state="disabled")

        def do_parse() -> None:
            nonlocal parsed_isbns
            text = txt_input.get("1.0", "end")
            try:
                items = parse_isbns_from_text(text)
            except Exception as exc:
                messagebox.showerror("Bulk Remove", f"Parse failed:\n{exc}")
                return
            parsed_isbns = items or []
            status_var.set(f"Found {len(parsed_isbns)} ISBN(s)")
            show_preview(parsed_isbns)
            try:
                btn_remove.configure(state=("normal" if parsed_isbns else "disabled"))
            except Exception:
                pass

        def do_remove() -> None:
            if not parsed_isbns:
                messagebox.showinfo("Bulk Remove", "No ISBNs to remove.")
                return
            if not messagebox.askyesno("Confirm Remove", f"Delete {len(parsed_isbns)} book(s)? This cannot be undone."):
                return
            try:
                deleted = self.service.delete_books(parsed_isbns)
            except Exception as exc:
                messagebox.showerror("Bulk Remove", f"Delete failed:\n{exc}")
                return
            self.reload_tables()
            self._set_status(f"Deleted {deleted} book(s).")
            dialog.destroy()

        btn_parse = ttk.Button(btn_frame, text="Parse", command=do_parse)
        btn_parse.pack(side="left")

        btn_remove = ttk.Button(btn_frame, text="Remove", command=do_remove, state="disabled")
        btn_remove.pack(side="right")
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))

        # Initial parse if content was pre-filled
        try:
            if txt_input.get("1.0", "end").strip():
                do_parse()
        except Exception:
            pass

    def _on_clear_database(self) -> None:
        confirm = messagebox.askyesno(
            "Clear Database",
            "This will delete all scanned books and lot recommendations. Continue?",
        )
        if not confirm:
            self._set_status("Database clear cancelled.")
            return
        try:
            self.service.clear_database()
        except Exception as exc:
            messagebox.showerror("Clear Database", f"Could not clear the database:\n{exc}")
            self._set_status("Database clear failed.")
            return

        self.isbn_var.set("")
        self.search_var.set("")
        self._populate_tables()
        self._display_cover_images([])
        self._set_detail_text("")
        self._set_status("Database cleared.")

    def reload_tables(self) -> None:
        self._populate_tables()

    def select_all_books(self) -> None:
        for iid in self.books_tree.get_children():
            self.books_tree.selection_add(iid)

    def _handle_select_all(self, event) -> str:
        self.select_all_books()
        return "break"

    def refresh_selected(self, *_args) -> None:
        if self._refresh_thread and self._refresh_thread.is_alive():
            messagebox.showinfo("Refresh", "A refresh is already in progress. Please wait for it to finish.")
            return
        selected = self.books_tree.selection()
        if not selected:
            messagebox.showinfo("Refresh", "Select one or more books to refresh.")
            return
        isbns: list[str] = []
        for iid in selected:
            values = self.books_tree.item(iid).get("values", [])
            if not values:
                continue
            isbn = values[0]
            if isbn:
                isbns.append(str(isbn))
        if not isbns:
            messagebox.showinfo("Refresh", "No valid ISBNs found in the selection.")
            return
        total = len(isbns)
        self._set_status(f"Refreshing {total} book(s)…")
        self.root.update_idletasks()
        self._start_progress("refresh", "Refresh", total)

        def progress(done: int, total_count: int) -> None:
            self.root.after(0, self._update_progress, "refresh", done, total_count)

        def handle_error(exc: Exception) -> None:
            self._refresh_thread = None
            self._reset_progress("refresh")
            messagebox.showerror("Refresh", f"Refresh failed:\n{exc}")
            self._set_status("Refresh failed.")

        def handle_success(count: int) -> None:
            self._refresh_thread = None
            self.reload_tables()
            self._finish_progress("refresh", label="Refresh", delay_ms=1200)
            self._set_status(f"Refreshed {count} book(s).")

        def worker(pending: list[str]) -> None:
            try:
                count = self.service.refresh_books(
                    pending,
                    requery_market=True,
                    requery_metadata=False,
                    progress_cb=progress,
                )
            except Exception as exc:  # pragma: no cover - UI error path
                self.root.after(0, lambda e=exc: handle_error(e))
                return
            self.root.after(0, lambda: handle_success(count))

        self._refresh_thread = threading.Thread(target=worker, args=(isbns,), daemon=True)
        self._refresh_thread.start()

    def _on_books_double_click(self, event) -> None:
        iid = self.books_tree.identify_row(event.y)
        if not iid:
            selection = self.books_tree.selection()
            if selection:
                iid = selection[0]
        if iid:
            self.open_edit_dialog(iid)

    def open_edit_dialog(self, item_id: str) -> None:
        values = self.books_tree.item(item_id).get("values", [])
        if not values:
            return
        isbn = str(values[0])
        title = values[1] if len(values) > 1 else ""
        authors = values[2] if len(values) > 2 else ""
        edition = values[3] if len(values) > 3 else ""
        cover_type = values[4] if len(values) > 4 else "Unknown"
        printing = values[5] if len(values) > 5 else ""

        dialog = Toplevel(self.root)
        dialog.title(f"Edit Book — {isbn}")
        dialog.transient(self.root)
        dialog.grab_set()

        v_title = tk.StringVar(value=title)
        v_authors = tk.StringVar(value=authors)
        v_edition = tk.StringVar(value=edition)
        v_cover = tk.StringVar(value=cover_type if cover_type in COVER_CHOICES else "Unknown")
        v_printing = tk.StringVar(value=printing)

        dialog.columnconfigure(1, weight=1)

        def add_row(idx: int, label: str, widget: Any) -> None:
            ttk.Label(dialog, text=label).grid(row=idx, column=0, sticky="w", padx=8, pady=6)
            widget.grid(row=idx, column=1, sticky="ew", padx=8, pady=6)

        entry_title = ttk.Entry(dialog, textvariable=v_title, width=50)
        entry_authors = ttk.Entry(dialog, textvariable=v_authors, width=50)
        combo_cover = ttk.Combobox(dialog, textvariable=v_cover, values=COVER_CHOICES, state="readonly", width=28)
        entry_edition = ttk.Entry(dialog, textvariable=v_edition, width=28)
        entry_printing = ttk.Entry(dialog, textvariable=v_printing, width=28)

        add_row(0, "Title", entry_title)
        add_row(1, "Author(s)", entry_authors)
        add_row(2, "Cover type", combo_cover)
        add_row(3, "Edition", entry_edition)
        add_row(4, "Printing", entry_printing)

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=5, column=0, columnspan=2, sticky="e", padx=8, pady=(4, 10))

        def do_save() -> None:
            payload: Dict[str, Any] = {
                "title": v_title.get().strip(),
                "authors": v_authors.get().strip(),
                "edition": v_edition.get().strip() or None,
                "cover_type": v_cover.get().strip() or "Unknown",
                "printing": v_printing.get().strip() or None,
            }
            try:
                self.service.update_book_fields(isbn, payload)
            except Exception as exc:
                messagebox.showerror("Edit Book", f"Could not save changes:\n{exc}")
                return
            self.reload_tables()
            self._set_status(f"Updated {isbn}.")
            dialog.destroy()

        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="right", padx=6)
        ttk.Button(button_frame, text="Save", command=do_save).pack(side="right")

        entry_title.focus_set()
        dialog.wait_window()

    def _on_modify_books(self) -> None:
        selected = self.books_tree.selection()
        if not selected:
            messagebox.showinfo("Modify Books", "Select one or more books to modify.")
            return
        isbns: list[str] = []
        for iid in selected:
            values = self.books_tree.item(iid).get("values", [])
            if not values:
                continue
            isbn = values[0]
            if isbn:
                isbns.append(str(isbn))
        if not isbns:
            messagebox.showinfo("Modify Books", "No valid ISBNs found in the selection.")
            return
        self.open_batch_modify_dialog(isbns)

    def open_batch_modify_dialog(self, isbns: list[str]) -> None:
        if not isbns:
            return

        dialog = Toplevel(self.root)
        dialog.title(f"Modify {len(isbns)} Book(s)")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)

        ttk.Label(
            dialog,
            text=f"Apply updates to {len(isbns)} selected book(s).",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(10, 6))

        apply_vars: dict[str, tk.BooleanVar] = {}
        value_vars: dict[str, tk.Variable] = {}

        def add_field(row_idx: int, field_key: str, label_text: str, widget: Any, *, enabled_state: str) -> None:
            var = tk.BooleanVar(value=False)
            apply_vars[field_key] = var
            ttk.Checkbutton(dialog, text=label_text, variable=var).grid(
                row=row_idx, column=0, sticky="w", padx=8, pady=4
            )
            widget.grid(row=row_idx, column=1, sticky="ew", padx=8, pady=4)

            def toggle() -> None:
                state = enabled_state if var.get() else "disabled"
                try:
                    widget.configure(state=state)
                except Exception:
                    pass

            var.trace_add("write", lambda *_: toggle())
            toggle()

        row = 1

        value_vars["title"] = tk.StringVar()
        title_entry = ttk.Entry(dialog, textvariable=value_vars["title"], width=50)
        add_field(row, "title", "Title", title_entry, enabled_state="normal")
        row += 1

        value_vars["authors"] = tk.StringVar()
        authors_entry = ttk.Entry(dialog, textvariable=value_vars["authors"], width=50)
        add_field(row, "authors", "Author(s)", authors_entry, enabled_state="normal")
        row += 1

        value_vars["cover_type"] = tk.StringVar(value="Unknown")
        cover_combo = ttk.Combobox(
            dialog,
            textvariable=value_vars["cover_type"],
            values=COVER_CHOICES,
            state="disabled",
            width=28,
        )
        add_field(row, "cover_type", "Cover type", cover_combo, enabled_state="readonly")
        row += 1

        value_vars["edition"] = tk.StringVar()
        edition_entry = ttk.Entry(dialog, textvariable=value_vars["edition"], width=28)
        add_field(row, "edition", "Edition", edition_entry, enabled_state="normal")
        row += 1

        value_vars["printing"] = tk.StringVar()
        printing_entry = ttk.Entry(dialog, textvariable=value_vars["printing"], width=28)
        add_field(row, "printing", "Printing", printing_entry, enabled_state="normal")
        row += 1

        value_vars["condition"] = tk.StringVar(value="Good")
        condition_combo = ttk.Combobox(
            dialog,
            textvariable=value_vars["condition"],
            values=["New", "Like New", "Very Good", "Good", "Acceptable", "Poor"],
            state="disabled",
            width=28,
        )
        add_field(row, "condition", "Condition", condition_combo, enabled_state="readonly")
        row += 1

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=row, column=0, columnspan=2, sticky="e", padx=8, pady=(6, 12))

        def do_apply() -> None:
            payload: Dict[str, Any] = {}
            if apply_vars.get("title") and apply_vars["title"].get():
                payload["title"] = value_vars["title"].get().strip()
            if apply_vars.get("authors") and apply_vars["authors"].get():
                payload["authors"] = value_vars["authors"].get().strip()
            if apply_vars.get("cover_type") and apply_vars["cover_type"].get():
                payload["cover_type"] = value_vars["cover_type"].get().strip() or "Unknown"
            if apply_vars.get("edition") and apply_vars["edition"].get():
                payload["edition"] = value_vars["edition"].get().strip()
            if apply_vars.get("printing") and apply_vars["printing"].get():
                payload["printing"] = value_vars["printing"].get().strip()
            if apply_vars.get("condition") and apply_vars["condition"].get():
                payload["condition"] = value_vars["condition"].get().strip()

            if not payload:
                messagebox.showinfo("Modify Books", "Select at least one field to update.")
                return

            try:
                updated_count = self.service.update_books_fields(isbns, payload)
            except Exception as exc:
                messagebox.showerror("Modify Books", f"Could not apply changes:\n{exc}")
                return

            if updated_count == 0:
                messagebox.showinfo("Modify Books", "No changes were applied.")
                return

            self.reload_tables()
            try:
                self.books_tree.selection_set(isbns)
                if isbns:
                    self.books_tree.focus(isbns[0])
            except Exception:
                pass
            self._set_status(f"Updated {updated_count} book(s).")
            dialog.destroy()

        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="right", padx=6)
        ttk.Button(button_frame, text="Apply", command=do_apply).pack(side="right")

        dialog.wait_window()

    def _popup_books_menu(self, event) -> None:
        iid = self.books_tree.identify_row(event.y)
        if iid:
            if iid not in self.books_tree.selection():
                self.books_tree.selection_set(iid)
            try:
                self.books_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.books_menu.grab_release()

    def _menu_edit_book(self) -> None:
        selection = self.books_tree.selection()
        if selection:
            self.open_edit_dialog(selection[0])

    def _menu_delete_books(self) -> None:
        selection = self.books_tree.selection()
        if not selection:
            return
        isbns = [self.books_tree.item(i, "values")[0] for i in selection if self.books_tree.item(i, "values")]
        if not isbns:
            return
        if not messagebox.askyesno("Delete Books", f"Delete {len(isbns)} selected book(s)? This cannot be undone."):
            return
        try:
            deleted = self.service.delete_books(isbns)
        except Exception as exc:
            messagebox.showerror("Delete Books", f"Delete failed:\n{exc}")
            return
        self.reload_tables()
        self._set_status(f"Deleted {deleted} book(s).")

    def _on_delete_key(self, _event) -> None:
        focus_widget = self.root.focus_get()
        if focus_widget is self.books_tree:
            self._menu_delete_books()

    def _on_lot_option_change(self) -> None:
        strategies = set()
        if self.var_lot_author.get():
            strategies.add("author")
        if self.var_lot_series.get():
            strategies.add("series")
        if self.var_lot_genre.get():
            strategies.add("genre")
        try:
            self.service.set_lot_strategies(strategies)
            self.service.recompute_lots()
            if hasattr(self, "lots_tree"):
                self._populate_lots()
        except Exception as e:
            messagebox.showerror("Lot Options", f"Could not recompute lots:\n{e}")

    def _refresh_series_catalog(self) -> None:
        try:
            authors = sorted({
                (b.metadata.authors[0].strip() if b.metadata.authors else "")
                for b in self.service.list_books()
                if b and getattr(b, "metadata", None) and b.metadata.authors
            })
            self.service.refresh_series_catalog_for_authors(authors)
            self.service.recompute_lots()
            self._populate_lots()
            messagebox.showinfo("Series Catalog", f"Refreshed for {len(authors)} author(s).")
        except Exception as e:
            messagebox.showerror("Series Catalog", f"Could not refresh:\n{e}")

    def _on_book_select(self, event) -> None:
        iid = self.books_tree.focus()
        if not iid:
            selection = self.books_tree.selection()
            if selection:
                iid = selection[0]
        if not iid:
            return
        book = self._book_by_iid.get(iid)
        if not book:
            values = self.books_tree.item(iid).get("values", [])
            isbn = values[0] if values else None
            if isbn:
                book = self._book_by_iid.get(str(isbn))
        if book:
            self._show_book_details(book)

    def _on_lot_select(self, event) -> None:
        selected = self.lots_tree.focus()
        if not selected:
            selection = self.lots_tree.selection()
            if selection:
                selected = selection[0]
        if not selected:
            return

        lot = self._lot_by_iid.get(selected)
        values = self.lots_tree.item(selected).get("values", [])
        if not lot and not values:
            return

        lot_name = getattr(lot, "label", None) or getattr(lot, "name", None) or (values[0] if values else "Lot")
        probability = getattr(lot, "probability_label", None) or getattr(lot, "probability", None) or (values[3] if len(values) > 3 else "")
        est_value = getattr(lot, "estimated_value", None)
        sell_through = getattr(lot, "sell_through", None)

        justification_lines = getattr(lot, "justification", None)
        if isinstance(justification_lines, str):
            justification_lines = [line.strip() for line in justification_lines.split("\n") if line.strip()]
        if not justification_lines and values and len(values) > 4 and values[4]:
            justification_lines = [part.strip() for part in values[4].split("; ") if part.strip()]
        if not justification_lines:
            justification_lines = []

        books: list[BookEvaluation] = []
        if hasattr(lot, "books") and getattr(lot, "books"):
            candidates = getattr(lot, "books")
            books = [b for b in candidates if isinstance(b, BookEvaluation)]
        else:
            isbn_lists = (
                getattr(lot, "book_isbns", None),
                getattr(lot, "isbns", None),
                getattr(lot, "isbn_list", None),
            )
            for isbn_list in isbn_lists:
                if isbn_list:
                    missing: list[str] = []
                    for isbn in isbn_list:
                        book = self._book_by_iid.get(isbn)
                        if book:
                            books.append(book)
                        else:
                            missing.append(isbn)
                    if missing:
                        by_isbn = {b.isbn: b for b in self.service.list_books()}
                        for isbn in missing:
                            book = by_isbn.get(isbn)
                            if book:
                                self._book_by_iid[isbn] = book
                                books.append(book)
                    break

        strategy = getattr(lot, "strategy", None)
        if not books:
            strategy_key = (strategy or "").lower()
            if strategy_key == "series" and hasattr(self.service, "build_series_lots_with_coverage"):
                try:
                    for entry in self.service.build_series_lots_with_coverage():
                        if entry.get("label") == lot_name:
                            books = [b for b in entry.get("books") or [] if isinstance(b, BookEvaluation)]
                            break
                except Exception:
                    pass

        cover_entries: list[tuple[Optional[str], Optional[Any]]] = []
        for book in books:
            url, img = self._best_cover_entry(book)
            cover_entries.append((url, img))

        cover_count = sum(1 for _, img in cover_entries if img)
        total_books = len(books)

        self._display_cover_images(cover_entries)
        if cover_count:
            if total_books:
                self._set_status(f"Loaded {cover_count}/{total_books} cover(s) for lot {lot_name}")
            else:
                self._set_status(f"Loaded {cover_count} cover(s) for lot {lot_name}")
        else:
            self._set_status(f"No thumbnails available for lot {lot_name}")

        lines = [f"Lot: {lot_name}"]
        author_label = getattr(lot, "display_author_label", None)
        if author_label:
            lines.append(f"Author: {author_label}")
        else:
            canonical_label = getattr(lot, "canonical_author", None)
            if canonical_label:
                lines.append(f"Author: {canonical_label}")
        if books:
            lines.append(f"Books: {len(books)}")
        if est_value is not None:
            try:
                lines.append(f"Estimated value: ${float(est_value):,.2f}")
            except Exception:
                lines.append(f"Estimated value: {est_value}")
        if probability:
            lines.append(f"Probability: {probability}")
        if sell_through not in (None, ""):
            try:
                lines.append(f"Sell-through: {float(sell_through):.0%}")
            except Exception:
                lines.append(f"Sell-through: {sell_through}")

        if justification_lines:
            lines.append("")
            lines.append("Justification:")
            lines.extend(f" - {reason}" for reason in justification_lines)

        if books:
            lines.append("")
            lines.append("Books in lot:")
            for idx, book in enumerate(books, 1):
                title = book.metadata.title or "(untitled)"
                credited = list(getattr(book.metadata, "credited_authors", ()))
                if not credited and book.metadata.authors:
                    credited = [a for a in book.metadata.authors]
                author_label = credited[0] if credited else "Unknown"
                canonical_label = getattr(book.metadata, "canonical_author", None)
                if canonical_label and canonical_label != author_label:
                    author_label = f"{author_label} ({canonical_label})"
                lines.append(f" {idx}. {title} — {author_label} ({book.isbn})")

        self._set_detail_text("\n".join(lines))

    def _on_lot_double_click(self, event) -> None:
        item = self.lots_tree.identify_row(event.y)
        lot = self._lot_by_iid.get(item)
        if not lot:
            return
        try:
            books = self.service.get_books_for_lot(lot)
        except Exception as e:
            messagebox.showerror("Lot Details", f"Could not load lot details:\n{e}")
            return
        self._open_lot_window(lot, books)

    def _open_lot_window(self, lot: LotSuggestion, books: list[BookEvaluation]) -> None:
        win = Toplevel(self.root)
        win.title(f"Lot Details — {getattr(lot, 'name', 'Lot')}")

        tree = ttk.Treeview(
            win,
            columns=("isbn", "title", "author", "condition", "est_price", "prob", "notes"),
            show="headings",
            height=12,
        )
        tree.pack(fill="both", expand=True)

        tree.heading("isbn", text="ISBN")
        tree.heading("title", text="Title")
        tree.heading("author", text="Author")
        tree.heading("condition", text="Condition")
        tree.heading("est_price", text="Est. Price")
        tree.heading("prob", text="Probability")
        tree.heading("notes", text="Notes")

        tree.column("isbn", width=130, anchor="w")
        tree.column("title", width=280, anchor="w")
        tree.column("author", width=180, anchor="w")
        tree.column("condition", width=100, anchor="w")
        tree.column("est_price", width=90, anchor="e")
        tree.column("prob", width=120, anchor="center")
        tree.column("notes", width=240, anchor="w")

        for b in books:
            isbn = getattr(b, "isbn", "")
            title = getattr(b.metadata, "title", "") if getattr(b, "metadata", None) else ""
            credited = list(getattr(b.metadata, "credited_authors", ())) if getattr(b, "metadata", None) else []
            if not credited and getattr(b, "metadata", None) and b.metadata.authors:
                credited = [a for a in b.metadata.authors]
            author_label = credited[0] if credited else "Unknown"
            canonical = getattr(b.metadata, "canonical_author", None)
            if canonical and canonical != author_label:
                author_label = f"{author_label} ({canonical})"
            condition = getattr(b, "condition", "")
            est_price = getattr(b, "estimated_price", 0.0)
            prob = f"{getattr(b, 'probability_label', '')} ({getattr(b, 'probability_score', 0.0):.0f})"
            notes = "; ".join(getattr(b, "justification", []) or [])
            price_str = f"${est_price:,.2f}" if isinstance(est_price, (int, float)) else ""
            tree.insert("", "end", values=(isbn, title, author_label, condition, price_str, prob, notes))

        # Series coverage panel if available
        cov = getattr(lot, "coverage", None)
        if not cov and isinstance(lot, dict):
            cov = lot.get("coverage")
        if cov:
            frm = ttk.Frame(win)
            frm.pack(fill="x", padx=8, pady=6)

            owned = cov.get("owned", 0)
            total = cov.get("total", 0)
            have_nums = ", ".join(str(n) for n in cov.get("have_numbers", []))
            missing_list = ", ".join(f"#{i}: {t}" for i, t in cov.get("missing", []))

            ttk.Label(frm, text=f"Series Coverage: {owned}/{total} owned").pack(anchor="w")
            if have_nums:
                ttk.Label(frm, text=f"Have #s: {have_nums}").pack(anchor="w")
            if missing_list:
                ttk.Label(frm, text=f"Missing: {missing_list}").pack(anchor="w")

        # optional: resize and modal behavior
        win.minsize(900, 380)
        win.transient(self.root)
        win.grab_set()

    def _show_copy_helper(self) -> None:
        script = (
            "javascript:(()=>{try{document.execCommand('selectAll');document.execCommand('copy');"
            "alert('LotHelper: table copied to clipboard');}catch(e){alert('Copy failed. Select all "
            "(Cmd/Ctrl+A) then copy (Cmd/Ctrl+C).');}})();"
        )
        messagebox.showinfo(
            "Copy Helper",
            "Create a bookmark and set its URL to this code:\n\n" + script,
        )

    def _get_selected_lot(self):
        if not getattr(self, "lots_tree", None):
            return None
        iid = self.lots_tree.focus()
        if not iid:
            selection = self.lots_tree.selection()
            if selection:
                iid = selection[0]
        lot = self._lot_by_iid.get(iid)
        if lot:
            return lot

        # Fall back to book selection and map to the first lot containing that ISBN
        book_iid = self.books_tree.focus() if getattr(self, "books_tree", None) else None
        if not book_iid and getattr(self, "books_tree", None):
            selection = self.books_tree.selection()
            if selection:
                book_iid = selection[0]
        book = None
        if book_iid:
            book = self._book_by_iid.get(book_iid) or self._book_by_iid.get(str(book_iid))
        isbn = getattr(book, "isbn", None) if book else None
        if not isbn:
            return None
        for candidate in self._lot_by_iid.values():
            if self._lot_contains_isbn(candidate, isbn):
                return candidate

        for candidate in self.service.current_lots():
            if self._lot_contains_isbn(candidate, isbn):
                return candidate
        return None

    def _get_selected_book(self) -> Optional[BookEvaluation]:
        if not getattr(self, "books_tree", None):
            return None
        iid = self.books_tree.focus()
        if not iid:
            selection = self.books_tree.selection()
            if selection:
                iid = selection[0]
        if not iid:
            return None
        book = self._book_by_iid.get(iid)
        if book:
            return book
        values = self.books_tree.item(iid).get("values", [])
        isbn = values[0] if values else None
        if isbn:
            return self._book_by_iid.get(str(isbn))
        return None

    def _lot_contains_isbn(self, lot, isbn: str) -> bool:
        if not lot or not isbn:
            return False
        for attr in ("book_isbns", "isbns", "isbn_list"):
            try:
                values = getattr(lot, attr)
            except Exception:
                values = None
            if values and isbn in values:
                return True
        if hasattr(lot, "books") and getattr(lot, "books"):
            try:
                for candidate in getattr(lot, "books") or []:
                    if isinstance(candidate, BookEvaluation) and candidate.isbn == isbn:
                        return True
            except Exception:
                pass
        if isinstance(lot, dict):
            for key in ("book_isbns", "isbns", "isbn_list"):
                values = lot.get(key)
                if values and isbn in values:
                    return True
        return False

    def _isbn_in_any_lot(self, isbn: str) -> bool:
        if not isbn:
            return False
        try:
            lots = self.service.list_lots()
        except Exception:
            lots = []
        for lot in lots:
            if isbn not in lot.book_isbns:
                continue
            try:
                books = self.service.get_books_for_lot(lot)
            except Exception:
                books = []
            unique = {getattr(book, "isbn", None) for book in books if getattr(book, "isbn", None)}
            if len(unique) > 1:
                return True
        return False

    def _current_lot_query(self, lot=None) -> str:
        if lot is None:
            lot = self._get_selected_lot()
        if lot:
            books: list[BookEvaluation] = []
            try:
                books = self.service.get_books_for_lot(lot)
            except Exception:
                books = []

            series = getattr(lot, "series_name", None)
            if not series and isinstance(lot, dict):
                series = lot.get("series_name")
            if not series and books:
                for book in books:
                    series = getattr(book.metadata, "series_name", None) or getattr(book.metadata, "series", None)
                    if series:
                        break

            author = getattr(lot, "author", None)
            if not author and isinstance(lot, dict):
                author = lot.get("author")
            if not author and books:
                for book in books:
                    if getattr(book.metadata, "authors", None):
                        author = book.metadata.authors[0]
                        break

            if hasattr(lot, "books") and getattr(lot, "books"):
                count = len(list(getattr(lot, "books") or ()))
            elif isinstance(lot, dict) and lot.get("books"):
                count = len(list(lot.get("books") or ()))
            else:
                identifiers = (
                    getattr(lot, "book_isbns", None)
                    or getattr(lot, "isbns", None)
                    or getattr(lot, "isbn_list", None)
                    or []
                )
                count = len(identifiers) or len(books)

            parts = []
            if series:
                parts.append(str(series))
            if author:
                parts.append(str(author))
            if count:
                parts.append(f"lot of {count}")

            query = " ".join(p.strip() for p in parts if p).strip()
            return query or "book lot"

        book = self._get_selected_book()
        if not book:
            messagebox.showwarning("Research", "Select a lot or book first.")
            return ""

        book_parts = []
        title = getattr(book.metadata, "title", None)
        if title:
            book_parts.append(str(title))
        authors = getattr(book.metadata, "authors", None)
        if authors:
            book_parts.append(str(authors[0]))
        series_name = getattr(book.metadata, "series_name", None)
        if series_name:
            book_parts.append(str(series_name))
        book_parts.append(book.isbn)
        return " ".join(p.strip() for p in book_parts if p).strip()

    def _open_research_for_current(self) -> None:
        query = self._current_lot_query()
        if not query:
            return
        try:
            webbrowser.open_new_tab("https://www.ebay.com/sh/research")
        except Exception as exc:
            messagebox.showerror("Research", f"Could not open Product Research:\n{exc}")
            return
        self._open_sold_search_for_current(query)

    def _open_sold_search_for_current(self, query: Optional[str] = None) -> None:
        search_query = query if query is not None else self._current_lot_query()
        if not search_query:
            return
        params = {"_nkw": search_query, "LH_Sold": 1, "LH_Complete": 1, "rt": "nc"}
        url = "https://www.ebay.com/sch/i.html?" + urllib.parse.urlencode(params)
        try:
            webbrowser.open_new_tab(url)
        except Exception as exc:
            messagebox.showerror("Research", f"Could not open Sold+Completed search:\n{exc}")

    def _import_product_research_clipboard(self) -> None:
        lot = self._get_selected_lot()
        if not lot:
            messagebox.showwarning("Import", "Select a lot first.")
            return

        query = self._current_lot_query(lot)
        if not query:
            return

        try:
            clip = self.root.clipboard_get()
        except Exception:
            messagebox.showerror("Import", "Clipboard is empty or unavailable.")
            return

        result = parse_prices_from_clipboard_text(clip, self._clipboard_import_options)
        prices = result.get("prices") or []
        if not prices:
            messagebox.showwarning(
                "Import",
                "No relevant sold prices found (after filters).",
            )
            return

        median_value = result.get("median")
        count = result.get("count_after") or len(prices)
        used = result.get("used", count)
        skipped = result.get("skipped", 0)
        if median_value is None:
            messagebox.showwarning("Import", "Prices were found but median could not be calculated.")
            return
        payload = {
            "manual_product_research": {
                "query": query,
                "sold_prices": {
                    "count": count,
                    "median": median_value,
                    "used_rows": used,
                    "skipped_rows": skipped,
                },
            }
        }

        try:
            self.service.attach_manual_research_to_lot(lot, payload)
            self.service.rescore_lot(lot)
        except Exception as exc:
            messagebox.showerror("Import", f"Could not attach manual research:\n{exc}")
            return

        if hasattr(self, "_refresh_lot_row"):
            try:
                self._refresh_lot_row(lot)
            except Exception:
                self._populate_lots()
        else:
            self._populate_lots()

        self._set_status(f"Imported manual product research ({count} prices, {skipped} skipped).")
        messagebox.showinfo(
            "Imported",
            f"Imported {count} sold prices; median ${median_value:.2f}",
        )

    def _refresh_lot_row(self, lot) -> None:
        target_iid = None
        for iid, stored in self._lot_by_iid.items():
            if stored is lot:
                target_iid = iid
                break
        if target_iid is None:
            # Fallback to full refresh
            self._populate_lots()
            return

        label = getattr(lot, "label", None) or getattr(lot, "name", "")
        if hasattr(lot, "books") and getattr(lot, "books"):
            size = len(list(getattr(lot, "books") or ()))
        else:
            ids = getattr(lot, "book_isbns", None) or getattr(lot, "isbns", None) or getattr(lot, "isbn_list", None) or []
            try:
                size = len(list(ids))
            except Exception:
                size = 0
        try:
            est_value = float(getattr(lot, "estimated_value", 0.0) or 0.0)
        except Exception:
            est_value = 0.0
        probability = getattr(lot, "probability_label", None) or getattr(lot, "probability", "")
        justification = "; ".join(str(j) for j in getattr(lot, "justification", []) if j)

        self.lots_tree.item(
            target_iid,
            values=(
                label,
                str(size),
                f"${est_value:,.2f}",
                probability,
                justification,
            ),
        )
        self._lot_by_iid[target_iid] = lot

    # ------------------------------------------------------------------
    # Author cleanup reviewer (interactive)
    def _collect_books_for_author_names(self, names: Iterable[str], limit: int = 12) -> list[BookEvaluation]:
        books: list[BookEvaluation] = []
        seen: set[str] = set()
        names_set = {str(n).strip() for n in names if n and str(n).strip()}
        try:
            candidates = self.service.list_books()
        except Exception:
            candidates = []
        for b in candidates:
            if len(books) >= limit:
                break
            try:
                credited = list(getattr(b.metadata, "credited_authors", ())) or [
                    a.strip() for a in getattr(b.metadata, "authors", ()) if a and str(a).strip()
                ]
            except Exception:
                credited = []
            if any(a in names_set for a in credited):
                if b.isbn not in seen:
                    books.append(b)
                    seen.add(b.isbn)
        return books

    def _open_author_cleanup_reviewer(self, clusters: Dict[str, list[str]]) -> None:
        # Prepare an ordered list of clusters for review
        order: list[tuple[str, list[str]]] = []
        for key, members in clusters.items():
            mems = [str(m).strip() for m in members if str(m).strip()]
            if not mems:
                continue
            # Prefer multi-token then shorter string then lexicographic
            mems_sorted = sorted(
                mems,
                key=lambda s: (-len([p for p in s.split() if p]), len(s), s.lower())
            )
            order.append((key, mems_sorted))
        if not order:
            messagebox.showinfo("Author Cleanup", "No normalization suggestions were generated.")
            return
        # Sort clusters by size desc to prioritize impactful ones
        order.sort(key=lambda item: len(item[1]), reverse=True)

        win = Toplevel(self.root)
        win.title("Author Cleanup — Review")
        win.transient(self.root)
        win.grab_set()
        win.geometry("820x640")

        state = {
            "index": 0,
            "order": order,
            "images": [],  # keep references to PhotoImage to avoid GC
            "member_vars": {},  # name -> BooleanVar
            "rep_var": tk.StringVar(),
        }

        header = ttk.Frame(win)
        header.pack(fill="x", padx=10, pady=(10, 6))

        lbl_pos = ttk.Label(header, text="")
        lbl_pos.pack(side="left")

        lbl_cluster = ttk.Label(header, text="", font=("TkDefaultFont", 10, "bold"))
        lbl_cluster.pack(side="right")

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=10, pady=6)

        # Representative selector
        rep_frame = ttk.LabelFrame(body, text="Proposed Representative")
        rep_frame.pack(fill="x", padx=4, pady=6)
        rep_combo = ttk.Combobox(rep_frame, textvariable=state["rep_var"], state="readonly", width=50)
        rep_combo.pack(side="left", padx=8, pady=6)

        # Members checklist
        members_frame = ttk.LabelFrame(body, text="Members to Rename → Representative")
        members_frame.pack(fill="both", expand=False, padx=4, pady=6)
        members_inner = ttk.Frame(members_frame)
        members_inner.pack(fill="x", padx=8, pady=6)

        # Thumbnails area (scrollable)
        thumbs_frame = ttk.LabelFrame(body, text="Sample Book Thumbnails")
        thumbs_frame.pack(fill="both", expand=True, padx=4, pady=6)

        canvas = tk.Canvas(thumbs_frame, height=260)
        sbar = ttk.Scrollbar(thumbs_frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        sbar.pack(side="right", fill="y")

        # Footer buttons
        footer = ttk.Frame(win)
        footer.pack(fill="x", padx=10, pady=(6, 10))
        btn_prev = ttk.Button(footer, text="Previous", command=lambda: move(-1))
        btn_next = ttk.Button(footer, text="Next", command=lambda: move(1))
        btn_skip = ttk.Button(footer, text="Skip", command=lambda: apply_cluster(apply_changes=False))
        btn_apply = ttk.Button(footer, text="Apply This Cluster", command=lambda: apply_cluster(apply_changes=True))
        btn_close = ttk.Button(footer, text="Close", command=win.destroy)
        btn_prev.pack(side="left")
        btn_next.pack(side="left", padx=(6, 0))
        btn_close.pack(side="right")
        btn_apply.pack(side="right", padx=(0, 6))
        btn_skip.pack(side="right", padx=(0, 6))

        def load_cluster(idx: int) -> None:
            # Reset image refs and members UI
            state["images"].clear()
            for child in members_inner.winfo_children():
                child.destroy()
            for child in inner.winfo_children():
                child.destroy()
            state["member_vars"].clear()

            total = len(state["order"])
            lbl_pos.config(text=f"Cluster {idx + 1} of {total}")

            key, members = state["order"][idx]
            lbl_cluster.config(text=f"Key: {key}")

            # Populate representative choices
            rep_combo.configure(values=members)
            rep_default = members[0]
            state["rep_var"].set(rep_default)

            # Member checkboxes (default include all except representative)
            for name in members:
                var = tk.BooleanVar(value=(name != rep_default))
                state["member_vars"][name] = var
                cb = ttk.Checkbutton(members_inner, text=name, variable=var)
                cb.pack(anchor="w", pady=2)

            # Load thumbnails for books matching any member names
            books = self._collect_books_for_author_names(members, limit=20)
            if not books:
                ttk.Label(inner, text="No thumbnails available for this cluster").pack(anchor="w", padx=8, pady=6)
            else:
                # Render in a grid
                col = 0
                row = 0
                for b in books:
                    url, img = self._best_cover_entry(b)
                    if img:
                        lbl = ttk.Label(inner, image=img)
                        lbl.grid(row=row, column=col, padx=4, pady=4, sticky="w")
                        state["images"].append(img)
                    else:
                        lbl = ttk.Label(inner, text=b.metadata.title or b.isbn)
                        lbl.grid(row=row, column=col, padx=4, pady=4, sticky="w")
                    col += 1
                    if col >= 6:
                        col = 0
                        row += 1

        def move(delta: int) -> None:
            new_idx = state["index"] + delta
            total = len(state["order"])
            if new_idx < 0 or new_idx >= total:
                return
            state["index"] = new_idx
            load_cluster(state["index"])

        def apply_cluster(apply_changes: bool) -> None:
            idx = state["index"]
            _key, members = state["order"][idx]
            representative = state["rep_var"].get().strip()
            if not representative:
                messagebox.showwarning("Author Cleanup", "Select a representative name first.")
                return
            if not apply_changes:
                # Move to next without applying
                move(1)
                return
            mapping: Dict[str, str] = {}
            for name in members:
                if name == representative:
                    continue
                var = state["member_vars"].get(name)
                if var and var.get():
                    mapping[name] = representative
            if not mapping:
                move(1)
                return

            # Run rename in background with progress
            self._set_status("Applying author cleanup…")
            self._start_progress("author_cleanup", "Authors", len(members))

            def progress(done: int, total_count: int) -> None:
                try:
                    self.root.after(0, self._update_progress, "author_cleanup", done, total_count or len(members))
                except Exception:
                    pass

            def handle_error(exc: Exception) -> None:
                self._reset_progress("author_cleanup")
                messagebox.showerror("Author Cleanup", f"Rename failed:\n{exc}")
                self._set_status("Author cleanup failed.")

            def handle_success(count: int) -> None:
                self.reload_tables()
                self._finish_progress("author_cleanup", label="Authors", delay_ms=800)
                self._set_status(f"Renamed authors in {count} row(s).")
                move(1)

            def worker() -> None:
                try:
                    updated = self.service.rename_authors(mapping, progress_cb=progress)
                except Exception as exc:
                    self.root.after(0, lambda: handle_error(exc))
                    return
                self.root.after(0, lambda: handle_success(updated))

            threading.Thread(target=worker, daemon=True).start()

        # Initialize first cluster
        load_cluster(state["index"])

    # ------------------------------------------------------------------
    # Data refresh

    def _populate_tables(self, *, select_isbn: Optional[str] = None) -> None:
        self._populate_books(select_isbn=select_isbn)
        self._populate_lots()
        self._update_book_count()
        self._trigger_cover_prefetch()

    def _populate_books(self, *, select_isbn: Optional[str] = None) -> None:
        for row in self.books_tree.get_children():
            self.books_tree.delete(row)
        self._book_by_iid.clear()
        for book in self.service.list_books():
            raw_meta = getattr(book.metadata, "raw", {}) or {}
            cover_type = raw_meta.get("cover_type") or "Unknown"
            printing = raw_meta.get("printing") or ""
            authors = ", ".join(book.metadata.authors) if book.metadata.authors else "N/A"
            sell_through = (
                f"{book.market.sell_through_rate:.0%}" if book.market and book.market.sell_through_rate else "N/A"
            )
            probability = f"{book.probability_label} ({book.probability_score:.0f})"
            scanned = self._format_timestamp(getattr(book, "created_at", None))
            quantity = str(getattr(book, "quantity", 1))
            booksrun_cash = ""
            booksrun_credit = ""
            booksrun_value = book.booksrun_value_label or ""
            offer = getattr(book, "booksrun", None)
            if offer is not None:
                if offer.cash_price is not None:
                    booksrun_cash = f"${offer.cash_price:.2f}"
                if offer.store_credit is not None:
                    booksrun_credit = f"${offer.store_credit:.2f}"
            if booksrun_value and book.booksrun_value_ratio is not None:
                try:
                    booksrun_value = f"{booksrun_value} ({book.booksrun_value_ratio:.0%})"
                except Exception:
                    booksrun_value = booksrun_value
            self.books_tree.insert(
                "",
                "end",
                iid=book.isbn,
                values=(
                    book.isbn,
                    book.metadata.title or "(untitled)",
                    authors,
                    book.edition or "",
                    cover_type,
                    printing,
                    f"${book.estimated_price:.2f}",
                    probability,
                    quantity,
                    book.condition,
                    sell_through,
                    booksrun_cash,
                    booksrun_credit,
                    booksrun_value,
                    scanned,
                ),
            )
            self._book_by_iid[book.isbn] = book
        # Select the requested ISBN when provided, otherwise fall back to first row
        target_iid = select_isbn if select_isbn and select_isbn in self._book_by_iid else None
        children = self.books_tree.get_children()
        if not target_iid and children:
            target_iid = children[0]
        if target_iid:
            self.books_tree.selection_set(target_iid)
            self.books_tree.focus(target_iid)
            try:
                self._on_book_select(None)
            except Exception:
                pass

    # Helper to populate the books table from a provided list (used by search)
    def _populate_books_from_list(self, books: Iterable[BookEvaluation]) -> None:
        for row in self.books_tree.get_children():
            self.books_tree.delete(row)
        self._book_by_iid.clear()
        for book in books:
            raw_meta = getattr(book.metadata, "raw", {}) or {}
            cover_type = raw_meta.get("cover_type") or "Unknown"
            printing = raw_meta.get("printing") or ""
            authors = ", ".join(book.metadata.authors) if book.metadata.authors else "N/A"
            sell_through = (
                f"{book.market.sell_through_rate:.0%}" if book.market and book.market.sell_through_rate else "N/A"
            )
            probability = f"{book.probability_label} ({book.probability_score:.0f})"
            scanned = self._format_timestamp(getattr(book, "created_at", None))
            quantity = str(getattr(book, "quantity", 1))
            booksrun_cash = ""
            booksrun_credit = ""
            booksrun_value = book.booksrun_value_label or ""
            offer = getattr(book, "booksrun", None)
            if offer is not None:
                if offer.cash_price is not None:
                    booksrun_cash = f"${offer.cash_price:.2f}"
                if offer.store_credit is not None:
                    booksrun_credit = f"${offer.store_credit:.2f}"
            if booksrun_value and book.booksrun_value_ratio is not None:
                try:
                    booksrun_value = f"{booksrun_value} ({book.booksrun_value_ratio:.0%})"
                except Exception:
                    booksrun_value = booksrun_value
            self.books_tree.insert(
                "",
                "end",
                iid=book.isbn,
                values=(
                    book.isbn,
                    book.metadata.title or "(untitled)",
                    authors,
                    book.edition or "",
                    cover_type,
                    printing,
                    f"${book.estimated_price:.2f}",
                    probability,
                    quantity,
                    book.condition,
                    sell_through,
                    booksrun_cash,
                    booksrun_credit,
                    booksrun_value,
                    scanned,
                ),
            )
            self._book_by_iid[book.isbn] = book
        # Auto-select first result if present
        children = self.books_tree.get_children()
        if children:
            first = children[0]
            self.books_tree.selection_set(first)
            self.books_tree.focus(first)
            try:
                self._on_book_select(None)
            except Exception:
                pass

    def _on_search(self) -> None:
        query = (self.search_var.get() or "").strip()
        if not query:
            self._populate_books()
            self._set_status("Search cleared; showing all books.")
            return
        try:
            results = self.service.search_books(query)
        except Exception as e:
            messagebox.showerror("Search", f"Search failed:\n{e}")
            return
        self._populate_books_from_list(results)
        self._set_status(f"Found {len(results)} match(es) for '{query}'")

    def _on_clear_search(self) -> None:
        self.search_var.set("")
        self._populate_books()
        self._set_status("Showing all books.")
        self._update_book_count()

    def _update_book_count(self) -> None:
        try:
            rows = self.service.db.fetch_all_books()  # type: ignore[attr-defined]
            count = len(rows)
        except Exception:
            try:
                count = len(self.service.list_books())
            except Exception:
                count = 0
        self.count_var.set(f"Books: {count}")

    def _populate_lots(self) -> None:
        for row in self.lots_tree.get_children():
            self.lots_tree.delete(row)
        self._lot_by_iid.clear()
        for lot in self.service.current_lots():
            books = list(getattr(lot, "books", []) or [])
            if not books:
                try:
                    books = self.service.get_books_for_lot(lot)
                except Exception:
                    books = []
            size = len(books)
            if size == 0:
                ids = getattr(lot, "book_isbns", None) or getattr(lot, "isbns", None) or getattr(lot, "isbn_list", None) or []
                try:
                    size = len(list(ids))
                except Exception:
                    size = 0

            series_name = getattr(lot, "series_name", None)
            if not series_name and books:
                for book in books:
                    name = getattr(book.metadata, "series_name", None)
                    if name:
                        series_name = name
                        break

            author_label = getattr(lot, "display_author_label", None) or getattr(lot, "canonical_author", "")
            author_label = author_label or ""

            base_title = getattr(lot, "name", "")
            if series_name:
                base_title = series_name
            if size:
                title = f"{base_title} (x{size})"
            else:
                title = base_title

            est_value = getattr(lot, "estimated_value", 0.0) or 0.0
            probability = getattr(lot, "probability", None) or getattr(lot, "probability_label", "")
            justification = "; ".join(getattr(lot, "justification", []) or [])

            values = (
                title,
                author_label,
                f"${est_value:,.2f}",
                probability,
                justification,
            )
            iid = self.lots_tree.insert("", "end", values=values)
            self._lot_by_iid[iid] = lot

    # ------------------------------------------------------------------
    # Helpers

    def _check_image_support(self) -> bool:
        try:
            import io as _io, requests as _requests  # type: ignore[reportMissingImports]
            from PIL import Image as _Image, ImageTk as _ImageTk  # type: ignore[reportMissingImports]
            return True
        except Exception:
            return False

    def _load_cover_image(self, url: str):
        """Fetch and cache a small thumbnail for the book cover."""
        if not url:
            return None
        if url in self._image_cache:
            return self._image_cache[url]
        # Import image libs locally to avoid optional import static warnings
        try:
            import io as _io, requests as _requests  # type: ignore[reportMissingImports]
            from PIL import Image as _Image, ImageTk as _ImageTk  # type: ignore[reportMissingImports]
        except Exception:
            try:
                if not getattr(self, "_warned_no_pil", False):
                    self._set_status("Install Pillow to enable cover thumbnails")
                    self._warned_no_pil = True
            except Exception:
                pass
            return None
        safe_url = url.replace("http://", "https://")
        path = self._cache_cover_to_disk(safe_url)
        try:
            if path and path.exists():
                with path.open("rb") as fh:
                    data = fh.read()
            else:
                resp = _requests.get(safe_url, timeout=10, headers={"User-Agent": "ISBN-Lot-Optimizer/2.0 (gui)"})
                resp.raise_for_status()
                data = resp.content
                if path:
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                    except Exception:
                        pass
            img = _Image.open(_io.BytesIO(data)).convert("RGB")
            img.thumbnail((120, 180))
            photo = _ImageTk.PhotoImage(img)
            self._image_cache[url] = photo
            return photo
        except Exception:
            self._image_cache[url] = None
            return None

    @staticmethod
    def _isbn_variants(*values: Iterable[Any] | Any) -> list[str]:
        """Return plausible ISBN-10/13 strings for cover fallbacks."""
        variants: list[str] = []
        seen: set[str] = set()

        def _add(code: Optional[str]) -> None:
            if not code:
                return
            if code in seen:
                return
            seen.add(code)
            variants.append(code)

        def _clean(value: Any) -> Optional[str]:
            if value is None:
                return None
            s = "".join(ch.upper() if ch.upper() == "X" else ch for ch in str(value) if ch.isdigit() or ch.upper() == "X")
            return s or None

        pending: list[Any] = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, (list, tuple, set, frozenset)):
                pending.extend(value)
            else:
                pending.append(value)

        for raw in pending:
            cleaned = _clean(raw)
            if not cleaned:
                continue

            if len(cleaned) == 13 and cleaned.isdigit():
                _add(cleaned)
                if cleaned.startswith(("978", "979")):
                    core = cleaned[3:12]
                    if len(core) == 9 and core.isdigit():
                        try:
                            _add(core + compute_isbn10_check_digit(core))
                        except Exception:
                            pass
                continue

            if len(cleaned) == 10 and cleaned[:9].isdigit():
                _add(cleaned)
                try:
                    _add(isbn10_to_isbn13(cleaned))
                except Exception:
                    pass
                continue

            normalized = normalise_isbn(cleaned)
            if normalized:
                _add(normalized)
                if normalized.startswith(("978", "979")):
                    core = normalized[3:12]
                    if len(core) == 9 and core.isdigit():
                        try:
                            _add(core + compute_isbn10_check_digit(core))
                        except Exception:
                            pass

        return variants

    def _cover_url_candidates(self, book: BookEvaluation) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def _add(url: Optional[str]) -> None:
            if not url:
                return
            s = str(url).strip()
            if not s or s in seen:
                return
            seen.add(s)
            candidates.append(s)

        meta = getattr(book, "metadata", None)
        if meta is not None:
            _add(getattr(meta, "cover_url", None))
            _add(getattr(meta, "thumbnail", None))
            raw = getattr(meta, "raw", None)
            if isinstance(raw, dict):
                images = raw.get("imageLinks") or {}
                if isinstance(images, dict):
                    _add(images.get("thumbnail"))
                    _add(images.get("smallThumbnail"))

        isbn_values = [getattr(meta, "isbn", None) if meta is not None else None, getattr(book, "isbn", None), getattr(book, "original_isbn", None)]
        identifiers = getattr(meta, "identifiers", ()) if meta is not None else ()
        isbn_values.append(identifiers)

        for code in self._isbn_variants(*isbn_values):
            _add(f"https://covers.openlibrary.org/b/isbn/{code}-M.jpg?default=false")
            _add(f"https://covers.openlibrary.org/b/isbn/{code}-L.jpg?default=false")

        if not candidates:
            for raw in (getattr(book, "isbn", None), getattr(book, "original_isbn", None)):
                if not raw:
                    continue
                cleaned = "".join(ch for ch in str(raw) if ch.isdigit() or ch.upper() == "X")
                if cleaned:
                    _add(f"https://covers.openlibrary.org/b/isbn/{cleaned}-M.jpg?default=false")
                    _add(f"https://covers.openlibrary.org/b/isbn/{cleaned}-L.jpg?default=false")

        return candidates

    def _best_cover_entry(self, book: BookEvaluation) -> tuple[Optional[str], Optional[Any]]:
        for url in self._cover_url_candidates(book):
            img = self._load_cover_image(url)
            if img:
                return url, img
        return None, None

    def _format_timestamp(self, value: Optional[Any]) -> str:
        if not value:
            return ""
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            if not text:
                return ""
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                if text.endswith("Z"):
                    try:
                        dt = datetime.fromisoformat(text[:-1])
                    except ValueError:
                        pass
                    else:
                        return dt.strftime("%Y-%m-%d %H:%M")
                try:
                    dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    return text
        return dt.strftime("%Y-%m-%d %H:%M")

    def _play_tone(self, tone: str) -> None:
        selection = self._sound_settings.get(tone, "system")
        if selection == "off":
            return

        if selection.startswith("chime") and self._chime_available:
            sound_id = selection.split("_", 1)[1] if "_" in selection else selection
            try:
                if sound_id == "success":
                    chime.success()  # type: ignore[arg-type]
                elif sound_id == "warning":
                    chime.warning()  # type: ignore[arg-type]
                elif sound_id == "error":
                    chime.error()  # type: ignore[arg-type]
                else:
                    chime.info()  # type: ignore[arg-type]
                return
            except Exception:
                pass

        if selection == "winsound" and self._winsound_available:
            try:
                if tone == "complete":
                    winsound.Beep(660, 150)  # type: ignore[attr-defined]
                    winsound.Beep(880, 120)  # type: ignore[attr-defined]
                elif tone == "lot":
                    winsound.Beep(523, 120)  # type: ignore[attr-defined]
                    winsound.Beep(659, 120)  # type: ignore[attr-defined]
                    winsound.Beep(784, 180)  # type: ignore[attr-defined]
                else:
                    winsound.Beep(784, 120)  # type: ignore[attr-defined]
                return
            except Exception:
                pass

        try:
            self.root.bell()
            if tone == "complete":
                self.root.after(120, self.root.bell)
            elif tone == "lot":
                self.root.after(100, self.root.bell)
                self.root.after(220, self.root.bell)
        except Exception:
            try:
                sys.stdout.write("\a")
                sys.stdout.flush()
                if tone == "complete":
                    sys.stdout.write("\a")
                    sys.stdout.flush()
                elif tone == "lot":
                    sys.stdout.write("\a")
                    sys.stdout.flush()
            except Exception:
                pass

    def _play_scan_started(self) -> None:
        self._play_tone("start")

    def _play_scan_complete(self) -> None:
        self._play_tone("complete")

    def _play_lot_match(self) -> None:
        self._play_tone("lot")

    def _focus_lot_for_isbn(self, isbn: str) -> None:
        target_iid = None
        target_lot = None
        for iid, cached in self._lot_by_iid.items():
            if self._lot_contains_isbn(cached, isbn) and self._lot_size(cached) > 1:
                target_iid = iid
                target_lot = cached
                break

        if target_iid is None:
            try:
                for lot in self.service.list_lots():
                    if self._lot_contains_isbn(lot, isbn) and self._lot_size(lot) > 1:
                        target_lot = lot
                        break
            except Exception:
                target_lot = None

        if target_iid is not None:
            try:
                self.lots_tree.selection_set(target_iid)
                self.lots_tree.focus(target_iid)
            except Exception:
                pass
            self._on_lot_select(None)
            return

        if target_lot is not None:
            try:
                books = self.service.get_books_for_lot(target_lot)
            except Exception:
                books = []
            if books:
                self._show_book_details(books[0])
            return

        book = self.service.get_book(isbn)
        if book:
            self._show_book_details(book)

    def _focus_lot_by_name(self, name: str) -> None:
        if not name:
            return
        try:
            lots = self.service.list_lots()
        except Exception:
            lots = []
        for lot in lots:
            if lot.name == name:
                self._focus_lot_object(lot)
                return

    def _focus_lot_object(self, lot) -> None:
        if lot is None:
            return
        target_iid = None
        for iid, cached in self._lot_by_iid.items():
            if getattr(cached, "name", None) == getattr(lot, "name", None) and getattr(cached, "strategy", None) == getattr(lot, "strategy", None):
                target_iid = iid
                break
        if target_iid is None:
            self._populate_lots()
            for iid, cached in self._lot_by_iid.items():
                if getattr(cached, "name", None) == getattr(lot, "name", None) and getattr(cached, "strategy", None) == getattr(lot, "strategy", None):
                    target_iid = iid
                    break
        if target_iid is not None:
            try:
                self.lots_tree.selection_set(target_iid)
                self.lots_tree.focus(target_iid)
            except Exception:
                pass
            self._on_lot_select(None)

    def _lot_size(self, lot) -> int:
        if hasattr(lot, "books") and getattr(lot, "books"):
            try:
                unique_isbns = {
                    getattr(book, "isbn", None)
                    for book in getattr(lot, "books") or []
                    if getattr(book, "isbn", None)
                }
                unique_isbns.discard(None)
                if unique_isbns:
                    return len(unique_isbns)
            except Exception:
                pass
        identifiers = (
            getattr(lot, "book_isbns", None)
            or getattr(lot, "isbns", None)
            or getattr(lot, "isbn_list", None)
            or []
        )
        try:
            unique_ids = {str(val) for val in identifiers if val}
            return len(unique_ids)
        except Exception:
            return 0

    def _get_sound_options(self) -> list[tuple[str, str]]:
        options: list[tuple[str, str]] = []
        if self._chime_available:
            options.extend(
                [
                    ("Chime: Info", "chime_info"),
                    ("Chime: Success", "chime_success"),
                    ("Chime: Warning", "chime_warning"),
                    ("Chime: Error", "chime_error"),
                ]
            )
        if self._winsound_available:
            options.append(("Windows Beep Pattern", "winsound"))
        options.append(("System Bell", "system"))
        options.append(("Silent", "off"))
        return options

    def _open_sound_preferences(self) -> None:
        if self._sound_pref_window and self._sound_pref_window.winfo_exists():
            self._sound_pref_window.focus_set()
            return

        options = self._get_sound_options()
        if not options:
            messagebox.showinfo("Sound Preferences", "No sound outputs are available on this system.")
            return

        self._sound_option_labels = [label for label, _ in options]
        self._sound_label_to_value = {label: value for label, value in options}
        value_to_label = {value: label for label, value in options}

        win = tk.Toplevel(self.root)
        win.title("Sound Preferences")
        win.transient(self.root)
        win.resizable(False, False)
        self._sound_pref_window = win
        self._sound_pref_vars = {}

        events = [
            ("Scan started", "start"),
            ("Scan complete", "complete"),
            ("Lot match", "lot"),
        ]

        ttk.Label(win, text="Select the sound to play for each event.").grid(
            row=0, column=0, columnspan=2, padx=12, pady=(12, 8), sticky="w"
        )

        for idx, (label, key) in enumerate(events, start=1):
            ttk.Label(win, text=label + ":").grid(row=idx, column=0, padx=12, pady=4, sticky="w")
            current_value = self._sound_settings.get(key, "system")
            display_value = value_to_label.get(current_value, self._sound_option_labels[0])
            var = tk.StringVar(value=display_value)
            combo = ttk.Combobox(
                win,
                textvariable=var,
                values=self._sound_option_labels,
                state="readonly",
                width=28,
            )
            combo.grid(row=idx, column=1, padx=12, pady=4, sticky="w")
            self._sound_pref_vars[key] = var

        button_frame = ttk.Frame(win)
        button_frame.grid(row=len(events) + 1, column=0, columnspan=2, pady=12)

        ttk.Button(button_frame, text="Save", command=self._save_sound_preferences).pack(side="left", padx=6)
        ttk.Button(button_frame, text="Cancel", command=self._close_sound_preferences).pack(side="left", padx=6)

        win.protocol("WM_DELETE_WINDOW", self._close_sound_preferences)

    def _save_sound_preferences(self) -> None:
        updated = False
        for key, var in self._sound_pref_vars.items():
            label = var.get()
            value = self._sound_label_to_value.get(label, "system")
            if self._sound_settings.get(key) != value:
                self._sound_settings[key] = value
                updated = True
        if updated:
            self._set_status("Sound preferences updated.")
            self._save_sound_settings()
        self._close_sound_preferences()

    def _close_sound_preferences(self) -> None:
        if self._sound_pref_window and self._sound_pref_window.winfo_exists():
            self._sound_pref_window.destroy()
        self._sound_pref_window = None
        self._sound_pref_vars = {}

    def _load_sound_settings(self) -> None:
        try:
            if self._settings_path.exists():
                payload = json.loads(self._settings_path.read_text(encoding="utf-8"))
                stored = payload.get("sound_settings")
                if isinstance(stored, dict):
                    self._sound_settings.update(stored)
        except Exception:
            pass

    def _save_sound_settings(self) -> None:
        try:
            if self._settings_path.exists():
                try:
                    payload = json.loads(self._settings_path.read_text(encoding="utf-8"))
                except Exception:
                    payload = {}
            else:
                payload = {}
            payload["sound_settings"] = self._sound_settings
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _display_cover_images(self, entries: list[tuple[Optional[str], Optional[Any]]]) -> None:
        # Clear existing thumbnails
        container = getattr(self, "cover_inner", None) or getattr(self, "cover_frame", None)
        if container is None:
            return
        for child in container.winfo_children():
            child.destroy()
        self._cover_images.clear()
        if not entries:
            ttk.Label(container, text="No thumbnail available").pack(side="left", padx=4)
            return

        sorted_entries: list[tuple[Optional[str], Optional[Any], Optional[str]]] = []
        for url, img in entries:
            matched_isbn = None
            if img:
                matched_isbn = self._isbn_for_cover(url)
            sorted_entries.append((url, img, matched_isbn))

        sorted_entries.sort(
            key=lambda item: self._book_created_at(item[2]) if item[2] else "",
            reverse=True,
        )

        for url, img, _isbn in sorted_entries:
            if img:
                label = ttk.Label(container, image=img)
                label.pack(side="left", padx=4)
                label.bind("<Button-1>", lambda e, img_url=url: self._focus_book_for_cover(img_url))
                self._cover_images.append(img)
            else:
                ttk.Label(container, text="No thumbnail available").pack(side="left", padx=4)

    def _focus_book_for_cover(self, cover_url: Optional[str]) -> None:
        if not cover_url:
            return
        target_isbn = self._isbn_for_cover(cover_url)
        if not target_isbn:
            return
        try:
            self.books_tree.selection_set(target_isbn)
            self.books_tree.focus(target_isbn)
        except Exception:
            pass
        book = self._book_by_iid.get(target_isbn)
        if book:
            self._show_book_details(book)

    def _isbn_for_cover(self, cover_url: Optional[str]) -> Optional[str]:
        if not cover_url:
            return None
        for isbn, book in self._book_by_iid.items():
            meta = getattr(book, "metadata", None)
            if not meta:
                continue
            url = getattr(meta, "cover_url", None)
            if url and url == cover_url:
                return isbn
            raw = getattr(meta, "raw", None)
            if isinstance(raw, dict):
                image_links = raw.get("imageLinks") or {}
                candidates = [
                    image_links.get("thumbnail"),
                    image_links.get("smallThumbnail"),
                ]
                if cover_url in candidates:
                    return isbn
        return None

    def _book_created_at(self, isbn: Optional[str]) -> str:
        if not isbn:
            return ""
        book = self._book_by_iid.get(isbn)
        if not book:
            try:
                book = next((b for b in self.service.list_books() if b.isbn == isbn), None)
            except Exception:
                book = None
        if book is None:
            return ""
        created_at = getattr(book, "created_at", None)
        if not created_at:
            return ""
        try:
            return str(created_at)
        except Exception:
            return ""

    def _trigger_cover_prefetch(self) -> None:
        if self._cover_prefetch_thread and self._cover_prefetch_thread.is_alive():
            return

        urls = self._gather_cover_urls()
        if not urls:
            self.root.after(0, lambda: self._reset_progress("prefetch"))
            return

        def worker(items: list[str]) -> None:
            try:
                total = len(items)
                self.root.after(
                    0,
                    lambda: self._start_progress("prefetch", "Prefetch", total, replace_existing=False),
                )
                done = 0
                for url in items:
                    self._cache_cover_to_disk(url)
                    done += 1
                    self.root.after(0, self._update_progress, "prefetch", done, total)
            finally:
                self._cover_prefetch_thread = None
                self.root.after(
                    0,
                    lambda: self._finish_progress("prefetch", label="Prefetch", delay_ms=1200),
                )

        self._cover_prefetch_thread = threading.Thread(target=worker, args=(urls,), daemon=True)
        self._cover_prefetch_thread.start()

    def _gather_cover_urls(self) -> list[str]:
        urls: set[str] = set()
        try:
            books = self.service.list_books()
        except Exception:
            books = []
        for book in books:
            for url in self._cover_url_candidates(book):
                if not url:
                    continue
                path = self._cache_cover_path(url)
                fail_path = self._cache_cover_fail_path(path) if path else None
                if path and path.exists():
                    continue
                if fail_path and fail_path.exists():
                    continue
                urls.add(url)
        return sorted(urls)

    def _cache_cover_path(self, url: str) -> Optional[Path]:
        if not url:
            return None
        safe_url = url.replace("http://", "https://")
        digest = hashlib.sha256(safe_url.encode("utf-8")).hexdigest()
        parsed = urllib.parse.urlparse(safe_url)
        ext = Path(parsed.path).suffix
        if not ext or len(ext) > 5:
            ext = ".jpg"
        return COVER_CACHE_DIR / f"{digest}{ext}"

    def _cache_cover_to_disk(self, url: str) -> Optional[Path]:
        if not url:
            return None
        safe_url = url.replace("http://", "https://")
        path = self._cache_cover_path(safe_url)
        if not path:
            return None
        if path.exists():
            fail_path = self._cache_cover_fail_path(path)
            if fail_path and fail_path.exists():
                try:
                    fail_path.unlink()
                except Exception:
                    pass
            return path
        try:
            import requests  # type: ignore[reportMissingImports]
        except Exception:
            return None
        try:
            resp = requests.get(safe_url, timeout=10, headers={"User-Agent": "ISBN-Lot-Optimizer/2.0 (prefetch)"})
            resp.raise_for_status()
        except Exception:
            fail_path = self._cache_cover_fail_path(path)
            if fail_path:
                try:
                    fail_path.parent.mkdir(parents=True, exist_ok=True)
                    fail_path.touch(exist_ok=True)
                except Exception:
                    pass
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)
            fail_path = self._cache_cover_fail_path(path)
            if fail_path and fail_path.exists():
                try:
                    fail_path.unlink()
                except Exception:
                    pass
            return path
        except Exception:
            return None

    def _cache_cover_fail_path(self, path: Optional[Path]) -> Optional[Path]:
        if not path:
            return None
        return path.with_suffix(path.suffix + ".fail")

    def _start_progress(self, task: str, label: str, total: int, *, replace_existing: bool = True) -> None:
        if not replace_existing and self._progress_task and self._progress_task != task:
            return
        self._cancel_progress_reset()
        self._progress_task = task
        self._progress_label = label
        self._progress_total = max(int(total or 0), 1)
        self._progress_done = 0
        try:
            self.preload_progress.config(mode="determinate", maximum=self._progress_total)
            self.preload_progress['value'] = 0
        except Exception:
            pass
        display_label = label or task.title()
        self.preload_text.set(f"{display_label} 0%")

    def _update_progress(self, task: str, done: int, total: Optional[int] = None) -> None:
        if task != self._progress_task:
            return
        if total is not None and total > 0 and total != self._progress_total:
            self._progress_total = max(int(total), 1)
            try:
                self.preload_progress.config(maximum=self._progress_total)
            except Exception:
                pass
        self._progress_done = max(0, min(int(done), self._progress_total))
        try:
            self.preload_progress['value'] = self._progress_done
        except Exception:
            pass
        denominator = self._progress_total or 1
        percent = int((self._progress_done / denominator) * 100)
        label = self._progress_label or task.title()
        self.preload_text.set(f"{label} {percent}%")

    def _finish_progress(self, task: str, *, label: Optional[str] = None, delay_ms: int = 1200) -> None:
        if task != self._progress_task:
            return
        maximum = self._progress_total or max(self._progress_done, 1)
        try:
            self.preload_progress.config(maximum=maximum)
            self.preload_progress['value'] = maximum
        except Exception:
            pass
        label_text = label or self._progress_label or task.title()
        self.preload_text.set(f"{label_text} 100%")
        self._schedule_progress_reset(task, delay_ms)

    def _schedule_progress_reset(self, task: str, delay_ms: int) -> None:
        self._cancel_progress_reset()

        def _do_reset() -> None:
            self._progress_reset_job = None
            self._reset_progress(task)

        self._progress_reset_job = self.root.after(max(delay_ms, 0), _do_reset)

    def _cancel_progress_reset(self) -> None:
        if not self._progress_reset_job:
            return
        try:
            self.root.after_cancel(self._progress_reset_job)
        except Exception:
            pass
        self._progress_reset_job = None

    def _reset_progress(self, task: Optional[str] = None) -> None:
        if task is not None and self._progress_task != task:
            return
        self._cancel_progress_reset()
        self._progress_task = None
        self._progress_label = ""
        self._progress_total = 0
        self._progress_done = 0
        try:
            self.preload_progress['value'] = 0
        except Exception:
            pass
        self.preload_text.set("")

    def _lots_for_book(self, isbn: str) -> list[str]:
        try:
            lots = self.service.list_lots()
        except Exception:
            lots = []
        names: list[str] = []
        for lot in lots:
            if isbn in lot.book_isbns:
                names.append(lot.name)
        return names

    def _show_cover_cache_info(self) -> None:
        loaded = sum(1 for img in self._image_cache.values() if img is not None)
        total = len(self._image_cache)
        failed_urls = [url for url, img in self._image_cache.items() if img is None]

        lines = [
            f"Cover image support: {'enabled' if self._image_supported else 'disabled'}",
            f"Cached lookups: {total}",
            f"Successful images: {loaded}",
        ]
        if failed_urls:
            lines.append("")
            lines.append("Failed URL(s):")
            lines.extend(f" - {url}" for url in failed_urls[:10])
            if len(failed_urls) > 10:
                lines.append(f"…and {len(failed_urls) - 10} more")
        messagebox.showinfo("Cover Cache", "\n".join(lines))

    def _show_cover_sources(self) -> None:
        selected = self.books_tree.focus()
        if not selected:
            selection = self.books_tree.selection()
            if selection:
                selected = selection[0]
        if not selected:
            messagebox.showinfo("Cover Sources", "Select a book first.")
            return
        values = self.books_tree.item(selected).get("values", [])
        isbn = values[0] if values else None
        if not isbn:
            messagebox.showinfo("Cover Sources", "Unable to locate the selected book in memory.")
            return
        book = self._book_by_iid.get(isbn)
        if not book:
            book = next((b for b in self.service.list_books() if b.isbn == isbn), None)
            if book:
                self._book_by_iid[isbn] = book
        if not book:
            messagebox.showinfo("Cover Sources", "Unable to locate the selected book in memory.")
            return

        urls = self._cover_url_candidates(book)
        if not urls:
            messagebox.showinfo("Cover Sources", "No candidate cover URLs were generated for this book.")
            return

        text = "\n".join(urls[:10])
        if len(urls) > 10:
            text += f"\n…and {len(urls) - 10} more"
        messagebox.showinfo("Cover Sources", text)

    def _show_book_details(self, book: BookEvaluation) -> None:
        url, img = self._best_cover_entry(book)
        self._display_cover_images([(url, img)])

        if img:
            self._set_status(f"Cover loaded for {book.isbn}")
        else:
            self._set_status(f"No thumbnail available for {book.isbn}")

        lines = [
            f"Title: {book.metadata.title}",
            f"ISBN: {book.isbn}",
            f"Authors: {', '.join(book.metadata.authors) if book.metadata.authors else 'N/A'}",
            f"Estimated price: ${book.estimated_price:.2f}",
            f"Probability: {book.probability_label} ({book.probability_score:.1f})",
            f"Condition: {book.condition}",
            f"Quantity: {getattr(book, 'quantity', 1)}",
        ]
        if book.market and book.market.sell_through_rate is not None:
            lines.append(f"Sell-through: {book.market.sell_through_rate:.0%}")
        if book.market and book.market.sold_avg_price:
            lines.append(f"Avg sold price: ${book.market.sold_avg_price:.2f}")
        if book.rarity is not None:
            lines.append(f"Rarity score: {book.rarity:.2f}")
        if book.edition:
            lines.append(f"Edition notes: {book.edition}")
        offer = getattr(book, "booksrun", None)
        if offer is not None:
            if offer.cash_price is not None:
                lines.append(f"BooksRun cash offer: ${offer.cash_price:.2f}")
            if offer.store_credit is not None:
                lines.append(f"BooksRun credit offer: ${offer.store_credit:.2f}")
            if book.booksrun_value_label:
                if book.booksrun_value_ratio is not None:
                    lines.append(
                        f"BooksRun value: {book.booksrun_value_label} ({book.booksrun_value_ratio:.0%} of estimate)"
                    )
                else:
                    lines.append(f"BooksRun value: {book.booksrun_value_label}")
            if getattr(offer, "url", None):
                lines.append(f"BooksRun link: {offer.url}")
        created_at = getattr(book, "created_at", None)
        if created_at:
            lines.append(f"Scanned: {self._format_timestamp(created_at)}")
        lots = self._lots_for_book(book.isbn)
        if lots:
            lines.append("")
            lines.append("Lots:")
            for name in lots:
                lines.append(f" - {name}")
        if book.justification:
            lines.append("")
            lines.append("Reasons:")
            lines.extend(f" - {reason}" for reason in book.justification)
        self._set_detail_text("\n".join(lines))
        if lots:
            self._link_lot_names(lots)

    def _set_detail_text(self, text: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("end", text)
        self.detail_text.tag_remove("lot_link", "1.0", "end")
        self.detail_text.configure(state="disabled")

    def _link_lot_names(self, lot_names: list[str]) -> None:
        if not lot_names:
            return
        self.detail_text.configure(state="normal")
        for name in lot_names:
            start = "1.0"
            while True:
                idx = self.detail_text.search(name, start, stopindex="end")
                if not idx:
                    break
                end = f"{idx}+{len(name)}c"
                self.detail_text.tag_add("lot_link", idx, end)
                self.detail_text.tag_config("lot_link", foreground="blue", underline=True)
                self.detail_text.tag_bind("lot_link", "<Button-1>", self._on_lot_link_click)
                start = end
        self.detail_text.configure(state="disabled")

    def _on_lot_link_click(self, event) -> None:
        index = self.detail_text.index(f"@{event.x},{event.y}")
        ranges = self.detail_text.tag_prevrange("lot_link", index)
        if not ranges:
            return
        start, end = ranges
        lot_name = self.detail_text.get(start, end)
        self._focus_lot_by_name(lot_name)

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _enqueue_series_enrichment(self, isbn: str) -> None:
        """
        Background-enrich a single ISBN with series data from Hardcover.
        Uses a fresh sqlite3 connection to avoid cross-thread issues.
        """
        def worker() -> None:
            conn = None
            try:
                from .services.hardcover import HardcoverClient
                from .services.series_resolver import (
                    ensure_series_schema,
                    get_series_for_isbn,
                    update_book_row_with_series,
                )
                # Separate connection for thread-safety
                conn = self.service.db._get_connection()  # type: ignore[attr-defined]
                ensure_series_schema(conn)
                hc = HardcoverClient()
                series = get_series_for_isbn(conn, isbn, hc)
                if series.get("confidence", 0) >= 0.6 and series.get("series_name"):
                    update_book_row_with_series(conn, isbn, series)
                else:
                    try:
                        conn.execute("UPDATE books SET series_last_checked = CURRENT_TIMESTAMP WHERE isbn = ?", (isbn,))
                        conn.commit()
                    except Exception:
                        pass
                try:
                    self.root.after(0, lambda: self._set_status(f"Series resolved for {isbn}"))
                except Exception:
                    pass
            except Exception:
                # Soft-fail; do not surface token or stack traces in GUI
                pass
            finally:
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _enqueue_series_backfill(self, limit: int = 200) -> None:
        """
        Background backfill of missing series rows after bulk import.
        """
        if not isinstance(limit, int) or limit <= 0:
            limit = 200

        def worker() -> None:
            conn = None
            try:
                from .services.hardcover import HardcoverClient
                from .services.series_resolver import (
                    ensure_series_schema,
                    get_series_for_isbn,
                    update_book_row_with_series,
                )
                conn = self.service.db._get_connection()  # type: ignore[attr-defined]
                ensure_series_schema(conn)
                hc = HardcoverClient()
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT isbn FROM books
                    WHERE (series_name IS NULL OR series_name = '')
                      AND isbn IS NOT NULL AND length(isbn)=13
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                )
                rows = [r[0] for r in cur.fetchall()]
                total = len(rows)
                if total:
                    try:
                        self.root.after(0, lambda: self._start_progress("series", "Series", total))
                    except Exception:
                        pass
                done = 0
                for code in rows:
                    try:
                        series = get_series_for_isbn(conn, code, hc)
                        if series.get("confidence", 0) >= 0.6 and series.get("series_name"):
                            update_book_row_with_series(conn, code, series)
                        else:
                            cur.execute("UPDATE books SET series_last_checked = CURRENT_TIMESTAMP WHERE isbn = ?", (code,))
                            conn.commit()
                    except Exception:
                        try:
                            cur.execute("UPDATE books SET series_last_checked = CURRENT_TIMESTAMP WHERE isbn = ?", (code,))
                            conn.commit()
                        except Exception:
                            pass
                    done += 1
                    try:
                        self.root.after(0, self._update_progress, "series", done, total)
                    except Exception:
                        pass
                try:
                    self.root.after(0, lambda: self._finish_progress("series", label="Series", delay_ms=1000))
                except Exception:
                    pass
            finally:
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self.service.close()
