import asyncio
import os
import json
import re
import gspread
import httpx
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# --- 設定エリア ---
SHEET_NAME = "Indevia.system"
WORKSHEET_NAME = "02_Purchase_Control"

def get_gspread_client():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    env_json = os.getenv("GSPREAD_SERVICE_ACCOUNT")
    if not env_json:
        raise ValueError("❌ Secrets 'GSPREAD_SERVICE_ACCOUNT' が設定されていません。")
    key_json = json.loads(env_json)
    creds = Credentials.from_service_account_info(key_json, scopes=scope)
    return gspread.authorize(creds)

async def update_spreadsheet(data_list):
    if not data_list:
        print("⚠️ 書き込むデータがないためスキップします。")
        return
    try:
        client = get_gspread_client()
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        rows = [[item['jan'], item['price'], item['shop'], item['url'], '', '', '', '', '', item['name']] for item in data_list]
        sheet.append_rows(rows)
        print(f"✅ スプレッドシートに {len(rows)} 件書き込みました！")
    except Exception as e:
        print
