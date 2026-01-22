# -*- coding: utf-8 -*-
"""
飞书云文档周报同步工具
======================
读取本地周报，与飞书云文档中的部门周报合并，并更新到飞书
"""

import os
import sys
import json
import re
import datetime
import requests
from datetime import timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# ============================================
# 路径处理
# ============================================

def get_base_path():
    """获取基础路径"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()
CONFIG_PATH = os.path.join(BASE_PATH, "feishu_config.json")
AUTH_FILE = os.path.join(BASE_PATH, "feishu_auth.json")
WEEKLY_REPORT_DIR = os.path.join(BASE_PATH, "周报")

# 默认配置
DEFAULT_CONFIG = {
    "feishu_wiki_url": "",
    "ai_api_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    "ai_model_id": "ep-20251223144447-7946z",
    "ai_api_key": "",
    "headless": False,
    "login_timeout": 120000,
    "page_timeout": 30000
}

# 合并提示词
MERGE_PROMPT = """# Role
你是一名资深产品总监，负责将个人周报内容合并到部门周报中。

# 核心规则（必须严格遵守）
1. **绝对保留**：飞书文档中其他同事已写的所有内容必须100%保留，一字不改、一条不删
2. **仅追加**：只在对应分类下追加【个人周报】中的新内容
3. **智能去重**：如果【个人周报】中的某项工作在飞书文档中已存在类似描述，则：
   - 若内容完全相同：跳过不添加
   - 若个人周报描述更详细：用个人周报的描述替换或补充
4. **保持结构**：严格保持飞书文档的原有分类结构和格式

# 输入说明
- 【飞书已有部门周报】：包含多位同事的工作内容，必须全部保留
- 【个人周报内容】：当前用户的个人周报，需要追加到对应分类

# 输出要求
1. 输出完整的合并后周报
2. 保持原有格式：日期、部门周报、本周工作内容、下周工作计划等结构
3. 个人新增的条目追加到对应分类的现有条目之后
4. 如果某个分类下原本只有序号没有内容（如"2. "），可以在此处添加

# 输出格式
直接输出合并后的完整周报，不要任何解释或说明。
"""


def load_config():
    """加载配置文件"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
                return {**DEFAULT_CONFIG, **config}
        except Exception as e:
            print(f"(WARNING) 读取配置文件失败: {e}")
    return DEFAULT_CONFIG.copy()


