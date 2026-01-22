# -*- coding: utf-8 -*-
"""
Playwright 自动周报生成器 (可打包版)
===================================
使用系统已安装的 Chrome 浏览器，无需额外下载 Chromium
支持 PyInstaller 打包成独立 exe
"""

import os
import sys
import json
import datetime
import requests
from datetime import timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ============================================
# 路径处理（支持 PyInstaller 打包）
# ============================================

def get_base_path():
    """获取基础路径，支持 PyInstaller 打包后的路径"""
    if getattr(sys, 'frozen', False):
        # 打包后的 exe 运行
        return os.path.dirname(sys.executable)
    else:
        # 普通 Python 脚本运行
        return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()
CONFIG_PATH = os.path.join(BASE_PATH, "playwright_config.json")
AUTH_FILE = os.path.join(BASE_PATH, "auth.json")
PROMPT_FILE = os.path.join(BASE_PATH, "提示词.md")
OUTPUT_DIR = os.path.join(BASE_PATH, "周报")

# 默认配置（user_id 和 org_id 会在首次登录后自动获取）
DEFAULT_CONFIG = {
    "tita_base_url": "https://work-weixin.tita.com",
    "user_id": "",  # 用户 ID，首次登录后自动获取
    "org_id": "",   # 组织 ID，首次登录后自动获取
    "ai_api_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    "ai_model_id": "ep-20251223144447-7946z",
    "ai_api_key": "12f6605e-5f2b-48e2-80e4-0f937557ec1a",
    "headless": False,
    "auto_submit": True,
    "login_timeout": 120000,
    "page_timeout": 30000
}

# 默认提示词（内置，当外部文件不存在时使用）
DEFAULT_PROMPT = """# Role
你是一名资深产品总监。你的核心任务是将用户提供的繁杂日报记录进行分类、去重、合并与提炼，生成一份语言精炼、逻辑清晰的周工作总结。

# Constraints & Formatting
1. **严格禁止 Markdown**：输出内容必须是纯文本格式。绝对不要使用 markdown 符号（如 **加粗**、## 标题、- 列表等）。
2. **文本排版规范**：
   - 标题：使用双冒号包裹，例如：:: 本周工作总结 ::。
   - 分点：使用数字序号（1. 2. 3.）。
   - 换行：不同板块之间必须空一行，以确保阅读舒适度。
3. **完整性**：不得遗漏用户提供的任何关键工作信息。
4. **语言风格**：专业、客观、高效，拒绝口语化和寒暄。

# Workflow
1. 接收用户提供的一周日报记录。
2. 以“资深产品总监”视角，对内容进行逻辑梳理、去重和专业化润色。
3. 按照以下结构输出纯文本周报：

   :: 本周工作总结 ::
   （按项目或事项分类，概括核心产出）

   :: 下周工作计划 ::
   （列出重点目标和计划）

   :: 问题与风险 ::
   （识别当前的堵点或风险，若无则不写此项）

# Initialization
直接输出最终生成的周报内容，不要包含任何“好的”、“收到”、“以下是周报”等额外语句。"""


def load_prompt():
    """加载提示词，优先读取外部文件，不存在则使用内置默认值"""
    if os.path.exists(PROMPT_FILE):
        try:
            with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                prompt = f.read().strip()
                if prompt:
                    print(f"(INFO) 使用外部提示词文件: {PROMPT_FILE}")
                    return prompt
        except Exception as e:
            print(f"(WARNING) 读取提示词文件失败: {e}")
    
    print("(INFO) 使用内置默认提示词")
    return DEFAULT_PROMPT


def load_config():
    """加载配置文件"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
                return {**DEFAULT_CONFIG, **config}
        except Exception as e:
            print(f"(WARNING) 读取配置文件失败: {e}，使用默认配置")
    return DEFAULT_CONFIG.copy()


def save_config(config):
    """保存配置到文件"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"(ERROR) 保存配置文件失败: {e}")
        return False


# ============================================
# Tita 自动化类
# ============================================

