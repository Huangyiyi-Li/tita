"""
Tita日报分析一体化服务

功能：
1. Web服务器 - 访问 http://localhost:8080 查看仪表板
2. 定时任务 - 自动爬取和分析日报
3. Cookie管理 - 后台保活 + 失效时自动弹出扫码

使用方式：
python tita_service.py
"""

import json
import sqlite3
import requests
import datetime
import time
import os
import sys
import random
import threading
import webbrowser
from pathlib import Path
from collections import Counter

# Flask和APScheduler
try:
    from flask import Flask, send_file, jsonify, redirect
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    print("缺少依赖，正在安装...")
    os.system("pip install flask apscheduler")
    from flask import Flask, send_file, jsonify, redirect
    from apscheduler.schedulers.background import BackgroundScheduler

# Selenium (用于扫码)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("⚠️ Selenium未安装，Cookie失效时需手动刷新")

# ==================== 配置 ====================
CONFIG_FILE = 'config.json'
DB_FILE = 'tita_logs.db'
DASHBOARD_FILE = '输出/daily_report_dashboard.html'
PORT = 8080
SHARED_COOKIE_FILE = r'f:\共享配置\tita_cookie.json'  # 共享Cookie文件

# ==================== 全局状态 ====================
service_status = {
    "last_fetch": None,
    "last_analysis": None,
    "last_keepalive": None,
    "cookie_valid": True,
    "total_logs": 0,
    "running_since": None
}

# 进度跟踪状态
fetch_progress = {
    "is_running": False,
    "phase": "",           # "idle", "fetching", "analyzing", "generating", "done", "error"
    "current": 0,          # 当前处理数
    "total": 0,            # 总数
    "current_user": "",    # 当前处理的用户名
    "message": "",         # 状态消息
    "start_time": None,
    "end_time": None
}

# ==================== 工具函数 ====================

