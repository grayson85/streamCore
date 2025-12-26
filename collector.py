# collector.py
# StreamCore 数据采集模块
# 支持 MacCMS V10 标准 JSON API 格式

import time
import shutil
import os
import json
import sqlite3
import requests
import fcntl
from datetime import datetime
from db_config import get_db_connection, TEMP_DB, MAIN_DB, get_all_sources, init_db

# Lock file to prevent concurrent collector instances
LOCK_FILE = 'collector.lock'

def acquire_lock():
    """
    Acquire an exclusive lock to prevent concurrent collector runs.
    
    Returns:
        file object if lock acquired, None if another instance is running
    """
    try:
        lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Write PID and start time for debugging
        lock_fd.write(f"PID: {os.getpid()}\n")
        lock_fd.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        lock_fd.flush()
        return lock_fd
    except (IOError, OSError):
        return None

def release_lock(lock_fd):
    """
    Release the lock and clean up lock file.
    
    Args:
        lock_fd: file object returned by acquire_lock()
    """
    if lock_fd:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except:
            pass

def convert_time_to_timestamp(time_value):
    """
    将时间值转换为时间戳
    
    Args:
        time_value: 时间值（可能是字符串、整数或浮点数）
        
    Returns:
        int: Unix 时间戳
    """
    if isinstance(time_value, (int, float)):
        return int(time_value)
    
    if isinstance(time_value, str):
        # 尝试多种日期时间格式
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d',
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(time_value, fmt)
                return int(dt.timestamp())
            except ValueError:
                continue
        
        # 如果所有格式都失败，尝试直接转换为整数
        try:
            return int(time_value)
        except ValueError:
            pass
    
    # 如果都失败，返回当前时间
    return int(time.time())