class TitaAutomation:
    """Tita 平台自动化操作类"""
    
    def __init__(self, config):
        self.config = config
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
    
    def start(self):
        """启动浏览器 - 使用系统已安装的 Chrome"""
        self.playwright = sync_playwright().start()
        
        # 使用系统安装的 Chrome 浏览器
        # channel="chrome" 会自动查找系统中的 Chrome
        try:
            self.browser = self.playwright.chromium.launch(
                headless=self.config.get("headless", False),
                channel="chrome"  # 使用系统 Chrome
            )
            print("(SUCCESS) 已使用系统 Chrome 浏览器")
        except Exception as e:
            print(f"(WARNING) 无法使用系统 Chrome: {e}")
            print("(INFO) 尝试使用 Playwright 内置浏览器...")
            self.browser = self.playwright.chromium.launch(
                headless=self.config.get("headless", False)
            )
        
        # 检查是否有保存的登录状态
        if os.path.exists(AUTH_FILE):
            print("(INFO) 发现已保存的登录状态，尝试加载...")
            try:
                self.context = self.browser.new_context(storage_state=AUTH_FILE)
                print("(SUCCESS) 登录状态加载成功")
            except Exception as e:
                print(f"(WARNING) 加载登录状态失败: {e}，需要重新登录")
                self.context = self.browser.new_context()
        else:
            print("(INFO) 首次运行，需要扫码登录")
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
    
    def check_login_state(self):
        """检查是否已登录"""
        try:
            self.page.goto(self.config.get("tita_base_url"))
            self.page.wait_for_load_state("networkidle", timeout=15000)
            
            current_url = self.page.url
            print(f"(DEBUG) 当前 URL: {current_url}")
            
            # 如果 URL 包含这些关键词，说明需要登录
            if "login" in current_url.lower() or "qrcode" in current_url.lower():
                return False
            
            # 如果 URL 包含这些关键词，说明已登录
            if any(keyword in current_url for keyword in ['/home', '/okr', '/weixin/pc', '/summary', '/task']):
                print("(DEBUG) URL 表明已登录")
                self.save_login_state()  # 保存登录状态
                return True
            
            # 尝试通过 API 验证
            return self._verify_login_via_api()
                    
        except Exception as e:
            print(f"(WARNING) 检查登录状态时出错: {e}")
            return False
    
    def _verify_login_via_api(self):
        """通过 API 验证登录状态"""
        try:
            api_url = self.get_api_url()
            result = self.page.evaluate("""
                async (apiUrl) => {
                    try {
                        const response = await fetch(apiUrl, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                "pageNum": 1, "pageSize": 1,
                                "relation": 1, "summaryType": 8
                            })
                        });
                        const data = await response.json();
                        return data.Code === 1;
                    } catch (e) { return false; }
                }
            """, api_url)
            return result
        except Exception:
            return False
    
    def login_with_qrcode(self):
        """等待用户扫码登录"""
        print("\n" + "=" * 50)
        print("请使用企业微信扫描二维码登录")
        print("=" * 50)
        
        self.page.goto(self.config.get("tita_base_url"))
        
        try:
            login_timeout = self.config.get("login_timeout", 120000)
            print(f"(INFO) 等待扫码登录（超时时间: {login_timeout // 1000} 秒）...")
            
            self.page.wait_for_function(
                """() => {
                    const url = window.location.href;
                    return !url.includes('login') && !url.includes('qrcode') && 
                           (document.querySelector('.home-container') || 
                            document.querySelector('.user-avatar') ||
                            document.querySelector('.nav-user') ||
                            url.includes('/home') ||
                            url.includes('/weixin/pc'));
                }""",
                timeout=login_timeout
            )
            
            print("(SUCCESS) 扫码登录成功!")
            self.save_login_state()
            self._extract_and_save_user_id()  # 提取并保存用户 ID
            return True
            
        except PlaywrightTimeout:
            print("(ERROR) 扫码登录超时，请重试")
            return False
        except Exception as e:
            print(f"(ERROR) 登录过程出错: {e}")
            return False
    
    def save_login_state(self):
        """保存登录状态到文件"""
        try:
            self.context.storage_state(path=AUTH_FILE)
            print(f"(SUCCESS) 登录状态已保存")
            return True
        except Exception as e:
            print(f"(ERROR) 保存登录状态失败: {e}")
            return False
    
    def _extract_and_save_user_id(self):
        """从当前 URL 提取用户 ID 和组织 ID 并保存到配置"""
        import re
        try:
            current_url = self.page.url
            print(f"(DEBUG) 正在从 URL 提取用户信息: {current_url}")
            
            # URL 格式通常是: https://work-weixin.tita.com/{user_id}/weixin/pc/home
            # 例如: https://work-weixin.tita.com/500866233/weixin/pc/home
            match = re.search(r'work-weixin\.tita\.com/(\d+)/', current_url)
            if match:
                user_id = match.group(1)
                print(f"(SUCCESS) 提取到用户 ID: {user_id}")
                
                # 尝试从页面获取 org_id（从 API URL 中获取）
                org_id = self._get_org_id(user_id)
                
                # 更新配置
                self.config["user_id"] = user_id
                if org_id:
                    self.config["org_id"] = org_id
                
                # 保存配置到文件
                self._save_config()
                return True
            else:
                print("(WARNING) 无法从 URL 提取用户 ID")
                return False
        except Exception as e:
            print(f"(ERROR) 提取用户 ID 时出错: {e}")
            return False
    
    def _get_org_id(self, user_id):
        """尝试获取组织 ID"""
        try:
            # 尝试通过页面请求获取 org_id
            # 通常 API URL 格式是: /api/v1/{org_id}/{user_id}/summary/search
            result = self.page.evaluate("""
                async () => {
                    try {
                        // 尝试从页面的网络请求中获取 org_id
                        // 或者从页面的全局变量中获取
                        if (window.__TITA_CONFIG__ && window.__TITA_CONFIG__.orgId) {
                            return window.__TITA_CONFIG__.orgId;
                        }
                        return null;
                    } catch (e) { return null; }
                }
            """)
            if result:
                print(f"(SUCCESS) 获取到组织 ID: {result}")
                return str(result)
            else:
                # 使用默认的 org_id（从原始配置中提取）
                return "569403"
        except Exception:
            return "569403"
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            print(f"(SUCCESS) 配置已保存到 {CONFIG_PATH}")
        except Exception as e:
            print(f"(ERROR) 保存配置失败: {e}")
    
    def get_api_url(self):
        """获取 API URL，使用动态的用户 ID"""
        base_url = self.config.get("tita_base_url")
        user_id = self.config.get("user_id", "")
        org_id = self.config.get("org_id", "569403")
        
        if user_id:
            return f"{base_url}/api/v1/{org_id}/{user_id}/summary/search"
        else:
            # 回退到旧配置兼容
            return self.config.get("tita_api_url", f"{base_url}/api/v1/569403/500866233/summary/search")
    
    def _close_popups(self):
        """关闭 Tita 的功能弹窗/引导弹窗"""
        try:
            # 精确的关闭按钮选择器
            close_selectors = [
                # AI 帮你写总结弹窗的关闭按钮
                ".tita-summary-guide__close",
                "div.tita-summary-guide__close",
                ".tita-summary-guide__close span",
                "span.tui-icon-canceled",
                ".tui-icon-canceled",
                # 其他可能的关闭按钮
                ".tita-modal-close",
                ".tita-drawer-close",
                "button:has-text('我知道了')",
                "button:has-text('知道了')",
                "button:has-text('跳过')",
            ]
            
            for selector in close_selectors:
                try:
                    close_btn = self.page.locator(selector)
                    if close_btn.count() > 0 and close_btn.first.is_visible():
                        print(f"(INFO) 关闭弹窗: {selector}")
                        close_btn.first.click()
                        self.page.wait_for_timeout(500)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False
    
    def _close_all_popups(self):
        """循环关闭所有可能的弹窗"""
        max_attempts = 5
        for _ in range(max_attempts):
            if not self._close_popups():
                break
            self.page.wait_for_timeout(300)
    
    def fetch_daily_reports(self, start_date, end_date):
        """获取日报数据"""
        print(f"(INFO) 正在获取日报: {start_date} 至 {end_date}")
        
        try:
            api_url = self.get_api_url()  # 使用动态 API URL
            base_url = self.config.get("tita_base_url")
            
            # 确保在正确的域名下，避免跨域问题
            current_url = self.page.url
            if base_url not in current_url:
                print(f"(INFO) 导航到 {base_url} ...")
                self.page.goto(base_url)
                self.page.wait_for_load_state("networkidle", timeout=10000)
            
            result = self.page.evaluate("""
                async (apiUrl) => {
                    try {
                        const response = await fetch(apiUrl, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            },
                            credentials: 'include',
                            body: JSON.stringify({
                                "pageNum": 1, "pageSize": 20,
                                "relation": 1, "summaryType": 8,
                                "startTime": "", "endTime": "",
                                "searchDepartmentIds": [""],
                                "searchUserIds": [""],
                                "searchGroupIds": [""]
                            })
                        });
                        return await response.json();
                    } catch (e) { return { error: e.message }; }
                }
            """, api_url)
            
            if "error" in result:
                print(f"(ERROR) 获取日报失败: {result['error']}")
                return []
            
            if result.get("Code") != 1:
                print(f"(ERROR) API 返回错误: {result.get('Message', '未知错误')}")
                return []
            
            feeds = result.get("Data", {}).get("feeds", [])
            filtered_reports = []
            
            for feed in feeds:
                daily_date_str = feed.get("dailyDate", "")
                if not daily_date_str:
                    continue
                
                try:
                    daily_date = datetime.datetime.strptime(daily_date_str, "%Y/%m/%d").date()
                except ValueError:
                    continue
                
                if start_date <= daily_date <= end_date:
                    report_content = ""
                    daily_content = feed.get("dailyContent", [])
                    
                    for section in daily_content:
                        title = section.get("title", "")
                        content = section.get("content", "")
                        if title in ["今日工作总结", "明日工作计划"] and content:
                            content = content.replace("#tita-n#", "\n- ")
                            report_content += f"[{title}]: {content}\n"
                    
                    if report_content:
                        filtered_reports.append(f"日期: {daily_date_str}\n{report_content}")
            
            print(f"(SUCCESS) 获取到 {len(filtered_reports)} 条日报")
            return sorted(filtered_reports)
            
        except Exception as e:
            print(f"(ERROR) 获取日报时发生异常: {e}")
            return []
    
    def submit_weekly_report(self, report_content):
        """自动提交周报到 Tita"""
        print("(INFO) 正在准备提交周报...")
        
        try:
            # 使用正确的周报创建页面 URL
            # currentTime 格式: 月份-第几周，如 01-02 表示1月第2周
            # Tita 规则：一周归属于周一所在的月份
            base_url = self.config.get('tita_base_url')
            today = datetime.date.today()
            
            # 获取本周一的日期
            monday = today - timedelta(days=today.weekday())
            
            # 这一周归属于周一所在的月份
            week_month = monday.month
            
            # 计算这是该月的第几周
            # 找到该月第一个周一
            first_day_of_month = monday.replace(day=1)
            first_monday = first_day_of_month + timedelta(days=(7 - first_day_of_month.weekday()) % 7)
            
            # 如果第一天就是周一，first_monday 就是第一天
            if first_day_of_month.weekday() == 0:
                first_monday = first_day_of_month
            
            # 计算当前周一是该月的第几个周一
            week_of_month = (monday - first_monday).days // 7 + 1
            
            # 格式化为 "月份-周数"，如 "01-02"
            current_time = f"{week_month:02d}-{week_of_month:02d}"
            print(f"(DEBUG) 本周一: {monday}, 归属: {week_month}月第{week_of_month}周, currentTime: {current_time}")
            
            # 使用动态用户 ID
            user_id = self.config.get("user_id", "")
            if not user_id:
                print("(ERROR) 未找到用户 ID，请先登录")
                return False
            
            weekly_url = f"{base_url}/{user_id}/weixin/pc/home#/summary/template?isCreate=true&hideNavTop=true&reportType=26&currentTime={current_time}&templateId=80&activeKey=week"
            
            print(f"(INFO) 打开周报页面: {weekly_url}")
            self.page.goto(weekly_url)
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(2000)  # 等待页面完全渲染
            
            print("(INFO) 等待周报编辑器加载...")
            
            # 等待 ProseMirror 编辑器出现
            try:
                self.page.wait_for_selector(".ProseMirror", timeout=10000)
                print("(SUCCESS) 找到 ProseMirror 编辑器")
            except PlaywrightTimeout:
                print("(ERROR) 编辑器加载超时")
                print(f"(INFO) 周报内容已准备好，请复制以下内容:\n\n{report_content}")
                input("按 Enter 键继续...")
                return False
            
            # 关闭可能出现的 AI 功能引导弹窗
            self._close_all_popups()
            
            # 解析周报内容，分离"本周工作总结"和"下周工作计划"
            this_week_content = report_content
            next_week_content = ""
            
            # 尝试分割内容
            if "下周工作计划" in report_content:
                parts = report_content.split("下周工作计划")
                if len(parts) >= 2:
                    this_week_content = parts[0].strip()
                    next_week_content = "下周工作计划" + parts[1].strip()
            elif "**下周" in report_content:
                parts = report_content.split("**下周")
                if len(parts) >= 2:
                    this_week_content = parts[0].strip()
                    next_week_content = "**下周" + parts[1].strip()
            
            # 填写本周工作总结（第一个 ProseMirror 编辑器）
            print("(INFO) 正在填写本周工作总结...")
            editor_this_week = self.page.locator(".ProseMirror").nth(0)
            editor_this_week.click()
            self.page.wait_for_timeout(300)
            self.page.keyboard.press("Control+a")
            self.page.keyboard.press("Delete")
            
            # 逐行输入内容
            for line in this_week_content.split("\n"):
                self.page.keyboard.type(line)
                self.page.keyboard.press("Enter")
            
            print("(SUCCESS) 本周工作总结已填写")
            
            # 如果有下周工作计划，填写第二个编辑器
            if next_week_content:
                print("(INFO) 正在填写下周工作计划...")
                try:
                    editor_next_week = self.page.locator(".ProseMirror").nth(1)
                    if editor_next_week.count() > 0:
                        editor_next_week.click()
                        self.page.wait_for_timeout(300)
                        self.page.keyboard.press("Control+a")
                        self.page.keyboard.press("Delete")
                        
                        for line in next_week_content.split("\n"):
                            self.page.keyboard.type(line)
                            self.page.keyboard.press("Enter")
                        
                        print("(SUCCESS) 下周工作计划已填写")
                except Exception as e:
                    print(f"(WARNING) 填写下周计划时出错: {e}")
            
            # 关闭可能出现的功能弹窗
            self._close_popups()
            
            # 滚动到底部找提交按钮
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(500)
            
            # 提交周报
            if self.config.get("auto_submit", False):
                print("(INFO) 正在查找提交按钮...")
                
                # 尝试多种方式找提交按钮
                submit_selectors = [
                    ".tita-summary-template__submit",
                    "span:has-text('提交')",
                    "button:has-text('提交')",
                    ".submit-btn"
                ]
                
                submit_btn = None
                for selector in submit_selectors:
                    try:
                        btn = self.page.locator(selector)
                        if btn.count() > 0:
                            submit_btn = btn.first
                            break
                    except Exception:
                        continue
                
                if submit_btn:
                    print("(INFO) 找到提交按钮，正在提交...")
                    submit_btn.click()
                    self.page.wait_for_timeout(1500)
                    
                    # 处理提交确认弹窗 "确认提交此总结吗？"
                    print("(INFO) 检查是否有确认弹窗...")
                    
                    # 等待确认弹窗出现
                    try:
                        # 先等待弹窗出现
                        self.page.wait_for_selector("text=确认提交此总结吗", timeout=3000)
                        print("(INFO) 检测到确认弹窗")
                    except Exception:
                        print("(DEBUG) 未检测到确认弹窗文字，尝试直接查找确认按钮")
                    
                    # 查找并点击确认按钮（蓝色的"确认"按钮）
                    try:
                        # 精确的选择器 - 确认弹窗内的确认按钮
                        confirm_selectors = [
                            # 精确匹配 Tita 确认弹窗的确认按钮
                            "span.titaui-dialog-confirm__btn-sure-text",
                            ".titaui-dialog-confirm__btn-sure-text",
                            # 包含确认文字的按钮父元素
                            ".titaui-dialog-confirm__btn-sure",
                            # 备选选择器
                            ".tita-modal button:has-text('确认')",
                            "button.tita-btn--primary:has-text('确认')",
                        ]
                        
                        clicked = False
                        for selector in confirm_selectors:
                            try:
                                confirm_btn = self.page.locator(selector)
                                if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                                    print(f"(INFO) 找到确认按钮: {selector}")
                                    confirm_btn.first.click()
                                    self.page.wait_for_timeout(2000)
                                    clicked = True
                                    break
                            except Exception:
                                continue
                        
                        if not clicked:
                            # 最后的备选方案：用 JavaScript 查找并点击
                            print("(INFO) 尝试使用 JavaScript 点击确认按钮...")
                            self.page.evaluate("""
                                () => {
                                    const buttons = document.querySelectorAll('button');
                                    for (const btn of buttons) {
                                        if (btn.innerText.includes('确认') && btn.offsetParent !== null) {
                                            btn.click();
                                            return true;
                                        }
                                    }
                                    return false;
                                }
                            """)
                            self.page.wait_for_timeout(2000)
                            
                    except Exception as e:
                        print(f"(WARNING) 处理确认弹窗时出错: {e}")
                    
                    print("(SUCCESS) 周报已提交!")
                    return True
                else:
                    print("(WARNING) 未找到提交按钮，请手动提交")
                    input("按 Enter 键继续...")
                    return False
            else:
                print("(INFO) auto_submit 设置为 False，请手动检查并提交")
                print("(INFO) 浏览器将保持打开状态，请手动操作...")
                input("按 Enter 键继续...")
                return True
                
        except Exception as e:
            print(f"(ERROR) 提交周报时发生异常: {e}")
            import traceback
            traceback.print_exc()
            return False


