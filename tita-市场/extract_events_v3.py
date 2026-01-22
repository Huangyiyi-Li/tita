"""
日报分析系统 v3.0 - 事件抽取器
支持：置信度输出、双跑一致性、Silver/Gray分流
"""
import sqlite3
import json
import requests
import os
import uuid
from datetime import datetime

# Configuration
CONFIG_FILE = 'config.json'
DB_FILE = 'tita_logs.db'
BUSINESS_KNOWLEDGE_FILE = 'business_knowledge.md'

# 一致性阈值
SILVER_THRESHOLD = 0.85
CONSISTENCY_THRESHOLD = 0.7

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def load_business_knowledge():
    if os.path.exists(BUSINESS_KNOWLEDGE_FILE):
        with open(BUSINESS_KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def load_taxonomy(conn):
    """加载已有的标签体系供LLM参考"""
    c = conn.cursor()
    c.execute("SELECT dimension, name_norm, definition FROM taxonomy WHERE status='stable'")
    tags = c.fetchall()
    
    taxonomy_text = ""
    for dim in ['action_type', 'blocker', 'outcome']:
        dim_tags = [t for t in tags if t[0] == dim]
        if dim_tags:
            taxonomy_text += f"\n### {dim}\n"
            for _, name, defn in dim_tags:
                taxonomy_text += f"- **{name}**: {defn or ''}\n"
    return taxonomy_text

def get_unprocessed_logs(conn):
    """获取尚未在events_v3中分析过的日志"""
    c = conn.cursor()
    c.execute('''
        SELECT feed_id, content, log_date, user_name 
        FROM daily_logs 
        WHERE feed_id NOT IN (SELECT DISTINCT doc_id FROM events_v3 WHERE doc_id IS NOT NULL)
        ORDER BY log_date DESC
    ''')
    return c.fetchall()

def build_extraction_prompt(business_knowledge, taxonomy_text, variant='A'):
    """构建抽取提示词，支持A/B变体"""
    
    base_prompt = f"""你是一个专业的商业事件分析员。请从日报中提取结构化的商业事件。

## 业务背景
{business_knowledge}

## 已有标签体系（请优先使用）
{taxonomy_text}

## 提取规则
1. 将日报拆解为独立事件，每个「学校×产品」的互动是一个事件
2. 必须给出置信度评分（0-1），反映你对该字段的确信程度
3. 引用原文片段作为证据

## 输出格式（JSON数组）
[
  {{
    "raw_span": "原文片段（完整引用）",
    "school_raw": "原始学校名",
    "school_norm": "规范学校名（如能确定）",
    "school_conf": 0.95,
    "product_raw": "原始产品名",
    "product_norm": "规范产品名",
    "product_conf": 0.90,
    "action_type": "动作类型标签",
    "action_type_conf": 0.85,
    "blocker": "阻碍原因（可为空）",
    "blocker_conf": 0.80,
    "outcome": "结果标签",
    "outcome_conf": 0.75,
    "event_conf": 0.85
  }}
]

只返回JSON，不要Markdown格式。"""

    if variant == 'B':
        # B变体：换一种表述方式，测试一致性
        base_prompt = base_prompt.replace("商业事件分析员", "销售日报结构化专家")
        base_prompt = base_prompt.replace("置信度评分", "确信度打分")
    
    return base_prompt

def call_llm_extraction(log_content, system_prompt, config):
    """调用LLM进行事件抽取"""
    api_key = config.get('volcengine_api_key')
    endpoint_id = config.get('volcengine_endpoint_id')
    
    if not api_key:
        return None, "No API Key"

    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": endpoint_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"日报内容：\n{log_content}"}
        ],
        "temperature": 0.1
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            res_json = response.json()
            content = res_json['choices'][0]['message']['content']
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content), None
        except Exception as e:
            if attempt < max_retries - 1:
                import time
                time.sleep(2)
            else:
                return None, str(e)

