#!/usr/bin/env python3
# merge_categories.py
# 合并重复分类 - 相同名称和父分类的分类保留最小ID

import sqlite3
import json
import shutil
import os
from datetime import datetime
from db_config import get_db_connection, MAIN_DB, TEMP_DB


def find_duplicate_categories(conn):
    """
    查找重复分类（相同名称+相同父分类）
    
    Returns:
        list: [(keep_id, delete_id, name, parent_id), ...]
    """
    cursor = conn.cursor()
    
    # 查找重复：相同 type_name 和 type_pid，保留最小 type_id
    cursor.execute("""
        SELECT 
            MIN(type_id) as keep_id,
            GROUP_CONCAT(type_id) as all_ids,
            type_name,
            type_pid,
            COUNT(*) as cnt
        FROM sc_type
        GROUP BY type_name, type_pid
        HAVING cnt > 1
        ORDER BY type_pid, type_name
    """)
    
    duplicates = []
    for row in cursor.fetchall():
        keep_id = row['keep_id']
        all_ids = [int(x) for x in row['all_ids'].split(',')]
        delete_ids = [x for x in all_ids if x != keep_id]
        
        for del_id in delete_ids:
            duplicates.append({
                'keep_id': keep_id,
                'delete_id': del_id,
                'name': row['type_name'],
                'parent_id': row['type_pid']
            })
    
    return duplicates


def get_parent_name(conn, parent_id):
    """获取父分类名称"""
    if parent_id == 0:
        return "(顶级分类)"
    cursor = conn.cursor()
    cursor.execute("SELECT type_name FROM sc_type WHERE type_id = ?", (parent_id,))
    result = cursor.fetchone()
    return result['type_name'] if result else f"ID:{parent_id}"