# ============================================
# AI 总结功能
# ============================================

def load_prompt_template():
    """加载提示词模板"""
    return load_prompt()


def generate_ai_summary(reports_text, config):
    """调用 AI 接口生成周报总结"""
    print("(INFO) 正在调用 AI 生成周报总结...")
    
    api_url = config.get("ai_api_url")
    api_key = config.get("ai_api_key")
    model_id = config.get("ai_model_id")
    
    prompt_template = load_prompt_template()
    
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
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            summary = result["choices"][0]["message"]["content"]
            print("(SUCCESS) AI 总结生成成功")
            return summary
        else:
            print(f"(WARNING) AI 响应格式异常: {result}")
            return None
            
    except requests.exceptions.Timeout:
        print("(ERROR) AI 接口请求超时")
        return None
    except Exception as e:
        print(f"(ERROR) 调用 AI 接口失败: {e}")
        return None


# ============================================
# 主函数
# ============================================

def get_current_week_range():
    """获取本周的周一（开始）和周六（结束）"""
    today = datetime.date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=5)
    return start_of_week, end_of_week


def save_report_to_file(report_content):
    """保存周报到本地文件"""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    filename = os.path.join(OUTPUT_DIR, f"周报_{datetime.date.today().strftime('%Y%m%d')}.md")
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"(SUCCESS) 周报已保存到: {filename}")
        return filename
    except Exception as e:
        print(f"(ERROR) 保存周报文件失败: {e}")
        return None


