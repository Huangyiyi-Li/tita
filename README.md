# 自动周报生成器 (Weekly Report Automation)

本项目用于自动抓取 Tita 平台的日报（本周一至周六），并使用火山引擎 AI 大模型汇总生成结构化的周报。

## 📁 目录结构

*   `weekly_report_generator.py`: 核心脚本（Python 版）。
*   `weekly_report_generator.ps1`: 核心脚本（PowerShell 版，无需 Python）。
*   `run_report.bat`: 启动脚本（运行 Python 版）。
*   `run_report_powershell.bat`: 启动脚本（运行 PowerShell 版）。
*   `config.json`: 配置文件，包含 API 地址、密钥、Cookie 等。
*   `提示词.md`: AI 生成周报时使用的指令（Prompt）。
*   `周报/`: 存放生成的周报文件。

## 🚀 快速开始

1.  **启动**: 双击 **`run_report_powershell.bat`**（推荐）或 **`run_report.bat`**。
2.  **等待**: 脚本会自动验证 Cookie、抓取数据、调用 AI，过程大约 10-30 秒。
3.  **结果**: 完成后，周报会保存在 `周报` 文件夹下，文件名为 `周报_YYYYMMDD.md`。

## 🔄 Cookie 共享功能 (新增)

本项目与 `tita-市场` 项目共享 Cookie，**无需单独维护**！

- **共享文件**: `f:\共享配置\tita_cookie.json`
- **刷新责任**: 由 `tita-市场` 项目负责刷新和保活
- **本项目**: 运行时自动从共享文件读取最新 Cookie

> 💡 只需在 `tita-市场` 刷新一次 Cookie，两个项目就都能用了！

## 🔄 Cookie 手动更新 (备用)

如果共享 Cookie 失效，脚本会自动检测并提示手动更新：

## ⚙️ 配置说明 (config.json)

所有关键参数都在 `config.json` 中：

| 字段 | 说明 |
|------|------|
| `tita_api_url` | Tita 日报 API 地址 |
| `ai_api_url` | 火山引擎 AI API 地址 |
| `ai_model_id` | AI 模型 ID |
| `ai_api_key` | AI API 密钥 |
| `headers.cookie` | Tita 登录凭证（自动更新） |
| `output_dir` | 周报保存目录 |

## 📝 修改周报格式 (提示词.md)

如果您希望周报的风格更正式、或包含特定板块：
1.  打开 `提示词.md`。
2.  直接修改其中的文本内容。
3.  **注意**: 请保留关于"输出格式"的指令，以免 AI 输出混乱的格式。

## 🛠️ 常见问题

| 问题 | 解决方案 |
|------|----------|
| Cookie 过期 | 按脚本提示更新即可，无需手动编辑文件 |
| PowerShell 乱码报错 | 确保 `.ps1` 文件为 **UTF-8 with BOM** 编码 |
| 找不到 requests 模块 | 运行 `pip install requests` |
| 未找到日报记录 | 检查是否已写当周日报 |
