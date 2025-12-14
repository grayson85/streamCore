# Collection Modes Guide

## Overview

StreamCore supports three collection modes to control data collection behavior.

## Collection Modes

### 1. Full Mode (Default)

**Usage:**
```bash
python3 collector.py --mode full
```

**Behavior:**
- Collects all data from sources
- User chooses number of pages to collect
- Merges duplicates automatically
- Swaps to main database when complete

**When to use:**
- Initial collection
- Periodic full refresh
- Want all available data

---

### 2. Incremental Mode

**Usage:**
```bash
python3 collector.py --mode incremental --hours 6
```

**Behavior:**
- Only collects data updated in last N hours
- Faster than full mode
- Merges duplicates automatically
- Swaps to main database when complete

**When to use:**
- Scheduled updates (cron jobs)
- Want only recent changes
- Running frequently (e.g., every 6 hours)

**Example cron:**
```bash
# Every 6 hours
0 */6 * * * cd /path/to/streamCore && python3 collector.py --mode incremental --hours 6
```

---

### 3. Details-Only Mode

**Usage:**
```bash
python3 collector.py --mode details-only
```

**Behavior:**
- Skips list collection
- Only fetches detailed data (play URLs, posters, etc.)
- For records missing details
- Merges duplicates automatically
- Swaps to main database when complete

**When to use:**
- After initial collection
- Want to update play URLs only
- Conserve bandwidth

---

## Data Operation Modes

Each source can have a different **operation mode** controlling how data is processed:

### add_update (Default, Recommended)

**Behavior:** Adds new + updates existing data

**SQL:** `INSERT OR REPLACE`

**When to use:**
- Main sources
- Want latest data always

---

### add (Add Only)

**Behavior:** Only adds new, ignores existing

**SQL:** `INSERT OR IGNORE`

**When to use:**
- Backup sources (avoid overwriting main source data)
- Supplementary content

---

### update (Update Only)

**Behavior:** Only updates existing, skips new

**SQL:** `UPDATE` (with existence check)

**When to use:**
- Update play URLs only
- Don't want new content
- Control database growth

---

## Configuration

### Set Operation Mode

When adding a source:

```bash
python3 setup.py add-source

# You'll be prompted:
⚙️ Operation mode (add_update/add/update) [default: add_update]: add_update
```

### View Current Mode

```bash
python3 setup.py list

# Output shows:
📡 Source: Example
   Operation mode: add_update
```

---

## Multi-Source Strategy

### Primary + Backup Sources

```
Source A (primary): operation_mode = add_update
Source B (backup):  operation_mode = add
```

→ A provides main content and updates, B supplements missing content

### Public + Specialized Sources

```
Source A (public):      operation_mode = add_update
Source B (specialized): operation_mode = update
```

→ A adds all content, B only updates play URLs for existing content

---

## Auto-Merge Feature

**All collection modes automatically merge duplicates before swapping databases!**

**Process:**
1. Collect data → `sc_temp.db`
2. Fetch details → `sc_temp.db`
3. **🆕 Merge duplicates** → `sc_temp.db`
4. Atomic swap → `sc_main.db`

**Example:**
```
Before merge in sc_temp.db:
  - vod_id=1: Movie A from "wj"
  - vod_id=2: Movie A from "mt"

After merge in sc_temp.db:
  - vod_id=1: Movie A
    vod_play_from: "wj$$$mt"
    vod_play_url: "wj_data$$$mt_data"
  - (vod_id=2 deleted)

Swap to sc_main.db:
  - Users see merged data immediately
  - Zero downtime (<10ms swap)
```

---

## CLI Summary

```bash
# Full collection (default)
python3 collector.py --mode full

# Incremental (last 6 hours)
python3 collector.py --mode incremental --hours 6

# Details only
python3 collector.py --mode details-only
```

**All modes:**
- ✅ Auto-merge duplicates
- ✅ Atomic database swap
- ✅ Zero downtime
- ✅ Backup before swap

---

## Best Practices

1. **Initial setup:** Use `--mode full`
2. **Regular updates:** Use `--mode incremental --hours 6` (cron every 6 hours)
3. **Details refresh:** Use `--mode details-only` when needed
4. **Multi-source:** Configure operation modes appropriately
5. **Monitoring:** Check merge statistics after collection

---

## FAQ

**Q: Which mode should I use for daily updates?**  
A: `--mode incremental --hours 24` for daily updates

**Q: How do I avoid overwriting data from source A with source B?**  
A: Set source A to `add_update`, source B to `add`

**Q: Can I run collection while API is serving requests?**  
A: Yes! Collector writes to `sc_temp.db`, API reads from `sc_main.db`

**Q: How long does the database swap take?**  
A: ~10ms (atomic file operation)

**Q: Are duplicates automatically merged?**  
A: Yes! All modes auto-merge before swapping databases
