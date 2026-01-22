@echo off
chcp 65001 >nul
echo =========================================
echo    PyInstaller 打包脚本
echo =========================================
echo.

cd /d "%~dp0"

echo 正在检查 PyInstaller...
pip install pyinstaller -q

echo.
echo 正在打包，请稍候（约需 1-2 分钟）...
echo.

pyinstaller build.spec --clean --noconfirm

echo.
if exist "dist\自动周报生成器.exe" (
    echo =========================================
    echo    打包成功！
    echo =========================================
    echo.
    echo 生成的 exe 文件位置:
    echo   dist\自动周报生成器.exe
    echo.
    echo 请将以下文件一起复制给用户:
    echo   1. dist\自动周报生成器.exe
    echo   2. playwright_config.json (配置文件)
    echo   3. 提示词.md (AI提示词)
    echo.
) else (
    echo =========================================
    echo    打包失败，请检查错误信息
    echo =========================================
)

pause