def main():
    """主函数"""
    print("\n" + "=" * 50)
    print("   Playwright 自动周报生成器 v2.0")
    print("   使用系统 Chrome 浏览器")
    print("=" * 50 + "\n")
    
    config = load_config()
    tita = TitaAutomation(config)
    
    try:
        print("(INFO) 正在启动浏览器...")
        tita.start()
        
        print("(INFO) 正在检查登录状态...")
        if not tita.check_login_state():
            if not tita.login_with_qrcode():
                print("(FAILED) 登录失败，程序退出")
                input("按 Enter 键退出...")
                return
        else:
            print("(SUCCESS) 已登录")
        
        start_date, end_date = get_current_week_range()
        print(f"(INFO) 周报范围: {start_date} 至 {end_date}")
        
        reports = tita.fetch_daily_reports(start_date, end_date)
        if not reports:
            print("(WARNING) 未找到本周的日报记录")
            print("(TIPS) 请检查：1. 是否已写日报；2. 日期范围是否正确")
            input("按 Enter 键退出...")
            return
        
        reports_text = "\n---\n".join(reports)
        print(f"(INFO) 日报内容预览:\n{reports_text[:500]}...")
        
        summary = generate_ai_summary(reports_text, config)
        if not summary:
            print("(FAILED) 生成周报失败")
            input("按 Enter 键退出...")
            return
        
        print("\n" + "-" * 50)
        print("生成的周报内容:")
        print("-" * 50)
        print(summary)
        print("-" * 50 + "\n")
        
        save_report_to_file(summary)
        
        if config.get("auto_submit", False):
            tita.submit_weekly_report(summary)
        else:
            print("\n(INFO) auto_submit 设置为 False，跳过自动提交")
            user_input = input("\n是否打开 Tita 页面手动提交? (y/n): ").strip().lower()
            if user_input == 'y':
                tita.submit_weekly_report(summary)
        
        print("\n" + "=" * 50)
        print("   周报生成完成!")
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
        tita.stop()


if __name__ == "__main__":
    main()
