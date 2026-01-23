import asyncio
import os
import json
import random
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# 除外ワードを一旦空にします（テストのため）
NG_WORDS = []
USER_AGENTS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"]

async def update_spreadsheet(data_list):
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets']
        key_json = json.loads(os.environ["GSPREAD_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(key_json, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open("Indevia.system").worksheet("02_Purchase_Control")
        
        rows = [[item['jan'], item['price'], item['shop'], item['url'], '', '', '', '', '', item['name']] for item in data_list]
        sheet.append_rows(rows)
        print(f"✅ {len(rows)}件をスプレッドシートに追記しました！")
    except Exception as e:
        print(f"❌ スプレッドシート更新エラー: {e}")

async def get_shop_data(page, shop_name, url, item_sel, name_sel, price_sel, keyword):
    await asyncio.sleep(2)
    results = []
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_selector(item_sel, timeout=10000)
        items = await page.query_selector_all(item_sel)
        
        for item in items[:3]:
            name = (await (await item.query_selector(name_sel)).inner_text()).strip()
            price_text = await (await item.query_selector(price_sel)).inner_text()
            price = int(''.join(filter(str.isdigit, price_text)))
            results.append({'jan': keyword, 'price': price, 'shop': shop_name, 'url': url, 'name': name})
    except:
        pass
    return results

async def main():
    # 検索ワードを「iPhone」という広い言葉にして、動作テストをします
    test_keyword = "iPhone" 
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENTS[0])
        page = await context.new_page()
        
        print(f"--- 動作テスト開始: {test_keyword} ---")
        all_res = []
        # じゃんぱらで「iPhone」を検索
        all_res.extend(await get_shop_data(page, "じゃんぱら", f"https://www.janpara.co.jp/sale/search/detail/?KEYWORDS={test_keyword}", ".search_result_item", ".item_name", ".price", test_keyword))

        if all_res:
            await update_spreadsheet(all_res)
        else:
            print("データが見つかりませんでした。サイトの構造が変わった可能性があります。")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
