
import os
import json
import time
import requests
import datetime
import webbrowser
from datetime import timedelta

# 配置文件路径
CONFIG_PATH = "config.json"
SHARED_COOKIE_FILE = r'f:\共享配置\tita_cookie.json'  # 共享Cookie文件

def load_shared_cookie():
    """从共享文件加载Cookie"""
    try:
        import os
        if os.path.exists(SHARED_COOKIE_FILE):
            with open(SHARED_COOKIE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cookie = data.get('cookie', '')
                if cookie:
                    updated_at = data.get('updated_at', '未知')
                    print(f"(信息) 使用共享Cookie (更新于: {updated_at})")
                    return cookie
    except Exception as e:
        print(f"(WARNING) 读取共享Cookie失败: {e}")
    return None

# 加载配置
def load_config():
    if not os.path.exists(CONFIG_PATH):
        print("(ERROR) 找不到配置文件 config.json")
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            config = json.load(f)
        
        # 优先从共享文件加载Cookie
        shared_cookie = load_shared_cookie()
        if shared_cookie:
            config['headers']['cookie'] = shared_cookie
        
        return config
    except Exception as e:
        print(f"(ERROR) 读取配置文件失败 - {e}")
        return None

def save_config(config):
    """保存配置到文件"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"(ERROR) 保存配置文件失败 - {e}")
        return False

def check_cookie_valid(config):
    """
    检查 Cookie 是否有效
    返回: True 如果有效, False 如果过期或无效
    """
    url = config.get("tita_api_url")
    headers = config.get("headers", {})
    payload = config.get("payload_template", {}).copy()
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        
        # 检查返回码 - Code=1 表示成功
        if data.get("Code") == 1:
            return True
        
        # 检查是否是认证失败的错误
        error_msg = data.get("Message", "").lower()
        if "login" in error_msg or "auth" in error_msg or "token" in error_msg or "session" in error_msg:
            return False
        
        # 如果 Code 不是 1，也可能是其他错误，但我们先假设 Cookie 可能有问题
        if data.get("Code") != 1:
            print(f"(WARNING) API 返回异常: {data.get('Message', '未知错误')}")
            return False
            
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"(ERROR) 网络请求失败: {e}")
        return False
    except json.JSONDecodeError:
        # 如果返回的不是 JSON，可能是登录页面 HTML
        print("(WARNING) API 返回非 JSON 数据，Cookie 可能已过期")
        return False

def update_cookie(config):
    """
    引导用户更新 Cookie
    返回: 更新后的配置，如果用户取消则返回 None
    """
    print("\n" + "=" * 50)
    print("(NOTICE) Cookie 已过期，需要更新")
    print("=" * 50)
    
    # 构造 Tita 登录页面 URL
    tita_url = "https://work-weixin.tita.com/"
    
    print(f"\n即将打开 Tita 页面: {tita_url}")
    print("请按以下步骤获取新的 Cookie:\n")
    print("  1. 在打开的浏览器中扫码登录 Tita")
    print("  2. 登录成功后，按 F12 打开开发者工具")
    print("  3. 切换到 Network (网络) 选项卡")
    print("  4. 刷新页面，点击任意一个请求")
    print("  5. 在 Headers 中找到 Cookie 字段，复制完整的值")
    print("\n" + "-" * 50)
    
    # 打开浏览器
    try:
        webbrowser.open(tita_url)
        print("(INFO) 已在浏览器中打开 Tita 页面")
    except Exception as e:
        print(f"(WARNING) 无法自动打开浏览器: {e}")
        print(f"请手动访问: {tita_url}")
    
    print("\n请粘贴新的 Cookie (输入后按 Enter):")
    print("(输入 'q' 或 'exit' 取消更新)")
    
    try:
        new_cookie = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n(CANCELLED) 用户取消了操作")
        return None
    
    if new_cookie.lower() in ["q", "exit", "quit", "cancel"]:
        print("(CANCELLED) 用户取消了更新")
        return None
    
    if not new_cookie:
        print("(ERROR) Cookie 不能为空")
        return None
    
    # 更新配置
    config["headers"]["cookie"] = new_cookie
    
    # 保存到文件
    if save_config(config):
        print("(SUCCESS) 新 Cookie 已保存到 config.json")
        return config
    else:
        print("(ERROR) 保存配置失败，请手动更新 config.json")
        return None

CONFIG = load_config()

def get_current_week_range():
    """获取本周的周一（开始）和周六（结束）"""
    today = datetime.date.today()
    start_of_week = today - timedelta(days=today.weekday())  # 周一
    end_of_week = start_of_week + timedelta(days=5)  # 周六
    return start_of_week, end_of_week

def fetch_daily_reports(start_date, end_date, config):
    """从 Tita API 获取日报并按日期筛选"""
    if not config:
        return []

    url = config.get("tita_api_url")
    headers = config.get("headers", {})
    payload = config.get("payload_template", {}).copy()
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        if data.get("Code") != 1:
            print(f"(ERROR) 获取数据错误: {data.get('Message')}")
            return []
            
        feeds = data.get("Data", {}).get("feeds", [])
        filtered_reports = []
        
        for feed in feeds:
            # 解析日期格式 "2026/01/08"
            daily_date_str = feed.get("dailyDate", "")
            if not daily_date_str:
                continue
                
            try:
                daily_date = datetime.datetime.strptime(daily_date_str, "%Y/%m/%d").date()
            except ValueError:
                continue
            
            if start_date <= daily_date <= end_date:
                report_content = ""
                # 提取板块
                daily_content = feed.get("dailyContent", [])
                for section in daily_content:
                    title = section.get("title", "")
                    content = section.get("content", "")
                    if title in ["今日工作总结", "明日工作计划"] and content:
                        report_content += f"[{title}]: {content}\n"
                
                if report_content:
                    filtered_reports.append(f"日期: {daily_date_str}\n{report_content}")
                    
        return sorted(filtered_reports, reverse=False) # 升序排列
        
    except Exception as e:
        print(f"(ERROR) 获取日报时发生异常: {e}")
        return []

def generate_summary(reports_text, prompt_template, config):
    """调用火山引擎 AI 生成汇总"""
    if not config:
        return None

    api_url = config.get("ai_api_url")
    api_key = config.get("ai_api_key")
    model_id = config.get("ai_model_id")

    messages = [
        {"role": "system", "content": prompt_template},
        {"role": "user", "content": f"以下是本周的日报记录，请汇总生成周报：\n\n{reports_text}"}
    ]
    
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.3
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        print("(INFO) 正在发送请求给 AI 模型，请稍候...")
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        
        # 检查响应
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            print(f"(WARNING) AI 响应格式异常: {result}")
            return None
            
    except Exception as e:
        print(f"(ERROR) 调用 AI 接口失败: {e}")
        return None

def main():
    global CONFIG
    
    if not CONFIG:
        return

    print("=== 自动周报生成器启动 ===")
    
    # 0. 检查 Cookie 是否有效
    print("(INFO) 正在验证 Cookie...")
    if not check_cookie_valid(CONFIG):
        print("(WARNING) Cookie 已过期或无效")
        CONFIG = update_cookie(CONFIG)
        if not CONFIG:
            print("(FAILED) 无法更新 Cookie，程序退出")
            return
        # 重新验证
        if not check_cookie_valid(CONFIG):
            print("(FAILED) 新 Cookie 仍然无效，请检查是否复制正确")
            return
        print("(SUCCESS) Cookie 验证通过!")
    else:
        print("(SUCCESS) Cookie 有效")
    
    # 1. 获取日期
    start_date, end_date = get_current_week_range()
    print(f"(INFO) 生成范围: {start_date} 至 {end_date}")
    
    # 2. 获取日报
    print("(INFO) 正在从 Tita 获取日报...")
    reports = fetch_daily_reports(start_date, end_date, CONFIG)
    if not reports:
        print("(WARNING) 未找到本周的日报记录。")
        print("(TIPS) 请检查：1. 是否已写日报；2. 日期范围是否正确。")
        return

    reports_text = "\n---\n".join(reports)
    print(f"(SUCCESS) 成功获取 {len(reports)} 条日报记录。")
    
    # 3. 读取提示词
    try:
        with open("提示词.md", "r", encoding="utf-8-sig") as f:
            prompt_template = f.read()
    except FileNotFoundError:
        print("(ERROR) 找不到文件 '提示词.md'。")
        return

    # 4. 生成汇总
    summary = generate_summary(reports_text, prompt_template, CONFIG)
    
    if summary:
        # 5. 保存结果
        output_dir = CONFIG.get("output_dir", "周报")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        filename = f"{output_dir}/周报_{datetime.date.today().strftime('%Y%m%d')}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(summary)
            
        print("--------------------------------------------------")
        print("(DONE) 周报已生成！")
        print(f"文件位置: {os.path.abspath(filename)}")
        print("--------------------------------------------------")
    else:
        print("(FAILED) 生成周报失败。")

if __name__ == "__main__":
    main()
