import asyncio
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def safe_text(item, selector):
    # エラーで止まらないようにtry-exceptを追加
    try:
        el = await item.query_selector(selector)
        if not el:
            return ""
        return (await el.inner_text()).strip()
    except:
        return ""

async def update_spreadsheet(data_list):
    try:
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]

        key_json_str = os.getenv("GSPREAD_SERVICE_ACCOUNT")
        if not key_json_str:
            raise RuntimeError("GSPREAD_SERVICE_ACCOUNT が設定されていません")

        key_json = json.loads(key_json_str)
        creds = Credentials.from_service_account_info(key_json, scopes=scope)
        client = gspread.authorize(creds)

        # ワークシート名を再確認してください
        sheet = client.open("Indevia.system").worksheet("02_Purchase_Control")

        rows = [
            [
                item['jan'], item['price'], item['shop'], item['url'],
                '', '', '', '', '', item['name']
            ]
            for item in data_list
        ]

        sheet.append_rows(rows)
        print(f"✅ スプレッドシートに {len(rows)} 件書き込みました！")

    except Exception as e:
        print(f"❌ スプレッドシート追記エラー: {e}")

async def main():
    keyword = "iPhone"
    async with async_playwright() as p:
        # 【修正1】headless=False にしてブラウザ画面を表示させる
        browser = await p.chromium.launch(headless=False, slow_mo=1000) 
        page = await browser.new_page()
        print("--- ブラウザ起動 ---")

        all_results = []

        try:
            target_url = f"https://netmall.hardoff.co.jp/search/?q={keyword}"
            print(f"アクセス中: {target_url}")
            
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            
            # 【修正2】最新のセレクタ構造に合わせて調整（汎用的なクラスに変更の可能性あり）
            # もし .p-result-card が見つからない場合、タイムアウトまで待機してしまいます
            # ここではまずページが正しく読み込まれたかタイトルなどを確認します
            print("ページ読み込み完了。要素を探します...")

            # 念のため少し待機
            await page.wait_for_timeout(3000)

            # NOTE: 現在のハードオフNetmallの商品カードのクラス名を確認する必要があります。
            # 以下は既存コードのままですが、もしここが古い場合はブラウザでF12キーを押し、
            # 商品カードの正しいクラス名を調べて書き換える必要があります。
            # 例: div[class*="item-card"] など
            
            # セレクタが見つかるかトライ（タイムアウトを短くして確認しやすくする）
            try:
                await page.wait_for_selector(".p-result-card", timeout=10000)
                items = await page.query_selector_all(".p-result-card")
                print(f"検索結果: {len(items)} 件見つかりました")
            except:
                print("⚠️ 指定したクラス名 (.p-result-card) が見つかりませんでした。")
                print("ブラウザ画面を見て、商品一覧が表示されているか、ログイン画面になっていないか確認してください。")
                items = []

            for item in items[:3]:
                name = await safe_text(item, ".p-result-card__title")
                price_text = await safe_text(item, ".p-result-card__price")
                
                # 価格の抽出ロジック（￥マークやカンマを除去）
                price = 0
                if price_text:
                    import re
                    nums = re.findall(r'\d+', price_text)
                    if nums:
                        price = int("".join(nums))

                print(f"取得データ: {name} / {price}円")

                all_results.append({
                    'jan': keyword, # JANの代わりに検索ワードを入れています
                    'name': name,
                    'price': price,
                    'shop': 'ハードオフ',
                    'url': target_url
                })

        except Exception as e:
            print(f"⚠️ スクレイピングエラー詳細: {e}")
            # エラー時も書き込み処理へ進む

        if not all_results:
            print("データが取得できなかったため、テストデータをセットします")
            all_results.append({
                'jan': 'TEST-FAIL',
                'name': '取得失敗（ブラウザ画面を確認してください）',
                'price': 0,
                'shop': 'SYSTEM',
                'url': '---'
            })

        await update_spreadsheet(all_results)
        
        # 確認のために少し待ってから閉じる
        await page.wait_for_timeout(5000) 
        await browser.close()
        print("--- 処理終了 ---")

if __name__ == "__main__":
    asyncio.run(main())
