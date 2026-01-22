#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 tita_logs.db 中的市场日志同步到飞书多维表格
"""

import json
import sqlite3
import requests
from datetime import datetime
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

def load_config():
    """加载配置文件"""
    config_path = BASE_DIR / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """获取飞书 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": app_id,
        "app_secret": app_secret
    }
    resp = requests.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"获取 access_token 失败: {data}")
    return data["tenant_access_token"]

def get_wiki_node_info(token: str, wiki_token: str) -> dict:
    """获取知识库节点信息，用于获取嵌入的多维表格的真实 app_token"""
    url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"token": wiki_token}
    
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    data = resp.json()
    
    if data.get("code") != 0:
        print(f"获取知识库节点信息失败: {data.get('msg')}")
        return {}
    
    return data.get("data", {}).get("node", {})

def make_dedup_key(name: str, log_date: str, content: str) -> str:
    """生成去重用的唯一键：姓名+日期+内容前100字符"""
    content_prefix = (content or "")[:100]
    return f"{name}|{log_date}|{content_prefix}"

def get_existing_records(token: str, app_token: str, table_id: str) -> set:
    """获取飞书表格中已存在的记录，用于去重"""
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}"}
    
    existing_keys = set()
    page_token = None
    
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") != 0:
            print(f"警告: 获取已有记录失败: {data.get('msg')}")
            break
        
        items = data.get("data", {}).get("items", [])
        for item in items:
            fields = item.get("fields", {})
            # 获取姓名（单选类型返回的是字符串或列表）
            name = fields.get("姓名", "")
            if isinstance(name, list):
                name = name[0] if name else ""
            # 获取日期（时间戳格式，转为日期字符串）
            log_date_ts = fields.get("日志日期")
            log_date = ""
            if log_date_ts:
                try:
                    log_date = datetime.fromtimestamp(log_date_ts / 1000).strftime("%Y-%m-%d")
                except:
                    pass
            # 获取内容
            content = fields.get("市场日志原文", "")
            if isinstance(content, list):
                content = content[0].get("text", "") if content else ""
            
            key = make_dedup_key(name, log_date, content)
            existing_keys.add(key)
        
        page_token = data.get("data", {}).get("page_token")
        if not page_token:
            break
    
    return existing_keys

def date_to_timestamp(date_str: str) -> int:
    """将日期字符串转换为毫秒时间戳"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp() * 1000)
    except:
        return int(datetime.now().timestamp() * 1000)

def sync_logs_to_feishu():
    """主同步函数"""
    print("=" * 50)
    print("    [SYNC] 同步市场日志到飞书多维表格")
    print("=" * 50)
    
    # 加载配置
    config = load_config()
    feishu_config = config.get("feishu", {})
    
    if not feishu_config:
        print("[ERROR] 错误: config.json 中缺少 feishu 配置")
        return
    
    app_id = feishu_config["app_id"]
    app_secret = feishu_config["app_secret"]
    app_token = feishu_config["app_token"]
    table_id = feishu_config["table_id"]
    
    # 获取 access_token
    print("\n[AUTH] 获取飞书 Access Token...")
    try:
        token = get_tenant_access_token(app_id, app_secret)
        print("   [OK] Token 获取成功")
    except Exception as e:
        print(f"   [FAIL] 获取 Token 失败: {e}")
        return
    
    # 尝试获取知识库嵌入表格的真实 app_token
    print("\n[INFO] 获取多维表格信息...")
    node_info = get_wiki_node_info(token, app_token)
    if node_info:
        obj_token = node_info.get("obj_token")
        obj_type = node_info.get("obj_type")
        print(f"   节点类型: {obj_type}")
        if obj_token:
            print(f"   真实 app_token: {obj_token}")
            app_token = obj_token
        else:
            print(f"   使用配置的 app_token: {app_token}")
    else:
        print(f"   使用配置的 app_token: {app_token}")
    
    # 获取已同步的记录
    print("\n[CHECK] 检查已同步的记录...")
    existing_keys = get_existing_records(token, app_token, table_id)
    print(f"   已有 {len(existing_keys)} 条记录")
    
    # 读取数据库
    print("\n[READ] 读取本地数据库...")
    db_path = BASE_DIR / "tita_logs.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT feed_id, user_name, log_date, content 
        FROM daily_logs 
        ORDER BY log_date DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    print(f"   共 {len(rows)} 条日志记录")
    
    # 筛选需要同步的记录
    to_sync = []
    for row in rows:
        feed_id, user_name, log_date, content = row
        user_name = user_name or "未知"
        content = content or ""
        key = make_dedup_key(user_name, log_date, content)
        if key not in existing_keys:
            to_sync.append({
                "feed_id": feed_id,
                "user_name": user_name,
                "log_date": log_date,
                "content": content
            })
    
    print(f"   需要同步 {len(to_sync)} 条新记录")
    
    if not to_sync:
        print("\n[OK] 没有新记录需要同步")
        return
    
    # 批量写入飞书
    print("\n[SYNC] 开始同步到飞书...")
    
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 分批处理，每批最多 500 条
    batch_size = 500
    success_count = 0
    fail_count = 0
    current_time = int(datetime.now().timestamp() * 1000)
    
    for i in range(0, len(to_sync), batch_size):
        batch = to_sync[i:i + batch_size]
        
        records = []
        for item in batch:
            records.append({
                "fields": {
                    "姓名": item["user_name"],  # 单选类型直接传字符串
                    "日志日期": date_to_timestamp(item["log_date"]),
                    "市场日志原文": item["content"],
                    "写入时间": current_time
                }
            })
        
        payload = {"records": records}
        
        try:
            resp = requests.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("code") == 0:
                success_count += len(batch)
                print(f"   [OK] 批次 {i // batch_size + 1}: 成功写入 {len(batch)} 条")
            else:
                fail_count += len(batch)
                print(f"   [FAIL] 批次 {i // batch_size + 1}: 写入失败 - {data.get('msg')}")
        except Exception as e:
            fail_count += len(batch)
            print(f"   [FAIL] 批次 {i // batch_size + 1}: 请求失败 - {e}")
    
    print("\n" + "=" * 50)
    print(f"[RESULT] 同步完成: 成功 {success_count} 条, 失败 {fail_count} 条")
    print("=" * 50)

if __name__ == "__main__":
    sync_logs_to_feishu()