def merge_categories(dry_run=False):
    """
    合并重复分类
    
    Args:
        dry_run: 如果为 True，只显示会做什么，不实际执行
    """
    print("=" * 70)
    print("🔄 合并重复分类")
    print("=" * 70)
    
    if dry_run:
        print("\n⚠️  预览模式 - 不会实际修改数据\n")
    
    # 创建备份
    if not dry_run:
        backup_name = f"{MAIN_DB}.{datetime.now().strftime('%Y%m%d%H%M%S')}.merge.bak"
        shutil.copy2(MAIN_DB, backup_name)
        print(f"✅ 已创建备份: {backup_name}")
    
    conn = get_db_connection(MAIN_DB)
    cursor = conn.cursor()
    
    # 1. 查找重复分类
    print("\n📊 查找重复分类...")
    duplicates = find_duplicate_categories(conn)
    
    if not duplicates:
        print("✅ 没有发现重复分类！")
        conn.close()
        return
    
    print(f"发现 {len(duplicates)} 对重复分类：\n")
    
    # 按父分类分组显示
    current_parent = None
    for dup in duplicates:
        if dup['parent_id'] != current_parent:
            current_parent = dup['parent_id']
            parent_name = get_parent_name(conn, current_parent)
            print(f"\n📁 {parent_name} (pid={current_parent}):")
        
        print(f"   [{dup['keep_id']:2d}] ← [{dup['delete_id']:2d}]  {dup['name']}")
    
    # 2. 统计影响
    print("\n" + "=" * 70)
    print("📈 影响分析")
    print("=" * 70)
    
    total_vod_updates = 0
    total_mapping_updates = 0
    
    for dup in duplicates:
        # 统计受影响的视频数
        cursor.execute("SELECT COUNT(*) FROM sc_vod WHERE vod_type_id = ?", (dup['delete_id'],))
        vod_count = cursor.fetchone()[0]
        total_vod_updates += vod_count
        
        if vod_count > 0:
            print(f"   [{dup['delete_id']}] {dup['name']}: {vod_count} 条视频将迁移到 [{dup['keep_id']}]")
    
    # 统计映射更新
    cursor.execute("SELECT res_source_id, res_name, res_mapping FROM sc_config")
    sources = cursor.fetchall()
    
    for source in sources:
        if source['res_mapping']:
            try:
                mapping = json.loads(source['res_mapping'])
                updates_needed = []
                
                for remote_id, local_id in mapping.items():
                    for dup in duplicates:
                        if local_id == dup['delete_id']:
                            updates_needed.append((remote_id, dup['delete_id'], dup['keep_id']))
                
                if updates_needed:
                    print(f"\n   📡 {source['res_name']}:")
                    for remote_id, old_id, new_id in updates_needed:
                        print(f"      远程{remote_id}: {old_id} → {new_id}")
                    total_mapping_updates += len(updates_needed)
            except:
                pass
    
    print(f"\n📊 总计:")
    print(f"   - 视频更新: {total_vod_updates} 条")
    print(f"   - 映射更新: {total_mapping_updates} 条")
    print(f"   - 分类删除: {len(duplicates)} 个")
    
    if dry_run:
        print("\n💡 运行 'python3 merge_categories.py' (不带 --dry-run) 执行合并")
        conn.close()
        return
    
    # 3. 确认执行
    print("\n" + "=" * 70)
    confirm = input("⚠️  确认执行合并？(yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("❌ 操作已取消")
        conn.close()
        return
    
    # 4. 执行合并
    print("\n🔄 执行合并...")
    
    vod_updated = 0
    mapping_updated = 0
    types_deleted = 0
    
    for dup in duplicates:
        # 更新视频
        cursor.execute(
            "UPDATE sc_vod SET vod_type_id = ? WHERE vod_type_id = ?",
            (dup['keep_id'], dup['delete_id'])
        )
        vod_updated += cursor.rowcount
    
    # 更新映射
    for source in sources:
        if source['res_mapping']:
            try:
                mapping = json.loads(source['res_mapping'])
                updated = False
                
                for remote_id in list(mapping.keys()):
                    local_id = mapping[remote_id]
                    for dup in duplicates:
                        if local_id == dup['delete_id']:
                            mapping[remote_id] = dup['keep_id']
                            updated = True
                            mapping_updated += 1
                
                if updated:
                    cursor.execute(
                        "UPDATE sc_config SET res_mapping = ? WHERE res_source_id = ?",
                        (json.dumps(mapping, ensure_ascii=False), source['res_source_id'])
                    )
            except:
                pass
    
    # 删除重复分类
    for dup in duplicates:
        cursor.execute("DELETE FROM sc_type WHERE type_id = ?", (dup['delete_id'],))
        types_deleted += cursor.rowcount
    
    conn.commit()
    
    print(f"\n✅ 合并完成:")
    print(f"   - 视频更新: {vod_updated} 条")
    print(f"   - 映射更新: {mapping_updated} 条")
    print(f"   - 分类删除: {types_deleted} 个")
    
    # 5. 同步到临时数据库
    print(f"\n🔄 同步到 {TEMP_DB}...")
    conn.close()
    shutil.copy2(MAIN_DB, TEMP_DB)
    print(f"✅ 同步完成")
    
    # 6. 验证结果
    print("\n" + "=" * 70)
    print("📋 验证结果")
    print("=" * 70)
    
    conn = get_db_connection(MAIN_DB)
    remaining = find_duplicate_categories(conn)
    
    if remaining:
        print(f"⚠️  仍有 {len(remaining)} 对重复分类")
    else:
        print("✅ 没有重复分类")
    
    # 显示最终分类结构
    cursor = conn.cursor()
    cursor.execute("SELECT type_id, type_name FROM sc_type WHERE type_pid = 0 ORDER BY type_id")
    l1_list = cursor.fetchall()
    
    print("\n📂 最终分类结构:")
    for l1 in l1_list:
        cursor.execute(
            "SELECT COUNT(*) FROM sc_type WHERE type_pid = ?",
            (l1['type_id'],)
        )
        l2_count = cursor.fetchone()[0]
        print(f"   [{l1['type_id']:2d}] {l1['type_name']} ({l2_count} 个子分类)")
    
    conn.close()
    print("\n" + "=" * 70)
    print("🎉 完成！")
    print("=" * 70)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='合并重复分类 - 相同名称和父分类的分类保留最小ID'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='预览模式，不实际执行'
    )
    
    args = parser.parse_args()
    merge_categories(dry_run=args.dry_run)
