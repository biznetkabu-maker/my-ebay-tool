import os
import json
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# --- 設定 ---
RAKUTEN_APP_ID = os.environ.get("RAKUTEN_APP_ID")

def get_gspread_client():
    json_creds = os.environ.get("GSPREAD_SERVICE_ACCOUNT")
    creds_dict = json.loads(json_creds)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# 1. JANコードから商品名を楽天APIで取得
def get_product_name_by_jan(jan):
    if not RAKUTEN_APP_ID:
        return None
    url = f"https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601?format=json&itemCode={jan}&applicationId={RAKUTEN_APP_ID}"
    # itemCodeで直接ヒットしない場合があるので、キーワード検索も試す
    url_keyword = f"https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601?format=json&keyword={jan}&applicationId={RAKUTEN_APP_ID}"
    
    try:
        res = requests.get(url_keyword, timeout=10)
        data = res.json()
        if data.get("Items"):
            # 最初に見つかった商品のタイトルを取得
            full_name = data["Items"][0]["Item"]["itemName"]
            # 検索しやすくするため、最初の15文字程度を抽出（または特定のキーワードで整える）
            return full_name.split("【")[0].strip()[:20] 
        return None
    except:
        return None

# 2. 取得した商品名でじゃんぱらを検索
def check_janpara_by_name(product_name):
    if not product_name:
        return None
    url = f"https://www.janpara.co.jp/sale/search/result/?KEYWORDS={product_name}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.find_all(class_="item_list")
        
        valid_prices = []
        for item in items:
            price_tag = item.select_one(".item_price, .price_detail, .price")
            if price_tag:
                price_text = price_tag.get_text(strip=True).replace("￥", "").replace(",", "").replace("円", "")
                try:
                    valid_prices.append(int(price_text))
                except:
                    continue
        return min(valid_prices) if valid_prices else None
    except:
        return None

# メイン処理
def main():
    client = get_gspread_client()
    sheet = client.open_by_key(os.environ.get("SPREADSHEET_ID")).get_worksheet(0)
    jan_list = sheet.col_values(1)[1:] # A列のJANコード
    
    for i, jan in enumerate(jan_list, start=2):
        print(f"--- 行{i} 処理開始 ---")
        # まず商品名に変換
        product_name = get_product_name_by_jan(jan)
        print(f"JAN: {jan} -> 商品名推測: {product_name}")
        
        # 名前でじゃんぱらを検索
        price = check_janpara_by_name(product_name)
        print(f"結果価格: {price}")
        
        if price:
            sheet.update_cell(i, 2, price) # B列に価格
            sheet.update_cell(i, 3, product_name) # C列に検索に使用した名前
        
        time.sleep(3)

if __name__ == "__main__":
    main()