def save_config(config):
    """保存配置"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"(ERROR) 保存配置失败: {e}")
        return False


# ============================================
# 日期工具
# ============================================

def get_current_week_range():
    """获取本周的周一和周六"""
    today = datetime.date.today()
    monday = today - timedelta(days=today.weekday())
    saturday = monday + timedelta(days=5)
    return monday, saturday


def get_week_info():
    """获取本周信息：年份、第几周、日期范围"""
    today = datetime.date.today()
    monday = today - timedelta(days=today.weekday())
    saturday = monday + timedelta(days=5)
    year, week_num, _ = monday.isocalendar()
    return {
        "year": year,
        "week_num": week_num,
        "monday": monday,
        "saturday": saturday,
        "date_str": f"{monday.strftime('%m/%d')}-{saturday.strftime('%m/%d')}"
    }


# ============================================
# 本地周报读取
# ============================================

def find_weekly_reports(start_date, end_date):
    """查找日期范围内的周报文件"""
    if not os.path.exists(WEEKLY_REPORT_DIR):
        print(f"(WARNING) 周报目录不存在: {WEEKLY_REPORT_DIR}")
        return []
    
    reports = []
    for filename in os.listdir(WEEKLY_REPORT_DIR):
        if filename.endswith(".md") and filename.startswith("周报_"):
            # 解析文件名中的日期，格式：周报_20260117.md
            match = re.search(r'周报_(\d{8})\.md', filename)
            if match:
                date_str = match.group(1)
                try:
                    file_date = datetime.datetime.strptime(date_str, "%Y%m%d").date()
                    if start_date <= file_date <= end_date:
                        filepath = os.path.join(WEEKLY_REPORT_DIR, filename)
                        reports.append({
                            "filename": filename,
                            "filepath": filepath,
                            "date": file_date
                        })
                except ValueError:
                    continue
    
    # 按日期排序
    reports.sort(key=lambda x: x["date"])
    return reports


def read_local_reports(start_date, end_date):
    """读取本地周报内容"""
    reports = find_weekly_reports(start_date, end_date)
    if not reports:
        print("(WARNING) 未找到本周的周报文件")
        return None
    
    combined_content = []
    for report in reports:
        try:
            with open(report["filepath"], "r", encoding="utf-8") as f:
                content = f.read()
                combined_content.append(f"=== {report['filename']} ===\n{content}")
                print(f"(SUCCESS) 读取周报: {report['filename']}")
        except Exception as e:
            print(f"(ERROR) 读取文件失败 {report['filename']}: {e}")
    
    return "\n\n".join(combined_content) if combined_content else None


# ============================================
# 飞书自动化类
# ============================================

class FeishuAutomation:
    """飞书文档自动化操作"""
    
    def __init__(self, config):
        self.config = config
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
    
    def start(self):
        """启动浏览器"""
        self.playwright = sync_playwright().start()
        
        try:
            self.browser = self.playwright.chromium.launch(
                headless=self.config.get("headless", False),
                channel="chrome"
            )
            print("(SUCCESS) 已使用系统 Chrome 浏览器")
        except Exception as e:
            print(f"(WARNING) 无法使用系统 Chrome: {e}")
            self.browser = self.playwright.chromium.launch(
                headless=self.config.get("headless", False)
            )
        
        # 加载已保存的登录状态
        if os.path.exists(AUTH_FILE):
            print("(INFO) 发现已保存的飞书登录状态，尝试加载...")
            try:
                self.context = self.browser.new_context(storage_state=AUTH_FILE)
                print("(SUCCESS) 飞书登录状态加载成功")
            except Exception as e:
                print(f"(WARNING) 加载登录状态失败: {e}")
                self.context = self.browser.new_context()
        else:
            print("(INFO) 首次运行，需要登录飞书")
            self.context = self.browser.new_context()
        
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.config.get("page_timeout", 30000))
    
    def stop(self):
        """关闭浏览器"""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def save_login_state(self):
        """保存飞书登录状态"""
        try:
            self.context.storage_state(path=AUTH_FILE)
            print("(SUCCESS) 飞书登录状态已保存")
            return True
        except Exception as e:
            print(f"(ERROR) 保存登录状态失败: {e}")
            return False
    
    def check_login_and_wait(self):
        """检查登录状态，如未登录则等待扫码"""
        wiki_url = self.config.get("feishu_wiki_url")
        print(f"(INFO) 正在打开飞书文档: {wiki_url}")
        
        try:
            self.page.goto(wiki_url, timeout=60000)  # 60秒超时
            # 使用 domcontentloaded 而不是 networkidle，更快完成
            self.page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"(WARNING) 页面加载较慢: {e}")
        
        # 等待页面稳定
        self.page.wait_for_timeout(3000)
        
        current_url = self.page.url
        print(f"(DEBUG) 当前 URL: {current_url}")
        
        # 检查是否需要登录
        if "passport" in current_url or "login" in current_url:
            print("\n" + "=" * 50)
            print("请使用飞书/企业微信扫码登录")
            print("=" * 50)
            
            try:
                login_timeout = self.config.get("login_timeout", 120000)
                print(f"(INFO) 等待扫码登录（超时时间: {login_timeout // 1000} 秒）...")
                
                # 等待重定向到文档页面
                self.page.wait_for_url(
                    lambda url: "wiki" in url or "docs" in url,
                    timeout=login_timeout
                )
                
                print("(SUCCESS) 登录成功!")
                self.page.wait_for_timeout(3000)  # 等待页面稳定
                self.save_login_state()
                
                # 重新加载目标页面
                self.page.goto(wiki_url, timeout=60000)
                self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                self.page.wait_for_timeout(3000)
                
            except PlaywrightTimeout:
                print("(ERROR) 登录超时")
                return False
        else:
            print("(SUCCESS) 已处于登录状态")
            self.save_login_state()
        
        return True
    
    def get_document_content(self):
        """获取飞书文档内容"""
        print("(INFO) 正在读取飞书文档内容...")
        
        try:
            # 等待文档编辑器加载
            self.page.wait_for_selector(".ne-doc-major-editor", timeout=10000)
            self.page.wait_for_timeout(2000)  # 等待内容完全渲染
            
            # 获取文档纯文本内容
            content = self.page.evaluate("""
                () => {
                    const editor = document.querySelector('.ne-doc-major-editor');
                    if (editor) {
                        return editor.innerText;
                    }
                    return '';
                }
            """)
            
            if content:
                print(f"(SUCCESS) 读取到飞书文档内容，长度: {len(content)} 字符")
                return content
            else:
                print("(WARNING) 飞书文档内容为空")
                return ""
                
        except Exception as e:
            print(f"(ERROR) 读取飞书文档失败: {e}")
            return ""
    
    def update_document(self, new_content):
        """更新飞书文档内容（追加到文档末尾）"""
        print("(INFO) 正在更新飞书文档...")
        
        try:
            # 点击文档末尾
            self.page.evaluate("""
                () => {
                    const editor = document.querySelector('.ne-doc-major-editor');
                    if (editor) {
                        // 滚动到底部
                        editor.scrollTop = editor.scrollHeight;
                    }
                }
            """)
            self.page.wait_for_timeout(500)
            
            # 使用键盘快捷键定位到文档末尾
            self.page.keyboard.press("Control+End")
            self.page.wait_for_timeout(500)
            
            # 添加分隔符和新内容
            self.page.keyboard.press("Enter")
            self.page.keyboard.press("Enter")
            
            # 逐行输入内容
            lines = new_content.split("\n")
            for line in lines:
                self.page.keyboard.type(line)
                self.page.keyboard.press("Enter")
            
            self.page.wait_for_timeout(1000)
            print("(SUCCESS) 飞书文档内容已更新")
            return True
            
        except Exception as e:
            print(f"(ERROR) 更新飞书文档失败: {e}")
            return False


# ============================================
# AI 合并功能
# ============================================

def merge_with_ai(feishu_content, local_content, config):
    """使用AI合并飞书内容和本地周报"""
    print("(INFO) 正在使用AI合并内容...")
    
    api_url = config.get("ai_api_url")
    api_key = config.get("ai_api_key")
    model_id = config.get("ai_model_id")
    
    week_info = get_week_info()
    
    user_content = f"""
