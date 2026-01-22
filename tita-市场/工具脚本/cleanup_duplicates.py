import sqlite3

DB_FILE = 'tita_logs.db'

def cleanup_duplicates():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 统计重复数据 - 使用更宽松的条件：同一日志+学校+产品+日期
    c.execute('''
        SELECT log_id, school_name, product_name, occurrence_date, COUNT(*) as cnt
        FROM events
        GROUP BY log_id, school_name, product_name, occurrence_date
        HAVING cnt > 1
    ''')
    duplicates = c.fetchall()
    print(f"发现 {len(duplicates)} 组重复事件")
    
    # 删除重复数据，每组只保留 raw_content 最长的那条（通常是最完整的）
    c.execute('''
        DELETE FROM events
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY log_id, school_name, product_name, occurrence_date 
                    ORDER BY LENGTH(raw_content) DESC
                ) as rn
                FROM events
            ) WHERE rn = 1
        )
    ''')
    deleted = c.rowcount
    conn.commit()
    
    print(f"已删除 {deleted} 条重复事件")
    
    # 统计剩余数据
    c.execute("SELECT COUNT(*) FROM events")
    total_events = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM opportunities")
    total_opps = c.fetchone()[0]
    
    print(f"\n当前数据库状态:")
    print(f"  - 事件总数: {total_events}")
    print(f"  - 机会总数: {total_opps}")
    
    conn.close()

if __name__ == "__main__":
    cleanup_duplicates()
