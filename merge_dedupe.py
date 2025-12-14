#!/usr/bin/env python3
"""
Database-Level Merge/Deduplication Tool
Merges duplicate records from multiple sources in the database

Usage:
  from merge_dedupe import auto_merge
  auto_merge('/path/to/database.db')
"""

import sqlite3
import json
import time


def find_duplicate_groups(conn, key_fields=['vod_name', 'vod_year']):
    """
    Find groups of duplicate records
    
    Returns:
        list: Groups with duplicate records
    """
    cursor = conn.cursor()
    
    # Build GROUP BY clause
    group_by = ", ".join(key_fields)
    select_fields = ", ".join(key_fields)
    
    cursor.execute(f"""
        SELECT {select_fields}, COUNT(*) as dup_count, GROUP_CONCAT(vod_id) as vod_ids
        FROM sc_vod
        GROUP BY {group_by}
        HAVING dup_count > 1
        ORDER BY dup_count DESC
    """)
    
    return cursor.fetchall()


def select_primary_record(conn, vod_ids):
    """
    Select best record from duplicate group
    Priority: has play_url > has blurb > has pic > latest vod_time
    """
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(vod_ids))
    
    cursor.execute(f"""
        SELECT vod_id, vod_play_url, vod_blurb, vod_pic, vod_time
        FROM sc_vod
        WHERE vod_id IN ({placeholders})
    """, vod_ids)
    
    # Score each record
    best_vod_id = None
    best_score = -1
    
    for row in cursor.fetchall():
        score = 0
        if row['vod_play_url']: score += 1000
        if row['vod_blurb']: score += 500  # NEW: Prioritize records with descriptions
        if row['vod_pic']: score += 100
        score += row['vod_time'] / 1000000.0
        
        if score > best_score:
            best_score = score
            best_vod_id = row['vod_id']
    
    return best_vod_id


def merge_play_data(conn, vod_ids):
    """
    Collect and merge play data from all duplicates
    Returns: (merged_play_from, merged_play_url)
    """
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(vod_ids))
    
    cursor.execute(f"""
        SELECT v.vod_id, v.vod_play_from, v.vod_play_url, c.res_id_prefix
        FROM sc_vod v
        JOIN sc_config c ON v.res_source_id = c.res_source_id
        WHERE v.vod_id IN ({placeholders})
    """, vod_ids)
    
    # Use dict to deduplicate by source prefix
    sources_data = {}  # {source_prefix: (play_from, play_url)}
    
    for row in cursor.fetchall():
        # Use prefix (e.g., "wj") instead of full name (e.g., "wjm3u8")
        source_prefix = row['res_id_prefix'].rstrip('_')
        play_url = row['vod_play_url']
        
        if play_url and source_prefix not in sources_data:
            # Only add if this source hasn't been added yet
            # Use prefix for consistency (wj, mt) not (wjm3u8, mtm3u8)
            sources_data[source_prefix] = (source_prefix, play_url)
    
    # Build merged strings from unique sources
    play_froms = []
    play_urls = []
    
    for source_prefix in sorted(sources_data.keys()):  # Sort for consistency
        play_from, play_url = sources_data[source_prefix]
        play_froms.append(play_from)
        play_urls.append(play_url)
    
    # Merge using MacCMS 10 format
    # vod_play_from: "wj$$$mt" (using prefixes for consistency)
    # vod_play_url: "source1_episodes$$$source2_episodes"
    merged_play_from = '$$$'.join(play_froms)
    merged_play_url = '$$$'.join(play_urls)
    
    return merged_play_from, merged_play_url


def merge_duplicate_group_with_log(conn, vod_ids, merge_key):
    """
    Merge a group of duplicate records and log the merge
    
    Args:
        conn: Database connection
        vod_ids: List of vod_id to merge
        merge_key: Deduplication key (e.g., "功夫|2025")
    
    Returns:
        dict: Merge statistics
    """
    cursor = conn.cursor()
    
    # Select primary record
    primary_id = select_primary_record(conn, vod_ids)
    duplicate_ids = [vid for vid in vod_ids if vid != primary_id]
    
    # Get source prefixes for all records
    placeholders = ','.join('?' * len(vod_ids))
    cursor.execute(f"""
        SELECT v.vod_id, c.res_id_prefix
        FROM sc_vod v
        JOIN sc_config c ON v.res_source_id = c.res_source_id
        WHERE v.vod_id IN ({placeholders})
    """, vod_ids)
    
    source_map = {row['vod_id']: row['res_id_prefix'].rstrip('_') 
                  for row in cursor.fetchall()}
    source_prefixes = ','.join(source_map.values())
    
    # Merge play data
    merged_from, merged_url = merge_play_data(conn, vod_ids)
    
    # Update primary record
    cursor.execute("""
        UPDATE sc_vod
        SET vod_play_from = ?, vod_play_url = ?
        WHERE vod_id = ?
    """, (merged_from, merged_url, primary_id))
    
    # Log the merge
    cursor.execute("""
        INSERT INTO sc_merge_log 
        (primary_vod_id, merged_vod_ids, source_prefixes, merge_timestamp, merge_key)
        VALUES (?, ?, ?, ?, ?)
    """, (
        primary_id,
        json.dumps(vod_ids),
        source_prefixes,
        int(time.time()),
        merge_key
    ))
    
    # Delete duplicate records
    if duplicate_ids:
        placeholders = ','.join('?' * len(duplicate_ids))
        cursor.execute(f"DELETE FROM sc_vod WHERE vod_id IN ({placeholders})", duplicate_ids)
        cursor.execute(f"DELETE FROM sc_search WHERE vod_id IN ({placeholders})", duplicate_ids)
    
    conn.commit()
    
    return {
        'primary_id': primary_id,
        'deleted_count': len(duplicate_ids),
        'sources': source_prefixes
    }


def auto_merge(db_path):
    """
    Auto-merge duplicates in the specified database
    Called by collector.py after data collection
    
    Args:
        db_path: Path to database (typically TEMP_DB)
    
    Returns:
        dict: Merge statistics
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Find duplicates
    duplicate_groups = find_duplicate_groups(conn, ['vod_name', 'vod_year'])
    
    groups_merged = 0
    records_deleted = 0
    
    for group in duplicate_groups:
        vod_ids = [int(vid) for vid in group['vod_ids'].split(',')]
        merge_key = f"{group['vod_name']}|{group['vod_year']}"
        
        try:
            result = merge_duplicate_group_with_log(conn, vod_ids, merge_key)
            groups_merged += 1
            records_deleted += result['deleted_count']
        except Exception as e:
            print(f"  ⚠️  Failed to merge group {merge_key}: {e}")
            continue
    
    conn.close()
    
    return {
        'groups_merged': groups_merged,
        'records_deleted': records_deleted
    }


if __name__ == '__main__':
    # For testing
    import sys
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        print(f"Merging duplicates in {db_path}...")
        stats = auto_merge(db_path)
        print(f"✅ Merged {stats['groups_merged']} groups, deleted {stats['records_deleted']} duplicates")
    else:
        print("Usage: python3 merge_dedupe.py <database_path>")
