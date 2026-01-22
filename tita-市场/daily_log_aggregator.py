import sqlite3
import requests
import json
import datetime
import os
import time

# Configuration
CONFIG_FILE = 'config.json'
DB_FILE = 'tita_logs.db'

def load_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_logs (
            feed_id TEXT PRIMARY KEY,
            user_id TEXT,
            user_name TEXT,
            department TEXT,
            log_date TEXT,
            content TEXT,
            analysis_json TEXT,
            crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn

def save_log_to_db(conn, log_data, analysis_result):
    c = conn.cursor()
    try:
        c.execute('''
            INSERT OR REPLACE INTO daily_logs 
            (feed_id, user_id, user_name, department, log_date, content, analysis_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            log_data['feed_id'],
            log_data['user_id'],
            log_data['user_name'],
            log_data['department'],
            log_data['log_date'],
            log_data['content'],
            json.dumps(analysis_result, ensure_ascii=False)
        ))
        conn.commit()
    except Exception as e:
        print(f"Error saving to DB: {e}")

def get_yesterday_time_range():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    
    # Format: YYYY-MM-DD HH:MM:SS
    start_time = f"{yesterday} 00:00:00"
    end_time = f"{yesterday} 23:59:59"
    return start_time, end_time, yesterday

def fetch_logs(config, start_time, end_time, auto_refresh_cookie=True):
    url = config['tita_api_url']
    headers = config['headers']
    
    all_logs = []
    page_num = 1
    page_size = 20
    
    while True:
        payload = {
            "pageNum": page_num,
            "pageSize": page_size,
            "relation": 0,
            "summaryType": 0,
            "startTime": start_time,
            "endTime": end_time,
            "searchDepartmentIds": [""],
            "searchUserIds": [""],
            "searchGroupIds": [""]
        }
        
        print(f"Fetching page {page_num}...")
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            # Cookie失效检测
            if response.status_code in [401, 403]:
                print("\n" + "=" * 50)
                print("[ERROR] Cookie已失效!")
                print("=" * 50)
                
                if auto_refresh_cookie:
                    print("\n[INFO] 正在启动Cookie刷新工具...")
                    try:
                        import subprocess
                        import sys
                        
                        # 获取cookie_refresher.py的路径
                        refresher_path = os.path.join(os.path.dirname(__file__), '工具脚本', 'cookie_refresher.py')
                        if not os.path.exists(refresher_path):
                            refresher_path = os.path.join(os.path.dirname(__file__), 'cookie_refresher.py')
                        
                        # 调用cookie刷新工具（使用--auto模式，不等待用户输入）
                        result = subprocess.run([sys.executable, refresher_path, '--auto'], 
                                              cwd=os.path.dirname(__file__))
                        
                        if result.returncode == 0:
                            print("\n[OK] Cookie刷新完成，重新加载配置...")
                            # 重新加载配置
                            new_config = load_config()
                            # 递归调用，但禁用自动刷新避免无限循环
                            return fetch_logs(new_config, start_time, end_time, auto_refresh_cookie=False)
                        else:
                            print("[FAIL] Cookie刷新失败")
                    except Exception as e:
                        print(f"[FAIL] 无法启动Cookie刷新工具: {e}")
                
                print("\n请手动运行以下命令刷新Cookie:")
                print("   python 工具脚本/cookie_refresher.py")
                print("\n或者手动更新 config.json 中的 cookie 值")
                print("=" * 50)
                return []
            
            response.raise_for_status()
            data = response.json()
            
            if data['Code'] != 1:
                print(f"Error from API: {data['Message']}")
                break
                
            feeds = data.get('Data', {}).get('feeds', [])
            if not feeds:
                break
                
            all_logs.extend(feeds)
            
            if len(feeds) < page_size:
                break
                
            page_num += 1
            time.sleep(1) 
            
        except Exception as e:
            print(f"Request failed: {e}")
            break
            
    return all_logs

def filter_logs(logs, target_departments):
    filtered = []
    for log in logs:
        user_info = log.get('publishUser', {})
        dept_name = str(user_info.get('departmentName', ''))
        
        if dept_name in target_departments:
            filtered.append(log)
    return filtered

def analyze_log_content(content, config):
    api_key = config.get('volcengine_api_key')
    endpoint_id = config.get('volcengine_endpoint_id')
    categories = config.get('analysis_categories')
    
    if not api_key or "PLEASE_ENTER" in api_key:
        print("Warning: No Volcano Engine API Key provided. Skipping analysis.")
        return {cat: "" for cat in categories}

    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    prompt = f"""
    你是一个专业的日志分析助手。请分析以下“日志原文”，并提取信息归类到以下类别中：
    {', '.join(categories)}

    如果某个类别没有相关信息，请返回空字符串。
    请直接返回一个标准的JSON格式对象，不要包含Markdown格式（如 ```json ... ```），也不要包含其他解释语。
    
    日志原文：
    {content}
    """
    
    payload = {
        "model": endpoint_id,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that outputs raw JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        res_json = response.json()
        
        content_str = res_json['choices'][0]['message']['content']
        content_str = content_str.replace('```json', '').replace('```', '').strip()
        
        return json.loads(content_str)
    except Exception as e:
        print(f"LLM Analysis failed: {e}")
        return {cat: "分析失败" for cat in categories}

def generate_report(logs_with_analysis, date_str, config):
    report_lines = []
    report_lines.append(f"# 日报汇总 - {date_str}")
    report_lines.append(f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"共筛选出 {len(logs_with_analysis)} 条记录")
    report_lines.append("")
    
    for idx, item in enumerate(logs_with_analysis, 1):
        log = item['original_log']
        analysis = item['analysis']
        user_name = log.get('publishUser', {}).get('name', 'Unknown')
        
        full_content = item['full_content']
        
        report_lines.append(f"## {idx}. {user_name}")
        report_lines.append("### 日志原文")
        report_lines.append(full_content)
        report_lines.append("")
        report_lines.append("### 日志分析")
        
        if isinstance(analysis, dict):
            for category, val in analysis.items():
                if val:
                    report_lines.append(f"- **{category}**: {val}")
        else:
            report_lines.append(f"- 分析结果格式错误: {analysis}")
        
        report_lines.append("\n---\n")
        
    output_filename = f"daily_report_{date_str}.md"
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
    
    print(f"Report generated: {output_filename}")

def main():
    if not os.path.exists(CONFIG_FILE):
        print(f"Config file {CONFIG_FILE} not found!")
        return

    config = load_config()
    conn = init_db()
    
    start_time, end_time, yesterday_date = get_yesterday_time_range()
    
    print(f"Fetching logs for {yesterday_date} ({start_time} to {end_time})...")
    
    all_logs = fetch_logs(config, start_time, end_time)
    print(f"Total logs fetched: {len(all_logs)}")
    
    target_depts = config['target_departments']
    filtered_logs = filter_logs(all_logs, target_depts)
    print(f"Logs after filtering (Dept {target_depts}): {len(filtered_logs)}")
    
    processed_logs = []
    
    for log in filtered_logs:
        user_name = log.get('publishUser', {}).get('name', 'Unknown')
        user_id = str(log.get('publishUser', {}).get('userId', ''))
        dept_name = log.get('publishUser', {}).get('departmentName', '')
        feed_id = log.get('feedId', '')
        
        raw_content_parts = []
        daily_content = log.get('dailyContent', [])
        if daily_content:
            for item in daily_content:
                title = item.get('title', '')
                text = item.get('content', '')
                if text and text.strip() != "":
                    if title == "今日 OKR 进展":
                       try:
                           okr_data = json.loads(text)
                           okr_names = [row['Name'] for row in okr_data.get('Rows', [])]
                           text = "\n".join([f"- {name}" for name in okr_names])
                       except:
                           pass 
                    raw_content_parts.append(f"**{title}**:\n{text}")
        
        full_content = "\n\n".join(raw_content_parts)
        
        # Avoid re-analyzing if already in DB (Optional optimization, but strictly speaking we should follow requirement to fetch and analyze)
        # But user wants "Every morning crawl".
        # Let's just analyze.
        
        print(f"Analyzing log for {user_name}...")
        analysis = analyze_log_content(full_content, config)
        
        # Save to DB
        db_data = {
            'feed_id': feed_id,
            'user_id': user_id,
            'user_name': user_name,
            'department': dept_name,
            'log_date': str(yesterday_date),
            'content': full_content
        }
        save_log_to_db(conn, db_data, analysis)
        
        processed_logs.append({
            'original_log': log,
            'full_content': full_content,
            'analysis': analysis
        })
        
    conn.close()
    generate_report(processed_logs, str(yesterday_date), config)

if __name__ == "__main__":
    main()
