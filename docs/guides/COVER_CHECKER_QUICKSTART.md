# Cover Checker Quick Start

## 🎯 What It Does
Automatically finds and fixes missing book cover images in your database.

## ⚡ Quick Commands

### Check what's missing:
```bash
python scripts/check_missing_covers.py --check-only
```

### Fix missing covers:
```bash
python scripts/check_missing_covers.py --fix
```

### Force recheck everything:
```bash
python scripts/check_missing_covers.py --fix --force-redownload
```

## 📊 API Endpoints

### Get stats:
```bash
curl http://localhost:8000/api/covers/stats
```

### Fix all missing:
```bash
curl -X POST http://localhost:8000/api/covers/fix \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Fix specific books:
```bash
curl -X POST http://localhost:8000/api/covers/fix \
  -H "Content-Type: application/json" \
  -d '{
    "isbns": ["9780670855032", "9780441172719"]
  }'
```

## 📝 Example Output

```
Checking 250 books for cover images...
------------------------------------------------------------
Progress: 50/250 (42 valid, 8 missing, 0 broken)
  ✅ Fixed: Ship of Magic
  ✅ Fixed: Dune
Progress: 100/250 (88 valid, 10 missing, 2 broken)
  ❌ No cover found: Unknown Book

============================================================
SUMMARY
============================================================
Total books:      250
Valid covers:     230 (92.0%)
Missing covers:   15 (6.0%)
Broken covers:    5 (2.0%)

Fixed:            18
Failed to fix:    2
```

## 🔄 Schedule Regular Checks

Add to crontab (runs weekly):
```bash
0 3 * * 0 cd /path/to/ISBN && python scripts/check_missing_covers.py --fix
```

## 🎓 How It Works

1. **Scans** all books in database
2. **Checks** if cover URLs exist and work
3. **Downloads** from Open Library if missing
4. **Updates** database with working URLs
5. **Rate limits** to be respectful (2 req/sec)

## 📚 Cover Sources

- Open Library (large): `https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg`
- Open Library (medium): `https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg`
- More sources can be added easily

## ✅ Benefits

- Professional catalog appearance
- Better user experience in iOS app
- Automatic fixes, no manual work
- Validates images (no 404s or placeholders)
- Background processing for large batches

## 📖 Full Documentation

See [COVER_CHECKER_GUIDE.md](COVER_CHECKER_GUIDE.md) for complete details.

## 🎉 That's It!

Your book catalog will now have complete cover images! 📚✨