def fetch_detail_data_from_source(source, vod_ids):
    """
    从资源站获取详细数据（包含播放地址等）
    
    Args:
        source: 资源站配置（dict-like 对象）
        vod_ids: 影片ID列表（远程ID，不含前缀）
        
    Returns:
        dict: API 响应数据，失败返回 None
    """
    if not vod_ids:
        return None
    
    # 重试配置
    max_retries = 3
    base_delay = 2
    
    for attempt in range(max_retries):
        try:
            # 构造 MacCMS 标准 detail API URL
            url = source['res_url']
            separator = '&' if '?' in url else '?'
            
            # 拼接多个ID（逗号分隔）
            ids_str = ','.join(str(vid) for vid in vod_ids)
            full_url = f"{url}{separator}ac=detail&ids={ids_str}"
            
            # 发送 HTTP GET 请求
            response = requests.get(full_url, timeout=30)
            response.raise_for_status()
            
            # 解析 JSON
            if source['data_format'] == 'json':
                try:
                    data = response.json()
                    return data
                except json.JSONDecodeError as e:
                    print(f"   ⚠️  JSON 解析失败 (尝试 {attempt+1}/{max_retries}): {e}")
                    # 仅在最后一次尝试失败时打印响应内容
                    if attempt == max_retries - 1:
                        print(f"   🔍 响应内容 (前200字符): {response.text[:200]!r}")
            else:
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  请求失败 (尝试 {attempt+1}/{max_retries}): {e}")
        except Exception as e:
            print(f"   ⚠️  未知错误 (尝试 {attempt+1}/{max_retries}): {e}")
            
        # 如果不是最后一次尝试，则等待后重试
        if attempt < max_retries - 1:
            wait_time = base_delay * (2 ** attempt)  # 指数退避: 2s, 4s...
            print(f"   ⏳ 等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)
            
    return None

def update_vod_with_detail(temp_conn, source, detail_list):
    """
    使用详细数据更新 sc_vod 表
    
    Args:
        temp_conn: 临时数据库连接
        source: 资源站配置
        detail_list: 详细数据列表（MacCMS 格式）
        
    Returns:
        int: 成功更新的数据条数
    """
    cursor = temp_conn.cursor()
    update_count = 0
    
    for vod in detail_list:
        try:
            # 提取远程ID
            remote_vod_id = str(vod.get('vod_id', ''))
            if not remote_vod_id:
                continue
            
            # 生成全局唯一 ID
            res_unique_id = f"{source['res_id_prefix']}{remote_vod_id}"
            
            # Extract detail fields
            vod_en = vod.get('vod_en', '')
            vod_pic = vod.get('vod_pic', '')
            vod_play_url = vod.get('vod_play_url', '')
            vod_actor = vod.get('vod_actor', '')
            vod_director = vod.get('vod_director', '')
            vod_blurb = vod.get('vod_blurb', vod.get('vod_content', ''))
            vod_year = vod.get('vod_year', '')
            vod_area = vod.get('vod_area', '')
            vod_lang = vod.get('vod_lang', '')
            vod_class = vod.get('vod_class', '')
            vod_time_hits = int(vod.get('vod_time_hits', 0))
            
            # Update sc_vod table
            cursor.execute("""
                UPDATE sc_vod
                SET vod_en = ?,
                    vod_pic = ?,
                    vod_play_url = ?,
                    vod_actor = ?,
                    vod_director = ?,
                    vod_blurb = ?,
                    vod_year = ?,
                    vod_area = ?,
                    vod_lang = ?,
                    vod_class = ?,
                    vod_time_hits = ?
                WHERE res_unique_id = ?
            """, (vod_en, vod_pic, vod_play_url, vod_actor, vod_director, vod_blurb, vod_year, vod_area, vod_lang, vod_class, vod_time_hits, res_unique_id))
            
            if cursor.rowcount > 0:
                # 更新搜索表（添加演员信息）
                cursor.execute("SELECT vod_id FROM sc_vod WHERE res_unique_id = ?", (res_unique_id,))
                result = cursor.fetchone()
                if result:
                    vod_id = result[0]
                    vod_name = vod.get('vod_name', '')
                    search_text = f"{vod_name} {vod_actor}".strip()
                    cursor.execute("""
                        UPDATE sc_search
                        SET search_text = ?
                        WHERE vod_id = ?
                    """, (search_text, vod_id))
                
                update_count += 1
            
        except Exception as e:
            print(f"   ⚠️  更新详细数据失败: {e}")
            continue
    
    temp_conn.commit()
    return update_count

def collect_details_for_source(temp_conn, source):
    """
    为资源站的所有影片采集详细数据
    
    Args:
        temp_conn: 临时数据库连接
        source: 资源站配置
        
    Returns:
        int: 成功更新的数据条数
    """
    cursor = temp_conn.cursor()
    
    # 查询该资源站的所有需要更新的影片ID (vod_play_url 为空)
    cursor.execute("""
        SELECT res_unique_id FROM sc_vod
        WHERE res_source_id = ? AND (vod_play_url IS NULL OR vod_play_url = '')
    """, (source['res_source_id'],))
    
    all_unique_ids = [row[0] for row in cursor.fetchall()]
    
    if not all_unique_ids:
        print(f"   ✅ 所有数据已完成详情同步，无需更新")
        return 0
    
    # 提取远程ID（去掉前缀）
    prefix_len = len(source['res_id_prefix'])
    remote_ids = [uid[prefix_len:] for uid in all_unique_ids]
    
    total_count = len(remote_ids)
    print(f"\n   📸 开始采集详细数据（播放地址、海报等）...")
    print(f"   📊 待处理: {total_count} 条")
    
    # 批量处理（每批20个） - API 限制单次最大返回 20 条
    batch_size = 20
    update_count = 0
    
    for i in range(0, total_count, batch_size):
        batch = remote_ids[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_count + batch_size - 1) // batch_size
        
        print(f"   🔄 批次 {batch_num}/{total_batches} (处理 {len(batch)} 条)...", end=' ')
        
        # 获取详细数据
        detail_data = fetch_detail_data_from_source(source, batch)
        
        if detail_data and detail_data.get('code') == 1:
            detail_list = detail_data.get('list', [])
            count = update_vod_with_detail(temp_conn, source, detail_list)
            update_count += count
            print(f"✅ 更新 {count} 条")
        else:
            print(f"❌ 失败")
    
    return update_count

def sync_hot_rank_to_new_records(conn):
    """
    Synchronize hot_rank to the newest record for each video.
    Specific to handling cases where a new ID is generated for the same video (e.g. new episodes).
    """
    print(f"\n" + "=" * 70)
    print(f"🔄 Syncing Hot Rank to Newest Records")
    print(f"=" * 70)
    
    cursor = conn.cursor()
    
    try:
        # Check if hot_rank column exists
        cursor.execute("PRAGMA table_info(sc_vod)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'hot_rank' not in columns:
            print("   ⚠️  hot_rank column not found, skipping sync")
            return 0

        # Find all names that have a hot_rank set to something other than 0
        cursor.execute("SELECT DISTINCT vod_name FROM sc_vod WHERE hot_rank > 0")
        hot_names = [row[0] for row in cursor.fetchall()]
        
        migrated_count = 0
        
        for name in hot_names:
            try:
                # Find all records for this name, ordered by vod_time DESC, then vod_id DESC
                cursor.execute("SELECT vod_id, hot_rank, vod_time FROM sc_vod WHERE vod_name = ? ORDER BY vod_time DESC, vod_id DESC", (name,))
                records = cursor.fetchall()
                
                if not records or len(records) < 1:
                    continue
                    
                # Newest is the first record
                newest_id = records[0][0]
                
                # Calculate the max rank among all these records (to preserve the highest rank if duplicates have different ranks)
                target_rank = 0
                for r in records:
                    if r[1] > 0:
                        target_rank = max(target_rank, r[1])
                
                # Check if we need to update anything
                # We need update if:
                # 1. The newest record doesn't have the target rank
                # 2. OR any other older record HAS a non-zero rank
                
                needs_update = False
                if records[0][1] != target_rank:
                    needs_update = True
                
                for r in records[1:]:
                    if r[1] > 0:
                        needs_update = True
                        break
                
                if not needs_update:
                    continue

                print(f"   🔄 Migrating hot_rank {target_rank} for '{name}' to newest ID {newest_id}")
                
                # Reset all to 0 first
                cursor.execute("UPDATE sc_vod SET hot_rank = 0 WHERE vod_name = ?", (name,))
                
                # Set the newest one to target_rank
                cursor.execute("UPDATE sc_vod SET hot_rank = ? WHERE vod_id = ?", (target_rank, newest_id))
                
                migrated_count += 1
                
            except Exception as e:
                print(f"   ⚠️  Error syncing '{name}': {e}")
                
        conn.commit()
        if migrated_count > 0:
            print(f"✅ Migrated hot_rank for {migrated_count} videos")
        else:
            print(f"✅ No queries needed migration")
            
        return migrated_count
            
    except Exception as e:
        print(f"❌ Hot rank sync failed: {e}")
        return 0

def swap_database_files():
    """
    原子性替换数据库文件，将 TEMP_DB 覆盖 MAIN_DB
    
    Returns:
        bool: 是否成功
    """
    if not os.path.exists(TEMP_DB):
        print(f"❌ 临时数据库文件 {TEMP_DB} 不存在，采集失败或未完成。")
        return False
    
    try:
        # 备份旧主数据库（如果存在）
        if os.path.exists(MAIN_DB):
            backup_name = f"{MAIN_DB}.{time.strftime('%Y%m%d%H%M%S')}.bak"
            shutil.copy2(MAIN_DB, backup_name)
            print(f"📦 已备份旧数据库：{backup_name}")
        
        # 原子性替换
        shutil.move(TEMP_DB, MAIN_DB)
        print(f"✅ 文件切换成功：{TEMP_DB} → {MAIN_DB}")
        
        # 💾 不再创建 sc_temp.db，节省磁盘空间
        # 下次采集时会自动从 sc_main.db 复制
        print(f"💾 已清理临时数据库，节省 {os.path.getsize(MAIN_DB) // 1024 // 1024}MB 空间")
        
        # 清理旧备份文件，只保留最近1个
        cleanup_old_backups(MAIN_DB, keep_count=1)
        
        return True
        
    except Exception as e:
        print(f"❌ 文件切换异常: {e}")
        return False

def cleanup_old_backups(db_name, keep_count=3):
    """
    清理旧的数据库备份文件，只保留最近的 N 个
    
    Args:
        db_name: 主数据库文件名
        keep_count: 保留的备份数量
    """
    try:
        # 获取当前目录
        current_dir = os.path.dirname(os.path.abspath(db_name)) or '.'
        
        # 查找所有备份文件（格式：sc_main.db.YYYYMMDDHHMMSS.bak）
        import glob
        backup_pattern = f"{db_name}.*.bak"
        backup_files = glob.glob(os.path.join(current_dir, backup_pattern))
        
        # 按修改时间排序（最新的在前）
        backup_files.sort(key=os.path.getmtime, reverse=True)
        
        # 删除超出保留数量的备份
        if len(backup_files) > keep_count:
            files_to_delete = backup_files[keep_count:]
            for old_backup in files_to_delete:
                try:
                    os.remove(old_backup)
                    print(f"🗑️  已删除旧备份：{os.path.basename(old_backup)}")
                except Exception as e:
                    print(f"⚠️  删除备份失败 {os.path.basename(old_backup)}: {e}")
            
            print(f"✅ 备份清理完成，保留最近 {keep_count} 个备份")
    
    except Exception as e:
        print(f"⚠️  备份清理异常: {e}")


def fetch_data_from_source(source, page=1, hours=None):
    """
    从资源站获取数据
    
    Args:
        source: 资源站配置（dict-like 对象）
        page: 页码
        hours: 可选，增量采集时间窗口（小时数），None 表示全量采集
        
    Returns:
        dict: API 响应数据，失败返回 None
    """
    try:
        # 构造 MacCMS 标准 API URL
        url = source['res_url']
        
        # 添加分页参数
        separator = '&' if '?' in url else '?'
        full_url = f"{url}{separator}ac=list&pg={page}"
        
        # 如果是增量模式，添加时间过滤参数
        if hours is not None:
            full_url += f"&h={hours}"
        
        print(f"   🌐 请求: {full_url}")
        
        try:
            resp = requests.get(full_url, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"   ❌ 请求失败: {e}")
            print(f"   ⚠️  跳过第 {page} 页，继续下一页...")
            # This function is not in a loop that can 'continue'.
            # It should return None to indicate failure.
            return None 
        
        try:
            data = resp.json()
            return data
        except ValueError as e:
            print(f"   ❌ JSON 解析失败: {e}")
            print(f"   ⚠️  跳过第 {page} 页，继续下一页...")
            # This function is not in a loop that can 'continue'.
            # It should return None to indicate failure.
            return None
            
    except requests.exceptions.Timeout:
        print(f"   ❌ 请求超时")
        return None
    except requests.exceptions.RequestException as e:
        print(f"   ❌ 请求失败: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"   ❌ JSON 解析失败: {e}")
        return None
    except Exception as e:
        print(f"   ❌ 未知错误: {e}")
        return None

def parse_and_insert_vod_data(temp_conn, source, vod_list):
    """
    解析并插入影片数据到临时数据库
    
    Args:
        temp_conn: 临时数据库连接
        source: 资源站配置
        vod_list: 影片列表（MacCMS 格式）
        
    Returns:
        int: 成功插入的数据条数
    """
    cursor = temp_conn.cursor()
    insert_count = 0
    skip_count = 0
    
    # 加载分类映射
    mapping = {}
    if source['res_mapping']:
        try:
            mapping = json.loads(source['res_mapping'])
        except:
            print(f"   ⚠️  分类映射解析失败")
    
    # 检查映射是否为空
    if not mapping:
        print(f"   ⚠️  警告：资源站 '{source['res_name']}' 没有配置分类映射！")
        print(f"   💡 请先使用 'python setup.py map-source-types --source {source['res_id_prefix']}' 配置映射")
        print(f"   ⏭️  跳过此资源站的数据采集")
        return 0
    
    for vod in vod_list:
        try:
            # 提取 MacCMS 标准字段
            remote_vod_id = str(vod.get('vod_id', ''))
            vod_name = vod.get('vod_name', '').strip()
            remote_type_id = str(vod.get('type_id', '0'))
            
            if not remote_vod_id or not vod_name:
                continue
            
            # 生成全局唯一 ID
            res_unique_id = f"{source['res_id_prefix']}{remote_vod_id}"
            
            # 🎯 严格映射模式：如果找不到映射，跳过数据
            vod_type_id = mapping.get(remote_type_id)
            
            if vod_type_id is None:
                # 跳过无映射的数据，避免脏数据
                skip_count += 1
                if skip_count <= 5:  # 只显示前5个警告，避免刷屏
                    print(f"   ⚠️  跳过无映射数据: {vod_name} (远程分类ID: {remote_type_id})")
                continue
            
            # Other fields
            vod_en = vod.get('vod_en', '')
            vod_pic = vod.get('vod_pic', '')
            vod_remarks = vod.get('vod_remarks', '')
            vod_blurb = vod.get('vod_blurb', vod.get('vod_content', ''))  # 简介
            vod_actor = vod.get('vod_actor', '')
            vod_director = vod.get('vod_director', '')
            vod_play_url = vod.get('vod_play_url', '')
            vod_play_from = vod.get('vod_play_from', '')
            
            # Normalize source names: wjm3u8 -> wj, mtm3u8 -> mt
            if vod_play_from:
                vod_play_from = vod_play_from.replace('wjm3u8', 'wj').replace('mtm3u8', 'mt')
            
            vod_year = vod.get('vod_year', '')
            vod_area = vod.get('vod_area', '')
            vod_lang = vod.get('vod_lang', '')
            vod_class = vod.get('vod_class', '')
            
            # 时间处理：支持字符串和时间戳两种格式
            vod_time_raw = vod.get('vod_time', None)
            if vod_time_raw is not None:
                vod_time = convert_time_to_timestamp(vod_time_raw)
            else:
                vod_time = int(time.time())
            
            vod_time_hits = int(vod.get('vod_time_hits', 0))
            vod_hits = int(vod.get('vod_hits', 0))
            
            # 插入 sc_vod 表（使用 INSERT OR REPLACE 去重）
            cursor.execute("""
                INSERT OR REPLACE INTO sc_vod (
                    res_unique_id, res_source_id, vod_name, vod_type_id,
                    vod_en, vod_pic, vod_remarks, vod_blurb, vod_play_url, vod_play_from,
                    vod_actor, vod_director, vod_year, vod_area, vod_lang, vod_class,
                    vod_time, vod_time_hits, vod_hits
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                res_unique_id, source['res_source_id'], vod_name, vod_type_id,
                vod_en, vod_pic, vod_remarks, vod_blurb, vod_play_url, vod_play_from,
                vod_actor, vod_director, vod_year, vod_area, vod_lang, vod_class,
                vod_time, vod_time_hits, vod_hits
            ))
            
            # 获取插入后的 vod_id
            cursor.execute("SELECT vod_id FROM sc_vod WHERE res_unique_id = ?", (res_unique_id,))
            result = cursor.fetchone()
            if result:
                vod_id = result[0]
                
                # 更新 sc_search 表（用于搜索优化）
                search_text = f"{vod_name} {vod_actor}".strip()
                cursor.execute("""
                    INSERT OR REPLACE INTO sc_search (vod_id, search_text)
                    VALUES (?, ?)
                """, (vod_id, search_text))
                
                insert_count += 1
            
        except Exception as e:
            print(f"   ⚠️  处理数据失败: {e} - 数据: {vod.get('vod_name', 'N/A')}")
            continue
    
    temp_conn.commit()
    
    # 报告跳过的数据
    if skip_count > 0:
        print(f"   ℹ️  共跳过 {skip_count} 条无映射数据")
    
    return insert_count

def collect_from_source(temp_conn, source, hours=None, auto_confirm=False):
    """
    从单个资源站采集所有数据
    
    Args:
        temp_conn: 临时数据库连接
        source: 资源站配置
        hours: 可选，增量采集时间窗口（小时数），None 表示全量采集
        auto_confirm: 非交互模式，自动确认采集（用于 cron/自动化）
        
    Returns:
        int: 总共采集的数据条数
    """
    print(f"\n📡 采集资源站: {source['res_name']} ({source['res_id_prefix']})")
    print(f"   URL: {source['res_url']}")
    
    # 先获取第一页，显示统计信息
    print(f"\n🔍 正在获取资源站信息...")
    first_page_data = fetch_data_from_source(source, 1, hours)
    
    if not first_page_data or first_page_data.get('code') != 1:
        print(f"   ❌ 无法获取资源站信息")
        return 0
    
    # 显示统计信息
    total_pages = first_page_data.get('pagecount', 1)
    total_records = first_page_data.get('total', 0)
    per_page = first_page_data.get('limit', 20)
    
    print(f"\n📊 资源站统计")
    print("=" * 50)
    print(f"   总页数: {total_pages:,} 页")
    print(f"   总记录: {total_records:,} 条")
    print(f"   每页数: {per_page} 条")
    
    # Initialize pagination variables
    start_page = 1
    max_pages = total_pages
    
    # 增量模式：跳过用户确认，直接采集所有结果
    if hours is not None:
        print(f"   📊 增量采集：最近 {hours} 小时内更新的数据")
        print("=" * 50)
    else:
        # 全量模式：显示预估时间并询问用户
        estimated_minutes = (total_pages * 0.5) / 60
        print(f"   预计耗时: {estimated_minutes:.1f} 分钟")
        print("=" * 50)
        
        # 询问用户确认 (除非 --yes 模式)
        if auto_confirm:
            print(f"\n✅ 非交互模式 (--yes)：自动采集全部 {total_pages:,} 页")
        else:
            print(f"\n⚠️  采集选项：")
            print(f"   [1] 采集全部 ({total_pages:,} 页)")
            print(f"   [2] 采集部分（指定页码范围）")
            print(f"   [3] 取消采集")
            
            choice = input("\n→ 请选择 [1/2/3，默认:1]: ").strip() or '1'
            
            if choice == '3':
                print("\n❌ 已取消采集")
                return 0
            
            if choice == '2':
                try:
                    print(f"\n→ 请输入页码范围：")
                    page_range = input(f"   格式: 起始页-结束页 (例如: 1-10 或 5-15) [1-{total_pages}]: ").strip()
                    
                    if '-' in page_range:
                        # Parse range like "5-10"
                        start_str, end_str = page_range.split('-', 1)
                        start_page = int(start_str.strip())
                        end_page = int(end_str.strip())
                        
                        # Validate range
                        if start_page < 1:
                            start_page = 1
                        if end_page > total_pages:
                            end_page = total_pages
                        if start_page > end_page:
                            start_page, end_page = end_page, start_page  # Swap if reversed
                        
                        max_pages = end_page
                        print(f"   ✅ 将采集第 {start_page} 到 {end_page} 页 (共 {end_page - start_page + 1} 页)")
                    else:
                        # Just a number, treat as number of pages from start
                        num_pages = int(page_range)
                        if 1 <= num_pages <= total_pages:
                            max_pages = num_pages
                            print(f"   ✅ 将采集前 {num_pages} 页")
                        else:
                            print(f"   ⚠️  页数超出范围，使用全部页数: {total_pages}")
                            
                except (ValueError, AttributeError):
                    print(f"   ⚠️  输入无效，使用全部页数: {total_pages}")
                    start_page = 1
                    max_pages = total_pages
    
    # 开始采集
    print(f"\n🚀 开始采集...")
    total_count = 0
    page = start_page  # Start from user-specified page
    
    while True:
        print(f"\n   📄 采集第 {page}/{max_pages} 页...")
        
        # 第一页已经获取过，直接使用
        if page == 1 and start_page == 1:
            data = first_page_data
        else:
            # 获取数据
            data = fetch_data_from_source(source, page, hours)
            
            if not data:
                print(f"   ⚠️  第 {page} 页获取失败，跳过并继续...")
                page += 1
                continue  # Skip failed page - exits this iteration completely
            
            # 检查响应码
            if data.get('code') != 1:
                print(f"   ⚠️  API 返回错误: {data.get('msg', '未知错误')}，跳过...")
                page += 1
                continue  # Skip page with API error

        
        # 提取影片列表
        vod_list = data.get('list', [])
        
        if not vod_list:
            print(f"   ✅ 第 {page} 页无数据，采集完成")
            break
        
        # 解析并插入数据
        count = parse_and_insert_vod_data(temp_conn, source, vod_list)
        total_count += count
        
        print(f"   ✅ 第 {page} 页处理完成，新增/更新 {count} 条数据")
        
        # 检查是否达到用户设定的页数限制
        if page >= max_pages:
            print(f"   ✅ 已达到设定页数 ({max_pages})，采集完成")
            break
        
        # 检查是否是最后一页
        try:
            current_page = int(data.get('page', page))
            total_pages_api = int(data.get('pagecount', 1))
        except (ValueError, TypeError):
            current_page = page
            total_pages_api = 1
        
        if current_page >= total_pages_api:
            print(f"   ✅ 已到达最后一页 ({total_pages_api})，采集完成")
            break
        
        page += 1
        
        # 礼貌延迟，避免对资源站造成压力
        time.sleep(0.5)
    
    return total_count

def run_collection():
    """主采集函数"""
    import argparse
    
    # Create argument parser
    parser = argparse.ArgumentParser(
        description='StreamCore Data Collector - Collect video data from multiple sources',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Full collection (default)
  python3 collector.py --mode full
  
  # Incremental collection (last 6 hours)
  python3 collector.py --mode incremental --hours 6
  
  # Details only (skip list collection)
  python3 collector.py --mode details-only

Note: All modes automatically merge duplicates before database swap!
        '''
    )
    
    parser.add_argument(
        '--mode',
        choices=['full', 'incremental', 'details-only'],
        default='full',
        help='Collection mode (default: full)'
    )
    
    parser.add_argument(
        '--hours',
        type=int,
        metavar='N',
        help='Hours for incremental mode (e.g., --mode incremental --hours 6)'
    )
    
    parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Non-interactive mode: auto-confirm all prompts (required for cron/automation)'
    )
    
    args = parser.parse_args()
    
    # Extract arguments
    mode = args.mode
    hours = args.hours
    auto_confirm = args.yes
    
    # Validate mode-specific requirements
    if mode == 'incremental' and hours is None:
        parser.error("--hours argument required for incremental mode")
    
    # Set details_only flag
    details_only = (mode == 'details-only')

    # 🔒 Acquire lock to prevent concurrent runs
    lock_fd = acquire_lock()
    if lock_fd is None:
        print("❌ 另一个采集器实例正在运行！")
        print("   如果确定没有其他实例，请删除 collector.lock 文件后重试")
        print("   rm collector.lock")
        return
    
    try:
        print("=" * 70)
        if details_only:
            mode_text = "仅采集详细数据模式"
        elif mode == 'incremental':
            mode_text = f"增量模式 - 最近 {hours} 小时"
        else:
            mode_text = "全量模式"
        
        print(f"🚀 StreamCore 采集任务启动 ({mode_text})")
        print(f"🔒 进程锁已获取 (PID: {os.getpid()})")
        print("=" * 70)
        print(f"⏰ 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
        # 🔍 Check if temp DB exists BEFORE connecting (which would create an empty file)
        if not os.path.exists(TEMP_DB):
            if os.path.exists(MAIN_DB):
                print(f"📦 正在从主数据库复制数据到临时库...")
                shutil.copy2(MAIN_DB, TEMP_DB)
            else:
                print(f"🆕 主数据库不存在，初始化新的临时数据库...")
                init_db(TEMP_DB)
        
        # Now connect (file exists and is populated/initialized)
        temp_conn = get_db_connection(TEMP_DB)

        # 🛡️ Self-healing: Check if the database is valid (has tables)
        # If the file exists but is empty (e.g. created by previous bug), table check will fail
        try:
            temp_conn.execute("SELECT 1 FROM sc_vod LIMIT 1")
        except sqlite3.OperationalError:
            print(f"⚠️  检测到临时数据库损坏或未初始化 (无 sc_vod 表)")
            print(f"🔄 正在尝试自动修复...")
            temp_conn.close()
            
            if os.path.exists(MAIN_DB):
                print(f"📦 从主数据库重新复制...")
                shutil.copy2(MAIN_DB, TEMP_DB)
            else:
                print(f"🆕 重新初始化数据库结构...")
                init_db(TEMP_DB)
            
            # Reconnect
            temp_conn = get_db_connection(TEMP_DB)

        main_conn = get_db_connection(MAIN_DB)
        sources = get_all_sources(main_conn)
        main_conn.close()
        
        if not sources:
            print("\n❌ 未配置任何资源站，请先使用 'python setup.py add-source' 添加资源站")
            temp_conn.close()
            return
        
        print(f"\n📋 共找到 {len(sources)} 个资源站配置")
        
        total_collected = 0
        success_count = 0
        
        # 1. 列表采集阶段 (非 details-only 模式下执行)
        if not details_only:
            for source in sources:
                try:
                    count = collect_from_source(temp_conn, source, hours, auto_confirm)
                    total_collected += count
                    success_count += 1
                except Exception as e:
                    print(f"\n❌ 采集资源站 {source['res_name']} 时发生异常: {e}")
                    continue
        else:
            print("\n⏭️  跳过列表采集阶段 (details-only)")
            # 统计一下有多少数据需要更新详情
            for source in sources:
                cursor = temp_conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM sc_vod WHERE res_source_id=?", (source['res_source_id'],))
                count = cursor.fetchone()[0]
                total_collected += count
                success_count += 1

        # 2. 详细数据采集阶段 (自动采集播放地址、海报等)
        detail_total = 0  # Initialize here to prevent UnboundLocalError
        if total_collected > 0:
            print("\n" + "=" * 70)
            print("📸 采集详细数据（播放地址、海报、演员等）")
            print("=" * 70)
            
            for source in sources:
                try:
                    count = collect_details_for_source(temp_conn, source)
                    detail_total += count
                except Exception as e:
                    print(f"\n❌ 采集详细数据失败 {source['res_name']}: {e}")
                    continue
            
            print(f"\n✅ 详细数据采集完成，共更新 {detail_total} 条记录")
        
        # 🆕 Sync hot_rank to newest records (Server-side fix for stale IDs)
        # Always run this to auto-heal the database even if no new data was collected
        migrated_hot_rank_count = sync_hot_rank_to_new_records(temp_conn)
        
        temp_conn.close()
        
        # Summary statistics
        print(f"\n======================================================================")
        print(f"📊 采集统计")
        print(f"======================================================================")
        print(f"✅ 处理资源站数: {success_count}/{len(sources)}")
        print(f"📦 新增记录数: {total_collected}")
        print(f"📦 更新详细信息数: {detail_total}")
        print(f"🔄 热榜迁移数: {migrated_hot_rank_count}")
        print(f"⏰ 完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 🆕 Auto-merge duplicates in TEMP database (before swap)
        if total_collected > 0 or detail_total > 0:
            print(f"\n======================================================================")
            print(f"🔄 Auto-Merging Duplicates")
            print(f"======================================================================")
            
            try:
                from merge_dedupe import auto_merge
                merge_stats = auto_merge(TEMP_DB)
                
                if merge_stats['groups_merged'] > 0:
                    print(f"✅ Merged {merge_stats['groups_merged']} duplicate groups")
                    print(f"✅ Deleted {merge_stats['records_deleted']} duplicate records")
                else:
                    print(f"   ℹ️  No duplicates found to merge")
            except Exception as e:
                print(f"⚠️  Merge failed: {e}")
                print(f"   Continuing without merge...")
        
        # Execute database file switch
        # Enable swap if ANY data was changed (collected, detail updated, OR hot rank migrated)
        if total_collected > 0 or detail_total > 0 or migrated_hot_rank_count > 0:
            print("\n" + "=" * 70)
            print("🔄 执行数据库文件切换")
            print("=" * 70)
            
            if swap_database_files():
                print("\n✅ 采集任务全部完成！新数据已生效。")
            else:
                print("\n❌ 文件切换失败，API 服务将继续使用旧数据")
        else:
            print("\n⚠️  未采集到任何数据，跳过文件切换")
        
        print("=" * 70)
    
    finally:
        # 🔓 Always release lock when done
        release_lock(lock_fd)
        print("🔓 进程锁已释放")

if __name__ == '__main__':
    run_collection()