def calculate_consistency(events_a, events_b):
    """计算两次抽取结果的一致性"""
    if not events_a or not events_b:
        return 0.0, []
    
    # 简化逻辑：按学校名匹配，计算字段一致率
    matched_pairs = []
    
    for ea in events_a:
        school_a = ea.get('school_norm') or ea.get('school_raw', '')
        best_match = None
        best_score = 0
        
        for eb in events_b:
            school_b = eb.get('school_norm') or eb.get('school_raw', '') or ''
            if school_a and school_b and (school_a in school_b or school_b in school_a):
                # 计算字段级一致性
                score = 0
                total = 0
                
                for field in ['action_type', 'blocker', 'outcome', 'product_norm']:
                    va = ea.get(field, '')
                    vb = eb.get(field, '')
                    if va or vb:
                        total += 1
                        if va == vb or (va and vb and (va in vb or vb in va)):
                            score += 1
                
                if total > 0 and score / total > best_score:
                    best_score = score / total
                    best_match = (ea, eb, best_score)
        
        if best_match:
            matched_pairs.append(best_match)
    
    if not matched_pairs:
        return 0.0, []
    
    avg_consistency = sum(p[2] for p in matched_pairs) / len(matched_pairs)
    return avg_consistency, matched_pairs

def merge_events(events_a, events_b, matched_pairs):
    """合并双跑结果，取置信度高的字段"""
    merged = []
    
    for ea, eb, consistency in matched_pairs:
        merged_event = {}
        
        for field in ['raw_span', 'school_raw', 'school_norm', 'product_raw', 'product_norm',
                      'action_type', 'blocker', 'outcome']:
            conf_field = field + '_conf' if field not in ['raw_span'] else None
            
            va = ea.get(field, '')
            vb = eb.get(field, '')
            
            if conf_field:
                ca = ea.get(conf_field, 0)
                cb = eb.get(conf_field, 0)
                merged_event[field] = va if ca >= cb else vb
                merged_event[conf_field] = max(ca, cb)
            else:
                # raw_span取较长的
                merged_event[field] = va if len(str(va)) >= len(str(vb)) else vb
        
        # 计算合并后的event_conf
        conf_fields = ['school_conf', 'product_conf', 'action_type_conf', 'outcome_conf']
        confs = [merged_event.get(f, 0) for f in conf_fields if merged_event.get(f)]
        merged_event['event_conf'] = sum(confs) / len(confs) if confs else 0.5
        merged_event['consistency_score'] = consistency
        
        merged.append(merged_event)
    
    return merged

