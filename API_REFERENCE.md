# StreamCore API Reference

## Overview

StreamCore provides a MacCMS V10 compatible JSON API for video content aggregation. The API follows RESTful principles and returns data in JSON format.

**Base URL**: `http://localhost:5000`

**Content Type**: `application/json; charset=utf-8`

---

## Authentication

Currently, no authentication is required. All endpoints are publicly accessible.

---

## Endpoints

### 1. Health Check

Check if the API service is running.

#### `GET /health`

**Response**:
```json
{
  "status": "ok",
  "service": "StreamCore API",
  "version": "1.0.0"
}
```

---

### 2. List Videos

Retrieve a paginated list of videos with optional filtering.

#### `GET /api.php/provide/vod/`

**Query Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ac` | string | Yes | - | Action type. Must be `list` |
| `t` | string | No | - | Category ID(s). Comma-separated for multiple. Supports L1/L2 hierarchy |
| `pg` | integer | No | 1 | Page number (minimum: 1) |
| `area` | string | No | - | Filter by region/area (e.g., `香港`, `美国`, `日本`) |
| `year` | string | No | - | Filter by year (e.g., `2025`, `2024`) |
| `h` | integer | No | - | Filter by hours since last update (e.g., `24` for last 24 hours) |

**Important Notes**:
- **Category Hierarchy**: If querying an L1 parent category, the response automatically includes all child (L2) videos
- **Pagination**: 20 items per page (fixed)
- **Ordering**: Results are sorted by `vod_year` (year) descending first, then by `vod_time` (update time) descending

**Example Requests**:
```
GET /api.php/provide/vod/?ac=list
GET /api.php/provide/vod/?ac=list&t=1
GET /api.php/provide/vod/?ac=list&t=1,2,3
GET /api.php/provide/vod/?ac=list&pg=2
GET /api.php/provide/vod/?ac=list&area=香港
GET /api.php/provide/vod/?ac=list&year=2025
GET /api.php/provide/vod/?ac=list&area=香港&year=2025
GET /api.php/provide/vod/?ac=list&h=24
GET /api.php/provide/vod/?ac=list&t=1&area=香港&year=2025&pg=1
GET /api.php/provide/vod/?ac=list&t=1&pg=2&h=24
```

**Response Schema**:
```json
{
  "code": 1,
  "msg": "数据列表",
  "page": 1,
  "pagecount": 10,
  "limit": 20,
  "total": 195,
  "list": [
    {
      "vod_id": 123,
      "vod_name": "复仇者联盟",
      "type_id": 1,
      "vod_pic": "https://example.com/poster.jpg",
      "vod_remarks": "HD",
      "vod_time": 1701936000
    }
  ]
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `code` | integer | Status code (1 = success, 0 = error) |
| `msg` | string | Response message |
| `page` | integer | Current page number |
| `pagecount` | integer | Total number of pages |
| `limit` | integer | Items per page |
| `total` | integer | Total number of items |
| `list` | array | Array of video objects |

**Video Object (List Mode)**:

| Field | Type | Description |
|-------|------|-------------|
| `vod_id` | integer | Internal video ID (auto-increment) |
| `vod_name` | string | Video title |
| `type_id` | integer | Category ID |
| `vod_pic` | string | Poster image URL |
| `vod_remarks` | string | Remarks (e.g., quality, episode info) |
| `vod_time` | integer | Unix timestamp of last update |

> [!WARNING]
> **Current Database Limitation**: The `vod_pic` field may be empty for some videos. The collector needs enhancement to fetch poster images from source APIs.

---

### 3. Video Details

Retrieve detailed information for specific videos, including play URLs.

#### `GET /api.php/provide/vod/`

**Query Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ac` | string | Yes | - | Action type. Must be `detail` |
| `ids` | string | No* | - | Video ID(s). Comma-separated for multiple |
| `wd` | string | No* | - | Search keyword |
| `h` | integer | No* | - | Filter by hours since last update |

*At least one of `ids`, `wd`, or `h` must be provided.

**Search Behavior**:
- **By IDs**: Direct lookup using `res_unique_id` (e.g., `wj_12345`)
- **By Keyword**: Full-text search in `sc_search` table (matches video names, actors, etc.)
- **By Time**: Returns videos updated within the specified hours

**Example Requests**:
```
GET /api.php/provide/vod/?ac=detail&ids=wj_12345
GET /api.php/provide/vod/?ac=detail&ids=wj_12345,wj_67890
GET /api.php/provide/vod/?ac=detail&wd=复仇者联盟
GET /api.php/provide/vod/?ac=detail&h=24
```

**Response Schema**:
```json
{
  "code": 1,
  "msg": "数据列表",
  "page": 1,
  "pagecount": 1,
  "limit": 2,
  "total": 2,
  "list": [
    {
      "vod_id": "wj_12345",
      "vod_name": "复仇者联盟",
      "type_id": 1,
      "vod_pic": "https://example.com/poster.jpg",
      "vod_remarks": "HD",
      "vod_time": 1701936000,
      "vod_play_url": "播放线路1$https://example.com/video1.m3u8#播放线路2$https://example.com/video2.m3u8",
      "vod_actor": "小罗伯特·唐尼,克里斯·埃文斯",
      "vod_blurb": "地球面临前所未有的威胁..."
    }
  ]
}
```

**Video Object (Detail Mode)**:

| Field | Type | Description |
|-------|------|-------------|
| `vod_id` | string | Unique resource ID (with prefix, e.g., `wj_12345`) |
| `vod_name` | string | Video title |
| `type_id` | integer | Category ID |
| `vod_pic` | string | Poster image URL |
| `vod_remarks` | string | Remarks (e.g., quality, episode info) |
| `vod_time` | integer | Unix timestamp of last update |
| `vod_play_url` | string | Play URLs (MacCMS V10 format) |
| `vod_actor` | string | Actor names (comma-separated) |
| `vod_blurb` | string | Video description/synopsis |

**Play URL Format** (MacCMS V10 Standard):
```
LineLabel1$Episode1URL#Episode2URL$$$LineLabel2$Episode1URL
```

Example:
```
高清线路$https://cdn1.example.com/ep01.m3u8#https://cdn1.example.com/ep02.m3u8$$$超清线路$https://cdn2.example.com/ep01.m3u8
```

> [!IMPORTANT]
> **Current Database Limitation**: 
> - `vod_play_url` may be empty for many videos
> - `vod_pic`, `vod_actor`, and `vod_blurb` may also be incomplete
> 
> The collector currently only fetches basic list data. To get full detail data, the collector needs to be updated to:
> 1. Make additional `ac=detail` API calls to source
> 2. Extract and store `vod_play_url`, `vod_play_from`, and other detail fields

---

## Error Responses

When an error occurs, the API returns:

```json
{
  "code": 0,
  "msg": "Error description"
}
```

**Common Error Scenarios**:

| HTTP Status | `code` | `msg` | Cause |
|-------------|--------|-------|-------|
| 500 | 0 | `数据库文件缺失，请先运行 python setup.py init 初始化项目` | Database not initialized |
| 400 | 0 | `不支持的操作: {action}` | Invalid `ac` parameter |
| 500 | 0 | `API 服务器错误: {error}` | Internal server error |

---

## Database Schema

### sc_vod Table (Video Core Data)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `vod_id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Internal video ID |
| `res_unique_id` | TEXT | UNIQUE, NOT NULL | Unique resource ID (with prefix) |
| `res_source_id` | INTEGER | NOT NULL | Source configuration ID |
| `vod_name` | TEXT | NOT NULL | Video title |
| `vod_type_id` | INTEGER | NOT NULL | Category ID |
| `vod_pic` | TEXT | NULLABLE | Poster image URL |
| `vod_remarks` | TEXT | NULLABLE | Remarks |
| `vod_blurb` | TEXT | NULLABLE | Synopsis/description |
| `vod_play_url` | TEXT | NULLABLE | Play URLs (MacCMS format) |
| `vod_actor` | TEXT | NULLABLE | Actor names |
| `vod_time` | INTEGER | NOT NULL | Last update timestamp |
| `vod_hits` | INTEGER | DEFAULT 0 | View count |

### sc_type Table (Categories)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `type_id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Category ID |
| `type_name` | TEXT | NOT NULL | Category name |
| `type_pid` | INTEGER | DEFAULT 0 | Parent category ID (0 = top level) |

### sc_search Table (Search Index)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `vod_id` | INTEGER | PRIMARY KEY | Video ID (references sc_vod) |
| `search_text` | TEXT | NOT NULL | Searchable text (names, actors, etc.) |

---

## Data Collection Status

### ✅ Currently Collected

- Video ID and unique resource ID
- Video name/title
- Category ID (with L1/L2 mapping)
- Remarks (quality, episode info)
- Last update timestamp

### ❌ Missing/Incomplete Data

The following fields are defined in the database but **not being populated** by the current collector:

1. **`vod_pic`** - Movie poster images
   - Database column exists
   - Collector doesn't fetch from source API
   
2. **`vod_play_url`** - Video play URLs
   - Database column exists
   - Requires `ac=detail` API calls to source
   - MacCMS V10 standard format needed
   
3. **`vod_play_from`** - Play line sources
   - Not even in database schema
   - Needs schema update + collector enhancement
   
4. **Full detail data**:
   - `vod_actor` - Actor names
   - `vod_blurb` - Video synopsis
   - Other MacCMS V10 standard fields

### 📋 Required Enhancements

To collect complete data, the following changes are needed:

1. **Update collector.py**:
   - Add `ac=detail` API calls after list collection
   - Extract `vod_pic`, `vod_play_url`, `vod_actor`, `vod_blurb` from detail responses
   - Update database with complete information

2. **Update API responses** (optional):
   - Consider adding `vod_play_from` field to detail responses
   - Add more MacCMS V10 compatible fields as needed

---

## MacCMS V10 Compatibility

This API follows MacCMS V10 standards:

✅ **Compatible Features**:
- Standard endpoint: `/api.php/provide/vod/`
- Action types: `ac=list`, `ac=detail`
- Standard query parameters: `t`, `pg`, `ids`, `wd`, `h`, `area`, `year`
- JSON response format with `code`, `msg`, `page`, `pagecount`, `limit`, `total`, `list`
- Category filtering (with L1/L2 hierarchy extension)
- Region/area filtering (`area` parameter)
- Year filtering (`year` parameter)
- Time-based filtering

⚠️ **Partial Compatibility**:
- `vod_play_url` format matches MacCMS but data is incomplete
- Detail responses missing some optional fields

❌ **Not Implemented**:
- XML format (`data_format=xml`)
- Class list in responses (`class` field)
- Some advanced MacCMS fields

---

## Usage Examples

### Python

```python
import requests

BASE_URL = "http://localhost:5000"

# Get all movies (category 1)
response = requests.get(f"{BASE_URL}/api.php/provide/vod/?ac=list&t=1")
data = response.json()
print(f"Found {data['total']} movies")

# Search for a video
response = requests.get(f"{BASE_URL}/api.php/provide/vod/?ac=detail&wd=复仇者联盟")
videos = response.json()['list']
for video in videos:
    print(f"{video['vod_name']} - {video['vod_remarks']}")

# Get videos updated in last 24 hours
response = requests.get(f"{BASE_URL}/api.php/provide/vod/?ac=detail&h=24")
recent = response.json()['list']
```

### cURL

```bash
# List all videos
curl "http://localhost:5000/api.php/provide/vod/?ac=list"

# Filter by category
curl "http://localhost:5000/api.php/provide/vod/?ac=list&t=1&pg=1"

# Get video details by ID
curl "http://localhost:5000/api.php/provide/vod/?ac=detail&ids=wj_12345,wj_67890"

# Search by keyword
curl "http://localhost:5000/api.php/provide/vod/?ac=detail&wd=复仇者联盟"

# Get recent updates
curl "http://localhost:5000/api.php/provide/vod/?ac=detail&h=24"
```

### JavaScript (fetch)

```javascript
// List videos with pagination
const response = await fetch('http://localhost:5000/api.php/provide/vod/?ac=list&pg=1');
const data = await response.json();
console.log(`Page ${data.page} of ${data.pagecount}`);

// Search
const searchResponse = await fetch('http://localhost:5000/api.php/provide/vod/?ac=detail&wd=复仇者联盟');
const searchData = await searchResponse.json();
searchData.list.forEach(video => {
  console.log(video.vod_name);
});
```

---

## Rate Limiting

Currently, there is **no rate limiting** implemented. For production use, consider implementing:
- Request rate limits per IP
- API key authentication
- CORS policies

---

## Changelog

### Version 1.0.0 (Current)
- ✅ Basic list and detail endpoints
- ✅ Category filtering with L1/L2 hierarchy
- ✅ Pagination support
- ✅ Keyword search
- ✅ Time-based filtering
- ✅ Chinese character support (UTF-8)
- ⚠️ Incomplete data collection (missing posters, play URLs)

---

## Support

For issues or questions:
1. Check the database with: `python setup.py list`
2. Test API with: `python test_api.py`
3. Review collector logs when running: `python collector.py`

---

## License

StreamCore API - Internal Use
