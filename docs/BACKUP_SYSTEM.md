# Database Backup System

**Status:** Production-ready automated backup system
**Last Updated:** November 2, 2025

## Overview

The ISBN Lot Optimizer now has a comprehensive automated backup system with:

1. **Integrated scraper backups** - Automatic backups during BookFinder data collection
2. **Scheduled periodic backups** - Hourly/daily automated backups via launchd/cron
3. **Manual backup tools** - On-demand backup capability
4. **Retention policy** - Automatic cleanup of old backups (30 days all, 6 months weekly, 1 year monthly)

## Backup Locations

**All backups stored in:** `~/.isbn_lot_optimizer/backups/`

**Databases backed up:**
- `catalog.db` (39 MB) - Main book catalog with BookFinder offers
- `metadata_cache.db` (42 MB) - ML training ISBN metadata
- `books.db` (18 MB) - Book metadata and attributes
- `training_data.db` (896 KB) - ML training samples
- `unified_index.db` (152 KB) - Unified ISBN index
- `unsigned_pairs.db` (72 KB) - Signed/unsigned ISBN pairs

**Total backup size:** ~100 MB per backup session

---

## Automatic Backups During Scraping

The BookFinder scraper (`scripts/collect_bookfinder_prices.py`) now automatically creates backups:

### Backup Schedule
- **Pre-scrape:** Before starting to collect data
- **Periodic:** Every 100 ISBNs processed (~25 minutes during scraping)
- **Post-scrape:** After scraping session completes

### Example Output
```
Creating pre-scrape backup...
✓ Backup created: catalog_pre-scrape_20251102_001234.db
  Size: 39.1 MB

[... scraping 100 ISBNs ...]

💾 Database backed up (100 ISBNs processed)

[... scraping continues ...]

💾 Final database backup completed
```

### Benefits
- **No data loss** during long-running scrapes (80+ hours for full catalog)
- **Resume capability** - Can restore to any 100-ISBN checkpoint
- **Automatic** - No manual intervention required

---

## Scheduled Periodic Backups

For automated backups independent of scraping activity.

### Quick Setup (macOS with launchd)

```bash
# Copy plist files to LaunchAgents
cp scripts/com.isbn.hourly-backup.plist ~/Library/LaunchAgents/
cp scripts/com.isbn.daily-backup.plist ~/Library/LaunchAgents/

# Load hourly backup (runs every hour, only if data changed in last 2 hours)
launchctl load ~/Library/LaunchAgents/com.isbn.hourly-backup.plist

# Load daily backup (runs at 3 AM every day)
launchctl load ~/Library/LaunchAgents/com.isbn.daily-backup.plist

# Verify loaded
launchctl list | grep isbn
```

### Unload/Stop Backups

```bash
# Stop hourly backups
launchctl unload ~/Library/LaunchAgents/com.isbn.hourly-backup.plist

# Stop daily backups
launchctl unload ~/Library/LaunchAgents/com.isbn.daily-backup.plist
```

### Check Backup Logs

```bash
# Hourly backup log
tail -f /tmp/isbn-hourly-backup.log

# Daily backup log
tail -f /tmp/isbn-daily-backup.log

# Error logs
tail -f /tmp/isbn-hourly-backup.error.log
tail -f /tmp/isbn-daily-backup.error.log
```

---

## Manual Backups

### Single Database Backup

```bash
# Backup specific database
python scripts/backup_database.py ~/.isbn_lot_optimizer/catalog.db --reason "before-experiment"
```

### All Databases Backup

```bash
# Backup all databases
python scripts/scheduled_backup.py --reason manual

# Backup only recently changed databases (last 6 hours)
python scripts/scheduled_backup.py --reason manual --if-changed 6

# Quiet mode (for cron)
python scripts/scheduled_backup.py --reason manual --quiet
```

---

## Backup Retention Policy

Automatic cleanup managed by `backup_database.py`:

| Age | Retention |
|-----|-----------|
| 0-30 days | All backups kept |
| 31-180 days | Weekly backups kept (newest per week) |
| 181-365 days | Monthly backups kept (newest per month) |
| > 365 days | Deleted |

**Example:**
- Today: 10 backups from various times
- Day 31: Oldest backup deleted, weekly snapshot kept
- Day 181: Weekly snapshots deleted, monthly snapshot kept
- Day 366: Deleted

This provides good coverage while managing disk space (~300 GB max for 1 year).

---

## Backup Naming Convention

Format: `{database}_{reason}_{timestamp}.db`

Examples:
- `catalog_pre-scrape_20251102_120000.db`
- `catalog_periodic-100_20251102_130000.db`
- `catalog_post-scrape_20251102_200000.db`
- `catalog_hourly_20251102_030000.db`
- `catalog_daily_20251102_030000.db`
- `catalog_manual_20251102_150000.db`

---

## Restore from Backup

### Restore Specific Database

```bash
# Stop scraper if running
# pkill -f collect_bookfinder_prices.py

# Restore from backup
cp ~/.isbn_lot_optimizer/backups/catalog_periodic-200_20251102_120000.db \
   ~/.isbn_lot_optimizer/catalog.db

# Verify restoration
python scripts/restore_database.py ~/.isbn_lot_optimizer/catalog.db --verify
```

### Find Specific Backup

