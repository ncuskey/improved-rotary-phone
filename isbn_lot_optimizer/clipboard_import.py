from __future__ import annotations

import csv
import io
import re
import statistics as st
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


PRICE_COL_RE = re.compile(r"\b((sold|final)\s*price)\b", re.IGNORECASE)
FALLBACK_PRICE_RE = re.compile(r"\b(total\s*price|price)\b", re.IGNORECASE)
CURR_COL_RE = re.compile(r"\b(currency|curr|price\s*currency)\b", re.IGNORECASE)
TITLE_COL_RE = re.compile(r"\b(title|item\s*title|name)\b", re.IGNORECASE)
COND_COL_RE = re.compile(r"\b(condition)\b", re.IGNORECASE)
DATE_COL_RE = re.compile(r"\b(sold|end|date|ended)\b", re.IGNORECASE)
QTY_COL_RE = re.compile(r"\b(qty|quantity)\b", re.IGNORECASE)


LOT_KEYWORDS = re.compile(r"\b(lot|set|bundle|collection|series)\b", re.IGNORECASE)
EX_RDIGEST = re.compile(r"reader'?s\s+digest|condensed\s+books?", re.IGNORECASE)
EX_BOOK_CLUB = re.compile(r"\b(book\s*club|BCE)\b", re.IGNORECASE)
EX_LARGE_PRINT = re.compile(r"\blarge\s*print\b", re.IGNORECASE)
EX_PICK_CHOOSE = re.compile(r"\b(you\s*pick|pick\s*(one|any)|choose)\b", re.IGNORECASE)
EX_ABRIDGED = re.compile(r"\babridged\b", re.IGNORECASE)


ALLOW_COND = {
    "VERY GOOD",
    "LIKE NEW",
    "GOOD",
    "ACCEPTABLE",
    "NEW",
    "BRAND NEW",
    "EXCELLENT",
}

def _normalize_cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        # Flatten lists of cell fragments (e.g., when a parser returns multiple pieces)
        return " ".join(_normalize_cell(x) for x in v).strip()
    if isinstance(v, (int, float)):
        return str(v)
    # Fallback to string; also trim surrounding whitespace
    return str(v).strip()


def _num_from_text(txt: str) -> Optional[float]:
    if not txt:
        return None
    s = str(txt).replace(",", "").strip()
    nums = re.findall(r"(\d+(?:\.\d+)?)", s)
    if not nums:
        return None
    vals = [float(x) for x in nums]
    if len(vals) >= 2 and ("-" in s or "–" in s or "to" in s.lower()):
        return round((vals[0] + vals[1]) / 2.0, 2)
    return round(vals[0], 2)


def _winsor(xs: List[float], p: float = 0.10) -> List[float]:
    ys: List[float] = sorted(float(v) for v in xs if isinstance(v, (int, float)) and v > 0)
    if len(ys) < 3:
        return ys
    k = max(1, int(len(ys) * p))
    trimmed: List[float] = ys[k : len(ys) - k] or ys
    return trimmed


def _parse_date(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%d %b %Y", "%b-%d-%y"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "").split("T")[0])
    except Exception:
        return None


class ImportOptions:
    def __init__(
        self,
        *,
        require_lot_keyword: bool = True,
        exclude_readers_digest: bool = True,
        exclude_book_club: bool = True,
        exclude_large_print: bool = False,
        exclude_pick_choose: bool = True,
        exclude_abridged: bool = True,
        min_items_if_present: int = 2,
        usd_only: bool = True,
        min_condition: Optional[str] = None,
        last_n_days: Optional[int] = 180,
    ) -> None:
        self.require_lot_keyword = require_lot_keyword
        self.exclude_readers_digest = exclude_readers_digest
        self.exclude_book_club = exclude_book_club
        self.exclude_large_print = exclude_large_print
        self.exclude_pick_choose = exclude_pick_choose
        self.exclude_abridged = exclude_abridged
        self.min_items_if_present = min_items_if_present
        self.usd_only = usd_only
        self.min_condition = (min_condition or "").upper() if min_condition else None
        self.last_n_days = last_n_days


def _row_is_relevant(row: Dict[str, Any], headers: List[str], opt: ImportOptions) -> bool:
    title = ""
    condition = ""
    currency = ""
    qty_txt = ""

    for h in headers:
        if not isinstance(h, str) or not h:
            continue
        value = _normalize_cell(row.get(h))
        if TITLE_COL_RE.search(h):
            title = value
        if COND_COL_RE.search(h):
            condition = value
        if CURR_COL_RE.search(h):
            currency = value
        if QTY_COL_RE.search(h):
            qty_txt = value

    title_lower = title.lower()

    if opt.usd_only and currency:
        if currency.upper() not in {"USD", "US", "US DOLLAR", "US$"}:
            return False

    if opt.require_lot_keyword and not LOT_KEYWORDS.search(title_lower):
        try:
            quantity = int(re.findall(r"\d+", qty_txt)[0])
            if quantity < opt.min_items_if_present:
                return False
        except Exception:
            return False

    if opt.exclude_readers_digest and EX_RDIGEST.search(title_lower):
        return False
    if opt.exclude_book_club and EX_BOOK_CLUB.search(title_lower):
        return False
    if opt.exclude_large_print and EX_LARGE_PRINT.search(title_lower):
        return False
    if opt.exclude_pick_choose and EX_PICK_CHOOSE.search(title_lower):
        return False
    if opt.exclude_abridged and EX_ABRIDGED.search(title_lower):
        return False

    if opt.min_condition and condition:
        if condition.upper() not in ALLOW_COND:
            return False

    return True


def _date_in_range(row: Dict[str, Any], headers: List[str], opt: ImportOptions) -> bool:
    if not opt.last_n_days:
        return True
    cutoff = datetime.utcnow() - timedelta(days=opt.last_n_days)
    for h in headers:
        if not isinstance(h, str) or not h:
            continue
        if DATE_COL_RE.search(h):
            dt = _parse_date(_normalize_cell(row.get(h)))
            if dt:
                return dt >= cutoff
    return True


def _any_date_in_text_within_range(text: str, last_n_days: Optional[int]) -> bool:
    if not last_n_days:
        return True
    cutoff = datetime.utcnow() - timedelta(days=last_n_days)
    # Allow both abbreviated and full month names, e.g., "Jul 21, 2025" or "July 21, 2025"
    for m in re.finditer(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}",
        text,
        re.IGNORECASE,
    ):
        s = m.group(0)
        dt = _parse_date(s)
        if not dt:
            try:
                dt = datetime.strptime(s, "%B %d, %Y")
            except Exception:
                dt = None
        if dt:
            return dt >= cutoff
    # If no date found, treat as acceptable (consistent with CSV path)
    return True


