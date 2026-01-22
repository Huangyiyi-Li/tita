"""
Cookie刷新工具 - 使用Selenium打开Tita登录页面获取新Cookie

功能：
1. 自动打开Tita登录页面
2. 显示企业微信扫码界面
3. 用户扫码后自动获取Cookie
4. 保存Cookie到config.json

使用方式：
python cookie_refresher.py
"""

import json
import time
import sys
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("❌ 缺少Selenium库，请先安装:")
    print("   pip install selenium")
    sys.exit(1)

# 配置
CONFIG_FILE = 'config.json'
TITA_LOGIN_URL = "https://work-weixin.tita.com"

# Cookie过期提示的关键标识
LOGIN_PAGE_INDICATORS = [
    "扫码登录",
    "企业微信登录",
    "qrcode",
    "login"
]

# 登录成功后的页面标识
SUCCESS_INDICATORS = [
    "/home",
    "/weixin/pc/home",
    "pc/home"
]

def get_config_path():
    """获取配置文件路径，支持从工具脚本目录或项目根目录运行"""
    # 首先尝试当前脚本的父目录的父目录（如果在工具脚本目录中）
    script_dir = Path(__file__).parent
    
    # 尝试路径1: 项目根目录 (../config.json)
    path1 = script_dir.parent / CONFIG_FILE
    if path1.exists():
        return path1
    
    # 尝试路径2: 当前目录 (./config.json)
    path2 = script_dir / CONFIG_FILE
    if path2.exists():
        return path2
    
    # 尝试路径3: 工作目录
    path3 = Path.cwd() / CONFIG_FILE
    if path3.exists():
        return path3
    
    # 默认返回项目根目录路径
    return path1

def load_config():
    """加载配置文件"""
    config_path = get_config_path()
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config):
    """保存配置文件"""
    config_path = get_config_path()
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def format_cookies_for_header(cookies):
    """将Selenium cookies格式化为请求头格式"""
    cookie_parts = []
    for cookie in cookies:
        cookie_parts.append(f"{cookie['name']}={cookie['value']}")
    return "; ".join(cookie_parts)


def create_driver():
    """创建Chrome WebDriver"""
    options = Options()
    
    # 基本设置
    options.add_argument('--start-maximized')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    
    # 尝试多种方式创建driver
    try:
        # 方式1: 使用系统PATH中的chromedriver
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e1:
        print(f"尝试方式1失败: {e1}")
        
        try:
            # 方式2: 使用webdriver_manager自动管理
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            return driver
        except ImportError:
            print("提示: 可以安装 webdriver_manager 自动管理驱动")
            print("   pip install webdriver-manager")
        except Exception as e2:
            print(f"尝试方式2失败: {e2}")
        
        try:
            # 方式3: 使用Edge浏览器
            from selenium.webdriver.edge.options import Options as EdgeOptions
            from selenium.webdriver.edge.service import Service as EdgeService
            
            edge_options = EdgeOptions()
            edge_options.add_argument('--start-maximized')
            driver = webdriver.Edge(options=edge_options)
            print("使用Edge浏览器")
            return driver
        except Exception as e3:
            print(f"尝试方式3 (Edge) 失败: {e3}")
    
    return None


def wait_for_login(driver, timeout=300):
    """
    等待用户完成扫码登录
    
    Args:
        driver: WebDriver实例
        timeout: 超时时间(秒)，默认5分钟
    
    Returns:
        bool: 是否登录成功
    """
    print("\n⏳ 等待扫码登录...")
    print(f"   (超时时间: {timeout}秒)")
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        current_url = driver.current_url
        
        # 检查是否已跳转到成功页面
        for indicator in SUCCESS_INDICATORS:
            if indicator in current_url:
                print("\n✅ 检测到登录成功!")
                return True
        
        # 每2秒检查一次
        time.sleep(2)
        
        # 显示进度
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0:
            print(f"   已等待 {elapsed} 秒...")
    
    print("\n⏰ 等待超时")
    return False


def extract_and_save_cookies(driver, config):
    """
    提取Cookie并保存到配置文件
    
    Args:
        driver: WebDriver实例
        config: 配置字典
    
    Returns:
        bool: 是否成功保存
    """
    try:
        # 等待页面完全加载
        time.sleep(3)
        
        # 获取所有cookies
        cookies = driver.get_cookies()
        
        if not cookies:
            print("❌ 未获取到任何Cookie")
            return False
        
        # 格式化为请求头格式
        cookie_string = format_cookies_for_header(cookies)
        
        print(f"\n📦 获取到 {len(cookies)} 个Cookie:")
        for cookie in cookies:
            print(f"   - {cookie['name']}")
        
        # 更新配置
        old_cookie = config['headers'].get('cookie', '')
        config['headers']['cookie'] = cookie_string
        
        # 保存配置
        save_config(config)
        
        print("\n💾 Cookie已保存到 config.json")
        print(f"\n新Cookie: {cookie_string[:80]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 保存Cookie失败: {e}")
        return False


def main():
    success = False
    print("=" * 50)
    print("[TOOL] Tita Cookie刷新工具")
    print("=" * 50)
    
    # 加载配置
    try:
        config = load_config()
    except FileNotFoundError:
        print(f"[FAIL] 配置文件 {CONFIG_FILE} 不存在!")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[FAIL] 配置文件格式错误: {e}")
        sys.exit(1)
    
    # 创建浏览器
    print("\n[INFO] 启动浏览器...")
    driver = create_driver()
    
    if not driver:
        print("[FAIL] 无法启动浏览器!")
        print("\n请确保:")
        print("  1. 已安装Chrome或Edge浏览器")
        print("  2. 安装chromedriver: pip install webdriver-manager")
        sys.exit(1)
    
    try:
        # 打开Tita登录页面
        print(f"\n📍 打开登录页面: {TITA_LOGIN_URL}")
        driver.get(TITA_LOGIN_URL)
        
        print("\n" + "=" * 50)
        print("📱 请使用企业微信扫描二维码登录")
        print("=" * 50)
        
        # 等待登录
        if wait_for_login(driver):
            # 提取并保存Cookie
            if extract_and_save_cookies(driver, config):
                print("\n[OK] Cookie刷新成功!")
                success = True
            else:
                print("\n[FAIL] Cookie保存失败")
        else:
            print("\n[FAIL] 登录超时或取消")
    
    except KeyboardInterrupt:
        print("\n\n[WARN] 用户取消操作")
    
    except Exception as e:
        print(f"\n[FAIL] 发生错误: {e}")
    
    finally:
        # 关闭浏览器
        print("\n[INFO] 关闭浏览器...")
        try:
            driver.quit()
        except:
            pass
    
    print("\n" + "=" * 50)
    
    # 检查是否为自动模式（被其他脚本调用时）
    if "--auto" not in sys.argv:
        input("按回车键退出...")
    
    # 返回正确的退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