```bash
# List all backups for catalog.db
ls -lth ~/.isbn_lot_optimizer/backups/catalog_*.db | head -20

# Find backups from specific date
ls -lth ~/.isbn_lot_optimizer/backups/catalog_*20251102*.db

# Find pre-scrape backups
ls -lth ~/.isbn_lot_optimizer/backups/catalog_pre-scrape*.db
```

---

## Monitoring & Maintenance

### Check Backup Space Usage

```bash
# Total backup directory size
du -sh ~/.isbn_lot_optimizer/backups/

# Size by database
du -sh ~/.isbn_lot_optimizer/backups/catalog_*.db | sort -h
du -sh ~/.isbn_lot_optimizer/backups/metadata_cache_*.db | sort -h
```

### Verify Backup Integrity

```bash
# Check if backup is valid SQLite database
sqlite3 ~/.isbn_lot_optimizer/backups/catalog_test_20251102_002558.db "PRAGMA integrity_check;"

# Should output: ok
```

### Manual Cleanup

```bash
# Delete all test backups
rm ~/.isbn_lot_optimizer/backups/*_test_*.db

# Delete backups older than 90 days
find ~/.isbn_lot_optimizer/backups -name "*.db" -mtime +90 -delete
```

---

## Troubleshooting

### Backup Failed During Scraping

**Symptom:** `Backup failed (non-fatal): ...` in scraper output

**Impact:** Scraping continues, but no backup created

**Solution:**
1. Check disk space: `df -h`
2. Check permissions: `ls -la ~/.isbn_lot_optimizer/backups/`
3. Manually backup: `python scripts/backup_database.py ~/.isbn_lot_optimizer/catalog.db --reason manual`

### Scheduled Backups Not Running

**Symptom:** No new backups appearing in backups directory

**Check:**
```bash
# Verify launchd jobs loaded
launchctl list | grep isbn

# Check logs for errors
tail -50 /tmp/isbn-hourly-backup.error.log
tail -50 /tmp/isbn-daily-backup.error.log

# Manually test script
python scripts/scheduled_backup.py --reason test
```

**Common Issues:**
1. **Python path wrong in plist** - Update to correct python3 path
2. **Permissions** - Ensure script is executable (`chmod +x scripts/scheduled_backup.py`)
3. **Working directory** - Ensure plist has correct working directory

### Backup Size Growing Too Fast

**Symptom:** `~/.isbn_lot_optimizer/backups/` > 500 GB

**Analysis:**
```bash
# Count backups per database
ls ~/.isbn_lot_optimizer/backups/ | awk -F'_' '{print $1}' | sort | uniq -c

# Check oldest backup
ls -lt ~/.isbn_lot_optimizer/backups/ | tail -5
```

**Solutions:**
1. **Verify retention policy running:** Check `backup_database.py` is cleaning old backups
2. **Manual cleanup:** Delete old test/periodic backups if retention policy failed
3. **Adjust periodic backup frequency:** Change hourly → every 4 hours in plist

---

## Best Practices

### During Active Development/Scraping
✅ Enable hourly backups
✅ Keep scraper auto-backups enabled
✅ Monitor `/tmp/isbn-*.log` files

### During Stable Operation
✅ Daily backups at 3 AM sufficient
✅ Disable hourly backups to reduce storage
✅ Manual backup before risky operations

### Before Risky Operations
✅ Manual backup with descriptive reason: `python scripts/backup_database.py ... --reason "before-schema-migration"`
✅ Verify backup created successfully
✅ Test restoration procedure

---

## Storage Estimates

| Backup Strategy | Daily Size | Monthly Size | Yearly Size |
|----------------|-----------|--------------|-------------|
| **Scraper only** (every 100 ISBNs) | ~5 GB | ~150 GB | Cleaned by retention |
| **Daily backups** | 100 MB | 3 GB | 36 GB |
| **Hourly backups** (changed only) | 2.4 GB | 72 GB | 100 GB (retention) |
| **Daily + hourly** | 2.5 GB | 75 GB | 136 GB (retention) |

**Recommendation:**
- **During scraping:** Daily + hourly (136 GB/year)
- **Stable operation:** Daily only (36 GB/year)

---

## Quick Reference

```bash
# Setup automated backups
cp scripts/*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.isbn.hourly-backup.plist
launchctl load ~/Library/LaunchAgents/com.isbn.daily-backup.plist

# Manual backup all databases
python scripts/scheduled_backup.py --reason manual

# Manual backup single database
python scripts/backup_database.py ~/.isbn_lot_optimizer/catalog.db --reason pre-experiment

# Check backup logs
tail -f /tmp/isbn-hourly-backup.log
tail -f /tmp/isbn-daily-backup.log

# List recent backups
ls -lth ~/.isbn_lot_optimizer/backups/ | head -20

# Restore backup
cp ~/.isbn_lot_optimizer/backups/catalog_*.db ~/.isbn_lot_optimizer/catalog.db

# Check backup space
du -sh ~/.isbn_lot_optimizer/backups/

# Stop automated backups
launchctl unload ~/Library/LaunchAgents/com.isbn.*.plist
```

---

**Status:** ✅ Backup system fully operational
**Coverage:** 6 databases, ~100 MB total
**Retention:** 30 days all, 6 months weekly, 1 year monthly
**Automation:** Scraper-integrated + scheduled hourly/daily
