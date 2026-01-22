"""
日报分析系统 v3.0 - 标签晋升脚本
每日定时运行，将满足条件的候选标签晋升为stable
"""
import sqlite3
from datetime import datetime

DB_FILE = 'tita_logs.db'

# 晋升阈值（保守起步）
PROMOTION_RULES = {
    'freq_7d': 5,           # 近7天出现≥5次
    'distinct_schools': 3,   # 覆盖≥3个学校
    'consistency_rate': 0.8, # 双跑一致率≥80%
    'similarity_threshold': 0.7  # 与现有stable标签相似度<70%才允许晋升
}

def calculate_tag_stats(conn):
    """计算每个候选标签的统计数据"""
    c = conn.cursor()
    
    # 获取所有候选标签
    c.execute("SELECT tag_id, dimension, name_norm FROM taxonomy WHERE status = 'candidate'")
    candidates = c.fetchall()
    
    print(f"\n发现 {len(candidates)} 个候选标签\n")
    
    for tag_id, dimension, name_norm in candidates:
        # 计算 freq_7d（近7天在events_v3中出现的次数）
        c.execute(f'''
            SELECT COUNT(*) FROM events_v3 
            WHERE {dimension} = ? 
            AND date(occurrence_date) >= date('now', '-7 days')
        ''', (name_norm,))
        freq_7d = c.fetchone()[0]
        
        # 计算 distinct_schools
        c.execute(f'''
            SELECT COUNT(DISTINCT school_norm) FROM events_v3 
            WHERE {dimension} = ?
        ''', (name_norm,))
        distinct_schools = c.fetchone()[0]
        
        # 计算 consistency_rate（在Silver事件中出现的比例）
        c.execute(f'''
            SELECT 
                COUNT(CASE WHEN consistency_flag = 'silver' THEN 1 END) as silver_count,
                COUNT(*) as total_count
            FROM events_v3 
            WHERE {dimension} = ?
        ''', (name_norm,))
        row = c.fetchone()
        silver_count, total_count = row[0] or 0, row[1] or 0
        consistency_rate = silver_count / total_count if total_count > 0 else 0
        
        # 更新统计数据
        c.execute('''
            UPDATE taxonomy 
            SET freq_7d = ?, distinct_schools = ?, consistency_rate = ?
            WHERE tag_id = ?
        ''', (freq_7d, distinct_schools, consistency_rate, tag_id))
    
    conn.commit()
    print("统计数据更新完成")

def check_similarity(conn, candidate_name, dimension):
    """检查候选标签是否与现有stable标签过于相似"""
    c = conn.cursor()
    
    c.execute('''
        SELECT name_norm FROM taxonomy 
        WHERE dimension = ? AND status = 'stable'
    ''', (dimension,))
    stable_tags = [row[0] for row in c.fetchall()]
    
    # 简单相似度：基于字符重叠
    for stable_name in stable_tags:
        # 计算字符级相似度
        set1 = set(candidate_name)
        set2 = set(stable_name)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        similarity = intersection / union if union > 0 else 0
        
        if similarity >= PROMOTION_RULES['similarity_threshold']:
            return stable_name, similarity
    
    return None, 0

def promote_candidates(conn):
    """执行候选标签晋升"""
    c = conn.cursor()
    
    # 获取满足基础条件的候选标签
    c.execute('''
        SELECT tag_id, dimension, name_norm, freq_7d, distinct_schools, consistency_rate
        FROM taxonomy 
        WHERE status = 'candidate'
        AND freq_7d >= ?
        AND distinct_schools >= ?
        AND consistency_rate >= ?
    ''', (
        PROMOTION_RULES['freq_7d'],
        PROMOTION_RULES['distinct_schools'],
        PROMOTION_RULES['consistency_rate']
    ))
    
    promotion_candidates = c.fetchall()
    
    print(f"\n满足晋升条件的候选标签: {len(promotion_candidates)}\n")
    
    promoted = []
    rejected = []
    
    for tag_id, dimension, name_norm, freq_7d, distinct_schools, consistency_rate in promotion_candidates:
        # 检查与现有stable标签的相似度
        similar_tag, similarity = check_similarity(conn, name_norm, dimension)
        
        if similar_tag:
            # 过于相似，建议合并而不是晋升
            rejected.append({
                'tag': name_norm,
                'dimension': dimension,
                'reason': f'与stable标签 "{similar_tag}" 相似度过高 ({similarity:.1%})',
                'suggestion': f'建议合并为 "{similar_tag}" 的别名'
            })
            continue
        
        # 执行晋升
        c.execute('''
            UPDATE taxonomy 
            SET status = 'stable', promoted_at = ?
            WHERE tag_id = ?
        ''', (datetime.now().isoformat(), tag_id))
        
        promoted.append({
            'tag': name_norm,
            'dimension': dimension,
            'freq_7d': freq_7d,
            'distinct_schools': distinct_schools,
            'consistency_rate': consistency_rate
        })
    
    conn.commit()
    
    # 输出晋升报告
    print("=" * 60)
    print("  标签晋升报告")
    print("=" * 60)
    
    if promoted:
        print(f"\n✅ 成功晋升 {len(promoted)} 个标签:\n")
        for p in promoted:
            print(f"  [{p['dimension']}] {p['tag']}")
            print(f"      freq_7d={p['freq_7d']}, schools={p['distinct_schools']}, consistency={p['consistency_rate']:.1%}")
    else:
        print("\n暂无标签满足晋升条件")
    
    if rejected:
        print(f"\n⚠️ {len(rejected)} 个标签因相似度过高被拒绝:\n")
        for r in rejected:
            print(f"  [{r['dimension']}] {r['tag']}")
            print(f"      原因: {r['reason']}")
            print(f"      建议: {r['suggestion']}")
    
    print("\n" + "=" * 60)
    
    return promoted, rejected

def show_candidate_summary(conn):
    """显示候选池概况"""
    c = conn.cursor()
    
    print("\n" + "=" * 60)
    print("  候选池概况")
    print("=" * 60 + "\n")
    
    for dimension in ['action_type', 'blocker', 'outcome']:
        c.execute('''
            SELECT name_norm, freq_7d, distinct_schools, consistency_rate
            FROM taxonomy 
            WHERE dimension = ? AND status = 'candidate'
            ORDER BY freq_7d DESC
            LIMIT 10
        ''', (dimension,))
        
        candidates = c.fetchall()
        
        print(f"📌 {dimension} (候选 Top 10):")
        if candidates:
            for name, freq, schools, rate in candidates:
                status = "🟢" if freq >= PROMOTION_RULES['freq_7d'] and schools >= PROMOTION_RULES['distinct_schools'] else "🟡"
                print(f"   {status} {name}: freq={freq}, schools={schools}, rate={rate:.1%}")
        else:
            print("   (无候选标签)")
        print()

def main():
    print("\n" + "=" * 60)
    print("  日报分析系统 v3.0 - 标签晋升检查")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_FILE)
    
    # 1. 更新统计数据
    print("\n[1/3] 更新候选标签统计...")
    calculate_tag_stats(conn)
    
    # 2. 显示候选池概况
    print("\n[2/3] 候选池概况...")
    show_candidate_summary(conn)
    
    # 3. 执行晋升
    print("\n[3/3] 执行晋升检查...")
    promote_candidates(conn)
    
    conn.close()
    print("\n完成！")

if __name__ == "__main__":
    main()
