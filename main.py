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
        print("⚠️ 書き込むデータがないためスキップします。")
        return
    try:
        client = get_gspread_client()
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        rows = [[
            item['jan'],
            item['price'],
            item['shop'],
            item['url'],
            item.get('image', ''),
            item.get('category', ''),
            '', '', '', '',
            item['name']
        ] for item in data_list]
        sheet.append_rows(rows)
        print(f"✅ スプレッドシートに {len(rows)} 件書き込みました！")
    except Exception as e:
        print(f"❌ スプレッドシート書き込みエラー: {e}")

# --- Yahoo価格補完（Playwright） ---
async def scrape_yahoo_price(page, url):
    try:
        await page.goto(url, wait_until="load", timeout=60000)
        price_el = await page.query_selector('span[class*="Price__value"]')
        if price_el:
            price_text = await price_el.inner_text()
            price_match = re.search(r"[0-9,]+", price_text)
            if price_match:
                return int(price_match.group(0).replace(",", ""))
    except Exception as e:
        print(f"❌ Yahoo価格補完エラー: {e}")
    return None

# --- 楽天 ---
async def fetch_rakuten(keyword):
    app_id = os.getenv("RAKUTEN_APP_ID")
    if not app_id:
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
                return []
            items = res.json().get("Items", [])
            return [{
                "jan": i["Item"].get("janCode") or keyword,
                "name": i["Item"]["itemName"],
                "price": i["Item"]["itemPrice"],
                "shop": "楽天",
                "url": i["Item"]["itemUrl"],
                "image": i["Item"].get("mediumImageUrls", [{}])[0].get("imageUrl", ""),
                "category": i["Item"].get("genreId", "")
            } for i in items]
        except Exception:
            return []

# --- Yahoo（価格補完付き） ---
async def fetch_yahoo(keyword, page):
    client_id = os.getenv("YAHOO_CLIENT_ID")
    if not client_id:
        return []
    url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
    params = {
        "appid": client_id,
        "query": keyword,
        "results": 3,
        "sort": "+price"
    }
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, params=params)
            if res.status_code != 200:
                print(f"⚠️ YahooAPIエラー: Status {res.status_code}")
                return []
            hits = res.json().get("hits", [])
            results = []
            for h in hits:
                price = h.get("price")
                url = h.get("url")

                # price==1 → 補完
                if price == 1 and url:
                    price = await scrape_yahoo_price(page, url)

                results.append({
                    "jan": h.get("jan_code") or keyword,
                    "name": h.get("name"),
                    "price": price,
                    "shop": "Yahoo",
                    "url": url,
                    "image": h.get("image", {}).get("medium", ""),
                    "category": h.get("category_id", "")
                })
            return results
        except Exception:
            return []

# --- じゃんぱら ---
async def fetch_janpara(page, keyword):
    results = []
    try:
        url = f"https://www.janpara.co.jp/sale/search/detail/?KEYWORDS={keyword}"
        await page.goto(url, wait_until="load", timeout=60000)
        items = await page.query_selector_all("a")
        for item in items:
            text = await item.inner_text()
            href = await item.get_attribute("href")
            if text and "円" in text and href and "ITMCODE" in href:
                price_match = re.search(r"([0-9,]+)円", text.replace("\n", ""))
                if price_match:
                    price = int(price_match.group(1).replace(",", ""))
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    name = max(lines, key=len) if lines else keyword
                    results.append({
                        "jan": keyword,
                        "name": name,
                        "price": price,
                        "shop": "じゃんぱら",
                        "url": f"https://www.janpara.co.jp{href}",
                        "image": "",
                        "category": ""
                    })
            if len(results) >= 3:
                break
    except Exception as e:
        print(f"❌ じゃんぱら取得エラー: {e}")
    return results

# --- メイン ---
async def main():
    try:
        client = get_gspread_client()
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        keywords = [v for v in sheet.col_values(1)[1:] if v]
        if not keywords:
            print("❌ キーワードがありません")
            return
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            for keyword in keywords:
                print(f"🔍 '{keyword}' を検索中...")
                all_data = []
                all_data.extend(await fetch_rakuten(keyword))
                all_data.extend(await fetch_yahoo(keyword, page))
                all_data.extend(await fetch_janpara(page, keyword))
                print(f"📊 {keyword}: {len(all_data)} 件取得")
                await update_spreadsheet(all_data)
            await browser.close()
        line_notify("✅ Invedia Scraper 完了しました")
        print("--- 全工程終了 ---")
    except Exception as e:
        print(f"❌ エラー: {e}")
        line_notify(f"❌ Scraper エラー: {e}")

if __name__ == "__main__":
    asyncio.run(main())