def load_shared_cookie():
    """从共享文件加载Cookie"""
    try:
        if os.path.exists(SHARED_COOKIE_FILE):
            with open(SHARED_COOKIE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('cookie', '')
    except Exception as e:
        log(f"读取共享Cookie失败: {e}", "WARNING")
    return None

def save_shared_cookie(cookie_str):
    """保存Cookie到共享文件"""
    try:
        os.makedirs(os.path.dirname(SHARED_COOKIE_FILE), exist_ok=True)
        data = {
            'cookie': cookie_str,
            'updated_at': datetime.datetime.now().isoformat(),
            'updated_by': 'tita-市场'
        }
        with open(SHARED_COOKIE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        log(f"Cookie已同步到共享文件")
    except Exception as e:
        log(f"保存共享Cookie失败: {e}", "WARNING")

def load_config():
    """加载配置，优先使用共享Cookie"""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 尝试从共享文件加载更新的Cookie
    shared_cookie = load_shared_cookie()
    if shared_cookie:
        config['headers']['cookie'] = shared_cookie
    
    return config

def save_config(config):
    """保存配置，同时更新共享Cookie文件"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    
    # 同步更新共享Cookie文件
    cookie_str = config.get('headers', {}).get('cookie', '')
    if cookie_str:
        save_shared_cookie(cookie_str)

def log(message, level="INFO"):
    """日志记录"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

# ==================== Cookie管理 ====================

def test_cookie(config):
    """测试Cookie是否有效"""
    url = config['tita_api_url']
    headers = config['headers']
    
    today = datetime.date.today()
    payload = {
        "pageNum": 1, "pageSize": 1, "relation": 0, "summaryType": 0,
        "startTime": f"{today} 00:00:00", "endTime": f"{today} 23:59:59",
        "searchDepartmentIds": [""], "searchUserIds": [""], "searchGroupIds": [""]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [401, 403]:
            return False, "Cookie已失效"
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}"
        data = response.json()
        if data.get('Code') != 1:
            return False, data.get('Message', 'API错误')
        return True, "Cookie有效"
    except Exception as e:
        return False, str(e)

def refresh_cookie_with_selenium():
    """使用Selenium弹出扫码窗口刷新Cookie"""
    if not SELENIUM_AVAILABLE:
        log("Selenium不可用，请手动更新Cookie", "ERROR")
        return False
    
    log("Cookie失效，正在打开扫码窗口...")
    
    try:
        options = Options()
        options.add_argument('--start-maximized')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        
        try:
            driver = webdriver.Chrome(options=options)
        except:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
        driver.get("https://work-weixin.tita.com")
        log("请使用企业微信扫码登录...")
        
        # 等待登录成功
        timeout = 300
        start = time.time()
        while time.time() - start < timeout:
            if any(x in driver.current_url for x in ["/home", "/weixin/pc/home"]):
                log("检测到登录成功!")
                time.sleep(3)
                
                # 提取Cookie
                cookies = driver.get_cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                
                # 保存到配置
                config = load_config()
                config['headers']['cookie'] = cookie_str
                save_config(config)
                
                driver.quit()
                log("Cookie已更新!")
                return True
            time.sleep(2)
        
        driver.quit()
        log("扫码超时", "ERROR")
        return False
        
    except Exception as e:
        log(f"扫码刷新失败: {e}", "ERROR")
        return False

def ensure_valid_cookie():
    """确保Cookie有效，失效时自动刷新"""
    global service_status
    config = load_config()
    
    valid, msg = test_cookie(config)
    service_status["cookie_valid"] = valid
    
    if not valid:
        log(f"Cookie检测: {msg}", "WARNING")
        if refresh_cookie_with_selenium():
            service_status["cookie_valid"] = True
            return True
        return False
    return True

# ==================== 数据爬取与分析 ====================

def fetch_and_analyze_logs(date_str=None):
    """爬取并分析日报"""
    global service_status, fetch_progress
    
    # 初始化进度
    fetch_progress["is_running"] = True
    fetch_progress["phase"] = "fetching"
    fetch_progress["current"] = 0
    fetch_progress["total"] = 0
    fetch_progress["current_user"] = ""
    fetch_progress["message"] = "正在检测Cookie状态..."
    fetch_progress["start_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fetch_progress["end_time"] = None
    
    try:
        if not ensure_valid_cookie():
            fetch_progress["phase"] = "error"
            fetch_progress["message"] = "Cookie无效且刷新失败"
            fetch_progress["is_running"] = False
            log("Cookie无效且刷新失败，跳过爬取", "ERROR")
            return False
        
        config = load_config()
        
        # 默认获取昨天的数据
        if date_str is None:
            target_date = datetime.date.today() - datetime.timedelta(days=1)
            date_str = str(target_date)
        
        fetch_progress["message"] = f"正在获取 {date_str} 的日报数据..."
        log(f"开始爬取 {date_str} 的日报...")
        
        # 调用现有的爬取逻辑
        import daily_log_aggregator as aggregator
        
        start_time = f"{date_str} 00:00:00"
        end_time = f"{date_str} 23:59:59"
        
        all_logs = aggregator.fetch_logs(config, start_time, end_time)
        if not all_logs:
            fetch_progress["phase"] = "done"
            fetch_progress["message"] = f"未获取到 {date_str} 的日报数据"
            fetch_progress["is_running"] = False
            log(f"未获取到 {date_str} 的日报数据")
            return False
        
        filtered = aggregator.filter_logs(all_logs, config['target_departments'])
        fetch_progress["total"] = len(filtered)
        fetch_progress["message"] = f"获取到 {len(filtered)} 条日报，开始AI分析..."
        fetch_progress["phase"] = "analyzing"
        log(f"获取到 {len(filtered)} 条日报")
        
        # 分析并保存
        conn = aggregator.init_db()
        processed = []
        
        for idx, log_item in enumerate(filtered):
            user_name = log_item.get('publishUser', {}).get('name', 'Unknown')
            user_id = str(log_item.get('publishUser', {}).get('userId', ''))
            dept_name = log_item.get('publishUser', {}).get('departmentName', '')
            feed_id = log_item.get('feedId', '')
            
            # 更新进度
            fetch_progress["current"] = idx + 1
            fetch_progress["current_user"] = user_name
            fetch_progress["message"] = f"正在分析: {user_name} ({idx + 1}/{len(filtered)})"
            
            # 提取内容
            content_parts = []
            for item in log_item.get('dailyContent', []):
                title = item.get('title', '')
                text = item.get('content', '')
                if text and text.strip():
                    if title == "今日 OKR 进展":
                        try:
                            okr = json.loads(text)
                            text = "\n".join([f"- {r['Name']}" for r in okr.get('Rows', [])])
                        except:
                            pass
                    content_parts.append(f"**{title}**:\n{text}")
            
            full_content = "\n\n".join(content_parts)
            
            log(f"分析: {user_name}...")
            analysis = aggregator.analyze_log_content(full_content, config)
            
            db_data = {
                'feed_id': feed_id, 'user_id': user_id, 'user_name': user_name,
                'department': dept_name, 'log_date': date_str, 'content': full_content
            }
            aggregator.save_log_to_db(conn, db_data, analysis)
            processed.append({'original_log': log_item, 'full_content': full_content, 'analysis': analysis})
        
        conn.close()
        
        # 生成报告
        fetch_progress["phase"] = "generating"
        fetch_progress["message"] = "正在生成Dashboard..."
        aggregator.generate_report(processed, date_str, config)
        
        service_status["last_fetch"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        service_status["last_analysis"] = service_status["last_fetch"]
        service_status["total_logs"] = len(processed)
        
        # 重新生成Dashboard
        regenerate_dashboard()
        
        # 完成
        fetch_progress["phase"] = "done"
        fetch_progress["message"] = f"✅ 完成! 处理 {len(processed)} 条日报"
        fetch_progress["end_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fetch_progress["is_running"] = False
        
        log(f"✅ 完成! 处理 {len(processed)} 条日报")
        return True
        
    except Exception as e:
        fetch_progress["phase"] = "error"
        fetch_progress["message"] = f"❌ 爬取分析失败: {str(e)}"
        fetch_progress["is_running"] = False
        log(f"爬取分析失败: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return False

def regenerate_dashboard():
    """重新生成Dashboard"""
    try:
        import generate_dashboard
        # 调用generate_dashboard的主逻辑
        if hasattr(generate_dashboard, 'main'):
            generate_dashboard.main()
        else:
            exec(open('generate_dashboard.py', encoding='utf-8').read())
        log("Dashboard已更新")
    except Exception as e:
        log(f"Dashboard生成失败: {e}", "ERROR")

# ==================== 定时任务 ====================

def keepalive_job():
    """保活任务"""
    global service_status
    config = load_config()
    valid, msg = test_cookie(config)
    service_status["cookie_valid"] = valid
    service_status["last_keepalive"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if valid:
        log(f"保活成功: {msg}")
    else:
        log(f"保活失败: {msg}", "WARNING")

def daily_fetch_job():
    """每日爬取任务"""
    log("执行每日定时爬取...")
    fetch_and_analyze_logs()

def setup_scheduler():
    """设置定时任务"""
    scheduler = BackgroundScheduler()
    
    config = load_config()
    keepalive_config = config.get('keepalive', {})
    
    # 每日爬取任务 - 早上9:00
    scheduler.add_job(daily_fetch_job, 'cron', hour=9, minute=0, id='daily_fetch')
    
    # 保活任务 - 工作时间内随机执行
    start_hour = keepalive_config.get('start_hour', 8)
    end_hour = keepalive_config.get('end_hour', 18)
    attempts = keepalive_config.get('daily_attempts', 3)
    
    # 计算保活时间点
    if attempts > 0:
        interval = (end_hour - start_hour) / attempts
        for i in range(attempts):
            hour = int(start_hour + i * interval)
            minute = random.randint(0, 59)
            scheduler.add_job(keepalive_job, 'cron', hour=hour, minute=minute, 
                            id=f'keepalive_{i}', jitter=300)  # 5分钟随机波动
    
    scheduler.start()
    log(f"定时任务已启动: 每日9:00爬取, {attempts}次保活({start_hour}:00-{end_hour}:00)")
    return scheduler

# ==================== Flask Web服务 ====================

app = Flask(__name__)

@app.route('/')
def index():
    """首页 - 显示Dashboard"""
    if os.path.exists(DASHBOARD_FILE):
        return send_file(DASHBOARD_FILE)
    return """
    <html>
    <head><title>Tita日报分析服务</title></head>
    <body style="font-family: sans-serif; padding: 40px; text-align: center;">
        <h1>🚀 Tita日报分析服务</h1>
        <p>Dashboard尚未生成，请先获取数据</p>
        <a href="/api/fetch" style="padding: 10px 20px; background: #4F46E5; color: white; 
           text-decoration: none; border-radius: 5px;">立即获取昨日日报</a>
        <br><br>
        <a href="/api/status">查看服务状态</a>
    </body>
    </html>
    """

@app.route('/api/status')
def api_status():
    """服务状态API"""
    return jsonify(service_status)

@app.route('/api/progress')
def api_progress():
    """获取拉取进度"""
    return jsonify(fetch_progress)

@app.route('/api/fetch')
def api_fetch():
    """手动触发爬取"""
    def do_fetch():
        fetch_and_analyze_logs()
    
    thread = threading.Thread(target=do_fetch)
    thread.start()
    
    return jsonify({"status": "started", "message": "后台开始爬取，请稍后刷新页面"})

@app.route('/api/refresh-cookie')
def api_refresh_cookie():
    """手动刷新Cookie"""
    def do_refresh():
        refresh_cookie_with_selenium()
    
    thread = threading.Thread(target=do_refresh)
    thread.start()
    
    return jsonify({"status": "started", "message": "正在打开扫码窗口..."})

@app.route('/api/keepalive')
def api_keepalive():
    """手动保活"""
    keepalive_job()
    return jsonify({"status": "done", "cookie_valid": service_status["cookie_valid"]})

# ==================== 主函数 ====================

def main():
    global service_status
    
    print("=" * 60)
    print("  🚀 Tita日报分析一体化服务")
    print("=" * 60)
    print()
    
    # 检查配置文件
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ 配置文件 {CONFIG_FILE} 不存在!")
        sys.exit(1)
    
    # 初始化状态
    service_status["running_since"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 启动定时任务
    scheduler = setup_scheduler()
    
    # 初始Cookie检测
    config = load_config()
    valid, msg = test_cookie(config)
    service_status["cookie_valid"] = valid
    
    if not valid:
        print(f"\n⚠️ Cookie状态: {msg}")
        print("将在首次访问时提示刷新\n")
    else:
        print(f"\n✅ Cookie状态: 有效\n")
    
    print(f"📡 Web服务地址: http://localhost:{PORT}")
    print(f"📊 Dashboard: http://localhost:{PORT}/")
    print(f"🔧 状态API: http://localhost:{PORT}/api/status")
    print(f"🔄 手动刷新: http://localhost:{PORT}/api/fetch")
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    # 自动打开浏览器
    webbrowser.open(f"http://localhost:{PORT}")
    
    # 启动Web服务
    try:
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n\n正在停止服务...")
        scheduler.shutdown()
        print("服务已停止")

if __name__ == "__main__":
    main()
