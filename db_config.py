# db_config.py
# StreamCore 数据库配置模块
# 兼容 MacCMS V10 的表结构设计

import sqlite3
import os

# 数据库文件名定义
MAIN_DB = 'sc_main.db'
TEMP_DB = 'sc_temp.db'

# 核心 SQL Schema (MacCMS V10 兼容，使用 SC_ 前缀)
INIT_SCHEMA = """
-- 1. sc_type 表 (本地分类结构)
CREATE TABLE IF NOT EXISTS sc_type (
    type_id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_name TEXT NOT NULL,
    type_pid INTEGER DEFAULT 0
);

-- 2. sc_config 表 (采集配置与映射)
CREATE TABLE IF NOT EXISTS sc_config (
    res_source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    res_name TEXT NOT NULL,
    res_url TEXT NOT NULL,
    data_format TEXT NOT NULL,
    res_id_prefix TEXT UNIQUE NOT NULL,
    res_mapping TEXT,
    operation_mode TEXT DEFAULT 'add_update'
);

-- 3. sc_vod 表 (影片核心数据 - MacCMS 兼容字段)
CREATE TABLE IF NOT EXISTS sc_vod (
    vod_id INTEGER PRIMARY KEY AUTOINCREMENT,
    res_unique_id TEXT UNIQUE NOT NULL,
    res_source_id INTEGER NOT NULL,
    vod_name TEXT NOT NULL,
    vod_en TEXT,
    vod_type_id INTEGER NOT NULL,
    vod_pic TEXT,
    vod_remarks TEXT,
    vod_blurb TEXT,
    vod_play_url TEXT,
    vod_play_from TEXT,
    vod_actor TEXT,
    vod_director TEXT,
    vod_year TEXT,
    vod_area TEXT,
    vod_lang TEXT,
    vod_class TEXT,
    vod_time INTEGER NOT NULL,
    vod_time_hits INTEGER DEFAULT 0,
    vod_hits INTEGER DEFAULT 0
);

-- 4. sc_search 表 (搜索优化)
CREATE TABLE IF NOT EXISTS sc_search (
    vod_id INTEGER PRIMARY KEY,
    search_text TEXT NOT NULL
);

-- 5. sc_merge_log 表 (合并记录追踪)
CREATE TABLE IF NOT EXISTS sc_merge_log (
    merge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_vod_id INTEGER NOT NULL,
    merged_vod_ids TEXT NOT NULL,
    source_prefixes TEXT NOT NULL,
    merge_timestamp INTEGER NOT NULL,
    merge_key TEXT NOT NULL
);

-- 性能优化索引
CREATE INDEX IF NOT EXISTS idx_vod_type ON sc_vod(vod_type_id);
CREATE INDEX IF NOT EXISTS idx_vod_time ON sc_vod(vod_time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_res_unique ON sc_vod(res_unique_id);
CREATE INDEX IF NOT EXISTS idx_search_text ON sc_search(search_text);
CREATE INDEX IF NOT EXISTS idx_merge_primary ON sc_merge_log(primary_vod_id);
CREATE INDEX IF NOT EXISTS idx_merge_key ON sc_merge_log(merge_key);
"""

def get_db_connection(db_name=MAIN_DB):
    """
    获取数据库连接，默认连接主数据库
    
    Args:
        db_name: 数据库文件名，默认 sc_main.db
        
    Returns:
        sqlite3.Connection: 数据库连接对象
    """
    if not os.path.exists(db_name):
        print(f"⚠️  警告：数据库文件 {db_name} 不存在。")
    
    conn = sqlite3.connect(db_name, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 支持字段名访问
    return conn

def init_db(db_name):
    """
    初始化数据库文件，创建所有表和索引
    
    Args:
        db_name: 要初始化的数据库文件名
    """
    conn = None
    try:
        conn = sqlite3.connect(db_name)
        conn.executescript(INIT_SCHEMA)
        conn.commit()
        print(f"✅ 数据库 {db_name} 初始化成功，Schema 已创建。")
    except Exception as e:
        print(f"❌ 初始化数据库 {db_name} 失败: {e}")
    finally:
        if conn:
            conn.close()

def create_initial_types(conn):
    """
    创建初始分类数据（电影、电视剧、动漫）
    
    Args:
        conn: 数据库连接对象
    """
    types_data = [
        (1, '电影', 0),
        (2, '电视剧', 0),
        (3, '动漫', 0),
        (4, '综艺', 0),
        (5, '纪录片', 0)
    ]
    
    cursor = conn.cursor()
    try:
        cursor.executemany(
            "INSERT OR IGNORE INTO sc_type (type_id, type_name, type_pid) VALUES (?, ?, ?)", 
            types_data
        )
        conn.commit()
        print("✅ 初始分类创建成功。")
    except Exception as e:
        print(f"❌ 创建初始分类失败: {e}")

def get_all_types(conn):
    """
    获取所有分类列表
    
    Args:
        conn: 数据库连接对象
        
    Returns:
        list: 分类列表
    """
    cursor = conn.cursor()
    cursor.execute("SELECT type_id, type_name, type_pid FROM sc_type ORDER BY type_id")
    return cursor.fetchall()

def get_all_sources(conn):
    """
    获取所有资源站配置
    
    Args:
        conn: 数据库连接对象
        
    Returns:
        list: 资源站配置列表
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT res_source_id, res_name, res_url, data_format, res_id_prefix, res_mapping, operation_mode
        FROM sc_config
    """)
    return cursor.fetchall()
