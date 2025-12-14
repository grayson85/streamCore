# setup.py
# StreamCore CLI 配置工具
# 用于初始化数据库、配置资源站和分类映射

import sys
import json
import sqlite3
import requests
from db_config import (
    init_db, get_db_connection, create_initial_types,
    MAIN_DB, TEMP_DB, get_all_types, get_all_sources
)

def fetch_remote_types(source):
    """
    从资源站 API 获取远程分类列表
    
    Args:
        source: 资源站配置
        
    Returns:
        dict: {type_id: type_name} 字典，失败返回空字典
    """
    try:
        # 构造 API URL，获取分类列表
        # MacCMS V10 标准：使用 ac=list 请求会返回 class 字段包含所有分类
        url = source['res_url']
        separator = '&' if '?' in url else '?'
        full_url = f"{url}{separator}ac=list"
        
        print(f"\n🌐 正在从资源站获取分类列表...")
        print(f"   请求: {full_url}")
        
        response = requests.get(full_url, timeout=15)
        response.raise_for_status()
        
        if source['data_format'] == 'json':
            data = response.json()
            
            # 检查响应
            if data.get('code') != 1:
                print(f"   ⚠️  API 返回错误: {data.get('msg', '未知错误')}")
                return {}
            
            # MacCMS V10 标准：从 'class' 字段获取分类列表
            class_list = data.get('class', [])
            
            if not class_list:
                print(f"   ⚠️  API 响应中没有 'class' 字段，尝试从影片列表提取...")
                # 备用方案：从影片列表中提取分类
                type_dict = {}
                vod_list = data.get('list', [])
                for vod in vod_list:
                    type_id = str(vod.get('type_id', ''))
                    type_name = vod.get('type_name', f'分类{type_id}')
                    if type_id and type_id not in type_dict:
                        type_dict[type_id] = type_name
                
                if type_dict:
                    print(f"   ✅ 从影片列表提取到 {len(type_dict)} 个分类")
                    return type_dict
                else:
                    print(f"   ❌ 未能获取任何分类信息")
                    return {}
            
            # 从 class 字段解析分类
            type_dict = {}
            for cls in class_list:
                type_id = str(cls.get('type_id', ''))
                type_name = cls.get('type_name', f'分类{type_id}')
                
                if type_id:
                    type_dict[type_id] = type_name
            
            print(f"   ✅ 成功获取 {len(type_dict)} 个分类（来自 class 字段）")
            return type_dict
            
        else:
            print(f"   ⚠️  暂不支持 {source['data_format']} 格式")
            return {}
            
    except requests.exceptions.Timeout:
        print(f"   ❌ 请求超时（15秒）")
        return {}
    except requests.exceptions.RequestException as e:
        print(f"   ⚠️  网络请求失败: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"   ❌ JSON 解析失败: {e}")
        return {}
    except Exception as e:
        print(f"   ⚠️  获取分类失败: {e}")
        return {}

def cmd_reset():
    """完全重置数据库 - 删除并重建"""
    print("=" * 70)
    print("⚠️  重置数据库（删除所有数据）")
    print("=" * 70)
    
    print("\n此操作将：")
    print("  - 删除所有数据库文件")
    print("  - 重新创建数据库")
    print("  - 创建初始分类")
    print("\n⚠️  所有数据将永久丢失！")
    
    confirm = input("\n确认重置？(yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("\n❌ 操作已取消")
        return
    
    import os
    
    # 删除数据库文件
    for db_file in [MAIN_DB, TEMP_DB]:
        if os.path.exists(db_file):
            os.remove(db_file)
            print(f"✅ 已删除 {db_file}")
    
    # 重新初始化
    print("\n重新初始化...")
    cmd_init()

def cmd_init():
    """初始化 StreamCore 项目"""
    print("=" * 60)
    print("🚀 StreamCore 项目初始化")
    print("=" * 60)
    
    # 初始化主数据库
    print("\n1️⃣  初始化主数据库 (sc_main.db)...")
    init_db(MAIN_DB)
    
    # 初始化临时数据库
    print("\n2️⃣  初始化临时数据库 (sc_temp.db)...")
    init_db(TEMP_DB)
    
    # 创建初始分类
    print("\n3️⃣  创建初始分类...")
    conn = get_db_connection(MAIN_DB)
    create_initial_types(conn)
    
    # 同步到临时数据库
    temp_conn = get_db_connection(TEMP_DB)
    create_initial_types(temp_conn)
    
    conn.close()
    temp_conn.close()
    
    print("\n" + "=" * 60)
    print("✅ StreamCore 项目初始化完成！")
    print("=" * 60)
    print("\n📖 下一步操作：")
    print("   1. 使用 'python setup.py add-source' 添加资源站")
    print("   2. 使用 'python setup.py setup-categories --source <前缀>' 配置分类")
    print("   3. 使用 'python collector.py' 执行数据采集")
    print("   4. 使用 'python app.py' 启动 API 服务")
    print()

def cmd_add_source():
    """交互式添加资源站配置"""
    print("=" * 70)
    print("➕ 添加资源站配置")
    print("=" * 70)
    
    # 交互式输入
    print("\n请输入资源站信息：")
    res_name = input("📌 资源站友好名称 (如: 无尽资源): ").strip()
    if not res_name:
        print("❌ 资源站名称不能为空！")
        return
    
    res_url = input("🌐 API 接口地址 (如: https://api.example.com/api.php/provide/vod/): ").strip()
    if not res_url:
        print("❌ API URL 不能为空！")
        return
    
    data_format = input("📄 数据格式 (json/xml) [默认: json]: ").strip().lower()
    if not data_format:
        data_format = 'json'
    
    if data_format not in ['json', 'xml']:
        print("❌ 数据格式必须是 json 或 xml！")
        return
    
    operation_mode = input("⚙️  数据操作模式 (add_update/add/update) [默认: add_update]: ").strip().lower()
    if not operation_mode:
        operation_mode = 'add_update'
    
    if operation_mode not in ['add_update', 'add', 'update']:
        print("❌ 操作模式必须是 add_update, add 或 update！")
        return
    
    res_id_prefix = input("🔖 资源站 ID 前缀 (用于生成唯一 ID，如: wj_): ").strip()
    if not res_id_prefix:
        print("❌ ID 前缀不能为空！")
        return
    
    # 插入数据库
    conn = get_db_connection(MAIN_DB)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO sc_config (res_name, res_url, data_format, res_id_prefix, res_mapping, operation_mode)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (res_name, res_url, data_format, res_id_prefix, '{}', operation_mode))
        conn.commit()
        
        res_source_id = cursor.lastrowid
        
        print("\n" + "=" * 70)
        print(f"✅ 资源站添加成功！资源站 ID: {res_source_id}")
        print("=" * 70)
        print(f"\n📝 资源站信息：")
        print(f"   名称: {res_name}")
        print(f"   URL: {res_url}")
        print(f"   格式: {data_format}")
        print(f"   操作模式: {operation_mode}")
        print(f"   前缀: {res_id_prefix}")
        
        # 操作模式说明
        print(f"\n💡 操作模式说明：")
        if operation_mode == 'add_update':
            print(f"   - 添加新数据并更新已存在的数据（推荐）")
        elif operation_mode == 'add':
            print(f"   - 只添加新数据，不更新已存在的")
        elif operation_mode == 'update':
            print(f"   - 只更新已存在的数据，不添加新的")
        
        print(f"\n💡 下一步：使用 'python setup.py setup-categories --source {res_id_prefix}' 配置分类")
        print()
        
    except sqlite3.IntegrityError as e:
        print(f"\n❌ 添加失败：ID 前缀 '{res_id_prefix}' 已存在！")
    except Exception as e:
        print(f"\n❌ 添加失败：{e}")
    finally:
        conn.close()

def cmd_delete_source(source_identifier):
    """删除资源站配置"""
    print("=" * 70)
    print("🗑️  删除资源站配置")
    print("=" * 70)
    
    conn = get_db_connection(MAIN_DB)
    cursor = conn.cursor()
    
    # 查找资源站 (通过ID或前缀)
    try:
        source_id = int(source_identifier)
        cursor.execute("SELECT * FROM sc_config WHERE res_source_id = ?", (source_id,))
    except ValueError:
        cursor.execute("SELECT * FROM sc_config WHERE res_id_prefix = ?", (source_identifier,))
    
    source = cursor.fetchone()
    if not source:
        print(f"\n❌ 未找到资源站：{source_identifier}")
        conn.close()
        return
    
    print(f"\n📌 将要删除的资源站：")
    print(f"   ID: {source['res_source_id']}")
    print(f"   名称: {source['res_name']}")
    print(f"   URL: {source['res_url']}")
    print(f"   前缀: {source['res_id_prefix']}")
    
    # 统计关联数据
    cursor.execute("SELECT COUNT(*) FROM sc_vod WHERE res_source_id = ?", (source['res_source_id'],))
    vod_count = cursor.fetchone()[0]
    
    print(f"\n⚠️  警告：")
    print(f"   - 将删除资源站配置")
    print(f"   - 将删除关联的 {vod_count} 条视频数据")
    print(f"   - 此操作不可恢复！")
    
    # 确认操作
    confirm = input(f"\n确认删除？请输入资源站前缀 '{source['res_id_prefix']}' 以确认: ").strip()
    
    if confirm != source['res_id_prefix']:
        print("\n❌ 确认失败，操作已取消")
        conn.close()
        return
    
    try:
        # 删除关联的视频数据
        cursor.execute("DELETE FROM sc_vod WHERE res_source_id = ?", (source['res_source_id'],))
        deleted_vod = cursor.rowcount
        
        # 删除关联的搜索数据 (孤立的记录)
        cursor.execute("""
            DELETE FROM sc_search 
            WHERE vod_id NOT IN (SELECT vod_id FROM sc_vod)
        """)
        deleted_search = cursor.rowcount
        
        # 删除资源站配置
        cursor.execute("DELETE FROM sc_config WHERE res_source_id = ?", (source['res_source_id'],))
        
        conn.commit()
        
        print("\n" + "=" * 70)
        print("✅ 删除成功")
        print("=" * 70)
        print(f"   删除资源站: {source['res_name']}")
        print(f"   删除视频数据: {deleted_vod} 条")
        print(f"   清理搜索数据: {deleted_search} 条")
        
        # 同步到临时数据库
        import shutil
        shutil.copy2(MAIN_DB, TEMP_DB)
        print(f"\n✅ 已同步到 {TEMP_DB}")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ 删除失败：{e}")
    finally:
        conn.close()

def auto_map_by_name(remote_types, cursor, existing_mapping=None):
    """
    自动按名称匹配远程分类到本地L2分类
    
    只匹配L2子分类（type_pid != 0），不匹配L1父分类
    
    Args:
        remote_types: dict, {remote_type_id: type_name}
        cursor: 数据库游标
        existing_mapping: dict, 现有映射（可选）
        
    Returns:
        tuple: (auto_mapped, unmatched)
            - auto_mapped: dict, {remote_type_id: local_type_id}
            - unmatched: dict, {remote_type_id: type_name}
    """
    if existing_mapping is None:
        existing_mapping = {}
    
    auto_mapped = {}
    unmatched = {}
    
    # 只获取L2本地分类（type_pid != 0）
    cursor.execute("SELECT type_id, type_name, type_pid FROM sc_type WHERE type_pid != 0 ORDER BY type_id")
    local_types = cursor.fetchall()
    
    # 构建本地L2分类名称索引 (name -> type_id)
    # 同名L2取第一个
    local_name_index = {}
    for lt in local_types:
        name_lower = lt['type_name'].strip().lower()
        if name_lower not in local_name_index:
            local_name_index[name_lower] = lt['type_id']
    
    for rid, rname in remote_types.items():
        # 跳过已映射的
        if rid in existing_mapping:
            continue
        
        rname_lower = rname.strip().lower()
        
        if rname_lower in local_name_index:
            auto_mapped[rid] = local_name_index[rname_lower]
        else:
            unmatched[rid] = rname
    
    return auto_mapped, unmatched


def cmd_setup_categories(source_identifier):
    """
    一站式分类配置 - 两轮流程
    第一轮：选择L1父分类
    第二轮：配置L2子分类并选择父分类
    """    
    print("=" * 70)
    print("🎯 一站式分类配置")
    print("=" * 70)
    
    conn = get_db_connection(MAIN_DB)
    cursor = conn.cursor()
    
    # 1. 查找资源站
    try:
        source_id = int(source_identifier)
        cursor.execute("SELECT * FROM sc_config WHERE res_source_id = ?", (source_id,))
    except ValueError:
        cursor.execute("SELECT * FROM sc_config WHERE res_id_prefix = ?", (source_identifier,))
    
    source = cursor.fetchone()
    if not source:
        print(f"❌ 未找到资源站：{source_identifier}")
        conn.close()
        return
    
    print(f"\n📌 资源站：{source['res_name']} ({source['res_id_prefix']})")
    
    # 2. 获取远程分类
    print("\n" + "=" * 70)
    remote_types = fetch_remote_types(source)
    
    if not remote_types:
        print("\n❌ 无法获取远程分类列表")
        conn.close()
        return
    
    print(f"✅ 成功获取 {len(remote_types)} 个远程分类")
    
    # 3. 检查现有分类并询问模式
    print("\n" + "=" * 70)
    cursor.execute("SELECT COUNT(*) FROM sc_type")
    existing_count = cursor.fetchone()[0]
    
    if existing_count > 0:
        print(f"📊 当前本地分类：{existing_count} 个")
        
        # 加载现有映射
        existing_mapping = {}
        if source['res_mapping']:
            try:
                existing_mapping = json.loads(source['res_mapping'])
            except:
                pass
        
        print(f"📊 当前映射数量：{len(existing_mapping)} 条")
        
        print("\n选择操作模式：")
        print("  [1] 增量添加 - 添加遗漏的分类（推荐）")
        print("  [2] 重新创建 - 清空并重新配置")
        
        mode = input("\n→ 选择模式 [1/2，默认:1]: ").strip() or '1'
        
        if mode == '2':
            # 重新创建模式
            confirm = input("\n⚠️  确认清空所有分类和映射？(yes/no): ").strip().lower()
            
            if confirm != 'yes':
                print("\n❌ 已取消")
                conn.close()
                return
            
            cursor.execute("DELETE FROM sc_type")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='sc_type'")
            cursor.execute("UPDATE sc_config SET res_mapping = '{}' WHERE res_source_id = ?", 
                           (source['res_source_id'],))
            conn.commit()
            print("✅ 已清空本地分类和映射")
            
            # 使用原来的全新创建流程
            incremental_mode = False
            current_mapping = {}
            existing_l1 = []
        else:
            # 增量添加模式
            print("\n✅ 使用增量添加模式")
            incremental_mode = True
            current_mapping = existing_mapping.copy()
            
            # 获取现有L1分类
            cursor.execute("SELECT type_id, type_name FROM sc_type WHERE type_pid = 0 ORDER BY type_id")
            existing_l1 = cursor.fetchall()
            
            print("\n现有L1分类：")
            for l1 in existing_l1:
                print(f"   [{l1['type_id']}] {l1['type_name']}")
    else:
        # 没有现有分类，直接全新创建
        print("📝 首次配置")
        incremental_mode = False
        current_mapping = {}
        existing_l1 = []
    
    # ========== 自动映射选项 ==========
    print("\n" + "=" * 70)
    print("🔄 自动映射选项")
    print("=" * 70)
    
    auto_mapped = {}
    
    # 计算可自动映射的数量
    test_auto_mapped, test_unmatched = auto_map_by_name(remote_types, cursor, current_mapping)
    
    if test_auto_mapped:
        print(f"\n📊 检测到 {len(test_auto_mapped)} 个远程分类可自动映射到本地L2分类（同名匹配）")
        print(f"   剩余 {len(test_unmatched)} 个需要手动配置")
        
        use_auto = input("\n→ 使用自动映射？(y/n) [默认:y]: ").strip().lower()
        
        if use_auto != 'n':
            print("\n✨ 自动映射结果：")
            
            for rid in sorted(test_auto_mapped.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                local_id = test_auto_mapped[rid]
                rname = remote_types[rid]
                cursor.execute("SELECT type_name FROM sc_type WHERE type_id = ?", (local_id,))
                local_type = cursor.fetchone()
                local_name = local_type['type_name'] if local_type else f'ID:{local_id}'
                print(f"   [{rid:3s}] {rname:20s} → L2[{local_id:2d}] {local_name}")
            
            auto_mapped = test_auto_mapped
            current_mapping.update(auto_mapped)
            print(f"\n✅ 已自动映射 {len(auto_mapped)} 个分类")
            
            if not test_unmatched:
                print("\n🎉 所有分类已映射完成，无需手动配置！")
                
                # 直接保存并退出
                mapping_json = json.dumps(current_mapping, ensure_ascii=False)
                cursor.execute("UPDATE sc_config SET res_mapping = ? WHERE res_source_id = ?",
                               (mapping_json, source['res_source_id']))
                conn.commit()
                
                # 显示最终结构
                print("\n" + "=" * 70)
                print("📋 最终结构")
                print("=" * 70)
                
                cursor.execute("SELECT type_id, type_name FROM sc_type WHERE type_pid = 0 ORDER BY type_id")
                for l1 in cursor.fetchall():
                    print(f"\n📁 [{l1['type_id']}] {l1['type_name']}")
                    
                    cursor.execute("SELECT type_id, type_name FROM sc_type WHERE type_pid = ? ORDER BY type_id", (l1['type_id'],))
                    for l2 in cursor.fetchall():
                        print(f"   └── [{l2['type_id']:2d}] {l2['type_name']}")
                
                conn.close()
                
                # 同步
                import shutil
                shutil.copy2(MAIN_DB, TEMP_DB)
                
                print("\n" + "=" * 70)
                print("🎉 配置完成！")
                print("=" * 70)
                print(f"\n   总映射: {len(current_mapping)} 条")
                print("\n💡 下一步：python collector.py")
                return
            else:
                print(f"\n📋 剩余 {len(test_unmatched)} 个未匹配分类需要手动配置：")
                for rid, rname in sorted(test_unmatched.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999):
                    print(f"   [{rid:3s}] {rname}")
        else:
            print("\n⏭️  跳过自动映射，进入手动配置模式")
    else:
        print("\n📊 未检测到可自动映射的L2分类（无同名匹配）")
        print("   将进入手动配置模式")
    
    # ========== 第一轮：L1父分类 ==========
    print("\n" + "=" * 70)
    print("📁 第一轮：配置L1父分类")
    print("=" * 70)
    
    print(f"\n共 {len(remote_types)} 个远程分类：")
    
    # 标记已映射的远程分类
    mapped_remote_ids = set(current_mapping.keys())
    
    for rid, rname in sorted(remote_types.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999):
        if rid in mapped_remote_ids:
            local_id = current_mapping[rid]
            cursor.execute("SELECT type_name FROM sc_type WHERE type_id = ?", (local_id,))
            local_type = cursor.fetchone()
            local_name = local_type['type_name'] if local_type else f'ID:{local_id}'
            print(f"   [{rid:3s}] {rname:20s} (已映射 → {local_id} {local_name})")
        else:
            print(f"   [{rid:3s}] {rname}")
    
    if incremental_mode:
        print("\n💡 选择要添加的L1父分类（已映射的会跳过）")
        print("   留空跳过此步骤")
    else:
        print("\n💡 选择哪些作为L1父分类")
    
    print("   示例：1,2,3,4,5")
    
    l1_input = input("\n→ 远程ID (逗号分隔): ").strip()
    
    l1_mapping = {}
    l1_created = existing_l1.copy() if incremental_mode else []
    
    if l1_input:
        l1_remote_ids = [id.strip() for id in l1_input.split(',')]
        
        print("\n创建L1：")
        for rid in l1_remote_ids:
            if rid not in remote_types:
                print(f"  ⚠️  跳过：远程ID {rid} 不存在")
                continue
            
            # 如果已映射，跳过
            if rid in mapped_remote_ids:
                print(f"  ⏭️  跳过：远程{rid} 已映射")
                continue
            
            rname = remote_types[rid]
            lname = input(f"\n[{rid}] {rname}\n  → 本地名称 [默认:{rname}]: ").strip() or rname
            
            # 检查是否存在相同名称的L1分类
            cursor.execute("SELECT type_id FROM sc_type WHERE type_name = ? AND type_pid = 0", (lname,))
            existing = cursor.fetchone()
            
            if existing:
                lid = existing['type_id']
                print(f"  ♻️  复用现有分类 → 本地L1[{lid}] {lname}")
            else:
                cursor.execute("INSERT INTO sc_type (type_name, type_pid) VALUES (?, 0)", (lname,))
                conn.commit()
                lid = cursor.lastrowid
                print(f"  ✅ 创建新分类 → 本地L1[{lid}] {lname}")
            
            l1_mapping[rid] = lid
            l1_created.append({'type_id': lid, 'type_name': lname})
        
        if l1_mapping:
            print(f"\n✅ 新创建 {len(l1_mapping)} 个L1")
    
    # ========== 第二轮：L2子分类 ==========
    print("\n" + "=" * 70)
    print("📂 第二轮：配置L2子分类")
    print("=" * 70)
    
    # 计算剩余未映射的远程分类
    all_mapped = set(current_mapping.keys()) | set(l1_mapping.keys())
    remaining = {k: v for k, v in remote_types.items() if k not in all_mapped}
    
    if not remaining:
        print("\n✅ 所有远程分类都已映射")
    else:
        print(f"\n剩余 {len(remaining)} 个未映射：")
        
        print("\n可选父分类：")
        for l1 in l1_created:
            if isinstance(l1, dict):
                print(f"   [{l1['type_id']}] {l1['type_name']}")
            else:
                print(f"   [{l1['type_id']}] {l1['type_name']}")

        
        print("\n💡 为每个远程分类选择父分类")
        print("   's'=跳过  'q'=完成")
        
        l2_mapping = {}
        l2_count = 0
        
        for rid, rname in sorted(remaining.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999):
            print(f"\n┌─ [{rid}] {rname}")
            
            pid_input = input("│  → 父分类ID [s/q]: ").strip().lower()
            
            if pid_input == 'q':
                print("│  ⏹️  结束")
                break
            
            if pid_input == 's' or not pid_input:
                print("│  ⏭️  跳过")
                continue
            
            try:
                pid = int(pid_input)
                
                cursor.execute("SELECT type_name FROM sc_type WHERE type_id = ? AND type_pid = 0", (pid,))
                parent = cursor.fetchone()
                
                if not parent:
                    print(f"│  ❌ ID{pid}不存在")
                    continue
                
                lname = input(f"│  → 名称 [默认:{rname}]: ").strip() or rname
                
                # 检查是否存在相同名称和父分类的L2分类
                cursor.execute("SELECT type_id FROM sc_type WHERE type_name = ? AND type_pid = ?", (lname, pid))
                existing = cursor.fetchone()
                
                if existing:
                    lid = existing['type_id']
                    print(f"│  ♻️  复用现有分类 → L2[{lid}] {lname} (父:{pid})")
                else:
                    cursor.execute("INSERT INTO sc_type (type_name, type_pid) VALUES (?, ?)", (lname, pid))
                    conn.commit()
                    lid = cursor.lastrowid
                    print(f"│  ✅ 创建新分类 → L2[{lid}] {lname} (父:{pid})")
                
                l2_mapping[rid] = lid
                l2_count += 1
                
            except ValueError:
                print("│  ❌ 无效")
        
        print(f"\n✅ 创建 {l2_count} 个L2")
    
    # ========== 保存映射 ==========
    # 合并映射：保留现有 + 新增L1 + 新增L2
    all_mapping = {**current_mapping, **l1_mapping, **l2_mapping}
    
    mapping_json = json.dumps(all_mapping, ensure_ascii=False)
    cursor.execute("UPDATE sc_config SET res_mapping = ? WHERE res_source_id = ?",
                   (mapping_json, source['res_source_id']))
    conn.commit()
    
    print("\n" + "=" * 70)
    print("💾 映射已保存")
    print("=" * 70)
    if incremental_mode:
        print(f"   现有映射: {len(current_mapping) - len(auto_mapped)} 条")
    if auto_mapped:
        print(f"   自动映射: {len(auto_mapped)} 条")
    print(f"   新增L1: {len(l1_mapping)} 条")
    print(f"   新增L2: {len(l2_mapping)} 条")
    print(f"   总计: {len(all_mapping)} 条")

    
    # 显示结构
    print("\n" + "=" * 70)
    print("📋 最终结构")
    print("=" * 70)
    
    cursor.execute("SELECT type_id, type_name FROM sc_type WHERE type_pid = 0 ORDER BY type_id")
    for l1 in cursor.fetchall():
        print(f"\n📁 [{l1['type_id']}] {l1['type_name']}")
        
        cursor.execute("SELECT type_id, type_name FROM sc_type WHERE type_pid = ? ORDER BY type_id", (l1['type_id'],))
        for l2 in cursor.fetchall():
            print(f"   └── [{l2['type_id']:2d}] {l2['type_name']}")
    
    conn.close()
    
    # 同步
    import shutil
    shutil.copy2(MAIN_DB, TEMP_DB)
    
    print("\n" + "=" * 70)
    print("🎉 配置完成！")
    print("=" * 70)
    print("\n💡 下一步：python collector.py")



def cmd_create_local_type():
    """创建新的本地分类"""
    print("=" * 60)
    print("📁 创建本地分类")
    print("=" * 60)
    
    conn = get_db_connection(MAIN_DB)
    
    # 显示现有分类
    print("\n📂 现有分类：")
    types = get_all_types(conn)
    for t in types:
        indent = "   " if t['type_pid'] != 0 else ""
        print(f"{indent}[{t['type_id']}] {t['type_name']}")
    
    # 交互式输入
    print("\n请输入新分类信息：")
    type_name = input("📌 分类名称: ").strip()
    if not type_name:
        print("❌ 分类名称不能为空！")
        conn.close()
        return
    
    type_pid_input = input("📂 父分类 ID (0 表示顶级分类) [默认: 0]: ").strip()
    type_pid = int(type_pid_input) if type_pid_input else 0
    
    # 插入数据库
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO sc_type (type_name, type_pid) VALUES (?, ?)
        """, (type_name, type_pid))
        conn.commit()
        
        new_type_id = cursor.lastrowid
        
        print("\n" + "=" * 60)
        print(f"✅ 分类创建成功！分类 ID: {new_type_id}")
        print("=" * 60)
        print(f"   名称: {type_name}")
        print(f"   父分类: {type_pid}")
        print()
        
    except Exception as e:
        print(f"\n❌ 创建失败：{e}")
    finally:
        conn.close()

def cmd_clear_mapping(source_identifier):
    """清空资源站的分类映射"""
    print("=" * 70)
    print("🗑️  清空分类映射")
    print("=" * 70)
    
    conn = get_db_connection(MAIN_DB)
    cursor = conn.cursor()
    
    # 查找资源站
    try:
        source_id = int(source_identifier)
        cursor.execute("SELECT * FROM sc_config WHERE res_source_id = ?", (source_id,))
    except ValueError:
        cursor.execute("SELECT * FROM sc_config WHERE res_id_prefix = ?", (source_identifier,))
    
    source = cursor.fetchone()
    if not source:
        print(f"❌ 未找到资源站：{source_identifier}")
        conn.close()
        return
    
    print(f"\n📌 资源站：{source['res_name']} ({source['res_id_prefix']})")
    
    # 获取当前映射数量
    current_mapping = {}
    if source['res_mapping']:
        try:
            current_mapping = json.loads(source['res_mapping'])
        except:
            pass
    
    if not current_mapping:
        print(f"\n⚠️  该资源站当前没有任何映射，无需清空")
        conn.close()
        return
    
    print(f"\n📊 当前映射数量：{len(current_mapping)} 条")
    
    # 确认操作
    confirm = input(f"\n⚠️  确认清空所有映射？此操作不可恢复！(yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("\n❌ 操作已取消")
        conn.close()
        return
    
    # 清空映射
    cursor.execute("UPDATE sc_config SET res_mapping = ? WHERE res_source_id = ?", 
                   ('{}', source['res_source_id']))
    conn.commit()
    
    print("\n✅ 分类映射已清空")
    print(f"📊 清空数量：{len(current_mapping)} 条")
    
    conn.close()
    
    # 同步到临时数据库
    import shutil
    shutil.copy2(MAIN_DB, TEMP_DB)
    print(f"✅ 已同步到 {TEMP_DB}")
    
    print(f"\n💡 提示：使用 'python setup.py map-source-types --source {source['res_id_prefix']}' 重新配置映射")
    print("=" * 70)

def cmd_list_config():
    """列出所有配置"""
    print("=" * 70)
    print("📋 StreamCore 配置概览")
    print("=" * 70)
    
    conn = get_db_connection(MAIN_DB)
    cursor = conn.cursor()
    
    # 显示分类（树状结构）
    print("\n📂 本地分类（L1 → L2 树状结构）：")
    
    # 获取所有 L1 分类
    cursor.execute("SELECT type_id, type_name FROM sc_type WHERE type_pid = 0 ORDER BY type_id")
    l1_categories = cursor.fetchall()
    
    for l1 in l1_categories:
        print(f"\n📁 [{l1['type_id']}] {l1['type_name']} (L1)")
        
        # 获取该 L1 下的所有 L2 子分类
        cursor.execute("""
            SELECT type_id, type_name FROM sc_type 
            WHERE type_pid = ? 
            ORDER BY type_id
        """, (l1['type_id'],))
        l2_categories = cursor.fetchall()
        
        if l2_categories:
            for l2 in l2_categories:
                print(f"   └── [{l2['type_id']:2d}] {l2['type_name']} (L2)")
        else:
            print(f"   └── (暂无子分类)")
    
    # 显示资源站
    print("\n" + "=" * 70)
    print("📡 资源站配置：")
    sources = get_all_sources(conn)
    if not sources:
        print("   （暂无配置）")
    else:
        for s in sources:
            print(f"\n   [{s['res_source_id']}] {s['res_name']}")
            print(f"       URL: {s['res_url']}")
            print(f"       前缀: {s['res_id_prefix']}")
            print(f"       格式: {s['data_format']}")
            print(f"       操作模式: {s['operation_mode']}")
            
            # 显示映射数量（即使为0）
            mapping_count = 0
            if s['res_mapping']:
                try:
                    mapping = json.loads(s['res_mapping'])
                    mapping_count = len(mapping)
                except:
                    pass
            
            if mapping_count > 0:
                print(f"       映射: {mapping_count} 条规则 ✅")
            else:
                print(f"       映射: 未配置 ⚠️")
    
    print("\n" + "=" * 70)
    conn.close()

def main():
    """主 CLI 入口点"""
    if len(sys.argv) < 2:
        print("\n📖 StreamCore CLI 工具")
        print("=" * 70)
        print("用法: python setup.py <命令> [参数]")
        print("\n可用命令：")
        print("  init                                - 初始化数据库")
    # This function is now effectively replaced by the argparse logic in __main__
    pass


if __name__ == '__main__':
    import argparse
    import sys
    
    # Create main parser
    parser = argparse.ArgumentParser(
        description='StreamCore Setup Tool - Configure sources and categories',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Available Commands:
  init                  Initialize database
  add-source            Add a new source
  delete-source         Delete a source
  setup-categories      Setup category mappings
  clear-mapping         Clear category mappings for a source
  create-local-type     Create local category
  list                  List all configurations

Examples:
  # Initialize database
  python3 setup.py init
  
  # Add a new source (interactive)
  python3 setup.py add-source
  
  # Delete a source
  python3 setup.py delete-source <source_id_or_prefix>
  
  # Setup category mappings
  python3 setup.py setup-categories --source <prefix>
  
  # List all configurations
  python3 setup.py list
        '''
    )
    
    parser.add_argument(
        'command',
        nargs='?',
        choices=['init', 'reset', 'add-source', 'delete-source', 'setup-categories', 
                 'clear-mapping', 'create-local-type', 'list'],
        help='Command to execute'
    )
    
    parser.add_argument(
        'args',
        nargs='*',
        help='Additional arguments for the command'
    )
    
    parser.add_argument(
        '--source',
        help='Source prefix for category mapping commands'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # If no command provided, show help
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    command = args.command
    
    print("=" * 70)
    
    if command == 'init':
        cmd_init()
    
    elif command == 'reset':
        cmd_reset()
        
    elif command == 'add-source':
        cmd_add_source()
    
    elif command == 'delete-source':
        if args.args:
            cmd_delete_source(args.args[0])
        else:
            print("❌ Error: delete-source requires source ID or prefix")
            print("   Usage: python3 setup.py delete-source <source_id_or_prefix>")
    
    elif command == 'setup-categories':
        if args.source:
            cmd_setup_categories(args.source)
        else:
            print("❌ Error: setup-categories requires --source argument")
            print("   Usage: python3 setup.py setup-categories --source <prefix>")
    
    elif command == 'clear-mapping':
        if args.source:
            cmd_clear_mapping(args.source)
        else:
            print("❌ Error: clear-mapping requires --source argument")
            print("   Usage: python3 setup.py clear-mapping --source <prefix>")
    
    elif command == 'create-local-type':
        cmd_create_local_type()
        
    elif command == 'list':
        cmd_list_config()
        
    else:
        print("=" * 70)
        print("❌ 未知命令")
        print("=" * 70)
        print("\n可用命令：")
        print("  init, add-source, delete-source, setup-categories")
        print("  clear-mapping, create-local-type, list")
        print("=" * 70)


if __name__ == '__main__':
    main()
