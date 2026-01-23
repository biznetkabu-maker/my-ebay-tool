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
        print(f"❌ スプレッドシート書き込みエラー: {e}")

async def fetch_rakuten(keyword):
    app_id = os.getenv("RAKUTEN_APP_ID")
    if not app_id: return []
    url = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
    params = {"applicationId": app_id, "keyword": keyword, "hits": 3, "format": "json", "sort": "+itemPrice"}
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, params=params)
            if res.status_code == 200:
                items = res.json().get("Items", [])
                return [{'jan': keyword, 'name': i['Item']['itemName'], 'price': i['Item']['itemPrice'], 'shop': '楽天', 'url': i['Item']['itemUrl']} for i in items]
        except: pass
    return []

async def fetch_yahoo(keyword):
    client_id = os.getenv("YAHOO_CLIENT_ID")
    if not client_id: return []
    url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
    # Yahoo V3 APIは Client ID をそのまま送るのではなく、正しい認証形式が必要です
    headers = {"User-Agent": f"YahooAppID: {client_id}"}
    params = {"query": keyword, "results": 3, "sort": "+price"}
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, params=params, headers=headers)
            if res.status_code != 200:
                print(f"⚠️ YahooAPIエラー: Status {res.status_code} (IDが正しいか確認してください)")
                return []
            hits = res.json().get("hits", [])
            return [{'jan': keyword, 'name': h['name'], 'price': h['price'], 'shop': 'Yahoo', 'url': h['url']} for h in hits]
        except: pass
    return []

async def fetch_janpara(page, keyword):
    results = []
    try:
        url = f"https://www.janpara.co.jp/sale/search/detail/?KEYWORDS={keyword}"
        await page.goto(url, wait_until="load", timeout=60000)
        items = await page.query_selector_all('a')
        for item in items:
            text = await item.inner_text()
            href = await item.get_attribute('href')
            if text and "円" in text and href and "ITMCODE" in href:
                price_match = re.search(r'([0-9,]+)円', text.replace('\n', ''))
                if price_match:
                    price = int(price_match.group(1).replace(',', ''))
                    name = max([l.strip() for l in text.split('\n') if l.strip()], key=len)
                    results.append({'jan': keyword, 'name': name, 'price': price, 'shop': 'じゃんぱら', 'url': f"https://www.janpara.co.jp{href}"})
            if len(results) >= 3: break
    except: pass
    return results

async def main():
    try:
        client = get_gspread_client()
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        
        # A列の2行目から値が入っている分だけ取得するように改良
        keywords = [val for val in sheet.col_values(1)[1:] if val] 
        
        if not keywords:
            print("❌ 検索キーワードが見つかりません。")
            return

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            page = await context.new_page()

            for keyword in keywords:
                print(f"🔍 キーワード '{keyword}' で検索開始...")
                all_data = []
                all_data.extend(await fetch_rakuten(keyword))
                all_data.extend(await fetch_yahoo(keyword))
                all_data.extend(await fetch_janpara(page, keyword))
                
                print(f"📊 {keyword}: {len(all_data)} 件取得")
                await update_spreadsheet(all_data)

            await browser.close()
        print("--- 全工程終了 ---")
    except Exception as e:
        print(f"❌ エラー: {e}")

if __name__ == "__main__":
    asyncio.run(main())
