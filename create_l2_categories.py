# create_l2_categories.py
# 创建二级分类（L2）数据

import sqlite3
from db_config import get_db_connection, MAIN_DB, TEMP_DB

def create_l2_categories():
    """创建两级分类结构"""
    
    print("=" * 70)
    print("🏗️  创建两级分类结构（L1 → L2）")
    print("=" * 70)
    
    conn = get_db_connection(MAIN_DB)
    cursor = conn.cursor()
    
    # L2 分类数据
    # type_id, type_name, type_pid (父分类ID)
    l2_categories = [
        # 电影 (type_pid=1) 的子分类
        (6, '动作片', 1),
        (7, '喜剧片', 1),
        (8, '爱情片', 1),
        (9, '科幻片', 1),
        (10, '恐怖片', 1),
        (11, '剧情片', 1),
        (12, '战争片', 1),
        
        # 电视剧 (type_pid=2) 的子分类
        (20, '国产剧', 2),
        (21, '港台剧', 2),
        (22, '日韩剧', 2),
        (23, '欧美剧', 2),
        
        # 动漫 (type_pid=3) 的子分类
        (30, '国产动漫', 3),
        (31, '日本动漫', 3),
        (32, '欧美动漫', 3),
        
        # 综艺 (type_pid=4) 的子分类
        (40, '大陆综艺', 4),
        (41, '港台综艺', 4),
        (42, '日韩综艺', 4),
        (43, '欧美综艺', 4),
        
        # 纪录片 (type_pid=5) 的子分类
        (50, '人文历史', 5),
        (51, '自然科学', 5),
        (52, '社会纪实', 5),
    ]
    
    print(f"\n📋 准备创建 {len(l2_categories)} 个二级分类...")
    print()
    
    inserted_count = 0
    
    for type_id, type_name, type_pid in l2_categories:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO sc_type (type_id, type_name, type_pid)
                VALUES (?, ?, ?)
            """, (type_id, type_name, type_pid))
            
            if cursor.rowcount > 0:
                # 获取父分类名称
                cursor.execute("SELECT type_name FROM sc_type WHERE type_id = ?", (type_pid,))
                parent = cursor.fetchone()
                parent_name = parent['type_name'] if parent else f'ID:{type_pid}'
                
                print(f"✅ [{type_id:2d}] {type_name:12s} (L1: {parent_name})")
                inserted_count += 1
        except Exception as e:
            print(f"❌ 创建失败 [{type_id}] {type_name}: {e}")
    
    conn.commit()
    
    # 同步到临时数据库
    temp_conn = get_db_connection(TEMP_DB)
    temp_cursor = temp_conn.cursor()
    
    for type_id, type_name, type_pid in l2_categories:
        temp_cursor.execute("""
            INSERT OR IGNORE INTO sc_type (type_id, type_name, type_pid)
            VALUES (?, ?, ?)
        """, (type_id, type_name, type_pid))
    
    temp_conn.commit()
    temp_conn.close()
    
    print("\n" + "=" * 70)
    print(f"✅ 成功创建 {inserted_count} 个二级分类")
    print("=" * 70)
    
    # 显示分类树
    print("\n📊 完整分类树结构：\n")
    
    cursor.execute("SELECT type_id, type_name FROM sc_type WHERE type_pid = 0 ORDER BY type_id")
    l1_categories = cursor.fetchall()
    
    for l1 in l1_categories:
        print(f"📁 [{l1['type_id']}] {l1['type_name']} (L1)")
        
        cursor.execute("""
            SELECT type_id, type_name FROM sc_type 
            WHERE type_pid = ? 
            ORDER BY type_id
        """, (l1['type_id'],))
        l2_list = cursor.fetchall()
        
        for l2 in l2_list:
            print(f"   └── [{l2['type_id']:2d}] {l2['type_name']} (L2)")
        
        if not l2_list:
            print(f"   └── (暂无子分类)")
        
        print()
    
    conn.close()
    print("=" * 70)

if __name__ == '__main__':
    create_l2_categories()