def save_events_v3(conn, doc_id, date_str, events, run_a_json, run_b_json, is_dual_run=True):
    """保存事件到events_v3表"""
    c = conn.cursor()
    saved_count = 0
    silver_count = 0
    
    for evt in events:
        event_id = str(uuid.uuid4())
        
        # 判断Silver/Gray
        event_conf = evt.get('event_conf', 0)
        consistency = evt.get('consistency_score', 1.0 if not is_dual_run else 0)
        
        if is_dual_run:
            if event_conf >= SILVER_THRESHOLD and consistency >= CONSISTENCY_THRESHOLD:
                consistency_flag = 'silver'
                silver_count += 1
            else:
                consistency_flag = 'gray'
        else:
            consistency_flag = 'pending'
        
        # 去重检查
        c.execute('''
            SELECT event_id FROM events_v3 
            WHERE doc_id = ? AND school_norm = ? AND raw_span = ?
        ''', (doc_id, evt.get('school_norm', ''), evt.get('raw_span', '')))
        
        if c.fetchone():
            continue
        
        c.execute('''
            INSERT INTO events_v3 (
                event_id, doc_id, raw_span,
                school_raw, school_norm, school_conf,
                product_raw, product_norm, product_conf,
                action_type, action_type_conf,
                blocker, blocker_conf,
                outcome, outcome_conf,
                event_conf, consistency_flag,
                run_a_json, run_b_json,
                occurrence_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_id, doc_id, evt.get('raw_span', ''),
            evt.get('school_raw', ''), evt.get('school_norm', ''), evt.get('school_conf', 0),
            evt.get('product_raw', ''), evt.get('product_norm', ''), evt.get('product_conf', 0),
            evt.get('action_type', ''), evt.get('action_type_conf', 0),
            evt.get('blocker', ''), evt.get('blocker_conf', 0),
            evt.get('outcome', ''), evt.get('outcome_conf', 0),
            evt.get('event_conf', 0), consistency_flag,
            json.dumps(run_a_json, ensure_ascii=False) if run_a_json else None,
            json.dumps(run_b_json, ensure_ascii=False) if run_b_json else None,
            date_str
        ))
        saved_count += 1
        
        # 更新候选标签池
        update_candidate_tags(c, evt)
    
    conn.commit()
    return saved_count, silver_count

def update_candidate_tags(cursor, event):
    """将新出现的标签加入候选池"""
    for dim in ['action_type', 'blocker', 'outcome']:
        tag_value = event.get(dim, '')
        if not tag_value:
            continue
        
        # 检查是否已存在
        cursor.execute('''
            SELECT tag_id, freq_7d FROM taxonomy 
            WHERE dimension = ? AND name_norm = ?
        ''', (dim, tag_value))
        
        existing = cursor.fetchone()
        if existing:
            # 更新频次
            cursor.execute('''
                UPDATE taxonomy SET freq_7d = freq_7d + 1 WHERE tag_id = ?
            ''', (existing[0],))
        else:
            # 新标签加入候选池
            tag_id = f"{dim[:3]}_{uuid.uuid4().hex[:8]}"
            cursor.execute('''
                INSERT INTO taxonomy (tag_id, dimension, name_norm, status, freq_7d)
                VALUES (?, ?, ?, 'candidate', 1)
            ''', (tag_id, dim, tag_value))

def main():
    import sys
    
    print("\n" + "="*60)
    print("  日报分析系统 v3.0 - 双跑一致性模式")
    print("="*60 + "\n")
    
    config = load_config()
    business_knowledge = load_business_knowledge()
    
    conn = sqlite3.connect(DB_FILE)
    taxonomy_text = load_taxonomy(conn)
    
    # 获取未处理日志
    logs = get_unprocessed_logs(conn)
    total = len(logs)
    print(f"发现 {total} 条未分析日志\n")
    
    if total == 0:
        print("无新日志需要分析，退出。")
        conn.close()
        return
    
    total_events = 0
    total_silver = 0
    
    for idx, log in enumerate(logs):
        doc_id, content, date_str, user_name = log
        progress = (idx + 1) / total * 100
        
        print(f"[{idx+1}/{total}] ({progress:.0f}%) 分析: {user_name} ({date_str})")
        
        # 构建提示词
        prompt_a = build_extraction_prompt(business_knowledge, taxonomy_text, 'A')
        prompt_b = build_extraction_prompt(business_knowledge, taxonomy_text, 'B')
        
        # Run A
        print("  ├─ Run A...", end="", flush=True)
        events_a, err_a = call_llm_extraction(content, prompt_a, config)
        if events_a:
            print(f" ✓ ({len(events_a)} events)")
        else:
            print(f" ✗ ({err_a})")
            continue
        
        # Run B
        print("  ├─ Run B...", end="", flush=True)
        events_b, err_b = call_llm_extraction(content, prompt_b, config)
        if events_b:
            print(f" ✓ ({len(events_b)} events)")
        else:
            print(f" ✗ ({err_b})")
            # 仅有A的结果，标记为pending
            saved, silver = save_events_v3(conn, doc_id, date_str, events_a, events_a, None, False)
            total_events += saved
            print(f"  └─ 保存 {saved} 事件 (pending)")
            continue
        
        # 计算一致性并合并
        consistency, matched = calculate_consistency(events_a, events_b)
        print(f"  ├─ 一致性: {consistency:.1%}")
        
        if matched:
            merged_events = merge_events(events_a, events_b, matched)
            saved, silver = save_events_v3(conn, doc_id, date_str, merged_events, events_a, events_b, True)
        else:
            # 无法匹配，各自保存为gray
            for e in events_a:
                e['consistency_score'] = 0
            saved, silver = save_events_v3(conn, doc_id, date_str, events_a, events_a, events_b, True)
        
        total_events += saved
        total_silver += silver
        print(f"  └─ 保存 {saved} 事件 (Silver: {silver})")
    
    conn.close()
    
    print("\n" + "="*60)
    print(f"  分析完成！")
    print(f"  总事件数: {total_events}")
    print(f"  Silver事件: {total_silver} ({total_silver/total_events*100:.1f}%)" if total_events > 0 else "")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