def parse_terapeak_plain_text(text: str, opt: ImportOptions) -> Dict[str, Any]:
    # Split Terapeak "Product research" rows by the "Edit" marker commonly present per row.
    blocks = re.split(r"\n\s*Edit\s*\n", text)
    prices: List[float] = []
    used = 0
    skipped = 0

    for b in blocks:
        if not b or not b.strip():
            continue
        t = b.lower()

        # Relevance filters mirrored from CSV path
        if opt.require_lot_keyword and not LOT_KEYWORDS.search(t):
            skipped += 1
            continue
        if opt.exclude_pick_choose and EX_PICK_CHOOSE.search(t):
            skipped += 1
            continue
        if opt.exclude_readers_digest and EX_RDIGEST.search(t):
            skipped += 1
            continue
        if opt.exclude_book_club and EX_BOOK_CLUB.search(t):
            skipped += 1
            continue
        if opt.exclude_abridged and EX_ABRIDGED.search(t):
            skipped += 1
            continue
        if not _any_date_in_text_within_range(b, opt.last_n_days):
            skipped += 1
            continue

        # Prefer "Avg sold price", fallback to a $ near "Fixed price"/"Auction"
        m = re.search(r"Avg\s+sold\s+price\s*\$?\s*([0-9]+(?:\.[0-9]{2})?)", b, re.IGNORECASE)
        if not m:
            m = re.search(r"(Fixed price|Auction).*?\$([0-9]+(?:\.[0-9]{2})?)", b, re.IGNORECASE | re.DOTALL)
            val = float(m.group(2)) if m else None
        else:
            val = float(m.group(1))

        if val and val > 0:
            prices.append(val)
            used += 1
        else:
            skipped += 1

    filtered = _winsor(prices)
    return {
        "prices": filtered,
        "used": used,
        "skipped": skipped,
        "median": round(st.median(filtered), 2) if filtered else None,
        "count_before": used + skipped,
        "count_after": len(filtered),
    }


def parse_prices_from_clipboard_text(text: str, opt: Optional[ImportOptions] = None) -> Dict[str, Any]:
    opt = opt or ImportOptions()
    result: Dict[str, Any] = {
        "prices": [],
        "used": 0,
        "skipped": 0,
        "median": None,
        "count_before": 0,
        "count_after": 0,
    }

    if not text:
        return result

    for delim in ("\t", ","):
        try:
            rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
        except Exception:
            rows = []
        if rows and rows[0]:
            raw_headers = list(rows[0].keys())
            headers = [h for h in raw_headers if isinstance(h, str) and h]
            price_cols = [h for h in headers if PRICE_COL_RE.search(h or "")]
            if not price_cols:
                price_cols = [h for h in headers if FALLBACK_PRICE_RE.search(h or "")]

            all_prices: List[float] = []
            for row in rows:
                result["count_before"] += 1

                if not _row_is_relevant(row, headers, opt) or not _date_in_range(row, headers, opt):
                    result["skipped"] += 1
                    continue

                value: Optional[float] = None
                for col in price_cols:
                    value = _num_from_text(_normalize_cell(row.get(col)))
                    if value is not None:
                        break
                if value is None and "price" in {h.lower() for h in headers}:
                    value = _num_from_text(_normalize_cell(row.get("price")))

                if value is not None and value > 0:
                    all_prices.append(value)
                    result["used"] += 1
                else:
                    result["skipped"] += 1

            filtered = _winsor(all_prices)
            result["prices"] = filtered
            result["count_after"] = len(filtered)
            if filtered:
                result["median"] = round(st.median(filtered), 2)
                return result
            # No CSV-derived prices; continue to try next delimiter or plain-text fallback

    # Terapeak plain-text block parser fallback (for full-page copies)
    ter = parse_terapeak_plain_text(text, opt)
    result.update(
        {
            "prices": ter.get("prices", []),
            "used": ter.get("used", 0),
            "skipped": ter.get("skipped", 0),
            "median": ter.get("median"),
            "count_before": ter.get("count_before", 0),
            "count_after": ter.get("count_after", 0),
        }
    )
    return result
