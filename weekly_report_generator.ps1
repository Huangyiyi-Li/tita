# 自动周报生成器 PowerShell 版
# 该脚本不依赖 Python，直接使用 PowerShell 运行

# 设置控制台输出编码为 UTF-8，以正确显示中文
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 获取脚本所在目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$ConfigPath = Join-Path $ScriptDir "config.json"

# --- 1. 加载配置 ---
function Load-Config {
    if (-not (Test-Path $ConfigPath)) {
        Write-Host "(ERROR) 找不到配置文件 config.json" -ForegroundColor Red
        return $null
    }
    try {
        $JsonContent = Get-Content $ConfigPath -Raw -Encoding UTF8
        return $JsonContent | ConvertFrom-Json
    }
    catch {
        Write-Host "(ERROR) 读取配置文件失败 - $_" -ForegroundColor Red
        return $null
    }
}

# --- 保存配置 ---
function Save-Config {
    param ($Config)
    try {
        $Config | ConvertTo-Json -Depth 10 | Set-Content -Path $ConfigPath -Encoding UTF8
        return $true
    }
    catch {
        Write-Host "(ERROR) 保存配置文件失败 - $_" -ForegroundColor Red
        return $false
    }
}

# --- 检查 Cookie 是否有效 ---
function Test-CookieValid {
    param ($Config)
    
    $Url = $Config.tita_api_url
    $Headers = @{}
    $Config.headers.PSObject.Properties | ForEach-Object {
        $Headers[$_.Name] = $_.Value
    }
    
    $Payload = $Config.payload_template
    $BodyJson = $Payload | ConvertTo-Json -Depth 10
    
    try {
        $Response = Invoke-RestMethod -Uri $Url -Method Post -Headers $Headers -Body $BodyJson -ContentType "application/json" -TimeoutSec 10
        
        if ($Response.Code -eq 1) {
            return $true
        }
        
        $ErrorMsg = $Response.Message
        if ($ErrorMsg) {
            Write-Host "(WARNING) API 返回异常: $ErrorMsg" -ForegroundColor Yellow
        }
        return $false
    }
    catch {
        $ErrorResponse = $_.Exception.Response
        if ($ErrorResponse) {
            Write-Host "(WARNING) 请求失败，Cookie 可能已过期" -ForegroundColor Yellow
        }
        else {
            Write-Host "(ERROR) 网络请求失败: $_" -ForegroundColor Red
        }
        return $false
    }
}

# --- 更新 Cookie ---
function Update-Cookie {
    param ($Config)
    
    Write-Host ""
    Write-Host ("=" * 50) -ForegroundColor Cyan
    Write-Host "(NOTICE) Cookie 已过期，需要更新" -ForegroundColor Cyan
    Write-Host ("=" * 50) -ForegroundColor Cyan
    
    $TitaUrl = "https://work-weixin.tita.com/"
    
    Write-Host ""
    Write-Host "即将打开 Tita 页面: $TitaUrl"
    Write-Host "请按以下步骤获取新的 Cookie:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  1. 在打开的浏览器中扫码登录 Tita"
    Write-Host "  2. 登录成功后，按 F12 打开开发者工具"
    Write-Host "  3. 切换到 Network (网络) 选项卡"
    Write-Host "  4. 刷新页面，点击任意一个请求"
    Write-Host "  5. 在 Headers 中找到 Cookie 字段，复制完整的值"
    Write-Host ""
    Write-Host ("-" * 50)
    
    # 打开浏览器
    try {
        Start-Process $TitaUrl
        Write-Host "(INFO) 已在浏览器中打开 Tita 页面" -ForegroundColor Cyan
    }
    catch {
        Write-Host "(WARNING) 无法自动打开浏览器: $_" -ForegroundColor Yellow
        Write-Host "请手动访问: $TitaUrl"
    }
    
    Write-Host ""
    Write-Host "请粘贴新的 Cookie (输入后按 Enter):"
    Write-Host "(输入 'q' 或 'exit' 取消更新)" -ForegroundColor Gray
    
    $NewCookie = Read-Host ">"
    
    if ($NewCookie -eq "q" -or $NewCookie -eq "exit" -or $NewCookie -eq "quit" -or $NewCookie -eq "cancel") {
        Write-Host "(CANCELLED) 用户取消了更新" -ForegroundColor Yellow
        return $null
    }
    
    if ([string]::IsNullOrWhiteSpace($NewCookie)) {
        Write-Host "(ERROR) Cookie 不能为空" -ForegroundColor Red
        return $null
    }
    
    # 更新配置
    $Config.headers.cookie = $NewCookie
    
    # 保存到文件
    if (Save-Config -Config $Config) {
        Write-Host "(SUCCESS) 新 Cookie 已保存到 config.json" -ForegroundColor Green
        return $Config
    }
    else {
        Write-Host "(ERROR) 保存配置失败，请手动更新 config.json" -ForegroundColor Red
        return $null
    }
}

