from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Iterable, Optional, overload

import requests  # type: ignore[reportMissingImports]

from shared.author_aliases import canonical_author as _alias_canonical_author
from shared.series_finder import attach_series

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPENLIB_DATA_URL = "https://openlibrary.org/api/books"
OPENLIB_ISBN_JSON = "https://openlibrary.org/isbn/{isbn}.json"
OPENLIB_WORK_JSON = "https://openlibrary.org{work_key}.json"
OPENLIB_COVER_TMPL = "https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"
OPENLIB_COVER_BY_ID = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"

CACHE_PATH = os.path.expanduser("~/.isbn_lot_optimizer/gbooks_cache.json")
CACHE_TTL_DAYS = 365
_CACHE_TTL_SECONDS = CACHE_TTL_DAYS * 24 * 60 * 60
_DEFAULT_HEADERS = {
    "User-Agent": "ISBN-Lot-Optimizer/3.0 (+https://github.com/)",
    "Accept": "application/json",
}
_REQUEST_TIMEOUT = 15


def enrich_authorship(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Populate credited_authors and canonical_author on metadata dicts."""
    credited = meta.get("authors") or meta.get("author") or []
    if isinstance(credited, str):
        credited = [credited]
    credited_list = [str(a).strip() for a in credited if str(a).strip()]
    if not credited_list:
        credited_list = ["Unknown"]
    canonical = _alias_canonical_author(credited_list[0]) or credited_list[0]
    meta["credited_authors"] = credited_list
    meta["canonical_author"] = canonical
    return meta


def _finalise_meta(meta: Dict[str, Any], isbn: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    """Ensure metadata dict includes canonical authorship and series info."""
    if not isinstance(meta, dict):
        return meta
    result = dict(meta)

    authors = result.get("authors")
    if isinstance(authors, tuple):
        authors = list(authors)
    if isinstance(authors, str):
        authors = [authors]
    if authors is None:
        authors = []
    result["authors"] = authors

    sess = session
    created_session = False
    if not sess:
        sess = requests.Session()
        sess.headers.update(_DEFAULT_HEADERS)
        created_session = True

    try:
        result = enrich_authorship(result)
        result = attach_series(result, isbn, session=sess)
    finally:
        if created_session:
            try:
                sess.close()
            except Exception:
                pass

    return result


# ------------------------------ Cache helpers ------------------------------ #
def _cache_load() -> Dict[str, Any]:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _cache_save(obj: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def cache_get(isbn: str) -> Optional[Dict[str, Any]]:
    key = _clean_isbn(isbn)
    if not key:
        return None
    data = _cache_load()
    entry = data.get(key)
    if not isinstance(entry, dict):
        return None
    timestamp = entry.get("ts")
    if not isinstance(timestamp, (int, float)):
        return None
    if time.time() - float(timestamp) > _CACHE_TTL_SECONDS:
        return None
    meta = entry.get("meta")
    return meta if isinstance(meta, dict) else None


def cache_set(isbn: str, meta: Dict[str, Any]) -> None:
    key = _clean_isbn(isbn)
    if not key or not isinstance(meta, dict):
        return
    data = _cache_load()
    data[key] = {"ts": time.time(), "meta": meta}
    _cache_save(data)


# ------------------------------ ISBN utilities ----------------------------- #
def _clean_isbn(value: str | None) -> str:
    if value is None:
        return ""
    stripped = re.sub(r"[^0-9Xx]", "", value.strip())
    return stripped.upper()


def _is_isbn10(value: str) -> bool:
    return bool(re.fullmatch(r"\d{9}[\dX]", value))


def _is_isbn13(value: str) -> bool:
    return bool(re.fullmatch(r"\d{13}", value))


def _isbn10_checkdigit(prefix: str) -> str:
    total = sum((10 - idx) * int(d) for idx, d in enumerate(prefix))
    remainder = 11 - (total % 11)
    if remainder == 10:
        return "X"
    if remainder == 11:
        return "0"
    return str(remainder)


def _isbn13_checkdigit(prefix: str) -> str:
    total = 0
    for idx, digit in enumerate(prefix):
        weight = 1 if idx % 2 == 0 else 3
        total += int(digit) * weight
    return str((10 - (total % 10)) % 10)


def isbn10_to_isbn13(isbn10: str | None) -> Optional[str]:
    cleaned = _clean_isbn(isbn10)
    if not _is_isbn10(cleaned):
        return None
    core = "978" + cleaned[:9]
    return core + _isbn13_checkdigit(core)


def isbn13_to_isbn10(isbn13: str | None) -> Optional[str]:
    cleaned = _clean_isbn(isbn13)
    if not _is_isbn13(cleaned) or not cleaned.startswith(("978", "979")):
        return None
    body = cleaned[3:12]
    return body + _isbn10_checkdigit(body)


def _isbn_language_hint(isbn13: str | None) -> Optional[str]:
    cleaned = _clean_isbn(isbn13)
    if not _is_isbn13(cleaned):
        return None
    if cleaned.startswith(("9780", "9781")):
        return "en"
    if cleaned.startswith("9782"):
        return "fr"
    if cleaned.startswith("9783"):
        return "de"
    if cleaned.startswith("9784"):
        return "ja"
    if cleaned.startswith("9785"):
        return "ru"
    if cleaned.startswith("9787"):
        return "zh"
    if cleaned.startswith(("97880", "97881", "97882")):
        return "cs"
    if cleaned.startswith("97884"):
        return "es"
    if cleaned.startswith(("97910", "97911")):
        return "fr"
    return None


# ------------------------------ HTTP helpers ------------------------------ #
def create_http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)
    return session


def _fetch_google_books_raw(isbn: str, api_key: Optional[str], sess: requests.Session) -> Optional[Dict[str, Any]]:
    params = {
        "q": f"isbn:{isbn}",
        "maxResults": "5",
        "printType": "books",
        "fields": (
            "items(volumeInfo/title,volumeInfo/subtitle,volumeInfo/authors,"
            "volumeInfo/publisher,volumeInfo/publishedDate,volumeInfo/pageCount,"
            "volumeInfo/categories,volumeInfo/averageRating,volumeInfo/ratingsCount,"
            "volumeInfo/language,volumeInfo/industryIdentifiers,"
            "volumeInfo/imageLinks/thumbnail,volumeInfo/description)"
        ),
    }
    if api_key:
        params["key"] = api_key
    try:
        response = sess.get(GOOGLE_BOOKS_URL, params=params, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code == 429:
        return None
    try:
        response.raise_for_status()
    except requests.HTTPError:
        return None
    try:
        payload = response.json() or {}
    except ValueError:
        return None
    items = payload.get("items") or []
    for item in items:
        info = item.get("volumeInfo")
        if isinstance(info, dict):
            return info
    return None


def _normalize_from_gbooks(info: Dict[str, Any]) -> Dict[str, Any]:
    identifiers = info.get("industryIdentifiers") or []
    isbn_10 = None
    isbn_13 = None
    for ident in identifiers:
        if not isinstance(ident, dict):
            continue
        if ident.get("type") == "ISBN_10" and ident.get("identifier"):
            isbn_10 = ident["identifier"].replace("-", "")
        if ident.get("type") == "ISBN_13" and ident.get("identifier"):
            isbn_13 = ident["identifier"].replace("-", "")

    title = info.get("title")
    subtitle = info.get("subtitle")
    authors = [str(a) for a in info.get("authors", []) if a]
    published_date = (info.get("publishedDate") or "").strip()
    match = re.match(r"^(\d{4})", published_date)
    publication_year = int(match.group(1)) if match else None

    combined_title = " ".join(filter(None, [title, subtitle]))
    series_name = None
    series_index: Optional[int] = None
    paren_match = re.search(r"\(([^()]+?),\s*#?(\d+)\)", combined_title)
    if paren_match:
        series_name = paren_match.group(1).strip()
        try:
            series_index = int(paren_match.group(2))
        except ValueError:
            series_index = None
    else:
        alt_match = re.search(r"(?:Book|Vol(?:ume)?)\s*(\d+)\s+of\s+([A-Za-z0-9'\-\s]+)", combined_title, flags=re.IGNORECASE)
        if alt_match:
            try:
                series_index = int(alt_match.group(1))
            except ValueError:
                series_index = None
            series_name = alt_match.group(2).strip()

    categories = [str(cat) for cat in info.get("categories", []) if cat]
    categories_str = ", ".join(categories) if categories else None

    image_links = info.get("imageLinks") or {}
    cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
    if isinstance(cover_url, str) and cover_url.startswith("http://"):
        cover_url = "https://" + cover_url[len("http://") :]

    return {
        "title": title,
        "subtitle": subtitle,
        "authors": authors,
        "authors_str": ", ".join(authors) if authors else None,
        "publisher": info.get("publisher"),
        "published_date": published_date or None,
        "publication_year": publication_year,
        "page_count": info.get("pageCount"),
        "categories": categories,
        "categories_str": categories_str,
        "average_rating": info.get("averageRating"),
        "ratings_count": info.get("ratingsCount"),
        "language": info.get("language"),
        "cover_url": cover_url,
        "description": info.get("description"),
        "isbn_10": isbn_10,
        "isbn_13": isbn_13,
        "series_name": series_name,
        "series_index": series_index,
        "source": "google_books",
        "raw": {"imageLinks": image_links},
    }


def _fetch_open_library(isbn: str, sess: requests.Session) -> Optional[Dict[str, Any]]:
    params = {"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"}
    try:
        response = sess.get(OPENLIB_DATA_URL, params=params, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        payload = response.json() or {}
    except ValueError:
        return None
    record = payload.get(f"ISBN:{isbn}")
    if not isinstance(record, dict):
        return None

    title = record.get("title")
    authors_raw = record.get("authors") or []
    authors: list[str] = [str(a.get("name")) for a in authors_raw if isinstance(a, dict) and a.get("name")]
    publish_date = (record.get("publish_date") or "").strip()
    year_match = re.search(r"(\d{4})", publish_date)
    publication_year = int(year_match.group(1)) if year_match else None

    subjects_raw = record.get("subjects") or []
    categories: list[str] = [str(s.get("name")) for s in subjects_raw if isinstance(s, dict) and s.get("name")]
    categories_str = ", ".join(categories) if categories else None

    series_list = record.get("series") or []
    series_name = series_list[0] if series_list and isinstance(series_list[0], str) else None

    identifiers = record.get("identifiers") or {}
    isbn_10 = None
    isbn_13 = None
    if isinstance(identifiers, dict):
        if identifiers.get("isbn_10"):
            isbn_10 = identifiers["isbn_10"][0]
        if identifiers.get("isbn_13"):
            isbn_13 = identifiers["isbn_13"][0]

    languages_list = record.get("languages") or []
    language = None
    if languages_list and isinstance(languages_list[0], dict):
        key = languages_list[0].get("key", "").split("/")[-1]
        map_lang = {"eng": "en", "fre": "fr", "fra": "fr", "ger": "de", "deu": "de", "spa": "es"}
        language = map_lang.get(key, key or None)

    return {
        "title": title,
        "subtitle": None,
        "authors": authors,
        "authors_str": ", ".join(authors) if authors else None,
        "publisher": (record.get("publishers") or [None])[0],
        "published_date": publish_date or None,
        "publication_year": publication_year,
        "page_count": record.get("number_of_pages"),
        "categories": categories,
        "categories_str": categories_str,
        "average_rating": None,
        "ratings_count": None,
        "language": language,
        "cover_url": OPENLIB_COVER_TMPL.format(isbn=isbn),
        "description": record.get("description", {}).get("value") if isinstance(record.get("description"), dict) else record.get("description"),
        "isbn_10": isbn_10,
        "isbn_13": isbn_13,
        "series_name": series_name,
        "series_index": None,
        "source": "open_library",
    }


def _fetch_open_library_deep(isbn: str, sess: requests.Session) -> Optional[Dict[str, Any]]:
    try:
        response = sess.get(OPENLIB_ISBN_JSON.format(isbn=isbn), timeout=_REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        book_payload = response.json() or {}
    except ValueError:
        return None

    title = book_payload.get("title")
    publish_date = (book_payload.get("publish_date") or "").strip()
    year_match = re.search(r"(\d{4})", publish_date)
    publication_year = int(year_match.group(1)) if year_match else None
    page_count = book_payload.get("number_of_pages")

    publishers = book_payload.get("publishers") or []
    publisher = publishers[0] if publishers else None

    languages_payload = book_payload.get("languages") or []
    language = None
    if languages_payload and isinstance(languages_payload[0], dict):
        lang_key = languages_payload[0].get("key", "").split("/")[-1]
        language = {"eng": "en", "ger": "de", "deu": "de", "fre": "fr", "fra": "fr", "spa": "es"}.get(lang_key, lang_key or None)
    language = language or _isbn_language_hint(isbn)

    covers = book_payload.get("covers") or []
    cover_url = OPENLIB_COVER_TMPL.format(isbn=isbn)
    if covers:
        cover_url = OPENLIB_COVER_BY_ID.format(cover_id=covers[0])

    series_name = None
    series_index: Optional[int] = None
    categories: list[str] = []

    work_key = None
    works_payload = book_payload.get("works") or []
    if works_payload and isinstance(works_payload[0], dict):
        work_key = works_payload[0].get("key")
    if work_key:
        try:
            work_response = sess.get(OPENLIB_WORK_JSON.format(work_key=work_key), timeout=_REQUEST_TIMEOUT)
            if work_response.status_code == 200:
                work_data = work_response.json() or {}
                if work_data.get("title") and not title:
                    title = work_data["title"]
                subjects = work_data.get("subjects") or []
                categories = [s for s in subjects if isinstance(s, str)]
                categories = [c for c in categories if c]
                series = work_data.get("series") or []
                if series and isinstance(series[0], str):
                    series_name = series[0]
                    idx_match = re.search(r"#?(\d+)", series_name)
                    if idx_match:
                        try:
                            series_index = int(idx_match.group(1))
                        except ValueError:
                            series_index = None
        except requests.RequestException:
            pass
        except ValueError:
            pass

    identifiers = {
        "isbn_10": book_payload.get("isbn_10"),
        "isbn_13": book_payload.get("isbn_13"),
    }
    isbn_10 = identifiers.get("isbn_10")
    if isinstance(isbn_10, list) and isbn_10:
        isbn_10 = isbn_10[0]
    isbn_13 = identifiers.get("isbn_13")
    if isinstance(isbn_13, list) and isbn_13:
        isbn_13 = isbn_13[0]

    return {
        "title": title,
        "subtitle": None,
        "authors": None,
        "authors_str": None,
        "publisher": publisher,
        "published_date": publish_date or None,
        "publication_year": publication_year,
        "page_count": page_count,
        "categories": categories,
        "categories_str": ", ".join(categories) if categories else None,
        "average_rating": None,
        "ratings_count": None,
        "language": language,
        "cover_url": cover_url,
        "description": None,
        "isbn_10": isbn_10,
        "isbn_13": isbn_13,
        "series_name": series_name,
        "series_index": series_index,
        "source": "open_library_deep",
    }


# --- binding detection via Open Library + fallbacks ---
def _normalize_binding(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    t = s.lower()
    if "hard" in t or "cloth" in t or "library binding" in t:
        return "Hardcover"
    if "mass" in t or "mmpb" in t:
        return "Mass Market Paperback"
    if "paper" in t or "trade" in t or "pbk" in t or "soft" in t:
        return "Paperback"
    return None


def binding_from_openlibrary(isbn: str, session: Optional[requests.Session] = None) -> Optional[str]:
    sess = session or create_http_session()
    try:
        r = sess.get(OPENLIB_ISBN_JSON.format(isbn=isbn), timeout=_REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        js = r.json()
        bind = _normalize_binding(js.get("physical_format"))
        if bind:
            return bind
        notes_val = js.get("notes")
        desc_raw = js.get("description")
        if isinstance(desc_raw, dict):
            desc_val = desc_raw.get("value")
        else:
            desc_val = desc_raw
        hints = " ".join([str(notes_val or ""), str(desc_val or "")])
        m = re.search(
            r"(hardcover|hardback|library binding|mass market paperback|trade paperback|paperback|pbk)",
            str(hints),
            re.IGNORECASE,
        )
        return _normalize_binding(m.group(1)) if m else None
    except Exception:
        return None
    finally:
        if session is None:
            try:
                sess.close()
            except Exception:
                pass


def binding_from_googlebooks(volume_info: Dict[str, Any]) -> Optional[str]:
    for k in ("title", "subtitle", "description"):
        v = volume_info.get(k)
        if not v:
            continue
        m = re.search(
            r"(hardcover|hardback|library binding|mass market paperback|trade paperback|paperback|pbk)",
            str(v),
            re.IGNORECASE,
        )
        if m:
            return _normalize_binding(m.group(1))
    return None


def detect_binding(isbn: str, gbooks_volume_info: Optional[Dict[str, Any]] = None, session: Optional[requests.Session] = None) -> Optional[str]:
    b = binding_from_openlibrary(isbn, session=session)
    if b:
        return b
    if gbooks_volume_info:
        b = binding_from_googlebooks(gbooks_volume_info)
        if b:
            return b
    return None

# --------------------------- Unified metadata fetch ----------------------- #
def _cache_success(meta: Dict[str, Any], keys: Iterable[str]) -> None:
    for key in keys:
        cache_set(key, meta)


def _apply_isbn_fallbacks(meta: Dict[str, Any], candidates: Iterable[str]) -> None:
    has_10 = bool(_clean_isbn(meta.get("isbn_10") or "") and _is_isbn10(_clean_isbn(meta.get("isbn_10") or "")))
    has_13 = bool(_clean_isbn(meta.get("isbn_13") or "") and _is_isbn13(_clean_isbn(meta.get("isbn_13") or "")))
    for candidate in candidates:
        if not candidate:
            continue
        if not has_10 and _is_isbn10(candidate):
            meta["isbn_10"] = candidate
            has_10 = True
        if not has_13 and _is_isbn13(candidate):
            meta["isbn_13"] = candidate
            has_13 = True
        if has_10 and has_13:
            break


def _fetch_metadata_internal(isbn: str, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    cleaned = _clean_isbn(isbn)
    if not cleaned:
        return None

    alt = None
    if _is_isbn10(cleaned):
        alt = isbn10_to_isbn13(cleaned)
    elif _is_isbn13(cleaned):
        alt = isbn13_to_isbn10(cleaned)

    attempts = []
    for candidate in (cleaned, alt):
        if candidate and candidate not in attempts:
            attempts.append(candidate)

    cached_meta = None
    cached_isbn = None
    for candidate in attempts:
        cached_meta = cache_get(candidate)
        if cached_meta:
            cached_isbn = candidate
            break
    if cached_meta:
        result = dict(cached_meta)
        original_source = result.get("source")
        result["source"] = "cache"
        if original_source and original_source != "cache":
            result.setdefault("cached_from", original_source)
        _apply_isbn_fallbacks(result, attempts)
        result = _finalise_meta(result, cached_isbn or attempts[0], session=session)
        return result

    own_session: Optional[requests.Session] = None
    sess = session
    if sess is None:
        own_session = create_http_session()
        sess = own_session

    try:
        api_key = os.getenv("GOOGLE_BOOKS_API_KEY") or None
        try:
            for candidate in attempts:
                if not candidate:
                    continue
                info = _fetch_google_books_raw(candidate, api_key, sess)
                if info:
                    meta = _normalize_from_gbooks(info)
                    # Attempt to detect binding using Open Library (primary) and Google Books hints (fallback)
                    try:
                        b = detect_binding(candidate, gbooks_volume_info=info, session=session or sess)
                        if b:
                            meta["binding"] = b
                    except Exception:
                        pass
                    meta = _finalise_meta(meta, candidate, session=session or sess)
                    _apply_isbn_fallbacks(meta, attempts)
                    _cache_success(meta, attempts)
                    return meta
        except Exception:
            pass

        try:
            for candidate in attempts:
                if not candidate:
                    continue
                meta = _fetch_open_library(candidate, sess)
                if meta:
                    # Detect binding via Open Library/Google Books hints
                    try:
                        b = detect_binding(candidate, session=session or sess)
                        if b:
                            meta["binding"] = b
                    except Exception:
                        pass
                    meta = _finalise_meta(meta, candidate, session=session or sess)
                    _apply_isbn_fallbacks(meta, attempts)
                    _cache_success(meta, attempts)
                    return meta
        except Exception:
            pass

        try:
            for candidate in attempts:
                if not candidate:
                    continue
                meta = _fetch_open_library_deep(candidate, sess)
                if meta:
                    # Detect binding via Open Library/Google Books hints
                    try:
                        b = detect_binding(candidate, session=session or sess)
                        if b:
                            meta["binding"] = b
                    except Exception:
                        pass
                    meta = _finalise_meta(meta, candidate, session=session or sess)
                    _apply_isbn_fallbacks(meta, attempts)
                    _cache_success(meta, attempts)
                    return meta
        except Exception:
            pass
    finally:
        if own_session is not None:
            own_session.close()

    hint = _isbn_language_hint(attempts[0] if attempts else None)
    if hint:
        meta = {
            "title": None,
            "subtitle": None,
            "authors": None,
            "authors_str": None,
            "publisher": None,
            "published_date": None,
            "publication_year": None,
            "page_count": None,
            "categories": None,
            "categories_str": None,
            "average_rating": None,
            "ratings_count": None,
            "language": hint,
            "cover_url": OPENLIB_COVER_TMPL.format(isbn=attempts[0]),
            "description": None,
            "isbn_10": alt if alt and _is_isbn10(alt) else (attempts[0] if _is_isbn10(attempts[0]) else None),
            "isbn_13": attempts[0] if _is_isbn13(attempts[0]) else (alt if alt and _is_isbn13(alt) else None),
            "series_name": None,
            "series_index": None,
            "source": "isbn_hint",
        }
        meta = _finalise_meta(meta, attempts[0] if attempts else cleaned, session=session)
        _cache_success(meta, attempts)
        return meta

    return None


def fetch_google_books(isbn: str, api_key: Optional[str] = None, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    if api_key:
        os.environ.setdefault("GOOGLE_BOOKS_API_KEY", api_key)
    return fetch_metadata(isbn, session=session)


@overload
def fetch_metadata(isbn: str, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]: ...


@overload
def fetch_metadata(session: requests.Session, isbn: str, delay: float | None = None) -> Optional[Dict[str, Any]]: ...


def fetch_metadata(*args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
    if not args and "isbn" not in kwargs:
        raise TypeError("fetch_metadata() missing required argument: 'isbn'")

    if args and isinstance(args[0], requests.Session):
        session = args[0]
        if len(args) > 1:
            isbn_value = args[1]
        else:
            isbn_value = kwargs.get("isbn")
        if isbn_value is None:
            raise TypeError("fetch_metadata() missing ISBN when called with session")
        delay = kwargs.get("delay")
        result = _fetch_metadata_internal(str(isbn_value), session=session)
        if not result and delay:
            try:
                time.sleep(float(delay))
            except Exception:
                pass
            result = _fetch_metadata_internal(str(isbn_value), session=session)
        return result

    if args:
        isbn_value = args[0]
        session = args[1] if len(args) > 1 and isinstance(args[1], requests.Session) else kwargs.get("session")
    else:
        isbn_value = kwargs.get("isbn")
        session = kwargs.get("session")
    if isbn_value is None:
        raise TypeError("fetch_metadata() missing ISBN")
    return _fetch_metadata_internal(str(isbn_value), session=session)
