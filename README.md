# Tita 工具集

Tita 平台日志相关工具，包括自动爬取日志同步到飞书、自动完成周报等。

## 📂 项目结构

```
tita/
├── tita-市场/                  # 日报分析系统
│   ├── tita_service.py         # 一体化服务（Web + 定时任务 + Cookie管理）
│   └── ...
│
├── weekly_report_generator.py  # 周报生成器（轻量版，仅生成文件）
├── playwright_weekly_report.py # 周报生成器（完整版，自动提交到Tita）
└── run_*.bat                   # 启动脚本
```

## 🚀 快速开始

### 周报生成器

1. 复制 `config.example.json` 为 `config.json`
2. 填写你的 API 密钥和 Cookie
3. 双击 `run_playwright.bat` 运行

### tita-市场 日报分析

1. 进入 `tita-市场/` 目录
2. 复制 `config.example.json` 为 `config.json`
3. 双击 `启动入口/start_service.bat`

## ⚙️ 配置说明

每个项目都有 `config.example.json` 配置模板，**config.json 已被 .gitignore 排除**，不会泄露敏感信息。

## 🔗 分支说明

| 分支 | 用途 |
|------|------|
| `master` | 共享Cookie版本（适合同时使用两个工具） |
| `standalone` | 独立版本（适合分享给他人） |

---

*更新时间: 2026-01-22*
