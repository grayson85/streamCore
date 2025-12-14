# StreamCore - MacCMS V10 Compatible Video Aggregation System

## 📖 Overview

StreamCore is a lightweight video aggregation system with **read-write isolation** architecture, fully compatible with **MacCMS V10** API specifications.

### Core Features

- 🎯 **MacCMS V10 Compatible**: API fully compatible with MacCMS collection standards
- 🔄 **Read-Write Isolation**: Collection writes to temp DB, API reads from main DB
- 🗃️ **Multi-Source Aggregation**: Collect from multiple sources with automatic deduplication
- 🔗 **Database-Level Merge**: Automatic duplicate merging during collection (zero downtime)
- 🗺️ **Category Mapping**: Auto-map external categories to local taxonomy
- 🔍 **Full-Text Search**: Fast search by name and actors
- ⚡ **High Performance**: SQLite + indexes for fast queries

## 🏗️ Architecture

```
┌─────────────┐
│  Collector  │ ──writes──> sc_temp.db (temp database)
└─────────────┘               │
                              │ 🆕 Auto-merge duplicates
                              │ Atomic swap
                              ↓
┌─────────────┐           sc_main.db (main database)
│  API Server │ ──reads──>    ↑
└─────────────┘               │
```

### Database Tables

- **sc_type** - Local category structure
- **sc_config** - Source configs and category mapping
- **sc_vod** - Video data (with merged multi-source content)
- **sc_search** - Search optimization
- **sc_merge_log** - Merge tracking (which sources are merged)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd streamCore
pip install -r requirements.txt
```

### 2. Initialize Project

```bash
python3 setup.py init
```

### 3. Add Sources

```bash
python3 setup.py add-source

# Example input:
# Source name: Example Source
# API URL: https://example.com/api.php/provide/vod/
# Format: json
# ID prefix: example_
```

### 4. Map Categories

```bash
python3 setup.py map-type --source example_

# Example mapping:
# 1:1  (remote movie → local movie)
# 2:2  (remote TV → local TV)
```

### 5. Collect Data

```bash
# Full collection
python3 collector.py --mode full

# Incremental (last 6 hours)
python3 collector.py --mode incremental --hours 6

# Details only (skip list collection)
python3 collector.py --mode details-only
```

**Note:** Auto-merge happens automatically after collection!

### 6. Start API Server

```bash
python3 app.py

# Server: http://localhost:5000
```

## 📚 API Usage

### List Endpoint

```bash
# Get list with filters
GET /api.php/provide/vod/?ac=list&t=1&pg=1

# Last 24 hours
GET /api.php/provide/vod/?ac=list&h=24
```

### Detail Endpoint

```bash
# Query by ID
GET /api.php/provide/vod/?ac=detail&ids=1,2,3

# Search by keyword
GET /api.php/provide/vod/?ac=detail&wd=movie+name
```

### Response Format

```json
{
  "code": 1,
  "msg": "数据列表",
  "page": 1,
  "pagecount": 10,
  "total": 200,
  "list": [
    {
      "vod_id": 1,
      "vod_name": "Movie Name",
      "vod_en": "mn",
      "vod_year": "2025",
      "vod_pic": "https://example.com/poster.jpg",
      "vod_remarks": "HD",
      "vod_play_from": "source1$$$source2",
      "vod_play_url": "ep1$url#ep2$url$$$ep1$url#ep2$url",
      "vod_time": 1734156000
    }
  ]
}
```

## 🛠️ CLI Reference

| Command | Description |
|---------|-------------|
| `python3 setup.py init` | Initialize database |
| `python3 setup.py add-source` | Add source |
| `python3 setup.py map-type --source <prefix>` | Configure category mapping |
| `python3 setup.py list` | View all configs |
| `python3 collector.py --mode full` | Full collection |
| `python3 collector.py --mode incremental --hours 6` | Incremental collection |
| `python3 collector.py --mode details-only` | Details only |
| `python3 app.py` | Start API server |

## 📦 Project Structure

```
/StreamCore/
├── requirements.txt    # Dependencies
├── db_config.py        # Database schema
├── setup.py            # Setup CLI
├── collector.py        # Data collector (with auto-merge)
├── merge_dedupe.py     # Merge script
├── app.py              # Flask API
├── sc_main.db          # Main DB (API reads from)
└── sc_temp.db          # Temp DB (collector writes to)
```

## ⚙️ Advanced Features

### Auto-Merge on Collection

**What it does:**
- Finds duplicate records (same name + year)
- Merges play sources using MacCMS 10 format
- Tracks source relationships in `sc_merge_log`

**Example:**
```
Before merge:
  - vod_id=1: 功夫 (2004) from source "wj"
  - vod_id=2: 功夫 (2004) from source "mt"

After merge:
  - vod_id=1: 功夫 (2004)
    vod_play_from: "wj$$$mt"
    vod_play_url: "wj_episodes$$$mt_episodes"
```

### Scheduled Collection

```bash
# Cron: Daily at 2 AM
0 2 * * * cd /path/to/streamCore && python3 collector.py --mode incremental --hours 24
```

### Production Deployment

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## 🔧 Tech Stack

- **Python 3.7+**
- **Flask 3.0** - Web framework
- **SQLite 3** - Database
- **Requests 2.31** - HTTP client

## 📝 Key Features

1. **MacCMS Compatibility**: Fully compatible with MacCMS V10 standards
2. **Smart Deduplication**: Database-level merge for fast queries (no runtime overhead)
3. **Category Mapping**: External category IDs mapped to local taxonomy
4. **Read-Write Isolation**: Collection doesn't impact API response time
5. **Atomic Swap**: Database file replacement is atomic (~10ms downtime)
6. **Source Tracking**: Know which sources are merged together

## 🤝 vs MacCMS

### Kept Features
- ✅ Resource collection
- ✅ Data storage
- ✅ API endpoints
- ✅ Category mapping
- ✅ Search functionality
- ✅ Multi-source merge

### Simplified Features
- ❌ User system
- ❌ Comments
- ❌ Complex actor relationships
- ❌ Frontend UI
- ❌ Player integration

StreamCore focuses on **resource aggregation** and **API provision**, allowing you to quickly build your own video resource platform.

## 📄 License

MIT License

## 🙋 Support

For questions, check project documentation or submit an issue.
