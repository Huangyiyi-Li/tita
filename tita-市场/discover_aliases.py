"""
日报分析系统 v3.0 - 别名自动发现
分析事件中的原始名称，发现学校/产品的别名映射关系
"""
import sqlite3
from collections import defaultdict
import re

DB_FILE = 'tita_logs.db'

# 别名晋升阈值
ALIAS_PROMOTION_RULES = {
    'min_freq': 3,           # 至少出现3次
    'min_cooccurrence': 2,   # 与规范名共现至少2次
    'similarity_threshold': 0.5  # 字符相似度阈值
}

def calculate_similarity(str1, str2):
    """计算两个字符串的相似度（基于公共子串和字符重叠）"""
    if not str1 or not str2:
        return 0
    
    str1 = str1.lower().strip()
    str2 = str2.lower().strip()
    
    # 完全包含关系
    if str1 in str2 or str2 in str1:
        return 0.9
    
    # 字符级Jaccard相似度
    set1 = set(str1)
    set2 = set(str2)
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0

def discover_school_aliases(conn):
    """发现学校别名"""
    c = conn.cursor()
    
    print("\n" + "="*60)
    print("  学校别名发现")
    print("="*60)
    
    # 获取所有 school_raw 和 school_norm 的组合
    c.execute('''
        SELECT school_raw, school_norm, COUNT(*) as freq
        FROM events_v3
        WHERE school_raw IS NOT NULL AND school_raw != ''
        AND school_norm IS NOT NULL AND school_norm != ''
        AND school_raw != school_norm
        GROUP BY school_raw, school_norm
        ORDER BY freq DESC
    ''')
    
    raw_norm_pairs = c.fetchall()
    print(f"\n发现 {len(raw_norm_pairs)} 组 (raw → norm) 映射关系\n")
    
    # 分析别名候选
    candidates = []
    for raw, norm, freq in raw_norm_pairs:
        # 检查是否已存在
        c.execute('''
            SELECT id FROM entity_aliases 
            WHERE entity_type = 'school' AND alias = ?
        ''', (raw,))
        
        if c.fetchone():
            continue
        
        # 计算相似度
        similarity = calculate_similarity(raw, norm)
        
        if similarity >= ALIAS_PROMOTION_RULES['similarity_threshold']:
            candidates.append({
                'alias': raw,
                'canonical': norm,
                'freq': freq,
                'similarity': similarity
            })
    
    # 插入候选别名
    new_count = 0
    for cand in candidates:
        try:
            c.execute('''
                INSERT INTO entity_aliases (entity_type, alias, canonical, confidence, freq, status)
                VALUES ('school', ?, ?, ?, ?, 'candidate')
            ''', (cand['alias'], cand['canonical'], cand['similarity'], cand['freq']))
            new_count += 1
            print(f"  📍 {cand['alias']} → {cand['canonical']} (freq={cand['freq']}, sim={cand['similarity']:.1%})")
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
    print(f"\n新增 {new_count} 个学校别名候选")
    return new_count

def discover_product_aliases(conn):
    """发现产品别名"""
    c = conn.cursor()
    
    print("\n" + "="*60)
    print("  产品别名发现")
    print("="*60)
    
    # 获取所有 product_raw 和 product_norm 的组合
    c.execute('''
        SELECT product_raw, product_norm, COUNT(*) as freq
        FROM events_v3
        WHERE product_raw IS NOT NULL AND product_raw != ''
        AND product_norm IS NOT NULL AND product_norm != ''
        AND product_raw != product_norm
        GROUP BY product_raw, product_norm
        ORDER BY freq DESC
    ''')
    
    raw_norm_pairs = c.fetchall()
    print(f"\n发现 {len(raw_norm_pairs)} 组 (raw → norm) 映射关系\n")
    
    # 分析别名候选
    candidates = []
    for raw, norm, freq in raw_norm_pairs:
        # 检查是否已存在
        c.execute('''
            SELECT id FROM entity_aliases 
            WHERE entity_type = 'product' AND alias = ?
        ''', (raw,))
        
        if c.fetchone():
            continue
        
        # 计算相似度
        similarity = calculate_similarity(raw, norm)
        
        if similarity >= ALIAS_PROMOTION_RULES['similarity_threshold']:
            candidates.append({
                'alias': raw,
                'canonical': norm,
                'freq': freq,
                'similarity': similarity
            })
    
    # 插入候选别名
    new_count = 0
    for cand in candidates:
        try:
            c.execute('''
                INSERT INTO entity_aliases (entity_type, alias, canonical, confidence, freq, status)
                VALUES ('product', ?, ?, ?, ?, 'candidate')
            ''', (cand['alias'], cand['canonical'], cand['similarity'], cand['freq']))
            new_count += 1
            print(f"  📦 {cand['alias']} → {cand['canonical']} (freq={cand['freq']}, sim={cand['similarity']:.1%})")
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
    print(f"\n新增 {new_count} 个产品别名候选")
    return new_count

