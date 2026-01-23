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

# --- 共通：スプレッドシート操作 ---
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

        rows = [
            [item['jan'], item['price'], item['shop'], item['url'], '', '', '', '', '', item['name']]
            for item in data_list
        ]
        sheet.append_rows(rows)
        print(f"✅ スプレッドシートに {len(rows)} 件書き込みました！")
    except Exception as e:
        print(f"❌ スプレッドシート書き込みエラー: {e}")

# --- 1. 楽天 API ---
async def fetch_rakuten(keyword):
    app_id = os.getenv("RAKUTEN_APP_ID")
    if not app_id:
        print("⚠️ 楽天APP_IDがSecretsに設定されていません。")
        return []
    
    url = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
    params = {
        "applicationId": app_id,
        "keyword": keyword,
        "hits": 3,
        "format": "json",
        "sort": "+itemPrice"
    }
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, params=params)
            if res.status_code != 200:
                print(f"⚠️ 楽天APIエラー: Status {res.status_code}")
                return []
            items = res.json().get("Items", [])
            return [{
                'jan': keyword, 'name': i['Item']['itemName'], 'price': i['Item']['itemPrice'],
                'shop': '楽天', 'url': i['Item']['itemUrl']
            } for i in items]
        except Exception as e:
            print(f"⚠️ 楽天取得失敗: {e}")
            return []

# --- 2. Yahoo API ---
async def fetch_yahoo(keyword):
    client_id = os.getenv("YAHOO_CLIENT_ID")
    if not client_id:
        print("⚠️ YAHOO_CLIENT_IDがSecretsに設定されていません。")
        return []

    url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
    headers = {"User-Agent": f"YahooAppID: {client_id}"}
    params = {"query": keyword, "results": 3, "sort": "+price"}
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, params=params, headers=headers)
            if res.status_code != 200:
                print(f"⚠️ YahooAPIエラー: Status {res.status_code}")
                return []
            hits = res.json().get("hits", [])
            return [{
                'jan': keyword, 'name': h['name'], 'price': h['price'],
                'shop': 'Yahoo', 'url': h['url']
            } for h in hits]
        except Exception as e:
            print(f"⚠️ Yahoo取得失敗: {e}")
            return []

# --- 3. じゃんぱら Scraping ---
async def fetch_janpara(page, keyword):
    results = []
    try:
        url = f"https://www.janpara.co.jp/sale/search/detail/?KEYWORDS={keyword}"
        await page.goto(url, wait_until="load", timeout=60000)
        await page.wait_for_timeout(2000)
        
        # 商品リストのリンクを解析
        items = await page.query_selector_all('a')
        for item in items:
            text = await item.inner_text()
            href = await item.get_attribute('href')
            
            # 価格(円)が含まれ、かつ商品詳細へのリンクである場合
            if text and "円" in text and href and "ITMCODE" in href:
                # 数字だけ抽出して価格にする
                price_match = re.search(r'([0-9,]+)円', text.replace('\n', ''))
                if price_match:
                    price = int(price_match.group(1).replace(',', ''))
                    # 商品名はテキストの長い行を仮採用
                    name_lines = [l.strip() for l in text.split('\n') if l.strip()]
                    name = max(name_lines, key=len) if name_lines else keyword
                    
                    results.append({
                        'jan': keyword, 'name': name, 'price': price,
                        'shop': 'じゃんぱら', 'url': f"https://www.janpara.co.jp{href}"
                    })
            if len(results) >= 3: break
    except Exception as e:
        print(f"⚠️ じゃんぱらエラー: {e}")
    return results

# --- メイン処理 ---
async def main():
    try:
        # 1. スプレッドシートからA2セルのキーワードを読み取る
        client = get_gspread_client()
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        keyword = sheet.acell('A2').value  # A2セルの値を取得
        
        if not keyword:
            print("❌ A2セルにキーワードが入っていないため終了します。")
            return

        all_data = []
        print(f"🔍 キーワード '{keyword}' で検索を開始します...")

        # API系を実行
        all_data.extend(await fetch_rakuten(keyword))
        all_data.extend(await fetch_yahoo(keyword))

        # スクレイピング系を実行
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            all_data.extend(await fetch_janpara(page, keyword))
            await browser.close()

        # 結果表示と書き込み
        print(f"📊 合計 {len(all_data)} 件のデータが見つかりました。")
        await update_spreadsheet(all_data)
        print("--- 全工程終了 ---")

    except Exception as e:
        print(f"❌ メイン処理でエラーが発生しました: {e}")

if __name__ == "__main__":
    asyncio.run(main())