$CONFIG = Load-Config
if (-not $CONFIG) { exit }

# --- 2. 获取本周范围 ---
function Get-Current-Week-Range {
    $Today = Get-Date -Hour 0 -Minute 0 -Second 0 -Millisecond 0
    $DaysToMonday = if ($Today.DayOfWeek -eq 'Sunday') { 6 } else { $Today.DayOfWeek.value__ - 1 }
    $StartOfWeek = $Today.AddDays(-$DaysToMonday)
    $EndOfWeek = $StartOfWeek.AddDays(5)
    
    return @{ Start = $StartOfWeek; End = $EndOfWeek }
}

# --- 3. 获取日报 ---
function Fetch-Daily-Reports {
    param ($StartDate, $EndDate, $Config)
    
    Write-Host "(INFO) 正在从 Tita 获取日报..." -ForegroundColor Cyan

    $Url = $Config.tita_api_url
    $Headers = @{}
    $Config.headers.PSObject.Properties | ForEach-Object {
        $Headers[$_.Name] = $_.Value
    }
    
    $Payload = $Config.payload_template
    $BodyJson = $Payload | ConvertTo-Json -Depth 10

    try {
        $Response = Invoke-RestMethod -Uri $Url -Method Post -Headers $Headers -Body $BodyJson -ContentType "application/json"
        
        if ($Response.Code -ne 1) {
            Write-Host "(ERROR) 获取数据错误: $($Response.Message)" -ForegroundColor Red
            return @()
        }

        $Feeds = $Response.Data.feeds
        $FilteredReports = @()

        foreach ($Feed in $Feeds) {
            $DailyDateStr = $Feed.dailyDate
            if (-not $DailyDateStr) { continue }

            try {
                $DailyDate = [datetime]::ParseExact($DailyDateStr, "yyyy/MM/dd", $null)
            }
            catch { continue }

            if ($DailyDate -ge $StartDate -and $DailyDate -le $EndDate) {
                $ReportContent = ""
                $DailyContent = $Feed.dailyContent

                foreach ($Section in $DailyContent) {
                    $Title = $Section.title
                    $Content = $Section.content
                    if (($Title -eq "今日工作总结" -or $Title -eq "明日工作计划") -and $Content) {
                        $ReportContent += "[$Title]: $Content`n"
                    }
                }

                if ($ReportContent) {
                    $FilteredReports += "日期: $DailyDateStr`n$ReportContent"
                }
            }
        }
        
        $FilteredReports = $FilteredReports | Sort-Object
        return $FilteredReports
    }
    catch {
        Write-Host "(ERROR) 获取日报时发生异常: $_" -ForegroundColor Red
        return @()
    }
}

