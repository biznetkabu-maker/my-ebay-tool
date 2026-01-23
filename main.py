import asyncio
import os
import json
import re
import gspread
import httpx
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# --- 設定 ---
SHEET_NAME = "Indevia.system"
WORKSHEET_NAME = "02_Purchase_Control"
LINE_TOKEN = os.getenv("LINE_NOTIFY_TOKEN")  # 任意

def line_notify(msg):
    if not LINE_TOKEN:
        return
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}"}
    data = {"message": msg}
    try:
        httpx.post(url, headers=headers, data=data, timeout=10)
    except:
        pass

def get_gspread_client():
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    env_json = os.getenv("GSPREAD_SERVICE_ACCOUNT")
    if not env_json:
        raise ValueError("❌ Secrets 'GSPREAD_SERVICE_ACCOUNT' が設定されていません。")
    key_json = json.loads(env_json)
    creds = Credentials.from_service_account_info(key_json, scopes=scope)
    return gspread.authorize(creds)

async def update_spreadsheet(data_list):
    if not data_list:
        print("⚠️ 書き込むデータがないためス
