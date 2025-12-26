# app.py
# StreamCore Flask API 服务
# 提供 MacCMS V10 兼容的 JSON API 接口

from flask import Flask, jsonify, request
from db_config import get_db_connection, MAIN_DB
import os
import time
import requests

app = Flask(__name__)

# 配置JSON响应不转义非ASCII字符（解决中文显示问题）
app.config['JSON_AS_ASCII'] = False
# 禁用 Flask 的 JSON 键排序，保持原始顺序
app.config['JSON_SORT_KEYS'] = False

# ============================================================
# 豆瓣热搜 API 配置
# ============================================================

# 豆瓣移动端 API 基础地址
DOUBAN_API_BASE = "https://m.douban.com/rexxar/api/v2/subject/recent_hot"

# 请求头（模拟微信内置浏览器）
DOUBAN_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/7.0.13(0x17000d2b) NetType/WIFI Language/zh_CN',
    'Referer': 'https://m.douban.com/tv/show'
}

# 热搜类型配置
HOT_TYPE_CONFIG = {
    'movie': {'url': f'{DOUBAN_API_BASE}/movie?start=0&limit=40', 'msg': '热门电影'},
    'newmovie': {'url': f'{DOUBAN_API_BASE}/movie?start=0&limit=40&category=%E6%9C%80%E6%96%B0&type=%E5%85%A8%E9%83%A8', 'msg': '最新电影'},
    'tv': {'url': f'{DOUBAN_API_BASE}/tv?start=0&limit=40&category=tv&type=tv', 'msg': '热门电视剧'},
    'show': {'url': f'{DOUBAN_API_BASE}/tv?start=0&limit=40&category=show&type=show', 'msg': '热门综艺'}
}

# 缓存配置（6小时）
HOT_CACHE_DURATION = 6 * 60 * 60
hot_cache = {}  # {hot_type: {'data': [...], 'timestamp': time}}

@app.route('/api.php/provide/vod', methods=['GET'])
@app.route('/api.php/provide/vod/', methods=['GET'])
def maccms_api():
    """
    MacCMS V10 兼容的采集 API 接口
    
    支持的参数：
    - ac: 动作类型 (list/detail)
    - t: 分类 ID（可选，逗号分隔多个）
    - pg: 页码（默认 1）
    - area: 地区筛选（可选，如：香港、美国、日本）
    - year: 年份筛选（可选，如：2025、2024）
    - lang: 语言筛选（可选，如：国语、英语、日语）
    - ids: 影片 ID（逗号分隔，用于 detail）
    - wd: 搜索关键词（用于 detail），支持智能搜索：
          - 单个字母 A-Z：首字母搜索（基于 vod_en）
          - # 或数字：数字开头的影片
          - 多字符：普通关键词搜索
    - h: 小时内更新（可选）
    """
    
    # 检查数据库文件
    if not os.path.exists(MAIN_DB):
        return jsonify({
            'code': 0,
            'msg': '数据库文件缺失，请先运行 python setup.py init 初始化项目'
        }), 500
    
    # 获取请求参数
    action = request.args.get('ac', 'list')
    
    conn = get_db_connection(MAIN_DB)
    cursor = conn.cursor()
    
    try:
        if action == 'list':
            return handle_list_action(cursor, request)
        elif action == 'detail':
            return handle_detail_action(cursor, request)
        elif action == 'hot':
            return handle_hot_action(cursor, request)
        else:
            return jsonify({
                'code': 0,
                'msg': f'不支持的操作: {action}'
            }), 400
            
    except Exception as e:
        print(f"❌ API 错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'code': 0,
            'msg': f'API 服务器错误: {str(e)}'
        }), 500
        
    finally:
        conn.close()

