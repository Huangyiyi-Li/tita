"""
日报分析系统 v3.0 - 数据库Schema升级
"""
import sqlite3

DB_FILE = 'tita_logs.db'

def upgrade_schema_v3():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. 创建 events_v3 表（升级版事件表）
    c.execute('''
    CREATE TABLE IF NOT EXISTS events_v3 (
        event_id TEXT PRIMARY KEY,
        doc_id TEXT,
        raw_span TEXT,
        span_start INTEGER,
        span_end INTEGER,
        
        -- 学校信息
        school_raw TEXT,
        school_norm TEXT,
        school_conf REAL DEFAULT 0.0,
        
        -- 产品信息
        product_raw TEXT,
        product_norm TEXT,
        product_conf REAL DEFAULT 0.0,
        
        -- 标签（多维）
        action_type TEXT,
        action_type_conf REAL DEFAULT 0.0,
        blocker TEXT,
        blocker_conf REAL DEFAULT 0.0,
        outcome TEXT,
        outcome_conf REAL DEFAULT 0.0,
        
        -- 全局置信度与一致性
        event_conf REAL DEFAULT 0.0,
        consistency_flag TEXT DEFAULT 'pending',  -- pending/silver/gray
        
        -- 双跑结果存档
        run_a_json TEXT,
        run_b_json TEXT,
        
        -- 元数据
        occurrence_date TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        FOREIGN KEY(doc_id) REFERENCES daily_logs(feed_id)
    )
    ''')
    
    # 2. 创建 taxonomy 表（标签分类表）
    c.execute('''
    CREATE TABLE IF NOT EXISTS taxonomy (
        tag_id TEXT PRIMARY KEY,
        dimension TEXT NOT NULL,  -- action_type / blocker / outcome
        name_norm TEXT NOT NULL,
        definition TEXT,
        examples TEXT,  -- JSON array of event_ids
        status TEXT DEFAULT 'candidate',  -- candidate / stable
        freq_7d INTEGER DEFAULT 0,
        freq_30d INTEGER DEFAULT 0,
        distinct_schools INTEGER DEFAULT 0,
        consistency_rate REAL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        promoted_at TIMESTAMP
    )
    ''')
    
    # 3. 创建 tag_aliases 表（标签别名表）
    c.execute('''
    CREATE TABLE IF NOT EXISTS tag_aliases (
        alias_id TEXT PRIMARY KEY,
        tag_id TEXT,
        alias_text TEXT NOT NULL,
        freq INTEGER DEFAULT 1,
        status TEXT DEFAULT 'candidate',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(tag_id) REFERENCES taxonomy(tag_id)
    )
    ''')
    
    # 4. 创建 entity_aliases 表（实体别名表：学校/产品）
    c.execute('''
    CREATE TABLE IF NOT EXISTS entity_aliases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,  -- school / product
        alias TEXT NOT NULL,
        canonical TEXT NOT NULL,
        confidence REAL DEFAULT 0.0,
        freq INTEGER DEFAULT 1,
        status TEXT DEFAULT 'candidate',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(entity_type, alias)
    )
    ''')
    
    # 5. 创建索引以提高查询性能
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_v3_doc ON events_v3(doc_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_v3_school ON events_v3(school_norm)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_v3_consistency ON events_v3(consistency_flag)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_taxonomy_dimension ON taxonomy(dimension)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_taxonomy_status ON taxonomy(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_entity_aliases_type ON entity_aliases(entity_type)')
    
    # 6. 初始化基础标签（Stable种子）
    seed_tags = [
        # action_type
        ('act_visit', 'action_type', '走访', '实地拜访学校', 'stable'),
        ('act_call', 'action_type', '电话沟通', '电话联系客户', 'stable'),
        ('act_demo', 'action_type', '演示', '产品演示/培训', 'stable'),
        ('act_pilot', 'action_type', '试点', '试用/试点部署', 'stable'),
        ('act_collect', 'action_type', '回收', '物料回收/订单收集', 'stable'),
        
        # blocker
        ('blk_busy', 'blocker', '期末繁忙', '学校期末考试/事务繁忙', 'stable'),
        ('blk_budget', 'blocker', '预算不足', '经费/预算限制', 'stable'),
        ('blk_approval', 'blocker', '领导审批', '需校长/领导审批', 'stable'),
        ('blk_policy', 'blocker', '政策限制', '教育局/政策相关阻力', 'stable'),
        
        # outcome
        ('out_agreed', 'outcome', '同意推进', '对方同意继续推进', 'stable'),
        ('out_rejected', 'outcome', '拒绝', '明确拒绝合作', 'stable'),
        ('out_pending', 'outcome', '待定', '需要等待/下学期再议', 'stable'),
        ('out_scheduled', 'outcome', '已约时间', '已约定下次沟通时间', 'stable'),
    ]
    
    for tag in seed_tags:
        try:
            c.execute('''
                INSERT OR IGNORE INTO taxonomy (tag_id, dimension, name_norm, definition, status)
                VALUES (?, ?, ?, ?, ?)
            ''', tag)
        except:
            pass
    
    conn.commit()
    conn.close()
    
    print("="*50)
    print("  数据库Schema升级完成 (v3.0)")
    print("="*50)
    print("\n新增表:")
    print("  - events_v3: 支持置信度、双跑一致性的事件表")
    print("  - taxonomy: 标签分类表（含晋升状态）")
    print("  - tag_aliases: 标签别名表")
    print("  - entity_aliases: 实体别名表（学校/产品）")
    print(f"\n已初始化 {len(seed_tags)} 个种子标签")

if __name__ == "__main__":
    upgrade_schema_v3()