# --- 4. 生成周报汇总 ---
function Generate-Summary {
    param ($ReportsText, $PromptTemplate, $Config)
    
    Write-Host "(INFO) 正在发送请求给 AI 模型，请稍候..." -ForegroundColor Cyan

    $ApiUrl = $Config.ai_api_url
    $ApiKey = $Config.ai_api_key
    $ModelId = $Config.ai_model_id

    $Messages = @(
        @{ role = "system"; content = $PromptTemplate },
        @{ role = "user"; content = "以下是本周的日报记录，请汇总生成周报：`n`n$ReportsText" }
    )

    $Payload = @{
        model       = $ModelId
        messages    = $Messages
        temperature = 0.3
    }
    $BodyJson = $Payload | ConvertTo-Json -Depth 10 -Compress

    $Headers = @{
        "Content-Type"  = "application/json"
        "Authorization" = "Bearer $ApiKey"
    }

    try {
        $Response = Invoke-RestMethod -Uri $ApiUrl -Method Post -Headers $Headers -Body $BodyJson -TimeoutSec 60

        if ($Response.choices -and $Response.choices.Count -gt 0) {
            return $Response.choices[0].message.content
        }
        else {
            Write-Host "(WARNING) AI 响应格式异常" -ForegroundColor Yellow
            return $null
        }
    }
    catch {
        Write-Host "(ERROR) 调用 AI 接口失败: $_" -ForegroundColor Red
        return $null
    }
}

# --- Main Logic ---

Write-Host "=== 自动周报生成器 (PowerShell版) 启动 ===" -ForegroundColor Green

# 0. 验证 Cookie
Write-Host "(INFO) 正在验证 Cookie..."
if (-not (Test-CookieValid -Config $CONFIG)) {
    Write-Host "(WARNING) Cookie 已过期或无效" -ForegroundColor Yellow
    $CONFIG = Update-Cookie -Config $CONFIG
    if (-not $CONFIG) {
        Write-Host "(FAILED) 无法更新 Cookie，程序退出" -ForegroundColor Red
        exit
    }
    # 重新验证
    if (-not (Test-CookieValid -Config $CONFIG)) {
        Write-Host "(FAILED) 新 Cookie 仍然无效，请检查是否复制正确" -ForegroundColor Red
        exit
    }
    Write-Host "(SUCCESS) Cookie 验证通过!" -ForegroundColor Green
}
else {
    Write-Host "(SUCCESS) Cookie 有效" -ForegroundColor Green
}

# 1. Date Range
$WeekRange = Get-Current-Week-Range
$StartStr = $WeekRange.Start.ToString("yyyy-MM-dd")
$EndStr = $WeekRange.End.ToString("yyyy-MM-dd")
Write-Host "(INFO) 生成范围: $StartStr 至 $EndStr"

# 2. Fetch Reports
$Reports = Fetch-Daily-Reports -StartDate $WeekRange.Start -EndDate $WeekRange.End -Config $CONFIG

if ($Reports.Count -eq 0) {
    Write-Host "(WARNING) 未找到本周的日报记录。" -ForegroundColor Yellow
    Write-Host "(TIPS) 请检查：1. 是否已写日报；2. 日期范围是否正确。" -ForegroundColor Yellow
    exit
}

$ReportsText = $Reports -join "`n---`n"
Write-Host "(SUCCESS) 成功获取 $($Reports.Count) 条日报记录。" -ForegroundColor Green

# 3. Read Prompt
$PromptPath = Join-Path $ScriptDir "提示词.md"
if (-not (Test-Path $PromptPath)) {
    Write-Host "(ERROR) 找不到文件 '提示词.md'。" -ForegroundColor Red
    exit
}
$PromptTemplate = Get-Content $PromptPath -Raw -Encoding UTF8

# 4. Generate
$Summary = Generate-Summary -ReportsText $ReportsText -PromptTemplate $PromptTemplate -Config $CONFIG

if ($Summary) {
    # 5. Save
    $OutputDirName = if ($CONFIG.output_dir) { $CONFIG.output_dir } else { "周报" }
    $OutputDir = Join-Path $ScriptDir $OutputDirName
    if (-not (Test-Path $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir | Out-Null
    }

    $DateStr = (Get-Date).ToString("yyyyMMdd")
    $Filename = "周报_$DateStr.md"
    $FilePath = Join-Path $OutputDir $Filename

    $Summary | Out-File -FilePath $FilePath -Encoding utf8

    Write-Host "--------------------------------------------------" -ForegroundColor Green
    Write-Host "(DONE) 周报已生成！" -ForegroundColor Green
    Write-Host "文件位置: $FilePath"
    Write-Host "--------------------------------------------------" -ForegroundColor Green
}
else {
    Write-Host "(FAILED) 生成周报失败。" -ForegroundColor Red
}