def handle_list_action(cursor, request):
    """
    处理列表查询请求
    
    Args:
        cursor: 数据库游标
        request: Flask 请求对象
        
    Returns:
        Flask JSON 响应
    """
    # 解析参数
    type_id = request.args.get('t')
    page = int(request.args.get('pg', 1))
    hours = request.args.get('h')
    area = request.args.get('area')  # 地区筛选
    year = request.args.get('year')  # 年份筛选
    lang = request.args.get('lang')  # 语言筛选
    
    # 限制分页参数
    if page < 1:
        page = 1
    limit = 20
    offset = (page - 1) * limit
    
    # 构建查询条件
    where_clauses = []
    params = []
    
    # 分类筛选
    # 重要：支持L1/L2两级分类查询
    # 如果查询L1父分类，需要包含所有子分类的数据
    if type_id:
        type_ids = [t.strip() for t in type_id.split(',') if t.strip()]
        if type_ids:
            # 对每个分类ID，检查是否是L1父分类，如果是则包含所有子分类
            all_type_ids = []
            for tid in type_ids:
                all_type_ids.append(tid)
                
                # 查询是否有子分类（type_pid = tid）
                cursor.execute("SELECT type_id FROM sc_type WHERE type_pid = ?", (tid,))
                child_types = cursor.fetchall()
                
                # 如果有子分类，添加到查询列表
                for child in child_types:
                    all_type_ids.append(str(child['type_id']))
            
            # 构建IN查询
            placeholders = ','.join('?' * len(all_type_ids))
            where_clauses.append(f"vod_type_id IN ({placeholders})")
            params.extend(all_type_ids)


    
    # 地区筛选（MacCMS V10 标准 + 智能映射）
    if area:
        # 智能地区映射：自动包含相关地区的别名
        # 例如：查询"中国"时自动包含"大陆"和"中国大陆"
        area_mapping = {
            '中国': ['中国', '大陆', '中国大陆'],
            '大陆': ['大陆', '中国', '中国大陆'],
            '中国大陆': ['中国大陆', '中国', '大陆'],
            '香港': ['香港', '中国香港'],
            '中国香港': ['中国香港', '香港'],
            '台湾': ['台湾', '中国台湾'],
            '中国台湾': ['中国台湾', '台湾'],
        }
        
        # 检查是否有映射，如果有则使用OR条件查询多个值
        if area in area_mapping:
            area_values = area_mapping[area]
            placeholders = ' OR '.join(['vod_area = ?' for _ in area_values])
            where_clauses.append(f"({placeholders})")
            params.extend(area_values)
        else:
            # 没有映射的地区使用精确匹配
            where_clauses.append("vod_area = ?")
            params.append(area)
    
    # 年份筛选（MacCMS V10 标准）
    if year:
        where_clauses.append("vod_year = ?")
        params.append(year)
    
    # 语言筛选（MacCMS V10 标准 + 智能映射）
    if lang:
        # 智能语言映射：自动包含相关语言的别名
        # 例如：查询"国语"时自动包含"普通话"
        lang_mapping = {
            '国语': ['国语', '普通话', '汉语普通话'],
            '汉语': ['汉语普通话', '普通话'],
            '普通话': ['普通话', '国语', '汉语普通话'],
            '汉语普通话': ['汉语普通话', '国语', '普通话'],
            '英语': ['英语', 'English'],
            'English': ['English', '英语'],
            '粤语': ['粤语', '广东话'],
            '广东话': ['广东话', '粤语'],
        }
        
        # 检查是否有映射，如果有则使用OR条件查询多个值
        if lang in lang_mapping:
            lang_values = lang_mapping[lang]
            placeholders = ' OR '.join(['vod_lang = ?' for _ in lang_values])
            where_clauses.append(f"({placeholders})")
            params.extend(lang_values)
        else:
            # 没有映射的语言使用精确匹配
            where_clauses.append("vod_lang = ?")
            params.append(lang)
    
    # 时间筛选（小时内更新）
    if hours:
        try:
            hours_int = int(hours)
            time_threshold = int(time.time()) - (hours_int * 3600)
            where_clauses.append("vod_time >= ?")
            params.append(time_threshold)
        except ValueError:
            pass
    
    # 构建 WHERE 子句
    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)
    
    # 查询总数
    count_sql = f"SELECT COUNT(*) FROM sc_vod {where_sql}"
    cursor.execute(count_sql, params)
    total = cursor.fetchone()[0]
    
    # 计算总页数
    pagecount = (total + limit - 1) // limit if total > 0 else 1
    
    # Query data (sorted by update time descending)
    list_sql = f"""
        SELECT vod_id
        FROM sc_vod
        {where_sql}
        ORDER BY vod_time DESC
        LIMIT ? OFFSET ?
    """
    cursor.execute(list_sql, params + [limit, offset])
    
    # Get vod_ids and fetch details
    vod_ids = [str(row['vod_id']) for row in cursor.fetchall()]
    
    if vod_ids:
        vod_list = fetch_vod_details(cursor, vod_ids)
    else:
        vod_list = []
    
    # Fetch class list for MacCMS compatibility and dynamic filtering
    class_list = []
    try:
        cursor.execute("SELECT type_id, type_name, type_pid FROM sc_type")
        types = cursor.fetchall()
        for t in types:
            class_list.append({
                'type_id': t['type_id'],
                'type_name': t['type_name'],
                'type_pid': t['type_pid']
            })
    except Exception as e:
        print(f"Error fetching class list: {e}")

    # Build response with accurate counts
    response = {
        'code': 1,
        'msg': '数据列表',
        'page': page,
        'pagecount': pagecount,
        'limit': len(vod_list),  # Actual count after deduplication
        'total': total,  # Keep original total for pagination
        'list': vod_list,
        'class': class_list
    }
    
    # 使用 Response 对象确保中文正常显示
    import json
    from flask import Response
    return Response(
        json.dumps(response, ensure_ascii=False),
        mimetype='application/json'
    )