【飞书已有部门周报内容】
{feishu_content if feishu_content else "(暂无内容)"}

---

【个人周报内容】
{local_content}

---

请将以上内容合并，生成本周（{week_info['year']}年第{week_info['week_num']}周，{week_info['date_str']}）的完整部门周报。
日期填写: {week_info['saturday'].strftime('%Y-%m-%d')}
"""
    
    messages = [
        {"role": "system", "content": MERGE_PROMPT},
        {"role": "user", "content": user_content}
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
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            merged = result["choices"][0]["message"]["content"]
            print("(SUCCESS) AI合并完成")
            return merged
        else:
            print(f"(WARNING) AI响应格式异常: {result}")
            return None
            
    except requests.exceptions.Timeout:
        print("(ERROR) AI接口请求超时")
        return None
    except Exception as e:
        print(f"(ERROR) AI合并失败: {e}")
        return None


# ============================================
# 主函数
# ============================================

def main():
    print("\n" + "=" * 50)
    print("   飞书云文档周报同步工具 v1.0")
    print("=" * 50 + "\n")
    
    # 加载配置
    config = load_config()
    
    if not config.get("feishu_wiki_url"):
        print("(ERROR) 请在 feishu_config.json 中配置 feishu_wiki_url")
        input("按 Enter 键退出...")
        return
    
    # 获取本周日期范围
    start_date, end_date = get_current_week_range()
    week_info = get_week_info()
    print(f"(INFO) 本周范围: {start_date} 至 {end_date}")
    print(f"(INFO) 第 {week_info['week_num']} 周")
    
    # 读取本地周报
    print("\n[步骤1] 读取本地周报...")
    local_content = read_local_reports(start_date, end_date)
    if not local_content:
        print("(WARNING) 未找到本周的本地周报，将仅读取飞书内容")
    
    # 启动飞书自动化
    feishu = FeishuAutomation(config)
    
    try:
        print("\n[步骤2] 启动浏览器并登录飞书...")
        feishu.start()
        
        if not feishu.check_login_and_wait():
            print("(FAILED) 飞书登录失败")
            input("按 Enter 键退出...")
            return
        
        # 读取飞书现有内容
        print("\n[步骤3] 读取飞书文档内容...")
        feishu_content = feishu.get_document_content()
        
        # AI合并
        if local_content:
            print("\n[步骤4] AI合并内容...")
            merged_content = merge_with_ai(feishu_content, local_content, config)
            
            if merged_content:
                print("\n" + "-" * 50)
                print("合并后的内容预览（前500字）:")
                print("-" * 50)
                print(merged_content[:500] + "..." if len(merged_content) > 500 else merged_content)
                print("-" * 50)
                
                # 询问是否更新
                print("\n(QUESTION) 是否将合并后的内容更新到飞书文档?")
                user_input = input("输入 'y' 确认更新，其他键跳过: ").strip().lower()
                
                if user_input == 'y':
                    print("\n[步骤5] 更新飞书文档...")
                    # 这里可以实现自动更新逻辑
                    # 由于飞书编辑器的复杂性，建议先手动复制
                    print("(INFO) 合并内容已复制到剪贴板，请手动粘贴到飞书文档")
                    
                    # 将内容复制到剪贴板
                    try:
                        import pyperclip
                        pyperclip.copy(merged_content)
                        print("(SUCCESS) 已复制到剪贴板")
                    except ImportError:
                        print("(WARNING) pyperclip 未安装，无法自动复制")
                        print("请手动复制以下内容:")
                        print("=" * 50)
                        print(merged_content)
                        print("=" * 50)
                else:
                    print("(INFO) 已跳过更新")
            else:
                print("(FAILED) AI合并失败")
        else:
            print("(INFO) 无本地周报，仅显示飞书现有内容")
            print(feishu_content[:1000] if feishu_content else "(无内容)")
        
        print("\n" + "=" * 50)
        print("   同步完成!")
        print("=" * 50)
        input("\n按 Enter 键退出...")
        
    except KeyboardInterrupt:
        print("\n(INFO) 用户中断操作")
    except Exception as e:
        print(f"(ERROR) 发生异常: {e}")
        import traceback
        traceback.print_exc()
        input("按 Enter 键退出...")
    finally:
        print("(INFO) 正在关闭浏览器...")
        feishu.stop()


if __name__ == "__main__":
    main()