def suggest_merges(conn):
    """建议同义合并"""
    c = conn.cursor()
    
    print("\n" + "="*60)
    print("  同义合并建议")
    print("="*60)
    
    # 查找可能的同义标签（在taxonomy中）
    c.execute('''
        SELECT t1.tag_id, t1.name_norm, t2.tag_id, t2.name_norm, t1.dimension
        FROM taxonomy t1
        JOIN taxonomy t2 ON t1.dimension = t2.dimension AND t1.tag_id < t2.tag_id
        WHERE t1.status = 'candidate' OR t2.status = 'candidate'
    ''')
    
    pairs = c.fetchall()
    suggestions = []
    
    for tag_id1, name1, tag_id2, name2, dimension in pairs:
        similarity = calculate_similarity(name1, name2)
        if similarity >= 0.7:  # 高相似度才建议合并
            suggestions.append({
                'tag1': name1,
                'tag2': name2,
                'dimension': dimension,
                'similarity': similarity
            })
    
    if suggestions:
        print(f"\n发现 {len(suggestions)} 组可能需要合并的同义标签:\n")
        for s in suggestions[:10]:  # 只显示前10个
            print(f"  [{s['dimension']}] \"{s['tag1']}\" ≈ \"{s['tag2']}\" (sim={s['similarity']:.1%})")
    else:
        print("\n暂无同义合并建议")
    
    return suggestions

def promote_aliases(conn):
    """晋升满足条件的别名"""
    c = conn.cursor()
    
    print("\n" + "="*60)
    print("  别名晋升检查")
    print("="*60)
    
    # 查找满足晋升条件的候选别名
    c.execute('''
        SELECT id, entity_type, alias, canonical, freq
        FROM entity_aliases
        WHERE status = 'candidate' AND freq >= ?
    ''', (ALIAS_PROMOTION_RULES['min_freq'],))
    
    promotable = c.fetchall()
    
    promoted_count = 0
    for alias_id, entity_type, alias, canonical, freq in promotable:
        c.execute('''
            UPDATE entity_aliases SET status = 'stable' WHERE id = ?
        ''', (alias_id,))
        promoted_count += 1
        print(f"  ✅ [{entity_type}] {alias} → {canonical} (freq={freq})")
    
    conn.commit()
    
    if promoted_count > 0:
        print(f"\n成功晋升 {promoted_count} 个别名")
    else:
        print("\n暂无别名满足晋升条件")
    
    return promoted_count

def show_alias_summary(conn):
    """显示别名概况"""
    c = conn.cursor()
    
    print("\n" + "="*60)
    print("  别名概况")
    print("="*60)
    
    for entity_type in ['school', 'product']:
        c.execute('''
            SELECT status, COUNT(*) 
            FROM entity_aliases 
            WHERE entity_type = ?
            GROUP BY status
        ''', (entity_type,))
        
        stats = dict(c.fetchall())
        candidate = stats.get('candidate', 0)
        stable = stats.get('stable', 0)
        
        print(f"\n  {entity_type.upper()}:")
        print(f"    候选: {candidate}")
        print(f"    稳定: {stable}")

def main():
    print("\n" + "="*60)
    print("  日报分析系统 v3.0 - 别名自动发现")
    print("="*60)
    
    conn = sqlite3.connect(DB_FILE)
    
    # 1. 发现学校别名
    discover_school_aliases(conn)
    
    # 2. 发现产品别名
    discover_product_aliases(conn)
    
    # 3. 同义合并建议
    suggest_merges(conn)
    
    # 4. 晋升别名
    promote_aliases(conn)
    
    # 5. 显示概况
    show_alias_summary(conn)
    
    conn.close()
    print("\n完成！")

if __name__ == "__main__":
    main()