def handle_detail_action(cursor, request):
    """
    处理详情查询请求
    
    Args:
        cursor: 数据库游标
        request: Flask 请求对象
        
    Returns:
        Flask JSON 响应
    """
    # 解析参数
    ids = request.args.get('ids')
    keyword = request.args.get('wd')
    hours = request.args.get('h')  # MacCMS V10标准：支持时间筛选
    page = int(request.args.get('pg', 1))  # 分页支持
    
    vod_list = []
    total = 0
    limit = 20
    offset = (page - 1) * limit
    
    if keyword:
        keyword = keyword.strip()
        
        if keyword:
            # 智能搜索：判断是首字母搜索还是关键词搜索
            # - 纯英文字母（A-Z，如 HZW）：转换为 H%Z%W% 模式匹配 vod_en
            # - # 或数字：搜索 vod_en 以数字开头
            # - 包含中文等非ASCII字符：普通关键词搜索
            
            search_term = keyword.upper().strip()
            
            # 判断是否为纯英文字母（首字母搜索模式）
            is_pinyin_search = search_term.replace(' ', '').isalpha() and search_term.replace(' ', '').isascii()
            is_number_search = len(search_term) == 1 and (search_term == '#' or search_term.isdigit())
            
            if is_number_search:
                # 搜索数字开头的影片
                cursor.execute("""
                    SELECT COUNT(*) FROM sc_vod 
                    WHERE vod_en GLOB '[0-9]*'
                """)
                total = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT vod_id FROM sc_vod 
                    WHERE vod_en GLOB '[0-9]*'
                    ORDER BY vod_time DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))
                
                results = cursor.fetchall()
                if results:
                    vod_ids = [str(row['vod_id']) for row in results]
                    vod_list = fetch_vod_details(cursor, vod_ids)
                    
            elif is_pinyin_search:
                # 拼音首字母搜索
                # 把 HZW 转换为 H%Z%W% 的 LIKE 模式
                letters = search_term.replace(' ', '')
                like_pattern = '%'.join(letters) + '%'  # HZW -> H%Z%W%
                
                cursor.execute("""
                    SELECT COUNT(*) FROM sc_vod 
                    WHERE UPPER(vod_en) LIKE ?
                """, (like_pattern,))
                total = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT vod_id FROM sc_vod 
                    WHERE UPPER(vod_en) LIKE ?
                    ORDER BY vod_time DESC
                    LIMIT ? OFFSET ?
                """, (like_pattern, limit, offset))
                
                results = cursor.fetchall()
                if results:
                    vod_ids = [str(row['vod_id']) for row in results]
                    vod_list = fetch_vod_details(cursor, vod_ids)
            else:
                # 普通关键词搜索（在 sc_search 表中搜索）
                cursor.execute("""
                    SELECT s.vod_id
                    FROM sc_search s
                    WHERE s.search_text LIKE ?
                    LIMIT 100
                """, (f'%{keyword}%',))
                
                search_results = cursor.fetchall()
                
                if search_results:
                    vod_ids = [str(row['vod_id']) for row in search_results]
                    vod_list = fetch_vod_details(cursor, vod_ids)
                    total = len(vod_list)
    
    elif ids:
        # ID query
        vod_ids = [id.strip() for id in ids.split(',') if id.strip()]
        if vod_ids:
            vod_list = fetch_vod_details(cursor, vod_ids)
            total = len(vod_list)
    
    elif hours:
        # MacCMS V10标准：按时间获取详情
        # ac=detail&h=24 - 获取24小时内更新的详细信息
        try:
            hours_int = int(hours)
            time_threshold = int(time.time()) - (hours_int * 3600)
            
            cursor.execute("""
                SELECT vod_id 
                FROM sc_vod 
                WHERE vod_time >= ?
                ORDER BY vod_time DESC
                LIMIT 100
            """, (time_threshold,))
            
            results = cursor.fetchall()
            if results:
                vod_ids = [str(row['vod_id']) for row in results]
                vod_list = fetch_vod_details(cursor, vod_ids)
                total = len(vod_list)
        except ValueError:
            pass
    
    # 计算总页数
    pagecount = (total + limit - 1) // limit if total > 0 else 1
    
    # 构建响应
    response = {
        'code': 1,
        'msg': '数据列表',
        'page': page,
        'pagecount': pagecount,
        'limit': len(vod_list),
        'total': total,
        'list': vod_list
    }
    
    # 使用 Response 对象确保中文正常显示
    import json
    from flask import Response
    return Response(
        json.dumps(response, ensure_ascii=False),
        mimetype='application/json'
    )


def fetch_vod_details(cursor, vod_ids):
    """
    根据ID列表获取影片详情（完整信息）
    MacCMS V10标准：detail接口返回完整数据，包括播放地址
    
    Args:
        cursor: 数据库游标
        vod_ids: 影片ID列表
        
    Returns:
        list: 影片详情列表
    """
    if not vod_ids:
        return []
    
    placeholders = ','.join('?' * len(vod_ids))
    
    cursor.execute(f"""
        SELECT 
            vod_id,
            vod_name,
            vod_en,
            vod_type_id AS type_id,
            vod_pic,
            vod_remarks,
            vod_time,
            vod_time_hits,
            vod_play_url,
            vod_play_from,
            vod_actor,
            vod_director,
            vod_year,
            vod_area,
            vod_lang,
            vod_class,
            vod_blurb
        FROM sc_vod
        WHERE vod_id IN ({placeholders})
    """, vod_ids)
    
    vod_list = []
    for row in cursor.fetchall():
        vod_data = {
            'vod_id': row['vod_id'],
            'vod_name': row['vod_name'],
            'vod_en': row['vod_en'] or '',
            'type_id': row['type_id'],
            'vod_pic': row['vod_pic'] or '',
            'vod_remarks': row['vod_remarks'] or '',
            'vod_time': row['vod_time'],
            'vod_time_hits': row['vod_time_hits'] or 0,
            'vod_play_url': row['vod_play_url'] or '',
            'vod_play_from': row['vod_play_from'] or '',
            'vod_actor': row['vod_actor'] or '',
            'vod_director': row['vod_director'] or '',
            'vod_year': row['vod_year'] or '',
            'vod_area': row['vod_area'] or '',
            'vod_lang': row['vod_lang'] or '',
            'vod_class': row['vod_class'] or '',
            'vod_blurb': row['vod_blurb'] or ''
        }
        vod_list.append(vod_data)
    
    # Populate empty vod_play_from fields with source names
    vod_list = populate_play_from_sources(cursor, vod_list)
    
    return vod_list

def populate_play_from_sources(cursor, vod_list):
    """
    Populate empty vod_play_from fields with meaningful source names
    Uses res_id_prefix from sc_config as the source identifier
    
    Args:
        cursor: Database cursor
        vod_list: List of vod records
        
    Returns:
        list: vod_list with populated vod_play_from fields
    """
    if not vod_list:
        return vod_list
    
    # Get vod_ids that need source names
    vod_ids_needing_names = [v['vod_id'] for v in vod_list if not v.get('vod_play_from')]
    
    if not vod_ids_needing_names:
        return vod_list  # All already have vod_play_from
    
    # Fetch source names for these vod_ids
    placeholders = ','.join('?' * len(vod_ids_needing_names))
    cursor.execute(f"""
        SELECT v.vod_id, c.res_id_prefix
        FROM sc_vod v
        JOIN sc_config c ON v.res_source_id = c.res_source_id
        WHERE v.vod_id IN ({placeholders})
    """, vod_ids_needing_names)
    
    # Build mapping: vod_id -> source_name
    vod_id_to_source = {}
    for row in cursor.fetchall():
        # Use prefix as source name (e.g., "wj_", "mt_")
        # Remove trailing underscore for cleaner display
        source_name = row['res_id_prefix'].rstrip('_')
        vod_id_to_source[row['vod_id']] = source_name
    
    # Update vod_list with source names
    for vod in vod_list:
        if not vod.get('vod_play_from') and vod['vod_id'] in vod_id_to_source:
            vod['vod_play_from'] = vod_id_to_source[vod['vod_id']]
    
    return vod_list

def get_dedup_key(vod):
    """
    Generate deduplication key for grouping records
    Fixed grouping: (vod_name, vod_year)
    
    Args:
        vod: Video record dict
        
    Returns:
        tuple: Deduplication key
    """
    return (vod.get('vod_name', ''), vod.get('vod_year', ''))

def select_primary_record(duplicates):
    """
    Select the best record as primary from duplicate group
    Priority: has play_url > has pic > latest vod_time
    
    Args:
        duplicates: List of duplicate video records
        
    Returns:
        dict: Primary record with best data quality
    """
    scored = []
    for vod in duplicates:
        score = 0
        # Priority 1: Has play URLs (most important)
        if vod.get('vod_play_url'):
            score += 1000
        # Priority 2: Has poster image
        if vod.get('vod_pic'):
            score += 100
        # Priority 3: Latest update time (tiebreaker)
        score += vod.get('vod_time', 0) / 1000000.0
        
        scored.append((score, vod))
    
    # Return the highest scored record
    return max(scored, key=lambda x: x[0])[1].copy()

def merge_vod_records(duplicates):
    """
    Merge duplicate records into single record with combined play sources
    Uses MacCMS 10 standard format for multi-source support
    
    Args:
        duplicates: List of duplicate video records
        
    Returns:
        dict: Merged record with combined vod_play_from and vod_play_url
    """
    if len(duplicates) == 1:
        return duplicates[0]
    
    # Select primary record (best metadata)
    merged = select_primary_record(duplicates)
    
    # Collect play sources from all duplicates
    play_froms = []
    play_urls = []
    
    for vod in duplicates:
        vod_play_from = vod.get('vod_play_from', '').strip()
        vod_play_url = vod.get('vod_play_url', '').strip()
        
        # Only include if has actual play data
        if vod_play_url:
            # Use vod_play_from if available, otherwise generate from vod_id
            if not vod_play_from:
                vod_play_from = f"source_{vod.get('vod_id', 'unknown')}"
            
            play_froms.append(vod_play_from)
            play_urls.append(vod_play_url)
    
    # Merge using MacCMS 10 standard format
    # vod_play_from: "source1$$$source2$$$source3"
    # vod_play_url: "source1_episodes$$$source2_episodes$$$source3_episodes"
    #   Where each source's episodes are internally separated by #:
    #   "第01集$url1#第02集$url2$$$第01集$url3#第02集$url4"
    if play_froms:
        merged['vod_play_from'] = '$$$'.join(play_froms)
        merged['vod_play_url'] = '$$$'.join(play_urls)  # FIX: Use $$$ between sources!
    
    return merged

def deduplicate_vod_list(vod_list):
    """
    Deduplicate video list by (vod_name, vod_year) and merge play sources
    Always-on feature for better UX
    
    Args:
        vod_list: List of video records
        
    Returns:
        list: Deduplicated records with merged sources (MacCMS 10 compatible)
    """
    if not vod_list:
        return []
    
    # Group by deduplication key
    groups = {}
    for vod in vod_list:
        key = get_dedup_key(vod)
        if key not in groups:
            groups[key] = []
        groups[key].append(vod)
    
    # Merge each group
    merged_list = []
    for key, duplicates in groups.items():
        merged = merge_vod_records(duplicates)
        merged_list.append(merged)
    
    return merged_list

# ============================================================
# 豆瓣热搜 API 功能
# ============================================================

def fetch_douban_hot(hot_type):
    """
    从豆瓣获取热门影视列表
    
    Args:
        hot_type: 热搜类型 (movie/newmovie/tv/show)
        
    Returns:
        list: 豆瓣返回的影片列表 [{title, id, rating, pic, ...}, ...]
    """
    if hot_type not in HOT_TYPE_CONFIG:
        return []
    
    config = HOT_TYPE_CONFIG[hot_type]
    
    try:
        response = requests.get(config['url'], headers=DOUBAN_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # 提取 items 列表
        items = data.get('items', [])
        print(f"✅ 豆瓣{config['msg']}获取成功: {len(items)} 部")
        return items
        
    except requests.RequestException as e:
        print(f"❌ 豆瓣 API 请求失败: {e}")
        return []
    except Exception as e:
        print(f"❌ 豆瓣数据解析失败: {e}")
        return []


def match_local_vod(cursor, douban_items):
    """
    将豆瓣影片与本地数据库匹配（优化版：批量查询）
    
    Args:
        cursor: 数据库游标
        douban_items: 豆瓣返回的影片列表
        
    Returns:
        list: 匹配到的本地 vod 列表，保持原始热度排序
    """
    # Phase 1: Collect all vod_ids with their ranks (fast matching phase)
    matched_ids = []  # [(vod_id, rank, title), ...]
    
    for rank, item in enumerate(douban_items, 1):
        title = item.get('title', '').strip()
        if not title:
            continue
        
        # 精确匹配
        cursor.execute("SELECT vod_id FROM sc_vod WHERE vod_name = ? LIMIT 1", (title,))
        result = cursor.fetchone()
        
        # 如果精确匹配失败，尝试模糊匹配（去掉季数等后缀）
        if not result:
            # 例如："曼哈顿金牌经纪 第二季" -> 尝试匹配 "曼哈顿金牌经纪%"
            base_title = title.split(' 第')[0].strip()
            if base_title != title:
                cursor.execute("SELECT vod_id FROM sc_vod WHERE vod_name LIKE ? LIMIT 1", (f"{base_title}%",))
                result = cursor.fetchone()
        
        if result:
            vod_id = str(result['vod_id'])
            matched_ids.append((vod_id, rank, title))
            print(f"  ✓ [{rank}] {title} -> vod_id={vod_id}")
        else:
            print(f"  ✗ [{rank}] {title} (未匹配)")
    
    if not matched_ids:
        return []
    
    # Phase 2: Batch fetch all vod details in ONE query
    vod_ids = [m[0] for m in matched_ids]
    vod_details_list = fetch_vod_details(cursor, vod_ids)
    
    # Build lookup map: vod_id -> vod_details
    vod_map = {str(v['vod_id']): v for v in vod_details_list}
    
    # Phase 3: Reconstruct ordered list with hot_rank
    matched_vods = []
    for vod_id, rank, title in matched_ids:
        if vod_id in vod_map:
            vod = vod_map[vod_id].copy()
            vod['hot_rank'] = rank
            matched_vods.append(vod)
    
    return matched_vods


def handle_hot_action(cursor, request):
    """
    处理热搜请求
    
    Args:
        cursor: 数据库游标
        request: Flask 请求对象
        
    Returns:
        Flask JSON 响应
    """
    import json
    from flask import Response
    
    hot_type = request.args.get('hot', 'movie')
    
    if hot_type not in HOT_TYPE_CONFIG:
        return jsonify({
            'code': 0,
            'msg': f'无效的热搜类型: {hot_type}，支持: movie/newmovie/tv/show'
        }), 400
    
    config = HOT_TYPE_CONFIG[hot_type]
    now = time.time()
    
    # 检查缓存
    if hot_type in hot_cache:
        cache_entry = hot_cache[hot_type]
        cache_age = now - cache_entry['timestamp']
        if cache_age < HOT_CACHE_DURATION:
            print(f"📦 使用缓存: {config['msg']} (剩余 {int((HOT_CACHE_DURATION - cache_age) / 3600)} 小时)")
            vod_list = cache_entry['matched_vods']
            
            response = {
                'code': 1,
                'msg': config['msg'],
                'page': 1,
                'pagecount': 1,
                'limit': len(vod_list),
                'total': len(vod_list),
                'list': vod_list,
                'cache': True,
                'cache_age_hours': round(cache_age / 3600, 1)
            }
            
            return Response(
                json.dumps(response, ensure_ascii=False),
                mimetype='application/json'
            )
    
    # 缓存过期或不存在，重新请求
    print(f"🔄 请求豆瓣 API: {config['msg']}")
    douban_items = fetch_douban_hot(hot_type)
    
    if not douban_items:
        return jsonify({
            'code': 0,
            'msg': f'无法获取{config["msg"]}数据'
        }), 500
    
    # 匹配本地数据库
    print(f"🔍 开始匹配本地数据库...")
    matched_vods = match_local_vod(cursor, douban_items)
    
    # 更新缓存
    hot_cache[hot_type] = {
        'douban_items': douban_items,
        'matched_vods': matched_vods,
        'timestamp': now
    }
    print(f"💾 缓存已更新: {config['msg']} ({len(matched_vods)}/{len(douban_items)} 匹配)")
    
    # 构建响应
    response = {
        'code': 1,
        'msg': config['msg'],
        'page': 1,
        'pagecount': 1,
        'limit': len(matched_vods),
        'total': len(matched_vods),
        'list': matched_vods,
        'cache': False,
        'douban_total': len(douban_items)
    }
    
    return Response(
        json.dumps(response, ensure_ascii=False),
        mimetype='application/json'
    )


# ============================================================
# 应用更新相关接口
# ============================================================

# 应用版本配置文件路径
APP_VERSION_CONFIG = os.path.join(os.path.dirname(__file__), 'app_version.json')
# APK文件存放目录
RELEASES_DIR = os.path.join(os.path.dirname(__file__), 'releases')

def get_app_version_config():
    """
    读取应用版本配置
    如果配置文件不存在，返回默认配置
    """
    default_config = {
        "HBbb": "2.0",  # 当前最新版本号
        "HBnr": "暂无更新",  # 更新内容说明
        "HBxz": "",  # APK下载地址（空表示无更新）
        "HBgg": "",  # 滚动公告文字
        "force_update": False  # 是否强制更新
    }
    
    if os.path.exists(APP_VERSION_CONFIG):
        try:
            import json
            with open(APP_VERSION_CONFIG, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 合并默认配置，确保所有字段都存在
                return {**default_config, **config}
        except Exception as e:
            print(f"⚠️ 读取版本配置失败: {e}")
    
    return default_config

@app.route('/app/version', methods=['GET'])
def app_version():
    """
    应用版本检查接口
    
    返回格式与 Android 应用的 BaseDataBean 兼容：
    - HBbb: 最新版本号（用于比较，如 "2.1"）
    - HBnr: 更新内容说明
    - HBxz: APK下载地址
    - force_update: 是否强制更新（可选）
    
    使用方法：
    1. 创建 app_version.json 配置文件
    2. 将 APK 放入 releases/ 目录
    3. 在配置中设置 HBxz 为下载地址
    
    示例配置 (app_version.json):
    {
        "HBbb": "2.1",
        "HBnr": "1. 修复了播放问题\\n2. 优化了搜索功能",
        "HBxz": "http://your-server:5000/releases/SMTVPlus-2.1-release.apk",
        "force_update": false
    }
    """
    config = get_app_version_config()
    
    import json
    from flask import Response
    
    # 返回与 peizhijson.php 格式兼容的响应
    # Android 应用期望的格式是: "某前缀" + JSON
    # 原始格式: result.trim().substring(2) 表示去掉前两个字符
    # 所以我们返回 "0," + JSON 以保持兼容性
    response_data = json.dumps(config, ensure_ascii=False)
    
    return Response(
        f"0,{response_data}",
        mimetype='application/json'
    )

@app.route('/app/version/json', methods=['GET'])
def app_version_json():
    """
    纯 JSON 格式的版本检查接口（用于调试和直接访问）
    """
    config = get_app_version_config()
    
    import json
    from flask import Response
    return Response(
        json.dumps(config, ensure_ascii=False),
        mimetype='application/json'
    )

@app.route('/releases/<filename>', methods=['GET'])
def serve_release(filename):
    """
    提供 APK 文件下载
    
    文件应放在 releases/ 目录下
    """
    from flask import send_from_directory, abort
    
    # 安全检查：只允许 .apk 文件
    if not filename.endswith('.apk'):
        abort(403, 'Only APK files are allowed')
    
    # 检查目录是否存在
    if not os.path.exists(RELEASES_DIR):
        os.makedirs(RELEASES_DIR)
        abort(404, f'No releases found. Please place APK files in {RELEASES_DIR}')
    
    # 检查文件是否存在
    filepath = os.path.join(RELEASES_DIR, filename)
    if not os.path.exists(filepath):
        abort(404, f'Release file not found: {filename}')
    
    return send_from_directory(RELEASES_DIR, filename, as_attachment=True)

@app.route('/releases/', methods=['GET'])
def list_releases():
    """
    列出所有可用的 APK 版本
    """
    releases = []
    
    if os.path.exists(RELEASES_DIR):
        for filename in os.listdir(RELEASES_DIR):
            if filename.endswith('.apk'):
                filepath = os.path.join(RELEASES_DIR, filename)
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                releases.append({
                    'filename': filename,
                    'size_mb': round(size_mb, 2),
                    'download_url': f'/releases/{filename}'
                })
    
    import json
    from flask import Response
    return Response(
        json.dumps({
            'releases': releases,
            'releases_dir': RELEASES_DIR,
            'current_version': get_app_version_config()
        }, ensure_ascii=False),
        mimetype='application/json'
    )

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'service': 'StreamCore API',
        'version': '1.0.0'
    })

@app.route('/', methods=['GET'])
def index():
    """首页，显示 API 使用说明"""
    help_text = """
    🎬 StreamCore API 服务
    
    MacCMS V10 兼容的资源采集接口
    
    📖 接口文档：
    
    1. 列表接口
       GET /api.php/provide/vod/?ac=list
       
       参数：
       - t: 分类 ID（可选，逗号分隔多个）
       - pg: 页码（默认 1）
       - h: 小时内更新（可选）
       
       示例：
       /api.php/provide/vod/?ac=list&t=1&pg=1
       /api.php/provide/vod/?ac=list&h=24
    
    2. 详情接口
       GET /api.php/provide/vod/?ac=detail
       
       参数：
       - ids: 影片 ID（逗号分隔）
       - wd: 智能搜索（关键词 或 首字母）
       - pg: 页码（用于首字母搜索分页）
       
       示例：
       /api.php/provide/vod/?ac=detail&ids=1,2,3
       /api.php/provide/vod/?ac=detail&wd=复仇者联盟  (关键词搜索)
       /api.php/provide/vod/?ac=detail&wd=A         (首字母搜索)
       /api.php/provide/vod/?ac=detail&wd=#&pg=2   (数字开头)
    
    3. 健康检查
       GET /health
    
    💡 更多信息请访问项目文档
    """
    
    return f"<pre>{help_text}</pre>"

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 StreamCore API 服务启动")
    print("=" * 70)
    print(f"📊 主数据库文件: {MAIN_DB}")
    print(f"🌐 API 端点: http://0.0.0.0:5000/api.php/provide/vod/")
    print(f"💚 健康检查: http://0.0.0.0:5000/health")
    print("=" * 70)
    print()
    
    app.run(host='0.0.0.0', port=5000, debug=True)
