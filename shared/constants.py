"""Shared constants and patterns used across the application."""
from __future__ import annotations

import re

# Title normalization - removes all non-alphanumeric characters
TITLE_NORMALIZER = re.compile(r"[^a-z0-9]+")

# Author name splitting on common delimiters
AUTHOR_SPLIT_RE = re.compile(r"[,;&]")

# Cover type options
COVER_CHOICES = [
    "Hardcover",
    "Trade Paperback",
    "Mass Market Paperback",
    "Library Binding",
    "Unknown",
]

# BooksRun fallback credentials (used when env vars not set)
BOOKSRUN_FALLBACK_KEY = "a08gyu3z4mmoro511yu0"
BOOKSRUN_FALLBACK_AFFILIATE = "18807"

# BookScouter API (replaces BooksRun with multi-vendor aggregation)
BOOKSCOUTER_FALLBACK_KEY = "0c7cd0b1712cd7da21d1a4d4855667ed"

# Default database path
DEFAULT_DB_NAME = "catalog.db"
DEFAULT_DB_DIR = ".isbn_lot_optimizer"
