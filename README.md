# StreamCore - MacCMS V10 兼容视频聚合系统

[English](#english) | [中文](#中文)

---

## 中文

### 📖 概述

StreamCore 是一个轻量级视频聚合系统，采用**读写分离**架构，完全兼容 **MacCMS V10** API 规范。

### 核心特性

- 🎯 **MacCMS V10 兼容**: API 完全兼容 MacCMS 采集标准
- 🔄 **读写分离**: 采集写入临时库，API 读取主库
- 🗃️ **多源聚合**: 支持多个数据源采集，自动去重
- 🔗 **数据库级合并**: 采集时自动合并重复内容（零停机）
- 🗺️ **分类映射**: 自动将外部分类映射到本地分类
- 🔍 **全文搜索**: 支持按名称和演员快速搜索
- ⚡ **高性能**: SQLite + 索引实现快速查询

### 🏗️ 架构

```
┌─────────────┐
│   采集器    │ ──写入──> sc_temp.db (临时数据库)
└─────────────┘               │
                              │ 🆕 自动合并重复
                              │ 原子交换
                              ↓
┌─────────────┐           sc_main.db (主数据库)
│  API 服务器  │ ──读取──>    ↑
└─────────────┘               │
```

### 🚀 快速开始

#### 1. 安装依赖

```bash
cd streamCore
pip install -r requirements.txt
```

#### 2. 初始化项目

```bash
python3 setup.py init
```

#### 3. 添加数据源

```bash
python3 setup.py add-source

# 示例输入：
# 数据源名称: 示例源
# API URL: https://example.com/api.php/provide/vod/
# 格式: json
# ID 前缀: example_
```

#### 4. 映射分类

```bash
python3 setup.py map-type --source example_

# 示例映射：
# 1:1  (远程电影 → 本地电影)
# 2:2  (远程电视剧 → 本地电视剧)
```

#### 5. 采集数据

```bash
# 完整采集
python3 collector.py --mode full

# 增量采集（最近6小时）
python3 collector.py --mode incremental --hours 6

# 仅采集详情
python3 collector.py --mode details-only
```

#### 6. 启动 API 服务

```bash
python3 app.py

# 服务地址: http://localhost:5000
```

### 📚 API 使用

#### 列表接口

```bash
# 获取列表（带筛选）
GET /api.php/provide/vod/?ac=list&t=1&pg=1

# 最近24小时更新
GET /api.php/provide/vod/?ac=list&h=24

# 按地区筛选
GET /api.php/provide/vod/?ac=list&area=香港

# 按年份筛选
GET /api.php/provide/vod/?ac=list&year=2025
```

#### 详情接口

```bash
# 按 ID 查询
GET /api.php/provide/vod/?ac=detail&ids=1,2,3

# 按关键词搜索
GET /api.php/provide/vod/?ac=detail&wd=电影名称
```

#### 响应格式

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
      "vod_name": "电影名称",
      "vod_en": "dymn",
      "vod_year": "2025",
      "vod_pic": "https://example.com/poster.jpg",
      "vod_remarks": "HD",
      "vod_play_from": "线路1$$$线路2",
      "vod_play_url": "第1集$url#第2集$url$$$第1集$url",
      "vod_time": 1734156000
    }
  ]
}
```

**排序规则**: 先按 `vod_year` 降序，再按 `vod_time` 降序

### 🛠️ CLI 命令参考

| 命令 | 说明 |
|------|------|
| `python3 setup.py init` | 初始化数据库 |
| `python3 setup.py add-source` | 添加数据源 |
| `python3 setup.py map-type --source <前缀>` | 配置分类映射 |
| `python3 setup.py list` | 查看所有配置 |
| `python3 collector.py --mode full` | 完整采集 |
| `python3 collector.py --mode incremental --hours 6` | 增量采集 |
| `python3 app.py` | 启动 API 服务 |

### 📦 项目结构

```
/streamCore/
├── requirements.txt    # 依赖
├── db_config.py        # 数据库配置
├── setup.py            # 设置 CLI
├── collector.py        # 数据采集器
├── merge_dedupe.py     # 合并脚本
├── app.py              # Flask API
├── sc_main.db          # 主数据库
└── sc_temp.db          # 临时数据库
```

---

## English

### 📖 Overview

StreamCore is a lightweight video aggregation system with **read-write isolation** architecture, fully compatible with **MacCMS V10** API specifications.

### Core Features

- 🎯 **MacCMS V10 Compatible**: API fully compatible with MacCMS collection standards
- 🔄 **Read-Write Isolation**: Collection writes to temp DB, API reads from main DB
- 🗃️ **Multi-Source Aggregation**: Collect from multiple sources with automatic deduplication
- 🔗 **Database-Level Merge**: Automatic duplicate merging during collection (zero downtime)
- 🗺️ **Category Mapping**: Auto-map external categories to local taxonomy
- 🔍 **Full-Text Search**: Fast search by name and actors
- ⚡ **High Performance**: SQLite + indexes for fast queries

### 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize
python3 setup.py init

# Add source
python3 setup.py add-source

# Map categories
python3 setup.py map-type --source <prefix>

# Collect data
python3 collector.py --mode full

# Start API
python3 app.py
```

### 📚 API Usage

```bash
# List
GET /api.php/provide/vod/?ac=list&t=1&pg=1

# Detail
GET /api.php/provide/vod/?ac=detail&ids=1,2,3

# Search
GET /api.php/provide/vod/?ac=detail&wd=keyword
```

**Sort Order**: `vod_year DESC, vod_time DESC`

### 🔧 Tech Stack

- Python 3.7+
- Flask 3.0
- SQLite 3

### 📄 License

MIT License
